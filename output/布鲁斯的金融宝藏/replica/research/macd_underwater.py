"""水下金叉才买（运行前写定，跑完不改）。水下金叉 = 金叉当日 DEA < 0（与页面“水上/水下金叉”定义一致）；水上金叉 = DEA ≥ 0。
规则：UW 只在水下金叉次日开盘买，死叉卖；AW 只做水上金叉（对照）；M 纯 MACD。逐笔：两类金叉各自一轮交易收益（含 0.2% 成本）。
样本、成交、成本、汇总方式同 macd_rsi_kdj.py；另按估值区间（沪深300 整体 PE 分位）拆分逐笔结果作参考。"""
import json, numpy as np, pandas as pd
exec(open("research/macd_rsi_kdj.py").read().split("ENTRY = {")[0])
ENTRY = {"UW": lambda x, t: x["dea"][t] < 0, "AW": lambda x, t: x["dea"][t] >= 0}
EXIT = {}
exec("def positions" + open("research/macd_rsi_kdj.py").read().split("def positions")[1].split("rows, ent, exv")[0])
rows, ent = [], []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code); i0 = 60
    if len(d) < 120: continue
    x = indicators(d, adj); idx = d.index; ao = (d.open * adj / d.close).values; m = x["dif"] > x["dea"]
    years = (idx[-1] - idx[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    h, _ = backtest(d, dv, mult, pd.Series(True, index=idx), i0, 0.0)
    r = dict(code=code, name=name, years=years, good=code in good, hold=ann(h), hold_dd=mdd(h))
    for k, sv in {"M": macd_state(adj).values, "UW": positions(x, entry="UW"), "AW": positions(x, entry="AW")}.items():
        st = pd.Series(sv, index=idx); n_, tr = backtest(d, dv, mult, st, i0, 0.001)
        a, _ = backtest(d.iloc[:mid + 1], dv.iloc[:mid + 1], mult.iloc[:mid + 1], st.iloc[:mid + 1], i0, 0.001); b, _ = backtest(d, dv, mult, st, mid, 0.001)
        r[k], r[k + "_dd"], r[k + "_exp"], r[k + "_h1"], r[k + "_h2"], r[k + "_n"] = ann(n_), mdd(n_), st.iloc[i0:].mean(), ann(a), ann(b), len(tr)
    for t in range(i0, len(d) - 1):
        if m[t] and not m[t-1]:
            j = t
            while j < len(d) - 1 and m[j]: j += 1
            if j >= len(d) - 1: continue
            ent.append(dict(code=code, good=code in good, long=years >= 3, date=idx[t], uw=bool(x["dea"][t] < 0), days=j - t, ret=ao[j + 1] / ao[t + 1] * 0.999 ** 2 - 1))
    rows.append(r)
t = pd.DataFrame(rows); E = pd.DataFrame(ent); t.to_csv("research/macd_underwater_results.csv", index=False); E.to_csv("research/macd_underwater_trades.csv", index=False)
names = {"M": "纯MACD（全部金叉）", "UW": "只做水下金叉", "AW": "只做水上金叉"}
for label, g, Eg in (("回测≥3年全部", t[t.years >= 3], E[E.long]), ("MACD优秀 17 只", t[t.good], E[E.good])):
    print(f"\n==== {label}（{len(g)} 只）  一直持有：年化中位 {g.hold.median()*100:+.2f}，均值 {g.hold.mean()*100:+.2f}，回撤中位 {g.hold_dd.median()*100:.1f}")
    print(f"   {'规则':<16}{'年化中位':>8}{'年化均值':>8}{'胜纯MACD':>9}{'胜持有':>8}{'前后半都胜MACD':>13}{'回撤中位':>8}{'持仓':>6}{'笔数中位':>8}")
    for k in names:
        vs = f"{(g[k]>g.M).sum()}/{len(g)}" if k != "M" else "-"; both = f"{((g[k+'_h1']>g.M_h1)&(g[k+'_h2']>g.M_h2)).sum()}/{len(g)}" if k != "M" else "-"
        print(f"   {names[k]:<14}{g[k].median()*100:+8.2f}{g[k].mean()*100:+8.2f}{vs:>9}{(g[k]>g.hold).sum():>5}/{len(g)}{both:>10}{g[k+'_dd'].median()*100:8.1f}{g[k+'_exp'].median()*100:5.0f}%{g[k+'_n'].median():8.0f}")
    for lab, z in (("水下金叉", Eg[Eg.uw]), ("水上金叉", Eg[~Eg.uw])):
        print(f"   逐笔·{lab}：{len(z)} 轮，平均 {z.ret.mean()*100:+.2f}%，中位 {z.ret.median()*100:+.2f}%，胜率 {(z.ret>0).mean()*100:.0f}%，平均持有 {z.days.mean():.0f} 天，盈利时平均 {z[z.ret>0].ret.mean()*100:+.2f}%，亏损时平均 {z[z.ret<=0].ret.mean()*100:+.2f}%")
El = E[E.long]; real = El[El.uw].ret.mean() - El[~El.uw].ret.mean(); v = El.ret.values; nk = El.uw.sum(); rng = np.random.default_rng(0)
sims = [(lambda p: v[p[:nk]].mean() - v[p[nk:]].mean())(rng.permutation(len(v))) for _ in range(5000)]
print(f"\n置换检验：水下减水上的平均收益差 {real*100:+.2f}%，随机分组达到或超过的概率 {(np.array(sims) >= real).mean():.1%}")
El = El.assign(year=El.date.dt.year)
print("\n逐年（回测≥3年全部，逐笔平均收益 %）：水下 / 水上 / 水下轮数")
for y, z in El.groupby("year"):
    a, b = z[z.uw], z[~z.uw]
    if len(z) >= 20: print(f"   {y}  {a.ret.mean()*100:+6.2f} / {b.ret.mean()*100:+6.2f} / {len(a)}")
