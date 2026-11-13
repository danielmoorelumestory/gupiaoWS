"""尾盘成交汇总：信号都是收盘确认的金叉/死叉（不变），只改成交时间：次日开盘 vs 当天收盘（尾盘）。
买入规则 × 成交方式：{MACD, A20, A20+K−D} × {基准(次开买/次开卖), 尾盘买, 尾盘卖, 尾盘买卖}。
A20 / K−D 均在金叉当天判断，口径同 macd_close_sell_a20.py。单边 0.1%，复权连续价，空仓零收益。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, indicators, wilder
ITEMS = json.load(open("data/page_etfs_plus.json")); COST = .001
THR = pd.read_csv("research/codex_filter17_thresholds.csv").set_index("year").amplitude20.to_dict()
t0 = pd.read_csv("research/macd_early_cross_results.csv", dtype={"code": str}); GOOD = set(t0.loc[t0.good, "code"])
def sim(o, c, st, i0, cb, cs, tr=None):
    nav = 1.0; hold = False; out = []; pend = "buy" if st[i0 - 1] else None; ent = 1
    for k in range(i0, len(c)):
        if pend == "buy": nav *= (1 - COST); ent = nav; nav *= c[k] / o[k]; hold = True
        elif pend == "sell":
            nav *= o[k] / c[k - 1] * (1 - COST); hold = False
            if tr is not None: tr.append(nav / ent - 1)
        elif hold: nav *= c[k] / c[k - 1]
        pend = None
        if st[k] and not hold:
            if cb: nav *= 1 - COST; ent = nav; hold = True
            else: pend = "buy"
        elif not st[k] and hold:
            if cs:
                nav *= 1 - COST; hold = False
                if tr is not None: tr.append(nav / ent - 1)
            else: pend = "sell"
        out.append(nav)
    return np.array(out)
ann = lambda n, idx: n[-1] ** (365.25 / max(1, (idx[-1] - idx[0]).days)) - 1
mdd = lambda n: (n / np.maximum(np.maximum.accumulate(n), 1) - 1).min()
EX = {"基准": (0, 0), "尾盘买": (1, 0), "尾盘卖": (0, 1), "尾盘买卖": (1, 1)}; BR = ["MACD", "A20", "A20K"]
rows = []; NAVB = {}; TR = {}; EV = []
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); f, m, gold, dead = indicators(d, c); fac = c / d.close.values
    o, h, l = d.open.values * fac, d.high.values * fac, d.low.values * fac; prev = np.r_[np.nan, c[:-1]]
    gap = f["hist"].to_numpy() * c / wilder(np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))); kd = f.kd.to_numpy()
    S = {"MACD": m.copy(), "A20": np.zeros(len(c), bool), "A20K": np.zeros(len(c), bool)}; i = 1
    while i < len(c):
        if m[i] and not m[i - 1]:
            b = i
            while i < len(c) and m[i]: i += 1
            th = THR.get(d.index[b].year, np.nan); okA = np.isfinite(th) and np.isfinite(gap[b]) and gap[b] >= th
            if okA: S["A20"][b:i] = True
            if okA and kd[b] >= 5.3: S["A20K"][b:i] = True
        else: i += 1
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); yrs = (d.index[-1] - d.index[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    r = dict(code=code, name=name, good=code in GOOD, years=yrs); j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
    for br in BR:
        st = S[br]
        for ex, (cb, cs) in EX.items():
            k_ = f"{br}|{ex}"; tr = []; n = sim(o, c, st, i0, cb, cs, tr); r[k_] = ann(n, d.index[i0:]); r[k_ + "_dd"] = mdd(n)
            r[k_ + "_h1"] = ann(sim(o[:mid], c[:mid], st[:mid], i0, cb, cs), d.index[i0:mid]); r[k_ + "_h2"] = ann(sim(o, c, st, mid, cb, cs), d.index[mid:])
            if yrs >= 3: TR.setdefault(k_, []).extend((code, x) for x in tr)
            if j0 >= 70: nv = sim(o, c, st, j0, cb, cs); r[k_ + "_B"] = ann(nv, d.index[j0:]); NAVB[(k_, code)] = pd.Series(nv, index=d.index[j0:])
    rows.append(r)
    if yrs >= 3:
        for k in range(i0, len(c) - 1):
            if m[k] != m[k - 1]: EV.append(dict(code=code, good=code in GOOD, date=d.index[k], side="买" if m[k] else "卖", g=(o[k + 1] / c[k] - 1) if m[k] else (c[k] / o[k + 1] - 1)))
t = pd.DataFrame(rows); t.to_csv("research/macd_close_exec_results.csv", index=False); L = t[t.years >= 3]; E = pd.DataFrame(EV)
P = lambda v: f"{v*100:+.2f}%"
print("一、每次信号：尾盘成交相对次日开盘成交多赚（买：次开/收-1；卖：收/次开-1），≥3年 50 只 2016 起")
for nm, sel in (("50 只", E.code.notna()), ("17 只", E.good), ("33 只", ~E.good)):
    for s in ("买", "卖"):
        g = E[sel & (E.side == s)]; e1, e2 = g[g.date < "2021-01-01"].g, g[g.date >= "2021-01-01"].g
        print(f"  {nm} 尾盘{s}：{len(g)} 次 平均 {g.g.mean()*100:+.3f}% 中位 {g.g.median()*100:+.3f}% 占便宜 {(g.g>0).mean():.0%} 吃亏 {(g.g<0).mean():.0%} ｜ 2016-20 {e1.mean()*100:+.3f}% 2021- {e2.mean()*100:+.3f}%")
for nm, G in (("≥3年 50 只", L), ("MACD优秀 17 只", L[L.good]), ("其余 33 只", L[~L.good])):
    print(f"\n[{nm}] 2016 起")
    for br in BR:
        for ex in EX:
            k_ = f"{br}|{ex}"; b = f"{br}|基准"; x = np.array([v for cd, v in TR[k_] if cd in set(G.code)])
            cmp = f"｜胜基准 {(G[k_]>G[b]).sum()}/{len(G)} 前后半都胜 {((G[k_+'_h1']>G[b+'_h1'])&(G[k_+'_h2']>G[b+'_h2'])).sum()}" if ex != "基准" else ""
            print(f"  {br:<4} {ex:<4} 年化均值 {P(G[k_].mean())} 中位 {P(G[k_].median())} 前半 {P(G[k_+'_h1'].mean())} 后半 {P(G[k_+'_h2'].mean())} 回撤中位 {G[k_+'_dd'].median()*100:.1f}% 胜率 {(x>0).mean():.1%} 每笔 {x.mean()*100:+.2f}%{cmp}")
B = t[t["MACD|基准_B"].notna()]; print(f"\n[2023-01-03 起固定 {len(B)} 只，初始等额组合]")
for br in BR:
    for ex in EX:
        k_ = f"{br}|{ex}"; port = pd.DataFrame({cd: NAVB[(k_, cd)] for cd in B.code}).ffill().mean(axis=1); ys = []
        for yy in range(2023, 2027):
            pv = port[port.index.year < yy].iloc[-1] if (port.index.year < yy).any() else 1; ys.append(port[port.index.year == yy].iloc[-1] / pv - 1)
        print(f"  {br:<4} {ex:<4} 组合年化 {P(ann(port.values, port.index))} 组合回撤 {mdd(port.values)*100:.1f}% 逐年 " + " ".join(f"{v*100:+.1f}" for v in ys))
G = L[L.good].set_index("code"); print("\n17 只 MACD 年化（基准 / 尾盘买 / 尾盘卖 / 尾盘买卖）")
for cd, r in G.iterrows(): print(f"  {cd} {r['name'][:8]:<9}" + " ".join(f"{r['MACD|'+ex]*100:+6.1f}" for ex in EX))
