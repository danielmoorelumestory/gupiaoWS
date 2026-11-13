"""大幅下跌后的金叉才买（运行前写定，跑完不改）。跌幅 = 金叉当日复权收盘 / 过去 60 个交易日（含当日）最高复权收盘 − 1。
规则：D10 跌幅 ≤ −10% 的金叉才买；D20 跌幅 ≤ −20% 才买；卖出均为死叉；M 纯 MACD。
逐笔：所有金叉按跌幅分档 <5%、5–10%、10–20%、≥20%，比较每轮收益（含 0.2% 成本）。样本、成交、成本、汇总同前。"""
import json, numpy as np, pandas as pd
exec(open("research/macd_rsi_kdj.py").read().split("ENTRY = {")[0])
ENTRY = {"D10": lambda x, t: x["dd60"][t] <= -0.10, "D20": lambda x, t: x["dd60"][t] <= -0.20}
EXIT = {}
exec("def positions" + open("research/macd_rsi_kdj.py").read().split("def positions")[1].split("rows, ent, exv")[0])
rows, ent = [], []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code); i0 = 60
    if len(d) < 120: continue
    x = indicators(d, adj); x["dd60"] = (adj / adj.rolling(60, min_periods=1).max() - 1).values
    idx = d.index; ao = (d.open * adj / d.close).values; m = x["dif"] > x["dea"]
    years = (idx[-1] - idx[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    h, _ = backtest(d, dv, mult, pd.Series(True, index=idx), i0, 0.0)
    r = dict(code=code, name=name, years=years, good=code in good, hold=ann(h), hold_dd=mdd(h))
    for k, sv in {"M": macd_state(adj).values, "D10": positions(x, entry="D10"), "D20": positions(x, entry="D20")}.items():
        st = pd.Series(sv, index=idx); n_, tr = backtest(d, dv, mult, st, i0, 0.001)
        a, _ = backtest(d.iloc[:mid + 1], dv.iloc[:mid + 1], mult.iloc[:mid + 1], st.iloc[:mid + 1], i0, 0.001); b, _ = backtest(d, dv, mult, st, mid, 0.001)
        r[k], r[k + "_dd"], r[k + "_exp"], r[k + "_h1"], r[k + "_h2"], r[k + "_n"] = ann(n_), mdd(n_), st.iloc[i0:].mean(), ann(a), ann(b), len(tr)
    for t in range(i0, len(d) - 1):
        if m[t] and not m[t-1]:
            j = t
            while j < len(d) - 1 and m[j]: j += 1
            if j >= len(d) - 1: continue
            ent.append(dict(code=code, good=code in good, long=years >= 3, date=idx[t], fall=x["dd60"][t], days=j - t, ret=ao[j + 1] / ao[t + 1] * 0.999 ** 2 - 1))
    rows.append(r)
t = pd.DataFrame(rows); E = pd.DataFrame(ent); t.to_csv("research/macd_after_drop_results.csv", index=False); E.to_csv("research/macd_after_drop_trades.csv", index=False)
names = {"M": "纯MACD（全部金叉）", "D10": "60日高点跌≥10%后金叉", "D20": "60日高点跌≥20%后金叉"}
bins = [-1, -0.20, -0.10, -0.05, 0.001]; labels = ["≥20%", "10–20%", "5–10%", "<5%"]
for label, g, Eg in (("回测≥3年全部", t[t.years >= 3], E[E.long]), ("MACD优秀 17 只", t[t.good], E[E.good])):
    print(f"\n==== {label}（{len(g)} 只）  一直持有：年化中位 {g.hold.median()*100:+.2f}，均值 {g.hold.mean()*100:+.2f}，回撤中位 {g.hold_dd.median()*100:.1f}")
    print(f"   {'规则':<20}{'年化中位':>8}{'年化均值':>8}{'胜纯MACD':>9}{'胜持有':>8}{'前后半都胜MACD':>13}{'回撤中位':>8}{'持仓':>6}{'笔数中位':>8}")
    for k in names:
        vs = f"{(g[k]>g.M).sum()}/{len(g)}" if k != "M" else "-"; both = f"{((g[k+'_h1']>g.M_h1)&(g[k+'_h2']>g.M_h2)).sum()}/{len(g)}" if k != "M" else "-"
        print(f"   {names[k]:<18}{g[k].median()*100:+8.2f}{g[k].mean()*100:+8.2f}{vs:>9}{(g[k]>g.hold).sum():>5}/{len(g)}{both:>10}{g[k+'_dd'].median()*100:8.1f}{g[k+'_exp'].median()*100:5.0f}%{g[k+'_n'].median():8.0f}")
    Eg = Eg.assign(bucket=pd.cut(Eg.fall, bins, labels=labels))
    print("   逐笔·按金叉时距 60 日高点的跌幅分档：")
    for lab in reversed(labels):
        z = Eg[Eg.bucket == lab]
        print(f"     {lab:<7} {len(z):5d} 轮 平均 {z.ret.mean()*100:+6.2f}% 中位 {z.ret.median()*100:+6.2f}% 胜率 {(z.ret>0).mean()*100:3.0f}% 盈利时 {z[z.ret>0].ret.mean()*100:+6.2f}% 亏损时 {z[z.ret<=0].ret.mean()*100:+6.2f}% 平均持有 {z.days.mean():3.0f} 天")
El = E[E.long]; v = El.ret.values; rng = np.random.default_rng(0)
for thr in (-0.10, -0.20):
    sel = (El.fall <= thr).values; real = v[sel].mean() - v[~sel].mean(); nk = sel.sum()
    sims = [(lambda p: v[p[:nk]].mean() - v[p[nk:]].mean())(rng.permutation(len(v))) for _ in range(5000)]
    print(f"\n置换检验（跌幅≥{-thr:.0%} 对其余）：平均收益差 {real*100:+.2f}%，随机达到或超过的概率 {(np.array(sims) >= real).mean():.1%}")
El = El.assign(year=El.date.dt.year)
print("\n逐年（回测≥3年全部，逐笔平均 %）：跌≥10%后 / 其余 / 跌≥10%轮数")
for y, z in El.groupby("year"):
    a, b = z[z.fall <= -0.10], z[z.fall > -0.10]
    if len(z) >= 20 and len(a): print(f"   {y}  {a.ret.mean()*100:+6.2f} / {b.ret.mean()*100:+6.2f} / {len(a)}")
