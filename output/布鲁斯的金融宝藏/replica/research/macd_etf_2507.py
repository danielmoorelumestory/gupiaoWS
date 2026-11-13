"""所有 ETF 统一从 2025-07-07 开盘（科创半导体ETF 的起点）到 2026-11-10 对比；规则同 macd_etf.py，MACD 收 0.1%，持有 0 费。
MACD 用各自完整历史计算（起点前已充分预热），起点当天以现金开始，按前一天信号决定是否开盘买入。"""
import pandas as pd, numpy as np
exec(open("research/macd_etf.py").read().split("rows, logs = [], {}")[0])
allc = {**picked, **EXTRA}; out = []
for code, (kw, name) in allc.items():
    d, dv, mult, adj, _ = load(code); st = macd_state(adj); i0 = d.index.searchsorted(pd.Timestamp("2025-07-07"))
    h, _ = backtest(d, dv, mult, pd.Series(True, index=d.index), i0, 0.0); m, tr = backtest(d, dv, mult, st, i0, 0.001)
    out.append(dict(name=name, base=code in picked, hc=h.iloc[-1]-1, mc=m.iloc[-1]-1, hd=mdd(h), md=mdd(m), n=len(tr),
                    y25h=h.loc[:"2025-12-31"].iloc[-1]-1, y25m=m.loc[:"2025-12-31"].iloc[-1]-1,
                    y26h=h.iloc[-1]/h.loc[:"2025-12-31"].iloc[-1]-1, y26m=m.iloc[-1]/m.loc[:"2025-12-31"].iloc[-1]-1))
t = pd.DataFrame(out); t["ex"] = t.mc - t.hc; t = t.sort_values("ex", ascending=False)
print("==== 2025-07-07 → 2026-11-10（%）")
for _, r in t.iterrows():
    print(f"  {r['name']:<12} 持有 {r.hc*100:+7.1f} MACD {r.mc*100:+7.1f} 差 {r.ex*100:+7.1f} | 回撤 持有 {r.hd*100:6.1f} MACD {r.md*100:6.1f} | 笔数 {r.n:3d} | 2025下半年 {r.y25h*100:+6.1f}/{r.y25m*100:+6.1f} 2026 {r.y26h*100:+6.1f}/{r.y26m*100:+6.1f}")
b = t[t.base]
print(f"  20只：MACD 更高 {(b.ex>0).sum()}/20，差中位数 {b.ex.median()*100:+.1f}；回撤更小 {(b.md>b.hd).sum()}/20；中位数 持有 {b.hc.median()*100:+.1f} MACD {b.mc.median()*100:+.1f} 回撤 {b.hd.median()*100:.1f}/{b.md.median()*100:.1f}")
print(f"  持有涨幅与差的秩相关 {b.hc.rank().corr(b.ex.rank()):+.2f}")
