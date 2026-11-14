"""池外高波动 ETF 多段牛熊检验（协议.md）。方案冻结，不选参。"""
import csv, gzip, io, json, random, statistics, sys
from pathlib import Path
from multiprocessing import Pool
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "年化优先与分组复验"))
import cs_common as C, regime_common as G, filter_common as F
from cs_common import summarize
b = C.blank
SCHEMES = {
  "纯MACD·尾盘卖（基准）": ("e", C.grid[C.MACD_KEY], True),
  "纯MACD·次开卖": ("e", C.grid[C.MACD_KEY], False),
  "16/35/9+MA10 E3/X3": ("e", {**b,"entry":"E3","exit":"X3","n":9,"hi":80,"macd":[16,35,9]}, True),
  "16/35/9+MA10 E3/X2": ("e", {**b,"entry":"E3","exit":"X2","macd":[16,35,9]}, True),
  "MACD+A20": ("f", {**b,"entry":"MACDF","exit":"X2","macd":[12,26,9],"flt":"A20"}, True),
  "MACD+K−D≥5.3": ("f", {**b,"entry":"MACDF","exit":"X2","macd":[12,26,9],"flt":"KD"}, True),
  "周线分段 WZ": ("r", {**b,"macd":[12,26,9],"entry":"REG","exit":"REG","N":"WZ-live","bullin":"GOLD","bullx":"X2","bearin":"E3","bearx":"X4"}, True),
  "宽度分段 B20-60": ("r", {**b,"macd":[12,26,9],"entry":"REG","exit":"REG","N":"B20-60","bullin":"GOLD","bullx":"X2","bearin":"NONE","bearx":"X2"}, True),
  "买入持有": ("e", C.HOLD, False),
}
WINDOWS = [("全历史", "1900-01-01", "2026-11-10"),
           ("牛 2014-07～2015-06", "2014-07-01", "2015-06-12"), ("熊 2015-06～2016-01", "2015-06-15", "2016-01-28"),
           ("震荡 2016-02～2018-01", "2016-02-01", "2018-01-26"), ("熊 2018", "2018-01-29", "2018-12-28"),
           ("牛 2019-01～2021-02", "2019-01-02", "2021-02-18"), ("熊 2021-02～2024-01", "2021-02-19", "2024-01-31"),
           ("牛 2024-02～2026-11", "2024-02-01", "2026-11-10")]
SETS = None; PANEL = None
def build():
    pool = C.load_panel(); _, th = F.add_filters(C.load_panel())
    audit = json.load(open(HERE / "data_audit.json"))
    new = {}
    for it in audit:
        if it.get("status") not in ("eligible", "unchecked"): continue
        rows = list(csv.DictReader(io.StringIO(gzip.decompress((HERE / f"data/{it['code']}.csv.gz").read_bytes()).decode()))) if (HERE / f"data/{it['code']}.csv.gz").exists() else None
        if rows is None: continue
        new[it["code"]] = C.engine.prepare(rows, it)
    F.add_filters(new, th); G.add_reg(new, breadth_from=pool)
    F.add_filters(pool, th); G.add_reg(pool)
    return pool, new, audit
def init():
    global PANEL; pool, new, _ = build(); PANEL = {**{"P"+k: v for k, v in pool.items()}, **{"N"+k: v for k, v in new.items()}}
def run(job):
    name, (wn, a, z) = job; kind, c, cs = SCHEMES[name]; out = {}
    for code, d in PANEL.items():
        if kind == "r": r = G.simulate_rg(d, c, (a, z), 20)
        elif kind == "f": r = F.simulate_f(d, c, (a, z), 20)
        else: r = (C.simulate_cs if cs else C.engine.simulate)(d, c, (a, z), 20)
        if r: out[code] = r["metric"]
    return name, wn, out
if __name__ == "__main__":
    import math
    pool, new, audit = build()
    TH = 0.31
    vol = {it["code"]: it["vol"] for it in audit if "vol" in it}
    main_hi = sorted("N"+k for k, it in ((it["code"], it) for it in audit) if it.get("status") == "eligible" and vol[k] >= TH and k in new)
    unchk_hi = sorted("N"+k for k, it in ((it["code"], it) for it in audit) if it.get("status") == "unchecked" and vol[k] >= TH and k in new)
    lo_new = sorted("N"+k for k, it in ((it["code"], it) for it in audit) if it.get("status") == "eligible" and vol[k] < TH and k in new)
    pv = {}
    for k, d in pool.items():
        c_ = [float(r["adjusted_close"]) for r in d["rows"]]; pv[k] = statistics.pstdev([math.log(c_[i]/c_[i-1]) for i in range(1, len(c_))]) * math.sqrt(244)
    pool_hi = sorted("P"+k for k, v in pv.items() if v >= TH)
    names = {**{"N"+it["code"]: it["name"] for it in audit}, **{"P"+k: d["item"]["name"] for k, d in pool.items()}}
    groups = {"池外高波动（主结论）": main_hi, "池外高波动·未核对": unchk_hi, "池外低波动（对照）": lo_new, "原主池高波动（参与过选参，仅参考）": pool_hi}
    for g, s in groups.items(): print(f"{g} {len(s)} 只：" + "、".join(names[x][:8] for x in s))
    with Pool(8, initializer=init) as p: res = p.map(run, [(n, w) for n in SCHEMES for w in WINDOWS])
    R = {(n, w): o for n, w, o in res}
    base = "纯MACD·尾盘卖（基准）"; rows = []
    def stat(o, grp):
        ms = [o[c] for c in grp if c in o]
        if not ms: return None
        ann = [m["cagr"] for m in ms if m["cagr"] is not None]
        use = "cagr" if len(ann) >= max(3, len(ms)//2) else "total_return"
        vals = [m[use] for m in ms if m[use] is not None]
        return use, statistics.median(vals), statistics.median(m["mdd"] for m in ms), len(ms)
    def ci(o, bo, grp, use):
        codes = [c for c in grp if c in o and c in bo and o[c][use] is not None and bo[c][use] is not None]
        if len(codes) < 3: return None
        rnd = random.Random(20261113)
        d = sorted(statistics.median(o[c][use] for c in s) - statistics.median(bo[c][use] for c in s) for s in ([rnd.choice(codes) for _ in codes] for _ in range(1000)))
        return d[25], d[974], sum(o[c][use] > bo[c][use] for c in codes), len(codes)
    for g, grp in groups.items():
        if not grp: continue
        print(f"\n######## {g}")
        for wn, a, z in WINDOWS:
            bs = stat(R[(base, wn)], grp)
            if bs is None: continue
            use = bs[0]
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}中位 / 回撤中位 / 样本）")
            for n in SCHEMES:
                s = stat(R[(n, wn)], grp)
                if s is None: continue
                o, bo = R[(n, wn)], R[(base, wn)]
                v = [o[c][use] for c in grp if c in o and o[c][use] is not None]
                med = statistics.median(v) if v else None
                line = f"  {n:<22} {('—' if med is None else f'{med*100:7.2f}%')}  回撤 {s[2]*100:6.1f}%  n={s[3]}"
                if n != base:
                    x = ci(o, bo, grp, use)
                    if x: line += f"  差95%[{x[0]*100:+.1f},{x[1]*100:+.1f}]{' ★' if x[0] > 0 else (' ✗' if x[1] < 0 else '')}  逐只胜 {x[2]}/{x[3]}"
                print(line)
                rows.append({"组": g, "时段": wn, "方案": n, "指标": "年化" if use == "cagr" else "累计", "中位": med, "回撤中位": s[2], "样本": s[3]})
    with open(HERE / "结果汇总.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
