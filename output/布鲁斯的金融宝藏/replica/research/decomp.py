import pandas as pd, numpy as np
df = pd.read_csv("data/equity_bond_spread.csv", parse_dates=["date"]).set_index("date")
b = pd.read_csv("data/cn10y.csv", parse_dates=["date"]).set_index("date")["cn10y"]
df["bond"] = b.reindex(df.index).ffill(); df = df.dropna()
df["ey"] = df["spread"] + df["bond"]; df["E"] = df["ey"] / 100 * df["index"]
s, p = df["spread"], df["index"]; H = (60, 120, 250)
fwd = {h: p.shift(-h) / p - 1 for h in H}
print("校验 最新: 息差", s.iloc[-1], "国债", df.bond.iloc[-1], "盈利收益率", round(df.ey.iloc[-1], 2), "隐含PE", round(100 / df.ey.iloc[-1], 2), "| 缺国债天数", int(b.reindex(df.index).isna().sum()))
def zs(x, w=750):
    m = x.rolling(w, min_periods=w // 2).mean(); sd = x.rolling(w, min_periods=w // 2).std(ddof=0); return (x - m) / sd
z = zs(s); zey = zs(df.ey); zb = zs(-df.bond)
def ev(flag, gap=20):
    out, last = [], -10**9
    for i in np.flatnonzero(flag.values):
        if i - last >= gap: out.append(i)
        last = i
    return out
def table(idx, title):
    print(f"\n== {title}")
    print("日期 | 息差 国债 盈利收益率 | 前250日: Δ息差 = Δ盈利收益率 − Δ国债 | 指数涨跌 利润变化 | 单看股票端z 单看债券端z | 之后120d 250d")
    for i in idx:
        r = df.iloc[i]; j = max(0, i - 250); q = df.iloc[j]
        f = [fwd[h].iloc[i] for h in (120, 250)]
        print(f"{df.index[i].date()} | {r.spread:.2f} {r.bond:.2f} {r.ey:.2f} | {r.spread-q.spread:+.2f} = {r.ey-q.ey:+.2f} − ({r.bond-q.bond:+.2f}) | {(r['index']/q['index']-1)*100:+.0f}% {(r.E/q.E-1)*100:+.0f}% | {zey.iloc[i]:+.2f} {zb.iloc[i]:+.2f} | " + " ".join("—" if np.isnan(x) else f"{x*100:+.0f}%" for x in f))
table(ev(z >= 2), "触及上轨 9 次"); table(ev(z <= -2), "跌破下轨 6 次")
def show(idx, label):
    row = [label, len(idx)]
    for h in H:
        r = fwd[h].iloc[idx].dropna(); row += [f"{r.mean()*100:+.1f}", f"{(r>0).mean()*100:.0f}%"]
    print(" | ".join(map(str, row)), [str(df.index[i].date()) for i in idx])
ok = z.notna()
print("\n== 单腿通道（同样 750 日 / 2 倍）  [n | 60d | 120d | 250d]")
print("同期基准", " ".join(f"{h}d {fwd[h][ok].mean()*100:+.1f}/{(fwd[h][ok]>0).mean()*100:.0f}%" for h in H))
show(ev(z >= 2), "息差 触上轨"); show(ev(zey >= 2), "只看盈利收益率 触上轨"); show(ev(zb >= 2), "只看国债(利率极低)")
show(ev(z <= -2), "息差 破下轨"); show(ev(zey <= -2), "只看盈利收益率 破下轨"); show(ev(zb <= -2), "只看国债(利率极高)")
print("\n== 全部交易日：股票端 z × 债券端 z 分组后的 250 日远期收益均值(%) / 天数")
ge = pd.cut(zey, [-9, -1, 0, 1, 9], labels=["股票很贵", "偏贵", "偏便宜", "很便宜"]); gb = pd.cut(zb, [-9, -1, 0, 1, 9], labels=["利率很高", "偏高", "偏低", "很低"])
print((fwd[250].groupby([ge, gb], observed=True).mean() * 100).unstack().round(1)); print(fwd[250].groupby([ge, gb], observed=True).count().unstack())
print("\n== 相关性（与 250 日远期收益，日频，仅作方向参考）")
for n, x in (("息差z", z), ("股票端z", zey), ("债券端z", zb)): print(n, round(x.corr(fwd[250]), 3), "| 120d", round(x.corr(fwd[120]), 3))
print("息差z 与 股票端z 相关", round(z.corr(zey), 3), " 与 债券端z", round(z.corr(zb), 3))
print("\n== 息差的波动来自哪一端（日变动方差占比）")
d = df[["spread", "ey", "bond"]].diff(250).dropna(); print("250日变动方差: 息差", round(d.spread.var(), 2), "盈利收益率", round(d.ey.var(), 2), "国债", round(d.bond.var(), 2))
print("\n当前", df.index[-1].date(), "息差z", round(z.iloc[-1], 2), "股票端z", round(zey.iloc[-1], 2), "债券端z", round(zb.iloc[-1], 2))
r, q = df.iloc[-1], df.iloc[-251]
print(f"近250日: Δ息差 {r.spread-q.spread:+.2f} = Δ盈利收益率 {r.ey-q.ey:+.2f} − Δ国债 {r.bond-q.bond:+.2f}; 指数 {(r['index']/q['index']-1)*100:+.0f}% 利润 {(r.E/q.E-1)*100:+.0f}%")
