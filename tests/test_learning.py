import tempfile
import unittest
from pathlib import Path

from bot import Bot
from learning import Learning
from storage import Store
from app import handle_mention


class LearningTests(unittest.TestCase):
    def test_slack_command_router_uses_learning_before_company_analysis(self):
        bot = Bot(self.store, mode="viewpoint")
        post = lambda **m: self.sent.append(m)
        handle_mention("start", self.event("1", "<@BOT1> 자료 추가"), bot, post, self.learning)
        self.add()
        handle_mention("extract", self.event("3", "<@BOT1> 관점 정리"), bot, post, self.learning)
        handle_mention("approve", self.event("4", "<@BOT1> 승인"), bot, post, self.learning)
        self.assertEqual(self.store.history(), [])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(any(s["kind"] == "principle" for s in self.store.sources("2099-01-01")))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "test.db")
        self.sent, self.calls = [], []
        self.learning = Learning(self.store, self.generate, persona="katoo")

    def generate(self, context):
        self.calls.append(context)
        source = context["sources"][0]
        return {"principles": [{"statement": "싸다는 이유만으로 사지 않는다.",
                                "conditions": "투자 시점 판단", "kind": "principle",
                                "source_id": source["id"], "quote": source["text"][:30]}]}

    def event(self, ts, text, user="U1", thread="1"):
        return dict(channel="C1", user=user, ts=ts, thread_ts=thread, text=text)

    def send(self, ts, text, user="U1"):
        return self.learning.handle_mention("E" + ts, self.event(ts, text, user), lambda **m: self.sent.append(m))

    def open(self):
        self.send("1", "자료 추가")

    def add(self, ts="2", user="U1"):
        return self.learning.handle_message("M" + ts, self.event(ts, "싸다고 미리 사기보다 시장에 돈이 들어오는지 확인해야 한다.", user), lambda **m: self.sent.append(m))

    def test_plain_replies_only_saved_in_open_learning_thread(self):
        self.assertFalse(self.add())
        self.open()
        self.assertTrue(self.add())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.sources("2099-01-01"), [])

    def test_extract_then_owner_approval_activates_cited_sources(self):
        self.open()
        self.add()
        self.send("3", "관점 정리")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.store.sources("2099-01-01"), [])
        self.send("4", "승인", user="U2")
        self.assertEqual(self.store.sources("2099-01-01"), [])
        self.send("5", "승인")
        sources = self.store.sources("2099-01-01")
        self.assertEqual({s["kind"] for s in sources}, {"principle", "perspective_material"})
        self.assertTrue(all(s["persona"] == "katoo" for s in sources))

    def test_duplicate_events_and_repeated_extraction_do_not_charge_again(self):
        self.open()
        self.add()
        self.add()
        self.send("3", "관점 정리")
        self.send("3", "관점 정리")
        self.send("4", "관점 정리")
        self.assertEqual(len(self.calls), 1)

    def test_new_material_requires_new_review_before_approval(self):
        self.open()
        self.add()
        self.send("3", "관점 정리")
        self.add("4")
        self.send("5", "승인")
        self.assertEqual(self.store.sources("2099-01-01"), [])

    def test_revision_is_reviewed_before_activation(self):
        self.open()
        self.add()
        self.send("3", "관점 정리")
        self.send("4", "수정: 싸다고 무조건 피한다는 뜻은 아니야")
        self.send("4b", "수정: 싸다고 무조건 피한다는 뜻은 아니야")
        self.assertEqual(len(self.calls), 2)
        self.assertIn("feedback", self.calls[-1])
        self.assertEqual(self.store.sources("2099-01-01"), [])
        self.send("5", "승인")
        self.assertEqual(len(self.store.sources("2099-01-01")), 2)

    def test_colleague_mention_in_source_is_preserved(self):
        self.learning.bot_user_id = "BOT1"
        self.open()
        self.learning.handle_message("mention-source", self.event("2", "<@U2>도 말했지만 싸다고 미리 사기보다 시장에 돈이 들어오는지 확인해야 한다."), lambda **m: self.sent.append(m))
        self.send("3", "관점 정리")
        self.assertIn("<@U2>", self.calls[0]["sources"][0]["text"])

    def test_private_learning_is_not_used_in_other_channel(self):
        self.open()
        self.add()
        self.send("3", "관점 정리")
        self.send("4", "승인")
        def forbidden(_):
            self.fail("다른 채널의 원문으로 답변 생성")
        result = Bot(self.store, forbidden, mode="viewpoint").ask("카투의 투자 원칙은?", channel="OTHER")
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["sources"], [])

    def test_link_only_requires_body_before_paid_extraction(self):
        self.open()
        self.learning.handle_message("link", self.event("2", "https://x.com/example/status/1"), lambda **m: self.sent.append(m))
        self.send("3", "관점 정리")
        self.assertEqual(len(self.calls), 0)

    def test_unrelated_people_and_bot_messages_not_collected(self):
        self.open()
        self.add(user="U2")
        event = dict(self.event("3", "봇 답변"), bot_id="B1")
        self.learning.handle_message("B", event, lambda **m: self.sent.append(m))
        self.send("4", "관점 정리")
        self.assertEqual(self.calls, [])

    def test_fabricated_quote_never_activates(self):
        self.open()
        self.add()
        def wrong(context):
            result = self.generate(context)
            result["principles"][0]["quote"] = "원문에 없는 문장"
            return result
        self.learning.generate = wrong
        self.send("3", "관점 정리")
        self.send("4", "승인")
        self.assertEqual(self.store.sources("2099-01-01"), [])

    def test_approved_viewpoint_can_answer_without_company_document(self):
        self.open()
        self.add()
        self.send("3", "관점 정리")
        self.send("4", "승인")
        def answer(context):
            self.assertEqual(context["mode"], "viewpoint")
            self.assertEqual(context["research_sources"], [])
            self.assertTrue(context["perspective_sources"])
            return dict(verdict="혼재", reason="승인된 글은 가격뿐 아니라 시장 반응도 보라고 말해요.",
                        counter="기업 가치가 먼저 개선될 수도 있어요.", change="최신 실적과 시세 확인이 필요해요.",
                        source_ids=[s["id"] for s in context["sources"] if s["kind"] == "perspective_material"],
                        principle_ids=[s["id"] for s in context["sources"] if s["kind"] == "principle"])
        result = Bot(self.store, answer, mode="viewpoint").ask("이 관점에서 하이닉스는 어떻게 봐?")
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["ticker"], "*")


if __name__ == "__main__":
    unittest.main()
