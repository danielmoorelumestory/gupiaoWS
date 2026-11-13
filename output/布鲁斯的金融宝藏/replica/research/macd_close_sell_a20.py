"""只尾盘卖 × A20（另附 A20+K−D 作参考）。规则延续，未调参：
A20：金叉当天 (DIF-DEA)/ATR14 ≥ 当年阈值（codex_filter17_thresholds.csv）才做本轮；K−D：金叉当天 KDJ K−D ≥ 5.3。
买入：金叉次日开盘；卖出：基准=死叉次日开盘，尾盘卖=死叉当天收盘价。单边 0.1%，复权连续价，空仓零收益。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, indicators, wilder
ITEMS = json.load(open("data/page_etfs_plus.json")); COST = .001
THR = pd.read_csv("research/codex_filter17_thresholds.csv").set_index("year").amplitude20.to_dict()
t0 = pd.read_csv("research/macd_early_cross_results.csv", dtype={"code": str}); GOOD = set(t0.loc[t0.good, "code"])
def sim(o, c, st, i0, cs):
    nav = 1.0; hold = False; out = []; pend = "buy" if st[i0 - 1] else None; nb = 0
    for k in range(i0, len(c)):
        if pend == "buy": nav *= (1 - COST) * c[k] / o[k]; hold = True; nb += 1
        elif pend == "sell": nav *= o[k] / c[k - 1] * (1 - COST); hold = False
        elif hold: nav *= c[k] / c[k - 1]
        pend = None
        if st[k] and not hold: pend = "buy"
        elif not st[k] and hold:
            if cs: nav *= 1 - COST; hold = False
            else: pend = "sell"
        out.append(nav)
    return np.array(out), nb
ann = lambda n, idx: n[-1] ** (365.25 / max(1, (idx[-1] - idx[0]).days)) - 1
mdd = lambda n: (n / np.maximum(np.maximum.accumulate(n), 1) - 1).min()
RULES = {"MACD": ("m", 0), "MACD尾盘卖": ("m", 1), "A20": ("a", 0), "A20尾盘卖": ("a", 1), "A20K": ("ak", 0), "A20K尾盘卖": ("ak", 1)}
rows = []; NAVB = {}
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); f, m, gold, dead = indicators(d, c); fac = c / d.close.values
    o, h, l = d.open.values * fac, d.high.values * fac, d.low.values * fac; prev = np.r_[np.nan, c[:-1]]
    gap = f["hist"].to_numpy() * c / wilder(np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))); kd = f.kd.to_numpy()
    S = {"m": m.copy(), "a": np.zeros(len(c), bool), "ak": np.zeros(len(c), bool)}; i = 1
    while i < len(c):
        if m[i] and not m[i - 1]:
            b = i
            while i < len(c) and m[i]: i += 1
            th = THR.get(d.index[b].year, np.nan); okA = np.isfinite(th) and np.isfinite(gap[b]) and gap[b] >= th
            if okA: S["a"][b:i] = True
            if okA and kd[b] >= 5.3: S["ak"][b:i] = True
        else: i += 1
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); yrs = (d.index[-1] - d.index[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    r = dict(code=code, name=name, good=code in GOOD, years=yrs); j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
    for k, (s, cs) in RULES.items():
        n, nb = sim(o, c, S[s], i0, cs); r[k] = ann(n, d.index[i0:]); r[k + "_dd"] = mdd(n); r[k + "_n"] = nb
        r[k + "_h1"] = ann(sim(o[:mid], c[:mid], S[s][:mid], i0, cs)[0], d.index[i0:mid]); r[k + "_h2"] = ann(sim(o, c, S[s], mid, cs)[0], d.index[mid:])
        if j0 >= 70: nv = sim(o, c, S[s], j0, cs)[0]; r[k + "_B"] = ann(nv, d.index[j0:]); NAVB[(k, code)] = pd.Series(nv, index=d.index[j0:])
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/macd_close_sell_a20_results.csv", index=False); L = t[t.years >= 3]
P = lambda v: f"{v*100:+.2f}%"
CMP = {"MACD尾盘卖": "MACD", "A20": "MACD", "A20尾盘卖": "A20", "A20K": "MACD", "A20K尾盘卖": "A20K"}
for nm, G in (("≥3年 50 只", L), ("MACD优秀 17 只", L[L.good]), ("其余 33 只", L[~L.good])):
    print(f"\n[{nm}] 2016 起")
    for k in RULES:
        b = CMP.get(k); x = f"｜对{b}：胜 {(G[k]>G[b]).sum()}/{len(G)} 前后半都胜 {((G[k+'_h1']>G[b+'_h1'])&(G[k+'_h2']>G[b+'_h2'])).sum()}" if b else ""
        y = f" 对MACD胜 {(G[k]>G['MACD']).sum()}/{len(G)}" if b and b != "MACD" else ""
        print(f"  {k:<8} 年化均值 {P(G[k].mean())} 中位 {P(G[k].median())} 前半 {P(G[k+'_h1'].mean())} 后半 {P(G[k+'_h2'].mean())} 回撤中位 {G[k+'_dd'].median()*100:.1f}% 买入中位 {G[k+'_n'].median():.0f}{x}{y}")
B = t[t["MACD_B"].notna()]; print(f"\n[2023-01-03 起固定 {len(B)} 只，初始等额组合]")
for k in RULES:
    port = pd.DataFrame({cd: NAVB[(k, cd)] for cd in B.code}).ffill().mean(axis=1); ys = []
    for yy in range(2023, 2027):
        pv = port[port.index.year < yy].iloc[-1] if (port.index.year < yy).any() else 1; ys.append(port[port.index.year == yy].iloc[-1] / pv - 1)
    print(f"  {k:<8} 年化均值 {P(B[k+'_B'].mean())} 组合年化 {P(ann(port.values, port.index))} 组合回撤 {mdd(port.values)*100:.1f}% 逐年 " + " ".join(f"{v*100:+.1f}" for v in ys))
G = L[L.good].set_index("code"); print("\n17 只（年化：MACD / MACD尾盘卖 / A20 / A20尾盘卖 / A20K / A20K尾盘卖）")
for cd, r in G.iterrows(): print(f"  {cd} {r['name'][:8]:<9}" + " ".join(f"{r[k]*100:+6.1f}" for k in RULES))
