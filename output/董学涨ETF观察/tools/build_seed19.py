"""一次性生成 19 池历史种子 data/seed19/composite_seed.json（开发工具，产品运行不调用、不依赖研究目录）。

来源：output/布鲁斯的金融宝藏/research/宽基ETF申赎算法核验20261122/claude/（只读）
- data/panel.csv：由 raw/sse（上交所 698 日原始响应）、raw/szse（12 个季度 XLSX）、raw/nav（东方财富 lsjz）解析
- raw/index/*.tsv.gz：BaoStock 指数日线；data/calendar.json：BaoStock 交易日历
- results/coverage.csv：交易所简称
种子里记录上述文件 sha256、原始响应抓取时间范围，便于追溯。
用法：.venv/bin/python tools/build_seed19.py
"""
import csv, gzip, hashlib, io, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dxz import pool19 as p19  # noqa: E402
from dxz.common import write_json_atomic  # noqa: E402

RES = os.path.normpath(os.path.join(ROOT, "..", "布鲁斯的金融宝藏", "research", "宽基ETF申赎算法核验20261122", "claude"))
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
panel = os.path.join(RES, "data", "panel.csv")
man = json.load(open(os.path.join(RES, "raw", "manifest.json")))
times = sorted(v["fetched_at"] for v in man.values())
cal = json.load(open(os.path.join(RES, "data", "calendar.json")))["dates"]
shares, navs, events = {c: {} for c in p19.CODES19}, {c: {} for c in p19.CODES19}, {c: {} for c in p19.CODES19}
for r in csv.DictReader(open(panel, encoding="utf-8")):
    c = r["code"]
    if c not in shares:
        continue
    if r["share"]:
        shares[c][r["date"]] = float(r["share"])
    if r["nav"]:
        navs[c][r["date"]] = float(r["nav"])
    if r["fhsp"]:
        events[c][r["date"]] = r["fhsp"]
names = {r["code"]: r["exchange_name"] for r in csv.DictReader(open(os.path.join(RES, "results", "coverage.csv"), encoding="utf-8-sig"))}
index = {}
for b in p19.BENCHMARKS:
    p = os.path.join(RES, "raw", "index", f"{b['key']}.tsv.gz")
    rows = list(csv.DictReader(io.StringIO(gzip.open(p).read().decode()), delimiter="\t"))
    index[b["key"]] = {r["date"]: float(r["close"]) for r in rows if r["close"] and r["date"] >= cal[0]}
index_research_keys = list(index)
assert sorted(shares) == sorted(p19.CODES19) and all(len(shares[c]) == len(cal) for c in p19.CODES19), "种子不完整"

# ---- 2024 以前段：tools/backfill19.py 抓取的官方原始响应（data/seed19/raw_pre2024）解析后写入的 data/cache19
C19 = os.path.join(ROOT, "data", "cache19")
RAW0 = os.path.join(ROOT, "data", "seed19", "raw_pre2024")
man0 = json.load(open(os.path.join(RAW0, "manifest.json")))
cal0 = [d for d in json.load(open(os.path.join(C19, "calendar.json")))["dates"] if p19.HIST_START <= d < cal[0]]
for d in cal0:
    c = json.load(open(os.path.join(C19, "sse", f"{d}.json")))
    assert c.get("raw") in man0, f"{d} 上交所缓存不是回补原始响应"
    for k, v in c["shares"].items():
        if k in shares:
            shares[k][d] = v
for f in sorted(os.listdir(os.path.join(C19, "szse"))):
    c = json.load(open(os.path.join(C19, "szse", f)))
    if not c.get("raw"):
        continue
    for d, m in c["shares"].items():
        if d in cal0:
            for k, v in m.items():
                if k in shares:
                    shares[k][d] = v
for code in p19.CODES19:  # 净值/事件：回补段（东方财富 lsjz）补在研究段之前
    c = json.load(open(os.path.join(C19, "nav", f"{code}.json")))
    for d, v in c["navs"].items():
        if d < cal[0]:
            navs[code][d] = v
    for d, t in c["events"].items():
        if d < cal[0]:
            events[code][d] = t
for k in p19.PRICE_KEYS:
    c = json.load(open(os.path.join(C19, "index", f"{k}.json")))
    old = index.get(k, {})
    index[k] = {**{d: v for d, v in c["closes"].items() if p19.HIST_START <= d and (d < cal[0] or k not in old)}, **old}
cal = cal0 + cal
seed = {"provenance": {
            "source_dir": "output/布鲁斯的金融宝藏/research/宽基ETF申赎算法核验20261122/claude",
            "raw_fetched_from": times[0], "raw_fetched_to": times[-1], "fetched_at": times[-1],
            "panel_csv_sha256": sha(panel), "raw_manifest_sha256": sha(os.path.join(RES, "raw", "manifest.json")),
            "index_tsv_sha256": {b["key"]: sha(os.path.join(RES, "raw", "index", f"{b['key']}.tsv.gz")) for b in p19.BENCHMARKS},
            "coverage": f"{cal[0]}~{cal[-1]}，{len(cal)} 交易日；2024-01-02 起 19 只无缺失，之前按上市先后存在缺失（未补值）",
            "pre2024": {"raw_dir": "data/seed19/raw_pre2024", "manifest_sha256": sha(os.path.join(RAW0, "manifest.json")),
                        "raw_files": len(man0), "raw_fetched_from": min(v["fetched_at"] for v in man0.values()),
                        "raw_fetched_to": max(v["fetched_at"] for v in man0.values()),
                        "calendar": "BaoStock query_trade_dates", "price": "BaoStock 不复权日线 close",
                        "nav_events": "东方财富 lsjz（DWJZ、FHSP）"},
            "note": "研究阶段官方原始响应解析结果；产品增量更新从种子之后的日期继续"},
        "calendar": cal, "names": names, "shares": shares,
        "nav": {c: {"navs": navs[c], "events": events[c]} for c in p19.CODES19}, "index": index}
out = os.path.join(ROOT, "data", "seed19", "composite_seed.json")
write_json_atomic(out, seed)
print(out, os.path.getsize(out), seed["provenance"]["coverage"])
