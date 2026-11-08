"""The manager bot: the Telegram bot that creates and manages organizers' bots.

Stage 3 (this file today):
- At startup, if MANAGER_BOT_TOKEN is set: getMe (learn our username and check
  `can_manage_bots`), then setWebhook to {PUBLIC_URL}/telegram/manager.
- POST /telegram/manager receives the manager bot's updates. Updates without the
  right X-Telegram-Bot-Api-Secret-Token are dropped. For now it answers any
  private message with a short intro; Stage 4 adds `/start <bot_id>` and the
  create button, and Stage 5 handles `managed_bot` updates.
- GET /v1/_dev/manager (X-Dev-Key) reports getMe + getWebhookInfo, without
  secrets, so hosted setups can be checked without a phone.

The webhook secret is derived from the token (HMAC), so there is no extra
secret to configure, and it changes automatically if the token is rotated.

Without MANAGER_BOT_TOKEN everything still runs; creation links use
MANAGER_BOT_USERNAME (default STUB_MANAGER_bot) and the route rejects all updates.
"""
import base64
import hashlib
import hmac
import os
import sys
import threading

import telegram
from common import DEV_KEY, PUBLIC_URL, HttpError, error

TOKEN = os.environ.get("MANAGER_BOT_TOKEN", "")
WEBHOOK_PATH = "/telegram/manager"
ALLOWED_UPDATES = ["message", "managed_bot"]
INTRO = ("Привет! Я создаю боты для проверки сообщений на пропагандистские нарративы. "
         "Чтобы создать бота, откройте ссылку из панели организатора.")

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


def handle_update(req, m, update):
    """POST /telegram/manager. Always 200 so Telegram doesn't retry."""
    given = req.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
    expected = webhook_secret()
    if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
        log("drop: bad or missing secret")
        return 200, None
    if not isinstance(update, dict):
        return 200, None

    if "managed_bot" in update:
        mb = update["managed_bot"]
        log(f"managed_bot update: creator={mb.get('user', {}).get('id')} bot=@{mb.get('bot', {}).get('username')}"
            " (activation arrives in Stage 5)")
        return 200, None

    msg = update.get("message")
    if not isinstance(msg, dict) or (msg.get("chat") or {}).get("type") != "private":
        return 200, None
    if "managed_bot_created" in msg:
        return 200, None  # service message; the managed_bot update carries what we need
    try:
        telegram.send_message(TOKEN, msg["chat"]["id"], INTRO)
    except telegram.TelegramError as e:
        log(f"reply failed: {e}")
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
