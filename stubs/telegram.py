"""Minimal Telegram Bot API client. Stdlib only.

Every call is `POST {TELEGRAM_API_BASE}/bot<token>/<method>` with a JSON body,
and every response is `{"ok": true, "result": ...}` or
`{"ok": false, "error_code": ..., "description": ..., "parameters": {...}}`.

- TELEGRAM_API_BASE defaults to https://api.telegram.org. Tests point it at
  tests/fake_telegram.py.
- Errors raise TelegramError. Tokens never appear in error messages or logs.
- A 429 (flood control) is retried once if Telegram asks to wait 5 s or less.

Method and field names follow the Bot API docs (Bot API 10.0, May 2026):
https://core.telegram.org/bots/api
"""
import json
import os
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
MAX_RETRY_WAIT = 5  # seconds


class TelegramError(Exception):
    """A failed Bot API call. `code` is Telegram's error_code, or None for network errors."""

    def __init__(self, method, code, description, retry_after=None):
        self.method, self.code, self.description, self.retry_after = method, code, description, retry_after
        super().__init__(f"{method}: {code or 'network'} {description}")


def _redact(text, token):
    return text.replace(token, "<token>") if token else text


def call(token, method, params=None, timeout=10, _retried=False):
    """Call one Bot API method and return its `result`."""
    url = f"{API_BASE}/bot{token}/{method}"
    data = json.dumps({k: v for k, v in (params or {}).items() if v is not None}).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except ValueError:
            raise TelegramError(method, e.code, "non-JSON error response") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise TelegramError(method, None, _redact(str(e), token)) from None

    if body.get("ok"):
        return body.get("result")
    code = body.get("error_code")
    desc = _redact(body.get("description") or "unknown error", token)
    retry_after = (body.get("parameters") or {}).get("retry_after")
    if code == 429 and retry_after is not None and retry_after <= MAX_RETRY_WAIT and not _retried:
        time.sleep(retry_after)
        return call(token, method, params, timeout, _retried=True)
    raise TelegramError(method, code, desc, retry_after)


# --- Bots ---------------------------------------------------------------------

def get_me(token):
    return call(token, "getMe")


def set_webhook(token, url, secret_token, allowed_updates=None, drop_pending_updates=None):
    """secret_token: 1-256 chars of A-Z a-z 0-9 _ - ; Telegram echoes it as X-Telegram-Bot-Api-Secret-Token."""
    return call(token, "setWebhook", {"url": url, "secret_token": secret_token,
                                      "allowed_updates": allowed_updates,
                                      "drop_pending_updates": drop_pending_updates})


def delete_webhook(token, drop_pending_updates=None):
    return call(token, "deleteWebhook", {"drop_pending_updates": drop_pending_updates})


def get_webhook_info(token):
    return call(token, "getWebhookInfo")


# --- Managed bots (called with the MANAGER bot's token) -----------------------

def get_managed_bot_token(manager_token, user_id):
    return call(manager_token, "getManagedBotToken", {"user_id": user_id})


def replace_managed_bot_token(manager_token, user_id):
    return call(manager_token, "replaceManagedBotToken", {"user_id": user_id})


def request_managed_bot_keyboard(text, request_id, suggested_name=None, suggested_username=None):
    """reply_markup with one button that asks the user to create a bot managed by the current bot."""
    request = {"request_id": request_id}
    if suggested_name:
        request["suggested_name"] = suggested_name
    if suggested_username:
        request["suggested_username"] = suggested_username
    return {"keyboard": [[{"text": text, "request_managed_bot": request}]],
            "resize_keyboard": True, "one_time_keyboard": True}


# --- Profile ------------------------------------------------------------------

def set_my_name(token, name):
    return call(token, "setMyName", {"name": name})


def set_my_description(token, description):
    return call(token, "setMyDescription", {"description": description})


def set_my_short_description(token, short_description):
    return call(token, "setMyShortDescription", {"short_description": short_description})


def set_my_commands(token, commands):
    """commands: [{"command": "start", "description": "..."}]"""
    return call(token, "setMyCommands", {"commands": commands})


# --- Messages -----------------------------------------------------------------

def send_message(token, chat_id, text, reply_to_message_id=None, reply_markup=None):
    params = {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
    if reply_to_message_id is not None:
        # Thread the reply under the user's message; still send if that message is gone.
        params["reply_parameters"] = {"message_id": reply_to_message_id, "allow_sending_without_reply": True}
    return call(token, "sendMessage", params)
