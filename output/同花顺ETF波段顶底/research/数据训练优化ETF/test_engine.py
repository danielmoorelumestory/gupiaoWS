from datetime import date,timedelta
import unittest

from engine import prepare,simulate
from grid import controls,enumerate_grid,MACDS,PERIODS
from search import rank_scores
from prepare_data import normalize_cash_factors
from decimal import Decimal as D


def fixture(n=350):
    dates=[(date(2020,1,1)+timedelta(days=i)).isoformat() for i in range(n)]
    data={"dates":dates,"open":[10.]*n,"close":[10.]*n,"s":[1.]*n,"u":[0.]*n,
          "above":[True]*n,"below":[False]*n,"bands":{p:[50.]*n for p in PERIODS},
          "macds":{m:([False]*n,[False]*n) for m in MACDS}}
    return data


def config(entry="E1",exit_="X3"):
    return {"entry":entry,"exit":exit_,"n":13,"lo":30,"macd":[12,26,9],"hi":70,"cap":None,"wait":5}


def run(d,c=None,cost=20,liquidate=True):
    return simulate(d,c or config(),(d["dates"][0],d["dates"][-1]),cost,True,liquidate)


class EngineTest(unittest.TestCase):
    def test_provider_cash_after_split_is_capital_weighted(self):
        factors=[("1900-01-01",D(1),D(0)),("2021-01-01",D(2),D(0)),("2021-02-01",D(2),D("0.35"))]
        capital=normalize_cash_factors(factors)
        self.assertEqual(capital[-1][2],D("0.70"))
        d=fixture();d["bands"][13][130:132]=[20.,35.]
        for i in range(135,len(d["dates"])):
            d["s"][i]=2.;d["open"][i]=d["close"][i]=5.
        for i in range(140,len(d["dates"])):d["u"][i]=.70
        result=run(d,cost=0)
        self.assertAlmostEqual(result["metric"]["dividend_reserve"],.07)
        self.assertAlmostEqual(result["metric"]["final_nav"],1.07)

    def test_provider_cash_before_and_after_split(self):
        factors=[("a",D(1),D("0.1")),("b",D(2),D("0.1")),("c",D(2),D("0.2"))]
        self.assertEqual(normalize_cash_factors(factors)[-1][2],D("0.3"))

    def test_grid_is_canonical306(self):
        grid=enumerate_grid()
        self.assertEqual(len(grid),306)
        self.assertTrue(all(c["cap"] is None for c in grid.values() if c["entry"]!="E3"))
        self.assertTrue(all(c["hi"] is None for c in grid.values() if c["exit"]!="X3"))

    def test_close_signal_next_open_and_delayed_exit(self):
        d=fixture();d["bands"][13][130:132]=[20.,35.]
        d["below"][135:145]=[True]*10;d["macds"][(12,26,9)][1][140]=True
        d["open"][132]=11.;d["open"][141]=12.
        r=run(d);t=r["trades"][0]
        self.assertEqual((t["entry_signal_index"],t["entry_index"],t["exit_signal_index"],t["exit_index"]),(131,132,140,141))
        self.assertAlmostEqual(r["metric"]["final_nav"],12/11*.999/1.001)

    def test_top_branch_above_ma_and_high_reset(self):
        d=fixture();v=d["bands"][13];v[130:132]=[20.,35.];v[136]=75.;v[137]=65.
        d["macds"][(12,26,9)][1][140]=True
        v[150:152]=[20.,35.];d["macds"][(12,26,9)][1][160]=True
        r=run(d)
        self.assertEqual(r["trades"][0]["exit_index"],141)
        self.assertTrue(r["trades"][1]["forced_end"])

    def test_existing_bearish_not_death(self):
        d=fixture();d["bands"][13][130:132]=[20.,35.]
        d["below"][135:]=[True]*(len(d["dates"])-135)
        self.assertEqual(run(d)["metric"]["natural"],0)

    def test_e2_five_sessions_cancel_and_consume(self):
        d=fixture();v=d["bands"][13];v[130:132]=[20.,35.]
        d["above"][131:135]=[False]*4
        r=run(d,config("E2","X1"));self.assertEqual(r["trades"][0]["entry_index"],136)
        d["above"][135]=False
        self.assertEqual(run(d,config("E2","X1"))["metric"]["entries"],0)
        d["above"][135]=True;v[133]=29.
        d["above"][134]=False
        # New recovery on134 resets the five-session window.
        self.assertEqual(run(d,config("E2","X1"))["trades"][0]["entry_index"],136)

    def test_e3_cap_and_no_delayed_gold_entry(self):
        d=fixture();c=config("E3","X2");c.update(lo=None,hi=None,cap=60)
        d["macds"][(12,26,9)][0][131]=True;d["bands"][13][131]=61
        self.assertEqual(run(d,c)["metric"]["entries"],0)
        d["bands"][13][131]=60
        self.assertEqual(run(d,c)["trades"][0]["entry_index"],132)

    def test_split_dividend_and_segregated_reserve(self):
        d=fixture();v=d["bands"][13];v[130:132]=[20.,35.]
        for i in range(135,len(d["dates"])):
            d["s"][i]=2.;d["u"][i]=.4;d["open"][i]=d["close"][i]=5.
        d["below"][140]=True;d["macds"][(12,26,9)][1][140]=True
        v[150:152]=[20.,35.]
        r=run(d,cost=0)
        self.assertAlmostEqual(r["metric"]["final_nav"],1.04)
        self.assertAlmostEqual(r["trades"][1]["entry_cash"],1.)

    def test_new_holder_exdate_no_coupon(self):
        d=fixture()
        for i in range(121,len(d["dates"])):d["u"][i]=1.
        r=run(d,controls()["HOLD"],cost=0)
        self.assertEqual(r["metric"]["dividend_reserve"],0)

    def test_forced_exit_not_win_rate_and_annual_support(self):
        r=run(fixture(),controls()["HOLD"])
        self.assertEqual(r["metric"]["natural"],0)
        self.assertIsNone(r["metric"]["wr"])
        self.assertIsNone(r["metric"]["cagr"])

    def test_prefix_has_no_future_signal_or_nav_changes(self):
        d=fixture();d["bands"][13][130:132]=[20.,35.]
        a=run(d,liquidate=False)
        shorter={k:([x for x in v[:280]] if isinstance(v,list) else v) for k,v in d.items()}
        b=run(shorter,liquidate=False)
        self.assertEqual(a["nav"][:len(b["nav"])],b["nav"])

    def test_precomputed_indicators_causal(self):
        rows=[{"date":str(i),"adjusted_close":str(10+(i%11)/10),"open":"10","close":"10","share_factor":"1","cumulative_cash":"0"} for i in range(300)]
        a,b=prepare(rows,{}),prepare(rows[:200],{})
        self.assertEqual(a["above"][:200],b["above"])
        for p in PERIODS:self.assertEqual(a["bands"][p][:200],b["bands"][p])
        for m in MACDS:
            for j in (0,1):self.assertEqual(a["macds"][m][j][:200],b["macds"][m][j])

    def test_equal_rank_multiobjective(self):
        scores=rank_scores({"A":{"wr_eq":.8,"cagr_med":.01},"B":{"wr_eq":.4,"cagr_med":.2}})
        self.assertEqual(scores["A"],scores["B"])


if __name__=="__main__":unittest.main()
