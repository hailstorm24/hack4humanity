"""stubs/telegram.py against tests/fake_telegram.py.

    python3 -m unittest discover -s tests -v
"""
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "stubs")]

import telegram  # noqa: E402
from fake_telegram import FakeTelegram  # noqa: E402


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeTelegram().start()
        telegram.API_BASE = self.fake.base_url
        self.manager = self.fake.add_bot("h4h_manager_bot", "H4H Manager", can_manage_bots=True)
        self.plain = self.fake.add_bot("plain_bot", "Plain")

    def tearDown(self):
        self.fake.stop()

    def test_get_me_reports_can_manage_bots(self):
        me = telegram.get_me(self.manager)
        self.assertEqual(me["username"], "h4h_manager_bot")
        self.assertTrue(me["can_manage_bots"])
        self.assertFalse(telegram.get_me(self.plain)["can_manage_bots"])

    def test_bad_token_raises_401_without_leaking_token(self):
        bad = "123:not-a-real-token-at-all"
        with self.assertRaises(telegram.TelegramError) as cm:
            telegram.get_me(bad)
        self.assertEqual(cm.exception.code, 401)
        self.assertNotIn(bad, str(cm.exception))

    def test_network_error_is_telegram_error_without_token(self):
        telegram.API_BASE = "http://127.0.0.1:9"  # nothing listens on the discard port
        with self.assertRaises(telegram.TelegramError) as cm:
            telegram.get_me(self.manager)
        self.assertIsNone(cm.exception.code)
        self.assertNotIn(self.manager, str(cm.exception))

    def test_429_retried_once_when_wait_is_short(self):
        self.fake.inject_error("sendMessage", 429, "Too Many Requests: retry after 1", retry_after=1)
        t0 = time.monotonic()
        msg = telegram.send_message(self.plain, 42, "hi")
        self.assertGreaterEqual(time.monotonic() - t0, 1)
        self.assertEqual(msg["text"], "hi")
        self.assertEqual(len(self.fake.calls_to("sendMessage")), 2)

    def test_429_not_retried_twice_or_when_wait_is_long(self):
        self.fake.inject_error("sendMessage", 429, "Too Many Requests", retry_after=1, times=2)
        with self.assertRaises(telegram.TelegramError) as cm:
            telegram.send_message(self.plain, 42, "hi")
        self.assertEqual(cm.exception.code, 429)
        self.fake.inject_error("sendMessage", 429, "Too Many Requests", retry_after=60)
        with self.assertRaises(telegram.TelegramError) as cm:
            telegram.send_message(self.plain, 42, "hi")
        self.assertEqual(cm.exception.retry_after, 60)

    def test_webhook_set_info_delete(self):
        telegram.set_webhook(self.plain, "https://example.test/webhook/x", "s3cr3t_-OK", allowed_updates=["message"])
        info = telegram.get_webhook_info(self.plain)
        self.assertEqual(info["url"], "https://example.test/webhook/x")
        self.assertEqual(info["allowed_updates"], ["message"])
        telegram.delete_webhook(self.plain)
        self.assertEqual(telegram.get_webhook_info(self.plain)["url"], "")

    def test_webhook_secret_with_disallowed_chars_rejected(self):
        # token_urlsafe() output is allowed; base64 '+' '/' '=' are not.
        with self.assertRaises(telegram.TelegramError) as cm:
            telegram.set_webhook(self.plain, "https://example.test/h", "abc+/=")
        self.assertEqual(cm.exception.code, 400)

    def test_managed_bot_token_get_and_replace(self):
        managed = self.fake.add_bot("org_bot", "Org", manager_id=self.fake.bot(self.manager)["id"])
        uid = self.fake.bot(managed)["id"]
        self.assertEqual(telegram.get_managed_bot_token(self.manager, uid), managed)
        new = telegram.replace_managed_bot_token(self.manager, uid)
        self.assertNotEqual(new, managed)
        self.assertEqual(telegram.get_me(new)["username"], "org_bot")
        with self.assertRaises(telegram.TelegramError) as cm:
            telegram.get_me(managed)  # old token revoked
        self.assertEqual(cm.exception.code, 401)

    def test_cannot_fetch_token_of_bot_you_dont_manage(self):
        other_uid = self.fake.bot(self.plain)["id"]
        with self.assertRaises(telegram.TelegramError) as cm:
            telegram.get_managed_bot_token(self.manager, other_uid)
        self.assertEqual(cm.exception.code, 400)

    def test_profile_setters(self):
        telegram.set_my_name(self.plain, "Odesa Fact Check")
        telegram.set_my_description(self.plain, "Перешлите мне сообщение.")
        telegram.set_my_short_description(self.plain, "Проверка нарративов")
        telegram.set_my_commands(self.plain, [{"command": "start", "description": "Начать"}])
        bot = self.fake.bot(self.plain)
        self.assertEqual((bot["name"], bot["description"], bot["short_description"]),
                         ("Odesa Fact Check", "Перешлите мне сообщение.", "Проверка нарративов"))
        self.assertEqual(bot["commands"], [{"command": "start", "description": "Начать"}])

    def test_send_message_threads_reply(self):
        telegram.send_message(self.plain, 42, "reply", reply_to_message_id=7)
        sent = self.fake.sent_to(42)[-1]
        self.assertEqual(sent["reply_parameters"], {"message_id": 7, "allow_sending_without_reply": True})

    def test_send_message_over_4096_rejected(self):
        with self.assertRaises(telegram.TelegramError) as cm:
            telegram.send_message(self.plain, 42, "x" * 4097)
        self.assertEqual(cm.exception.code, 400)

    def test_request_managed_bot_keyboard_shape(self):
        kb = telegram.request_managed_bot_keyboard("Create bot", 5, "Odesa Fact Check", "odesa_factcheck_bot")
        self.assertEqual(kb["keyboard"], [[{"text": "Create bot", "request_managed_bot": {
            "request_id": 5, "suggested_name": "Odesa Fact Check", "suggested_username": "odesa_factcheck_bot"}}]])
        telegram.send_message(self.manager, 42, "Tap to create", reply_markup=kb)
        self.assertEqual(self.fake.sent_to(42)[-1]["reply_markup"], kb)


if __name__ == "__main__":
    unittest.main()
