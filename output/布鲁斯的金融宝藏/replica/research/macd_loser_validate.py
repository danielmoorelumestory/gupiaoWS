"""用发现段（<2023）找到的两个候选过滤，在验证段（2023-01-03 起）做组合回测（候选与阈值来自发现段，验证段不再调整）。
C1：金叉当日 K−D < 5.3（发现段 K−D 最低 20% 切点）的金叉跳过；C2：距上次死叉 ≤3 个交易日的金叉跳过；C12：两者都跳过。
卖出均为死叉；其余口径同前。只统计 2023 年前已上市满 60 日、验证段 ≥1.5 年的 ETF。"""
import json, numpy as np, pandas as pd
exec(open("research/macd_rsi_kdj.py").read().split("ENTRY = {")[0])
def pos(x, rule):
    dif, dea, K, D = x["dif"], x["dea"], x["K"], x["D"]; n = len(dif); p = np.zeros(n, bool); hold = False; last_dead = -999
    for t in range(1, n):
        if dif[t] <= dea[t] and dif[t-1] > dea[t-1]: last_dead = t
        if hold:
            if dif[t] < dea[t]: hold = False
        elif dif[t] > dea[t] and dif[t-1] <= dea[t-1]:
            skip = (rule in ("C1", "C12") and K[t] - D[t] < 5.3) or (rule in ("C2", "C12") and t - last_dead <= 3)
            hold = not skip
        p[t] = hold
    return p
rows = []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code)
    i0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
    if i0 < 60 or (d.index[-1] - d.index[i0]).days < 548: continue
    x = indicators(d, adj); r = dict(code=code, name=name)
    for k, sv in {"M": macd_state(adj).values, "C1": pos(x, "C1"), "C2": pos(x, "C2"), "C12": pos(x, "C12")}.items():
        n_, tr = backtest(d, dv, mult, pd.Series(sv, index=d.index), i0, 0.001); r[k], r[k + "_dd"], r[k + "_n"] = ann(n_), mdd(n_), len(tr)
    h, _ = backtest(d, dv, mult, pd.Series(True, index=d.index), i0, 0.0); r["H"] = ann(h)
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/macd_loser_validate_results.csv", index=False)
print(f"验证段 2023-01-03 至 2026-11-10，{len(t)} 只 ETF（年化 %）")
for k, nm in (("H", "一直持有"), ("M", "纯MACD"), ("C1", "跳过 K−D<5.3 的金叉"), ("C2", "跳过距死叉≤3日的金叉"), ("C12", "两者都跳过")):
    extra = f"  胜纯MACD {(t[k]>t.M).sum()}/{len(t)}  回撤中位 {t[k+'_dd'].median()*100:.1f}  笔数中位 {t[k+'_n'].median():.0f}" if k != "H" else ""
    print(f"   {nm:<18} 年化中位 {t[k].median()*100:+6.2f}  均值 {t[k].mean()*100:+6.2f}{extra}")
