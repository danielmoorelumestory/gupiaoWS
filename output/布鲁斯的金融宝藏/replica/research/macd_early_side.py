"""提前买 / 提前卖分开统计（诊断，口径同 macd_early_cross.py）。
每次盘中触及临界价：确认 → 相对次日开盘成交的价差收益；假信号 → 次日开盘纠正的价差损失 - 来回手续费 0.2%。
净效果/次 = 全部触发的平均。另按组、按年统计；并汇总 R3/R4 相对基准的年化差。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, ema
ITEMS = json.load(open("data/page_etfs_plus.json")); AF, AS = 2 / 13, 2 / 27; R = []
t = pd.read_csv("research/macd_early_cross_results.csv", dtype={"code": str}); GOOD = set(t.loc[t.good, "code"])
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); fac = c / d.close.values; o, h, l = d.open.values * fac, d.high.values * fac, d.low.values * fac
    ef, es = ema(c, AF), ema(c, AS); dif = ef - es; dea = ema(dif, .2); m = dif > dea
    ps = np.r_[np.nan, (dea[:-1] - (1 - AF) * ef[:-1] + (1 - AS) * es[:-1]) / (AF - AS)]
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); yrs = (d.index[-1] - d.index[i0]).days / 365.25
    if yrs < 3: continue
    for k in range(i0, len(c) - 1):
        for side, cond, fill, ok in (("买", not m[k - 1] and h[k] >= ps[k], max(o[k], ps[k]), m[k]), ("卖", m[k - 1] and l[k] <= ps[k], min(o[k], ps[k]), not m[k])):
            if not cond: continue
            g = o[k + 1] / fill - 1 if side == "买" else fill / o[k + 1] - 1
            R.append(dict(code=code, good=code in GOOD, yrs=yrs, year=d.index[k].year, side=side, ok=bool(ok), g=g, net=g if ok else g - .002,
                          gapopen=(o[k] >= ps[k]) if side == "买" else (o[k] <= ps[k])))
X = pd.DataFrame(R); X.to_csv("research/macd_early_side_events.csv", index=False)
def show(G, label):
    n_y = G.groupby("code").yrs.first().sum()
    ok, fk = G[G.ok], G[~G.ok]
    print(f"  {label}：每只每年触发 {len(G)/n_y:.1f} 次｜确认 {G.ok.mean():.0%} 平均赚 {ok.g.mean()*100:+.2f}%｜假信号 {1-G.ok.mean():.0%} 平均亏 {fk.net.mean()*100:+.2f}%（含手续费）｜净 {G.net.mean()*100:+.3f}%/次，每年合计 {G.net.sum()/n_y*100:+.2f}%")
for nm, sel in (("≥3年 50 只", X.code.notna()), ("MACD优秀 17 只", X.good), ("其余 33 只", ~X.good)):
    print(f"\n[{nm}]")
    for s in ("买", "卖"): show(X[sel & (X.side == s)], f"提前{s}")
    L = t[(t.years >= 3) & (t.good if nm.startswith("MACD") else (~t.good if nm.startswith("其余") else True))]
    for k, s in (("R3只提前买", "买"), ("R4只提前卖", "卖")):
        print(f"  {k}：年化 {L['基准'].mean()*100:+.2f}% → {L[k].mean()*100:+.2f}%（差 {(L[k]-L['基准']).mean()*100:+.2f}），回撤中位 {L['基准_dd'].median()*100:.1f}% → {L[k+'_dd'].median()*100:.1f}%，胜基准 {(L[k]>L['基准']).sum()}/{len(L)}")
print("\n[开盘就已越过临界价 vs 盘中才碰到]（50 只）")
for s in ("买", "卖"):
    for gp, G in X[X.side == s].groupby("gapopen"):
        print(f"  提前{s}·{'开盘已越过' if gp else '盘中碰到'}：{len(G)} 次 确认 {G.ok.mean():.0%} 净 {G.net.mean()*100:+.3f}%/次")
print("\n[逐年 净收益/次，50 只]  年份: 提前买 / 提前卖")
for y, G in X.groupby("year"): print(f"  {y}: {G[G.side=='买'].net.mean()*100:+.3f}% / {G[G.side=='卖'].net.mean()*100:+.3f}%")
