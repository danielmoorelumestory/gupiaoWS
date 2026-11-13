import json, numpy as np, pandas as pd
src = open("research/macd_etf.py").read()
exec(src.split("picked = json.load")[0]); END = "2026-11-10"
exec("def events" + src.split("def events")[1].split("rows, logs = [], {}")[0])
for c, n, g in json.load(open("data/page_etfs.json")):
    d, dv, mult, adj, log = load(c)
    for x in log:
        if x.startswith("拆分"):
            ratio = float(x.split("1:")[1].split("（")[0]); real = float(x.split("今开 ")[1].rstrip("）"))
            flag = "" if abs(real / ratio - 1) < 0.1 else "  ← 不符"
            print(c, n, x, flag)
        elif x.startswith("剔除"): print(c, n, x)
