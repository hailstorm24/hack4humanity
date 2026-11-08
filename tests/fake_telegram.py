"""In-process fake of the Telegram Bot API, for tests. Stdlib only.

It implements the methods our code calls, records every call, and plays
Telegram's side of the conversation: it can deliver updates to a bot's
webhook (with the X-Telegram-Bot-Api-Secret-Token header) the way Telegram
would.

    fake = FakeTelegram().start()
    os.environ["TELEGRAM_API_BASE"] = fake.base_url
    manager = fake.add_bot("h4h_manager_bot", "H4H Manager", can_manage_bots=True)
    ...
    fake.stop()

Behaviour follows the Bot API docs (10.0, May 2026). Error descriptions are
plausible, not copied from Telegram; code should branch on error_code, never
on description text. The real API is checked in Stages 3-4.
"""
import itertools
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
COMMAND_RE = re.compile(r"^[a-z0-9_]{1,32}$")


class ApiError(Exception):
    def __init__(self, code, description, retry_after=None):
        self.code, self.description, self.retry_after = code, description, retry_after


class FakeTelegram:
    def __init__(self, allow_http_webhooks=True):
        self.allow_http_webhooks = allow_http_webhooks  # real Telegram requires https
        self.lock = threading.RLock()
        self.bots = {}          # bot id -> bot state
        self.tokens = {}        # token -> bot id
        self.calls = []         # [{"method", "bot" (username), "params"}]
        self.outbox = []        # messages sent by bots
        self._errors = []       # injected failures
        self._ids = itertools.count(7_000_000_001)
        self._update_ids = itertools.count(1)
        self._message_ids = itertools.count(1)
        self._server = None

    # --- lifecycle --------------------------------------------------------------

    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                m = re.match(r"^/bot([^/]+)/([A-Za-z]+)$", self.path)
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    params = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    params = None
                if not m or params is None:
                    return self._reply(404, {"ok": False, "error_code": 404, "description": "Not Found"})
                try:
                    result = fake._dispatch(m.group(1), m.group(2), params)
                    self._reply(200, {"ok": True, "result": result})
                except ApiError as e:
                    body = {"ok": False, "error_code": e.code, "description": e.description}
                    if e.retry_after is not None:
                        body["parameters"] = {"retry_after": e.retry_after}
                    self._reply(e.code, body)

            def _reply(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    # --- test controls ----------------------------------------------------------

    def add_bot(self, username, first_name, can_manage_bots=False, manager_id=None):
        """Register a bot; returns its token."""
        with self.lock:
            bot_id = next(self._ids)
            token = f"{bot_id}:{secrets.token_urlsafe(26)[:35]}"
            self.bots[bot_id] = {
                "id": bot_id, "username": username, "first_name": first_name,
                "can_manage_bots": can_manage_bots, "manager_id": manager_id, "token": token,
                "name": first_name, "description": "", "short_description": "", "commands": [],
                "webhook": None,
            }
            self.tokens[token] = bot_id
            return token

    def bot(self, token_or_username):
        with self.lock:
            if token_or_username in self.tokens:
                return self.bots[self.tokens[token_or_username]]
            return next(b for b in self.bots.values() if b["username"] == token_or_username)

    def inject_error(self, method, code, description="Injected", retry_after=None, times=1):
        """Make the next `times` calls to `method` fail."""
        with self.lock:
            self._errors.append({"method": method, "code": code, "description": description,
                                 "retry_after": retry_after, "times": times})

    def calls_to(self, method):
        with self.lock:
            return [c for c in self.calls if c["method"] == method]

    def create_managed_bot(self, manager_token, creator, username, name):
        """Play the organizer confirming bot creation in Telegram's app.

        Creates the bot (managed by the manager), then delivers what Telegram
        delivers to the manager: a `managed_bot` update and a service message
        with `managed_bot_created` in the organizer's private chat.
        Returns (new bot's token, [webhook responses]).
        """
        manager = self.bot(manager_token)
        if not manager["can_manage_bots"]:
            raise ValueError("manager bot has not enabled bot management")
        token = self.add_bot(username, name, manager_id=manager["id"])
        bot_user = self._user(self.bot(token))
        responses = [
            self.deliver(manager_token, {"managed_bot": {"user": creator, "bot": bot_user}}),
            self.deliver(manager_token, {"message": self._message(
                creator, {"managed_bot_created": {"bot": bot_user}})}),
        ]
        return token, responses

    def user_sends(self, token, user, **message_fields):
        """Play a user sending a private message to a bot. Returns the webhook response."""
        return self.deliver(token, {"message": self._message(user, message_fields)})

    def deliver(self, token, update):
        """POST an update to the bot's webhook like Telegram would.

        Returns (status, parsed body or None), or None if the update type is
        filtered out by the webhook's allowed_updates. Raises if no webhook is set.
        """
        bot = self.bot(token)
        hook = bot["webhook"]
        if not hook:
            raise AssertionError(f"@{bot['username']} has no webhook set")
        kind = next(k for k in update if k != "update_id")
        if hook["allowed_updates"] and kind not in hook["allowed_updates"]:
            return None
        update = {"update_id": next(self._update_ids), **update}
        headers = {"Content-Type": "application/json"}
        if hook["secret_token"]:
            headers["X-Telegram-Bot-Api-Secret-Token"] = hook["secret_token"]
        req = urllib.request.Request(hook["url"], data=json.dumps(update).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            return e.code, None

    def sent_to(self, chat_id):
        with self.lock:
            return [m for m in self.outbox if m["chat_id"] == chat_id]

    # --- helpers ----------------------------------------------------------------

    @staticmethod
    def _user(bot):
        return {"id": bot["id"], "is_bot": True, "first_name": bot["first_name"], "username": bot["username"]}

    def _message(self, user, fields):
        return {"message_id": next(self._message_ids), "date": int(time.time()),
                "chat": {"id": user["id"], "type": "private", "first_name": user.get("first_name", "")},
                "from": user, **fields}

    # --- Bot API ----------------------------------------------------------------

    def _dispatch(self, token, method, p):
        with self.lock:
            if token not in self.tokens:
                raise ApiError(401, "Unauthorized")
            bot = self.bots[self.tokens[token]]
            self.calls.append({"method": method, "bot": bot["username"], "params": p})
            for err in self._errors:
                if err["method"] == method and err["times"] > 0:
                    err["times"] -= 1
                    raise ApiError(err["code"], err["description"], err["retry_after"])
            handler = getattr(self, f"_m_{method}", None)
            if handler is None:
                raise ApiError(404, "Not Found: method not found")
            return handler(bot, p)

    def _m_getMe(self, bot, p):
        return {**self._user(bot), "can_manage_bots": bot["can_manage_bots"]}

    def _m_setWebhook(self, bot, p):
        url = p.get("url") or ""
        if not url.startswith("https://") and not (self.allow_http_webhooks and url.startswith("http://")):
            raise ApiError(400, "Bad Request: bad webhook: An HTTPS URL must be provided for webhook")
        secret = p.get("secret_token")
        if secret is not None and not SECRET_RE.match(secret):
            raise ApiError(400, "Bad Request: secret token contains unallowed characters")
        bot["webhook"] = {"url": url, "secret_token": secret, "allowed_updates": p.get("allowed_updates")}
        return True

    def _m_deleteWebhook(self, bot, p):
        bot["webhook"] = None
        return True

    def _m_getWebhookInfo(self, bot, p):
        hook = bot["webhook"] or {}
        info = {"url": hook.get("url", ""), "has_custom_certificate": False, "pending_update_count": 0}
        if hook.get("allowed_updates"):
            info["allowed_updates"] = hook["allowed_updates"]
        return info

    def _managed(self, manager, p):
        target = self.bots.get(p.get("user_id"))
        if not manager["can_manage_bots"] or not target or target["manager_id"] != manager["id"]:
            raise ApiError(400, "Bad Request: bot not found")
        return target

    def _m_getManagedBotToken(self, manager, p):
        return self._managed(manager, p)["token"]

    def _m_replaceManagedBotToken(self, manager, p):
        target = self._managed(manager, p)
        del self.tokens[target["token"]]
        target["token"] = f"{target['id']}:{secrets.token_urlsafe(26)[:35]}"
        self.tokens[target["token"]] = target["id"]
        return target["token"]

    def _m_setMyName(self, bot, p):
        if len(p.get("name") or "") > 64:
            raise ApiError(400, "Bad Request: bot name is too long")
        bot["name"] = p.get("name") or ""
        return True

    def _m_setMyDescription(self, bot, p):
        if len(p.get("description") or "") > 512:
            raise ApiError(400, "Bad Request: description is too long")
        bot["description"] = p.get("description") or ""
        return True

    def _m_setMyShortDescription(self, bot, p):
        if len(p.get("short_description") or "") > 120:
            raise ApiError(400, "Bad Request: short description is too long")
        bot["short_description"] = p.get("short_description") or ""
        return True

    def _m_setMyCommands(self, bot, p):
        cmds = p.get("commands")
        if not isinstance(cmds, list) or any(
                not COMMAND_RE.match(c.get("command", "")) or not 1 <= len(c.get("description", "")) <= 256
                for c in cmds):
            raise ApiError(400, "Bad Request: invalid commands")
        bot["commands"] = cmds
        return True

    def _m_sendMessage(self, bot, p):
        text = p.get("text") or ""
        if "chat_id" not in p:
            raise ApiError(400, "Bad Request: chat_id is empty")
        if not text:
            raise ApiError(400, "Bad Request: message text is empty")
        if len(text) > 4096:
            raise ApiError(400, "Bad Request: message is too long")
        msg = {"message_id": next(self._message_ids), "date": int(time.time()),
               "chat": {"id": p["chat_id"], "type": "private"}, "from": self._user(bot), "text": text}
        self.outbox.append({"bot": bot["username"], "chat_id": p["chat_id"], "text": text,
                            "reply_parameters": p.get("reply_parameters"),
                            "reply_markup": p.get("reply_markup"), "message_id": msg["message_id"]})
        return msg
