"""行业 ETF：累计涨幅与最大回撤对比（规则、数据、撮合同 macd_etf.py；MACD 收 0.1%；持有 0 费）。"""
import pandas as pd, numpy as np
exec(open("research/macd_etf.py").read().split("rows, logs = [], {}")[0])
allc = {**picked, **EXTRA}; out = []
for code, (kw, name) in allc.items():
    d, dv, mult, adj, _ = load(code); st = macd_state(adj)
    for per, start in (("上市后", d.index[60]), ("2021起", pd.Timestamp("2021-01-04"))):
        i0 = d.index.searchsorted(start)
        if i0 < 60: continue
        h, _ = backtest(d, dv, mult, pd.Series(True, index=d.index), i0, 0.0); m, tr = backtest(d, dv, mult, st, i0, 0.001)
        def dd(n):
            peak = np.maximum(n.cummax(), 1); x = n / peak - 1; t = x.idxmin(); p = n.loc[:t].idxmax() if n.loc[:t].max() > 1 else n.index[0]
            return x.min(), p.date(), t.date()
        hd, md = dd(h), dd(m)
        out.append(dict(per=per, name=name, start=d.index[i0].date(), hc=h.iloc[-1]-1, mc=m.iloc[-1]-1, hd=hd[0], hdp=f"{hd[1]}→{hd[2]}", md=md[0], mdp=f"{md[1]}→{md[2]}", base=code in picked))
t = pd.DataFrame(out)
for per in ("上市后", "2021起"):
    g = t[t.per == per].sort_values("mc", key=lambda s: -(t.loc[s.index, "mc"] - t.loc[s.index, "hc"]))
    print(f"\n==== {per}（至 2026-11-10）累计涨幅 % 与最大回撤 %")
    for _, r in g.iterrows():
        print(f"  {r['name']:<12} {r.start}  持有累计 {r.hc*100:+8.1f}  MACD累计 {r.mc*100:+8.1f}  | 持有回撤 {r.hd*100:6.1f} ({r.hdp})  MACD回撤 {r.md*100:6.1f} ({r.mdp})")
    b = g[g.base]; print(f"  20只：MACD 累计更高 {(b.mc>b.hc).sum()}/{len(b)}；回撤更小 {(b.md>b.hd).sum()}/{len(b)}；中位数 持有累计 {b.hc.median()*100:+.1f} MACD累计 {b.mc.median()*100:+.1f} 持有回撤 {b.hd.median()*100:.1f} MACD回撤 {b.md.median()*100:.1f}")
