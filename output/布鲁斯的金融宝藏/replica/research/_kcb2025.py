import pandas as pd
exec(open("research/macd_etf.py").read().split("rows, logs = [], {}")[0])
for code in ("588170", "588200", "512480"):
    d, dv, mult, adj, _ = load(code); s = macd_state(adj).loc["2025-07-04":"2026-01-05"]; idx = list(s.index)
    print(code, "07-04 信号持有:", bool(s.iloc[0]), " 期间复权收盘涨幅（07-04→12-31）", round((adj.loc["2025-12-31"]/adj.loc["2025-07-04"]-1)*100,1))
    for i in range(1, len(idx) - 1):
        if s.iloc[i] != s.iloc[i-1]:
            n = idx[i+1]; print("   ", "买" if s.iloc[i] else "卖", n.date(), "复权开盘", round(adj.loc[n] / d.close.loc[n] * d.open.loc[n], 3))
