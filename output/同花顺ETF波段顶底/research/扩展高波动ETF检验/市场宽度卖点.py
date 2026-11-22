"""用户问（2026-11-22）：卖点加上市场宽度呢。事前写定：
宽度同 市场宽度叠加择时.py（研究面板 ETF 站上 20 日线比例，当日收盘算；无数据的日子不触发）。买入完全不变，原卖点全部保留，另加一条「当日收盘卖」：
  宽度<20%卖 / 宽度<30%卖 / 宽度<30%且破10日线卖 / 宽度<40%且破10日线卖
线上 A 组 13 只（Y1·创业板择时）、B 组 11 只（金叉·沪深300择时），研究面板截至 2026-11-10，单边 0.1%。
自检：不加宽度卖点时与现行完全一致。历史统计，不构成投资建议。"""
import importlib.util, statistics, math
sp = importlib.util.spec_from_file_location("Z", "B组双熊破线卖对照.py"); Z = importlib.util.module_from_spec(sp); sp.loader.exec_module(Z)
sp2 = importlib.util.spec_from_file_location("Q", "市场宽度叠加择时.py"); Q = importlib.util.module_from_spec(sp2); sp2.loader.exec_module(Q)
C, W = Z.C, Z.W
OLD = '        if below[i] and ((config["anyx"]'
ADD = '        if config.get("BX") is not None and data["BRL"][i] is not None and data["BRL"][i] < config["BX"] and (not config.get("BXma") or below[i]): return True\n'
def build(src, eng):
    assert src.count(OLD) == 1; ns = dict(vars(eng)); ns["math"] = math; exec(src.replace(OLD, ADD + OLD), ns); return ns["simulate_y"]
simA = build(C.Y.src, C.Y.G.engine); simB = build(Z.B.src, Z.B.G.engine)
RULES = {"现行": {}, "宽度<20%卖": {"BX": .2}, "宽度<30%卖": {"BX": .3}, "宽度<30%且破10日线卖": {"BX": .3, "BXma": True}, "宽度<40%且破10日线卖": {"BX": .4, "BXma": True}}
def run(d, g, extra):
    if g == "A": return simA(d, {**C.Y.VAR["Y1"], **extra}, C.FULL, 20, retain=True)
    return simB(d, {**Z.BASE, "anyx": False, **extra}, C.FULL, 20, retain=True)
if __name__ == "__main__":
    C.init(); BR = Q.breadth(); out = {}
    print(f"宽度 <20% 的天数占 {sum(v<.2 for v in BR.values())/len(BR)*100:.0f}%，<30% 占 {sum(v<.3 for v in BR.values())/len(BR)*100:.0f}%，<40% 占 {sum(v<.4 for v in BR.values())/len(BR)*100:.0f}%")
    for g, codes in (("A", Q.A), ("B", Q.B)):
        for c in codes:
            d = W.data_of(c); d["BRL"] = [BR.get(t) for t in d["dates"]]; ref = W.run(d, g)
            assert [x["nav"] for x in run(d, g, {})["nav"]] == [x["nav"] for x in ref["nav"]], c   # 自检
            for k, ex in RULES.items():
                r = run(d, g, ex); m = Z.stats({x["date"]: x["nav"] for x in r["nav"]}); m["trades"] = sum(1 for t in r["trades"] if not t.get("forced_end")); out[(g, c, k)] = m
        print(f"\n## {g} 组（{len(codes)} 只平均）")
        for k in RULES:
            F = lambda key: statistics.mean(out[(g, c, k)][key] for c in codes)
            up = sum(out[(g, c, k)]["cal"] > out[(g, c, "现行")]["cal"] for c in codes); dn = sum(out[(g, c, k)]["mdd"] > out[(g, c, "现行")]["mdd"] for c in codes)
            yrs = {y: statistics.mean(out[(g, c, k)]["years"][y] for c in codes if y in out[(g, c, k)]["years"]) for y in ("2020", "2021", "2022", "2023", "2024", "2025", "2026")}
            print(f"  {k:12s} 年化 {F('cagr')*100:5.1f}% 回撤 {F('mdd')*100:6.1f}% 卡玛 {F('cal'):4.2f} 逐年均 {F('avg')*100:5.1f}% 交易 {F('trades'):5.1f} 卡玛变好 {up}/{len(codes)} 回撤变小 {dn}/{len(codes)} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in yrs.items()))
