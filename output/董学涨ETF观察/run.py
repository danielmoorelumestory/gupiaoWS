"""董学涨ETF观察 —— 一键入口。

    .venv/bin/python run.py update            # 采集全部（份额/净值/行情/定期报告）并生成 web/data/*.json
    .venv/bin/python run.py update --no-reports
    .venv/bin/python run.py reports           # 只更新定期报告（holdings.json）
    .venv/bin/python run.py composite         # 只更新视频19只ETF观察池（update 已含此步）
    .venv/bin/python run.py serve --port 8793 # 独立静态预览 http://127.0.0.1:8793/（开发用）

退出码（供观测台服务监督，不能把失败显示成成功）：
    0  完整成功：各阶段 ok、无报告问题、份额均到应有日期
    2  异常中止：旧产物未被覆盖
    3  另一个 update/reports 正在运行（文件锁占用），本次未执行
    4  已完成但有阶段失败/报告问题（沿用了缓存，见 status.json）
    5  已完成且各阶段 ok，但数据未到应有日期或无法确认（上游未发布/日历失败）
每次执行（除 3、serve）都写 data/last_run.json 记录结果。
"""
import argparse
import fcntl
import functools
import http.server
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
LOCK = os.path.join(ROOT, "data", ".run.lock")
LAST = os.path.join(ROOT, "data", "last_run.json")


def acquire_lock():
    """进程级互斥：update 与 reports 写同一批产物，不能并发。返回持有的文件对象或 None。"""
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    f = open(LOCK, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def classify_update(payload, stages):
    # carried = --no-reports 时沿用的上次报告状态，不算本次失败
    bad = [k for k, v in (stages or {}).items() if v and v.get("ok") is False and not v.get("carried")]
    fr = payload.get("freshness") or {}
    if bad:
        return 4, "阶段失败/不完整（沿用缓存）：" + "、".join(bad)
    members = fr.get("members") or {}
    lag = {k: [c for c, m in members.items() if m.get(k)] for k in ("nav_lag", "quote_lag")}
    failed = [c for c, m in members.items() if m.get("quotes_ok") is False or m.get("nav_ok") is False]
    # 19 池阶段（存在时）：stale 只有明确 False 才算到最新；True=落后，None=日历未知无法确认
    comp = (stages or {}).get("composite")
    comp_lag = bool(comp) and comp.get("stale") is not False
    if not fr.get("all_shares_fresh") or fr.get("rank_stale") or lag["nav_lag"] or lag["quote_lag"] or failed or comp_lag:
        parts = []
        if not fr.get("all_shares_fresh"):
            parts.append("；".join(fr.get("flags") or []) or "份额未全部到应有日期")
        if fr.get("rank_stale"):
            parts.append(f"排名日 {payload.get('rank_day') or '无'} 早于应有日期 {payload.get('expected_latest')}")
        if lag["nav_lag"]:
            parts.append("净值落后：" + "、".join(lag["nav_lag"]))
        if lag["quote_lag"]:
            parts.append("行情落后：" + "、".join(lag["quote_lag"]))
        if failed:
            parts.append("行情/净值抓取失败：" + "、".join(failed))
        if comp_lag:
            parts.append(f"19 池数据截至 {comp.get('data_last') or '无'}，" + (
                f"早于应有日期 {comp.get('expected_latest')}" if comp.get("stale") else "交易日历未知，无法确认是否到最新"))
        return 5, "未完成到应有日期（partial）：" + "；".join(parts)
    return 0, f"完成：份额、净值、行情与排名均到 {payload.get('rank_day')}"


def write_last(cmd, code, message, started, extra=None):
    from dxz.common import now_iso, write_json_atomic
    write_json_atomic(LAST, {"cmd": cmd, "code": code, "message": message, "started_at": started,
                             "finished_at": now_iso(), **(extra or {})})


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update")
    u.add_argument("--start", default="2024-01-02")
    u.add_argument("--no-reports", action="store_true")
    sub.add_parser("reports", help="只更新定期报告与汇金披露（holdings.json）")
    sub.add_parser("composite", help="只更新视频19只ETF观察池（composite.json）；update 已包含此步")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8793)
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.join(ROOT, "web"))
        with http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler) as srv:
            print(f"http://127.0.0.1:{a.port}/")
            srv.serve_forever()
        return 0
    lock = acquire_lock()
    if lock is None:
        print("另一个 update/reports 任务正在运行，本次跳过", file=sys.stderr)
        return 3
    from dxz.common import now_iso
    started = now_iso()
    if a.cmd == "composite":  # 不写 last_run.json（那是观测台 update/reports 任务的记录）
        try:
            from dxz.build import update_composite_only
            stage, log = update_composite_only()
        finally:
            lock.close()
        print(f"19 池：ok={stage.get('ok')} 数据截至 {stage.get('data_last')} 应有 {stage.get('expected_latest')} "
              f"stale={stage.get('stale')} issues={stage.get('issues') or stage.get('error')}")
        return 0 if stage.get("ok") and stage.get("stale") is False else (2 if stage.get("error") else 4)
    name = a.cmd + (" --no-reports" if a.cmd == "update" and a.no_reports else "")
    try:
        if a.cmd == "update":
            from dxz.build import update
            try:
                payload, log = update(start=a.start, with_reports=not a.no_reports)
            except Exception as e:  # noqa: BLE001
                msg = f"更新失败（旧产物未被覆盖）：{e}"
                print(msg, file=sys.stderr)
                write_last(name, 2, msg, started)
                return 2
            code, msg = classify_update(payload, payload.get("stages"))
            print(f"{msg}（rank_day={payload['rank_day']} expected_latest={payload['expected_latest']}，日志 {len(log)} 条）")
            write_last(name, code, msg, started, {"rank_day": payload["rank_day"],
                                                  "expected_latest": payload["expected_latest"]})
            return code
        from dxz.build import update_reports
        try:
            reps, log = update_reports()
        except Exception as e:  # noqa: BLE001
            msg = f"报告更新失败（旧产物未被覆盖）：{e}"
            print(msg, file=sys.stderr)
            write_last(name, 2, msg, started)
            return 2
        st = (json.load(open(os.path.join(ROOT, "web", "data", "status.json"))).get("stages") or {}).get("reports") or {}
        issues = st.get("issues") or {}
        if not reps:
            code, msg = 2, "未得到任何报告记录"
        elif issues:
            code, msg = 4, "报告有问题（已沿用有效缓存）：" + "；".join(f"{c}：{'，'.join(v)}" for c, v in issues.items())[:400]
        else:
            code, msg = 0, f"报告 {len(reps)} 份，无问题"
        print(msg)
        write_last(name, code, msg, started, {"count": len(reps)})
        return code
    finally:
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
