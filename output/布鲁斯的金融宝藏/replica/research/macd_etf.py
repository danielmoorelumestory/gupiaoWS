"""MACD 在行业 ETF 上的回测，用 ETF 实际（未复权）开盘、收盘价，分红和份额拆分按实际记录处理。运行前写定：
品种选择规则：20 个行业关键词（半导体、芯片、证券、银行、医疗、医药、军工、新能源车、光伏、酒、煤炭、有色、计算机、传媒、消费、红利、
  房地产、钢铁、通信、人工智能）各取名称含该词、2020 年底前上市、当前规模最大的一只（东财 ETF 列表）；另加用户点名的科创半导体ETF（588170）
  和科创芯片ETF（588200），这两只上市晚，单独列出。
规则：MACD 12/26/9（ETF 收盘价），DIF > DEA 持有；金叉次日开盘买，死叉次日开盘卖；空仓现金零收益；单边 10 个基点（另报 0）。
起点：上市后第 60 个交易日开盘（留 MACD 预热），以现金开始；另报 2021-01-04 起的共同时段（只含 2020 年底前上市的 20 只）。截至 2026-11-10。
分红：东财“分红送配详情”的每份现金（结果缓存到 data/etf_*_events.json；分红≥昨收 2% 而开盘未跌掉一半的记录判为错配并剔除），除息日给前一天收盘的持有人，加在隔夜那一段（相当于收到即在开盘再投）；一直持有同样处理。
拆分：东财“拆分详情”的比例，在价格实际跳变的那天把持仓份额乘上比例。新浪累计分红只用来核对。"""
import json, re, numpy as np, pandas as pd, akshare as ak
END = "2026-11-10"
picked = json.load(open("data/etf_picked.json"))
EXTRA = {"588170": ["科创半导体（点名）", "科创半导体ETF华夏"], "588200": ["科创芯片（点名）", "科创芯片ETF嘉实"]}

def events(code):
    import os
    fn = f"data/etf_{code}_events.json"
    if os.path.exists(fn):
        j = json.load(open(fn)); return {pd.Timestamp(k): v for k, v in j["div"]}, [(pd.Timestamp(t), r) for t, r in j["spl"]]
    div, spl = {}, []
    try:
        f = ak.fund_open_fund_info_em(symbol=code, indicator="分红送配详情")
        for _, r in f.iterrows():
            m = re.search(r"派现金([\d.]+)元", str(r["每10份分红"])); div[pd.Timestamp(r["除息日"])] = float(m.group(1)) / 10
    except Exception: pass
    try:
        f = ak.fund_open_fund_info_em(symbol=code, indicator="拆分详情")
        for _, r in f.iterrows():
            a, b = str(r["拆分折算比例"]).split(":"); spl.append((pd.Timestamp(r["拆分折算日"]), float(b) / float(a)))
    except Exception: pass
    json.dump({"div": [[str(k.date()), v] for k, v in div.items()], "spl": [[str(t.date()), r] for t, r in spl]}, open(fn, "w"))
    return div, spl

def load(code):
    d = pd.read_csv(f"data/etf_{code}_raw.csv", parse_dates=["date"]).set_index("date").sort_index().loc[:END]
    d = d[~d.index.duplicated()]
    div, spl = events(code)
    dv = pd.Series(0.0, index=d.index); mult = pd.Series(1.0, index=d.index); log = []
    for t, x in div.items():
        k = d.index.searchsorted(t)
        if k >= len(d) or k == 0: continue
        exp, gap = x / d.close.iloc[k - 1], d.open.iloc[k] / d.close.iloc[k - 1] - 1
        # 核验：分红占昨收 ≥2% 时，开盘必须至少跌掉一半分红，否则判定该记录与这只 ETF 价格不符，不计入
        if exp >= 0.02 and gap > -0.5 * exp:
            log.append(f"剔除 {d.index[k].date()} 每份 {x:.4f}（应跳 {-exp:.1%}，实际 {gap:+.1%}）"); continue
        dv.iloc[k] += x; log.append(f"除息 {d.index[k].date()} 每份 {x:.4f}（应跳 {-exp:.1%}，实际 {gap:+.1%}）")
    for t, ratio in spl:
        ks = range(max(1, d.index.searchsorted(t) - 2), min(len(d), d.index.searchsorted(t) + 4))
        k = min(ks, key=lambda k: abs(np.log(d.close.iloc[k - 1] / d.open.iloc[k]) - np.log(ratio)))
        mult.iloc[k] = ratio; log.append(f"拆分 {d.index[k].date()} 1:{ratio:g}（昨收/今开 {d.close.iloc[k-1]/d.open.iloc[k]:.3f}）")
    # 用于计算 MACD 的连续价格：把拆分前的价格除以比例，并把分红加回（后复权思路，只影响信号，不影响成交价）
    # 收盘到收盘的总收益：(今收 + 每份分红) × 拆分比例 / 昨收，累乘成连续价格
    r = (d.close + dv) * mult / d.close.shift(1); r.iloc[0] = 1.0
    adj = d.close.iloc[0] * r.cumprod()
    return d, dv, mult, adj, log

def macd_state(c):
    dif = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    return dif > dif.ewm(span=9, adjust=False).mean()

def backtest(d, dv, mult, st, i0, cost):
    """t 日收盘定仓位，t+1 开盘成交。隔夜一段：(今开 × 拆分比例 + 每份分红 × 拆分比例) / 昨收。"""
    o, c, D, M, s = d.open.values, d.close.values, dv.values, mult.values, st.values
    nav = 1.0; hold = False; out = []; trades = []; entry = 1.0
    for k in range(i0, len(d)):
        want = bool(s[k - 1]) if st is not None else True
        if hold: nav *= (o[k] + D[k]) * M[k] / c[k - 1]
        if want != hold:
            if want: entry = nav
            else: trades.append(nav * (1 - cost) / entry - 1)
            nav *= 1 - cost; hold = want
        if hold: nav *= c[k] / o[k]
        out.append(nav)
    return pd.Series(out, index=d.index[i0:]), trades

def ann(nav): return nav.iloc[-1] ** (365.25 / (nav.index[-1] - nav.index[0]).days) - 1
def mdd(nav): return (nav / np.maximum(nav.cummax(), 1) - 1).min()

rows, logs = [], {}
allc = {**picked, **EXTRA}
for code, (kw, name) in allc.items():
    d, dv, mult, adj, log = load(code); logs[code] = log
    st = macd_state(adj); always = pd.Series(True, index=d.index)
    for per, start in (("上市后", d.index[60]), ("2021 起", pd.Timestamp("2021-01-04"))):
        if per == "2021 起" and code in EXTRA: continue
        i0 = d.index.searchsorted(start)
        if i0 < 60: continue
        h, _ = backtest(d, dv, mult, always, i0, 0.0)
        r = dict(code=code, kw=kw, name=name, per=per, start=d.index[i0].date(), hold=ann(h), hold_dd=mdd(h),
                 vol=np.log(d.close / d.close.shift()).iloc[i0:].std() * np.sqrt(244))
        for cost in (0.001, 0.0):
            nav, tr = backtest(d, dv, mult, st, i0, cost)
            r[f"m{int(cost*1e4)}"] = ann(nav); r[f"dd{int(cost*1e4)}"] = mdd(nav); r["n"] = len(tr); r[f"win{int(cost*1e4)}"] = np.mean(np.array(tr) > 0) if tr else np.nan
        rows.append(r)
t = pd.DataFrame(rows); t["ex"] = t.m10 - t.hold; t["ex0"] = t.m0 - t.hold
for per in ("上市后", "2021 起"):
    g = t[t.per == per].sort_values("ex", ascending=False)
    print(f"\n==== {per}（{'各自上市后第 60 个交易日起' if per == '上市后' else '2021-01-04 起，共同时段'}，至 {END}；年化 %）")
    print(f"   {'ETF':<16}{'起点':>12}{'一直持有':>9}{'MACD收0.1%':>11}{'差':>7}{'MACD不计费':>10}{'差':>7}{'持有回撤':>9}{'MACD回撤':>9}{'笔数':>5}{'胜率':>6}{'年化波动':>8}")
    for _, r in g.iterrows():
        print(f"   {r['name']:<14}{str(r.start):>12}{r.hold*100:+9.2f}{r.m10*100:+11.2f}{r.ex*100:+7.2f}{r.m0*100:+10.2f}{r.ex0*100:+7.2f}{r.hold_dd*100:9.1f}{r.dd10*100:9.1f}{r.n:5d}{r.win10*100:6.0f}{r.vol*100:8.1f}")
    base = g[~g.code.isin(EXTRA)]
    print(f"   规则选出的 20 只：MACD（收 0.1%）跑赢一直持有 {(base.ex > 0).sum()}/{len(base)}，平均差 {base.ex.mean()*100:+.2f}；不计费 {(base.ex0 > 0).sum()}/{len(base)}；"
          f"回撤更小 {(base.dd10 > base.hold_dd).sum()}/{len(base)}；年化波动与差的秩相关 {base.vol.rank().corr(base.ex.rank()):+.2f}")
print("\n==== 分红与拆分记录（东财），及新浪累计分红核对")
for code, log in logs.items():
    try:
        s = ak.fund_etf_dividend_sina(symbol=("sh" if code[0] in "5" else "sz") + code); sina = float(s["累计分红"].max()) if len(s) else 0.0
    except Exception: sina = float("nan")
    em = sum(float(x.split("每份 ")[1].split("（")[0]) for x in log if x.startswith("除息"))
    print(f"   {code} {allc[code][1]}：{'；'.join(log) if log else '无'}  | 东财每份合计 {em:.4f}，新浪累计 {sina:.4f}")
t.to_csv("research/macd_etf_results.csv", index=False)
