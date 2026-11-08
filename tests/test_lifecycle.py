"""End-to-end bot lifecycle: the real service (stubs/server.py) against the fake Telegram.

The service runs as a subprocess with TELEGRAM_API_BASE pointing at the fake
and a throwaway SQLite file (sending is on by default since Stage 6). The fake plays Telegram: it
delivers updates to the service's webhooks and records what the service sends.

Tests are grouped by the plan stage that added them (docs/bot-creation-plan.md).
Active bots are made the real way: /start link -> create in Telegram ->
managed_bot update -> activation.

    python3 -m unittest discover -s tests -v
"""
import itertools
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STUBS = os.path.join(os.path.dirname(HERE), "stubs")
sys.path[:0] = [HERE, STUBS]

import telegram  # noqa: E402
from fake_telegram import FakeTelegram  # noqa: E402

DEV_KEY = "test-dev-key"
CONFIG = {
    "display_name": "Odesa Fact Check",
    "username": "odesa_factcheck_bot",
    "description": "Перешлите мне сообщение, и я проверю его.",
    "short_description": "Проверка нарративов",
    "confidence_threshold": 0.6,
    "other_response": "NONE",
    "responses": [{"narrative": "Blaming the war on others rather than the invader",
                   "subnarrative": None, "text": "BLAME"}],
}
ORGANIZER = {"id": 555000111, "is_bot": False, "first_name": "Oksana"}
READER = {"id": 555000222, "is_bot": False, "first_name": "Oleh"}
_org_ids = itertools.count(600000001)


def new_organizer():
    """A fresh Telegram user per test, so claims never leak between tests."""
    return {"id": next(_org_ids), "is_bot": False, "first_name": "Org"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeTelegram().start()
        telegram.API_BASE = cls.fake.base_url
        cls.manager = cls.fake.add_bot("h4h_manager_bot", "H4H Manager", can_manage_bots=True)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = {**os.environ, "PORT": str(cls.port), "HOST": "127.0.0.1", "DEV_KEY": DEV_KEY,
               "STUB_DB": os.path.join(cls.tmp.name, "test.db"), "DATABASE_URL": "",
               "TELEGRAM_API_BASE": cls.fake.base_url,
               "PUBLIC_URL": f"http://127.0.0.1:{cls.port}", "MANAGER_BOT_TOKEN": cls.manager}
        env.pop("MANAGER_BOT_USERNAME", None)  # the username must come from getMe
        env.pop("TELEGRAM_SEND", None)  # Stage 6: sending must be on by default
        cls.log = open(os.path.join(cls.tmp.name, "server.log"), "w")
        cls.proc = subprocess.Popen([sys.executable, "server.py"], cwd=STUBS, env=env,
                                    stdout=cls.log, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + "/healthz", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("server did not start; see log")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)
        cls.log.close()
        cls.fake.stop()
        cls.tmp.cleanup()

    # --- helpers ----------------------------------------------------------------

    def api(self, method, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            return e.code, (json.loads(raw) if raw else None)

    def db(self):
        return sqlite3.connect(os.path.join(self.tmp.name, "test.db"))

    def _row(self, bot_id):
        with self.db() as c:
            c.row_factory = sqlite3.Row
            return dict(c.execute("SELECT * FROM bots WHERE bot_id=?", (bot_id,)).fetchone())

    def _pending(self, **overrides):
        status, bot = self.api("POST", "/v1/bots", {**CONFIG, **overrides})
        self.assertEqual(status, 201, bot)
        return bot["bot_id"]

    def _start(self, org, bot_id):
        """Organizer opens the creation link; returns the manager's reply."""
        self.fake.user_sends(self.manager, org, text=f"/start {bot_id}")
        return self.fake.sent_to(org["id"])[-1]

    def _new_active_bot(self, username):
        """Full real flow; returns (Bot as the API reports it, the new bot's token)."""
        org, bot_id = new_organizer(), self._pending(username=username)
        self._start(org, bot_id)
        token, responses = self.fake.create_managed_bot(self.manager, org, username, CONFIG["display_name"])
        self.assertEqual([r[0] for r in responses], [200, 200])
        status, bot = self.api("GET", f"/v1/bots/{bot_id}")
        self.assertEqual(bot["status"], "active", bot)
        return bot, token

    # --- Stage 1-2: what exists today -------------------------------------------

    def test_create_returns_manager_deep_link(self):
        status, bot = self.api("POST", "/v1/bots", CONFIG)
        self.assertEqual(status, 201)
        self.assertEqual(bot["creation_link"], f"https://t.me/h4h_manager_bot?start={bot['bot_id']}")

    def test_reply_is_sent_through_telegram_and_threaded(self):
        bot, token = self._new_active_bot("reply_test_bot")
        status, _ = self.fake.user_sends(token, READER, text="НАТО провоцировало Россию")
        self.assertEqual(status, 200)
        sent = self.fake.sent_to(READER["id"])[-1]
        self.assertEqual((sent["bot"], sent["text"]), ("reply_test_bot", "BLAME"))
        incoming_id = sent["message_id"] - 1  # fake numbers messages sequentially
        self.assertEqual(sent["reply_parameters"]["message_id"], incoming_id)

    def test_start_photo_and_no_match_replies(self):
        _, token = self._new_active_bot("cases_test_bot")
        before = len(self.fake.sent_to(READER["id"]))
        self.fake.user_sends(token, READER, text="/start")
        self.fake.user_sends(token, READER, photo=[{"file_id": "x", "width": 1, "height": 1}])
        self.fake.user_sends(token, READER, text="Хорошая погода")
        texts = [m["text"] for m in self.fake.sent_to(READER["id"])[before:]]
        self.assertEqual(texts, ["Перешлите мне сообщение, и я проверю его.",
                                 "Пожалуйста, перешлите текстовое сообщение или пост с подписью.",
                                 "NONE"])

    def test_group_messages_and_filtered_updates_get_no_reply(self):
        bot, token = self._new_active_bot("quiet_test_bot")
        before = len(self.fake.outbox)
        group_msg = {"message": {"message_id": 1, "date": 1, "chat": {"id": -100, "type": "group"},
                                 "from": READER, "text": "НАТО провоцировало Россию"}}
        self.assertEqual(self.fake.deliver(token, group_msg)[0], 200)
        # allowed_updates=["message"]: Telegram never delivers edited_message to us.
        self.assertIsNone(self.fake.deliver(token, {"edited_message": group_msg["message"]}))
        self.assertEqual(len(self.fake.outbox), before)

    def test_forged_update_without_secret_is_ignored(self):
        bot, token = self._new_active_bot("forged_test_bot")
        before = len(self.fake.outbox)
        update = {"update_id": 1, "message": {"message_id": 1, "date": 1, "chat": {"id": 9, "type": "private"},
                                              "text": "НАТО провоцировало Россию"}}
        status, body = self.api("POST", f"/webhook/{bot['bot_id']}", update)  # no secret header
        self.assertEqual((status, body), (200, None))
        self.assertEqual(len(self.fake.outbox), before)

    def test_send_failure_is_logged_not_raised(self):
        _, token = self._new_active_bot("flaky_test_bot")
        self.fake.inject_error("sendMessage", 403, "Forbidden: bot was blocked by the user")
        status, _ = self.fake.user_sends(token, READER, text="НАТО провоцировало Россию")
        self.assertEqual(status, 200)  # Telegram must still get a 200, or it retries

    def test_deleted_bot_stops_replying(self):
        bot, token = self._new_active_bot("deleted_test_bot")
        secret = self.fake.bot(token)["webhook"]["secret_token"]
        self.assertEqual(self.api("DELETE", f"/v1/bots/{bot['bot_id']}")[0], 204)
        before = len(self.fake.outbox)
        # Telegram no longer delivers (Stage 7), and a late delivery with the old secret is ignored.
        update = {"update_id": 1, "message": {"message_id": 1, "date": 1, "from": READER,
                                              "chat": {"id": READER["id"], "type": "private"},
                                              "text": "НАТО провоцировало Россию"}}
        self.assertEqual(self.api("POST", f"/webhook/{bot['bot_id']}", update,
                                  {"X-Telegram-Bot-Api-Secret-Token": secret}), (200, None))
        self.assertEqual(len(self.fake.outbox), before)

    # --- Stage 3: manager bot --------------------------------------------------

    def test_stage3_manager_webhook_registered_on_startup(self):
        info = telegram.get_webhook_info(self.manager)
        self.assertEqual(info["url"], f"{self.base}/telegram/manager")
        self.assertEqual(info["allowed_updates"], ["message", "managed_bot"])
        secret = self.fake.bot(self.manager)["webhook"]["secret_token"]
        self.assertRegex(secret, r"^[A-Za-z0-9_-]{32,256}$")
        self.assertEqual([c["bot"] for c in self.fake.calls_to("getMe")][:1], ["h4h_manager_bot"])

    def test_stage3_manager_answers_private_messages(self):
        status, _ = self.fake.user_sends(self.manager, ORGANIZER, text="/start")
        self.assertEqual(status, 200)
        sent = self.fake.sent_to(ORGANIZER["id"])[-1]
        self.assertEqual(sent["bot"], "h4h_manager_bot")
        self.assertIn("Привет", sent["text"])

    def test_stage3_manager_drops_updates_without_secret(self):
        before = len(self.fake.outbox)
        update = {"update_id": 1, "message": {"message_id": 1, "date": 1, "from": ORGANIZER,
                                              "chat": {"id": ORGANIZER["id"], "type": "private"}, "text": "/start"}}
        self.assertEqual(self.api("POST", "/telegram/manager", update), (200, None))
        self.assertEqual(self.api("POST", "/telegram/manager", update,
                                  {"X-Telegram-Bot-Api-Secret-Token": "wrong"}), (200, None))
        self.assertEqual(len(self.fake.outbox), before)

    def test_stage3_managed_bot_update_returns_200(self):
        org = new_organizer()
        _, responses = self.fake.create_managed_bot(self.manager, org, "stage3_probe_bot", "Probe")
        self.assertEqual([r[0] for r in responses], [200, 200])

    def test_stage3_dev_status_reports_setup_without_secrets(self):
        self.assertEqual(self.api("GET", "/v1/_dev/manager")[0], 403)
        status, st = self.api("GET", "/v1/_dev/manager", headers={"X-Dev-Key": DEV_KEY})
        self.assertEqual(status, 200)
        self.assertEqual((st["configured"], st["username"], st["can_manage_bots"]), (True, "h4h_manager_bot", True))
        self.assertEqual(st["webhook_url"], st["expected_webhook_url"])
        self.assertIsNone(st["startup_error"])
        dumped = json.dumps(st)
        self.assertNotIn(self.manager, dumped)
        self.assertNotIn(self.fake.bot(self.manager)["webhook"]["secret_token"], dumped)

    # --- Stage 4: creation link + matching ----------------------------------------

    def test_stage4_start_link_offers_create_button(self):
        org, bot_id = new_organizer(), self._pending()
        sent = self._start(org, bot_id)
        req = sent["reply_markup"]["keyboard"][0][0]["request_managed_bot"]
        self.assertEqual((req["suggested_name"], req["suggested_username"]),
                         (CONFIG["display_name"], CONFIG["username"]))
        self.assertTrue(0 <= req["request_id"] < 2**31)
        row = self._row(bot_id)
        self.assertEqual((row["organizer_tg_id"], row["status"]), (org["id"], "pending"))
        self.assertTrue(row["claimed_at"])

    def test_stage4_start_link_rejects_bad_unknown_expired_and_active(self):
        org = new_organizer()
        self.assertIn("недействительна", self._start(org, "not-a-uuid")["text"])
        self.assertIn("недействительна", self._start(org, "00000000-0000-0000-0000-000000000000")["text"])
        expired = self._pending()
        with self.db() as c:
            c.execute("UPDATE bots SET expires_at='2000-01-01T00:00:00Z' WHERE bot_id=?", (expired,))
        self.assertIn("истёк", self._start(org, expired)["text"])
        active, _ = self._new_active_bot("stage4_active_bot")
        self.assertIn("t.me/stage4_active_bot", self._start(org, active["bot_id"])["text"])
        deleted = self._pending()
        self.api("DELETE", f"/v1/bots/{deleted}")
        self.assertIn("недействительна", self._start(org, deleted)["text"])
        for bot_id in (expired, active["bot_id"], deleted):
            self.assertNotEqual(self._row(bot_id)["organizer_tg_id"], org["id"])

    def test_stage4_managed_bot_matched_to_claim(self):
        org, bot_id = new_organizer(), self._pending()
        self._start(org, bot_id)
        _, responses = self.fake.create_managed_bot(self.manager, org, CONFIG["username"], "Odesa")
        self.assertEqual([r[0] for r in responses], [200, 200])
        row = self._row(bot_id)
        self.assertEqual(row["telegram_bot_id"], self.fake.bot(CONFIG["username"])["id"])
        self.assertEqual((row["telegram_username"], row["status"]), (CONFIG["username"], "active"))
        sent = self.fake.sent_to(org["id"])[-1]
        self.assertIn("@" + CONFIG["username"], sent["text"])
        self.assertEqual(sent["reply_markup"], {"remove_keyboard": True})

    def test_stage4_changed_username_still_matches(self):
        org, bot_id = new_organizer(), self._pending(username="wanted_name_bot")
        self._start(org, bot_id)
        self.fake.create_managed_bot(self.manager, org, "organizer_picked_bot", "Odesa")
        self.assertEqual(self._row(bot_id)["telegram_username"], "organizer_picked_bot")

    def test_stage4_two_claims_prefer_username_then_latest(self):
        org = new_organizer()
        first, second = self._pending(username="first_claim_bot"), self._pending(username="second_claim_bot")
        self._start(org, first)
        time.sleep(1.1)  # claimed_at has 1 s resolution
        self._start(org, second)
        self.fake.create_managed_bot(self.manager, org, "first_claim_bot", "One")  # username wins
        self.assertEqual(self._row(first)["telegram_username"], "first_claim_bot")
        self.assertIsNone(self._row(second)["telegram_bot_id"])
        self.fake.create_managed_bot(self.manager, org, "renamed_second_bot", "Two")  # then latest claim
        self.assertEqual(self._row(second)["telegram_username"], "renamed_second_bot")

    def test_stage4_unclaimed_creator_is_told_and_nothing_linked(self):
        org, bot_id = new_organizer(), self._pending()  # never opened the link
        self.fake.create_managed_bot(self.manager, org, "stray_bot", "Stray")
        self.assertIn("не нашёл", self.fake.sent_to(org["id"])[-1]["text"])
        self.assertIsNone(self._row(bot_id)["telegram_bot_id"])

    def test_stage4_repeat_update_for_linked_bot_is_ignored(self):
        org, bot_id = new_organizer(), self._pending()
        self._start(org, bot_id)
        token, _ = self.fake.create_managed_bot(self.manager, org, "repeat_test_bot", "Rep")
        before = len(self.fake.sent_to(org["id"]))
        bot_user = {"id": self.fake.bot(token)["id"], "is_bot": True, "first_name": "Rep",
                    "username": "repeat_test_bot"}
        self.assertEqual(self.fake.deliver(self.manager, {"managed_bot": {"user": org, "bot": bot_user}})[0], 200)
        self.assertEqual(len(self.fake.sent_to(org["id"])), before)
        self.assertEqual(self._row(bot_id)["telegram_username"], "repeat_test_bot")

    # --- Stage 5: activation ------------------------------------------------------

    def test_stage5_managed_bot_update_activates(self):
        org = new_organizer()
        status, bot = self.api("POST", "/v1/bots", CONFIG)
        self.fake.user_sends(self.manager, org, text=f"/start {bot['bot_id']}")
        token, _ = self.fake.create_managed_bot(self.manager, org, "renamed_by_organizer_bot", "Odesa")
        status, got = self.api("GET", f"/v1/bots/{bot['bot_id']}")
        self.assertEqual(got["status"], "active")
        self.assertEqual(got["telegram_username"], "renamed_by_organizer_bot")
        self.assertEqual(got["telegram_link"], "https://t.me/renamed_by_organizer_bot")
        live = self.fake.bot(token)
        self.assertEqual((live["name"], live["description"], live["short_description"]),
                         (CONFIG["display_name"], CONFIG["description"], CONFIG["short_description"]))
        self.assertTrue(live["webhook"]["url"].endswith(f"/webhook/{bot['bot_id']}"))
        self.assertEqual(live["webhook"]["allowed_updates"], ["message"])
        row = self._row(bot["bot_id"])
        self.assertEqual(live["webhook"]["secret_token"], row["secret_token"])
        self.assertIsNone(row["telegram_token"])  # tokens are never stored
        self.assertNotIn(token, json.dumps(got))
        self.assertIn("t.me/renamed_by_organizer_bot", self.fake.sent_to(org["id"])[-1]["text"])
        # And it answers readers.
        self.fake.user_sends(token, READER, text="НАТО провоцировало Россию")
        self.assertEqual(self.fake.sent_to(READER["id"])[-1]["text"], "BLAME")

    def test_stage5_webhook_failure_stays_pending_and_reopening_retries(self):
        org, bot_id = new_organizer(), self._pending(username="retry_test_bot")
        self._start(org, bot_id)
        self.fake.inject_error("setWebhook", 500, "Internal Server Error")
        token, responses = self.fake.create_managed_bot(self.manager, org, "retry_test_bot", "Retry")
        self.assertEqual([r[0] for r in responses], [200, 200])
        self.assertEqual(self.api("GET", f"/v1/bots/{bot_id}")[1]["status"], "pending")
        self.assertIn("не удалось", self.fake.sent_to(org["id"])[-1]["text"])
        self.assertIsNone(self.fake.bot(token)["webhook"])
        sent = self._start(org, bot_id)  # reopening the creation link retries activation
        self.assertIn("t.me/retry_test_bot", sent["text"])
        self.assertEqual(self.api("GET", f"/v1/bots/{bot_id}")[1]["status"], "active")
        self.assertIsNotNone(self.fake.bot(token)["webhook"])

    def test_stage5_token_fetch_failure_stays_pending(self):
        org, bot_id = new_organizer(), self._pending(username="notoken_test_bot")
        self._start(org, bot_id)
        self.fake.inject_error("getManagedBotToken", 400, "Bad Request: bot not found")
        self.fake.create_managed_bot(self.manager, org, "notoken_test_bot", "NoTok")
        self.assertEqual(self.api("GET", f"/v1/bots/{bot_id}")[1]["status"], "pending")
        self.assertIn("не удалось", self.fake.sent_to(org["id"])[-1]["text"])

    def test_stage5_profile_failure_is_not_fatal(self):
        self.fake.inject_error("setMyDescription", 400, "Bad Request: description is too long")
        bot, token = self._new_active_bot("profile_fail_test_bot")
        self.assertEqual(self.fake.bot(token)["name"], CONFIG["display_name"])

    def test_stage5_runtime_refetches_rotated_token(self):
        bot, token = self._new_active_bot("rotate_test_bot")
        self.fake.user_sends(token, READER, text="Хорошая погода")  # warms the token cache
        bot_tg_id = self.fake.bot(token)["id"]
        new_token = telegram.replace_managed_bot_token(self.manager, bot_tg_id)  # old token now 401s
        status, _ = self.fake.user_sends(new_token, READER, text="НАТО провоцировало Россию")
        self.assertEqual(status, 200)
        sent = self.fake.sent_to(READER["id"])[-1]
        self.assertEqual((sent["bot"], sent["text"]), ("rotate_test_bot", "BLAME"))

    # --- Stage 6: real replies ----------------------------------------------------

    def test_stage6_redelivered_update_gets_one_reply(self):
        _, token = self._new_active_bot("redeliver_test_bot")
        before = len(self.fake.sent_to(READER["id"]))
        msg = self.fake._message(READER, {"text": "НАТО провоцировало Россию"})
        for _ in range(2):  # Telegram retries when we answer too slowly
            self.assertEqual(self.fake.deliver(token, {"update_id": 9_100_001, "message": msg})[0], 200)
        self.assertEqual([m["text"] for m in self.fake.sent_to(READER["id"])[before:]], ["BLAME"])
        # A new update_id is answered as usual.
        self.fake.deliver(token, {"update_id": 9_100_002, "message": msg})
        self.assertEqual(len(self.fake.sent_to(READER["id"])) - before, 2)

    def test_stage6_same_update_id_on_another_bot_is_not_a_repeat(self):
        _, one = self._new_active_bot("dedup_one_test_bot")
        _, two = self._new_active_bot("dedup_two_test_bot")
        before = len(self.fake.sent_to(READER["id"]))
        msg = self.fake._message(READER, {"text": "Хорошая погода"})
        self.fake.deliver(one, {"update_id": 9_200_001, "message": msg})
        self.fake.deliver(two, {"update_id": 9_200_001, "message": msg})  # update_ids are per bot
        self.assertEqual([m["bot"] for m in self.fake.sent_to(READER["id"])[before:]],
                         ["dedup_one_test_bot", "dedup_two_test_bot"])

    def test_stage6_manager_ignores_redelivered_update(self):
        org = new_organizer()
        msg = self.fake._message(org, {"text": "/start"})
        for _ in range(2):
            self.fake.deliver(self.manager, {"update_id": 9_300_001, "message": msg})
        self.assertEqual(len(self.fake.sent_to(org["id"])), 1)

    def test_stage6_bot_without_token_only_logs(self):
        """Dev-activated without a token (how the hosted smoke test works): replies are echoed, not sent."""
        bot_id = self._pending(username="tokenless_test_bot")
        status, act = self.api("POST", f"/v1/_dev/bots/{bot_id}/activate", {}, {"X-Dev-Key": DEV_KEY})
        self.assertEqual(status, 200, act)
        before = len(self.fake.outbox)
        update = {"update_id": 1, "message": {"message_id": 1, "date": 1, "from": READER,
                                              "chat": {"id": READER["id"], "type": "private"},
                                              "text": "НАТО провоцировало Россию"}}
        status, body = self.api("POST", f"/webhook/{bot_id}", update,
                                {"X-Telegram-Bot-Api-Secret-Token": act["secret_token"]})
        self.assertEqual((status, body), (200, {"stub_replies": ["BLAME"]}))
        self.assertEqual(len(self.fake.outbox), before)

    # --- Stage 7: lifecycle -------------------------------------------------------

    def test_stage7_delete_removes_webhook(self):
        bot, token = self._new_active_bot("stage7_test_bot")
        self.api("DELETE", f"/v1/bots/{bot['bot_id']}")
        self.assertEqual(telegram.get_webhook_info(token)["url"], "")
        self.assertEqual(self.fake.calls_to("deleteWebhook")[-1]["params"].get("drop_pending_updates"), True)

    def test_stage7_delete_survives_telegram_error(self):
        bot, token = self._new_active_bot("delete_err_test_bot")
        self.fake.inject_error("deleteWebhook", 500, "Internal Server Error")
        self.assertEqual(self.api("DELETE", f"/v1/bots/{bot['bot_id']}")[0], 204)
        self.assertEqual(self.api("GET", f"/v1/bots/{bot['bot_id']}")[1]["status"], "deleted")

    def _token_or_owner_update(self, token, owner):
        b = self.fake.bot(token)
        bot_user = {"id": b["id"], "is_bot": True, "first_name": b["first_name"], "username": b["username"]}
        return self.fake.deliver(self.manager, {"managed_bot": {"user": owner, "bot": bot_user}})

    def test_stage7_token_change_rewires_webhook(self):
        bot, token = self._new_active_bot("tokenchange_test_bot")
        secret = self.fake.bot(token)["webhook"]["secret_token"]
        new_token = telegram.replace_managed_bot_token(self.manager, self.fake.bot(token)["id"])
        self.fake.bot(new_token)["webhook"] = None  # as if Telegram dropped it with the old token
        before = len(self.fake.calls_to("getManagedBotToken"))
        org = {"id": self._row(bot["bot_id"])["organizer_tg_id"], "is_bot": False, "first_name": "Org"}
        self.assertEqual(self._token_or_owner_update(new_token, org)[0], 200)
        self.assertGreater(len(self.fake.calls_to("getManagedBotToken")), before)  # fresh token fetched
        hook = self.fake.bot(new_token)["webhook"]
        self.assertTrue(hook["url"].endswith(f"/webhook/{bot['bot_id']}"))
        self.assertEqual(hook["secret_token"], secret)
        self.fake.user_sends(new_token, READER, text="НАТО провоцировало Россию")
        self.assertEqual(self.fake.sent_to(READER["id"])[-1]["text"], "BLAME")

    def test_stage7_owner_change_is_recorded(self):
        bot, token = self._new_active_bot("ownerchange_test_bot")
        new_owner = new_organizer()
        self._token_or_owner_update(token, new_owner)
        row = self._row(bot["bot_id"])
        self.assertEqual((row["organizer_tg_id"], row["status"]), (new_owner["id"], "active"))
        self.assertEqual(self.fake.sent_to(new_owner["id"]), [])  # no chatter on owner changes

    def test_stage7_update_for_failed_activation_retries(self):
        org, bot_id = new_organizer(), self._pending(username="update_retry_test_bot")
        self._start(org, bot_id)
        self.fake.inject_error("setWebhook", 500, "Internal Server Error")
        token, _ = self.fake.create_managed_bot(self.manager, org, "update_retry_test_bot", "Ret")
        self.assertEqual(self._row(bot_id)["status"], "pending")
        self._token_or_owner_update(token, org)
        self.assertEqual(self._row(bot_id)["status"], "active")

    def test_stage7_update_for_deleted_bot_keeps_it_silent(self):
        bot, token = self._new_active_bot("deleted_update_test_bot")
        self.api("DELETE", f"/v1/bots/{bot['bot_id']}")
        telegram.set_webhook(token, f"{self.base}/webhook/{bot['bot_id']}", "x" * 32)  # someone re-pointed it
        self._token_or_owner_update(token, new_organizer())
        self.assertIsNone(self.fake.bot(token)["webhook"])
        self.assertEqual(self._row(bot["bot_id"])["status"], "deleted")

    def test_stage7_expired_linked_bot_is_not_activated(self):
        org, bot_id = new_organizer(), self._pending(username="expired_link_test_bot")
        self._start(org, bot_id)
        self.fake.inject_error("setWebhook", 500, "Internal Server Error")
        token, _ = self.fake.create_managed_bot(self.manager, org, "expired_link_test_bot", "Exp")
        with self.db() as c:
            c.execute("UPDATE bots SET expires_at='2000-01-01T00:00:00Z' WHERE bot_id=?", (bot_id,))
        self.assertIn("истёк", self._start(org, bot_id)["text"])  # reopening no longer retries
        self._token_or_owner_update(token, org)  # nor does a later update
        self.assertEqual(self.api("GET", f"/v1/bots/{bot_id}")[1]["status"], "expired")
        self.assertIsNone(self.fake.bot(token)["webhook"])

    def test_stage7_dev_endpoint_refuses_linked_bot(self):
        org, bot_id = new_organizer(), self._pending(username="devlinked_test_bot")
        self._start(org, bot_id)
        self.fake.inject_error("setWebhook", 500, "Internal Server Error")
        self.fake.create_managed_bot(self.manager, org, "devlinked_test_bot", "Dev")
        status, _ = self.api("POST", f"/v1/_dev/bots/{bot_id}/activate", {}, {"X-Dev-Key": DEV_KEY})
        self.assertEqual(status, 409)
        self.assertEqual(self._row(bot_id)["status"], "pending")


if __name__ == "__main__":
    unittest.main()
