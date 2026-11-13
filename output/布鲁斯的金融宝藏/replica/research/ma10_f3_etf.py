"""F3“来回次数少”过滤用在 63 只页面 ETF 的 10 日线规则上。运行前写定，跑完不改：
规则：复权连续价收盘站上 10 日线次日开盘买，跌破次日开盘卖；F3 = 过去 60 日 10 日线穿越次数 ≤ 9（阈值来自 ma10_regime.py 指数训练集，不用 ETF 数据重定）；
F3 只拦新买入，持仓照常跌破卖。对照：不过滤的 10 日线、MACD 12/26/9、一直持有。
口径同 macd_etf.py：未复权价成交，分红/拆分按东财记录（缓存），t+1 开盘，单边 0.1%，空仓零息；修正：早于首条行情的拆分记录不施加（Codex 第15轮）。
起点：上市后第 70 个交易日开盘（10 日线 + 60 日穿越计数预热），至 2026-11-10。汇总只看回测期 ≥3 年；另报前后两半段、MACD优秀 17 只/其余，以及 2023 年起的共同时段。"""
import json, numpy as np, pandas as pd
END = "2026-11-10"; COST = 0.001; TH = 9
codes = {c: n for c, n, *_ in json.load(open("data/page_etfs_plus.json"))}
def load(code):
    d = pd.read_csv(f"data/etf_{code}_raw.csv", parse_dates=["date"]).set_index("date").sort_index().loc[:END]
    d = d[~d.index.duplicated()]
    j = json.load(open(f"data/etf_{code}_events.json"))
    dv = pd.Series(0.0, index=d.index); mult = pd.Series(1.0, index=d.index)
    for t, x in j["div"]:
        k = d.index.searchsorted(pd.Timestamp(t))
        if k >= len(d) or k == 0: continue
        exp, gap = x / d.close.iloc[k - 1], d.open.iloc[k] / d.close.iloc[k - 1] - 1
        if exp >= 0.02 and gap > -0.5 * exp: continue
        dv.iloc[k] += x
    for t, ratio in j["spl"]:
        t = pd.Timestamp(t)
        if t < d.index[0]: continue
        ks = range(max(1, d.index.searchsorted(t) - 2), min(len(d), d.index.searchsorted(t) + 4))
        k = min(ks, key=lambda k: abs(np.log(d.close.iloc[k - 1] / d.open.iloc[k]) - np.log(ratio)))
        mult.iloc[k] = ratio
    r = (d.close + dv) * mult / d.close.shift(1); r.iloc[0] = 1.0
    return d, dv, mult, d.close.iloc[0] * r.cumprod()
def bt(d, dv, mult, st, i0, i1=None):
    o, c, D, M, s = d.open.values, d.close.values, dv.values, mult.values, st.values
    i1 = len(d) if i1 is None else i1; nav = 1.0; hold = False; out = []; ntr = 0; held = 0
    for k in range(i0, i1):
        want = bool(s[k - 1])
        if hold: nav *= (o[k] + D[k]) * M[k] / c[k - 1]
        if want != hold: nav *= 1 - COST; hold = want; ntr += want
        if hold: nav *= c[k] / o[k]; held += 1
        out.append(nav)
    return pd.Series(out, index=d.index[i0:i1]), ntr, held / max(1, i1 - i0)
ann = lambda n: n.iloc[-1] ** (365.25 / max(1, (n.index[-1] - n.index[0]).days)) - 1
mdd = lambda n: (n / np.maximum(n.cummax(), 1) - 1).min()
def states(adj):
    above = adj > adj.rolling(10).mean()
    cross60 = above.astype(int).diff().abs().rolling(60).sum()
    gate = (cross60 <= TH).fillna(False).values; a = above.values; s = np.zeros(len(a), bool)
    for i in range(1, len(a)): s[i] = a[i] if s[i - 1] else (a[i] and gate[i])
    dif = adj.ewm(span=12, adjust=False).mean() - adj.ewm(span=26, adjust=False).mean()
    return {"MA10": above, "MA10+F3": pd.Series(s, index=adj.index), "MACD": dif > dif.ewm(span=9, adjust=False).mean(), "持有": pd.Series(True, index=adj.index)}, gate
res = pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str})
GOOD = set(res.loc[res.good.astype(str) == "True", "code"])
rows = []
for code in codes:
    d, dv, mult, adj = load(code); S, gate = states(adj)
    i0 = 70
    if i0 >= len(d) - 20: continue
    r = dict(code=code, name=codes[code], start=d.index[i0].date(), years=(d.index[-1] - d.index[i0]).days / 365.25, good=code in GOOD, gate=gate[i0:].mean())
    mid = i0 + (len(d) - i0) // 2
    for k, st in S.items():
        nav, n, ex = bt(d, dv, mult, st, i0)
        r[k] = ann(nav); r[k + "_dd"] = mdd(nav); r[k + "_n"] = n; r[k + "_ex"] = ex
        r[k + "_h1"] = ann(bt(d, dv, mult, st, i0, mid)[0]); r[k + "_h2"] = ann(bt(d, dv, mult, st, mid)[0])
        j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
        r[k + "_23"] = ann(bt(d, dv, mult, st, j0)[0]) if j0 >= i0 else np.nan
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/ma10_f3_etf_results.csv", index=False)
L = t[t.years >= 3]
P = lambda v: f"{v*100:+.2f}%"
print(f"共 {len(t)} 只，回测期 ≥3 年 {len(L)} 只（MACD优秀 {L.good.sum()} 只）。F3 通过的交易日比例中位 {L.gate.median():.0%}")
print(f"\n{'策略':<9}{'年化均值':>9}{'年化中位':>9}{'回撤中位':>9}{'买入次数中位':>10}{'持仓时间中位':>10}")
for k in ("持有", "MA10", "MA10+F3", "MACD"):
    print(f"{k:<9}{P(L[k].mean()):>10}{P(L[k].median()):>10}{L[k+'_dd'].median()*100:>9.1f}%{L[k+'_n'].median():>10.0f}{L[k+'_ex'].median():>11.0%}")
def cmp(a, b, G=L, tag=""):
    w = (G[a] > G[b]).sum(); both = ((G[a+'_h1'] > G[b+'_h1']) & (G[a+'_h2'] > G[b+'_h2'])).sum(); dd = (G[a+'_dd'] > G[b+'_dd']).sum()
    print(f"  {tag}{a} 对 {b}：年化胜 {w}/{len(G)}，平均差 {P((G[a]-G[b]).mean())}，中位差 {P((G[a]-G[b]).median())}；前后半段都胜 {both}；回撤更小 {dd}")
print()
for a, b in (("MA10+F3", "MA10"), ("MA10+F3", "持有"), ("MA10+F3", "MACD"), ("MA10", "持有"), ("MACD", "持有")): cmp(a, b)
for nm, G in (("MACD优秀", L[L.good]), ("其余", L[~L.good])):
    print(f"\n[{nm} {len(G)} 只] 年化均值 持有 {P(G['持有'].mean())}  MA10 {P(G['MA10'].mean())}  MA10+F3 {P(G['MA10+F3'].mean())}  MACD {P(G['MACD'].mean())}")
    cmp("MA10+F3", "MA10", G); cmp("MA10+F3", "MACD", G)
C = t[t["持有_23"].notna()]
print(f"\n[2023-01-03 起共同时段，{len(C)} 只] 年化均值 持有 {P(C['持有_23'].mean())}  MA10 {P(C['MA10_23'].mean())}  MA10+F3 {P(C['MA10+F3_23'].mean())}  MACD {P(C['MACD_23'].mean())}；"
      f"F3 胜 MA10 {(C['MA10+F3_23'] > C['MA10_23']).sum()}/{len(C)}，胜 MACD {(C['MA10+F3_23'] > C['MACD_23']).sum()}/{len(C)}，胜持有 {(C['MA10+F3_23'] > C['持有_23']).sum()}/{len(C)}")
print("\n逐只（≥3年，按 F3−MA10 年化差排序）：")
print(f"  {'代码':<7}{'名称':<14}{'起点':>11}{'持有':>8}{'MA10':>8}{'+F3':>8}{'MACD':>8}{'F3回撤':>8}{'MA10回撤':>9}")
for _, r in L.assign(x=L['MA10+F3'] - L['MA10']).sort_values("x", ascending=False).iterrows():
    print(f"  {r.code:<7}{str(r['name'])[:12]:<14}{str(r.start):>11}{r['持有']*100:+8.1f}{r['MA10']*100:+8.1f}{r['MA10+F3']*100:+8.1f}{r['MACD']*100:+8.1f}{r['MA10+F3_dd']*100:8.1f}{r['MA10_dd']*100:9.1f}{' ★' if r.good else ''}")
