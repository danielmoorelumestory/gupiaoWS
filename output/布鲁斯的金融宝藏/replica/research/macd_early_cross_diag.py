"""诊断（事后）：盘中触及临界价买入，确认/假信号各占多少，价格占了多少便宜，假信号亏多少。≥3年 50 只，2016 起，空仓且昨收非多头的日子。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, ema
ITEMS = json.load(open("data/page_etfs_plus.json")); AF, AS = 2 / 13, 2 / 27; R = []
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); fac = c / d.close.values; o, h, l = d.open.values * fac, d.high.values * fac, d.low.values * fac
    ef, es = ema(c, AF), ema(c, AS); dif = ef - es; dea = ema(dif, .2); m = dif > dea
    ps = np.r_[np.nan, (dea[:-1] - (1 - AF) * ef[:-1] + (1 - AS) * es[:-1]) / (AF - AS)]
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04")))
    if (d.index[-1] - d.index[i0]).days < 3 * 365.25: continue
    for k in range(i0, len(c) - 1):
        if not m[k - 1] and h[k] >= ps[k]:
            fill = max(o[k], ps[k]); R.append(dict(ok=bool(m[k]), need=ps[k] / c[k - 1] - 1, adv=o[k + 1] / fill - 1, fake=o[k + 1] / fill - 1))
        if m[k - 1] and l[k] <= ps[k]:
            fill = min(o[k], ps[k]); R.append(dict(ok=not m[k], need=ps[k] / c[k - 1] - 1, adv=fill / o[k + 1] - 1, fake=fill / o[k + 1] - 1, side="sell"))
X = pd.DataFrame(R); X["side"] = X.side.fillna("buy")
for s, G in X.groupby("side"):
    print(f"[{'盘中触及金叉价' if s=='buy' else '盘中触及死叉价'}] 共 {len(G)} 次，收盘确认 {G.ok.mean():.1%}，假信号 {1-G.ok.mean():.1%}；临界价距昨收中位 {G.need.median()*100:+.2f}%")
    print(f"   确认的：相比次日开盘成交，平均{'便宜' if s=='buy' else '多卖'} {G[G.ok].adv.mean()*100:+.2f}%（中位 {G[G.ok].adv.median()*100:+.2f}%）")
    print(f"   假信号：次日开盘纠正，平均 {G[~G.ok].fake.mean()*100:+.2f}%（中位 {G[~G.ok].fake.median()*100:+.2f}%），另加一来一回手续费 0.2%")
