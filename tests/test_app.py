import json
import tempfile
import unittest
from pathlib import Path
from app import handle_mention
from bot import Bot
from storage import Store


class SlackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "bot.db")
        self.bot = Bot(self.store)
        self.sent = []

    def tearDown(self):
        self.temp.cleanup()

    def post(self, **message):
        self.sent.append(message)

    def test_horizon_followup_preserves_question_in_thread(self):
        event = dict(text="<@BOT> 삼성전자 살까?", channel="C1", ts="1", user="U1")
        handle_mention("e1", event, self.bot, self.post)
        handle_mention("e2", dict(event, text="<@BOT> 1~3개월", ts="2", thread_ts="1"), self.bot, self.post)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[-1]["thread_ts"], "1")
        self.assertEqual(self.store.history()[0]["question"], "삼성전자 살까?")
        self.assertEqual(self.store.history()[0]["horizon"], "1~3개월")

    def test_duplicate_event_does_not_post_twice(self):
        event = dict(text="<@BOT> 삼성전자 1년", channel="C1", ts="1", user="U1")
        handle_mention("e1", event, self.bot, self.post)
        handle_mention("e1", event, self.bot, self.post)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(self.store.history()), 1)

    def test_same_ticker_followup_keeps_horizon(self):
        event = dict(text="<@BOT> 삼성전자 1년", channel="C1", ts="1", user="U1")
        handle_mention("e1", event, self.bot, self.post)
        handle_mention("e2", dict(event, text="<@BOT> 삼성전자 반대 근거는?", ts="2", thread_ts="1"), self.bot, self.post)
        self.assertEqual(self.store.history()[0]["horizon"], "1년")

    def test_changed_ticker_does_not_inherit_horizon(self):
        event = dict(text="<@BOT> 삼성전자 1년", channel="C1", ts="1", user="U1")
        handle_mention("e1", event, self.bot, self.post)
        handle_mention("e2", dict(event, text="<@BOT> SK하이닉스는?", ts="2", thread_ts="1"), self.bot, self.post)
        self.assertEqual(self.store.history()[0]["status"], "needs_horizon")

    def test_failed_delivery_retries_cached_analysis(self):
        event = dict(text="<@BOT> 삼성전자 1년", channel="C1", ts="1", user="U1")
        def fail(**_):
            raise OSError("network")
        with self.assertRaises(OSError):
            handle_mention("e1", event, self.bot, fail)
        handle_mention("e1", event, self.bot, self.post)
        self.assertEqual(len(self.store.history()), 1)
        self.assertEqual(len(self.sent), 1)

    def test_another_user_cannot_overwrite_pending_question(self):
        event = dict(text="<@BOT> 삼성전자", channel="C1", ts="1", user="U1")
        handle_mention("e1", event, self.bot, self.post)
        handle_mention("e2", dict(event, user="U2", text="<@BOT> 1년", ts="2", thread_ts="1"), self.bot, self.post)
        self.assertNotEqual(self.store.history()[0]["question"], "삼성전자")


if __name__ == "__main__":
    unittest.main()
