"""按“买入后持有期间最高收盘相对成本的涨幅”分档看胜率。口径同 macd_loss_anatomy.py（复权连续价，买 b+1 开盘、卖死叉次日开盘、扣双边 0.1%），
另给 A20+K−D 版本，以及用盘中最高价计算的对照。50 只 ≥3 年，2016 起。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, indicators, wilder
THR = pd.read_csv("research/codex_filter17_thresholds.csv").set_index("year").amplitude20.to_dict()
R = []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mm, c = load(code); f, m, gold, dead = indicators(d, c)
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04")))
    if (d.index[-1] - d.index[i0]).days / 365.25 < 3: continue
    fac = c / d.close.values; oa = d.open.values * fac; ha = d.high.values * fac; la = d.low.values * fac
    prev = np.r_[np.nan, c[:-1]]; gap = f["hist"].to_numpy() * c / wilder(np.maximum(ha - la, np.maximum(abs(ha - prev), abs(la - prev))))
    i = i0
    while i < len(d) - 1:
        if m[i] and not m[i - 1]:
            b = i
            while i < len(d) and m[i]: i += 1
            if i >= len(d) - 1: break
            e = i; cost = oa[b + 1]; th = THR.get(d.index[b].year, np.nan)
            ok = np.isfinite(th) and np.isfinite(gap[b]) and gap[b] >= th and f.kd.iloc[b] >= 5.3
            R.append(dict(code=code, ok=ok, days=e - b, ret=oa[e + 1] / cost * 0.999 ** 2 - 1,
                          peak=c[b + 1:e + 1].max() / cost - 1, peak_hi=ha[b + 1:e + 1].max() / cost - 1))
        else: i += 1
T = pd.DataFrame(R); T.to_csv("research/macd_peak_trades.csv", index=False)
def table(X, col, nm):
    print(f"\n[{nm}] 共 {len(X)} 笔，总胜率 {(X.ret > 0).mean():.1%}")
    print(f"  {'曾经涨到':<10}{'占全部':>7}{'胜率':>7}{'平均每笔':>9}{'其中最后亏的平均':>14}")
    for lo in (0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15):
        x = X[X[col] > lo] if lo == 0 else X[X[col] >= lo]
        print(f"  {'高于成本' if lo == 0 else f'≥+{lo:.0%}':<10}{len(x)/len(X):>7.0%}{(x.ret > 0).mean():>7.0%}{x.ret.mean()*100:>+8.2f}%{x.ret[x.ret <= 0].mean()*100:>+13.2f}%")
    x = X[X[col] <= 0]; print(f"  {'从未高于成本':<10}{len(x)/len(X):>6.0%}{(x.ret > 0).mean():>7.0%}{x.ret.mean()*100:>+8.2f}%")
    print("  分档（互斥）：")
    bins = [-1, 0, 0.02, 0.05, 0.08, 0.15, 10]; lab = ["从未高于成本", "0~2%", "2~5%", "5~8%", "8~15%", "≥15%"]
    X = X.assign(档=pd.cut(X[col], bins, labels=lab, right=False))
    for k, x in X.groupby("档", observed=True): print(f"    {k:<8} 占 {len(x)/len(X):>4.0%}  胜率 {(x.ret > 0).mean():>4.0%}  平均 {x.ret.mean()*100:+6.2f}%")
table(T, "peak", "纯 MACD，按收盘价"); table(T, "peak_hi", "纯 MACD，按盘中最高价"); table(T[T.ok], "peak", "A20+K−D，按收盘价")
