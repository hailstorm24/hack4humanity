"""End-to-end bot lifecycle: the real service (stubs/server.py) against the fake Telegram.

The service runs as a subprocess with TELEGRAM_API_BASE pointing at the fake,
TELEGRAM_SEND=1 and a throwaway SQLite file. The fake plays Telegram: it
delivers updates to the service's webhooks and records what the service sends.

Steps that later stages build are skipped tests named after their stage. As
each stage lands, its skip is removed and the dev-activate shortcut in
`_activate_via_dev_endpoint` shrinks until it's gone (Stage 5).

    python3 -m unittest discover -s tests -v
"""
import json
import os
import socket
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
               "TELEGRAM_API_BASE": cls.fake.base_url, "TELEGRAM_SEND": "1",
               "PUBLIC_URL": f"http://127.0.0.1:{cls.port}", "MANAGER_BOT_TOKEN": cls.manager}
        env.pop("MANAGER_BOT_USERNAME", None)  # the username must come from getMe
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

    def _activate_via_dev_endpoint(self, bot_id, username):
        """Stand-in for Stages 3-5: make a managed bot in the fake, activate via the dev endpoint,
        and set its webhook the way Stage 5's activation will."""
        token = self.fake.add_bot(username, CONFIG["display_name"],
                                  manager_id=self.fake.bot(self.manager)["id"])
        status, act = self.api("POST", f"/v1/_dev/bots/{bot_id}/activate",
                               {"telegram_token": token, "telegram_username": username},
                               {"X-Dev-Key": DEV_KEY})
        self.assertEqual(status, 200, act)
        telegram.set_webhook(token, act["webhook_url"], act["secret_token"], allowed_updates=["message"])
        return token

    def _new_active_bot(self, username):
        status, bot = self.api("POST", "/v1/bots", {**CONFIG, "username": username})
        self.assertEqual(status, 201, bot)
        return bot, self._activate_via_dev_endpoint(bot["bot_id"], username)

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
        self.assertEqual(self.api("DELETE", f"/v1/bots/{bot['bot_id']}")[0], 204)
        before = len(self.fake.outbox)
        self.fake.user_sends(token, READER, text="НАТО провоцировало Россию")
        self.assertEqual(len(self.fake.outbox), before)

    # --- Later stages: shape fixed now, enabled as each stage lands ---------------

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

    def test_stage3_managed_bot_update_accepted_quietly(self):
        # Until Stage 5 it is only logged; it must not error or message the organizer.
        before = len(self.fake.sent_to(ORGANIZER["id"]))
        _, responses = self.fake.create_managed_bot(self.manager, ORGANIZER, "stage3_probe_bot", "Probe")
        self.assertEqual([r[0] for r in responses], [200, 200])
        self.assertEqual(len(self.fake.sent_to(ORGANIZER["id"])), before)

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

    @unittest.skip("Stage 4: /start <bot_id> records organizer and offers the create button")
    def test_stage4_start_link_offers_create_button(self):
        status, bot = self.api("POST", "/v1/bots", CONFIG)
        self.fake.user_sends(self.manager, ORGANIZER, text=f"/start {bot['bot_id']}")
        markup = self.fake.sent_to(ORGANIZER["id"])[-1]["reply_markup"]
        req = markup["keyboard"][0][0]["request_managed_bot"]
        self.assertEqual((req["suggested_name"], req["suggested_username"]),
                         (CONFIG["display_name"], CONFIG["username"]))

    @unittest.skip("Stage 5: managed_bot update activates the bot without the dev endpoint")
    def test_stage5_managed_bot_update_activates(self):
        status, bot = self.api("POST", "/v1/bots", CONFIG)
        self.fake.user_sends(self.manager, ORGANIZER, text=f"/start {bot['bot_id']}")
        token, _ = self.fake.create_managed_bot(self.manager, ORGANIZER, "renamed_by_organizer_bot", "Odesa")
        status, got = self.api("GET", f"/v1/bots/{bot['bot_id']}")
        self.assertEqual(got["status"], "active")
        self.assertEqual(got["telegram_username"], "renamed_by_organizer_bot")
        live = self.fake.bot(token)
        self.assertEqual((live["name"], live["description"]), (CONFIG["display_name"], CONFIG["description"]))
        self.assertTrue(live["webhook"]["url"].endswith(f"/webhook/{bot['bot_id']}"))

    @unittest.skip("Stage 7: DELETE calls deleteWebhook")
    def test_stage7_delete_removes_webhook(self):
        bot, token = self._new_active_bot("stage7_test_bot")
        self.api("DELETE", f"/v1/bots/{bot['bot_id']}")
        self.assertEqual(telegram.get_webhook_info(token)["url"], "")


if __name__ == "__main__":
    unittest.main()
