"""【第二轮，用户提出 X2，运行前写定】X2 高位后破位：持有中 V 曾 >70（买入日起算）之后，收盘跌破 10 日线（复权收盘 < 10 日均线）或 MACD 死叉，先到者当天尾盘卖；
V 未曾 >70 时只按 MACD 死叉卖。T+1 同上。另列 E2+X2。
MACD × 同花顺波段顶底（V=100*SUM(MAX(ΔC,0),13)/SUM(|ΔC|,13)，阈值 30/70 原样，不调参）。运行前写定，跑完不改。
基准：MACD 金叉次日开盘买，死叉当天尾盘（收盘价）卖。T+1：买入当天不能卖，若卖出信号落在买入当天，顺延到次日开盘卖。
组合（只用 V 的原生阈值 30/70 与原生周期 13）：
 E1 低位金叉：金叉当天及之前 13 个交易日内，V 曾 <30 才买（超卖后的金叉）。
 E2 不追高：金叉当天 V >70 则跳过本轮。
 X1 高位离场：持有中 V 从 >70 回落到 ≤70，当天尾盘卖；本轮不再买回，等下一次金叉。
 组合 E1+X1、E2+X1。另列 MACD 次日开盘卖作参照。
单边 0.1%，复权连续价，空仓零收益；2016 起（或上市第 70 日），≥3 年的 50 只；17/33 分组与 2023 起 45 只组合同前。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, ema
ITEMS = json.load(open("data/page_etfs_plus.json")); COST = .001
t0 = pd.read_csv("research/macd_early_cross_results.csv", dtype={"code": str}); GOOD = set(t0.loc[t0.good, "code"])
def band(c, n=13):
    dc = np.r_[np.nan, np.diff(c)]; up = pd.Series(np.maximum(dc, 0)).rolling(n).sum().values; ab = pd.Series(np.abs(dc)).rolling(n).sum().values
    with np.errstate(invalid="ignore", divide="ignore"): return np.where(ab > 0, 100 * up / ab, np.nan)
def sim(o, c, st, i0, cs, tr=None):
    """st[k]=k 日收盘后的目标仓位。cs：卖出按当天收盘；T+1 冲突时顺延次日开盘。"""
    nav = 1.0; hold = False; out = []; pend = "buy" if st[i0 - 1] else None; ent = 1; bday = -1; nb = 0
    for k in range(i0, len(c)):
        if pend == "buy" and not hold: nav *= 1 - COST; ent = nav; nav *= c[k] / o[k]; hold = True; bday = k; nb += 1
        elif pend == "sell" and hold:
            nav *= o[k] / c[k - 1] * (1 - COST); hold = False
            if tr is not None: tr.append(nav / ent - 1)
        elif hold: nav *= c[k] / c[k - 1]
        pend = None
        if st[k] and not hold: pend = "buy"
        elif not st[k] and hold:
            if cs and bday != k:
                nav *= 1 - COST; hold = False
                if tr is not None: tr.append(nav / ent - 1)
            else: pend = "sell"
        out.append(nav)
    return np.array(out), nb
ann = lambda n, idx: n[-1] ** (365.25 / max(1, (idx[-1] - idx[0]).days)) - 1
mdd = lambda n: (n / np.maximum(np.maximum.accumulate(n), 1) - 1).min()
R = {"MACD次开卖": ("base", 0), "MACD尾盘卖": ("base", 1), "E1低位金叉": ("e1", 1), "E2不追高": ("e2", 1), "X1高位离场": ("x1", 1), "E1+X1": ("e1x1", 1), "E2+X1": ("e2x1", 1), "X2高位破位": ("x2", 1), "E2+X2": ("e2x2", 1)}
rows = []; NAVB = {}; TR = {k: [] for k in R}; T1 = 0; NCY = 0; VG = []; X2N = []
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); o = d.open.values * c / d.close.values
    dif = ema(c, 2 / 13) - ema(c, 2 / 27); m = dif > ema(dif, .2); V = band(c); ma10 = pd.Series(c).rolling(10).mean().values
    S = {k: np.zeros(len(c), bool) for k in ("base", "e1", "e2", "x1", "e1x1", "e2x1", "x2", "e2x2")}; i = 1
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); yrs = (d.index[-1] - d.index[i0]).days / 365.25
    while i < len(c):
        if m[i] and not m[i - 1]:
            b = i
            while i < len(c) and m[i]: i += 1
            e = i
            if b >= i0 and e == b + 1: T1 += 1
            if b >= i0: NCY += 1
            low = np.nanmin(V[max(0, b - 13):b + 1]) < 30 if np.isfinite(V[max(0, b - 13):b + 1]).any() else False
            hot = np.isfinite(V[b]) and V[b] > 70
            stop = e
            for k in range(b + 2, e):  # 买入日 b+1 当天不能卖；最早 b+2 收盘
                if V[k - 1] > 70 and V[k] <= 70: stop = k; break
            stop2 = e; armed = False
            for k in range(b + 1, e):
                armed = armed or (np.isfinite(V[k]) and V[k] > 70)
                if armed and k >= b + 2 and c[k] < ma10[k]: stop2 = k; break
            S["x2"][b:stop2] = True
            if not hot: S["e2x2"][b:stop2] = True
            if b >= i0 and yrs >= 3: X2N.append((stop2 < e, armed))
            S["base"][b:e] = True; S["x1"][b:stop] = True
            if low: S["e1"][b:e] = True; S["e1x1"][b:stop] = True
            if not hot: S["e2"][b:e] = True; S["e2x1"][b:stop] = True
            if b >= i0 and yrs >= 3: VG.append(dict(code=code, good=code in GOOD, V=V[b], low=low, hot=hot, xs=stop < e, ret=c[e - 1 if e < len(c) else len(c) - 1] / o[min(b + 1, len(c) - 1)] - 1 if e < len(c) else np.nan))
        else: i += 1
    mid = i0 + (len(d) - i0) // 2; r = dict(code=code, name=name, good=code in GOOD, years=yrs); j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
    for k_, (s, cs) in R.items():
        tr = []; n, nb = sim(o, c, S[s], i0, cs, tr); r[k_] = ann(n, d.index[i0:]); r[k_ + "_dd"] = mdd(n); r[k_ + "_n"] = nb
        r[k_ + "_h1"] = ann(sim(o[:mid], c[:mid], S[s][:mid], i0, cs)[0], d.index[i0:mid]); r[k_ + "_h2"] = ann(sim(o, c, S[s], mid, cs)[0], d.index[mid:])
        if yrs >= 3: TR[k_] += [(code, x) for x in tr]
        if j0 >= 70: nv = sim(o, c, S[s], j0, cs)[0]; r[k_ + "_B"] = ann(nv, d.index[j0:]); NAVB[(k_, code)] = pd.Series(nv, index=d.index[j0:])
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/macd_band_combo2_results.csv", index=False); L = t[t.years >= 3]; P = lambda v: f"{v*100:+.2f}%"
print(f"T+1 检查：2016 起 {NCY} 个金叉周期中，{T1} 个是金叉次日即死叉（买入当天就该卖），已顺延到再下一日开盘卖")
G0 = pd.DataFrame(VG); print(f"X2：本轮曾>70 {np.mean([a for _, a in X2N]):.0%}，在死叉前因跌破10日线卖出 {np.mean([x for x, _ in X2N]):.0%}"); print(f"金叉当天 V：中位 {G0.V.median():.1f}；满足 E1（13 日内曾<30）{G0.low.mean():.0%}；E2 跳过（V>70）{G0.hot.mean():.0%}；X1 在死叉前触发 {G0["xs"].mean():.0%}")
for nm, G in (("≥3年 50 只", L), ("MACD优秀 17 只", L[L.good]), ("其余 33 只", L[~L.good])):
    print(f"\n[{nm}] 2016 起")
    for k_ in R:
        x = np.array([v for cd, v in TR[k_] if cd in set(G.code)]); b = "MACD尾盘卖"
        cmp = f"｜胜尾盘卖基准 {(G[k_]>G[b]).sum()}/{len(G)} 前后半都胜 {((G[k_+'_h1']>G[b+'_h1'])&(G[k_+'_h2']>G[b+'_h2'])).sum()}" if k_ not in (b, "MACD次开卖") else ""
        print(f"  {k_:<8} 年化均值 {P(G[k_].mean())} 中位 {P(G[k_].median())} 前半 {P(G[k_+'_h1'].mean())} 后半 {P(G[k_+'_h2'].mean())} 回撤中位 {G[k_+'_dd'].median()*100:.1f}% 买入中位 {G[k_+'_n'].median():.0f} 胜率 {(x>0).mean():.1%} 每笔 {x.mean()*100:+.2f}%{cmp}")
B = t[t["MACD尾盘卖_B"].notna()]; print(f"\n[2023-01-03 起固定 {len(B)} 只组合]")
for k_ in R:
    port = pd.DataFrame({cd: NAVB[(k_, cd)] for cd in B.code}).ffill().mean(axis=1); ys = []
    for yy in range(2023, 2027):
        pv = port[port.index.year < yy].iloc[-1] if (port.index.year < yy).any() else 1; ys.append(port[port.index.year == yy].iloc[-1] / pv - 1)
    print(f"  {k_:<8} 组合年化 {P(ann(port.values, port.index))} 组合回撤 {mdd(port.values)*100:.1f}% 逐年 " + " ".join(f"{v*100:+.1f}" for v in ys))
G = L[L.good].set_index("code"); print("\n17 只年化（" + " / ".join(R) + "）")
for cd, r in G.iterrows(): print(f"  {cd} {r['name'][:7]:<8}" + " ".join(f"{r[k]*100:+6.1f}" for k in R))
