import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app import import_document
from bot import Bot, render
from storage import Store


class DocumentTests(unittest.TestCase):
    def setUp(self):
        clock = patch("app.today", return_value="2026-10-15")
        clock.start()
        self.addCleanup(clock.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.db")
        self.file = Path(self.temp.name) / "report.md"
        self.file.write_text("# 삼성전자\n매출은 100억원에서 115억원으로 증가. 평가용 가상 자료.")
        self.calls = 0

    def tearDown(self):
        self.temp.cleanup()

    def add(self):
        return import_document(self.store, self.file, "005930", "2026-10-14", "2026-11-14", synthetic=True)

    def generate(self, context):
        self.calls += 1
        return dict(verdict="혼재", reason="매출은 늘었지만 이익 자료는 부족해요.",
                    counter="비용 증가 가능성을 확인해야 해요.", change="이익과 현금흐름 자료를 확인해요.",
                    source_ids=[context["sources"][0]["id"]], principle_ids=[])

    def ask(self, **kwargs):
        return Bot(self.store, self.generate, mode="documents").ask("삼성전자 재무를 분석해줘", as_of="2026-10-15", **kwargs)

    def test_document_analysis_needs_neither_market_data_nor_horizon(self):
        self.add()
        result = self.ask()
        self.assertEqual(result["status"], "answered")
        self.assertIn("현재 가격", render(result))
        self.assertIn("일반 문서 분석", render(result))
        self.assertIn("가상", render(result))

    def test_preview_calls_no_model_and_creates_no_analysis(self):
        self.add()
        result = self.ask(preview=True)
        self.assertEqual(result["status"], "preview")
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.store.history(), [])

    def test_invalid_preview_creates_no_analysis(self):
        Bot(self.store, self.generate, mode="documents").ask("네이버", preview=True)
        Bot(self.store, self.generate).ask("삼성전자", preview=True)
        self.assertEqual(self.store.history(), [])
        self.assertEqual(self.calls, 0)

    def test_identical_question_and_sources_reuse_answer(self):
        self.add()
        first = self.ask()
        second = self.ask()
        self.assertEqual(self.calls, 1)
        self.assertEqual(second["analysis_id"], first["analysis_id"])
        self.assertTrue(second["cached"])

    def test_changed_document_invalidates_cache(self):
        self.add()
        self.ask()
        self.file.write_text("삼성전자 영업이익 감소. 평가용 가상 자료.")
        self.add()
        self.ask()
        self.assertEqual(self.calls, 2)

    def test_explicit_refresh_bypasses_cache(self):
        self.add()
        self.ask()
        self.ask(refresh=True)
        self.assertEqual(self.calls, 2)

    def test_future_document_is_not_analyzed(self):
        self.add()
        result = Bot(self.store, self.generate, mode="documents").ask("삼성전자", as_of="2026-10-13")
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(self.calls, 0)

    def test_document_mode_rejects_buy_verdict(self):
        self.add()
        def wrong(context):
            return dict(self.generate(context), verdict="매수 검토")
        result = Bot(self.store, wrong, mode="documents").ask("삼성전자", as_of="2026-10-15")
        self.assertEqual(result["status"], "generation_failed")
        self.assertEqual(self.calls, 1)

    def test_price_sources_are_not_silently_used_in_document_mode(self):
        self.add()
        market = dict(self.store.sources("2026-10-15")[0], id="M1", kind="market")
        self.store.import_sources([market])
        result = self.ask()
        self.assertTrue(all(s["kind"] in {"document", "financial", "principle"} for s in result["sources"]))


if __name__ == "__main__":
    unittest.main()
