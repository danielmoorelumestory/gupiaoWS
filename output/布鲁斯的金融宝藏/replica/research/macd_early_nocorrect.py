"""用户口径：提前成交后失败也不纠正，等下一次信号。
E1 提前买：空仓时盘中最高 ≥ P* 即按 max(开盘,P*) 买；之后只按确认死叉次日开盘卖（若收盘未金叉，继续持有，等金叉后再死叉）。
E2 提前卖：持仓时盘中最低 ≤ P* 即按 min(开盘,P*) 卖；之后只在确认金叉次日开盘买（若收盘未死叉，空仓等死叉后再金叉）。
E3 两者都用。每轮多头/空头周期内第一次触及临界价才算一次事件；之后路径与基准在下一次确认信号处汇合，
故每次事件相对基准的超额 = 提前买：o[金叉+1]/成交价-1；提前卖：成交价/o[死叉+1]-1（手续费两边相同）。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, ema, wilder
ITEMS = json.load(open("data/page_etfs_plus.json")); AF, AS, COST = 2 / 13, 2 / 27, .001
t0 = pd.read_csv("research/macd_early_cross_results.csv", dtype={"code": str}); GOOD = set(t0.loc[t0.good, "code"])
def sim(o, h, l, c, m, ps, i0, eb, es):
    nav = 1.0; hold = False; out = []; pend = "buy" if m[i0 - 1] else None
    for k in range(i0, len(c)):
        acted = False
        if pend == "buy": nav *= (1 - COST) * c[k] / o[k]; hold = True; acted = True
        elif pend == "sell": nav *= o[k] / c[k - 1] * (1 - COST); hold = False; acted = True
        elif hold and es and m[k - 1] and l[k] <= ps[k]: nav *= min(o[k], ps[k]) / c[k - 1] * (1 - COST); hold = False; acted = True
        elif hold: nav *= c[k] / c[k - 1]
        elif eb and not m[k - 1] and h[k] >= ps[k]: p = max(o[k], ps[k]); nav *= (1 - COST) * c[k] / p; hold = True; acted = True
        pend = None
        if m[k] and not m[k - 1] and not hold: pend = "buy"
        if not m[k] and m[k - 1] and hold: pend = "sell"
        if not acted and hold and not m[k] and m[k - 1]: pass
        out.append(nav)
    return np.array(out)
ann = lambda n, idx: n[-1] ** (365.25 / max(1, (idx[-1] - idx[0]).days)) - 1
mdd = lambda n: (n / np.maximum(np.maximum.accumulate(n), 1) - 1).min()
rows = []; EV = []; NAVB = {}
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); fac = c / d.close.values; o, h, l = d.open.values * fac, d.high.values * fac, d.low.values * fac
    ef, es_ = ema(c, AF), ema(c, AS); dif = ef - es_; dea = ema(dif, .2); m = dif > dea; hist = dif - dea
    prev = np.r_[np.nan, c[:-1]]; atr = wilder(np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev))))
    ps = np.r_[np.nan, (dea[:-1] - (1 - AF) * ef[:-1] + (1 - AS) * es_[:-1]) / (AF - AS)]
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); yrs = (d.index[-1] - d.index[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    r = dict(code=code, name=name, good=code in GOOD, years=yrs); j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
    for k_, (eb, es) in {"基准": (0, 0), "E1提前买": (1, 0), "E2提前卖": (0, 1), "E3都提前": (1, 1)}.items():
        n = sim(o, h, l, c, m, ps, i0, eb, es); r[k_] = ann(n, d.index[i0:]); r[k_ + "_dd"] = mdd(n)
        r[k_ + "_h1"] = ann(sim(o[:mid], h[:mid], l[:mid], c[:mid], m[:mid], ps[:mid], i0, eb, es), d.index[i0:mid]); r[k_ + "_h2"] = ann(sim(o, h, l, c, m, ps, mid, eb, es), d.index[mid:])
        if j0 >= 70: nv = sim(o, h, l, c, m, ps, j0, eb, es); r[k_ + "_B"] = ann(nv, d.index[j0:]); NAVB[(k_, code)] = pd.Series(nv, index=d.index[j0:])
    rows.append(r)
    if yrs < 3: continue
    # 事件：每个空头周期第一次触及金叉价（提前买），每个多头周期第一次触及死叉价（提前卖）
    k = i0
    while k < len(c) - 1:
        bull = m[k - 1]; trig = (l[k] <= ps[k]) if bull else (h[k] >= ps[k])
        if not trig: k += 1; continue
        fill = min(o[k], ps[k]) if bull else max(o[k], ps[k]); x = k
        while x < len(c) and m[x] == bull: x += 1  # x = 确认信号日
        if x + 1 >= len(c): break
        ex = fill / o[x + 1] - 1 if bull else o[x + 1] / fill - 1
        EV.append(dict(code=code, good=code in GOOD, date=d.index[k], side="卖" if bull else "买", ok=(x == k), early_days=x - k, ex=ex,
                       前1日涨跌=c[k-1]/c[k-2]-1, 前3日涨跌=c[k-1]/c[k-4]-1, 临界价距昨收=ps[k]/c[k-1]-1, 开盘跳空=o[k]/c[k-1]-1, 昨日柱距零=hist[k-1]/atr[k-1]))
        k = x + 1  # 下一个周期
t = pd.DataFrame(rows); t.to_csv("research/macd_early_nocorrect_results.csv", index=False); X = pd.DataFrame(EV); X.to_csv("research/macd_early_nocorrect_events.csv", index=False)
L = t[t.years >= 3]; P = lambda v: f"{v*100:+.2f}%"
for nm, G in (("≥3年 50 只", L), ("MACD优秀 17 只", L[L.good]), ("其余 33 只", L[~L.good])):
    print(f"\n[{nm}] 2016 起")
    for k_ in ("基准", "E1提前买", "E2提前卖", "E3都提前"):
        x = f"｜胜基准 {(G[k_]>G['基准']).sum()}/{len(G)} 前后半都胜 {((G[k_+'_h1']>G['基准_h1'])&(G[k_+'_h2']>G['基准_h2'])).sum()}" if k_ != "基准" else ""
        print(f"  {k_:<7} 年化均值 {P(G[k_].mean())} 中位 {P(G[k_].median())} 前半 {P(G[k_+'_h1'].mean())} 后半 {P(G[k_+'_h2'].mean())} 回撤中位 {G[k_+'_dd'].median()*100:.1f}%{x}")
B = t[t["基准_B"].notna()]; print(f"\n[2023-01-03 起固定 {len(B)} 只组合]")
for k_ in ("基准", "E1提前买", "E2提前卖", "E3都提前"):
    port = pd.DataFrame({cd: NAVB[(k_, cd)] for cd in B.code}).ffill().mean(axis=1)
    print(f"  {k_:<7} 组合年化 {P(ann(port.values, port.index))} 组合回撤 {mdd(port.values)*100:.1f}%")
for s in ("买", "卖"):
    S = X[X.side == s].copy(); okS, fl = S[S.ok], S[~S.ok]
    print(f"\n==== 提前{s}（每轮第一次触及，50 只）：{len(S)} 次，当天确认 {S.ok.mean():.0%}，相对基准平均 {S.ex.mean()*100:+.2f}%/次 中位 {S.ex.median()*100:+.2f}% ====")
    print(f"  成功（当天确认）：{len(okS)} 次 平均 {okS.ex.mean()*100:+.2f}%")
    print(f"  失败：{len(fl)} 次 平均 {fl.ex.mean()*100:+.2f}% 中位 {fl.ex.median()*100:+.2f}%，比真正信号早 中位 {fl.early_days.median():.0f} 天（75%分位 {fl.early_days.quantile(.75):.0f} 天）")
    for a, b in ((1, 1), (2, 3), (4, 10), (11, 999)):
        g = fl[(fl.early_days >= a) & (fl.early_days <= b)]; print(f"    早 {a}-{b if b<999 else '以上'} 天：{len(g)} 次 平均 {g.ex.mean()*100:+.2f}% 中位 {g.ex.median()*100:+.2f}%")
    for nm, sel in (("17 只", S.good), ("33 只", ~S.good)): print(f"  {nm}：{sel.sum()} 次 平均 {S[sel].ex.mean()*100:+.2f}%")
    print("  按特征五等分：相对基准平均/次（前段2016-20 ｜ 后段2021-）")
    for f in ("前1日涨跌", "前3日涨跌", "临界价距昨收", "开盘跳空", "昨日柱距零"):
        S["q"] = pd.qcut(S[f], 5, labels=False, duplicates="drop"); print(f"   [{f}]")
        for q, G in S.groupby("q"):
            e1, e2 = G[G.date < "2021-01-01"], G[G.date >= "2021-01-01"]; lo, hi = G[f].min(), G[f].max()
            rng = f"{lo:.2f}~{hi:.2f}" if f == "昨日柱距零" else f"{lo*100:+.1f}%~{hi*100:+.1f}%"
            print(f"     {rng:<16} n={len(G):4d} 当天确认 {G.ok.mean():.0%} 平均 {G.ex.mean()*100:+.2f}% ｜ {e1.ex.mean()*100:+.2f}% ｜ {e2.ex.mean()*100:+.2f}%")
