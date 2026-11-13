"""R1 尾盘成交拆成只尾盘买 / 只尾盘卖（规则延续 macd_early_cross.py，未调参）。
尾盘买：t 收盘金叉 → 按 t 收盘价买；死叉仍次日开盘卖。尾盘卖：死叉按 t 收盘价卖；金叉仍次日开盘买。
另统计每次信号：收盘价 vs 次日开盘价的差（买：次开/收-1；卖：收/次开-1），即尾盘成交相对基准多赚的部分。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, ema
ITEMS = json.load(open("data/page_etfs_plus.json")); COST = .001
t0 = pd.read_csv("research/macd_early_cross_results.csv", dtype={"code": str}); GOOD = set(t0.loc[t0.good, "code"])
def sim(o, c, m, i0, cb, cs):
    nav = 1.0; hold = False; out = []; pend = None  # pend: 次日开盘要做的动作
    if m[i0 - 1]: pend = "buy"
    for k in range(i0, len(c)):
        if pend == "buy": nav *= (1 - COST) * c[k] / o[k]; hold = True
        elif pend == "sell": nav *= o[k] / c[k - 1] * (1 - COST); hold = False
        elif hold: nav *= c[k] / c[k - 1]
        pend = None
        if m[k] and not hold:
            if cb: nav *= 1 - COST; hold = True
            else: pend = "buy"
        elif not m[k] and hold:
            if cs: nav *= 1 - COST; hold = False
            else: pend = "sell"
        out.append(nav)
    return np.array(out)
ann = lambda n, idx: n[-1] ** (365.25 / max(1, (idx[-1] - idx[0]).days)) - 1
mdd = lambda n: (n / np.maximum(np.maximum.accumulate(n), 1) - 1).min()
rows = []; EV = []
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); o = d.open.values * c / d.close.values
    dif = ema(c, 2 / 13) - ema(c, 2 / 27); m = dif > ema(dif, .2)
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); yrs = (d.index[-1] - d.index[i0]).days / 365.25
    if yrs < 3: continue
    mid = i0 + (len(d) - i0) // 2; r = dict(code=code, good=code in GOOD)
    for k, (cb, cs) in {"基准": (0, 0), "R1双向": (1, 1), "只尾盘买": (1, 0), "只尾盘卖": (0, 1)}.items():
        n = sim(o, c, m, i0, cb, cs); r[k] = ann(n, d.index[i0:]); r[k + "_dd"] = mdd(n)
        r[k + "_h1"] = ann(sim(o[:mid], c[:mid], m[:mid], i0, cb, cs), d.index[i0:mid]); r[k + "_h2"] = ann(sim(o, c, m, mid, cb, cs), d.index[mid:])
    rows.append(r)
    for k in range(i0, len(c) - 1):
        if m[k] != m[k - 1]: EV.append(dict(good=code in GOOD, side="买" if m[k] else "卖", g=(o[k + 1] / c[k] - 1) if m[k] else (c[k] / o[k + 1] - 1)))
t = pd.DataFrame(rows); E = pd.DataFrame(EV)
for nm, sel, es in (("50 只", t.code.notna(), E.good.notna()), ("MACD优秀 17 只", t.good, E.good), ("其余 33 只", ~t.good, ~E.good)):
    G = t[sel]; print(f"\n[{nm}]")
    for k in ("基准", "R1双向", "只尾盘买", "只尾盘卖"):
        x = f"（差 {(G[k]-G['基准']).mean()*100:+.2f}）胜基准 {(G[k]>G['基准']).sum()}/{len(G)} 前后半都胜 {((G[k+'_h1']>G['基准_h1'])&(G[k+'_h2']>G['基准_h2'])).sum()}" if k != "基准" else ""
        print(f"  {k:<6} 年化均值 {G[k].mean()*100:+.2f}%{x} 回撤中位 {G[k+'_dd'].median()*100:.1f}%")
    for s in ("买", "卖"):
        g = E[es & (E.side == s)].g; print(f"  尾盘{s}相对次日开盘：平均 {g.mean()*100:+.3f}% 中位 {g.median()*100:+.3f}% 占便宜比例 {(g>0).mean():.0%}（{len(g)} 次）")
