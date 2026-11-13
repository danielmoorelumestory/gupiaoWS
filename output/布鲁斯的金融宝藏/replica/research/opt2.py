import pandas as pd, numpy as np, sys
df = pd.read_csv(sys.argv[1], parse_dates=["date"]).set_index("date")
s, p = df["spread"], df["index"]; H = (60, 120, 250)
fwd = {h: p.shift(-h) / p - 1 for h in H}
def z_(w): 
    m = s.rolling(w, min_periods=w//2).mean(); sd = s.rolling(w, min_periods=w//2).std(ddof=0); return (s - m) / sd
def show(idx, label):
    row = [label, len(idx)]
    for h in H:
        r = fwd[h].iloc[idx].dropna(); row += [f"{r.mean()*100:+.1f}", f"{(r>0).mean()*100:.0f}%({len(r)})"]
    print(" | ".join(map(str, row)), [str(s.index[i].date()) for i in idx])
z = z_(750); ok = z.notna()
print("同期基准", " ".join(f"{h}d {fwd[h][ok].mean()*100:+.1f}/{(fwd[h][ok]>0).mean()*100:.0f}%" for h in H))
print("== 破下轨后一年内跌破均线")
for w in (500, 750, 1000):
    zz = z_(w)
    for k in (1.5, 2.0):
        for n in (120, 250):
            ma = p.rolling(n).mean(); idx = []; armed = -1
            for i in range(len(p)):
                if zz.iloc[i] <= -k: armed = i
                if armed >= 0 and i - armed <= 250 and p.iloc[i] < ma.iloc[i] and p.iloc[i-1] >= ma.iloc[i-1]: idx.append(i); armed = -1
            show(idx, f"w{w} k{k} MA{n}")
print("== 上轨 1.5σ 首次进入（w750），分前后段")
def ev(flag, gap=20):
    out, last = [], -10**9
    for i in np.flatnonzero(flag.values):
        if i - last >= gap: out.append(i)
        last = i
    return out
e = ev(z >= 1.5); show(e, "k1.5 全部")
show([i for i in e if s.index[i].year <= 2015], "≤2015"); show([i for i in e if s.index[i].year > 2015], ">2015")
e2 = ev(z >= 2); show(e2, "k2 全部")
print("== 区间内持有：z>=1.5 进，z<=0 出 / z>=2 进，z<=0 出 / 一直持有")
r = p.pct_change().fillna(0)
def strat(k_in, out=0.0):
    pos = np.zeros(len(p)); h = 0
    for i, zi in enumerate(z.values):
        if not np.isnan(zi):
            if zi >= k_in: h = 1
            elif zi <= out: h = 0
        pos[i] = h
    pos = pd.Series(pos, index=p.index).shift(1).fillna(0)[ok]
    eq = (1 + r[ok] * pos).cumprod(); yrs = len(eq) / 244
    return f"年化 {(eq.iloc[-1] ** (1/yrs) - 1)*100:.1f}% 回撤 {((eq/eq.cummax()-1).min())*100:.0f}% 持仓占比 {pos.mean()*100:.0f}%"
print("1.5→0:", strat(1.5)); print("2→0:", strat(2)); print("1.5→-1:", strat(1.5, -1)); print("1→0:", strat(1.0))
eq = (1 + r[ok]).cumprod(); print("持有:", f"年化 {(eq.iloc[-1] ** (244/len(eq)) - 1)*100:.1f}% 回撤 {((eq/eq.cummax()-1).min())*100:.0f}%")
