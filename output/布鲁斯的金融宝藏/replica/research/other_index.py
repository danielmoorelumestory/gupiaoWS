"""把息差通道原样（750 日、2 倍标准差、20 日合并）搬到别的指数上。
乐咕的指数市盈率是月频，这里用月末的 指数/市盈率 得到每股盈利并向后填充，再用每日收盘还原日频市盈率（不含未来数据）。"""
import pandas as pd, numpy as np
H = (60, 120, 250)
bond = pd.read_csv("data/cn10y.csv", parse_dates=["date"]).set_index("date")["cn10y"]
def daily_spread(pe_file, px, col="滚动市盈率"):
    pe = pd.read_csv(pe_file, parse_dates=["日期"]).set_index("日期")
    e = (pe["指数"] / pe[col]).reindex(px.index.union(pe.index)).ffill().reindex(px.index)
    ey = e / px * 100
    return (ey - bond.reindex(px.index).ffill()).dropna()
def run(name, s, p, w=750, k=2.0, gap=20):
    p = p.reindex(s.index); fwd = {h: p.shift(-h) / p - 1 for h in H}
    m = s.rolling(w, min_periods=w // 2).mean(); sd = s.rolling(w, min_periods=w // 2).std(ddof=0); z = (s - m) / sd; ok = z.notna()
    print(f"\n=== {name}  通道可用 {z.dropna().index[0].date()} 起，{int(ok.sum())} 个交易日；最新息差 {s.iloc[-1]:.2f} 偏离 {z.iloc[-1]:+.2f}")
    print("  同期基准  " + "  ".join(f"{h}日 {fwd[h][ok].mean()*100:+.1f}%/{(fwd[h][ok].dropna()>0).mean()*100:.0f}%" for h in H))
    for label, flag in (("触上轨", z >= k), ("破下轨", z <= -k)):
        idx, last = [], -10**9
        for i in np.flatnonzero(flag.values):
            if i - last >= gap: idx.append(i)
            last = i
        line = f"  {label} {len(idx)} 次  "
        for h in H:
            r = fwd[h].iloc[idx].dropna(); line += f"{h}日 {r.mean()*100:+.1f}%/{(r>0).mean()*100:.0f}%({len(r)})  " if len(r) else f"{h}日 —  "
        print(line)
        for i in idx: print("     ", s.index[i].date(), f"息差 {s.iloc[i]:.2f}", " ".join("—" if np.isnan(fwd[h].iloc[i]) else f"{fwd[h].iloc[i]*100:+.0f}%" for h in H))
    return z
if __name__ == "__main__":
    ref = pd.read_csv("data/equity_bond_spread.csv", parse_dates=["date"]).set_index("date")
    approx = daily_spread("data/csi300_pe_lg.csv", ref["index"])
    d = (approx - ref["spread"]).dropna()
    print(f"校验：沪深300 用月频还原的息差与日频真值相比，平均偏差 {d.mean():+.3f}，绝对偏差中位数 {d.abs().median():.3f}，95% 分位 {d.abs().quantile(.95):.3f}，相关 {approx.corr(ref['spread']):.4f}")
    run("沪深300（日频真值）", ref["spread"], ref["index"]); run("沪深300（月频还原）", approx, ref["index"])
    for name, code in (("中证1000", "sh000852"), ("中证500", "sh000905")):
        px = pd.read_csv(f"data/index_{code}.csv", parse_dates=["date"]).set_index("date")["close"]
        for col in ("滚动市盈率", "滚动市盈率中位数"):
            run(f"{name}（{col}）", daily_spread(f"data/pe_lg_{code}.csv", px, col), px)
