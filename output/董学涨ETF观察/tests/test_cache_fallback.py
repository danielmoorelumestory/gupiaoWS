"""失败保留最近有效缓存、不冒充最新。"""
import json
import os

from dxz import shares as S


class Resp:
    def __init__(self, obj, status=200):
        self.obj, self.status_code = obj, status

    def json(self):
        return self.obj


class Sess:
    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def request(self, method, url, **kw):
        self.calls.append(kw.get("params", {}).get("STAT_DATE"))
        return self.fn(kw.get("params", {}))


def write(cache, d, shares):
    os.makedirs(os.path.join(cache, "sse"), exist_ok=True)
    with open(os.path.join(cache, "sse", f"{d}.json"), "w") as f:
        json.dump({"date": d, "shares": shares}, f)


def test_failed_fetch_keeps_old_cache_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    cache = str(tmp_path)
    write(cache, "2026-11-19", {"510300": 1.0})                     # 不完整缓存（缺 510050）
    sess = Sess(lambda p: Resp({}, status=503))
    log = []
    out, _ = S.fetch_sse(sess, ["2026-11-19", "2026-11-20"], ["510300", "510050"], cache, log, pause=0)
    assert out == {"2026-11-19": {"510300": 1.0}}                     # 旧值沿用；11-20 无数据就是无数据
    assert any("沿用旧缓存" in x for x in log) and any("2026-11-20 获取失败" in x for x in log)


def test_complete_cache_not_refetched_and_wrong_date_rejected(tmp_path):
    cache = str(tmp_path)
    write(cache, "2026-11-19", {"510300": 1.0, "510050": 2.0})

    def fn(p):  # 服务端错把 11-19 数据当 11-20 返回
        return Resp({"result": [{"SEC_CODE": "510300", "STAT_DATE": "2026-11-19", "TOT_VOL": "9"}]})
    sess = Sess(fn)
    log = []
    out, _ = S.fetch_sse(sess, ["2026-11-19", "2026-11-20"], ["510300", "510050"], cache, log, pause=0)
    assert sess.calls == ["2026-11-20"]
    assert "2026-11-20" not in out
    assert not os.path.exists(os.path.join(cache, "sse", "2026-11-20.json"))
