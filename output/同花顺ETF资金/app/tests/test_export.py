import json
import pytest
import store
from export import build_data_json, write_data_json


def _db(tmp_path):
    return store.init_db(str(tmp_path / "t.db"))


def test_build_series_in_yi(tmp_path):
    conn = _db(tmp_path)
    store.save_agg(conn, "2026-11-12", -2.4801e10, -1.0e10)  # 元
    store.save_index(conn, "2026-11-12", 3634.35)
    d = build_data_json(conn)
    row = d["series"][0]
    assert row["flow_all"] == pytest.approx(-248.01)   # 元→亿元
    assert row["flow_broad"] == pytest.approx(-100.0)
    assert row["index"] == pytest.approx(3634.35)


def test_build_kpi_yesterday_and_cum60(tmp_path):
    conn = _db(tmp_path)
    store.save_agg(conn, "2026-11-10", 1.0e8, 0.5e8)
    store.save_agg(conn, "2026-11-11", 2.0e8, 1.0e8)
    store.save_agg(conn, "2026-11-12", 3.0e8, 1.5e8)
    d = build_data_json(conn)
    assert d["kpi"]["all"]["yesterday"] == pytest.approx(3.0)       # 末日
    assert d["kpi"]["all"]["cum60"] == pytest.approx(6.0)           # 近60日和
    assert d["kpi"]["broad"]["cum60"] == pytest.approx(3.0)


def test_data_json_has_disclaimer(tmp_path):
    conn = _db(tmp_path)
    assert "非同花顺原口径" in build_data_json(conn)["note"]


def test_write_data_json_file(tmp_path):
    conn = _db(tmp_path)
    store.save_agg(conn, "2026-11-12", 1.0e8, 0.5e8)
    p = tmp_path / "data.json"
    write_data_json(conn, str(p))
    loaded = json.load(open(p, encoding="utf-8"))
    assert loaded["series"] and "updated" in loaded
