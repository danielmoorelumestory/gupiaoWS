"""用户规则：10 日线配合 MACD。运行前写定，不调参数：
MACD 用通用参数 12/26/9：DIF = EMA12 − EMA26（收盘价），DEA = DIF 的 9 日 EMA。金叉 = DIF 上穿 DEA，死叉 = 下穿。
规则 A（主口径）：收盘在 10 日线上方 且 DIF > DEA 时持有。两个条件中后满足的那天收盘后成立，下一个交易日开盘买；
  任意一个不再满足（跌破 10 日线或死叉），下一个交易日开盘卖。
规则 B（严格口径，敏感性）：要求“上穿 10 日线”和“金叉”两个事件都在最近 5 个交易日内发生，且后到那天两个条件都还成立才买；卖出同 A。
对照：只用 10 日线；只用 MACD（金叉买、死叉卖）；一直持有。
撮合沿用经审计的 backtest()：t 日收盘决定，t+1 开盘成交，起点现金开始，价格指数不计分红，单边 0 或 10 个基点。"""
import io, contextlib, numpy as np, pandas as pd
src = open("research/ma10_regime.py", encoding="utf-8").read().split("# ---------------------------------------------------------------- 一、诊断")[0]
with contextlib.redirect_stdout(io.StringIO()): exec(src)
import builtins
def run_cost(d, st, start, cost):
    global COST
    old = COST; globals()["COST"] = cost
    try: return backtest(d, st, start)
    finally: globals()["COST"] = old

def macd(c):
    dif = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    return dif, dif.ewm(span=9, adjust=False).mean()

def rules(d):
    c = d.close; above = c > c.rolling(10).mean(); dif, dea = macd(c); pos = dif > dea
    up10 = above & ~above.shift(1, fill_value=False); gold = pos & ~pos.shift(1, fill_value=False)
    A = above & pos
    # 规则 B：空仓时要两个事件都在最近 5 天内、且当天两条件都成立；持有时任一条件失效即卖
    r10 = up10.rolling(5).max().fillna(0).astype(bool); rg = gold.rolling(5).max().fillna(0).astype(bool)
    entry = (A & r10 & rg).values; a = A.values; s = np.zeros(len(a), bool)
    for i in range(1, len(a)): s[i] = a[i] if s[i - 1] else entry[i]
    return {"10日线+MACD": A, "严格版(5日内)": pd.Series(s, index=d.index), "只用10日线": above, "只用MACD": pos}

def summary(nav, trades, d, a):
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    t = np.array([r for _, r in trades]) if trades else np.array([])
    return ann(nav), mdd(nav), len(t), (t > 0).mean() if len(t) else np.nan

for cost in (0.001, 0.0):
    for label, period in (("检验期（2016 年起，科创50 从 2020-07-23）", "test"), ("全部（2006 年起；中证1000 2015-07、创业板 2011-06、科创50 2020-07-23）", "all")):
        print(f"\n==== 单边费用 {cost*1e4:.0f} 个基点 · {label}")
        print(f"   {'':<8}" + "".join(f"{k:>16}" for k in ["10日线+MACD", "严格版(5日内)", "只用10日线", "只用MACD", "一直持有"]))
        wins = {k: 0 for k in ["10日线+MACD", "严格版(5日内)", "只用MACD"]}; beat_hold = dict(wins)
        for c in ["sh000300", "sh000001", "sh000016", "sh000905", "sh000852", "sz399006", "sh000688"]:
            d = D[c]; a = ("2020-07-23" if c == "sh000688" else "2016-01-01") if period == "test" else START.get(c, "2006-01-04")
            res = {}
            for k, st in rules(d).items():
                nav, tr = run_cost(d, st, a, cost); res[k] = summary(nav, tr, d, a)
            h = hold_nav(d, a); res["一直持有"] = (ann(h), mdd(h), 0, np.nan)
            for k in wins:
                wins[k] += res[k][0] > res["只用10日线"][0]; beat_hold[k] += res[k][0] > res["一直持有"][0]
            print(f"   {NAMES[c]:<6}年化 " + "".join(f"{res[k][0]*100:+15.2f}%" for k in res))
            print(f"   {'':<6}回撤 " + "".join(f"{res[k][1]*100:15.1f}%" for k in res))
            print(f"   {'':<6}笔数 " + "".join(f"{res[k][2]:16d}" for k in list(res)[:4]) + f"{'—':>16}")
            print(f"   {'':<6}胜率 " + "".join(f"{res[k][3]*100:15.1f}%" for k in list(res)[:4]) + f"{'—':>16}")
        print("   年化高于“只用10日线”的指数数：" + "，".join(f"{k} {v}/7" for k, v in wins.items()) + "；高于一直持有：" + "，".join(f"{k} {v}/7" for k, v in beat_hold.items()))
