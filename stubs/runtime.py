"""Bot Runtime stub (bot-runtime-api.yaml) on :8002.

Implements the full message-handling algorithm from the spec. Sending is
faked by default: replies are logged and echoed in the 200 response body
(Telegram ignores webhook response bodies, so this is harmless) so you can
test with curl.

Set TELEGRAM_SEND=1 to really call sendMessage (via telegram.py, so
TELEGRAM_API_BASE can point at a fake), using the `telegram_token` passed to
the dev activate endpoint.
"""
import hmac
import json
import os
import sys

import telegram
from common import CLASSIFIER_URL, db, http_json, init_db, serve

TELEGRAM_SEND = os.environ.get("TELEGRAM_SEND") == "1"
MAX_LEN = 4096
OK = (200, None)


def log(msg):
    print(f"[runtime] {msg}", file=sys.stderr)


def resolve_replies(cfg, labels):
    """Steps 5-9: threshold, resolve mappings, dedupe, fallback, join/split."""
    mapping = {(r["narrative"], r["subnarrative"]): r["text"] for r in cfg["responses"]}
    kept = sorted((l for l in labels if l["score"] >= cfg["confidence_threshold"]),
                  key=lambda l: l["score"], reverse=True)
    texts = []
    for l in kept:
        t = mapping.get((l["narrative"], l["subnarrative"])) or mapping.get((l["narrative"], None))
        if t and t not in texts:
            texts.append(t)
    if not texts:
        texts = [cfg["other_response"]]
    messages, cur = [], ""
    for t in texts:
        candidate = f"{cur}\n\n{t}" if cur else t
        if len(candidate) <= MAX_LEN:
            cur = candidate
        else:
            messages.append(cur)
            cur = t
    messages.append(cur)
    return messages


def send(row, chat_id, reply_to, text):
    if not (TELEGRAM_SEND and row["telegram_token"]):
        log(f"(fake send) chat={chat_id} reply_to={reply_to}: {text[:80]!r}")
        return
    telegram.send_message(row["telegram_token"], chat_id, text, reply_to_message_id=reply_to)


def webhook(req, m, update):
    bot_id = m.group(1).lower()
    with db() as c:
        row = c.execute("SELECT * FROM bots WHERE bot_id=?", (bot_id,)).fetchone()
    # Request checks: unknown/inactive bot or bad secret -> silent 200.
    if not row or row["status"] != "active":
        log(f"drop: bot {bot_id} unknown or not active")
        return OK
    given = req.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
    if not hmac.compare_digest(given.encode(), (row["secret_token"] or "").encode()):
        log(f"drop: bad secret for {bot_id}")
        return OK

    msg = (update or {}).get("message") if isinstance(update, dict) else None
    if not isinstance(msg, dict) or (msg.get("chat") or {}).get("type") != "private":
        return OK  # step 1
    cfg = json.loads(row["config"])
    chat_id, reply_to = msg["chat"]["id"], msg.get("message_id")
    text = msg.get("text") or msg.get("caption") or ""

    if text.strip().split(" ")[0].split("@")[0] == "/start":
        replies = [cfg["start_message"]]  # step 2
    elif not text.strip():
        replies = [cfg["non_text_message"]]  # step 3
    else:
        try:  # step 4
            status, body = http_json("POST", f"{CLASSIFIER_URL}/classify", {"text": text[:4096]}, timeout=10)
        except OSError as e:
            status, body = None, None
            log(f"classifier error: {e!r}")
        if status == 200 and body:
            log(f"model_version={body.get('model_version')} labels={body['labels']}")
            replies = resolve_replies(cfg, body["labels"])
        else:
            replies = [cfg["error_message"]]

    for r in replies:  # step 10
        try:
            send(row, chat_id, reply_to, r)
        except telegram.TelegramError as e:
            log(f"sendMessage failed: {e}")
    return 200, {"stub_replies": replies}


ROUTES = [("POST", r"/webhook/([0-9a-fA-F-]{36})", webhook)]

if __name__ == "__main__":
    print(f"[runtime] storage: {init_db()}", file=sys.stderr)
    serve(ROUTES, 8002, "runtime")
