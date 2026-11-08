"""End-to-end smoke test for the stubs. Stdlib only.

    python3 tools/smoke_test.py http://127.0.0.1:8080 --dev-key KEY        # full run
    python3 tools/smoke_test.py URL --dev-key KEY --persist-create        # create an active bot, print its id
    python3 tools/smoke_test.py URL --persist-check BOT_ID                # confirm it survived a restart

URL is the server root (all services in one process, as server.py runs them).
Bots it creates use usernames starting with `smoketest_` and are deleted at the
end of a full run.
"""
import argparse
import itertools
import json
import sys
import urllib.error
import urllib.request

CONFIG = {
    "display_name": "Smoke Test",
    "username": "smoketest_ci_bot",
    "confidence_threshold": 0.6,
    "other_response": "NONE",
    "responses": [
        {"narrative": "Blaming the war on others rather than the invader", "subnarrative": None, "text": "BLAME"},
        {"narrative": "Amplifying war-related fears", "subnarrative": None, "text": "FEAR"},
    ],
}


class Client:
    def __init__(self, base, dev_key=None):
        self.base, self.dev_key = base.rstrip("/"), dev_key

    def call(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        h = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=90) as r:  # Render cold starts take ~1 min
                raw = r.read()
                return r.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw.decode(errors="replace")

    def create_active(self, username="smoketest_ci_bot", telegram_username=None):
        status, bot = self.call("POST", "/v1/bots", {**CONFIG, "username": username})
        expect(status == 201, f"create -> {status} {bot}")
        body = {"telegram_username": telegram_username} if telegram_username else {}
        status, act = self.call("POST", f"/v1/_dev/bots/{bot['bot_id']}/activate", body,
                                {"X-Dev-Key": self.dev_key or ""})
        expect(status == 200, f"dev activate -> {status} {act}")
        return bot, act


failures = []


def expect(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        failures.append(what)
    return ok


def full_run(c):
    print("health + taxonomy")
    expect(c.call("GET", "/healthz") == (200, {"status": "ok"}), "GET /healthz")
    s, t = c.call("GET", "/v1/taxonomy")
    expect(s == 200 and len(t["narratives"]) == 11
           and sum(len(n["subnarratives"]) for n in t["narratives"]) == 38, "taxonomy 11 narratives / 38 subs")

    print("validation")
    s, e = c.call("POST", "/v1/bots", {**CONFIG, "username": "x", "confidence_threshold": 2,
                                       "responses": [CONFIG["responses"][0], CONFIG["responses"][0]]})
    issues = {d["issue"] for d in (e or {}).get("details", [])}
    expect(s == 422 and {"pattern_mismatch", "out_of_range", "duplicate_mapping"} <= issues,
           f"invalid config -> 422 with expected issues ({sorted(issues)})")

    print("create -> pending")
    s, bot = c.call("POST", "/v1/bots", CONFIG)
    expect(s == 201 and bot["status"] == "pending", "create -> 201 pending")
    bid = bot["bot_id"]
    expect(bot.get("creation_link", "").endswith(f"?start={bid}"), f"creation_link is a /start deep link ({bot.get('creation_link')})")
    expect("telegram_username" not in bot, "no telegram_username while pending")

    print("dev activate")
    s, _ = c.call("POST", f"/v1/_dev/bots/{bid}/activate", {}, {"X-Dev-Key": "wrong"})
    expect(s == 403, "activate with wrong key -> 403")
    s, act = c.call("POST", f"/v1/_dev/bots/{bid}/activate", {"telegram_username": "smoketest_renamed_bot"},
                    {"X-Dev-Key": c.dev_key or ""})
    expect(s == 200 and act.get("status") == "active", f"activate -> 200 active ({s})")
    s, got = c.call("GET", f"/v1/bots/{bid}")
    expect(got.get("telegram_username") == "smoketest_renamed_bot"
           and got.get("telegram_link") == "https://t.me/smoketest_renamed_bot"
           and got["config"]["username"] == "smoketest_ci_bot",
           "changed username: telegram_username/link use it, config unchanged")

    print("runtime")
    hook = f"/webhook/{bid}"
    sec = {"X-Telegram-Bot-Api-Secret-Token": act.get("secret_token", "")}

    update_ids = itertools.count(1)  # unique like Telegram's; the runtime drops repeated ids

    def msg(**fields):
        return {"update_id": next(update_ids), "message": {"message_id": 7, "date": 1, "chat": {"id": 1, "type": "private"}, **fields}}

    expect(c.call("POST", hook, msg(text="НАТО провоцировало Россию"), sec)[1] == {"stub_replies": ["BLAME"]},
           "keyword match -> mapped reply")
    expect(c.call("POST", hook, msg(text="Хорошая погода"), sec)[1] == {"stub_replies": ["NONE"]},
           "no match -> other_response")
    expect(c.call("POST", hook, msg(text="НАТО провоцировало Россию"), {"X-Telegram-Bot-Api-Secret-Token": "x"})
           == (200, None), "wrong secret -> silent 200")

    print("list + delete")
    s, page = c.call("GET", "/v1/bots?status=active&limit=200")
    expect(s == 200 and any(b["bot_id"] == bid for b in page["bots"]), "listed as active")
    expect(c.call("DELETE", f"/v1/bots/{bid}")[0] == 204, "delete -> 204")
    expect(c.call("DELETE", f"/v1/bots/{bid}")[0] == 204, "delete again -> 204")
    s, got = c.call("GET", f"/v1/bots/{bid}")
    expect(s == 200 and got["status"] == "deleted" and got.get("deleted_at"), "deleted bot still readable")
    expect(c.call("POST", hook, msg(text="НАТО провоцировало"), sec) == (200, None), "deleted bot -> silent 200")
    expect(c.call("GET", "/v1/bots/00000000-0000-0000-0000-000000000000")[0] == 404, "unknown id -> 404")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--dev-key")
    ap.add_argument("--persist-create", action="store_true")
    ap.add_argument("--persist-check", metavar="BOT_ID")
    a = ap.parse_args()
    c = Client(a.base, a.dev_key)

    if a.persist_create:
        bot, act = c.create_active("smoketest_persist_bot", "smoketest_persist_live_bot")
        print(json.dumps({"bot_id": bot["bot_id"], "secret_token": act["secret_token"]}))
    elif a.persist_check:
        bid = a.persist_check
        s, got = c.call("GET", f"/v1/bots/{bid}")
        expect(s == 200, f"bot {bid} still exists after restart ({s})")
        if s == 200:
            expect(got["status"] == "active", f"still active ({got['status']})")
            expect(got.get("telegram_username") == "smoketest_persist_live_bot", "telegram_username kept")
            expect(got["config"]["responses"] == CONFIG["responses"], "config kept")
            expect(c.call("DELETE", f"/v1/bots/{bid}")[0] == 204, "cleanup delete")
    else:
        full_run(c)

    if failures:
        print(f"\n{len(failures)} FAILED", file=sys.stderr)
        sys.exit(1)
    if not a.persist_create:
        print("\nall passed")


if __name__ == "__main__":
    main()
