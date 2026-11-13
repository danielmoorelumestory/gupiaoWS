"""用他在视频里报过的数字检验公式；数字出处见各测试的注释。"""
import math

import numpy as np
import pandas as pd
import pytest

from bruce_replica import breadth, journal, midterm, pcr, rules, technical


def test_trin_matches_episode16_example():
    # 第16集 03:05–03:44：上涨 80.9%、下跌 17.6%，下跌股占成交额 27%，阿姆士 1.69
    assert breadth.trin(80.9, 17.6, 73, 27) == pytest.approx(1.69, abs=0.02)


def test_up_side_share_for_ice_point_case():
    # 第21集：5% 红盘、阿姆士 0.31 → 上涨的 5% 个股约占 14.5% 的成交
    assert breadth.up_side_share(0.05, 0.31) == pytest.approx(0.145, abs=0.002)


def _market(n_up, n_down, n_flat, amt_up_each, amt_down_each):
    rows = ([{"name": f"U{i}", "pct_chg": 1.0, "volume": 10, "amount": amt_up_each} for i in range(n_up)]
            + [{"name": f"D{i}", "pct_chg": -1.0, "volume": 30, "amount": amt_down_each} for i in range(n_down)]
            + [{"name": f"F{i}", "pct_chg": 0.0, "volume": 5, "amount": 1.0} for i in range(n_flat)])
    return pd.DataFrame(rows)


def test_breadth_reading_counts_and_both_trin_versions():
    r = breadth.breadth_reading(_market(80, 18, 2, amt_up_each=1.0, amt_down_each=2.0))
    assert (r.n_up, r.n_down, r.n_flat) == (80, 18, 2)
    assert r.up_ratio == pytest.approx(0.80)
    assert r.trin_amount == pytest.approx((80 / 18) / (80 / 36))   # 下跌股平均成交额是上涨股的 2 倍 → 2.0
    assert r.trin_volume == pytest.approx(3.0)                     # 下跌股平均成交量是 3 倍
    assert r.down_amount_share == pytest.approx(36 / 116)


def test_breadth_switches_change_the_pool():
    df = _market(80, 18, 2, 1.0, 2.0)
    df.loc[0, "name"] = "*ST某某"
    assert breadth.breadth_reading(df, exclude_st=True).n_up == 79
    assert breadth.breadth_reading(df, flat_as_down=True).n_down == 20


def test_suspended_stocks_are_ignored():
    df = _market(3, 2, 0, 1.0, 1.0)
    df.loc[0, "amount"] = 0
    assert breadth.breadth_reading(df).n_up == 2


def test_mcclellan_is_ema19_minus_ema39():
    s = pd.Series(np.r_[np.zeros(5), np.full(60, 100.0)])
    m = breadth.mcclellan(s)
    assert m["mcl"].iloc[4] == 0
    assert m["mcl"].iloc[10] > 0                    # 短均线先跟上
    assert abs(m["mcl"].iloc[-1]) < m["mcl"].max()  # 之后收敛
    manual = s.ewm(span=19, adjust=False).mean() - s.ewm(span=39, adjust=False).mean()
    assert np.allclose(m["mcl"], manual)


def test_share_above_ma():
    idx = pd.RangeIndex(30)
    close = pd.DataFrame({"a": np.arange(30.0) + 1, "b": 30.0 - np.arange(30.0)}, index=idx)
    p = breadth.share_above_ma(close, windows=(20,))
    assert math.isnan(p["P20"].iloc[10])
    assert p["P20"].iloc[-1] == pytest.approx(0.5)  # 一只在均线上方，一只在下方


def _ohlcv(close, volume=None):
    close = pd.Series(close, dtype=float)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close,
                         "volume": pd.Series(volume if volume is not None else np.ones(len(close)), dtype=float)})


def test_vwmacd_follows_on_screen_formula():
    df = _ohlcv(np.arange(1, 61), volume=np.arange(1, 61))
    v = technical.vwmacd(df)
    c, vol = df["close"], df["volume"]
    vc1 = (c * vol).iloc[-12:].sum() / vol.iloc[-12:].sum()
    vc2 = (c * vol).iloc[-26:].sum() / vol.iloc[-26:].sum()
    assert v["dif"].iloc[-1] == pytest.approx(vc1 - vc2)
    assert v["macd"].iloc[-1] == pytest.approx((v["dif"].iloc[-1] - v["dea"].iloc[-1]) * 2)


def test_ichimoku_uses_7_22_44():
    df = _ohlcv(np.arange(1, 101))
    ich = technical.ichimoku(df)
    assert ich["tenkan"].iloc[-1] == pytest.approx((df["high"].iloc[-7:].max() + df["low"].iloc[-7:].min()) / 2)
    assert ich["kijun"].iloc[-1] == pytest.approx((df["high"].iloc[-22:].max() + df["low"].iloc[-22:].min()) / 2)
    assert ich["cloud_pos"].iloc[-1] == "云上"       # 单边上涨，价格在云上


def test_cci_and_kdj_ranges_on_uptrend():
    df = _ohlcv(np.arange(1, 61))
    assert technical.cci(df).iloc[-1] > 100
    assert technical.kdj(df)["k"].iloc[-1] > 80
    assert technical.donchian(df)["position"].iloc[-1] == "中轨偏上"


def test_combine_follows_episode26_rule():
    # 第26集：资金面空、技术面多 → 准备空；技术面也转空 → 开空
    assert rules.combine("空", "多").startswith("准备空")
    assert rules.combine("空", "空").startswith("空")
    assert rules.combine("中", "多").startswith("观望")
    with pytest.raises(ValueError):
        rules.combine("看空", "多")


@pytest.mark.parametrize("case", rules.CASES, ids=lambda c: c.date)
def test_each_case_is_its_own_nearest_match(case):
    res = rules.read_short_term(case.up_ratio, case.trin)
    assert res["nearest"].date == case.date and res["similar"]


def test_reading_far_from_all_cases_is_flagged():
    assert rules.read_short_term(0.30, 3.0)["similar"] is False


def test_stage_note_and_tiers():
    assert "不看" in rules.read_short_term(0.5, 0.6, stage="初段")["note"]
    assert rules.trin_tier(0.46).startswith("低于0.5")
    assert rules.trin_tier(0.9).startswith("0.7至1")
    assert rules.trin_tier(1.69).startswith("高于1")


def test_midterm_helpers():
    assert midterm.mktcap_gdp_zone(1.05) == "高估区"
    assert midterm.mktcap_gdp_zone(0.85) == "高估线与低估线之间"
    assert midterm.mktcap_gdp_zone(0.45) == "极低估区"
    spread = midterm.equity_bond_spread(pd.Series([10.0, 20.0]), pd.Series([2.0, 2.0]))
    assert list(spread) == pytest.approx([8.0, 3.0])
    band = midterm.std_band(pd.Series(np.r_[np.zeros(50), [10.0]]), window=20)
    assert band["zone"].iloc[-1] == "触及上轨"
    df = pd.DataFrame({"turnover": [1, 6, 7, None]})
    assert midterm.high_turnover_share(df) == pytest.approx(2 / 3)


def test_journal_template_and_sample_row(tmp_path):
    # 第26集 03:20 样例：买入 put，沽3月2900，100手，单价395，止损320，最大亏损 -7500
    assert journal.max_loss(395, 320, 100) == -7500
    p = tmp_path / "j.csv"
    journal.append(p, {"日期": "2019-11-20", "基本面总结": "空", "技术面总结": "空", "结论": "空 最大25%",
                       "行动": "买入put", "仓单": "沽3月2900", "手数": 100, "单价": 395, "止损位": 320,
                       "最大亏损": -7500})
    got = pd.read_csv(p)
    assert list(got.columns) == journal.COLUMNS and got.loc[0, "最大亏损"] == -7500
    with pytest.raises(KeyError):
        journal.append(p, {"不存在的栏": 1})


def _stats(pcr50, pcr300):
    rows = []
    for i, (a, b) in enumerate(zip(pcr50, pcr300)):
        d = f"2026-01-{i + 1:02d}"
        rows += [{"date": d, "underlying": "510050", "put_oi": a * 100, "call_oi": 100, "put_vol": 1, "call_vol": 1},
                 {"date": d, "underlying": "510300", "put_oi": b * 300, "call_oi": 300, "put_vol": 1, "call_vol": 1}]
    return pd.DataFrame(rows)


def test_pcr_series_total_is_size_weighted():
    s = pcr.pcr_series(_stats([1.0], [0.6]))
    assert s.iloc[0] == pytest.approx((100 + 180) / 400)


def test_pcr_band_flags_upper_as_top_and_lower_as_bottom():
    base = [0.8, 0.82] * 10
    up = pcr.pcr_band(pd.Series(base + [1.2]), window=20)
    dn = pcr.pcr_band(pd.Series(base + [0.5]), window=20)
    assert up["signal"].iloc[-1] == pcr.TOP and dn["signal"].iloc[-1] == pcr.BOTTOM
    assert up["signal"].iloc[-2] == pcr.NONE and pd.isna(up["signal"].iloc[0])


def test_pcr_interpret_follows_his_50_vs_300_rule():
    # 金融宝藏第7集：300 破下轨而 50 未破 → 下跌未结束
    assert "没有结束" in pcr.interpret(pcr.NONE, pcr.BOTTOM)
    assert "底部信号" in pcr.interpret(pcr.BOTTOM, pcr.BOTTOM)
    assert "只是回调" in pcr.interpret(pcr.TOP, pcr.NONE, trend="上行")   # 4/17 误报
    assert "空仓" in pcr.interpret(pcr.NONE, pcr.NONE)


def test_shrinking_rally_matches_his_november_calls():
    assert rules.shrinking_rally(0.88, 2.0)        # 11/05
    assert not rules.shrinking_rally(0.55, 0.30)   # 7/21 底部放量
    assert not rules.shrinking_rally(0.60, 1.6)


def test_std_band_marks_both_extremes():
    s = pd.Series([1.0, 1.1] * 10 + [0.2])
    b = midterm.std_band(s, window=20)
    assert b["zone"].iloc[-1] == "跌破下轨"
    assert "顶部" in midterm.spread_reading("跌破下轨") and "底部" in midterm.spread_reading("触及上轨")


def test_band_episodes_merges_nearby_days():
    idx = pd.to_datetime(["2024-09-13", "2024-09-18", "2024-12-02", "2025-04-07"])
    band = pd.DataFrame({"zone": ["触及上轨", "触及上轨", "中轨与上轨之间", "触及上轨"]}, index=idx)
    eps = midterm.band_episodes(band, "触及上轨")
    assert [(a.strftime("%m-%d"), b.strftime("%m-%d")) for a, b in eps] == [("09-13", "09-18"), ("04-07", "04-07")]


def test_cffex_pcr_reproduces_his_screen_values():
    # 金融宝藏第7集（2026-09-30）画面：300 PCR 0.7491、50 PCR 0.7329。持仓量取自中金所当日统计。
    stats = pd.DataFrame([
        {"date": "2026-09-30", "underlying": "IO", "put_oi": 89582, "call_oi": 119586},
        {"date": "2026-09-30", "underlying": "HO", "put_oi": 36721, "call_oi": 50105},
    ])
    assert pcr.pcr_series(stats, pcr.IO).iloc[0] == pytest.approx(0.7491, abs=5e-5)
    assert pcr.pcr_series(stats, pcr.HO).iloc[0] == pytest.approx(0.7329, abs=5e-5)


def test_breadth_from_hist_and_merge(tmp_path):
    from bruce_replica import data
    h = tmp_path / "hist"
    h.mkdir()
    rows = {"600001": [("2026-01-05", 1.0, 10, 100.0, 1.0), ("2026-01-06", -1.0, 10, 100.0, 6.0)],
            "000002": [("2026-01-05", 2.0, 10, 100.0, 1.0), ("2026-01-06", 1.0, 10, 300.0, 1.0)],
            "300003": [("2026-01-05", -1.0, 30, 400.0, 1.0), ("2026-01-06", 0.0, 0, 0.0, 0.0)]}   # 01-06 停牌
    for code, r in rows.items():
        pd.DataFrame(r, columns=["date", "pct_chg", "volume", "amount", "turnover"]).to_csv(h / f"{code}.csv", index=False)
    b = data.breadth_from_hist(tmp_path).set_index("date")
    d5, d6 = b.loc["2026-01-05"], b.loc["2026-01-06"]
    assert (d5.n_up, d5.n_down, d5.n_flat) == (2, 1, 0)
    assert d5.trin_amount == pytest.approx((2 / 1) / (200 / 400))     # 4.0：两只上涨股成交额不及一只下跌股
    assert (d6.n_up, d6.n_down) == (1, 1) and d6.up_ratio == pytest.approx(0.5)   # 停牌股不计
    pd.DataFrame([{"date": "2026-01-06", "n_up": 9}]).to_csv(tmp_path / "breadth_daily.csv", index=False)
    m = data.merge_breadth_history(b.reset_index(), tmp_path).set_index("date")
    assert m.loc["2026-01-06", "n_up"] == 9 and m.loc["2026-01-05", "n_up"] == 2       # 已有日期不覆盖


def test_etf_amount_ma_matches_his_code():
    # 数据证伪第5集画面：TOTAL_AMO 为三只 ETF 成交额之和，AMO_MA 为其 20 日均线
    idx = pd.date_range("2026-09-01", periods=21, freq="B")
    amt = pd.DataFrame({"510300": 50.0, "510050": 30.0, "588000": 20.0}, index=idx)
    amt.iloc[-1] = [40.0, 30.0, 20.0]
    e = midterm.etf_amount_ma(amt)
    assert e["total"].iloc[-1] == pytest.approx(90.0)
    assert e["ma"].iloc[-1] == pytest.approx((19 * 100 + 90) / 20)
    assert pd.isna(e["ma"].iloc[18])


def test_percentile_band_position():
    s = pd.Series(range(1, 101), index=pd.date_range("2020-01-01", periods=100, freq="W"), dtype=float)
    b = midterm.percentile_band(s)
    assert b["value"] == 100 and b["pct"] == pytest.approx(1.0)
    assert b["low"] == pytest.approx(20.8) and b["high"] == pytest.approx(80.2)


def test_backtest_events_and_forward_returns():
    from bruce_replica import backtest
    idx = pd.date_range("2026-01-01", periods=12, freq="B")
    flag = pd.Series([0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0], index=idx).astype(bool)
    assert backtest.events(flag, gap=3) == [idx[1], idx[7]]          # 相邻两天并成一次
    price = pd.Series(range(100, 112), index=idx, dtype=float)
    fr = backtest.forward_returns(price, [idx[1], idx[7]], (2, 5))
    assert fr.loc[idx[1], 2] == pytest.approx(103 / 101 - 1)
    assert pd.isna(fr.loc[idx[7], 5])                                 # 到期日超出样本
    s = backtest.summarize(price, [idx[1]], (2,), expect=1)
    assert s.loc[2, "方向对的比例"] == 1.0 and s.loc[2, "基准同方向比例"] == 1.0


def test_state_strategy_acts_next_day():
    from bruce_replica import backtest
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    price = pd.Series([100, 110, 121, 60.5, 60.5], index=idx)
    enter = pd.Series([True, False, False, False, False], index=idx)
    exit_ = pd.Series([False, False, True, False, False], index=idx)
    r = backtest.state_strategy(price, enter, exit_)
    assert r["持仓时间占比"] == pytest.approx(2 / 5)                   # 信号当天收盘确认，次日收益起生效：持有第 2、3 天
    assert r["策略"]["最大回撤"] == 0.0 and r["买入持有"]["最大回撤"] == pytest.approx(-0.5)   # 躲开了第 4 天的下跌
    assert r["切换次数"] == 2
