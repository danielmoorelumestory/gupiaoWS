"""平时纯 MACD、大跌后金叉加仓（运行前写定，跑完不改）。
资金两半独立运作、不再平衡：核心半 = 纯 MACD；加仓半 = 只做“金叉当日较 60 日最高复权收盘跌 ≥X”的金叉，死叉卖，其余空仓（现金 0 收益）。
组合净值 = 0.5×核心净值 + 0.5×加仓净值。X 主规则 20%，对照 10%。
对照：满仓纯 MACD；半仓纯 MACD（0.5×MACD + 0.5×现金）；同等平均仓位纯 MACD（c×MACD + (1−c)×现金，c 使平均投入资金比例与加仓组合相同，逐只计算）。
成交、成本、样本、汇总同前。"""
import json, numpy as np, pandas as pd
exec(open("research/macd_after_drop.py").read().split("rows, ent = [], []")[0])
def invested(navs_w, sts):
    """各子账户持仓日的资金占比（按子账户净值加权），返回逐日组合投入比例。"""
    tot = sum(w * n for w, n in navs_w); inv = sum(w * n * s for (w, n), s in zip(navs_w, sts))
    return (inv / tot).mean()
rows = []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code); i0 = 60
    if len(d) < 120: continue
    x = indicators(d, adj); x["dd60"] = (adj / adj.rolling(60, min_periods=1).max() - 1).values
    idx = d.index; years = (idx[-1] - idx[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    sm = macd_state(adj); nm, _ = backtest(d, dv, mult, sm, i0, 0.001)
    held = lambda st: st.shift(1).iloc[i0:].fillna(False).astype(float).values   # 当天是否持仓（前一日信号）
    h, _ = backtest(d, dv, mult, pd.Series(True, index=idx), i0, 0.0)
    r = dict(code=code, name=name, years=years, good=code in good, hold=ann(h), hold_dd=mdd(h), M=ann(nm), M_dd=mdd(nm))
    half = 0.5 * nm + 0.5; r["half"], r["half_dd"] = ann(half), mdd(half)
    expM = held(sm).mean(); r["expM"] = expM
    for k in ("D20", "D10"):
        sd = pd.Series(positions(x, entry=k), index=idx); nd, _ = backtest(d, dv, mult, sd, i0, 0.001)
        comb = 0.5 * nm + 0.5 * nd; r[k], r[k + "_dd"] = ann(comb), mdd(comb)
        inv = invested([(0.5, nm.values), (0.5, nd.values)], [held(sm), held(sd)]); r[k + "_inv"] = inv
        c = min(1.0, inv / expM) if expM > 0 else 0; fair = c * nm + (1 - c); r[k + "_fair"], r[k + "_fair_dd"], r[k + "_c"] = ann(fair), mdd(fair), c
        # 前后半段：各自从半段起点重新开始
        for half_name, a, b in (("h1", i0, mid + 1), ("h2", mid, len(d))):
            sub = slice(None, b)
            m1, _ = backtest(d.iloc[sub], dv.iloc[sub], mult.iloc[sub], sm.iloc[sub], a, 0.001); d1, _ = backtest(d.iloc[sub], dv.iloc[sub], mult.iloc[sub], sd.iloc[sub], a, 0.001)
            r[f"{k}_{half_name}"] = ann(0.5 * m1 + 0.5 * d1); r[f"{k}_fair_{half_name}"] = ann(c * m1 + (1 - c))
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/macd_add_on_drop_results.csv", index=False)
for label, g in (("回测≥3年全部", t[t.years >= 3]), ("MACD优秀 17 只", t[t.good])):
    print(f"\n==== {label}（{len(g)} 只）")
    print(f"   {'方案':<26}{'年化中位':>8}{'年化均值':>8}{'回撤中位':>8}{'平均投入':>8}")
    print(f"   {'一直持有':<24}{g.hold.median()*100:+8.2f}{g.hold.mean()*100:+8.2f}{g.hold_dd.median()*100:8.1f}{100:7.0f}%")
    print(f"   {'满仓纯MACD':<24}{g.M.median()*100:+8.2f}{g.M.mean()*100:+8.2f}{g.M_dd.median()*100:8.1f}{g.expM.median()*100:7.0f}%")
    print(f"   {'半仓纯MACD（不加仓）':<20}{g.half.median()*100:+8.2f}{g.half.mean()*100:+8.2f}{g.half_dd.median()*100:8.1f}{g.expM.median()*50:7.0f}%")
    for k, nm_ in (("D20", "跌≥20%"), ("D10", "跌≥10%")):
        print(f"   {'半仓MACD+'+nm_+'金叉加仓':<20}{g[k].median()*100:+8.2f}{g[k].mean()*100:+8.2f}{g[k+'_dd'].median()*100:8.1f}{g[k+'_inv'].median()*100:7.0f}%")
        print(f"   {'  同等平均仓位纯MACD':<21}{g[k+'_fair'].median()*100:+8.2f}{g[k+'_fair'].mean()*100:+8.2f}{g[k+'_fair_dd'].median()*100:8.1f}{g[k+'_inv'].median()*100:7.0f}%")
        print(f"     加仓方案胜“同等仓位”{(g[k]>g[k+'_fair']).sum()}/{len(g)}，前后两半都胜 {((g[k+'_h1']>g[k+'_fair_h1'])&(g[k+'_h2']>g[k+'_fair_h2'])).sum()}/{len(g)}；胜“半仓不加仓”{(g[k]>g.half).sum()}/{len(g)}")
