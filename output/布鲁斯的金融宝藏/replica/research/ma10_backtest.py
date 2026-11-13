"""10 日均线穿越回测。规则在跑之前写定，不事后换参数：
信号：收盘价 > 10 日均线（含当天）记为线上；从线下（含等于）到线上为站上，反之为跌破。
成交：信号日的下一个交易日开盘价买入或卖出。空仓拿现金，收益记 0。
费用：每次买或卖按成交额收 0 或 10 个基点，两档都报。
分红：指数是价格指数，持仓过夜时把当天"全收益指数涨幅 − 价格指数涨幅"加回来。
对照：同期一直持有（同样加回分红）。
附带一个事先写定的组合：收盘价同时在 10 日线和 200 日线之上才持有。除此之外不跑别的均线或组合。"""
import numpy as np, pandas as pd
d = pd.read_csv("data/index_sh000300_ohlc.csv", parse_dates=["date"]).set_index("date")
tr = pd.read_csv("data/tr_H00300.csv", parse_dates=["date"]).set_index("date")["close"]
import sys; START = sys.argv[1] if len(sys.argv) > 1 else "2005-01-04"   # 可在命令行指定起点
tr = tr[tr.index.isin(d.index)]; tr = tr[~tr.index.duplicated()].reindex(d.index)
div = (tr.pct_change() - d.close.pct_change()).fillna(0.0).clip(lower=0)      # 当日除息带来的差
ma10 = d.close.rolling(10).mean(); ma200 = d.close.rolling(200).mean()
print("开盘价与收盘价完全相同的天数（2005 年起）：", int((d.open == d.close).loc[START:].sum()), "/", len(d.loc[START:]))

def run(state, cost, label):
    """state[t]：t 日收盘后是否应持有。t+1 开盘按 state[t] 调仓。"""
    held = state.shift(1).fillna(False).astype(bool)                            # t 日开盘之后是否持有
    prev = held.shift(1).fillna(False).astype(bool)                             # t 日开盘之前（过夜）是否持有
    night = d.open / d.close.shift(1) - 1 + div                                 # 昨收 → 今开，含除息
    day = d.close / d.open - 1                                                  # 今开 → 今收
    trade = held != prev
    r = (1 + night.where(prev, 0.0)) * (1 - cost * trade) * (1 + day.where(held, 0.0)) - 1
    r = r.loc[START:]; held_ = held.loc[START:]; trade_ = trade.loc[START:]
    nav = (1 + r).cumprod(); yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    dd = (nav / nav.cummax() - 1).min()
    # 逐笔：买入开盘到卖出开盘
    buys = list(trade_[trade_ & held_].index); sells = list(trade_[trade_ & ~held_].index)
    if sells and buys and sells[0] < buys[0]: sells = sells[1:]
    n = min(len(buys), len(sells)); idx = d.index
    tr_ret = []
    for b, s in zip(buys[:n], sells[:n]):
        seg = r.loc[b:s]; tr_ret.append((1 + seg).prod() - 1)
    tr_ret = np.array(tr_ret); days = [idx.get_loc(s) - idx.get_loc(b) for b, s in zip(buys[:n], sells[:n])]
    print(f"\n【{label}｜单边费用 {cost*1e4:.0f} 个基点】")
    print(f"  期末净值 {nav.iloc[-1]:.2f}，年化 {(nav.iloc[-1] ** (1/yrs) - 1)*100:+.2f}%，最大回撤 {dd*100:.1f}%，持仓天数占比 {held_.mean()*100:.0f}%")
    if n:
        w = tr_ret > 0
        print(f"  完整交易 {n} 笔（每年 {n/yrs:.1f} 笔），赚钱 {w.sum()} 笔（{w.mean()*100:.1f}%），平均每笔 {tr_ret.mean()*100:+.2f}%，中位数 {np.median(tr_ret)*100:+.2f}%")
        print(f"  赚钱的平均 {tr_ret[w].mean()*100:+.2f}%，亏钱的平均 {tr_ret[~w].mean()*100:+.2f}%，平均持有 {np.mean(days):.1f} 个交易日，中位数 {np.median(days):.0f}")
        top = np.sort(tr_ret)[::-1]; print(f"  最赚的 10 笔合计贡献（对数）占全部的 {np.log1p(top[:10]).sum()/np.log1p(tr_ret).sum()*100:.0f}%" if np.log1p(tr_ret).sum() > 0 else "  全部交易合计为负")
    return r, nav

hold = pd.Series(True, index=d.index)
out = {}
for cost in (0.0, 0.001):
    out["hold", cost] = run(hold, 0.0, "一直持有")[0] if cost == 0 else out["hold", 0.0]
    out["ma10", cost] = run(d.close > ma10, cost, "10 日线：站上买、跌破卖")[0]
    out["both", cost] = run((d.close > ma10) & (d.close > ma200), cost, "10 日线和 200 日线都在线上才持有")[0]

print("\n逐年收益（%）：一直持有 ｜ 10 日线 0 费用 ｜ 10 日线 10 基点 ｜ 双线 10 基点")
ann = lambda r: (1 + r).groupby(r.index.year).prod() - 1
t = pd.concat([ann(out["hold", 0.0]), ann(out["ma10", 0.0]), ann(out["ma10", 0.001]), ann(out["both", 0.001])], axis=1)
for y, row in t.iterrows(): print(f"  {y}: " + " ｜ ".join(f"{v*100:+7.1f}" for v in row))
print(f"  10 日线（10 基点）跑赢一直持有的年份：{(t.iloc[:,2] > t.iloc[:,0]).sum()} / {len(t)}")
print("\n分段年化（%）：一直持有 ｜ 10 日线 0 费用 ｜ 10 日线 10 基点 ｜ 双线 10 基点")
for a, b in (("2005-01-04", "2009-12-31"), ("2010-01-01", "2015-12-31"), ("2016-01-01", "2020-12-31"), ("2021-01-01", "2026-11-10"), ("2010-01-01", "2026-11-10")):
    f = lambda r: ((1 + r.loc[a:b]).prod() ** (365.25 / (pd.Timestamp(b) - pd.Timestamp(a)).days) - 1) * 100
    print(f"  {a[:4]}–{b[:4]}: " + " ｜ ".join(f"{f(out[k]):+6.1f}" for k in (("hold", 0.0), ("ma10", 0.0), ("ma10", 0.001), ("both", 0.001))))
# 隔夜与日内拆分：站上之后的收益来自哪一段
night = (d.open / d.close.shift(1) - 1).loc[START:]; day = (d.close / d.open - 1).loc[START:]
st = (d.close > ma10).shift(1).fillna(False).loc[START:]
print(f"\n信号日次日的开盘跳空：站上后平均 {night[st & ~st.shift(1, fill_value=False)].mean()*100:+.3f}%，跌破后平均 {night[~st & st.shift(1, fill_value=False)].mean()*100:+.3f}%（全部日子平均 {night.mean()*100:+.3f}%）")

# ---------------------------------------------------------------- 用户追加的规则：连续两日站上才买，一日跌破就卖
print("\n" + "=" * 20, "追加：连续两个交易日收盘在 10 日线之上，次日开盘买；任一日收盘不在线上，次日开盘卖")
above = (d.close > ma10)
def two_day(extra=None):
    s = np.zeros(len(d), bool); a = above.values; e = np.ones(len(d), bool) if extra is None else extra.values
    for i in range(1, len(d)):
        s[i] = (a[i] and e[i]) if s[i - 1] else (a[i] and a[i - 1] and e[i])
    return pd.Series(s, index=d.index)
o2 = {}
for cost in (0.0, 0.001):
    o2["two", cost] = run(two_day(), cost, "连续两日站上买、一日跌破卖")[0]
    o2["two200", cost] = run(two_day(d.close > ma200), cost, "同上，且要求在 200 日线之上")[0]
print("\n逐年收益（%）：一直持有 ｜ 一日站上 10 基点 ｜ 两日站上 0 费用 ｜ 两日站上 10 基点")
t = pd.concat([ann(out["hold", 0.0]), ann(out["ma10", 0.001]), ann(o2["two", 0.0]), ann(o2["two", 0.001])], axis=1)
for y, row in t.iterrows(): print(f"  {y}: " + " ｜ ".join(f"{v*100:+7.1f}" for v in row))
print(f"  两日站上（10 基点）跑赢一直持有的年份：{(t.iloc[:,3] > t.iloc[:,0]).sum()} / {len(t)}；跑赢一日站上（10 基点）的年份：{(t.iloc[:,3] > t.iloc[:,1]).sum()} / {len(t)}")
print("\n分段年化（%）：一直持有 ｜ 一日站上 10 基点 ｜ 两日站上 0 费用 ｜ 两日站上 10 基点")
for a, b in (("2005-01-04", "2009-12-31"), ("2010-01-01", "2015-12-31"), ("2016-01-01", "2020-12-31"), ("2021-01-01", "2026-11-10"), ("2010-01-01", "2026-11-10")):
    f = lambda r: ((1 + r.loc[a:b]).prod() ** (365.25 / (pd.Timestamp(b) - pd.Timestamp(a)).days) - 1) * 100
    print(f"  {a[:4]}–{b[:4]}: " + " ｜ ".join(f"{f(x):+6.1f}" for x in (out["hold", 0.0], out["ma10", 0.001], o2["two", 0.0], o2["two", 0.001])))
