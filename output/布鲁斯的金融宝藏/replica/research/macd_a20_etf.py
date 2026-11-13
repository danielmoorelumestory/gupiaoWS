"""63 只页面 ETF：MACD、MACD+A20 金叉间距、MACD+金叉日 K−D≥5.3、两者同时满足（后加）、一直持有。运行前写定：
价格与指标用 codex_macd_common（比例除权连续价、Wilder ATR14、KDJ 9,3,3；早于首条行情的拆分不施加）。
A20：金叉当天 (DIF−DEA)/ATR14 ≥ 金叉所在年份阈值（codex_filter17_thresholds.csv 的 amplitude20，ETF 池前 3 年已结束交易 20% 分位）；无阈值年份视为不通过。
只在金叉当天决定该轮是否入场，通过则次日开盘买，死叉次日开盘卖，不补买。成交：未复权开盘价，分红/拆分归属前日持仓，单边 0.1%，空仓零息。
区间 A：max(上市后第 70 个交易日, 2016-01-04) 至 2026-11-10，汇总回测期 ≥3 年；区间 B：2023-01-03 起、当时已预热的固定池，另给初始等额组合。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, indicators, wilder
ITEMS = json.load(open("data/page_etfs_plus.json"))
THR = pd.read_csv("research/codex_filter17_thresholds.csv").set_index("year").amplitude20.to_dict()
res = pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}); GOOD = set(res.loc[res.good.astype(str) == "True", "code"])
def bt(d, dv, mm, st, i0, i1=None):
    o, c = d.open.values, d.close.values; i1 = len(d) if i1 is None else i1; nav = 1.0; hold = False; out = []; nb = 0
    for k in range(i0, i1):
        want = bool(st[k - 1])
        if hold: nav *= (o[k] + dv[k]) * mm[k] / c[k - 1]
        if want != hold: nav *= 0.999; hold = want; nb += want
        if hold: nav *= c[k] / o[k]
        out.append(nav)
    return pd.Series(out, index=d.index[i0:i1]), nb
ann = lambda n: n.iloc[-1] ** (365.25 / max(1, (n.index[-1] - n.index[0]).days)) - 1
mdd = lambda n: (n / np.maximum(n.cummax(), 1) - 1).min()
rows, NAVB = [], {}
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); f, m, gold, dead = indicators(d, c)
    fac = c / d.close.to_numpy(); h = d.high.to_numpy() * fac; l = d.low.to_numpy() * fac; prev = np.r_[np.nan, c[:-1]]
    gap = f["hist"].to_numpy() * c / wilder(np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev))))
    pa = np.zeros(len(d), bool); pk = np.zeros(len(d), bool); nx = 0; npass = 0
    i = 1
    while i < len(d):
        if m[i] and not m[i - 1]:
            b = i
            while i < len(d) and m[i]: i += 1
            th = THR.get(d.index[b].year, np.nan)
            pa[b:i] = np.isfinite(th) and np.isfinite(gap[b]) and gap[b] >= th; pk[b:i] = f.kd.iloc[b] >= 5.3
        else: i += 1
    S = {"持有": np.ones(len(d), bool), "MACD": m, "A20": m & pa, "K−D": m & pk, "A20+K−D": m & pa & pk}
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04")))
    r = dict(code=code, name=name, grp=grp, good=code in GOOD, start=d.index[i0].date(), years=(d.index[-1] - d.index[i0]).days / 365.25)
    mid = i0 + (len(d) - i0) // 2
    for k, st in S.items():
        nav, nb = bt(d, dv, mm, st, i0); r[k] = ann(nav); r[k + "_dd"] = mdd(nav); r[k + "_n"] = nb
        r[k + "_h1"] = ann(bt(d, dv, mm, st, i0, mid)[0]); r[k + "_h2"] = ann(bt(d, dv, mm, st, mid)[0])
    j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
    if j0 >= 60:
        for k, st in S.items():
            nav, _ = bt(d, dv, mm, st, j0); r[k + "_B"] = ann(nav); r[k + "_Bdd"] = mdd(nav); NAVB[(k, code)] = nav
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/macd_a20_etf_results.csv", index=False)
P = lambda v: f"{v*100:+.2f}%"
L = t[t.years >= 3]
print(f"区间 A：2016 年起（或上市后第 70 个交易日），≥3 年 {len(L)} 只（MACD优秀 {L.good.sum()} 只）")
print(f"{'策略':<6}{'年化均值':>9}{'年化中位':>9}{'回撤中位':>9}{'买入次数中位':>9}")
for k in ("持有", "MACD", "A20", "K−D"): print(f"{k:<6}{P(L[k].mean()):>10}{P(L[k].median()):>10}{L[k+'_dd'].median()*100:>9.1f}%{L[k+'_n'].median():>9.0f}")
def cmp(a, b, G, tag=""):
    print(f"  {tag}{a} 对 {b}：年化胜 {(G[a] > G[b]).sum()}/{len(G)}，平均差 {P((G[a]-G[b]).mean())}，中位差 {P((G[a]-G[b]).median())}；前后半都胜 {((G[a+'_h1'] > G[b+'_h1']) & (G[a+'_h2'] > G[b+'_h2'])).sum()}；回撤更小 {(G[a+'_dd'] > G[b+'_dd']).sum()}")
for a, b in (("A20", "MACD"), ("K−D", "MACD"), ("A20", "持有"), ("MACD", "持有")): cmp(a, b, L)
for nm, G in (("MACD优秀", L[L.good]), ("其余", L[~L.good])):
    print(f"[{nm} {len(G)} 只] 年化均值 持有 {P(G['持有'].mean())} MACD {P(G['MACD'].mean())} A20 {P(G['A20'].mean())} K−D {P(G['K−D'].mean())}")
    cmp("A20", "MACD", G, "  "); cmp("K−D", "MACD", G, "  ")
B = t[t["MACD_B"].notna()]
print(f"\n区间 B：2023-01-03 起固定 {len(B)} 只")
for k in ("持有", "MACD", "A20", "K−D"):
    port = pd.DataFrame({c: NAVB[(k, c)] for c in B.code}).ffill().mean(axis=1)
    print(f"  {k:<4} 年化均值 {P(B[k+'_B'].mean())} 中位 {P(B[k+'_B'].median())} 回撤中位 {B[k+'_Bdd'].median()*100:.1f}%｜初始等额组合 年化 {P(ann(port))} 最大回撤 {mdd(port)*100:.2f}%")
    if k != "持有": print(f"       胜 MACD {(B[k+'_B'] > B['MACD_B']).sum()}/{len(B)}" if k != "MACD" else "", end="\n" if k != "MACD" else "")
yr = {k: pd.DataFrame({c: NAVB[(k, c)] for c in B.code}).ffill().mean(axis=1) for k in ("MACD", "A20", "K−D")}
for y in range(2023, 2027):
    g = {k: (v[v.index.year == y].iloc[-1] / (v[v.index.year < y].iloc[-1] if (v.index.year < y).any() else 1) - 1) for k, v in yr.items()}
    print(f"  {y} 组合收益 MACD {P(g['MACD'])}  A20 {P(g['A20'])}（差 {P(g['A20']-g['MACD'])}）  K−D {P(g['K−D'])}（差 {P(g['K−D']-g['MACD'])}）")
print("\n逐只（区间 A，≥3年，按 A20−MACD 排序）")
for _, r in L.assign(x=L.A20 - L.MACD).sort_values("x", ascending=False).iterrows():
    print(f"  {r.code} {str(r['name'])[:10]:<12}{str(r.start):>11} 持有{r['持有']*100:+7.1f} MACD{r.MACD*100:+7.1f} A20{r.A20*100:+7.1f} K−D{r['K−D']*100:+7.1f}  回撤 MACD{r.MACD_dd*100:6.1f} A20{r.A20_dd*100:6.1f}{' ★' if r.good else ''}")
