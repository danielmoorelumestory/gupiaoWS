#!/usr/bin/env python3
"""全历史复测：每只ETF从上市第120根（index=120）起至2026-11-10，6方案，20bp。复用本目录retest61.py的独立实现。"""
import csv, json, statistics as st, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import retest61 as R

WINS = {"full": ("0000-01-01", "2026-11-10"), "pre_test": ("0000-01-01", "2024-06-30"),
        "test": ("2024-07-01", "2026-11-10")}
etfs = R.INPUTS["primary_etfs"]
assert all(v["ok"] for v in R.check_inputs().values())
res = R.run_all(etfs, WINS, [20])
rows = []
for (w, cost, c, code), r in res.items():
    m = dict(r["metrics"]); m["window"] = w
    m["good"] = any(e["code"] == code and "MACD优秀" in e["groups"] for e in etfs)
    rows.append(m)
F = ["window", "config", "code", "name", "good", "first", "last", "sessions", "calendar_days", "years",
     "final_nav", "total_return", "cagr", "mdd", "entries", "natural", "forced", "wins", "wr",
     "pooled_wr", "time_exposure", "dividend_reserve", "fees"]
R.write_csv(HERE / "full_history_long.csv", rows, F)
print(json.dumps({"groups": len(rows), "by_window": {w: sum(1 for x in rows if x["window"] == w) for w in WINS}}))
