"""MACD 金叉 + 站上 10 日线。运行前写定三种规则（复权连续价收盘判断，t+1 开盘成交，单边 0.1%，空仓零息）：
V1 多头周期内收盘首次站上 MA10 即买（金叉当天已在线上则当天定），死叉卖；同一周期卖出前只买一次。
V2 金叉当天收盘在 MA10 上方才买，否则跳过整轮；死叉卖。
V3 MACD 多头 且 收盘 > MA10 时持有，任一不满足即卖，可在周期内反复进出。
对照：纯 MACD、一直持有。价格/指标用 codex_macd_common.load（比例除权、上市前拆分不施加）。区间同 macd_a20_etf.py：max(第 70 个交易日, 2016-01-04) 起；另报 2023-01-03 起固定池。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, indicators
ITEMS = json.load(open("data/page_etfs_plus.json"))
res = pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}); GOOD = set(res.loc[res.good.astype(str) == "True", "code"])
def bt(d, dv, mm, st, i0, trades=None, tag=None):
    o, c = d.open.values, d.close.values; nav = 1.0; hold = False; out = []; nb = 0; entry = 1
    for k in range(i0, len(d)):
        want = bool(st[k - 1])
        if hold: nav *= (o[k] + dv[k]) * mm[k] / c[k - 1]
        if want != hold:
            if want: entry = nav; nb += 1
            elif trades is not None: trades.append((tag, nav * 0.999 / entry - 1))
            nav *= 0.999; hold = want
        if hold: nav *= c[k] / o[k]
        out.append(nav)
    return pd.Series(out, index=d.index[i0:]), nb
ann = lambda n: n.iloc[-1] ** (365.25 / max(1, (n.index[-1] - n.index[0]).days)) - 1
mdd = lambda n: (n / np.maximum(n.cummax(), 1) - 1).min()
K = ["持有", "MACD", "V1", "V2", "V3"]; rows = []; NAVB = {}; TR = []
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); f, m, gold, dead = indicators(d, c)
    above = c > pd.Series(c).rolling(10).mean().to_numpy()
    v1 = np.zeros(len(d), bool); v2 = np.zeros(len(d), bool); i = 1
    while i < len(d):
        if m[i] and not m[i - 1]:
            b = i
            while i < len(d) and m[i]: i += 1
            hit = np.flatnonzero(above[b:i])
            if len(hit): v1[b + hit[0]:i] = True
            if above[b]: v2[b:i] = True
        else: i += 1
    S = {"持有": np.ones(len(d), bool), "MACD": m, "V1": v1, "V2": v2, "V3": m & above}
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); yrs = (d.index[-1] - d.index[i0]).days / 365.25
    r = dict(code=code, name=name, good=code in GOOD, start=d.index[i0].date(), years=yrs)
    mid = i0 + (len(d) - i0) // 2
    for k, st in S.items():
        tr = []
        nav, nb = bt(d, dv, mm, st, i0, tr, k); r[k] = ann(nav); r[k + "_dd"] = mdd(nav); r[k + "_n"] = nb
        h1 = bt(d.iloc[:mid], dv[:mid], mm[:mid], st[:mid], i0)[0]; h2 = bt(d, dv, mm, st, mid)[0]; r[k + "_h1"] = ann(h1); r[k + "_h2"] = ann(h2)
        if yrs >= 3: TR += [dict(code=code, good=code in GOOD, rule=k, ret=x) for _, x in tr]
    j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
    if j0 >= 60:
        for k, st in S.items(): nav, _ = bt(d, dv, mm, st, j0); r[k + "_B"] = ann(nav); NAVB[(k, code)] = nav
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/macd_ma10_combo_results.csv", index=False); T = pd.DataFrame(TR)
P = lambda v: f"{v*100:+.2f}%"; L = t[t.years >= 3]
for nm, G in (("≥3年 50 只", L), ("MACD优秀 17 只", L[L.good]), ("其余 33 只", L[~L.good])):
    print(f"\n[{nm}] 2016 起")
    for k in K:
        x = T[(T.rule == k) & T.code.isin(G.code)].ret
        extra = "" if k in ("持有", "MACD") else f"｜胜MACD {(G[k] > G['MACD']).sum()}/{len(G)} 前后半都胜 {((G[k+'_h1'] > G['MACD_h1']) & (G[k+'_h2'] > G['MACD_h2'])).sum()} 回撤更小 {(G[k+'_dd'] > G['MACD_dd']).sum()}"
        wr = f" 胜率 {(x > 0).mean():.1%} 每笔均 {x.mean()*100:+.2f}%" if k != "持有" else ""
        print(f"  {k:<4} 年化均值 {P(G[k].mean())} 中位 {P(G[k].median())} 回撤中位 {G[k+'_dd'].median()*100:.1f}% 买入中位 {G[k+'_n'].median():.0f}{wr}{extra}")
B = t[t["MACD_B"].notna()]
print(f"\n[2023-01-03 起固定 {len(B)} 只]")
for k in K:
    port = pd.DataFrame({c: NAVB[(k, c)] for c in B.code}).ffill().mean(axis=1); ys = []
    for y in range(2023, 2027):
        prev = port[port.index.year < y].iloc[-1] if (port.index.year < y).any() else 1; ys.append(port[port.index.year == y].iloc[-1] / prev - 1)
    print(f"  {k:<4} 年化均值 {P(B[k+'_B'].mean())} 组合年化 {P(ann(port))} 组合回撤 {mdd(port)*100:.2f}% " + ("" if k == "MACD" else f"胜MACD {(B[k+'_B'] > B['MACD_B']).sum()}/{len(B)} ") + "逐年 " + " ".join(f"{y*100:+.1f}" for y in ys))
G = L[L.good].set_index("code").loc[["515790","159851","562500","512480","588200","513130","512200","159852","516160","512880","513090","159667","159792","159883","512070","159865","159869"]]
print("\n17 只（年化：持有 / MACD / V1 / V2 / V3；回撤 MACD / V1 / V3）")
for c, r in G.iterrows(): print(f"  {c} {r['name'][:8]:<9}" + " ".join(f"{r[k]*100:+6.1f}" for k in K) + f"   {r.MACD_dd*100:6.1f} {r.V1_dd*100:6.1f} {r.V3_dd*100:6.1f}")
