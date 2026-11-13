"""汇总 MACD / A20 / K−D / A20+K−D（读 macd_a20_etf_results.csv 与组合净值需重跑主脚本，这里只做横截面与组合汇总）。"""
import sys, numpy as np, pandas as pd
sys.argv = ["x"]; import io, contextlib
with contextlib.redirect_stdout(io.StringIO()): exec(open("research/macd_a20_etf.py").read())
K = ["持有", "MACD", "A20", "K−D", "A20+K−D"]; P = lambda v: f"{v*100:+.2f}%"
for nm, G in (("≥3年 50 只", L), ("MACD优秀 17 只", L[L.good]), ("其余 33 只", L[~L.good])):
    print(f"\n[{nm}] 区间 A")
    for k in K: print(f"  {k:<8} 年化均值 {P(G[k].mean())} 中位 {P(G[k].median())} 回撤中位 {G[k+'_dd'].median()*100:.1f}% 买入中位 {G[k+'_n'].median():.0f}" + ("" if k in ("持有", "MACD") else f"｜胜MACD {(G[k] > G['MACD']).sum()}/{len(G)} 前后半都胜 {((G[k+'_h1'] > G['MACD_h1']) & (G[k+'_h2'] > G['MACD_h2'])).sum()} 回撤更小 {(G[k+'_dd'] > G['MACD_dd']).sum()}"))
B = t[t["MACD_B"].notna()]
for nm, G in (("2023起 45 只", B), ("2023起 MACD优秀", B[B.good])):
    print(f"\n[{nm} {len(G)} 只] 区间 B")
    for k in K:
        port = pd.DataFrame({c: NAVB[(k, c)] for c in G.code}).ffill().mean(axis=1)
        yrs = []
        for y in range(2023, 2027):
            prev = port[port.index.year < y].iloc[-1] if (port.index.year < y).any() else 1
            yrs.append(port[port.index.year == y].iloc[-1] / prev - 1)
        print(f"  {k:<8} 年化均值 {P(G[k+'_B'].mean())} 组合年化 {P(ann(port))} 组合回撤 {mdd(port)*100:.2f}% 胜MACD {(G[k+'_B'] > G['MACD_B']).sum() if k != 'MACD' else '-'} 逐年 " + " ".join(f"{y*100:+.1f}" for y in yrs))
G = L[L.good]
print("\n17 只逐只（区间 A 年化：MACD / A20 / K−D / 两者）")
for _, r in G.iterrows(): print(f"  {r.code} {str(r['name'])[:8]:<10} {r.MACD*100:+6.1f} {r.A20*100:+6.1f} {r['K−D']*100:+6.1f} {r['A20+K−D']*100:+6.1f}  回撤 {r.MACD_dd*100:.1f}/{r['A20+K−D_dd']*100:.1f}  买入 {r.MACD_n}/{r['A20+K−D_n']}")
