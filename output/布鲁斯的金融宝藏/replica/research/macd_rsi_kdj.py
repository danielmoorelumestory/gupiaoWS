"""MACD 结合 RSI / KDJ（运行前写定，跑完不改）。RSI14（Wilder 平滑）；KDJ 9,3,3（RSV 用复权高低收，K、D 初值 50，K=2/3K昨+1/3RSV）。
A 买入过滤（金叉当日判断，不满足则跳过这一轮金叉；卖出仍为死叉）：R50 RSI>50；R70 RSI<70；KD K>D；J100 J<100。
B 增加卖出（死叉照常卖，先到先卖；被提前卖出后等下一次金叉）：RSIX RSI 由 ≥70 跌破 70；KDX K 下穿 D 且前一日 K>80。
成交：信号日次日开盘；单边 0.1%；一直持有 0 费。样本：页面清单+半导体，上市后第 60 个交易日起，汇总只统计回测期≥3 年。
逐笔：A 类比较“过滤后买入”与“被跳过”的金叉交易各自的收益（纯 MACD 那一轮的开盘买到开盘卖，含 0.2% 成本）；
      B 类比较提前卖出价/死叉卖出价 − 1。"""
import json, numpy as np, pandas as pd
src = open("research/macd_etf.py").read()
exec(src.split("picked = json.load")[0]); END = "2026-11-10"
exec("def events" + src.split("def events")[1].split("rows, logs = [], {}")[0])
good = set(pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}).query("good").code)

def indicators(d, adj):
    f = adj / d.close; c = adj; hi = d.high * f; lo = d.low * f
    dif = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean(); dea = dif.ewm(span=9, adjust=False).mean()
    ch = c.diff(); up = ch.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); dn = (-ch.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan)); rsi = rsi.fillna(100)
    hh = hi.rolling(9, min_periods=1).max(); ll = lo.rolling(9, min_periods=1).min(); rsv = ((c - ll) / (hh - ll).replace(0, np.nan) * 100).fillna(50)
    K = np.zeros(len(c)); D = np.zeros(len(c)); k = dd = 50.0
    for i, v in enumerate(rsv.values): k = 2/3*k + v/3; dd = 2/3*dd + k/3; K[i], D[i] = k, dd
    return dict(dif=dif.values, dea=dea.values, rsi=rsi.values, K=K, D=D, J=3*K - 2*D)

ENTRY = {"R50": lambda x, t: x["rsi"][t] > 50, "R70": lambda x, t: x["rsi"][t] < 70, "KD": lambda x, t: x["K"][t] > x["D"][t], "J100": lambda x, t: x["J"][t] < 100}
EXIT = {"RSIX": lambda x, t: x["rsi"][t-1] >= 70 and x["rsi"][t] < 70, "KDX": lambda x, t: x["K"][t-1] > 80 and x["K"][t-1] >= x["D"][t-1] and x["K"][t] < x["D"][t]}

def positions(x, entry=None, exit_=None):
    dif, dea = x["dif"], x["dea"]; n = len(dif); pos = np.zeros(n, bool); hold = False; armed = True
    for t in range(1, n):
        cross_up = dif[t] > dea[t] and dif[t-1] <= dea[t-1]
        if dif[t] <= dea[t]: armed = True
        if hold:
            if dif[t] < dea[t]: hold = False
            elif exit_ and EXIT[exit_](x, t): hold = False; armed = False
        else:
            if entry: hold = cross_up and ENTRY[entry](x, t)
            else: hold = dif[t] > dea[t] and armed
        pos[t] = hold
    return pos

rows, ent, exv = [], [], []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code); i0 = 60
    if len(d) < 120: continue
    x = indicators(d, adj); idx = d.index; ao = (d.open * adj / d.close).values; m = x["dif"] > x["dea"]
    years = (idx[-1] - idx[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    h, _ = backtest(d, dv, mult, pd.Series(True, index=idx), i0, 0.0)
    r = dict(code=code, name=name, years=years, good=code in good, hold=ann(h), hold_dd=mdd(h))
    sts = {"M": macd_state(adj).values, **{k: positions(x, entry=k) for k in ENTRY}, **{k: positions(x, exit_=k) for k in EXIT}}
    for k, sv in sts.items():
        st = pd.Series(sv, index=idx); n_, tr = backtest(d, dv, mult, st, i0, 0.001)
        a, _ = backtest(d.iloc[:mid + 1], dv.iloc[:mid + 1], mult.iloc[:mid + 1], st.iloc[:mid + 1], i0, 0.001); b, _ = backtest(d, dv, mult, st, mid, 0.001)
        r[k], r[k + "_dd"], r[k + "_exp"], r[k + "_h1"], r[k + "_h2"] = ann(n_), mdd(n_), st.iloc[i0:].mean(), ann(a), ann(b)
    # 逐笔：每一轮金叉交易（信号日 t，t+1 开盘买；死叉信号日 j，j+1 开盘卖）
    for t in range(i0, len(d) - 1):
        if m[t] and not m[t-1]:
            j = t
            while j < len(d) - 1 and m[j]: j += 1
            if j >= len(d) - 1: continue
            ret = ao[j + 1] / ao[t + 1] * (0.999 ** 2) - 1
            ent.append(dict(code=code, good=code in good, ret=ret, **{k: bool(ENTRY[k](x, t)) for k in ENTRY}))
            for k in EXIT:
                for s in range(t + 1, j + 1):
                    if EXIT[k](x, s):
                        if s < j: exv.append(dict(rule=k, code=code, good=code in good, days=j - s, gain=ao[s + 1] / ao[j + 1] - 1))
                        break
    rows.append(r)
t = pd.DataFrame(rows); E = pd.DataFrame(ent); X = pd.DataFrame(exv)
t.to_csv("research/macd_rsi_kdj_results.csv", index=False); E.to_csv("research/macd_rsi_kdj_entries.csv", index=False); X.to_csv("research/macd_rsi_kdj_exits.csv", index=False)
names = {"M": "纯MACD", "R50": "金叉+RSI>50", "R70": "金叉+RSI<70", "KD": "金叉+K>D", "J100": "金叉+J<100", "RSIX": "加卖:RSI超买回落", "KDX": "加卖:KDJ高位死叉"}
long = set(t[t.years >= 3].code)
for label, g, Eg, Xg in (("回测≥3年全部", t[t.years >= 3], E[E.code.isin(long)], X[X.code.isin(long)]), ("MACD优秀 17 只", t[t.good], E[E.good], X[X.good])):
    print(f"\n==== {label}（{len(g)} 只）  一直持有：年化中位 {g.hold.median()*100:+.2f}，回撤中位 {g.hold_dd.median()*100:.1f}")
    print(f"   {'规则':<14}{'年化中位':>8}{'年化均值':>8}{'胜纯MACD':>9}{'前后半都胜':>9}{'回撤中位':>8}{'回撤更小':>8}{'持仓':>6}")
    for k in names:
        vs = f"{(g[k]>g.M).sum()}/{len(g)}" if k != "M" else "-"; both = f"{((g[k+'_h1']>g.M_h1)&(g[k+'_h2']>g.M_h2)).sum()}/{len(g)}" if k != "M" else "-"
        dd = f"{(g[k+'_dd']>g.M_dd).sum()}/{len(g)}" if k != "M" else "-"
        print(f"   {names[k]:<12}{g[k].median()*100:+8.2f}{g[k].mean()*100:+8.2f}{vs:>9}{both:>9}{g[k+'_dd'].median()*100:8.1f}{dd:>8}{g[k+'_exp'].median()*100:5.0f}%")
    print(f"   逐笔·买入过滤（共 {len(Eg)} 轮金叉交易，平均每轮 {Eg.ret.mean()*100:+.2f}%，胜率 {(Eg.ret>0).mean()*100:.0f}%）：")
    for k in ENTRY:
        a, b = Eg[Eg[k]], Eg[~Eg[k]]
        print(f"     {names[k]:<12} 买入 {len(a):4d} 轮 平均 {a.ret.mean()*100:+6.2f}% 胜率 {(a.ret>0).mean()*100:3.0f}% | 跳过 {len(b):4d} 轮 平均 {b.ret.mean()*100:+6.2f}% 胜率 {(b.ret>0).mean()*100:3.0f}%")
    print("   逐笔·提前卖出（提前卖出价/死叉卖出价 − 1）：")
    for k in EXIT:
        z = Xg[Xg.rule == k]
        print(f"     {names[k]:<12} {len(z):4d} 次 卖对 {(z.gain>0).mean()*100:3.0f}% 平均 {z.gain.mean()*100:+6.2f}% 中位 {z.gain.median()*100:+6.2f}% 距死叉中位 {z.days.median():.0f} 天")
# 置换检验：买入过滤的“买入组平均 − 跳过组平均”是否超出随机分组
rng = np.random.default_rng(0); El = E[E.code.isin(long)]
print("\n==== 置换检验（回测≥3年全部）：随机把同样多轮交易划为“买入组”，差值 ≥ 实际差值的概率")
for k in ENTRY:
    real = El[El[k]].ret.mean() - El[~El[k]].ret.mean(); nk = El[k].sum(); v = El.ret.values
    sims = []
    for _ in range(5000):
        p = rng.permutation(len(v)); sims.append(v[p[:nk]].mean() - v[p[nk:]].mean())
    print(f"   {names[k]:<12} 实际差 {real*100:+.2f}%  随机达到或超过的概率 {(np.array(sims) >= real).mean():.1%}")
