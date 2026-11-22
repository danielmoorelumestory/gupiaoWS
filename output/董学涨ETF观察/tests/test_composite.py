"""视频19只ETF观察池：公式、基期、缺失成员、拆分、种子真实数值、成员固定。"""
import json
import os

import pytest

from dxz import composite as cm
from dxz import pool19 as p19

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODES = ["A", "B", "C"]


def _sh(**kw):
    return {c: dict(v) for c, v in kw.items()}


def test_index_base_and_daily_change():
    cal = ["d1", "d2", "d3"]
    sh = _sh(A={"d1": 10, "d2": 12, "d3": 15}, B={"d1": 20, "d2": 20, "d3": 18}, C={"d1": 70, "d2": 70, "d3": 70})
    rows, meta = cm.compute(cal, sh, CODES, "d2")
    assert meta["base_ok"] and meta["base_sum"] == 102
    r = {x["d"]: x for x in rows}
    assert r["d2"]["idx"] == pytest.approx(100.0)
    assert r["d1"]["idx"] == pytest.approx(100 * 100 / 102)
    assert r["d3"]["idx"] == pytest.approx(100 * 103 / 102)
    assert r["d1"]["chg"] is None and r["d2"]["chg"] == 2 and r["d3"]["chg"] == 1
    assert meta["data_last"] == "d3"


def test_missing_member_is_null_not_zero_and_breaks_next_change():
    cal = ["d1", "d2", "d3", "d4"]
    sh = _sh(A={"d1": 10, "d2": 10, "d3": 11, "d4": 12}, B={"d1": 20, "d3": 20, "d4": 21}, C={"d1": 70, "d2": 70, "d3": 70, "d4": 70})
    rows, meta = cm.compute(cal, sh, CODES, "d1")
    r = {x["d"]: x for x in rows}
    assert r["d2"]["n"] == 2 and r["d2"]["sum"] is None and r["d2"]["idx"] is None and r["d2"]["chg"] is None
    assert r["d3"]["chg"] is None          # 前一日不完整 → 不跨缺口
    assert r["d4"]["chg"] == 2             # 两端都完整才算
    assert "d2" in meta["incomplete_days"]
    sh["B"].pop("d4")                     # 最新日缺成员：数据截至日回退到最后完整日
    _, meta = cm.compute(cal, sh, CODES, "d1")
    assert meta["data_last"] == "d3" and meta["members_last"]["B"] == "d3"


def test_zero_or_negative_share_treated_missing():
    rows, _ = cm.compute(["d1"], _sh(A={"d1": 0}, B={"d1": 1}, C={"d1": 1}), CODES, "d1")
    assert rows[0]["n"] == 2 and rows[0]["sum"] is None


def test_base_missing_or_incomplete_not_computable():
    sh = _sh(A={"d1": 1, "d2": 1}, B={"d2": 1}, C={"d1": 1, "d2": 1})
    rows, meta = cm.compute(["d1", "d2"], sh, CODES, "d1")
    assert not meta["base_ok"] and "不完整" in meta["base_error"]
    assert all(r["idx"] is None for r in rows)
    _, meta = cm.compute(["d1", "d2"], sh, CODES, "d9")
    assert not meta["base_ok"] and meta["base_error"] == "基期不在样本内"


def test_split_day_change_null_and_pre_split_marked():
    cal = ["d1", "d2", "d3"]
    sh = _sh(A={"d1": 100, "d2": 50, "d3": 51}, B={"d1": 1, "d2": 1, "d3": 1}, C={"d1": 1, "d2": 1, "d3": 1})
    splits = cm.split_days({"A": {"d2": "每份基金份额折算0.5份", "d3": "每10份派现金0.2元"}})
    assert splits == {"A": ["d2"]}        # 现金分红不算拆分
    rows, meta = cm.compute(cal, sh, CODES, "d3", splits)
    r = {x["d"]: x for x in rows}
    assert r["d2"]["chg"] is None and r["d2"]["split"] == ["A"]
    assert r["d3"]["chg"] == 1
    assert r["d1"]["pre_split"] and not r["d2"]["pre_split"]
    assert meta["split_dates"] == [{"code": "A", "date": "d2"}]


def test_pool_is_fixed_19_without_588000():
    assert p19.CODES19 == "510300,510310,510050,510330,159919,512100,588080,159915,510500,159845,560010,510180,159629,510230,512500,515800,159952,588050,159901".split(",")
    assert "588000" not in p19.CODES19 and p19.BASE_DATE == "2025-11-20"


SEED = os.path.join(ROOT, "data", "seed19", "composite_seed.json")


@pytest.mark.skipif(not os.path.exists(SEED), reason="无种子")
def test_seed_reproduces_research_values():
    seed = json.load(open(SEED))
    ev = {c: v["events"] for c, v in seed["nav"].items()}
    rows, meta = cm.compute(seed["calendar"], seed["shares"], p19.CODES19, p19.BASE_DATE, cm.split_days(ev))
    r = {x["d"]: x for x in rows}
    assert meta["base_sum"] / 1e8 == pytest.approx(4932.0890704, abs=1e-6)
    assert r["2025-11-20"]["idx"] == pytest.approx(100.0)
    assert r["2026-11-20"]["idx"] == pytest.approx(65.74277195965216, abs=1e-9)
    assert r["2024-09-20"]["chg"] is None and r["2024-09-20"]["split"] == ["510310"]
    # 2022-08-01 起 1044 个交易日；首个 19 只完整日 2022-08-04（560010 上交所份额首日），之后每日 19 只齐全
    assert seed["calendar"][0] == p19.HIST_START and len(rows) == 1044
    assert meta["first_complete"] == "2022-08-04" and meta["members_first"]["560010"] == "2022-08-04"
    assert all(x["n"] == 19 for x in rows if x["d"] >= "2022-08-04")
    assert [x["n"] for x in rows[:3]] == [17, 18, 18]
    # 2024 前份额折算（东方财富 FHSP），与交易所份额跳变同日；该日变化置空
    sp = {(x["code"], x["date"]) for x in meta["split_dates"]}
    assert {("159845", "2023-02-28"), ("560010", "2022-09-13"), ("159629", "2022-11-11"), ("159629", "2023-06-08"),
            ("510310", "2024-09-20")} <= sp
    assert all(r[d]["chg"] is None for d in ("2023-02-28", "2022-09-13", "2022-11-11", "2023-06-08"))
    assert r["2022-08-04"]["pre_split"] and not r["2024-09-23"]["pre_split"]


OUTF = os.path.join(ROOT, "web", "data", "composite.json")


@pytest.mark.skipif(not os.path.exists(OUTF), reason="未生成产物")
def test_product_payload_contract():
    d = json.load(open(OUTF))
    assert d["codes"] == p19.CODES19 and [m["code"] for m in d["members"]] == p19.CODES19
    assert all("待核验" not in json.dumps(m, ensure_ascii=False) for m in d["members"])
    r = {x["d"]: x for x in d["rows"]}
    assert r["2025-11-20"]["idx"] == pytest.approx(100.0)
    assert r["2026-11-20"]["idx"] == pytest.approx(65.7428, abs=1e-4)
    assert d["data_last"] >= "2026-11-20" and d["generated_at"][:10] >= d["data_last"]
    assert "30" not in [str(b.get("threshold")) for b in d["benchmarks"]]  # 无阈值字段


def test_validate_rejects_future_and_wrong_pool():
    rows = [{"d": "2099-01-01", "q": [None] * 19}]
    errs = cm.validate(rows, p19.CODES19, "2026-11-22")
    assert any("未来" in e for e in errs)
    assert cm.validate([], p19.CODES19[:-1] + ["588000"], "2026-11-22")


# ---------------------------------------------------------------- 长历史（2022-08 起）

def test_early_incomplete_days_and_first_complete():
    cal = ["d1", "d2", "d3", "d4"]
    sh = _sh(A={"d1": 1, "d2": 1, "d3": 1, "d4": 1}, B={"d3": 2, "d4": 2}, C={"d2": 3, "d3": 3, "d4": 3})
    rows, meta = cm.compute(cal, sh, CODES, "d4")
    assert meta["first_complete"] == "d3"
    assert meta["members_first"] == {"A": "d1", "B": "d3", "C": "d2"}
    assert meta["early_incomplete"] == [{"d": "d1", "missing": ["B", "C"]}, {"d": "d2", "missing": ["B"]}]
    assert all(r["sum"] is None and r["idx"] is None for r in rows[:2])   # 不补 0
    assert rows[2]["chg"] is None and rows[3]["chg"] == 0


def test_merge_calendar_does_not_truncate_to_main_2024():
    own = ["2022-08-01", "2022-08-02", "2023-12-29", "2024-01-02"]
    main = ["2024-01-02", "2024-01-03"]
    assert cm.merge_calendar(own, main, "2022-08-01") == ["2022-08-01", "2022-08-02", "2023-12-29", "2024-01-02", "2024-01-03"]
    assert cm.merge_calendar(own, main, "2022-08-02")[0] == "2022-08-02"


def test_calendar19_uses_own_early_cache_without_network(tmp_path, monkeypatch):
    p = tmp_path / "calendar.json"
    p.write_text(json.dumps({"dates": ["2022-08-01", "2023-12-29", "2024-01-02"]}))
    monkeypatch.setattr(cm, "CAL19", str(p))
    import dxz.quotes as q
    monkeypatch.setattr(q, "BaoStock", lambda: (_ for _ in ()).throw(AssertionError("不应联网")))
    cal, ok = cm.calendar19(["2024-01-02", "2024-01-03"], True, [], "2022-08-01")
    assert ok and cal == ["2022-08-01", "2023-12-29", "2024-01-02", "2024-01-03"]


def test_fetch_index_backfills_when_cache_starts_late(tmp_path):
    (tmp_path / "index").mkdir()
    (tmp_path / "index" / "X.json").write_text(json.dumps({"closes": {"2024-01-02": 10.0}}))
    seen = {}

    class B:
        class bs:
            @staticmethod
            def query_history_k_data_plus(key, fields, start_date, end_date, **kw):
                seen["lo"] = start_date
                return [{"date": "2022-08-01", "code": key, "close": "9.5"}]

        @staticmethod
        def _rows(x):
            return x
    have, st = cm.fetch_index(B, "X", "2022-08-01", "2024-01-05", str(tmp_path), [])
    assert st["ok"] and seen["lo"] == "2022-08-01" and have == {"2022-08-01": 9.5, "2024-01-02": 10.0}
    have, st = cm.fetch_index(B, "X", "2022-08-01", "2024-01-05", str(tmp_path), [])
    assert seen["lo"] == "2023-12-23"    # 已覆盖起点 → 增量


@pytest.mark.skipif(not os.path.exists(OUTF), reason="未生成产物")
def test_product_long_history():
    d = json.load(open(OUTF))
    rows = d["rows"]
    assert rows[0]["d"] == p19.HIST_START or rows[0]["d"] < "2022-08-05"
    fc = d["first_complete"]
    assert fc and fc < "2022-09-01"
    after = [r for r in rows if r["d"] >= fc]
    assert all(r["n"] == 19 and r["sum"] is not None for r in after)
    assert all(r["n"] < 19 and r["sum"] is None for r in rows if r["d"] < fc)
    r = {x["d"]: x for x in rows}
    assert r["2025-11-20"]["idx"] == pytest.approx(100.0)
    assert r["2026-11-20"]["idx"] == pytest.approx(65.74277195965216, abs=1e-9)
    assert r["2024-09-20"]["chg"] is None
    for k in ("hs300", "sh", "etf510300"):
        assert all(x[k] is None or x[k] > 0 for x in rows)
        assert sum(x[k] is not None for x in after) >= len(after) - 2
