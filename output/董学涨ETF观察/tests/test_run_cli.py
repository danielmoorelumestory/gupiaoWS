"""run.py：互斥锁与有意义的退出码（观测台服务据此显示成功/部分/失败）。"""
import fcntl
import json

import run


def test_lock_busy_returns_3(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "LOCK", str(tmp_path / ".run.lock"))
    held = open(run.LOCK, "a+")
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert run.main(["reports"]) == 3
        assert run.main(["update", "--no-reports"]) == 3
    finally:
        held.close()
    assert run.acquire_lock() is not None


def test_classify_update():
    ok = {"rank_day": "2026-11-20", "freshness": {"all_shares_fresh": True, "flags": []}}
    assert run.classify_update(ok, {"quotes": {"ok": True}})[0] == 0
    assert run.classify_update(ok, {"quotes": {"ok": False}})[0] == 4
    # --no-reports 沿用的上次报告状态不算本次失败
    assert run.classify_update(ok, {"reports": {"ok": False, "carried": True}})[0] == 0
    stale = {"freshness": {"all_shares_fresh": False, "flags": ["份额陈旧：159915(至2026-11-19)"]}}
    code, msg = run.classify_update(stale, {"quotes": {"ok": True}})
    assert code == 5 and "159915" in msg


def test_reports_exit_code_reflects_issues(tmp_path, monkeypatch):
    import dxz.build as B
    monkeypatch.setattr(run, "LOCK", str(tmp_path / ".run.lock"))
    monkeypatch.setattr(run, "LAST", str(tmp_path / "last_run.json"))
    monkeypatch.setattr(run, "ROOT", str(tmp_path))
    (tmp_path / "web" / "data").mkdir(parents=True)
    st = tmp_path / "web" / "data" / "status.json"
    monkeypatch.setattr(B, "update_reports", lambda: ([{"status": "named_top10"}], []))
    st.write_text(json.dumps({"stages": {"reports": {"ok": False, "issues": {"560010": ["2026-06-30 本次 unverified"]}}}}))
    assert run.main(["reports"]) == 4
    assert json.loads((tmp_path / "last_run.json").read_text())["code"] == 4
    st.write_text(json.dumps({"stages": {"reports": {"ok": True, "issues": {}}}}))
    assert run.main(["reports"]) == 0
    monkeypatch.setattr(B, "update_reports", lambda: ([], []))
    assert run.main(["reports"]) == 2


def test_classify_update_fresh_shares_but_lagging_quotes_or_nav_not_success():
    base = {"rank_day": "2026-11-20", "expected_latest": "2026-11-23"}
    m_ok = {"nav_lag": False, "quote_lag": False, "quotes_ok": True, "nav_ok": True}
    cases = [
        ({"all_shares_fresh": True, "rank_stale": True, "members": {"510300": m_ok}}, "排名日"),
        ({"all_shares_fresh": True, "members": {"510300": dict(m_ok, nav_lag=True)}}, "净值落后：510300"),
        ({"all_shares_fresh": True, "members": {"510300": dict(m_ok, quote_lag=True)}}, "行情落后：510300"),
        ({"all_shares_fresh": True, "members": {"510300": dict(m_ok, quotes_ok=False)}}, "抓取失败：510300"),
    ]
    for fr, frag in cases:
        code, msg = run.classify_update(dict(base, freshness=fr), {"quotes": {"ok": True}})
        assert code == 5 and frag in msg and "partial" in msg, (fr, msg)
    code, msg = run.classify_update(dict(base, freshness={"all_shares_fresh": True, "members": {"510300": m_ok}}),
                                    {"quotes": {"ok": True}})
    assert code == 0 and "均到" in msg


def test_classify_update_composite_stage():
    fresh = {"rank_day": "2026-11-20", "expected_latest": "2026-11-20",
             "freshness": {"all_shares_fresh": True, "members": {}}}
    ok = {"quotes": {"ok": True}}
    # 无 composite 阶段：兼容旧调用
    assert run.classify_update(fresh, ok)[0] == 0
    assert run.classify_update(fresh, dict(ok, composite={"ok": True, "stale": False}))[0] == 0
    code, msg = run.classify_update(fresh, dict(ok, composite={"ok": True, "stale": True, "data_last": "2026-11-19",
                                                               "expected_latest": "2026-11-20"}))
    assert code == 5 and "19 池" in msg and "2026-11-19" in msg
    code, msg = run.classify_update(fresh, dict(ok, composite={"ok": True, "stale": None, "data_last": "2026-11-20"}))
    assert code == 5 and "日历未知" in msg
    assert run.classify_update(fresh, dict(ok, composite={"ok": True}))[0] == 5   # 缺 stale 字段视为无法确认
    # 阶段失败仍优先 exit4
    assert run.classify_update(fresh, dict(ok, composite={"ok": False, "stale": True}))[0] == 4
    assert run.classify_update(fresh, {"quotes": {"ok": False}, "composite": {"ok": True, "stale": True}})[0] == 4
