from datetime import date, timedelta
from fractions import Fraction
import unittest

from strategy import features, simulate


def fixture(n=25):
    rows = [{"date": (date(2020, 1, 1)+timedelta(days=i)).isoformat(),
             "open": "10", "close": "10", "adjusted_close": "10",
             "share_factor": "1", "cumulative_cash": "0", "volume": "100"}
            for i in range(n)]
    feat = [{"value": 50, "above_ma": False, "below_ma": False} for _ in rows]
    return rows, feat


def run(rows, feat, name="COMBO_WAIT", cost=0, liquidate=True):
    return simulate(rows, feat, name, rows[0]["date"], rows[-1]["date"], cost, liquidate)


class StrategyTest(unittest.TestCase):
    def test_features_exact_mean_and_nonrecursive_strength(self):
        rows, _ = fixture(40)
        for i, row in enumerate(rows):
            row["adjusted_close"] = str(100+i%7)
        feat = features(rows)
        for i in range(13, len(rows)):
            closes = [Fraction(r["adjusted_close"]) for r in rows]
            changes = [closes[j]-closes[j-1] for j in range(i-12, i+1)]
            expected = 100*sum(max(0, x) for x in changes)/sum(abs(x) for x in changes)
            self.assertAlmostEqual(feat[i]["value"], float(expected))
            mean = sum(closes[i-9:i+1])/10
            self.assertEqual(feat[i]["above_ma"], closes[i] > mean)
            self.assertEqual(feat[i]["below_ma"], closes[i] < mean)

    def test_wait_for_later_ma_and_no70_exit(self):
        rows, feat = fixture()
        feat[13]["value"] = 20
        feat[14]["value"] = 31
        feat[16]["above_ma"] = True
        feat[18].update(value=5, below_ma=True)
        rows[17]["open"], rows[19]["open"] = "11", "9"
        result = run(rows, feat)
        trade = result["trades"][0]
        self.assertEqual((trade["entry_signal_index"], trade["entry_index"]), (16, 17))
        self.assertEqual((trade["exit_signal_index"], trade["exit_index"]), (18, 19))
        self.assertFalse(trade["forced_end"])
        self.assertAlmostEqual(result["nav"][-1]["nav"], 9/11)
        self.assertEqual(run(rows, feat, "COMBO_SAME")["trades"], [])

    def test_setup_consumed_and_new_cycle_required(self):
        rows, feat = fixture()
        feat[13]["value"] = 20
        feat[14].update(value=31, above_ma=True)
        feat[16]["below_ma"] = True
        for i in range(17, len(rows)):
            feat[i]["above_ma"] = True
        result = run(rows, feat)
        self.assertEqual(len(result["trades"]), 1)
        feat[20]["value"] = 20
        self.assertEqual(len(run(rows, feat)["trades"]), 2)

    def test_ma_equality_keeps_state(self):
        rows, feat = fixture()
        self.assertEqual(run(rows, feat, "MA10_ONLY")["trades"], [])
        feat[13]["above_ma"] = True
        result = run(rows, feat, "MA10_ONLY")
        self.assertEqual(len(result["trades"]), 1)
        self.assertTrue(result["trades"][0]["forced_end"])
        self.assertEqual(result["metrics"]["natural_exits"], 0)

    def test_exact_two_sided_fees_on_buy_hold(self):
        rows, feat = fixture()
        result = run(rows, feat, "BUY_HOLD", cost=10)
        expected = (1-.0005)/(1+.0005)
        self.assertAlmostEqual(result["nav"][-1]["nav"], expected)
        self.assertAlmostEqual(result["metrics"]["fees_initial_capital"], 1-expected)
        self.assertEqual(result["trades"][0]["entry_index"], 14)

    def test_split_dividend_before_open_and_no_reinvestment(self):
        rows, feat = fixture()
        feat[13]["above_ma"] = True
        feat[16]["below_ma"] = True
        feat[18]["above_ma"] = True
        for i in range(16, len(rows)):
            rows[i].update(share_factor="2", cumulative_cash="0.4", open="5", close="5")
        result = run(rows, feat, "MA10_ONLY")
        first, second = result["trades"]
        self.assertAlmostEqual(first["exit_shares"], .2)
        self.assertAlmostEqual(first["earned_dividends"], .04)
        self.assertAlmostEqual(second["entry_cash"], 1)
        self.assertAlmostEqual(second["entry_shares"], .2)
        self.assertAlmostEqual(result["nav"][-1]["nav"], 1.04)

    def test_ex_date_new_holder_does_not_receive_coupon(self):
        rows, feat = fixture()
        for i in range(14, len(rows)):
            rows[i]["cumulative_cash"] = "1"
        result = run(rows, feat, "BUY_HOLD")
        self.assertEqual(result["metrics"]["dividend_reserve"], 0)

    def test_sell_open_holder_still_receives_ex_date_coupon(self):
        rows, feat = fixture()
        feat[13]["above_ma"] = True
        feat[15]["below_ma"] = True
        for i in range(16, len(rows)):
            rows[i]["cumulative_cash"] = "1"
        result = run(rows, feat, "MA10_ONLY")
        self.assertAlmostEqual(result["trades"][0]["earned_dividends"], .1)

    def test_no_future_information_in_features_or_trades(self):
        rows, feat = fixture(50)
        for i, row in enumerate(rows):
            row["adjusted_close"] = str(10+(i%9-4)/10)
        f = features(rows)
        prefix = features(rows[:35])
        self.assertEqual(f[:35], prefix)
        full = run(rows, f, "MA10_ONLY", liquidate=False)
        short = run(rows[:35], prefix, "MA10_ONLY", liquidate=False)
        self.assertEqual(full["nav"][:len(short["nav"])], short["nav"])

    def test_first_day_can_recover_from_previous_low(self):
        rows, feat = fixture()
        feat[12]["value"] = 29
        feat[13].update(value=30, above_ma=True)
        result = run(rows, feat, "COMBO_SAME")
        self.assertEqual(result["trades"][0]["entry_index"], 14)


if __name__ == "__main__":
    unittest.main()
