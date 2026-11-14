"""多元行情信号 × 两种模板：在原主池高波动上选，在池外高波动上检验（多元行情协议.md）。"""
import csv, gzip, io, json, math, random, statistics, sys
from collections import defaultdict
from pathlib import Path
from multiprocessing import Pool
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "年化优先与分组复验")); sys.path.insert(0, str(HERE))
import cs_common as C, regime_common as G
import run_extended as X
b = C.blank

def series_from_rows(rows): return {r["date"]: float(r["adjusted_close"]) for r in rows}
def load_new(code):
    rows = list(csv.DictReader(io.StringIO(gzip.decompress((HERE / f"data/{code}.csv.gz").read_bytes()).decode())))
    return series_from_rows(rows)
def load_510880():
    import prepare_new as P
    r = P.prepare("510880", "红利ETF")  # 生成 data/510880.csv.gz（unchecked 时也写出？）
    return r
def index_series(sym):
    d = json.loads(gzip.decompress((HERE / f"data/raw/{sym}-sina-index.json.gz").read_bytes()))
    return {x["day"][:10]: float(x["close"]) for x in d if x["day"][:10] <= "2026-11-10"}
def ma_state(series, n):
    """返回 {date: bool or None}：值 > n 日均线；不足 n 天为 None。"""
    ds = sorted(series); out = {}; s = 0.0; v = [series[d] for d in ds]
    for i, d in enumerate(ds):
        s += v[i]
        if i >= n: s -= v[i-n]
        out[d] = (v[i] > s/n) if i >= n-1 else None
    return out
def ratio(a, b_):
    return {d: a[d]/b_[d] for d in a if d in b_}
def ma_cross(series, f, s):
    ds = sorted(series); v = [series[d] for d in ds]; out = {}
    for i, d in enumerate(ds):
        out[d] = (sum(v[i-f+1:i+1])/f > sum(v[i-s+1:i+1])/s) if i >= s-1 else None
    return out

def build_signals(pool):
    dates = sorted({d for x in pool.values() for d in x["dates"]})
    cnt = {n: defaultdict(lambda: [0, 0]) for n in (20, 60)}
    for x in pool.values():
        c = [float(r["adjusted_close"]) for r in x["rows"]]
        for n in (20, 60):
            f = G._ma_flag(c, n)
            for i in range(n-1, len(c)):
                cell = cnt[n][x["dates"][i]]; cell[0] += f[i]; cell[1] += 1
    br = {n: {d: (cnt[n][d][0]/cnt[n][d][1] if cnt[n][d][1] >= 10 else None) for d in dates} for n in (20, 60)}
    sig = {}
    sig["B20-60"] = {d: None if br[20][d] is None else br[20][d] >= .6 for d in dates}
    sig["B60-50"] = {d: None if br[60][d] is None else br[60][d] >= .5 for d in dates}
    sm = {}; win = []
    for d in dates:
        if br[20][d] is not None: win.append(br[20][d]); win[:] = win[-5:]
        sm[d] = sum(win)/5 >= .55 if br[20][d] is not None and len(win) == 5 else None
    sig["B20s-55"] = sm
    h = {}; state = True
    for d in dates:
        v = br[20][d]
        if v is None: h[d] = None; continue
        if v >= .6: state = True
        elif v < .4: state = False
        h[d] = state
    sig["B20h"] = h
    sig["B2060"] = {d: None if br[20][d] is None or br[60][d] is None else (br[20][d] >= .5 and br[60][d] >= .5) for d in dates}
    p949, p890 = load_new("159949"), series_from_rows(pool["512890"]["rows"])
    p915 = load_new("159915"); p880 = load_new("510880")
    r1, r2 = ratio(p949, p890), ratio(p915, p880)
    sig["R1-20"], sig["R1-60"] = ma_state(r1, 20), ma_state(r1, 60)
    sig["R2-20"], sig["R2-60"] = ma_state(r2, 20), ma_state(r2, 60)
    sig["R2-x"] = ma_cross(r2, 20, 60)
    hs, cy = index_series("sh000300"), index_series("sz399006")
    sig["I300-60"], sig["I300-120"], sig["ICYB-60"] = ma_state(hs, 60), ma_state(hs, 120), ma_state(cy, 60)
    def vote(k):
        out = {}
        for d in set(sig["B20-60"]) | set(sig["R2-20"]) | set(sig["I300-60"]):
            vs = [sig[n].get(d) for n in ("B20-60", "R2-20", "I300-60")]; vs = [v for v in vs if v is not None]
            out[d] = None if len(vs) < 3 else sum(vs) >= k
        return out
    sig["V2of3"], sig["V3of3"] = vote(2), vote(3)
    return sig
def last_known(sig_map, dates):
    """把按日期的信号映射到某只 ETF 的交易日；该日无值时取之前最近一次（因果）；None/未形成 → 牛。"""
    ks = sorted(sig_map); out = []; j = -1; cur = None
    for d in dates:
        while j+1 < len(ks) and ks[j+1] <= d: j += 1; cur = sig_map[ks[j]]
        out.append(True if cur is None else cur)
    return out
SIGS = ["B20-60","B60-50","B20s-55","B20h","B2060","R1-20","R1-60","R2-20","R2-60","R2-x","I300-60","I300-120","ICYB-60","V2of3","V3of3"]
TEMPL = {"T1熊不开新仓": ("NONE", "X2"), "T2熊清仓": ("NONE", "ALL")}
def cfg(sigk, t): bi, bx = TEMPL[t]; return {**b, "macd":[12,26,9], "entry":"REG", "exit":"REG", "N":sigk, "bullin":"GOLD", "bullx":"X2", "bearin":bi, "bearx":bx}
PANEL = None
def init():
    global PANEL
    pool, new, audit = X.build(); sig = build_signals(pool)
    PANEL = {**{"P"+k: v for k, v in pool.items()}, **{"N"+k: v for k, v in new.items()}}
    for d in PANEL.values():
        d["reg"] = {k: last_known(sig[k], d["dates"]) for k in SIGS}
def run(job):
    key, w = job
    out = {}
    for code, d in PANEL.items():
        if key == "MACD": r = C.simulate_cs(d, C.grid[C.MACD_KEY], w, 20)
        elif key == "HOLD": r = C.engine.simulate(d, C.HOLD, w, 20)
        else:
            s, t = key.split("|"); r = G.simulate_rg(d, cfg(s, t), w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def calmar(m): return m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
if __name__ == "__main__":
    import math
    pool, new, audit = X.build()
    TH = .31
    def vol(rows):
        c_ = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c_[i]/c_[i-1]) for i in range(1, len(c_))]) * math.sqrt(244)
    SEL = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= TH]
    TEST = ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= TH and it["code"] in new]
    keys = ["MACD", "HOLD"] + [f"{s}|{t}" for s in SIGS for t in TEMPL]
    full = ("1900-01-01", "2026-11-10")
    with Pool(8, initializer=init) as p: res = p.map(run, [(k, full) for k in keys])
    R = {k: o for k, w, o in res}
    def agg(o, grp):
        ms = [o[c] for c in grp if c in o]
        cal = [x for x in (calmar(m) for m in ms) if x is not None]
        return statistics.median(cal), statistics.median(m["cagr"] for m in ms if m["cagr"] is not None), statistics.median(m["mdd"] for m in ms)
    print(f"选定集 {len(SEL)} 只，检验集 {len(TEST)} 只")
    print("\n## 选定集（原主池高波动，全历史）按卡玛比排序")
    rank = sorted(keys, key=lambda k: -agg(R[k], SEL)[0])
    for k in rank:
        c, a, m = agg(R[k], SEL); print(f"  {k:<22} 卡玛 {c:5.3f}  年化 {a*100:6.2f}%  回撤 {m*100:6.1f}%")
    top = [k for k in rank if k not in ("MACD", "HOLD")][:3]
    print("\n晋级：", top)
    print("\n## 检验集（池外高波动，全历史）")
    for k in ["MACD", "B20-60|T1熊不开新仓"] + top + ["HOLD"]:
        c, a, m = agg(R[k], TEST); print(f"  {k:<22} 卡玛 {c:5.3f}  年化 {a*100:6.2f}%  回撤 {m*100:6.1f}%")
    print("\n## 检验集分段（年化或累计中位 / 回撤中位）")
    show = ["MACD", "B20-60|T1熊不开新仓"] + top
    with Pool(8, initializer=init) as p: res2 = p.map(run, [(k, (a, z)) for k in show for _, a, z in X.WINDOWS[1:]])
    R2 = {(k, w): o for k, w, o in res2}
    for wn, a, z in X.WINDOWS[1:]:
        line = f"  {wn:<20}"
        for k in show:
            o = R2[(k, (a, z))]; ms = [o[c] for c in TEST if c in o]
            if not ms: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            v = statistics.median(m[use] for m in ms if m[use] is not None)
            line += f" | {k.split('|')[0][:10]} {v*100:6.1f}%({statistics.median(m['mdd'] for m in ms)*100:5.1f})"
        print(line + f"  n={len(ms)}")
    # 全部 30 组在检验集上的表现（诊断，不用于选择）
    print("\n## 诊断：全部组合在检验集全历史（不用于选择）")
    for k in sorted(keys, key=lambda k: -agg(R[k], TEST)[0]):
        c, a, m = agg(R[k], TEST); print(f"  {k:<22} 卡玛 {c:5.3f}  年化 {a*100:6.2f}%  回撤 {m*100:6.1f}%")
