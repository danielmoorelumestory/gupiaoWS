"""用上证指数的 10 日线信号去交易沪深300 或科创50。规则在跑之前写定：
信号来源：上证指数收盘价与它自己的 10 日均线（含当天）。
规则一：站上次日开盘买，跌破次日开盘卖。规则二：连续两日站上才买，一日跌破即卖。
成交：按被交易指数的次日开盘价。空仓现金零收益。费用单边 0 或 10 个基点。
沪深300 持仓过夜加回分红（全收益−价格）；科创50 没有全收益数据，不加分红。
对照：一直持有；以及用被交易指数自己的 10 日线发信号。除此之外不跑别的参数。"""
import numpy as np, pandas as pd
def load(code): return pd.read_csv(f"data/index_{code}_ohlc.csv", parse_dates=["date"]).set_index("date")
sse, hs, kc = load("sh000001"), load("sh000300"), load("sh000688")
tr = pd.read_csv("data/tr_H00300.csv", parse_dates=["date"]).set_index("date")["close"]
tr = tr[tr.index.isin(hs.index)]; tr = tr[~tr.index.duplicated()].reindex(hs.index)
div300 = (tr.pct_change() - hs.close.pct_change()).fillna(0.0).clip(lower=0)

def state(src, rule):
    """src 收盘后的目标仓位（True=持有）。"""
    a = (src.close > src.close.rolling(10).mean()).values; s = np.zeros(len(a), bool)
    if rule == 1: s = a.copy()
    else:
        for i in range(1, len(a)): s[i] = a[i] if s[i - 1] else (a[i] and a[i - 1])
    return pd.Series(s, index=src.index)

def simulate(tgt, st, start, cost, div=None):
    """逐日循环撮合：t 日收盘看 st[t]，t+1 日开盘成交。返回日净值和逐笔收益。"""
    st = st.reindex(tgt.index).fillna(False); idx = tgt.loc[start:].index; o, c = tgt.open, tgt.close
    dv = div if div is not None else pd.Series(0.0, index=tgt.index)
    pos = tgt.index.get_indexer(idx); nav = 1.0; hold = False; navs = []; trades = []; entry = None
    for k in pos:
        want = bool(st.iloc[k - 1])                               # 昨天收盘后的信号
        if hold: nav *= o.iloc[k] / c.iloc[k - 1] + dv.iloc[k]    # 过夜：昨收 → 今开，含除息
        if want != hold:
            nav *= 1 - cost
            if want: entry = nav / (1 - cost)                      # 买入前的净值，逐笔收益含买卖两次费用
            elif entry is not None: trades.append(nav / entry - 1)
            hold = want
        if hold: nav *= c.iloc[k] / o.iloc[k]                     # 今开 → 今收
        navs.append(nav)
    return pd.Series(navs, index=idx), np.array(trades)

def report(label, nav, trades, held_share=None):
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25; dd = (nav / nav.cummax() - 1).min()
    s = f"  {label:<26} 年化 {(nav.iloc[-1] ** (1/yrs) - 1)*100:+6.2f}%  回撤 {dd*100:6.1f}%  净值 {nav.iloc[-1]:5.2f}"
    if len(trades): s += f"  {len(trades):3d} 笔  胜率 {(trades > 0).mean()*100:4.1f}%  每笔 {trades.mean()*100:+.2f}%"
    print(s); return nav

def block(name, tgt, start, div, own_name):
    print(f"\n=== 交易 {name}，{start} 起 ===")
    allnav = {}
    allnav["hold"] = report("一直持有", *simulate(tgt, pd.Series(True, index=tgt.index), start, 0.0, div))
    for cost in (0.0, 0.001):
        print(f" 单边费用 {cost*1e4:.0f} 个基点：")
        for rule in (1, 2):
            for src, sn in ((tgt, own_name), (sse, "上证")):
                allnav[sn, rule, cost] = report(f"{sn}信号·规则{'一' if rule == 1 else '二'}", *simulate(tgt, state(src, rule), start, cost, div))
    ann = lambda n: n.groupby(n.index.year).last() / n.groupby(n.index.year).last().shift(1).fillna(1.0) - 1
    cols = [("一直持有", "hold"), (f"{own_name}·一", (own_name, 1, 0.001)), ("上证·一", ("上证", 1, 0.001)), (f"{own_name}·二", (own_name, 2, 0.001)), ("上证·二", ("上证", 2, 0.001))]
    t = pd.concat([ann(allnav[k]) for _, k in cols], axis=1); t.columns = [c for c, _ in cols]
    print(" 逐年收益（%，10 个基点）：" + " ｜ ".join(t.columns))
    for y, row in t.iterrows(): print(f"  {y}: " + " ｜ ".join(f"{v*100:+7.1f}" for v in row))
    print(f"  跑赢一直持有的年份：" + "，".join(f"{c} {(t[c] > t['一直持有']).sum()}/{len(t)}" for c in t.columns[1:]))
    print(f"  上证信号跑赢自身信号的年份：规则一 {(t['上证·一'] > t[f'{own_name}·一']).sum()}/{len(t)}，规则二 {(t['上证·二'] > t[f'{own_name}·二']).sum()}/{len(t)}")

# 两个信号来源有多不一样
for nm, tgt in (("沪深300", hs.loc["2005-01-04":]), ("科创50", kc.iloc[10:])):
    a = state(tgt if nm == "科创50" else hs, 1).reindex(tgt.index); b = state(sse, 1).reindex(tgt.index)
    print(f"{nm} 自身信号与上证信号同向的交易日占比：{(a == b).mean()*100:.1f}%")
block("沪深300", hs, "2005-01-04", div300, "300")
block("沪深300", hs, "2012-01-01", div300, "300")
block("科创50", kc, "2020-01-16", None, "科创")       # 科创50 自己的 10 日线从第 10 个交易日起才有值
