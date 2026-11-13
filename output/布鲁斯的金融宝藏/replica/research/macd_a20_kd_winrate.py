"""逐笔胜率：MACD / +A20 / +K−D / +A20+K−D，口径同 macd_a20_etf.py（同区间、同撤合、扣双边 0.1%）。只统计已平仓交易。"""
import sys, io, contextlib, numpy as np, pandas as pd
src = open("research/macd_a20_etf.py", encoding="utf-8").read().split("t = pd.DataFrame(rows)")[0]
src = src.replace("rows, NAVB = [], {}", "rows, NAVB, TR = [], {}, []")
src = src.replace("""    S = {"持有\"""", """    pass
    S = {"持有\"""")
# 在每只 ETF 的策略循环后记录逐笔
src = src.replace("""    j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))""", """    o_, c_ = d.open.values, d.close.values
    for k, st in S.items():
        if k == "持有": continue
        nav = 1.0; hold = False; entry = None; bd = None
        for kk in range(i0, len(d)):
            want = bool(st[kk - 1])
            if hold: nav *= (o_[kk] + dv[kk]) * mm[kk] / c_[kk - 1]
            if want != hold:
                if want: entry = nav; bd = d.index[kk]
                else: TR.append(dict(code=code, good=code in GOOD, rule=k, buy=bd, ret=nav * 0.999 / entry - 1, years=(d.index[-1] - d.index[i0]).days / 365.25))
                nav *= 0.999; hold = want
            if hold: nav *= c_[kk] / o_[kk]
    j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))""")
with contextlib.redirect_stdout(io.StringIO()): exec(src)
T = pd.DataFrame(TR); T.to_csv("research/macd_a20_kd_trades.csv", index=False)
K = ["MACD", "A20", "K−D", "A20+K−D"]
def show(nm, X):
    print(f"\n[{nm}]")
    print(f"  {'规则':<8}{'笔数':>6}{'胜率':>8}{'平均每笔':>9}{'中位每笔':>9}{'赚钱笔均值':>10}{'亏钱笔均值':>10}{'盈亏比':>7}")
    for k in K:
        x = X[X.rule == k].ret
        w, l = x[x > 0], x[x <= 0]
        print(f"  {k:<8}{len(x):>6}{(x > 0).mean():>8.1%}{x.mean()*100:>+8.2f}%{x.median()*100:>+8.2f}%{w.mean()*100:>+9.2f}%{l.mean()*100:>+9.2f}%{w.mean()/-l.mean():>7.2f}")
show("≥3年 50 只", T[T.years >= 3]); show("MACD优秀 17 只", T[(T.years >= 3) & T.good]); show("其余 33 只", T[(T.years >= 3) & ~T.good])
show("2023-01-03 起买入的交易（50 只）", T[(T.years >= 3) & (T.buy >= "2023-01-03")])
G = T[(T.years >= 3) & T.good]
print("\n17 只逐只胜率（MACD / A20 / K−D / 两者）")
for code, g in G.groupby("code", sort=False):
    print(f"  {code} " + "  ".join(f"{(g[g.rule == k].ret > 0).mean():.0%}({(g.rule == k).sum()})" for k in K))
L = T[T.years >= 3]
per = L.groupby(["code", "rule"]).ret.apply(lambda x: (x > 0).mean()).unstack()
for k in K[1:]: print(f"50 只中 {k} 胜率高于 MACD 的：{(per[k] > per['MACD']).sum()}/{len(per)}，持平 {(per[k] == per['MACD']).sum()}")
