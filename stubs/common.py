"""Tiny stdlib-only HTTP helpers shared by the three stub services."""
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from store import db, init as init_db  # noqa: F401  (re-exported for the services)

HERE = os.path.dirname(os.path.abspath(__file__))
CLASSIFIER_URL = os.environ.get("CLASSIFIER_URL", "http://127.0.0.1:8001/v1")
# Public base URL when hosted. Render sets RENDER_EXTERNAL_URL / RENDER_EXTERNAL_HOSTNAME itself.
PUBLIC_URL = (os.environ.get("PUBLIC_URL")
              or os.environ.get("RENDER_EXTERNAL_URL")
              or (f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}" if os.environ.get("RENDER_EXTERNAL_HOSTNAME") else "")
              ).rstrip("/")
HOST = os.environ.get("HOST", "127.0.0.1")
DEV_KEY = os.environ.get("DEV_KEY")  # when set, /_dev endpoints need header X-Dev-Key


class UpdateDedup:
    """Remembers recent Telegram update_ids per bot (memory only), to skip re-deliveries."""

    def __init__(self, per_key=1000):
        self._per_key, self._seen, self._lock = per_key, {}, threading.Lock()

    def is_repeat(self, key, update_id):
        """True if (key, update_id) was seen before; otherwise records it. None never repeats."""
        if not isinstance(update_id, int):
            return False
        with self._lock:
            ids = self._seen.setdefault(key, OrderedDict())
            if update_id in ids:
                return True
            ids[update_id] = None
            if len(ids) > self._per_key:
                ids.popitem(last=False)
            return False


def load_taxonomy():
    with open(os.path.join(HERE, "taxonomy.json"), encoding="utf-8") as f:
        t = json.load(f)
    return {"taxonomy_version": t["taxonomy_version"], "narratives": t["narratives"]}


def error(code, message=None, details=None):
    body = {"error": code}
    if message:
        body["message"] = message
    if details:
        body["details"] = details
    return body


class HttpError(Exception):
    def __init__(self, status, body):
        self.status, self.body = status, body


def http_json(method, url, body=None, timeout=10):
    """Call another stub service. Returns (status, parsed_json_or_None)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, None


def serve(routes, port, name):
    """routes: list of (METHOD, regex, handler). handler(req, match, body) -> (status, json|None)."""
    compiled = [(m, re.compile("^" + p + "$"), h) for m, p, h in routes]

    class Handler(BaseHTTPRequestHandler):
        def _dispatch(self, method):
            path, _, query = self.path.partition("?")
            self.query = dict(p.split("=", 1) if "=" in p else (p, "")
                              for p in query.split("&") if p)
            allowed = False
            for m, rx, h in compiled:
                match = rx.match(path)
                if not match:
                    continue
                allowed = True
                if m != method:
                    continue
                body = None
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    try:
                        body = json.loads(self.rfile.read(length))
                    except ValueError:
                        return self._send(400, error("invalid_request", "Body is not valid JSON"))
                try:
                    status, out = h(self, match, body)
                except HttpError as e:
                    status, out = e.status, e.body
                except Exception as e:  # noqa: BLE001 - stub: surface everything
                    print(f"[{name}] internal error: {e!r}", file=sys.stderr)
                    status, out = 500, error("internal", str(e))
                return self._send(status, out)
            if allowed:
                return self._send(405, error("invalid_request", "Method not allowed"))
            return self._send(404, error("not_found", f"No route for {method} {path}"))

        def _send(self, status, out):
            payload = b"" if out is None else json.dumps(out, ensure_ascii=False, indent=2).encode()
            self.send_response(status)
            if payload:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Telegram-Bot-Api-Secret-Token, X-Dev-Key")
            self.end_headers()

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def log_message(self, fmt, *args):
            print(f"[{name}] {self.address_string()} {fmt % args}", file=sys.stderr)

    print(f"[{name}] listening on http://{HOST}:{port}", file=sys.stderr)
    ThreadingHTTPServer((HOST, port), Handler).serve_forever()
