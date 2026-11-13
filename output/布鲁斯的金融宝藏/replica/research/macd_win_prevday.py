"""诊断：盈利/亏损交易在买入前的涨跌幅。规则 MACD + 尾盘卖（金叉次日开盘买，死叉当天收盘卖，单边 0.1%）。
“前一天”= 买入日的前一天 = 金叉当天的涨跌；另给金叉前一天、金叉前3日累计涨跌。2016 起（或上市第70日）。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, ema
ITEMS = json.load(open("data/page_etfs_plus.json"))
t = pd.read_csv("research/macd_close_exec_results.csv", dtype={"code": str}); L = t[t.years >= 3]; GOOD = set(L.loc[L.good, "code"]); ALL = set(L.code)
R = []
for code, name, grp in ITEMS:
    if code not in ALL: continue
    d, dv, mm, c = load(code); o = d.open.values * c / d.close.values; dif = ema(c, 2/13) - ema(c, 2/27); m = dif > ema(dif, .2)
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04")))
    for g in range(i0 - 1, len(c) - 1):
        if m[g] and not m[g - 1]:
            x = g
            while x < len(c) and m[x]: x += 1
            if x >= len(c): break
            ret = c[x] / o[g + 1] * .999 * .999 - 1
            R.append(dict(code=code, name=name, good=code in GOOD, date=d.index[g], ret=ret, win=ret > 0, 金叉当天=c[g]/c[g-1]-1, 金叉前一天=c[g-1]/c[g-2]-1, 金叉前3日=c[g-1]/c[g-4]-1, 次日开盘跳空=o[g+1]/c[g]-1, 持有天数=x-g))
X = pd.DataFrame(R); X.to_csv("research/macd_win_prevday_trades.csv", index=False)
def pc(v): return f"{v*100:+.2f}%"
for nm, S in (("MACD优秀 17 只", X[X.good]), ("50 只", X)):
    print(f"\n######## {nm}：{len(S)} 笔，胜率 {S.win.mean():.1%}，每笔均 {pc(S.ret.mean())} ########")
    for f in ("金叉当天", "金叉前一天", "金叉前3日", "次日开盘跳空"):
        W, Lo = S[S.win][f], S[~S.win][f]
        print(f"\n[{f}涨跌] 盈利 {len(W)} 笔：10%分位 {pc(W.quantile(.1))} 25% {pc(W.quantile(.25))} 中位 {pc(W.median())} 75% {pc(W.quantile(.75))} 90% {pc(W.quantile(.9))}")
        print(f"            亏损 {len(Lo)} 笔：10%分位 {pc(Lo.quantile(.1))} 25% {pc(Lo.quantile(.25))} 中位 {pc(Lo.median())} 75% {pc(Lo.quantile(.75))} 90% {pc(Lo.quantile(.9))}")
        bins = [-1, -.01, 0, .005, .01, .02, .03, 1] if f != "次日开盘跳空" else [-1, -.005, -.001, .001, .005, .01, 1]
        S2 = S.assign(b=pd.cut(S[f], bins))
        for b, G in S2.groupby("b", observed=True):
            e1, e2 = G[G.date < "2021-01-01"], G[G.date >= "2021-01-01"]
            print(f"    {str(b):<16} {len(G):4d} 笔 胜率 {G.win.mean():.0%} 每笔均 {pc(G.ret.mean())} 中位 {pc(G.ret.median())} ｜ 2016-20 {len(e1)}笔 胜率 {e1.win.mean():.0%} 均 {pc(e1.ret.mean())} ｜ 2021- {len(e2)}笔 胜率 {e2.win.mean():.0%} 均 {pc(e2.ret.mean())}")
