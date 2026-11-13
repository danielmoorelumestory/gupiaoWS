"""出场改良：止损线放在成本下方 3%（T+1：买入日收盘起判断，最早次日开盘卖）。运行前写定，跑完不改：
A=C1：收盘 ≥ 成本×1.05 之前，任一日收盘 ≤ 成本×0.97 → 次日开盘卖，达到 +5% 后止损失效、等死叉；
B=C2：整个持有期任一日收盘 ≤ 成本×0.97 → 次日开盘卖（固定 −3% 止损对照）。止损后本轮不再买回。以下为原模板说明：
买入同各自基础规则（金叉次日开盘）；成本 = 买入日开盘价（复权连续价口径）；持有期间某日收盘 ≥ 成本×1.03 后进入保本状态，
此后收盘 ≤ 成本 则次日开盘卖；否则死叉次日开盘卖。保本卖出后本轮不再买回。单边 0.1%，空仓零息，口径同 macd_a20_etf.py。
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
K = ["持有", "MACD", "MACD+A", "MACD+B", "A20K", "A20K+A", "A20K+B"]; rows = []; NAVB = {}; TR = []; EV = []
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); f, m, gold, dead = indicators(d, c)
    fac = c / d.close.values; oa = d.open.values * fac
    h = d.high.values * fac; l = d.low.values * fac; prev = np.r_[np.nan, c[:-1]]
    gap = f["hist"].to_numpy() * c / wilder(np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev))))
    base_m = np.zeros(len(d), bool); base_a = np.zeros(len(d), bool); SM = {v: np.zeros(len(d), bool) for v in 'AB'}; SA = {v: np.zeros(len(d), bool) for v in 'AB'}; i = 1
    while i < len(d):
        if m[i] and not m[i - 1]:
            b = i
            while i < len(d) and m[i]: i += 1
            e = i  # 周期 b..e-1 多头
            th = THR.get(d.index[b].year, np.nan)
            ok = np.isfinite(th) and np.isfinite(gap[b]) and gap[b] >= th and f.kd.iloc[b] >= 5.3
            stops = {}
            for var in ("A", "B"):
                stop = e
                if b + 1 < len(d):
                    cost = oa[b + 1]; up = False
                    for k in range(b + 1, e):
                        if var == "A" and c[k] >= cost * 1.05: break
                        if c[k] <= cost * 0.97: stop = k; break
                stops[var] = stop
            base_m[b:e] = True
            for var, stop in stops.items():
                SM[var][b:stop] = True
                if ok: SA[var][b:stop] = True
            if ok: base_a[b:e] = True
            stop = stops["A"]
            EV.append(dict(code=code, date=d.index[b], hit=stops["A"] < e, hitB=stops["B"] < e, ok=ok))
        else: i += 1
    S = {"持有": np.ones(len(d), bool), "MACD": base_m, "MACD+A": SM["A"], "MACD+B": SM["B"], "A20K": base_a, "A20K+A": SA["A"], "A20K+B": SA["B"]}
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
t = pd.DataFrame(rows); t.to_csv("research/macd_stop3below_results.csv", index=False); T = pd.DataFrame(TR)
P = lambda v: f"{v*100:+.2f}%"; L = t[t.years >= 3]
E = pd.DataFrame(EV); E = E[E.code.isin(L.code) & (E.date >= "2016-01-04")]
print(f"2016 起 {len(E)} 次金叉中，触发止损：A {E.hit.mean():.0%}，B {E.hitB.mean():.0%}")
for nm, G in (("≥3年 50 只", L), ("MACD优秀 17 只", L[L.good]), ("其余 33 只", L[~L.good])):
    print(f"\n[{nm}] 2016 起")
    for k in K:
        x = T[(T.rule == k) & T.code.isin(G.code)].ret
        base = {"MACD+A": "MACD", "MACD+B": "MACD", "A20K+A": "A20K", "A20K+B": "A20K"}.get(k)
        cmp = f"｜胜{base} {(G[k] > G[base]).sum()}/{len(G)} 前后半都胜 {((G[k+'_h1'] > G[base+'_h1']) & (G[k+'_h2'] > G[base+'_h2'])).sum()} 回撤更小 {(G[k+'_dd'] > G[base+'_dd']).sum()}" if base else ""
        wr = f" 胜率 {(x > 0).mean():.1%}（亏损≤0.5%的算平 {(x > -0.005).mean():.1%}） 每笔均 {x.mean()*100:+.2f}% 赚均 {x[x>0].mean()*100:+.2f}% 亏均 {x[x<=0].mean()*100:+.2f}%" if k != "持有" else ""
        print(f"  {k:<9} 年化均值 {P(G[k].mean())} 中位 {P(G[k].median())} 回撤中位 {G[k+'_dd'].median()*100:.1f}% 买入中位 {G[k+'_n'].median():.0f}{wr}{cmp}")
B = t[t["MACD_B"].notna()]
print(f"\n[2023-01-03 起固定 {len(B)} 只]")
for k in K:
    port = pd.DataFrame({c: NAVB[(k, c)] for c in B.code}).ffill().mean(axis=1); ys = []
    for y in range(2023, 2027):
        prev = port[port.index.year < y].iloc[-1] if (port.index.year < y).any() else 1; ys.append(port[port.index.year == y].iloc[-1] / prev - 1)
    base = {"MACD+A": "MACD", "MACD+B": "MACD", "A20K+A": "A20K", "A20K+B": "A20K"}.get(k)
    print(f"  {k:<9} 年化均值 {P(B[k+'_B'].mean())} 组合年化 {P(ann(port))} 组合回撤 {mdd(port)*100:.2f}% " + (f"胜{base} {(B[k+'_B'] > B[base+'_B']).sum()}/{len(B)} " if base else "") + "逐年 " + " ".join(f"{y*100:+.1f}" for y in ys))
G = L[L.good].set_index("code").loc[["515790","159851","562500","512480","588200","513130","512200","159852","516160","512880","513090","159667","159792","159883","512070","159865","159869"]]
print("\n17 只（年化 MACD / +A / +B / A20K / A20K+A / A20K+B；回撤 MACD / +A / +B）")
for c, r in G.iterrows(): print(f"  {c} {r['name'][:8]:<9}" + " ".join(f"{r[k]*100:+6.1f}" for k in K[1:]) + f"   {r.MACD_dd*100:6.1f} {r['MACD+A_dd']*100:6.1f} {r['MACD+B_dd']*100:6.1f}")
