import json
import store
import fetch
import pipeline


def test_run_daily_updates_agg_and_json(tmp_path, monkeypatch):
    conn = store.init_db(str(tmp_path / "t.db"))
    store.save_shares(conn, "2026-11-11", {"510300": 100.0})  # 前一交易日
    monkeypatch.setattr(fetch, "fetch_shares", lambda d: {"510300": 110.0})
    monkeypatch.setattr(fetch, "fetch_navs", lambda codes, d: {"510300": 2.0})
    monkeypatch.setattr(fetch, "fetch_sse_index", lambda s, e: [{"date": "2026-11-12", "close": 3600.0}])

    jp = tmp_path / "data.json"
    pipeline.run_daily(conn, "2026-11-12", data_path=str(jp))

    series = store.read_agg_series(conn)
    row = [r for r in series if r["date"] == "2026-11-12"]
    assert row and row[0]["flow_all"] == 20.0      # (110-100)*2
    loaded = json.load(open(jp, encoding="utf-8"))
    assert loaded["series"] and loaded["series"][-1]["date"] == "2026-11-12"
    assert loaded["series"][-1]["index"] == 3600.0
