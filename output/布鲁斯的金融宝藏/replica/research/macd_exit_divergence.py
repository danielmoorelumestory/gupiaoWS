"""卖出规则对比（运行前写定，跑完不改）。买入都一样：MACD 金叉（DIF 上穿 DEA，信号日次日开盘买）。
  M  纯 MACD：死叉卖。
  W1 动能减弱后破 10 日线：持仓期间出现“上涨日红柱缩短”（今收>昨收 且 0<柱今<柱昨，柱=DIF−DEA）即记警示；
     警示后收盘 < MA10 卖；死叉照常卖；先到先卖。
  W5 同 W1，警示改为“5 日价格上涨而 DIF 走低”：今收>5 日前收 且 DIF今<DIF 5 日前。
  B  直接破 10 日线：收盘 < MA10 或死叉即卖（不需要警示）。
被 10 日线卖出后，须等 DIF 回到 DEA 下方（死叉）后再次金叉才重新买入；回测起点若已是 DIF>DEA 视同可买。
价格：复权连续价（等价前复权）算 MACD 与 MA10；成交用实际开盘价，分红拆分按实际记录；单边 0.1%；一直持有 0 费。
样本：页面清单 62 只 + 半导体ETF，上市后第 60 个交易日起至 2026-11-10；汇总只统计回测期 ≥3 年的。"""
import json, numpy as np, pandas as pd
src = open("research/macd_etf.py").read()
exec(src.split("picked = json.load")[0]); END = "2026-11-10"
exec("def events" + src.split("def events")[1].split("rows, logs = [], {}")[0])
good = set(pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}).query("good").code)

def positions(adj, rule):
    c = adj.values
    s = pd.Series(c); dif = (s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()).values
    dea = pd.Series(dif).ewm(span=9, adjust=False).mean().values; hist = dif - dea; ma = s.rolling(10).mean().values
    pos = np.zeros(len(c), bool); hold = False; armed = True; warn = False
    for t in range(1, len(c)):
        if dif[t] <= dea[t]: armed = True
        if hold:
            if dif[t] < dea[t]: hold = False
            else:
                if rule == "W1" and c[t] > c[t-1] and 0 < hist[t] < hist[t-1]: warn = True
                if rule == "W5" and t >= 5 and c[t] > c[t-5] and dif[t] < dif[t-5]: warn = True
                if (rule == "B" or (rule in ("W1", "W5") and warn)) and not np.isnan(ma[t]) and c[t] < ma[t]:
                    hold = False; armed = False
        else:
            if dif[t] > dea[t] and armed: hold = True; warn = False
        pos[t] = hold
    return pd.Series(pos, index=adj.index)

rows = []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code); i0 = 60
    if len(d) < 120: continue
    years = (d.index[-1] - d.index[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    h, _ = backtest(d, dv, mult, pd.Series(True, index=d.index), i0, 0.0)
    r = dict(code=code, name=name, years=years, good=code in good, hold=ann(h), hold_dd=mdd(h))
    for rule in ("M", "W1", "W5", "B"):
        st = macd_state(adj) if rule == "M" else positions(adj, rule)
        n, tr = backtest(d, dv, mult, st, i0, 0.001)
        r[rule] = ann(n); r[rule + "_dd"] = mdd(n); r[rule + "_n"] = len(tr); r[rule + "_exp"] = st.iloc[i0:].mean()
        a, _ = backtest(d.iloc[:mid + 1], dv.iloc[:mid + 1], mult.iloc[:mid + 1], st.iloc[:mid + 1], i0, 0.001)
        b, _ = backtest(d, dv, mult, st, mid, 0.001); r[rule + "_h1"], r[rule + "_h2"] = ann(a), ann(b)
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/macd_exit_divergence_results.csv", index=False)
names = {"M": "纯MACD", "W1": "红柱缩短后破MA10", "W5": "5日背离后破MA10", "B": "直接破MA10"}
for label, g in (("回测≥3年全部", t[t.years >= 3]), ("MACD优秀 17 只", t[t.good])):
    print(f"\n==== {label}（{len(g)} 只；年化、回撤取中位数，%）")
    print(f"   {'规则':<16}{'年化中位':>8}{'比持有高':>9}{'比纯MACD高':>11}{'回撤中位':>9}{'回撤小于纯MACD':>14}{'前后半都胜纯MACD':>16}{'笔数中位':>8}{'持仓时间':>8}")
    for k in ("M", "W1", "W5", "B"):
        vsM = (g[k] > g.M).sum() if k != "M" else "-"; dd = (g[k + "_dd"] > g.M_dd).sum() if k != "M" else "-"
        both = ((g[k + "_h1"] > g.M_h1) & (g[k + "_h2"] > g.M_h2)).sum() if k != "M" else "-"
        print(f"   {names[k]:<14}{g[k].median()*100:+8.2f}{(g[k]>g.hold).sum():>6}/{len(g)}{str(vsM):>8}/{len(g)}{g[k+'_dd'].median()*100:9.1f}{str(dd):>10}/{len(g)}{str(both):>12}/{len(g)}{g[k+'_n'].median():8.0f}{g[k+'_exp'].median()*100:7.0f}%")
    print(f"   一直持有 年化中位 {g.hold.median()*100:+.2f}，回撤中位 {g.hold_dd.median()*100:.1f}")
print("\n==== MACD优秀 逐只（年化 % / 最大回撤 %）")
for _, r in t[t.good].sort_values("M", ascending=False).iterrows():
    print(f"   {r.code} {r['name']:<12} 持有 {r.hold*100:+6.1f}/{r.hold_dd*100:5.0f} | 纯MACD {r.M*100:+6.1f}/{r.M_dd*100:5.0f} | 红柱缩短 {r.W1*100:+6.1f}/{r.W1_dd*100:5.0f} | 5日背离 {r.W5*100:+6.1f}/{r.W5_dd*100:5.0f} | 直接破MA10 {r.B*100:+6.1f}/{r.B_dd*100:5.0f}")
