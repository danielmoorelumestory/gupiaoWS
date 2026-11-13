"""钝化后破均线卖出（运行前写定，跑完不改）。买入：MACD 金叉次日开盘。卖出：死叉，或“警示后收盘 < MA_n”，先到先卖，次日开盘成交。
警示：DH 顶部钝化 = 收盘为近 10 日（含当天）最高收盘，且 DIF 低于近 10 日最高 DIF；
      W5 5 日背离 = 今收 > 5 日前收 且 DIF 今 < DIF 5 日前；NONE = 不需要警示。
规则：DH5（钝化+MA5，主规则）、DH10（钝化+MA10）、W55（5日背离+MA5）、W510（5日背离+MA10，上次的）、B5（直接破MA5）、M（纯MACD）。
被均线卖出后须等死叉再金叉才重新买入。其余数据、成本、样本同 macd_exit_divergence.py；汇总只统计回测期≥3年。
另做逐笔评估：提前卖出价/死叉卖出价 − 1（复权开盘价）。"""
import json, numpy as np, pandas as pd
src = open("research/macd_etf.py").read()
exec(src.split("picked = json.load")[0]); END = "2026-11-10"
exec("def events" + src.split("def events")[1].split("rows, logs = [], {}")[0])
good = set(pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}).query("good").code)
RULES = {"DH5": ("DH", 5), "DH10": ("DH", 10), "W55": ("W5", 5), "W510": ("W5", 10), "B5": ("NONE", 5)}

def ind(adj):
    s = adj; dif = (s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()); dea = dif.ewm(span=9, adjust=False).mean()
    return s.values, dif.values, dea.values, {5: s.rolling(5).mean().values, 10: s.rolling(10).mean().values}, s.rolling(10).max().values, dif.rolling(10).max().values

def positions(adj, warn_kind, n):
    c, dif, dea, ma, cmax, dmax = ind(adj); ma = ma[n]
    pos = np.zeros(len(c), bool); hold = False; armed = True; warn = False
    for t in range(1, len(c)):
        if dif[t] <= dea[t]: armed = True
        if hold:
            if dif[t] < dea[t]: hold = False
            else:
                if warn_kind == "DH" and t >= 9 and c[t] >= cmax[t] and dif[t] < dmax[t]: warn = True
                if warn_kind == "W5" and t >= 5 and c[t] > c[t-5] and dif[t] < dif[t-5]: warn = True
                if (warn_kind == "NONE" or warn) and not np.isnan(ma[t]) and c[t] < ma[t]: hold = False; armed = False
        elif dif[t] > dea[t] and armed: hold = True; warn = False
        pos[t] = hold
    return pd.Series(pos, index=adj.index)

rows, ev = [], []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code); i0 = 60
    if len(d) < 120: continue
    years = (d.index[-1] - d.index[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    h, _ = backtest(d, dv, mult, pd.Series(True, index=d.index), i0, 0.0)
    r = dict(code=code, name=name, years=years, good=code in good, hold=ann(h), hold_dd=mdd(h))
    _, dif, dea, _, _, _ = ind(adj); m = dif > dea; ao = (d.open * adj / d.close).values
    sts = {"M": macd_state(adj), **{k: positions(adj, *v) for k, v in RULES.items()}}
    for k, st in sts.items():
        n, tr = backtest(d, dv, mult, st, i0, 0.001)
        a, _ = backtest(d.iloc[:mid + 1], dv.iloc[:mid + 1], mult.iloc[:mid + 1], st.iloc[:mid + 1], i0, 0.001); b, _ = backtest(d, dv, mult, st, mid, 0.001)
        r[k], r[k + "_dd"], r[k + "_n"], r[k + "_exp"], r[k + "_h1"], r[k + "_h2"] = ann(n), mdd(n), len(tr), st.iloc[i0:].mean(), ann(a), ann(b)
        if k == "M": continue
        sv = st.values
        for i in range(max(61, i0 + 1), len(d) - 1):
            if sv[i - 1] and not sv[i] and m[i]:
                j = i
                while j < len(d) - 1 and m[j]: j += 1
                if j < len(d) - 1: ev.append(dict(rule=k, code=code, good=code in good, days=j - i, gain=ao[i + 1] / ao[j + 1] - 1))
    rows.append(r)
t = pd.DataFrame(rows); e = pd.DataFrame(ev); t.to_csv("research/macd_exit_dunhua_results.csv", index=False); e.to_csv("research/macd_exit_dunhua_events.csv", index=False)
names = {"M": "纯MACD", "DH5": "钝化后破MA5", "DH10": "钝化后破MA10", "W55": "5日背离后破MA5", "W510": "5日背离后破MA10", "B5": "直接破MA5"}
for label, g, ge in (("回测≥3年全部", t[t.years >= 3], e[e.code.isin(t[t.years >= 3].code)]), ("MACD优秀 17 只", t[t.good], e[e.good])):
    print(f"\n==== {label}（{len(g)} 只）  一直持有：年化中位 {g.hold.median()*100:+.2f}，回撤中位 {g.hold_dd.median()*100:.1f}")
    print(f"   {'规则':<14}{'年化中位':>8}{'年化均值':>8}{'胜纯MACD':>9}{'前后半都胜':>9}{'回撤中位':>8}{'回撤更小':>8}{'持仓':>6} | {'提前卖出':>6}{'卖对':>6}{'每次平均':>8}{'距死叉':>6}")
    for k in names:
        vs = f"{(g[k]>g.M).sum()}/{len(g)}" if k != "M" else "-"; both = f"{((g[k+'_h1']>g.M_h1)&(g[k+'_h2']>g.M_h2)).sum()}/{len(g)}" if k != "M" else "-"
        dd = f"{(g[k+'_dd']>g.M_dd).sum()}/{len(g)}" if k != "M" else "-"
        x = ge[ge.rule == k]; evs = f"{len(x):>6}{(x.gain>0).mean()*100:5.0f}%{x.gain.mean()*100:+8.2f}{x.days.median():6.0f}天" if len(x) else ""
        print(f"   {names[k]:<12}{g[k].median()*100:+8.2f}{g[k].mean()*100:+8.2f}{vs:>9}{both:>9}{g[k+'_dd'].median()*100:8.1f}{dd:>8}{g[k+'_exp'].median()*100:5.0f}% | {evs}")
rng = np.random.default_rng(0); base = e[e.rule == "B5"].gain.values
for k in ("DH5", "W55"):
    w = e[e.rule == k].gain.values; sims = np.array([rng.choice(base, len(w), replace=False).mean() for _ in range(20000)])
    print(f"\n{names[k]}：{len(w)} 次平均 {w.mean()*100:+.2f}%；从“直接破MA5”{len(base)} 次中随机抽同样多次，平均 ≥ 它的概率 {(sims >= w.mean()).mean():.1%}；去掉最好 3 次后平均 {np.sort(w)[:-3].mean()*100:+.2f}%")
print("\n==== MACD优秀 逐只年化（%）")
for _, r in t[t.good].sort_values("M", ascending=False).iterrows():
    print(f"   {r.code} {r['name']:<12} 持有{r.hold*100:+6.1f} 纯MACD{r.M*100:+6.1f} 钝化MA5{r.DH5*100:+6.1f} 钝化MA10{r.DH10*100:+6.1f} 背离MA5{r.W55*100:+6.1f} 直接MA5{r.B5*100:+6.1f}")
