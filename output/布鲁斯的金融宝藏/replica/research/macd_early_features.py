"""诊断：盘中触及临界价（提前买/提前卖）成功与失败前的特征。成功=当天收盘确认（金叉/死叉成立）。
净收益/次口径同 macd_early_side.py（相对次日开盘成交，假信号再扣 0.2%）。全是事后分档，前后两段（2016-2020 / 2021-）分开看稳定性。
特征（均在触发前或开盘时可知）：前1日涨跌、前3日涨跌、前5日涨跌、临界价距昨收、开盘跳空、昨日柱距零(按ATR)、柱子近3日变化。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, ema, wilder
ITEMS = json.load(open("data/page_etfs_plus.json")); AF, AS = 2 / 13, 2 / 27; R = []
t = pd.read_csv("research/macd_early_cross_results.csv", dtype={"code": str}); GOOD = set(t.loc[t.good, "code"])
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); fac = c / d.close.values; o, h, l = d.open.values * fac, d.high.values * fac, d.low.values * fac
    ef, es = ema(c, AF), ema(c, AS); dif = ef - es; dea = ema(dif, .2); m = dif > dea; hist = dif - dea
    prev = np.r_[np.nan, c[:-1]]; atr = wilder(np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev))))

    ps = np.r_[np.nan, (dea[:-1] - (1 - AF) * ef[:-1] + (1 - AS) * es[:-1]) / (AF - AS)]
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04")))
    if (d.index[-1] - d.index[i0]).days < 3 * 365.25: continue
    for k in range(i0, len(c) - 1):
        for side, cond, fill, ok in (("买", not m[k - 1] and h[k] >= ps[k], max(o[k], ps[k]), m[k]), ("卖", m[k - 1] and l[k] <= ps[k], min(o[k], ps[k]), not m[k])):
            if not cond: continue
            g = o[k + 1] / fill - 1 if side == "买" else fill / o[k + 1] - 1
            R.append(dict(code=code, good=code in GOOD, date=d.index[k], side=side, ok=bool(ok), net=g if ok else g - .002,
                          前1日涨跌=c[k-1]/c[k-2]-1, 前3日涨跌=c[k-1]/c[k-4]-1, 前5日涨跌=c[k-1]/c[k-6]-1, 临界价距昨收=ps[k]/c[k-1]-1,
                          开盘跳空=o[k]/c[k-1]-1, 昨日柱距零=hist[k-1]/atr[k-1], 柱3日变化=(hist[k-1]-hist[k-4])/atr[k-1]))
X = pd.DataFrame(R); X.to_csv("research/macd_early_features_events.csv", index=False)
F = ["前1日涨跌", "前3日涨跌", "前5日涨跌", "临界价距昨收", "开盘跳空", "昨日柱距零", "柱3日变化"]
PCT = {"昨日柱距零", "柱3日变化"}
for s in ("买", "卖"):
    S = X[X.side == s].copy(); early = S.date < "2021-01-01"
    print(f"\n==== 提前{s}：{len(S)} 次，成功 {S.ok.mean():.0%}，净 {S.net.mean()*100:+.3f}%/次 ====")
    print("  成功 vs 失败 的特征中位数：")
    for f in F:
        a, b = S[S.ok][f].median(), S[~S.ok][f].median(); fm = (lambda v: f"{v:.2f}") if f in PCT else (lambda v: f"{v*100:+.2f}%")
        print(f"    {f:<7} 成功 {fm(a):>8}  失败 {fm(b):>8}")
    print("  按特征五等分（分位点用全部事件）：成功率 / 净收益每次 ｜ 前段2016-20 成功率/净 ｜ 后段2021- 成功率/净")
    for f in F:
        S["q"] = pd.qcut(S[f], 5, labels=False, duplicates="drop"); edges = S.groupby("q")[f].agg(["min", "max"])
        print(f"   [{f}]")
        for q, G in S.groupby("q"):
            e1, e2 = G[G.date < "2021-01-01"], G[G.date >= "2021-01-01"]; lo, hi = edges.loc[q]
            rng = f"{lo:.2f}~{hi:.2f}" if f in PCT else f"{lo*100:+.1f}%~{hi*100:+.1f}%"
            print(f"     {rng:<16} n={len(G):4d} 成功 {G.ok.mean():.0%} 净 {G.net.mean()*100:+.3f}% ｜ {e1.ok.mean():.0%} {e1.net.mean()*100:+.3f}% ｜ {e2.ok.mean():.0%} {e2.net.mean()*100:+.3f}%")
