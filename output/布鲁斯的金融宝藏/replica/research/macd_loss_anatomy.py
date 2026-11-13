"""纯 MACD 逐笔：按持有天数分档看胜率与收益，看亏损来自哪里（50 只 ≥3 年，2016 起，口径同 macd_a20_etf.py）。另算“若持有期间最高浮盈≥x 就算赢”的上限胜率，说明出场方式对胜率的影响。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, indicators
R = []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mm, c = load(code); f, m, gold, dead = indicators(d, c)
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04")))
    if (d.index[-1] - d.index[i0]).days / 365.25 < 3: continue
    o = d.open.values; i = i0
    while i < len(d) - 1:
        if m[i] and not m[i - 1]:
            b = i
            while i < len(d) and m[i]: i += 1
            if i >= len(d) - 1: break
            e = i  # 死叉日，次日开盘卖
            # 用复权连续价近似持仓收益：买 b+1 开盘、卖 e+1 开盘
            fac = c / d.close.values; ob, oe = o[b + 1] * fac[b + 1], o[e + 1] * fac[e + 1]
            path = c[b + 1:e + 1] / ob - 1
            R.append(dict(code=code, days=e + 1 - (b + 1), ret=oe / ob * 0.999 ** 2 - 1, peak=path.max() if len(path) else 0))
        else: i += 1
T = pd.DataFrame(R)
print(f"共 {len(T)} 笔，胜率 {(T.ret > 0).mean():.1%}，平均 {T.ret.mean()*100:+.2f}%")
T["档"] = pd.cut(T.days, [0, 5, 10, 20, 40, 1000], labels=["≤5天", "6–10天", "11–20天", "21–40天", ">40天"])
g = T.groupby("档", observed=True)
print(f"{'持有':<7}{'笔数占比':>8}{'胜率':>7}{'平均每笔':>9}{'占总亏损':>9}{'占总盈利':>9}")
loss, gain = -T.ret[T.ret < 0].sum(), T.ret[T.ret > 0].sum()
for k, x in g: print(f"{k:<7}{len(x)/len(T):>8.0%}{(x.ret > 0).mean():>7.0%}{x.ret.mean()*100:>+8.2f}%{-x.ret[x.ret < 0].sum()/loss:>9.0%}{x.ret[x.ret > 0].sum()/gain:>9.0%}")
print("\n亏损交易里，持有期间曾经浮盈（收盘计）达到：")
L = T[T.ret <= 0]
for th in (0.01, 0.02, 0.03, 0.05): print(f"  ≥{th:.0%}：{(L.peak >= th).mean():.0%}")
print(f"亏损交易中位亏损 {L.ret.median()*100:.2f}%，盈利交易中位盈利 {T.ret[T.ret > 0].median()*100:.2f}%")
