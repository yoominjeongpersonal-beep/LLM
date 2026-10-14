import tempfile
import unittest
from pathlib import Path

from bot import Bot, render
from storage import Store


def source(id, kind, **overrides):
    record = dict(id=id, kind=kind, ticker="005930", title=id, text="평가용 자료",
                  url="https://example.com/" + id, published_at="2026-10-14",
                  observed_at="2026-10-14", valid_until="2026-10-15",
                  reviewed=True, synthetic=False)
    record.update(overrides)
    return record


def answer(context):
    return dict(verdict="관망", reason="실적과 시장 반응을 함께 확인해요.",
                counter="시장이 늦게 반응할 수 있어요.", change="거래량 증가 시 재검토해요.",
                source_ids=[s["id"] for s in context["sources"]], principle_ids=["P01"])


class BotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "bot.db")
        self.bot = Bot(self.store, answer)

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, **market):
        self.store.import_sources([
            source("P01", "principle", ticker="*"), source("F1", "financial"),
            source("M1", "market", **market), source("S1", "sector")])

    def ask(self):
        return self.bot.ask("삼성전자 살까?", "1~3개월", "2026-10-15")

    def test_complete_data_returns_cited_answer_and_snapshot(self):
        self.seed()
        result = self.ask()
        self.assertEqual(result["verdict"], "관망")
        self.assertIn("https://example.com/F1", render(result))
        self.assertEqual(self.store.history()[0]["sources"][0]["text"], "평가용 자료")
        self.assertEqual(self.store.history()[0]["question"], "삼성전자 살까?")

    def test_missing_data_is_saved_without_model_call(self):
        def forbidden(_):
            self.fail("불충분한 자료로 모델을 호출했습니다")
        result = Bot(self.store, forbidden).ask("삼성전자", "1년", "2026-10-15")
        self.assertEqual(result["verdict"], "판단 보류")
        self.assertIn("market", result["missing"])
        self.assertEqual(len(self.store.history()), 1)

    def test_future_published_data_is_excluded(self):
        self.seed(published_at="2026-10-16")
        self.assertEqual(self.ask()["verdict"], "판단 보류")

    def test_future_observed_data_is_excluded(self):
        self.seed(observed_at="2026-10-16", valid_until="2026-10-17")
        self.assertEqual(self.ask()["verdict"], "판단 보류")

    def test_expired_or_old_market_data_is_excluded(self):
        self.seed(observed_at="2026-10-10")
        self.assertEqual(self.ask()["verdict"], "판단 보류")

    def test_expired_data_is_excluded_even_if_observed_recently(self):
        self.seed(valid_until="2026-10-14")
        self.assertEqual(self.ask()["verdict"], "판단 보류")

    def test_network_failure_returns_saved_abstention(self):
        self.seed()
        def unavailable(_):
            raise OSError("offline")
        result = Bot(self.store, unavailable).ask("삼성전자", "1년", "2026-10-15")
        self.assertEqual(result["status"], "generation_failed")
        self.assertEqual(self.store.history()[0]["verdict"], "판단 보류")

    def test_model_cannot_add_fields_to_override_source_snapshot(self):
        self.seed()
        def invalid(context):
            return dict(answer(context), sources=[])
        result = Bot(self.store, invalid).ask("삼성전자", "1년", "2026-10-15")
        self.assertEqual(result["verdict"], "판단 보류")
        self.assertEqual(len(result["sources"]), 4)

    def test_unreviewed_principle_cannot_be_used(self):
        self.seed()
        self.store.import_sources([source("P01", "principle", reviewed=False)])
        self.assertEqual(self.ask()["verdict"], "판단 보류")

    def test_invalid_citations_retry_then_abstain(self):
        self.seed()
        def invalid(context):
            return dict(answer(context), source_ids=["invented"])
        result = Bot(self.store, invalid).ask("삼성전자", "1년", "2026-10-15")
        self.assertEqual(result["verdict"], "판단 보류")
        self.assertEqual(result["attempts"], 2)

    def test_missing_horizon_asks_for_clarification(self):
        self.assertEqual(self.bot.ask("삼성전자")["status"], "needs_horizon")

    def test_ambiguous_and_unsupported_tickers_do_not_analyze(self):
        for question in ("삼성전자와 SK하이닉스 비교", "네이버 살까?"):
            self.assertEqual(self.bot.ask(question, "1년")["status"], "unsupported")

    def test_import_is_atomic_on_invalid_record(self):
        with self.assertRaises(ValueError):
            self.store.import_sources([source("ok", "market"), source("bad", "market", url="oops")])
        self.assertEqual(self.store.sources("2026-10-15"), [])

    def test_synthetic_data_cannot_look_like_real_analysis(self):
        self.seed(synthetic=True)
        self.assertIn("가상", render(self.ask()))

    def test_source_title_cannot_emit_slack_broadcast(self):
        self.seed()
        self.store.import_sources([source("F1", "financial", title="<!channel> 공시")])
        self.assertNotIn("<!channel>", render(self.ask()))


if __name__ == "__main__":
    unittest.main()
