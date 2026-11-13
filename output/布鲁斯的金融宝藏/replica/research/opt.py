import pandas as pd, numpy as np, sys
df = pd.read_csv(sys.argv[1], parse_dates=["date"]).set_index("date")
s, p = df["spread"], df["index"]
H = (60, 120, 250)
fwd = {h: p.shift(-h) / p - 1 for h in H}
def ev(flag, gap=20):
    out, last = [], -10**9
    idx = np.flatnonzero(flag.values)
    for i in idx:
        if i - last >= gap: out.append(i)
        last = i
    return out
def stat(idx, label, valid=None):
    row = [label, len(idx)]
    for h in H:
        r = fwd[h].iloc[idx].dropna()
        b = fwd[h][valid] if valid is not None else fwd[h]
        row += [f"{r.mean()*100:+.1f}", f"{(r>0).mean()*100:.0f}%" if len(r) else "-", f"{r.min()*100:+.0f}" if len(r) else "-"]
    print(" | ".join(str(x) for x in row))
def band(w, k):
    m = s.rolling(w, min_periods=w//2).mean(); sd = s.rolling(w, min_periods=w//2).std(ddof=0)
    return m, sd, (s - m) / sd
print("基准(全样本)", " ".join(f"{h}d {fwd[h].mean()*100:+.1f}/{(fwd[h]>0).mean()*100:.0f}%" for h in H))
print("\n== 1 参数稳健性：上轨触发  [n | 60d均值 胜率 最差 | 120d | 250d]")
for w in (250, 500, 750, 1000, 1250):
    for k in (1.5, 2.0, 2.5):
        m, sd, z = band(w, k); stat(ev(z >= k), f"w{w} k{k}")
print("\n== 1b 下轨触发")
for w in (250, 500, 750, 1000, 1250):
    for k in (1.5, 2.0):
        m, sd, z = band(w, k); stat(ev(z <= -k), f"w{w} k{k}")
m, sd, z = band(750, 2)
print("\n== 2 连续关系：按 z 值分档后的远期收益（全部日子，750日）")
bins = [-9, -2, -1, 0, 1, 1.5, 2, 9]
g = pd.cut(z, bins)
t = pd.DataFrame({f"{h}d": fwd[h].groupby(g, observed=True).mean()*100 for h in H}); t["天数"] = g.value_counts().sort_index(); 
t["250d胜率"] = (fwd[250] > 0).groupby(g, observed=True).mean()*100
print(t.round(1))
print("\n== 2b 分前后两段（2005-2015 / 2016-至今）120d 均值")
for a, b in (("2005", "2015"), ("2016", "2026")):
    print(a, b, (fwd[120][a:b].groupby(g[a:b], observed=True).mean()*100).round(1).to_dict())
print("\n== 3 确认版：触上轨后，等息差回落到上轨下方 x 倍σ 再算信号")
up = z >= 2
for back in (0.0, 0.25, 0.5):
    idx = []
    armed = False
    for i, (zi) in enumerate(z.values):
        if np.isnan(zi): continue
        if zi >= 2: armed = True
        elif armed and zi < 2 - back: idx.append(i); armed = False
    # 合并
    out, last = [], -10**9
    for i in idx:
        if i - last >= 60: out.append(i)
        last = i
    stat(out, f"回落{back}σ"); print("   ", [str(s.index[i].date()) for i in out])
print("\n== 3b 确认版：触上轨后 120 日内，指数首次站上 MA(n)")
for n in (20, 60):
    ma = p.rolling(n).mean(); idx = []; armed = -1
    for i in range(len(p)):
        if up.iloc[i]: armed = i
        elif armed >= 0 and i - armed <= 120 and p.iloc[i] > ma.iloc[i] and p.iloc[i-1] <= ma.iloc[i-1]:
            idx.append(i); armed = -1
    out, last = [], -10**9
    for i in idx:
        if i - last >= 60: out.append(i)
        last = i
    stat(out, f"站上MA{n}"); print("   ", [str(s.index[i].date()) for i in out])
print("\n== 4 分位版：息差处于过去 N 日的分位 >= q")
for w in (750, 1250, 2500):
    r = s.rolling(w, min_periods=w//2).rank(pct=True)
    for q in (0.95, 0.98):
        stat(ev(r >= q), f"w{w} q{q}")
print("\n== 5 下轨+趋势：z<=-2 且指数跌破 MA120（之后）")
for n in (60, 120, 250):
    ma = p.rolling(n).mean(); idx = []; armed = -1
    for i in range(len(p)):
        if z.iloc[i] <= -2: armed = i
        if armed >= 0 and i - armed <= 250 and p.iloc[i] < ma.iloc[i] and p.iloc[i-1] >= ma.iloc[i-1]:
            idx.append(i); armed = -1
    stat(idx, f"破下轨后跌破MA{n}"); print("   ", [str(s.index[i].date()) for i in idx])
