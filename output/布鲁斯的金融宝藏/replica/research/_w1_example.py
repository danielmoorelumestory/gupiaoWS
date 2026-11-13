import pandas as pd, numpy as np
exec(open("research/macd_exit_divergence.py").read().split("rows = []")[0])
d, dv, mult, adj, _ = load("588200"); st = positions(adj, "W1"); ma = adj.rolling(10).mean()
s = pd.Series(adj.ewm(span=12, adjust=False).mean() - adj.ewm(span=26, adjust=False).mean()); dea = s.ewm(span=9, adjust=False).mean()
idx = list(d.index); n = 0
for i in range(61, len(idx) - 1):
    if st.iloc[i - 1] and not st.iloc[i] and s.iloc[i] > dea.iloc[i]:   # 卖出信号且仍是金叉状态 → 由 10 日线触发
        t, nx = idx[i], idx[i + 1]
        print(f"信号日 {t.date()} 收盘 {d.close.iloc[i]:.3f}（复权 {adj.iloc[i]:.3f} < MA10 {ma.iloc[i]:.3f}），DIF>DEA 未死叉 → 卖出日 {nx.date()} 开盘 {d.open.iloc[i+1]:.3f}")
        n += 1
        if n == 3: break
