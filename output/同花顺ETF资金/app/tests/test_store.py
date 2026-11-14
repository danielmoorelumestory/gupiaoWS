import store


def _db(tmp_path):
    return store.init_db(str(tmp_path / "t.db"))


def test_save_read_shares_roundtrip(tmp_path):
    conn = _db(tmp_path)
    store.save_shares(conn, "2026-11-12", {"510300": 100.0, "159919": 50.0})
    assert store.read_shares(conn, "2026-11-12") == {"510300": 100.0, "159919": 50.0}


def test_save_shares_idempotent(tmp_path):
    conn = _db(tmp_path)
    store.save_shares(conn, "2026-11-12", {"510300": 100.0})
    store.save_shares(conn, "2026-11-12", {"510300": 120.0})  # 同日重存 → 覆盖，不翻倍
    assert store.read_shares(conn, "2026-11-12") == {"510300": 120.0}


def test_latest_date_before(tmp_path):
    conn = _db(tmp_path)
    for d in ("2026-11-10", "2026-11-11", "2026-11-12"):
        store.save_shares(conn, d, {"510300": 1.0})
    assert store.latest_date_before(conn, "2026-11-12") == "2026-11-11"
    assert store.latest_date_before(conn, "2026-11-10") is None


def test_read_agg_series_sorted(tmp_path):
    conn = _db(tmp_path)
    store.save_agg(conn, "2026-11-12", 3.0, 1.0)
    store.save_agg(conn, "2026-11-10", 1.0, 0.5)
    store.save_agg(conn, "2026-11-11", 2.0, 0.8)
    series = store.read_agg_series(conn)
    assert [r["date"] for r in series] == ["2026-11-10", "2026-11-11", "2026-11-12"]
    assert series[0] == {"date": "2026-11-10", "flow_all": 1.0, "flow_broad": 0.5}


def test_save_agg_idempotent(tmp_path):
    conn = _db(tmp_path)
    store.save_agg(conn, "2026-11-12", 3.0, 1.0)
    store.save_agg(conn, "2026-11-12", 9.0, 4.0)  # 覆盖
    series = store.read_agg_series(conn)
    assert len(series) == 1 and series[0]["flow_all"] == 9.0


def test_read_index_map(tmp_path):
    conn = _db(tmp_path)
    store.save_index(conn, "2026-11-12", 3634.35)
    assert store.read_index_map(conn) == {"2026-11-12": 3634.35}
