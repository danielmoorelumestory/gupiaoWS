from datetime import date, timedelta
import unittest

from rules import cap_allowed, features, simulate, verify_dependencies


def fixture(n=35, recovery=31):
    rows = [{"date": (date(2020, 1, 1)+timedelta(days=i)).isoformat(),
             "open": "10", "close": "10", "adjusted_close": "10",
             "share_factor": "1", "cumulative_cash": "0", "volume": "100"}
            for i in range(n)]
    feat = [{"value": 50, "above_ma": True, "below_ma": False,
             "dif": "0", "dea": "0", "death_cross": False, "bearish": False} for _ in rows]
    feat[13]["value"], feat[14]["value"] = 20, recovery
    return rows, feat


def run(rows, feat, strategy="MACD_CAP45", cost=10, liquidate=True):
    return simulate(rows, feat, strategy, rows[0]["date"], rows[-1]["date"], cost, liquidate)


class CapTest(unittest.TestCase):
    def test_frozen_dependencies(self):
        verify_dependencies()

    def test_45_included_and_above45_rejected(self):
        self.assertTrue(cap_allowed(45))
        self.assertFalse(cap_allowed(45.000001))
        self.assertFalse(cap_allowed(None))
        rows, f = fixture(recovery=45)
        self.assertEqual(run(rows, f)["trades"][0]["entry_index"], 15)
        f[14]["value"] = 45.000001
        self.assertEqual(run(rows, f)["trades"], [])
        self.assertEqual(len(run(rows, f, "MACD_STATE")["trades"]), 1)

    def test_no_late_buy_after_skipped_signal(self):
        rows, f = fixture(recovery=55)
        f[15]["value"], f[16]["value"] = 44, 40
        self.assertEqual(run(rows, f)["trades"], [])
        f[20]["value"], f[21]["value"] = 29, 40
        self.assertEqual(run(rows, f)["trades"][0]["entry_index"], 22)

    def test_ma_condition_and_fresh_cross_still_required(self):
        rows, f = fixture(recovery=35)
        f[14].update(above_ma=False, below_ma=True)
        self.assertEqual(run(rows, f)["trades"], [])
        f[13]["value"], f[14]["value"] = 32, 35
        f[14].update(above_ma=True, below_ma=False)
        self.assertEqual(run(rows, f)["trades"], [])

    def test_cap_does_not_force_sell_or_block_existing_sell(self):
        rows, f = fixture(recovery=40)
        f[16]["value"] = 80
        f[18].update(value=65, death_cross=True)
        result = run(rows, f)
        t = result["trades"][0]
        self.assertEqual(t["exit_index"], 19)
        self.assertTrue(t["exit_top_branch"])
        self.assertFalse(t["exit_price_below_ma"])

    def test_entry_under45_does_not_add_macd_filter(self):
        rows, f = fixture(recovery=40)
        f[14].update(bearish=True, dif="-1", dea="0")
        self.assertEqual(run(rows, f)["trades"][0]["entry_index"], 15)

    def test_identical_ledger_when_all_entry_signals_pass(self):
        rows, f = fixture(recovery=40)
        f[18].update(death_cross=True, below_ma=True, above_ma=False)
        f[23]["value"], f[24]["value"] = 20, 45
        f[27].update(death_cross=True, below_ma=True, above_ma=False)
        for cost in (0, 10, 30):
            a, b = run(rows, f, cost=cost), run(rows, f, "MACD_STATE", cost=cost)
            self.assertEqual(a["nav"], b["nav"])
            self.assertEqual(a["trades"], b["trades"])
            self.assertEqual(a["metrics"], b["metrics"])

    def test_prefix_causality(self):
        rows, _ = fixture(100)
        for i, r in enumerate(rows):
            r["adjusted_close"] = str(10+(i%11-5)/10)
        f = features(rows)
        full = run(rows, f, liquidate=False)
        short = run(rows[:70], f[:70], liquidate=False)
        self.assertEqual(full["nav"][:len(short["nav"])], short["nav"])


if __name__ == "__main__":
    unittest.main()
