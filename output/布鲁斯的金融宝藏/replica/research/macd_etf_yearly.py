"""行业 ETF MACD 逐年统计。规则、数据、撮合与 macd_etf.py 完全相同（直接复用其前 77 行的函数），起点为各自上市后第 60 个交易日，
收 0.1%。每年收益 = 当年最后一天净值 / 上一年最后一天净值 − 1（起点那一年从起点算，是不满一年的部分年）。"""
import pandas as pd, numpy as np
src = open("research/macd_etf.py").read().split("rows, logs = [], {}")[0]; exec(src)
allc = {**picked, **EXTRA}; H, Mc = {}, {}
def yearly(nav):
    e = nav.groupby(nav.index.year).last(); prev = e.shift(1); prev.iloc[0] = 1.0; return e / prev - 1
for code, (kw, name) in allc.items():
    d, dv, mult, adj, _ = load(code); st = macd_state(adj); i0 = 60
    h, _ = backtest(d, dv, mult, pd.Series(True, index=d.index), i0, 0.0); m, _ = backtest(d, dv, mult, st, i0, 0.001)
    H[name], Mc[name] = yearly(h) * 100, yearly(m) * 100
H, Mc = pd.DataFrame(H).T, pd.DataFrame(Mc).T; D = Mc - H
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
fmt = lambda x: "" if pd.isna(x) else f"{x:+.1f}"
for title, t in (("MACD 减 一直持有（百分点）", D), ("一直持有（%）", H), ("MACD 收 0.1%（%）", Mc)):
    print(f"\n==== {title}；起点年份为不满一年；2026 截至 11-10"); print(t.map(fmt).to_string())
base = D.loc[[allc[c][1] for c in picked]]
print("\n==== 每年汇总（规则选出的 20 只，不含两只科创）")
print(pd.DataFrame({"样本数": base.notna().sum(), "MACD 跑赢": (base > 0).sum(), "差的中位数": base.median().round(1),
                    "持有中位数": H.loc[base.index].median().round(1), "MACD中位数": Mc.loc[base.index].median().round(1)}).T.to_string())
