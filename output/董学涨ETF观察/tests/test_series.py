"""非连续交易日、净申赎近似、折算、放量比、历史位置。"""
from dxz.series import build_rows, detect_split, summarize

CAL = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]


def test_d1_not_across_gap_and_net_sub_uses_same_day_nav():
    shares = {"2026-11-16": 100.0, "2026-11-17": 110.0, "2026-11-19": 130.0, "2026-11-20": 120.0}
    navs = {"2026-11-17": 2.0, "2026-11-19": 2.0, "2026-11-20": 3.0}
    rows = build_rows(CAL, shares, navs, {})
    by = {r["d"]: r for r in rows}
    assert by["2026-11-17"]["d1"] == 10 and by["2026-11-17"]["net_sub_est"] == 20
    assert by["2026-11-18"]["share"] is None              # 缺日保留为 None，不补 0 不插值
    assert by["2026-11-19"]["d1"] is None                  # 前一交易日缺 → 不跨缺口
    assert by["2026-11-20"]["d1"] == -10 and by["2026-11-20"]["net_sub_est"] == -30
    assert by["2026-11-20"]["scale_nav"] == 360
    assert by["2026-11-16"]["scale_nav"] is None           # 无同日净值则不算规模
    assert by["2026-11-20"]["chg1"] == -10
    assert by["2026-11-20"]["chg5"] is None


def test_split_detected_and_excluded():
    assert detect_split(100, 200, 2.0, 1.0, None)
    assert not detect_split(100, 200, 2.0, 2.0, None)     # 真实大额申购（净值不变）不是折算
    assert detect_split(100, 101, 2.0, 2.0, "每份基金份额折算0.49977589份")
    assert not detect_split(100, 101, 2.0, 1.93, "每10份派现金0.5500元")   # 现金分红不是折算
    rows = build_rows(CAL[:2], {CAL[0]: 100.0, CAL[1]: 200.0}, {CAL[0]: 2.0, CAL[1]: 1.0}, {})
    assert rows[1]["split"] and rows[1]["d1"] is None and rows[1]["net_sub_est"] is None and rows[1]["chg1"] is None


def test_amount_ratio20_requires_full_window():
    cal = [f"2026-01-{i:02d}" for i in range(1, 23)]
    bars = {d: {"close": 1.0, "amount": 10.0} for d in cal}
    bars[cal[21]]["amount"] = 30.0
    shares = {d: 1.0 for d in cal}
    rows = build_rows(cal, shares, {}, bars)
    assert rows[21]["amount_ratio20"] == 3.0
    assert rows[19]["amount_ratio20"] is None
    del bars[cal[5]]
    rows = build_rows(cal, shares, {}, bars)
    assert rows[21]["amount_ratio20"] is None


def test_summary_rank_and_missing():
    shares = {"2026-11-16": 100.0, "2026-11-17": 300.0, "2026-11-19": 200.0, "2026-11-20": 250.0}
    s = summarize(build_rows(CAL, shares, {}, {}))
    assert s["first"] == "2026-11-16" and s["last"] == "2026-11-20" and s["count"] == 4
    assert s["missing_days"] == ["2026-11-18"]
    assert s["max"] == {"d": "2026-11-17", "share": 300.0}
    assert s["pct_rank"] == 0.75
