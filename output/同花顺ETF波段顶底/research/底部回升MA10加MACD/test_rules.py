from datetime import date, timedelta
import unittest

from rules import features, plan, simulate, verify_dependencies


def fixture(n=30):
    rows = [{"date": (date(2020, 1, 1)+timedelta(days=i)).isoformat(),
             "open": "10", "close": "10", "adjusted_close": "10",
             "share_factor": "1", "cumulative_cash": "0", "volume": "100"}
            for i in range(n)]
    feat = [{"value": 50, "above_ma": True, "below_ma": False,
             "dif": "0", "dea": "0", "death_cross": False, "bearish": False} for _ in rows]
    feat[13]["value"] = 20
    feat[14]["value"] = 31
    return rows, feat


def run(rows, feat, strategy="MACD_STATE", cost=0, liquidate=True):
    return simulate(rows, feat, strategy, rows[0]["date"], rows[-1]["date"], cost, liquidate)


class RulesTest(unittest.TestCase):
    def test_frozen_dependencies(self):
        verify_dependencies()

    def test_no_entry_below_ma_or_later_without_fresh_recovery(self):
        rows, f = fixture()
        f[14].update(above_ma=False, below_ma=True)
        result = run(rows, f)
        self.assertEqual(result["trades"], [])

    def test_entry_next_open_without_macd_buy_filter(self):
        rows, f = fixture()
        f[14].update(bearish=True, dif="-1", dea="0")
        result = run(rows, f)
        self.assertEqual(result["trades"][0]["entry_index"], 15)
        self.assertEqual(result["trades"][0]["entry_signal_index"], 14)

    def test_prior_ma_break_then_later_death_cross_sells(self):
        rows, f = fixture()
        for i in range(16, 20):
            f[i].update(above_ma=False, below_ma=True)
        f[18]["death_cross"] = True
        result = run(rows, f)
        t = result["trades"][0]
        self.assertEqual((t["exit_signal_index"], t["exit_index"]), (18, 19))
        self.assertFalse(t["forced_end"])

    def test_price_recovery_before_death_does_not_sell_price_branch(self):
        rows, f = fixture()
        f[16].update(above_ma=False, below_ma=True)
        f[18]["death_cross"] = True
        self.assertTrue(run(rows, f)["trades"][0]["forced_end"])

    def test_already_bearish_is_not_fresh_death(self):
        rows, f = fixture()
        for i in range(16, len(rows)):
            f[i].update(above_ma=False, below_ma=True, bearish=True, dif="-1", dea="0")
        self.assertTrue(run(rows, f)["trades"][0]["forced_end"])

    def test_top_branch_sells_above_ma_after_delayed_death(self):
        rows, f = fixture()
        f[16]["value"] = 75
        f[17]["value"] = 69
        f[19]["death_cross"] = True
        t = run(rows, f)["trades"][0]
        self.assertEqual(t["exit_index"], 20)
        self.assertTrue(t["exit_top_branch"])
        self.assertFalse(t["exit_price_below_ma"])
        self.assertEqual(t["held_last_down70_date"], rows[17]["date"])

    def test_pre_entry_high_does_not_qualify_as_held_top(self):
        rows, f = fixture()
        f[12]["value"] = 80
        f[18]["death_cross"] = True
        self.assertTrue(run(rows, f)["trades"][0]["forced_end"])

    def test_top_recovers_above70_before_death(self):
        rows, f = fixture()
        f[16]["value"] = 75
        f[17]["value"] = 69
        f[18].update(value=72, death_cross=True)
        self.assertTrue(run(rows, f)["trades"][0]["forced_end"])

    def test_new_position_resets_top_memory(self):
        rows, f = fixture(40)
        f[16]["value"] = 75
        f[17].update(value=65, death_cross=True)
        f[22]["value"] = 20
        f[23]["value"] = 31
        f[26]["death_cross"] = True
        result = run(rows, f)
        self.assertEqual(len(result["trades"]), 2)
        self.assertFalse(result["trades"][0]["forced_end"])
        self.assertTrue(result["trades"][1]["forced_end"])

    def test_equality_at30_70_and_ma(self):
        rows, f = fixture()
        f[14]["value"] = 30
        f[16]["value"] = 70
        f[17].update(value=69, death_cross=True, above_ma=False, below_ma=False)
        t = run(rows, f)["trades"][0]
        self.assertEqual(t["exit_index"], 18)
        self.assertTrue(t["exit_top_branch"])

    def test_split_coupon_fees_use_frozen_ledger(self):
        rows, f = fixture()
        for i in range(16, len(rows)):
            rows[i].update(open="5", close="5", share_factor="2", cumulative_cash="0.4")
        f[18].update(above_ma=False, below_ma=True, death_cross=True)
        result = run(rows, f, cost=10)
        expected = (1-.0005)/(1+.0005)+.04/(1+.0005)
        self.assertAlmostEqual(result["metrics"]["final_nav"], expected)
        self.assertEqual(result["metrics"]["natural_exits"], 1)

    def test_macd_recursion_and_no_future_information(self):
        rows, _ = fixture(100)
        for i, r in enumerate(rows):
            r["adjusted_close"] = str(10+(i%11-5)/10)
        actual = features(rows)
        self.assertEqual(actual[:70], features(rows[:70]))
        fast = slow = float(rows[0]["adjusted_close"])
        signal, olddif, olddea = 0.0, 0.0, 0.0
        for i, (r, f) in enumerate(zip(rows, actual)):
            c = float(r["adjusted_close"])
            fast += 2/13*(c-fast)
            slow += 2/27*(c-slow)
            dif = fast-slow
            signal += 2/10*(dif-signal)
            self.assertAlmostEqual(float(f["dif"]), dif, places=12)
            self.assertAlmostEqual(float(f["dea"]), signal, places=12)
            if i:
                self.assertEqual(f["death_cross"], olddif >= olddea and dif < signal)
            olddif, olddea = dif, signal
        full = run(rows, actual, liquidate=False)
        short = run(rows[:70], actual[:70], liquidate=False)
        self.assertEqual(full["nav"][:len(short["nav"])], short["nav"])


if __name__ == "__main__":
    unittest.main()
