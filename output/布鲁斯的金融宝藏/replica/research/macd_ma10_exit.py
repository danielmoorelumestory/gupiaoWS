"""用户规则 C：MACD 金叉买入；跌破 10 日线或 MACD 死叉，任一出现就卖。运行前写定：
金叉 = 当天 DIF > DEA 且前一天 DIF <= DEA（MACD 12/26/9，与 ma10_macd.py 相同）。
空仓时只在金叉那天收盘后发出买入，下一个交易日开盘买；不管当时在不在 10 日线上方。
持有时，从买入后的第一个收盘起，只要收盘 <= 10 日线或 DIF <= DEA，下一个交易日开盘卖。
卖出后要等下一次金叉才再买（即使之后又站上 10 日线、MACD 仍在多头）。
敏感性 C'：金叉当天收盘已在 10 日线下方的，不买（否则次日买入后马上就满足卖出条件）。
对照：A（10 日线 + MACD 都满足才持有）、只用 MACD、只用 10 日线、一直持有。撮合、费用、样本同 ma10_macd.py。
另对沪深300 做含分红版本：持仓过夜加回（全收益涨幅 − 价格涨幅），不截断负值（同 Codex 13 号审计的有符号口径）。"""
import io, contextlib, numpy as np, pandas as pd
src = open("research/ma10_macd.py", encoding="utf-8").read().split("for cost in (0.001, 0.0):")[0]
with contextlib.redirect_stdout(io.StringIO()): exec(src)

def rule_c(d, skip_below=False):
    c = d.close; above = (c > c.rolling(10).mean()).values; dif, dea = macd(c); pos = (dif > dea).values
    gold = pos & ~np.r_[False, pos[:-1]]
    s = np.zeros(len(c), bool); just = np.zeros(len(c), bool); n_below = 0
    for i in range(1, len(c)):
        if s[i - 1]: s[i] = above[i] and pos[i]
        elif gold[i]:
            if not above[i]: n_below += 1
            s[i] = not (skip_below and not above[i])
    return pd.Series(s, index=d.index), n_below

KEYS = ["C 金叉买", "C' 线下金叉不买", "A 两者都满足", "只用MACD", "只用10日线", "一直持有"]
def all_rules(d):
    r = rules(d)
    return {"C 金叉买": rule_c(d)[0], "C' 线下金叉不买": rule_c(d, True)[0], "A 两者都满足": r["10日线+MACD"], "只用MACD": r["只用MACD"], "只用10日线": r["只用10日线"]}

CODES = ["sh000300", "sh000001", "sh000016", "sh000905", "sh000852", "sz399006", "sh000688"]
for cost in (0.001, 0.0):
    for label, period in (("检验期（2016 年起，科创50 从 2020-07-23）", "test"), ("全部（2006 年起；中证1000 2015-07、创业板 2011-06、科创50 2020-07-23）", "all")):
        print(f"\n==== 单边费用 {cost*1e4:.0f} 个基点 · {label}")
        print(f"   {'':<10}" + "".join(f"{k:>14}" for k in KEYS))
        cnt = {k: [0, 0, 0] for k in KEYS[:5] if k != "C 金叉买"}; beat = {k: 0 for k in KEYS[:5]}
        for c in CODES:
            d = D[c]; a = ("2020-07-23" if c == "sh000688" else "2016-01-01") if period == "test" else START.get(c, "2006-01-04")
            res = {}
            for k, st in all_rules(d).items():
                nav, tr = run_cost(d, st, a, cost); res[k] = summary(nav, tr, d, a)
            h = hold_nav(d, a); res["一直持有"] = (ann(h), mdd(h), 0, np.nan)
            for k in beat: beat[k] += res[k][0] > res["一直持有"][0]
            for k in cnt: cnt[k][0] += res["C 金叉买"][0] > res[k][0]; cnt[k][1] += res["C 金叉买"][1] > res[k][1]
            print(f"   {NAMES[c]:<6}年化 " + "".join(f"{res[k][0]*100:+13.2f}%" for k in KEYS))
            print(f"   {'':<6}回撤 " + "".join(f"{res[k][1]*100:13.1f}%" for k in KEYS))
            print(f"   {'':<6}笔数 " + "".join(f"{res[k][2]:14d}" for k in KEYS[:5]) + f"{'—':>14}")
            print(f"   {'':<6}胜率 " + "".join(f"{res[k][3]*100:13.1f}%" for k in KEYS[:5]) + f"{'—':>14}")
        print("   C 年化更高的指数数：" + "，".join(f"对 {k} {v[0]}/7" for k, v in cnt.items()) + "；C 回撤更小：" + "，".join(f"对 {k} {v[1]}/7" for k, v in cnt.items()))
        print("   高于一直持有：" + "，".join(f"{k} {v}/7" for k, v in beat.items()))

print("\n==== 金叉当天收盘已在 10 日线下方的次数（2006 年起全部历史）")
for c in CODES: print(f"   {NAMES[c]}：{rule_c(D[c])[1]} 次")

# 沪深300 含分红
d = D["sh000300"]; tr = pd.read_csv("data/tr_H00300.csv", parse_dates=["date"]).set_index("date")["close"]
tr = tr[tr.index.isin(d.index)]; tr = tr[~tr.index.duplicated()].reindex(d.index)
div = (tr.pct_change() - d.close.pct_change()).fillna(0.0)
def bt_div(st, start, cost):
    idx = d.loc[start:].index; pos = d.index.get_indexer(idx); o, c, dv, s = d.open.values, d.close.values, div.values, st.values
    nav = 1.0; hold = False; navs = []
    for k in pos:
        want = bool(s[k - 1])
        if hold: nav *= o[k] / c[k - 1] + dv[k]
        if want != hold: nav *= 1 - cost; hold = want
        if hold: nav *= c[k] / o[k]
        navs.append(nav)
    return pd.Series(navs, index=idx)
print("\n==== 沪深300 含分红近似（单边 10 个基点；一直持有 0 费）")
for a in ("2016-01-01", "2006-01-04"):
    sts = all_rules(d); sts["一直持有"] = pd.Series(True, index=d.index)
    print(f"   {a[:4]} 起：" + "，".join(f"{k} {ann(bt_div(st, a, 0 if k == '一直持有' else 0.001))*100:+.2f}%（回撤 {mdd(bt_div(st, a, 0 if k == '一直持有' else 0.001))*100:.1f}%）" for k, st in sts.items()))
