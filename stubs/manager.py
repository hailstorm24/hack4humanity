"""The manager bot: the Telegram bot that creates and manages organizers' bots.

Stage 3:
- At startup, if MANAGER_BOT_TOKEN is set: getMe (learn our username and check
  `can_manage_bots`), then setWebhook to {PUBLIC_URL}/telegram/manager.
- POST /telegram/manager receives the manager bot's updates. Updates without the
  right X-Telegram-Bot-Api-Secret-Token are dropped. Other private messages get
  a short intro.
- GET /v1/_dev/manager (X-Dev-Key) reports getMe + getWebhookInfo, without
  secrets, so hosted setups can be checked without a phone.

Stage 4:
- `/start <bot_id>` (the creation_link) claims a pending bot for the sender:
  stores organizer_tg_id + claimed_at, then replies with a request_managed_bot
  button pre-filled with display_name and username. Unknown, expired, active
  or deleted bots get an explanation instead. The latest opener wins while the
  bot is pending.
- A `managed_bot` update is matched to the creator's claimed pending bot:
  the one whose config.username equals the new bot's username, else the most
  recently claimed. The match stores telegram_bot_id + telegram_username; the
  bot stays `pending` until Stage 5 activates it. Updates for a bot that is
  already linked (token or owner changes) are left for Stage 7.

The webhook secret is derived from the token (HMAC), so there is no extra
secret to configure, and it changes automatically if the token is rotated.

Without MANAGER_BOT_TOKEN everything still runs; creation links use
MANAGER_BOT_USERNAME (default STUB_MANAGER_bot) and the route rejects all updates.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone

import telegram
from common import DEV_KEY, PUBLIC_URL, HttpError, db, error

TOKEN = os.environ.get("MANAGER_BOT_TOKEN", "")
WEBHOOK_PATH = "/telegram/manager"
ALLOWED_UPDATES = ["message", "managed_bot"]
INTRO = ("Привет! Я создаю боты для проверки сообщений на пропагандистские нарративы. "
         "Чтобы создать бота, откройте ссылку из панели организатора.")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
TEXT = {
    "invalid": "Эта ссылка недействительна. Создайте бота заново в панели организатора.",
    "expired": "Срок действия этой ссылки истёк. Создайте бота заново в панели организатора.",
    "active": "Этот бот уже создан: {link}",
    "create": ("Нажмите кнопку ниже, чтобы создать бота «{name}». "
               "Telegram покажет предложенные имя и адрес — их можно изменить."),
    "button": "Создать бота",
    "linked": "Бот @{username} создан. Завершаю настройку…",
    "unmatched": ("Бот @{username} создан, но я не нашёл ожидающей заявки. "
                  "Откройте ссылку из панели организатора и создайте бота через кнопку."),
}

_state = {"username": os.environ.get("MANAGER_BOT_USERNAME", "STUB_MANAGER_bot"),
          "can_manage_bots": None, "webhook_set": False, "startup_error": None}
_lock = threading.Lock()


def log(msg):
    print(f"[manager] {msg}", file=sys.stderr)


def username():
    """Manager bot's username for creation links (from getMe once started)."""
    return _state["username"]


def webhook_secret():
    if not TOKEN:
        return ""
    digest = hmac.new(TOKEN.encode(), b"h4h-manager-webhook-v1", hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")  # 43 chars of A-Z a-z 0-9 _ -


def startup():
    """Check the manager bot and register its webhook. Never raises: the API must start anyway."""
    if not TOKEN:
        log("MANAGER_BOT_TOKEN not set; manager bot disabled (creation links use a placeholder)")
        return
    try:
        me = telegram.get_me(TOKEN)
        with _lock:
            _state["username"] = me["username"]
            _state["can_manage_bots"] = bool(me.get("can_manage_bots"))
        log(f"manager bot @{me['username']}, can_manage_bots={_state['can_manage_bots']}")
        if not _state["can_manage_bots"]:
            log("WARNING: bot management is off. Enable it in @BotFather's Mini App, or creation will fail.")
        if not PUBLIC_URL:
            log("PUBLIC_URL unknown; not registering the webhook")
            return
        telegram.set_webhook(TOKEN, PUBLIC_URL + WEBHOOK_PATH, webhook_secret(), allowed_updates=ALLOWED_UPDATES)
        _state["webhook_set"] = True
        log(f"webhook set to {PUBLIC_URL}{WEBHOOK_PATH}")
    except telegram.TelegramError as e:
        _state["startup_error"] = str(e)
        log(f"startup failed: {e}")


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def request_id_for(bot_id):
    """Stable signed-32-bit-safe id for the request_managed_bot button."""
    return int(hashlib.sha256(bot_id.encode()).hexdigest()[:7], 16)  # < 2^28


def reply(chat_id, text, reply_markup=None):
    try:
        telegram.send_message(TOKEN, chat_id, text, reply_markup=reply_markup)
    except telegram.TelegramError as e:
        log(f"reply failed: {e}")


def handle_start(msg, payload):
    """/start <bot_id>: claim the pending bot and offer the create button."""
    chat_id, user_id = msg["chat"]["id"], (msg.get("from") or {}).get("id")
    if not UUID_RE.match(payload) or user_id is None:
        return reply(chat_id, TEXT["invalid"])
    bot_id = payload.lower()
    with db() as c:
        row = c.execute("SELECT * FROM bots WHERE bot_id=?", (bot_id,)).fetchone()
        if not row or row["status"] in ("deleted", "failed"):
            return reply(chat_id, TEXT["invalid"])
        if row["status"] == "active":
            return reply(chat_id, TEXT["active"].format(link=row["telegram_link"]))
        if row["status"] == "expired" or (row["expires_at"] and row["expires_at"] < now_iso()):
            return reply(chat_id, TEXT["expired"])
        if row["telegram_bot_id"] is not None:
            return reply(chat_id, TEXT["linked"].format(username=row["telegram_username"]))
        c.execute("UPDATE bots SET organizer_tg_id=?, claimed_at=? WHERE bot_id=? AND status='pending'",
                  (user_id, now_iso(), bot_id))
    cfg = json.loads(row["config"])
    log(f"claim: bot {bot_id} by tg user {user_id}")
    keyboard = telegram.request_managed_bot_keyboard(
        TEXT["button"], request_id_for(bot_id), cfg["display_name"], cfg["username"])
    reply(chat_id, TEXT["create"].format(name=cfg["display_name"]), keyboard)


def handle_managed_bot(mb):
    """managed_bot update: link the new Telegram bot to the creator's pending record."""
    creator, tg_bot = mb.get("user") or {}, mb.get("bot") or {}
    tg_bot_id, tg_username = tg_bot.get("id"), tg_bot.get("username") or ""
    if creator.get("id") is None or tg_bot_id is None:
        return log(f"managed_bot: malformed update {mb!r}")
    with db() as c:
        if c.execute("SELECT 1 FROM bots WHERE telegram_bot_id=?", (tg_bot_id,)).fetchone():
            return log(f"managed_bot: @{tg_username} already linked (token/owner change: Stage 7)")
        candidates = c.execute(
            "SELECT * FROM bots WHERE organizer_tg_id=? AND status='pending' AND telegram_bot_id IS NULL"
            " AND (expires_at IS NULL OR expires_at > ?) ORDER BY claimed_at DESC",
            (creator["id"], now_iso())).fetchall()
        if not candidates:
            log(f"managed_bot: no pending claim for tg user {creator['id']} (bot @{tg_username})")
            return reply(creator["id"], TEXT["unmatched"].format(username=tg_username),
                         {"remove_keyboard": True})
        by_name = [r for r in candidates
                   if json.loads(r["config"])["username"].lower() == tg_username.lower()]
        row = (by_name or candidates)[0]
        c.execute("UPDATE bots SET telegram_bot_id=?, telegram_username=? WHERE bot_id=? AND status='pending'",
                  (tg_bot_id, tg_username, row["bot_id"]))
    how = "username" if by_name else "most recent claim"
    log(f"match: @{tg_username} ({tg_bot_id}) -> bot {row['bot_id']} by {how}"
        f" ({len(candidates)} candidate(s)); activation is Stage 5")
    reply(creator["id"], TEXT["linked"].format(username=tg_username), {"remove_keyboard": True})


def handle_update(req, m, update):
    """POST /telegram/manager. Always 200 so Telegram doesn't retry."""
    given = req.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
    expected = webhook_secret()
    if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
        log("drop: bad or missing secret")
        return 200, None
    if not isinstance(update, dict):
        return 200, None

    if isinstance(update.get("managed_bot"), dict):
        handle_managed_bot(update["managed_bot"])
        return 200, None

    msg = update.get("message")
    if not isinstance(msg, dict) or (msg.get("chat") or {}).get("type") != "private":
        return 200, None
    if "managed_bot_created" in msg:
        return 200, None  # service message; the managed_bot update carries what we need
    parts = (msg.get("text") or "").split(maxsplit=1)
    if parts and parts[0].split("@")[0] == "/start" and len(parts) == 2:
        handle_start(msg, parts[1].strip())
    else:
        reply(msg["chat"]["id"], INTRO)
    return 200, None


def dev_status(req, m, body):
    """GET /v1/_dev/manager: is the manager bot set up? No secrets in the output."""
    if DEV_KEY and not hmac.compare_digest((req.headers.get("X-Dev-Key") or "").encode(), DEV_KEY.encode()):
        raise HttpError(403, error("invalid_request", "Missing or wrong X-Dev-Key"))
    out = {"configured": bool(TOKEN), "username": username(), "expected_webhook_url":
           (PUBLIC_URL + WEBHOOK_PATH) if PUBLIC_URL else None, "startup_error": _state["startup_error"]}
    if TOKEN:
        try:
            me = telegram.get_me(TOKEN)
            info = telegram.get_webhook_info(TOKEN)
            out.update({
                "can_manage_bots": bool(me.get("can_manage_bots")),
                "webhook_url": info.get("url"),
                "allowed_updates": info.get("allowed_updates"),
                "pending_update_count": info.get("pending_update_count"),
                "last_error_message": info.get("last_error_message"),
                "last_error_date": info.get("last_error_date"),
            })
        except telegram.TelegramError as e:
            out["telegram_error"] = str(e)
    return 200, out


ROUTES = [
    ("POST", WEBHOOK_PATH, handle_update),
    ("GET", r"/v1/_dev/manager", dev_status),
]
