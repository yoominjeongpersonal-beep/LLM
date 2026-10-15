import unittest
from metrics import calculate_metrics


def financial(current=115, previous=100):
    return dict(id="F", kind="financial", published_at="2026-10-14", measurements={
        "revenue": dict(current=current, previous=previous, unit="억원", basis="연결",
                        period="2026년 2분기", previous_period="2025년 2분기",
                        period_end="2026-06-30", previous_period_end="2025-06-30")})


class MetricsTests(unittest.TestCase):
    def test_revenue_growth_uses_code_and_preserves_context(self):
        result = calculate_metrics([financial()])
        metric = result["items"][0]
        self.assertEqual(metric["change_pct"], 15.0)
        self.assertEqual(metric["unit"], "억원")
        self.assertEqual(metric["source_ids"], ["F"])
        self.assertIn("2025년 2분기", metric["comparison"])

    def test_zero_and_negative_baseline_are_not_misleading_percentages(self):
        for previous in (0, -100):
            metric = calculate_metrics([financial(previous=previous)])["items"][0]
            self.assertIsNone(metric["change_pct"])
            self.assertIn("증감률 계산 제외", metric["display"])

    def test_invalid_or_future_measurement_is_not_used(self):
        for value in (True, float("nan"), float("inf"), "115", 10**1000):
            self.assertEqual(calculate_metrics([financial(current=value)])["items"], [])
        record = financial()
        record["measurements"]["revenue"]["period_end"] = "2027-06-30"
        self.assertEqual(calculate_metrics([record])["items"], [])

    def test_relative_return_is_percentage_points_on_matching_dates(self):
        sources = [dict(id="M", kind="market", published_at="2026-10-14", prices=[
            dict(date="2026-09-14", close=100), dict(date="2026-10-14", close=103)]),
            dict(id="S", kind="sector", title="반도체 지수", published_at="2026-10-14", prices=[
                dict(date="2026-09-14", close=200), dict(date="2026-10-14", close=220)])]
        result = calculate_metrics(sources)
        metric = next(m for m in result["items"] if m["key"] == "relative_return")
        self.assertEqual(metric["stock_return_pct"], 3.0)
        self.assertEqual(metric["sector_return_pct"], 10.0)
        self.assertEqual(metric["difference_pp"], -7.0)
        sources[1]["prices"][0]["date"] = "2026-09-15"
        self.assertNotIn("relative_return", [m["key"] for m in calculate_metrics(sources)["items"]])

    def test_volume_uses_disjoint_five_and_twenty_observations(self):
        points = [dict(date="2026-09-%02d" % (i+1), close=100, volume=1000 if i<20 else 750)
                  for i in range(25)]
        result = calculate_metrics([dict(id="M", kind="market", published_at="2026-10-14", prices=points)])
        metric = next(m for m in result["items"] if m["key"] == "volume_change")
        self.assertEqual(metric["change_pct"], -25.0)
        self.assertEqual(metric["recent_average"], 750)
        self.assertEqual(metric["previous_average"], 1000)

    def test_duplicate_dates_and_future_prices_are_rejected(self):
        for dates in (("2026-10-13", "2026-10-13"), ("2026-10-13", "2026-10-16")):
            record = dict(id="M", kind="market", published_at="2026-10-14",
                          prices=[dict(date=d, close=100, volume=100) for d in dates])
            self.assertEqual(calculate_metrics([record])["items"], [])

    def test_missing_numbers_remain_explicitly_missing(self):
        result = calculate_metrics([])
        self.assertEqual(result["items"], [])
        self.assertIn("매출 증감률", result["missing"])
