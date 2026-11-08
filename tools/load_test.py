"""Burst-load a running server the way a live demo audience would. Stdlib only.

    python3 tools/load_test.py <base_url> [-n 100] [--dev-key KEY]

Without --dev-key (safe on the hosted URL, no Telegram traffic):
  1. warm-up GET /healthz (timed: shows a cold start)
  2. n concurrent POST /classifier/v1/classify with demo phrases
  3. n concurrent webhook deliveries to an unknown bot id (exercises the DB lookup)

With --dev-key, also:
  4. creates a bot, activates it with the dev endpoint (tokenless, so replies are
     only logged, never sent to Telegram), sends n concurrent messages with unique
     update_ids and checks every one got its reply, then deletes the bot.

Reports status counts and p50 / p95 / max latency per phase; exits 1 on any failure.
"""
import argparse
import concurrent.futures
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid

PHRASES = [
    "НАТО провоцировало Россию",
    "Украиной правят неонацисты",
    "Санкции бьют по Европе, Европа замерзнет",
    "Западные СМИ лгут",
    "Хорошая погода сегодня",
]
CONFIG = {
    "display_name": "Load test",
    "username": "loadtest_tmp_bot",
    "confidence_threshold": 0.6,
    "other_response": "NONE",
    "responses": [{"narrative": "Blaming the war on others rather than the invader",
                   "subnarrative": None, "text": "BLAME"}],
}


def call(base, method, path, body=None, headers=None, timeout=120):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, None, time.monotonic() - t0
    except OSError as e:
        return f"error: {e.__class__.__name__}", None, time.monotonic() - t0


def burst(name, n, fn, ok):
    """Run fn(i) n times at once; ok(status, body) says whether a result counts as success."""
    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(fn, range(n)))
    wall = time.monotonic() - t0
    lat = sorted(r[2] for r in results)
    counts = {}
    for s, _, _ in results:
        counts[s] = counts.get(s, 0) + 1
    bad = sum(1 for s, b, _ in results if not ok(s, b))
    p95 = lat[max(0, int(len(lat) * 0.95) - 1)]
    print(f"{name}: {n} requests in {wall:.1f}s | status {counts} | "
          f"p50 {statistics.median(lat) * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms, max {lat[-1] * 1000:.0f} ms"
          f"{f' | {bad} FAILED' if bad else ''}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("-n", type=int, default=100, help="concurrent requests per phase (default 100)")
    ap.add_argument("--dev-key", help="also run a full message burst through a temporary dev-activated bot")
    a = ap.parse_args()
    base, n = a.base_url.rstrip("/"), a.n

    s, _, t = call(base, "GET", "/healthz")
    print(f"warm-up: /healthz -> {s} in {t:.1f}s{' (cold start)' if t > 5 else ''}")
    if s != 200:
        sys.exit(1)

    failed = burst("classify", n, lambda i: call(base, "POST", "/classifier/v1/classify",
                                                 {"text": PHRASES[i % len(PHRASES)]}),
                   lambda s, b: s == 200 and b and "labels" in b)
    unknown = str(uuid.uuid4())
    failed += burst("webhook, unknown bot", n,
                    lambda i: call(base, "POST", f"/webhook/{unknown}", {"update_id": i + 1}),
                    lambda s, b: s == 200)

    if a.dev_key:
        s, bot, _ = call(base, "POST", "/v1/bots", CONFIG)
        if s != 201:
            print(f"create bot -> {s}")
            sys.exit(1)
        bid = bot["bot_id"]
        try:
            s, act, _ = call(base, "POST", f"/v1/_dev/bots/{bid}/activate", {}, {"X-Dev-Key": a.dev_key})
            if s != 200:
                print(f"dev activate -> {s}")
                sys.exit(1)
            sec = {"X-Telegram-Bot-Api-Secret-Token": act["secret_token"]}

            def msg(i):
                text = PHRASES[i % len(PHRASES)]
                return call(base, "POST", f"/webhook/{bid}", {"update_id": i + 1, "message": {
                    "message_id": i + 1, "date": 1, "chat": {"id": 1000 + i, "type": "private"},
                    "from": {"id": 1000 + i, "is_bot": False, "first_name": "Load"}, "text": text}}, sec)

            failed += burst("webhook, active bot (full reply path)", n, msg,
                            lambda s, b: s == 200 and b and b.get("stub_replies"))
        finally:
            call(base, "DELETE", f"/v1/bots/{bid}")

    print("all passed" if not failed else f"{failed} request(s) failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
