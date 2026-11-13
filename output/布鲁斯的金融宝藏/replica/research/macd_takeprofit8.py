"""出场改良：固定 +8% 止盈。运行前写定，跑完不改：
买入同各自基础规则（金叉次日开盘）；成本 = 买入日开盘价（复权连续价口径）；持有期间某日收盘 ≥ 成本×1.08 则次日开盘卖；
否则死叉次日开盘卖。止盈后本轮不再买回。单边 0.1%，空仓零息，口径同 macd_a20_etf.py。
基础规则：纯 MACD、MACD+A20+K−D（A20 用 codex_filter17 年度阈值，K−D≥5.3，均在金叉当天判断）。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, indicators, wilder
ITEMS = json.load(open("data/page_etfs_plus.json"))
THR = pd.read_csv("research/codex_filter17_thresholds.csv").set_index("year").amplitude20.to_dict()
res = pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}); GOOD = set(res.loc[res.good.astype(str) == "True", "code"])
ARM = 0.03
def bt(d, dv, mm, st, i0, tr=None, tag=None):
    o, c = d.open.values, d.close.values; nav = 1.0; hold = False; out = []; nb = 0; entry = 1
    for k in range(i0, len(d)):
        want = bool(st[k - 1])
        if hold: nav *= (o[k] + dv[k]) * mm[k] / c[k - 1]
        if want != hold:
            if want: entry = nav; nb += 1
            elif tr is not None: tr.append(dict(rule=tag, ret=nav * 0.999 / entry - 1))
            nav *= 0.999; hold = want
        if hold: nav *= c[k] / o[k]
        out.append(nav)
    return pd.Series(out, index=d.index[i0:]), nb
ann = lambda n: n.iloc[-1] ** (365.25 / max(1, (n.index[-1] - n.index[0]).days)) - 1
mdd = lambda n: (n / np.maximum(n.cummax(), 1) - 1).min()
K = ["持有", "MACD", "MACD+止盈", "A20K", "A20K+止盈"]; rows = []; NAVB = {}; TR = []; EV = []
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); f, m, gold, dead = indicators(d, c)
    fac = c / d.close.values; oa = d.open.values * fac
    h = d.high.values * fac; l = d.low.values * fac; prev = np.r_[np.nan, c[:-1]]
    gap = f["hist"].to_numpy() * c / wilder(np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev))))
    base_m = np.zeros(len(d), bool); be_m = np.zeros(len(d), bool); base_a = np.zeros(len(d), bool); be_a = np.zeros(len(d), bool); i = 1
    while i < len(d):
        if m[i] and not m[i - 1]:
            b = i
            while i < len(d) and m[i]: i += 1
            e = i  # 周期 b..e-1 多头
            th = THR.get(d.index[b].year, np.nan)
            ok = np.isfinite(th) and np.isfinite(gap[b]) and gap[b] >= th and f.kd.iloc[b] >= 5.3
            stop = e
            if b + 1 < len(d):
                cost = oa[b + 1]
                for k in range(b + 1, e):
                    if c[k] >= cost * 1.08: stop = k; break
            base_m[b:e] = True; be_m[b:stop] = True
            if stop < e: be_m[stop] = False
            if ok: base_a[b:e] = True; be_a[b:stop] = True
            EV.append(dict(code=code, date=d.index[b], hit=stop < e, ok=ok))
        else: i += 1
    S = {"持有": np.ones(len(d), bool), "MACD": base_m, "MACD+止盈": be_m, "A20K": base_a, "A20K+止盈": be_a}
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); yrs = (d.index[-1] - d.index[i0]).days / 365.25
    r = dict(code=code, name=name, good=code in GOOD, start=d.index[i0].date(), years=yrs); mid = i0 + (len(d) - i0) // 2
    for k, st in S.items():
        tr = []; nav, nb = bt(d, dv, mm, st, i0, tr, k); r[k] = ann(nav); r[k + "_dd"] = mdd(nav); r[k + "_n"] = nb
        r[k + "_h1"] = ann(bt(d.iloc[:mid], dv[:mid], mm[:mid], st[:mid], i0)[0]); r[k + "_h2"] = ann(bt(d, dv, mm, st, mid)[0])
        if yrs >= 3: TR += [dict(code=code, **x) for x in tr]
    j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
    if j0 >= 60:
        for k, st in S.items(): nav, _ = bt(d, dv, mm, st, j0); r[k + "_B"] = ann(nav); NAVB[(k, code)] = nav
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/macd_takeprofit8_results.csv", index=False); T = pd.DataFrame(TR)
P = lambda v: f"{v*100:+.2f}%"; L = t[t.years >= 3]
E = pd.DataFrame(EV); E = E[E.code.isin(L.code) & (E.date >= "2016-01-04")]
print(f"2016 起 {len(E)} 次金叉中，触发 +8% 止盈 {E.hit.mean():.0%}")
for nm, G in (("≥3年 50 只", L), ("MACD优秀 17 只", L[L.good]), ("其余 33 只", L[~L.good])):
    print(f"\n[{nm}] 2016 起")
    for k in K:
        x = T[(T.rule == k) & T.code.isin(G.code)].ret
        base = {"MACD+止盈": "MACD", "A20K+止盈": "A20K"}.get(k)
        cmp = f"｜胜{base} {(G[k] > G[base]).sum()}/{len(G)} 前后半都胜 {((G[k+'_h1'] > G[base+'_h1']) & (G[k+'_h2'] > G[base+'_h2'])).sum()} 回撤更小 {(G[k+'_dd'] > G[base+'_dd']).sum()}" if base else ""
        wr = f" 胜率 {(x > 0).mean():.1%}（亏损≤0.5%的算平 {(x > -0.005).mean():.1%}） 每笔均 {x.mean()*100:+.2f}% 赚均 {x[x>0].mean()*100:+.2f}% 亏均 {x[x<=0].mean()*100:+.2f}%" if k != "持有" else ""
        print(f"  {k:<9} 年化均值 {P(G[k].mean())} 中位 {P(G[k].median())} 回撤中位 {G[k+'_dd'].median()*100:.1f}% 买入中位 {G[k+'_n'].median():.0f}{wr}{cmp}")
B = t[t["MACD_B"].notna()]
print(f"\n[2023-01-03 起固定 {len(B)} 只]")
for k in K:
    port = pd.DataFrame({c: NAVB[(k, c)] for c in B.code}).ffill().mean(axis=1); ys = []
    for y in range(2023, 2027):
        prev = port[port.index.year < y].iloc[-1] if (port.index.year < y).any() else 1; ys.append(port[port.index.year == y].iloc[-1] / prev - 1)
    base = {"MACD+止盈": "MACD", "A20K+止盈": "A20K"}.get(k)
    print(f"  {k:<9} 年化均值 {P(B[k+'_B'].mean())} 组合年化 {P(ann(port))} 组合回撤 {mdd(port)*100:.2f}% " + (f"胜{base} {(B[k+'_B'] > B[base+'_B']).sum()}/{len(B)} " if base else "") + "逐年 " + " ".join(f"{y*100:+.1f}" for y in ys))
G = L[L.good].set_index("code").loc[["515790","159851","562500","512480","588200","513130","512200","159852","516160","512880","513090","159667","159792","159883","512070","159865","159869"]]
print("\n17 只（年化 MACD / +止盈 / A20K / A20K+止盈；回撤 MACD / +止盈）")
for c, r in G.iterrows(): print(f"  {c} {r['name'][:8]:<9}" + " ".join(f"{r[k]*100:+6.1f}" for k in K[1:]) + f"   {r.MACD_dd*100:6.1f} {r['MACD+止盈_dd']*100:6.1f}")
