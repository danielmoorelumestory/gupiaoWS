"""数据语义：错日、单位、缺数、冲突。"""
import pytest

from dxz.common import SourceError
from dxz.nav import parse_nav_page
from dxz.shares import parse_sse, parse_szse_rows, quarter_ranges, unit_factor


def test_sse_wan_to_fen_and_rejects_wrong_date():
    raw = {"result": [
        {"SEC_CODE": "510300", "STAT_DATE": "2026-11-20", "TOT_VOL": "5518488.77", "SEC_NAME": "沪深300ETF"},
        {"SEC_CODE": "510050", "STAT_DATE": "2026-11-19", "TOT_VOL": "1666056.68"},  # 错日
        {"SEC_CODE": "999999", "STAT_DATE": "2026-11-20", "TOT_VOL": "1"},           # 池外
    ]}
    out, names, errs = parse_sse(raw, "2026-11-20", ["510300", "510050"])
    assert out == {"510300": 55184887700.0}          # 与视频画面 55,184,887,700 一致
    assert "510050" not in out                        # 错日不采用，也不补 0
    assert any("日期与请求日不符" in e for e in errs)


def test_sse_conflict_and_invalid():
    raw = {"result": [
        {"SEC_CODE": "510300", "STAT_DATE": "2026-11-20", "TOT_VOL": "1.00"},
        {"SEC_CODE": "510300", "STAT_DATE": "2026-11-20", "TOT_VOL": "2.00"},
        {"SEC_CODE": "510050", "STAT_DATE": "2026-11-20", "TOT_VOL": "-"},
    ]}
    out, _, errs = parse_sse(raw, "2026-11-20", ["510300", "510050"])
    assert out == {}
    assert len(errs) == 2


def test_szse_units():
    assert unit_factor("基金规模(份)") == 1
    assert unit_factor("基金规模<br>(万份)") == 10000
    with pytest.raises(SourceError):
        unit_factor("基金规模(亿份)")
    rows = [("日期", "基金代码", "基金简称", "基金规模(份)"),
            ("2026-11-20", "159915", "创业板ETF", "53174454936.00"),
            ("2026-09-30", "159915", "创业板ETF", "1.00"),        # 区间外
            ("2026-11-19", "159915  ", "创业板ETF", "49,907,454,936.00")]
    out, names, errs = parse_szse_rows(rows, ["159915"], "2026-10-01", "2026-12-31")
    assert out == {"2026-11-20": {"159915": 53174454936.0}, "2026-11-19": {"159915": 49907454936.0}}
    assert names["159915"] == "创业板ETF"
    assert any("不在请求区间" in e for e in errs)


def test_quarter_ranges_cover_without_gap():
    q = quarter_ranges("2024-01-02", "2026-11-22")
    assert q[0][1] == "2024-01-02" and q[-1][2] == "2026-11-22"
    assert len(q) == 12
    for a, b in zip(q, q[1:]):
        from datetime import date, timedelta
        assert date.fromisoformat(a[2]) + timedelta(days=1) == date.fromisoformat(b[1])


def test_nav_exact_dates_only():
    raw = {"ErrCode": 0, "TotalCount": 3, "Data": {"LSJZList": [
        {"FSRQ": "2026-11-20", "DWJZ": "4.0286", "FHSP": "", "FHFCZ": ""},
        {"FSRQ": "2026-11-19", "DWJZ": "", "FHSP": "", "FHFCZ": ""},
        {"FSRQ": "2026-10-01", "DWJZ": "4.0", "FHSP": "", "FHFCZ": ""},
        {"FSRQ": "2026-11-18", "DWJZ": "4.05", "FHSP": "每份派现金0.0700元", "FHFCZ": ""},
    ]}}
    navs, ev, n, total, errs = parse_nav_page(raw, "2026-11-01", "2026-11-20")
    assert navs == {"2026-11-20": 4.0286, "2026-11-18": 4.05}
    assert ev == {"2026-11-18": "每份派现金0.0700元"}
    assert n == 4 and total == 3
    assert any("区间外" in e for e in errs) and any("无效" in e for e in errs)
