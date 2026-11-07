"""Bot Management API stub (bot-management-api.yaml) on :8000.

Real: validation, taxonomy checks, soft delete, pending->expired, listing.
Faked: the Telegram managed-bot flow. `creation_link` is a placeholder; use
the dev-only endpoint below to simulate the organizer confirming in Telegram.

Dev-only (not in the spec):
  POST /v1/_dev/bots/{bot_id}/activate   body {} or {"fail": "username_occupied"}
       -> activates the bot and returns its webhook `secret_token`, or marks it failed.
"""
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import hmac

from common import CLASSIFIER_URL, DEV_KEY, PUBLIC_URL, HttpError, db, error, http_json, serve

PENDING_TTL = timedelta(hours=24)
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,28}[Bb][Oo][Tt]$")
UUID_RE = r"([0-9a-fA-F-]{36})"
STATUSES = ["pending", "active", "failed", "expired", "deleted"]
DEFAULTS = {
    "start_message": "Перешлите мне сообщение, и я проверю его.",
    "non_text_message": "Пожалуйста, перешлите текстовое сообщение или пост с подписью.",
    "error_message": "Сейчас не удаётся проверить сообщение. Попробуйте позже.",
}
# field -> (required, min_len, max_len)
STRING_FIELDS = {
    "display_name": (True, 1, 64),
    "username": (True, 5, 32),
    "description": (False, 0, 512),
    "short_description": (False, 0, 120),
    "start_message": (False, 0, 4096),
    "non_text_message": (False, 0, 4096),
    "error_message": (False, 0, 4096),
    "other_response": (True, 1, 4096),
}
ALLOWED = set(STRING_FIELDS) | {"confidence_threshold", "responses"}


def now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def fetch_taxonomy():
    try:
        status, body = http_json("GET", f"{CLASSIFIER_URL}/taxonomy", timeout=5)
    except OSError as e:
        raise HttpError(503, error("model_unavailable", f"Classifier unreachable: {e}"))
    if status != 200:
        raise HttpError(503, error("model_unavailable", f"Classifier taxonomy returned {status}"))
    return body


def validate(cfg, taxonomy):
    if not isinstance(cfg, dict):
        raise HttpError(400, error("invalid_request", "Body must be a JSON object"))
    d = []

    def bad(field, issue):
        d.append({"field": field, "issue": issue})

    for k in cfg:
        if k not in ALLOWED:
            bad(k, "unknown_field")
    for k, (req, lo, hi) in STRING_FIELDS.items():
        if k not in cfg:
            if req:
                bad(k, "required")
            continue
        v = cfg[k]
        if not isinstance(v, str):
            bad(k, "wrong_type")
        elif not lo <= len(v) <= hi:
            bad(k, "out_of_range")
    if isinstance(cfg.get("username"), str) and not USERNAME_RE.match(cfg["username"]):
        bad("username", "pattern_mismatch")

    t = cfg.get("confidence_threshold")
    if t is None:
        bad("confidence_threshold", "required")
    elif isinstance(t, bool) or not isinstance(t, (int, float)):
        bad("confidence_threshold", "wrong_type")
    elif not 0 <= t <= 1:
        bad("confidence_threshold", "out_of_range")

    subs = {n["name"]: set(n["subnarratives"]) for n in taxonomy["narratives"]}
    responses = cfg.get("responses")
    if responses is None:
        bad("responses", "required")
    elif not isinstance(responses, list):
        bad("responses", "wrong_type")
    else:
        seen = set()
        for i, r in enumerate(responses):
            f = f"responses[{i}]"
            if not isinstance(r, dict):
                bad(f, "wrong_type")
                continue
            for k in r:
                if k not in ("narrative", "subnarrative", "text"):
                    bad(f"{f}.{k}", "unknown_field")
            for k in ("narrative", "subnarrative", "text"):
                if k not in r:
                    bad(f"{f}.{k}", "required")
            n, s, text = r.get("narrative"), r.get("subnarrative"), r.get("text")
            if "text" in r and (not isinstance(text, str) or not 1 <= len(text) <= 4096):
                bad(f"{f}.text", "out_of_range" if isinstance(text, str) else "wrong_type")
            if "narrative" in r:
                if not isinstance(n, str):
                    bad(f"{f}.narrative", "wrong_type")
                elif n not in subs:
                    bad(f"{f}.narrative", "unknown_narrative")
                elif s is not None and (not isinstance(s, str) or s not in subs[n]):
                    bad(f"{f}.subnarrative", "unknown_subnarrative")
            key = (n, s)
            if key in seen:
                bad(f, "duplicate_mapping")
            seen.add(key)
    if d:
        raise HttpError(422, error("validation_failed", f"{len(d)} problem(s) in config", d))
    return {**DEFAULTS, **cfg}


def to_api(row):
    """DB row -> Bot schema. Lazily expires pending bots. Never exposes secrets."""
    status = row["status"]
    if status == "pending" and row["expires_at"] and row["expires_at"] < iso(now()):
        with db() as c:
            c.execute("UPDATE bots SET status='expired' WHERE bot_id=? AND status='pending'", (row["bot_id"],))
        status = "expired"
    bot = {
        "bot_id": row["bot_id"],
        "status": status,
        "config": json.loads(row["config"]),
        "taxonomy_version": row["taxonomy_version"],
        "created_at": row["created_at"],
    }
    if status == "pending":
        bot["creation_link"] = row["creation_link"]
        bot["expires_at"] = row["expires_at"]
    if status == "active":
        bot["telegram_link"] = row["telegram_link"]
    if status == "failed":
        bot["failure_reason"] = row["failure_reason"]
    if status == "deleted":
        bot["deleted_at"] = row["deleted_at"]
    return bot


def get_row(bot_id):
    with db() as c:
        row = c.execute("SELECT * FROM bots WHERE bot_id=?", (bot_id.lower(),)).fetchone()
    if not row:
        raise HttpError(404, error("not_found", "No bot with this id"))
    return row


def get_taxonomy(req, m, body):
    return 200, fetch_taxonomy()


def create_bot(req, m, body):
    taxonomy = fetch_taxonomy()
    cfg = validate(body, taxonomy)
    bot_id = str(uuid.uuid4())
    created = now()
    with db() as c:
        c.execute(
            "INSERT INTO bots (bot_id, status, config, taxonomy_version, created_at, expires_at, creation_link)"
            " VALUES (?,?,?,?,?,?,?)",
            (bot_id, "pending", json.dumps(cfg, ensure_ascii=False), taxonomy["taxonomy_version"],
             iso(created), iso(created + PENDING_TTL),
             # Placeholder: the real link comes from Telegram's managed-bot flow.
             f"https://t.me/newbot/STUB_MANAGER_bot/{cfg['username']}?name={bot_id}"),
        )
    return 201, to_api(get_row(bot_id))


def list_bots(req, m, body):
    status = req.query.get("status")
    if status and status not in STATUSES:
        raise HttpError(400, error("invalid_request", f"status must be one of {STATUSES}"))
    try:
        limit = int(req.query.get("limit", 50))
        offset = int(req.query.get("cursor") or 0)
        assert 1 <= limit <= 200 and offset >= 0
    except (ValueError, AssertionError):
        raise HttpError(400, error("invalid_request", "limit must be 1-200; cursor must come from next_cursor"))
    with db() as c:
        rows = c.execute("SELECT * FROM bots ORDER BY created_at DESC, bot_id LIMIT ? OFFSET ?",
                         (limit + 1, offset)).fetchall()
    bots = [to_api(r) for r in rows]
    more = len(bots) > limit
    bots = bots[:limit]
    if status:  # filter after lazy expiry so `expired` is accurate (fine at stub scale)
        bots = [b for b in bots if b["status"] == status]
    return 200, {"bots": bots, "next_cursor": str(offset + limit) if more else None}


def get_bot(req, m, body):
    return 200, to_api(get_row(m.group(1)))


def delete_bot(req, m, body):
    row = get_row(m.group(1))
    if row["status"] != "deleted":
        with db() as c:
            # Real impl: also call deleteWebhook with the bot's token.
            c.execute("UPDATE bots SET status='deleted', deleted_at=?, creation_link=NULL WHERE bot_id=?",
                      (iso(now()), row["bot_id"]))
    return 204, None


def dev_activate(req, m, body):
    if DEV_KEY and not hmac.compare_digest((req.headers.get("X-Dev-Key") or "").encode(), DEV_KEY.encode()):
        raise HttpError(403, error("invalid_request", "Missing or wrong X-Dev-Key"))
    row = get_row(m.group(1))
    if to_api(row)["status"] != "pending":
        raise HttpError(409, error("invalid_request", f"Bot is {to_api(row)['status']}, not pending"))
    fail = (body or {}).get("fail")
    with db() as c:
        if fail:
            c.execute("UPDATE bots SET status='failed', failure_reason=? WHERE bot_id=?", (fail, row["bot_id"]))
            return 200, {"status": "failed", "failure_reason": fail}
        secret = secrets.token_urlsafe(32)
        username = json.loads(row["config"])["username"]
        c.execute("UPDATE bots SET status='active', secret_token=?, telegram_link=?, telegram_token=?"
                  " WHERE bot_id=?",
                  (secret, f"https://t.me/{username}", (body or {}).get("telegram_token"), row["bot_id"]))
    return 200, {"status": "active", "secret_token": secret,
                 "webhook_url": f"{PUBLIC_URL or 'http://127.0.0.1:8002'}/webhook/{row['bot_id']}"}


ROUTES = [
    ("GET", r"/v1/taxonomy", get_taxonomy),
    ("GET", r"/v1/bots", list_bots),
    ("POST", r"/v1/bots", create_bot),
    ("GET", rf"/v1/bots/{UUID_RE}", get_bot),
    ("DELETE", rf"/v1/bots/{UUID_RE}", delete_bot),
    ("POST", rf"/v1/_dev/bots/{UUID_RE}/activate", dev_activate),
]

if __name__ == "__main__":
    db().close()
    serve(ROUTES, 8000, "management")
