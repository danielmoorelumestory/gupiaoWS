import pandas as pd, numpy as np
exec(open("research/macd_etf.py").read().split("rows, logs = [], {}")[0])
d, dv, mult, adj, _ = load("512690"); st = macd_state(adj)
y = d.loc["2019-12-31":"2020-12-31"]; s = st.loc[y.index]
# 交易：t 日信号变化，t+1 开盘成交
chg = s.astype(int).diff().fillna(0); idx = list(y.index)
print("2019-12-31 收盘信号持有:", bool(s.iloc[0]), "收盘", y.close.iloc[0])
for i, t in enumerate(idx[:-1]):
    if chg.loc[t] != 0:
        n = idx[i+1]; print(("金叉→买 " if chg.loc[t] > 0 else "死叉→卖 "), t.date(), "成交", n.date(), "开盘", d.open.loc[n])
# 空仓期间指数涨幅（以 adj 计）
pos = s.shift(1).fillna(s.iloc[0]).astype(bool)  # 当天是否持仓（近似）
r = adj.loc[y.index].pct_change().fillna(0)
seg = (pos != pos.shift()).cumsum()
print("\n各段（持仓/空仓）区间涨跌（复权收盘近似）：")
for k, g in r.groupby(seg):
    a = g.index[0].date(); b = g.index[-1].date(); print(f"  {'持仓' if pos.loc[g.index[0]] else '空仓'} {a}→{b} {((1+g).prod()-1)*100:+.1f}%  {len(g)}天")
print("年内：持有", adj.loc["2020-12-31"]/adj.loc["2019-12-31"]-1)
