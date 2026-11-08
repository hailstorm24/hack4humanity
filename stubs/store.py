"""Bot storage: SQLite locally, Postgres when DATABASE_URL is set.

Callers use `db()` as a context manager and write SQLite-style `?` placeholders:

    with db() as c:
        row = c.execute("SELECT * FROM bots WHERE bot_id=?", (bot_id,)).fetchone()
        row["status"]

The block commits on success, rolls back on error, and releases the
connection. Rows support `row["column"]` on both backends.

Postgres connections are pooled: opening one costs a TLS handshake to Neon, and
a burst of demo traffic opened one per request. Up to DB_POOL_MAX (default 10)
idle connections are kept, each reused only within POOL_IDLE_SECONDS (60) of
its last use, so one the server dropped while idle isn't handed out. Broken or
mid-transaction connections are closed, never pooled. SQLite isn't pooled.

Postgres needs `psycopg` (see requirements.txt). It is imported only when
DATABASE_URL is set, so local SQLite runs stay dependency-free.
"""
import os
import sqlite3
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_PATH = os.environ.get("STUB_DB", os.path.join(HERE, "data.db"))
BACKEND = "postgres" if DATABASE_URL.startswith(("postgres://", "postgresql://")) else "sqlite"

# Every column of `bots`, in order. New columns go at the end; _ensure_schema
# adds any that an older database is missing.
COLUMNS = [
    ("bot_id", "TEXT PRIMARY KEY"),
    ("status", "TEXT NOT NULL"),
    ("config", "TEXT NOT NULL"),            # BotConfig JSON, defaults filled in
    ("taxonomy_version", "TEXT NOT NULL"),
    ("created_at", "TEXT NOT NULL"),         # ISO 8601 UTC; text sorts correctly
    ("expires_at", "TEXT"),
    ("creation_link", "TEXT"),
    ("telegram_link", "TEXT"),
    ("failure_reason", "TEXT"),
    ("deleted_at", "TEXT"),
    ("secret_token", "TEXT"),                # webhook secret we generate per bot
    ("telegram_token", "TEXT"),              # dev/testing only; Stage 5 fetches tokens via getManagedBotToken instead
    # Added for real Telegram creation (Stage 0 decisions)
    ("telegram_bot_id", "BIGINT"),           # managed bot's Telegram user id
    ("organizer_tg_id", "BIGINT"),           # organizer's Telegram user id, learned from /start <bot_id>
    ("telegram_username", "TEXT"),           # actual username; may differ from config.username
    ("claimed_at", "TEXT"),                  # when organizer_tg_id last opened the /start link
]
# Managed bots Telegram created for someone with no claimed pending record yet
# (e.g. they used the t.me/newbot link before opening a creation link). Linked
# and removed when that person next opens a creation link.
EXTRA_TABLES = [
    "CREATE TABLE IF NOT EXISTS orphan_bots (\n"
    "    telegram_bot_id BIGINT PRIMARY KEY,\n"
    "    creator_tg_id BIGINT NOT NULL,\n"
    "    telegram_username TEXT,\n"
    "    seen_at TEXT NOT NULL\n"
    ")",
    "CREATE INDEX IF NOT EXISTS orphan_bots_creator ON orphan_bots (creator_tg_id)",
]
INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS bots_telegram_bot_id ON bots (telegram_bot_id) WHERE telegram_bot_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS bots_organizer_status ON bots (organizer_tg_id, status)",
    "CREATE INDEX IF NOT EXISTS bots_created_at ON bots (created_at)",
]

_ready = False
_ready_lock = threading.Lock()
POOL_MAX = int(os.environ.get("DB_POOL_MAX", "10"))
POOL_IDLE_SECONDS = 60
_pool = []  # [(raw psycopg connection, last used monotonic time)], most recent last
_pool_lock = threading.Lock()


class _Conn:
    """Uniform wrapper: `?` placeholders, dict-like rows, commit/rollback/close on exit."""

    def __init__(self, raw, pg, pooled=False):
        self._raw, self._pg, self._pooled = raw, pg, pooled

    def execute(self, sql, params=()):
        if not self._pg:
            return self._raw.execute(sql, params)
        sql = sql.replace("?", "%s")
        if not self._pooled:
            return self._raw.execute(sql, params)
        self._pooled = False  # only the first statement may be retried: nothing has run yet
        import psycopg
        try:
            return self._raw.execute(sql, params)
        except psycopg.OperationalError:
            # The server dropped it while idle (e.g. Neon restarted): the rest of the pool
            # is likely dead too. Start over on a fresh connection.
            _close_quietly(self._raw)
            _drain_pool()
            self._raw = _pg_new()
            return self._raw.execute(sql, params)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        ok = False
        try:
            if exc_type is None:
                self._raw.commit()
            else:
                self._raw.rollback()
            ok = True
        finally:
            if not (ok and self._pg and _release(self._raw)):
                _close_quietly(self._raw)
        return False


def _close_quietly(raw):
    try:
        raw.close()
    except Exception:  # noqa: BLE001 - already broken; nothing else to do
        pass


def _drain_pool():
    with _pool_lock:
        stale, _pool[:] = [r for r, _ in _pool], []
    for raw in stale:
        _close_quietly(raw)


def _pg_new():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)


def _release(raw):
    """Return a healthy, idle Postgres connection to the pool. False if the caller should close it."""
    import psycopg
    if raw.closed or raw.broken or raw.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        return False
    with _pool_lock:
        if len(_pool) >= POOL_MAX:
            return False
        _pool.append((raw, time.monotonic()))
    return True


def _pg_checkout():
    """The most recently used pooled connection, if used within POOL_IDLE_SECONDS; else None.

    The pool is ordered by last use, so once the newest is too old, all of them are: drop them all.
    """
    with _pool_lock:
        if _pool and time.monotonic() - _pool[-1][1] <= POOL_IDLE_SECONDS:
            raw = _pool[-1][0]
            if not raw.closed and not raw.broken:
                _pool.pop()
                return raw
    _drain_pool()
    return None


def _connect():
    if BACKEND == "postgres":
        raw = _pg_checkout()
        return _Conn(raw, pg=True, pooled=True) if raw is not None else _Conn(_pg_new(), pg=True)
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    raw = sqlite3.connect(DB_PATH, timeout=5)
    raw.row_factory = sqlite3.Row
    return _Conn(raw, pg=False)


def _ensure_schema(c):
    cols = ",\n    ".join(f"{name} {kind}" for name, kind in COLUMNS)
    c.execute(f"CREATE TABLE IF NOT EXISTS bots (\n    {cols}\n)")
    if BACKEND == "postgres":
        have = {r["column_name"] for r in c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'bots'").fetchall()}
    else:
        have = {r["name"] for r in c.execute("PRAGMA table_info(bots)").fetchall()}
    for name, kind in COLUMNS:
        if name not in have:
            c.execute(f"ALTER TABLE bots ADD COLUMN {name} {kind}")
    for sql in INDEXES + EXTRA_TABLES:
        c.execute(sql)


def db():
    """Open a connection, creating or upgrading the schema on first use in this process."""
    global _ready
    if not _ready:
        with _ready_lock:
            if not _ready:
                with _connect() as c:
                    _ensure_schema(c)
                _ready = True
    return _connect()


def init():
    """Create or upgrade the schema now (fail fast at startup) and say where data lives."""
    with db():
        pass
    return describe()


def describe():
    """Where data lives, for startup logs (never prints credentials)."""
    if BACKEND == "postgres":
        host = DATABASE_URL.split("@", 1)[-1].split("/", 1)[0].split("?", 1)[0]
        return f"postgres @ {host}"
    return f"sqlite @ {DB_PATH}"
