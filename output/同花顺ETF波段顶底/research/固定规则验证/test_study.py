"""事件研究的成交时点、现金/份额权益和去重边界。"""
import unittest
from run_study import deduplicate, opportunity, segment, signals


def row(day, price, shares=1, cash=0, low=None):
    return dict(date=day, open=price, close=price, high=price,
                low=price if low is None else low, share_factor=shares,
                cumulative_cash=cash, adjusted_close=price*shares+cash, volume=100)


class StudyTests(unittest.TestCase):
    def test_next_open_and_exact_holding_session_count(self):
        data = [row("2022-01-03", 100), row("2022-01-04", 10), row("2022-01-05", 11)]
        event = opportunity(data, 0, 2)
        self.assertEqual(event["entry_date"], "2022-01-04")
        self.assertEqual(event["exit_date"], "2022-01-05")
        self.assertAlmostEqual(event["gross_return"], 0.1)
        self.assertIsNone(opportunity(data, 0, 3))

    def test_split_and_cash_dividend_are_not_a_price_crash(self):
        data = [row("2022-01-03", 10), row("2022-01-04", 10),
                row("2022-01-05", 4.5, shares=2, cash=1, low=4.4)]
        event = opportunity(data, 0, 2)
        self.assertAlmostEqual(event["gross_return"], 0)
        self.assertAlmostEqual(event["mae_gross"], -0.02)

    def test_entry_day_cash_is_not_credited_to_new_holder(self):
        data = [row("2022-01-03", 10), row("2022-01-04", 5, shares=2, cash=1),
                row("2022-01-05", 5, shares=2, cash=1.4)]
        self.assertAlmostEqual(opportunity(data, 0, 2)["gross_return"], 0.04)

    def test_split_boundary_is_purged(self):
        self.assertIsNone(segment("2020-12-31", "2021-01-04", "2021-01-11"))
        self.assertEqual(segment("2021-01-04", "2021-01-05", "2021-01-15"), "historical_holdout")

    def test_no_overlapping_holding_windows(self):
        events = [dict(entry_index=i, exit_index=i+4) for i in [1, 2, 5, 6, 8, 11]]
        self.assertEqual([e["entry_index"] for e in deduplicate(events)], [1, 6, 11])

    def test_signals_do_not_depend_on_future_prices(self):
        prices = list(range(30, 10, -1)) + [20, 21, 22, 23, 24, 25]
        values, flags = signals(prices)
        extended_values, extended_flags = signals(prices+[100, 1, 200])
        self.assertEqual(values, extended_values[:len(prices)])
        self.assertEqual(flags, extended_flags[:len(prices)])


if __name__ == "__main__":
    unittest.main()
