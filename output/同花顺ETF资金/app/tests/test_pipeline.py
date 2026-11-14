import json
import store
import fetch
import pipeline


def test_run_daily_updates_agg_and_json(tmp_path, monkeypatch):
    conn = store.init_db(str(tmp_path / "t.db"))
    store.save_shares(conn, "2026-11-11", {"510300": 100.0})  # 前一交易日
    monkeypatch.setattr(fetch, "fetch_sse_shares", lambda d: {"510300": 110.0})
    monkeypatch.setattr(fetch, "fetch_szse_shares", lambda d: {})
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


def test_run_daily_skips_incomplete_day(tmp_path, monkeypatch):
    # 沪市份额为空（节假日/未披露）→ 不应落库该日，避免毒化次日前值基准
    conn = store.init_db(str(tmp_path / "t.db"))
    store.save_shares(conn, "2026-11-11", {"510300": 100.0})  # 真实前值
    monkeypatch.setattr(fetch, "fetch_sse_shares", lambda d: {})           # 沪空
    monkeypatch.setattr(fetch, "fetch_szse_shares", lambda d: {"159919": 55.0})  # 深仍给最新
    monkeypatch.setattr(fetch, "fetch_navs", lambda codes, d: {"159919": 2.0})
    monkeypatch.setattr(fetch, "fetch_sse_index", lambda s, e: [])

    pipeline.run_daily(conn, "2026-11-12", data_path=str(tmp_path / "d.json"))

    assert store.read_shares(conn, "2026-11-12") == {}          # 残缺日未落库
    assert store.latest_date_before(conn, "2026-11-13") == "2026-11-11"  # 基准仍是真实前值
    assert all(r["date"] != "2026-11-12" for r in store.read_agg_series(conn))
