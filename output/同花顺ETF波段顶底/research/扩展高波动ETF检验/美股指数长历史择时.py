"""用户要求（2026-11-18）：回测时间长一些。用 Yahoo 指数日线（纳指100 1985-10 起，标普500 1970 起；与腾讯近 300 日收盘一致）。
直接在指数上回测（不含股息，不含 QDII 溢价；ETF 实际还有约 1~1.5% 股息、汇率与溢价影响），事前写定规则与 美股ETF纯择时降回撤.py 相同：
T200、T200B、M10、MOM12、X50、VOL、VOLT、CRASH、V15i、V15iT；信号用当日收盘，仓位作用于下一交易日；换手成本 0.1%；空仓收益 0（另报空仓按年化 2% 的敏感性）。
窗口：全历史（预热 260 日后）、1990 起、2000 起、2010 起、2020 起；另报逐个十年（1990s/2000s/2010s/2020s）。
合格：两指数 × 全部 5 个窗口都满足 回撤比一直持有小 ≥25%（相对）且 卡玛 ≥ 一直持有。历史统计，不构成投资建议。"""
import json, gzip, math, statistics, sys
from pathlib import Path
RAW = Path(__file__).resolve().parent / "data/raw"
def load(n): return dict(json.loads(gzip.decompress((RAW / f"yahoo-{n}.json.gz").read_bytes())))
def metrics(nav, a, b):
    ks = [k for k in sorted(nav) if a <= k <= b]
    if len(ks) < 200: return None
    v0 = nav[ks[0]]; yrs = (len(ks) - 1) / 252; cagr = (nav[ks[-1]] / v0) ** (1 / yrs) - 1
    peak = v0; mdd = 0; pk = when = ks[0]; best = ("", "")
    for k in ks:
        if nav[k] > peak: peak, pk = nav[k], k
        dd = nav[k] / peak - 1
        if dd < mdd: mdd, best = dd, (pk, k)
    return {"cagr": cagr, "mdd": mdd, "cal": cagr / -mdd if mdd else 0, "when": f"{best[0][:7]}→{best[1][:7]}"}
def states(I):
    ds = sorted(I); iv = [I[t] for t in ds]; n = len(ds)
    def ma(k): 
        out = [None] * n; s = 0
        for i in range(n):
            s += iv[i]
            if i >= k: s -= iv[i-k]
            if i >= k-1: out[i] = s / k
        return out
    M200, M210, M50, M20 = ma(200), ma(210), ma(50), ma(20)
    r = [0] + [iv[i] / iv[i-1] - 1 for i in range(1, n)]
    VOL = [statistics.pstdev(r[i-19:i+1]) * math.sqrt(252) if i >= 20 else None for i in range(n)]
    S = {}
    S["T200"] = [M200[i] is None or iv[i] > M200[i] for i in range(n)]
    s = True; S["T200B"] = []
    for i in range(n):
        if M200[i]: s = False if iv[i] < M200[i] * .98 else True if iv[i] > M200[i] * 1.02 else s
        S["T200B"].append(s)
    def monthly(cond):
        out = []; cur = True
        for i in range(n):
            if i + 1 < n and ds[i+1][:7] != ds[i][:7]:
                c = cond(i); cur = cur if c is None else c
            out.append(cur)
        return out
    S["M10"] = monthly(lambda i: iv[i] > M210[i] if M210[i] else None)
    S["MOM12"] = monthly(lambda i: iv[i] > iv[i-252] if i >= 252 else None)
    S["X50"] = [M200[i] is None or M50[i] > M200[i] for i in range(n)]
    s = True; S["VOL"] = []
    for i in range(n):
        if VOL[i] is not None: s = False if VOL[i] > .30 else True if VOL[i] < .20 else s
        S["VOL"].append(s)
    S["VOLT"] = [a and b for a, b in zip(S["VOL"], S["T200"])]
    s = True; S["CRASH"] = []
    for i in range(n):
        if i >= 20: s = False if iv[i] / iv[i-5] - 1 <= -.06 else True if (not s and iv[i] > M20[i]) else s
        S["CRASH"].append(s)
    W = {k: [1.0 if x else 0.0 for x in v] for k, v in S.items()}
    for name, half in (("V15i", False), ("V15iT", True)):
        cur = 1.0; out = []
        for i in range(n):
            w = min(1.0, .15 / VOL[i]) if VOL[i] else 1.0
            if half and not S["T200"][i]: w *= .5
            if abs(w - cur) >= .1 or (w == 1.0 and cur != 1.0): cur = w
            out.append(cur)
        W[name] = out
    W["一直持有"] = [1.0] * n
    return ds, iv, W
def run(ds, iv, w, cash=0.0, cost=.001):
    nav = {ds[0]: 1.0}; v = 1.0
    for i in range(1, len(ds)):
        wt = w[i-1]; pw = w[i-2] if i >= 2 else wt
        v *= (1 + wt * (iv[i] / iv[i-1] - 1) + (1 - wt) * cash / 252) * (1 - cost * abs(wt - pw)); nav[ds[i]] = v
    return nav
if __name__ == "__main__":
    res = {}; ORDER = ["一直持有", "T200", "T200B", "M10", "MOM12", "X50", "VOL", "VOLT", "CRASH", "V15i", "V15iT"]
    for nm in ("NDX", "SPX"):
        I = load(nm); ds, iv, W = states(I); start = ds[260]
        WINS = {"全历史": (start, "2026-11-10"), "1990起": ("1990-01-01", "2026-11-10"), "2000起": ("2000-01-01", "2026-11-10"), "2010起": ("2010-01-01", "2026-11-10"), "2020起": ("2020-01-01", "2026-11-10")}
        DEC = {"1990s": ("1990-01-01", "1999-12-31"), "2000s": ("2000-01-01", "2009-12-31"), "2010s": ("2010-01-01", "2019-12-31"), "2020s": ("2020-01-01", "2026-11-10")}
        print(f"\n######## {nm}（{start} 起可用）")
        for cash in (0.0, 0.02):
            navs = {k: run(ds, iv, W[k], cash) for k in ORDER}
            for wn, (a, b) in ({**WINS, **DEC}.items() if cash == 0 else WINS.items()):
                print(f"## {wn}{'' if cash == 0 else '（空仓年化 2%）'}")
                for k in ORDER:
                    m = metrics(navs[k], max(a, start), b)
                    if m is None: continue
                    if cash == 0: res[(nm, wn, k)] = m
                    print(f"  {k:8s} 年化 {m['cagr']*100:6.1f}% 回撤 {m['mdd']*100:6.1f}%（{m['when']}） 卡玛 {m['cal']:5.2f}")
    print("\n######## 合格检查（空仓收益 0；两指数 × 5 窗口；格内 回撤缩小/卡玛差/年化差pp）")
    for k in ORDER[1:]:
        ok = True; cells = []
        for nm in ("NDX", "SPX"):
            for wn in ("全历史", "1990起", "2000起", "2010起", "2020起"):
                m, h = res[(nm, wn, k)], res[(nm, wn, "一直持有")]
                cut = 1 - m["mdd"] / h["mdd"]; dc = m["cal"] - h["cal"]; da = (m["cagr"] - h["cagr"]) * 100; good = cut >= .25 and dc >= 0; ok &= good
                cells.append(f"{nm[0]}{wn[:4]}:{cut*100:.0f}%/{dc:+.2f}/{da:+.1f}{'✓' if good else '✗'}")
        print(f"  {'合格' if ok else '  - '} {k:6s} " + " ".join(cells))
