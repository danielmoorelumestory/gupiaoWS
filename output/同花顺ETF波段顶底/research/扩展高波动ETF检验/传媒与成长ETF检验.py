"""用户要求（2026-11-18）：传媒板块有没有；159259 成长ETF易方达也测一下。事前写定口径同 汽车替代对照.py：
候选 传媒 512980（成交额最大）/159805，影视 159855，成长 159259；报上市日、成交额、年化波动、A/B 两套全历史指标与逐年、
按 2021 年前规则选的方案，以及与 游戏 159869、创业板成长 159967、创业板 159915、沪深300 510300 的日收益相关。历史统计，不构成投资建议。"""
import importlib.util
sp = importlib.util.spec_from_file_location("V", "汽车替代对照.py"); V = importlib.util.module_from_spec(sp); sp.loader.exec_module(V)
W, C, X = V.W, V.C, V.X
import math, statistics
if __name__ == "__main__":
    C.init(); ref = {c: V.lr(W.data_of(c)) for c in ("159869", "159967", "159915", "510300")}
    for c in ["512980", "159805", "159855", "159259"]:
        d = W.data_of(c)
        if W.run(d, "A") is None: print(f"\n{c} 上市 {d['dates'][0]}，不足 121 根日线，跳过"); continue
        R = V.lr(d); vol = statistics.pstdev(list(R.values()))*math.sqrt(244); pl = W.choose(d)
        cor = " ".join(f"{k}:{statistics.correlation([R[t] for t in R if t in v], [v[t] for t in R if t in v]):.2f}" for k, v in ref.items() if sum(1 for t in R if t in v) > 120)
        print(f"\n{c} 上市 {d['dates'][0]} 成交额 {V.amt(c)/10000:.2f} 亿 波动 {vol*100:.0f}% 规则选 {pl} ｜相关 {cor}")
        for p in "AB":
            nav = {x["date"]: x["nav"] for x in W.run(d, p)["nav"]}; m = C.window_metrics(nav, ("1900-01-01", X.END))
            print(f"   {p}: 起 {min(nav)} 年化 {m['cagr']*100:6.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:5.2f} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
