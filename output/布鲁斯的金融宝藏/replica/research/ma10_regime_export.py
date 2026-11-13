"""把 ma10_regime.py 的过滤状态导出给可视化页面用。不改任何阈值，直接复用该脚本里的定义。
每个指数：日期、开盘、收盘、标志位（bit0–4 = F1–F5 通过，bit5 = 收盘在 10 日线之上）。"""
import json, sys, io, contextlib, numpy as np, pandas as pd
src = open("research/ma10_regime.py", encoding="utf-8").read().split("# ---------------------------------------------------------------- 一、诊断")[0]
with contextlib.redirect_stdout(io.StringIO()): exec(src)
out = {"thresholds": {k: float(v) for k, v in TH.items()}, "indices": []}
order = ["sh000300", "sh000001", "sh000016", "sh000905", "sh000852", "sz399006", "sh000688"]
for c in order:
    d, f = D[c], F[c]
    start = START.get(c, "2006-01-04")
    lo = d.index.get_indexer([d.loc[start:].index[0]])[0] - 15          # 多留 15 天给均线和信号
    keys = list(FILTERS)[1:]
    bits = sum(FILTERS[k](f).fillna(False).astype(int) * (1 << j) for j, k in enumerate(keys)) + f.above.astype(int) * 32
    x = d.iloc[lo:]; b = bits.iloc[lo:]
    out["indices"].append({"code": c, "name": NAMES[c], "start": start, "testStart": "2020-07-23" if c == "sh000688" else "2016-01-01",
        "date": [t.strftime("%Y%m%d") for t in x.index], "open": [round(v, 2) for v in x.open], "close": [round(v, 2) for v in x.close], "flag": [int(v) for v in b]})
    # 校验值：检验期从现金开始的年化，供页面算法对照
    for k in ("不过滤", "F3 来回次数少"):
        nav, tr = backtest(d, state(f, FILTERS[k](f)), out["indices"][-1]["testStart"])
        out["indices"][-1].setdefault("check", {})[k] = round(ann(nav) * 100, 4)
print(json.dumps({i["name"]: i["check"] for i in out["indices"]}, ensure_ascii=False))
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
