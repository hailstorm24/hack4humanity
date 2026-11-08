"""Bot storage: SQLite locally, Postgres when DATABASE_URL is set.

Callers use `db()` as a context manager and write SQLite-style `?` placeholders:

    with db() as c:
        row = c.execute("SELECT * FROM bots WHERE bot_id=?", (bot_id,)).fetchone()
        row["status"]

The block commits on success, rolls back on error, and always closes the
connection. Rows support `row["column"]` on both backends.

Postgres needs `psycopg` (see requirements.txt). It is imported only when
DATABASE_URL is set, so local SQLite runs stay dependency-free.
"""
import os
import sqlite3
import threading

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
]
INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS bots_telegram_bot_id ON bots (telegram_bot_id) WHERE telegram_bot_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS bots_organizer_status ON bots (organizer_tg_id, status)",
    "CREATE INDEX IF NOT EXISTS bots_created_at ON bots (created_at)",
]

_ready = False
_ready_lock = threading.Lock()


class _Conn:
    """Uniform wrapper: `?` placeholders, dict-like rows, commit/rollback/close on exit."""

    def __init__(self, raw, pg):
        self._raw, self._pg = raw, pg

    def execute(self, sql, params=()):
        if self._pg:
            sql = sql.replace("?", "%s")
        return self._raw.execute(sql, params)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._raw.commit()
            else:
                self._raw.rollback()
        finally:
            self._raw.close()
        return False


def _connect():
    if BACKEND == "postgres":
        import psycopg
        from psycopg.rows import dict_row
        return _Conn(psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10), pg=True)
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
    for sql in INDEXES:
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
