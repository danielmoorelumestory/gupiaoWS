"""截图回归数值、窗口边界与时间因果性；不联网。"""
import unittest
from pathlib import Path

from bruce_replica.etf_band import calculate_rows, etf_band, explain_rows, load_prices, zone

ARCHIVE = Path(__file__).resolve().parents[3] / "同花顺ETF波段顶底"


class EtfBandTests(unittest.TestCase):
    def test_verified_price_snapshot(self):
        rows, source = load_prices(ARCHIVE / "evidence/tencent-588060.json")
        self.assertEqual(source["source_series"], "day")
        values = {r["date"]: r for r in calculate_rows(rows)}
        self.assertEqual(values["2026-11-13"]["display_value"], "53.115")
        self.assertAlmostEqual(values["2026-11-13"]["value"], 3240 / 61, places=12)
        self.assertEqual(values["2026-08-18"]["display_value"], "71.661")
        self.assertEqual(values["2026-10-19"]["display_value"], "3.478")

    def test_fourteen_closes_needed_for_thirteen_changes(self):
        values = etf_band(range(1, 16))
        self.assertEqual(values[:13], [None] * 13)
        self.assertEqual(values[13:], [100, 100])
        self.assertEqual(etf_band(range(15, 0, -1))[13:], [0, 0])

    def test_flat_window_becomes_undefined_after_old_move_expires(self):
        values = etf_band(["1", "1.001"] + ["1.001"] * 13)
        self.assertEqual(values[-2], 100)
        self.assertIsNone(values[-1])
        self.assertEqual(etf_band([1] * 20), [None] * 20)

    def test_missing_price_requires_a_new_complete_window(self):
        values = etf_band(list(range(1, 15)) + [None] + list(range(1, 15)))
        self.assertEqual(values[13], 100)
        self.assertEqual(values[14:28], [None] * 14)
        self.assertEqual(values[-1], 100)

    def test_future_prices_cannot_change_past_readings(self):
        prices = [100, 102, 101, 105, 99, 101, 107, 103, 101, 100, 98, 99, 100, 101, 102]
        prefix = etf_band(prices)
        self.assertEqual(etf_band(prices + [300, 1, 900])[:len(prices)], prefix)

    def test_bad_prices_periods_and_dates_are_rejected(self):
        for price in [0, -1, "NaN", "Infinity", "bad"]:
            with self.subTest(price=price), self.assertRaises(ValueError):
                etf_band([price])
        for period in [0, -1, True, 1.5]:
            with self.subTest(period=period), self.assertRaises(ValueError):
                etf_band([1], period)
        with self.assertRaises(ValueError):
            calculate_rows([{"date": "2026-01-02", "close": "1"}] * 2)

    def test_threshold_boundaries_are_explicit_project_choices(self):
        self.assertEqual(zone(29.999), "低位区")
        self.assertEqual(zone(70.001), "高位区")
        self.assertEqual(zone(30), "中间区")
        self.assertEqual(zone(70), "中间区")
        self.assertEqual(zone(None), "无有效值")

    def test_explanation_keeps_verified_values_and_explains_expiry(self):
        rows, _ = load_prices(ARCHIVE / "evidence/tencent-588060.json")
        plain, explained = calculate_rows(rows), explain_rows(rows)
        self.assertEqual([r["value"] for r in plain], [r["value"] for r in explained])
        last = explained[-1]
        self.assertAlmostEqual(last["incoming_change"], -0.016)
        self.assertAlmostEqual(last["outgoing_change"], -0.036)
        self.assertAlmostEqual(last["expiry_contribution_points"], 6.209209475645462)
        self.assertAlmostEqual(last["incoming_contribution_points"], -2.9406092234386523)
        self.assertIn("价格未涨", last["mechanism"])
        for r in explained:
            if r["expiry_contribution_points"] is not None:
                self.assertAlmostEqual(r["value_change_points"], r["expiry_contribution_points"]
                                       + r["incoming_contribution_points"], places=11)

    def test_explanation_does_not_invent_intermediate_zero_denominator(self):
        rows = [{"date": f"2026-01-{i+1:02d}", "close": c}
                for i, c in enumerate([1, 2, 2, 3])]
        last = explain_rows(rows, 2)[-1]
        self.assertEqual(last["value"], 100)
        self.assertIsNone(last["expiry_contribution_points"])
        self.assertIn("零波动", last["decomposition_status"])

    def test_explanation_respects_missing_values_and_prefix_causality(self):
        rows = [{"date": f"2026-01-{i+1:02d}", "close": c}
                for i, c in enumerate([1, 2, 1, None, 2, 3, 4])]
        explained = explain_rows(rows, 2)
        self.assertIsNone(explained[5]["value"])
        self.assertEqual(explained[6]["value"], 100)
        self.assertEqual(explain_rows(rows[:6], 2), explained[:6])


if __name__ == "__main__":
    unittest.main()
