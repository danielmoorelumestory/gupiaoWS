"""用户问（2026-11-22）：把市场宽度也加入择时，效果如何。事前写定：
宽度：全 A 涨跌家数本地只有 2025-06 起 351 天，太短；改用研究面板全部 ETF（≥10 只有数据的日子）中收盘站上 20 日线的比例（与 regime_common 的 B20-60 同定义），当日收盘计算。
只改买入条件，卖出完全不变（A 组 Y1 的「择时熊且破 10 日线卖」仍按原创业板择时；B 组死叉卖）。线上 A 组 13 只、B 组 11 只，研究面板截至 2026-11-10，单边 0.1%。
  现行            原择时牛才买
  且宽度≥40/50/60%  原择时牛 且 宽度达标 才买
  或宽度≥70%       原择时牛 或 宽度≥70% 可买（放宽）
自检：买入用原择时时，与现行结果完全一致。历史统计，不构成投资建议。"""
import importlib.util, statistics, math
from collections import defaultdict
sp = importlib.util.spec_from_file_location("Z", "B组双熊破线卖对照.py"); Z = importlib.util.module_from_spec(sp); sp.loader.exec_module(Z)
C, W = Z.C, Z.W
A = ['513310', '588200', '159869', '159851', '512760', '516520', '159667', '562500', '516510', '159939', '512670', '159998', '159852']
B = Z.CODES
old = '(config["anyx"] and reg[i] is False)'; assert C.Y.src.count(old) == 1
_ns = dict(vars(C.Y.G.engine)); _ns["math"] = math
exec(C.Y.src.replace(old, '(config["anyx"] and data["reg"][config.get("XN") or config["N"]][i] is False)'), _ns); simy = _ns["simulate_y"]
def breadth():
    cell = defaultdict(lambda: [0, 0])
    for d in C.T.M.PANEL.values():
        c = [float(r["adjusted_close"]) for r in d["rows"]]
        for i in range(19, len(c)):
            x = cell[d["dates"][i]]; x[0] += c[i] > sum(c[i-19:i+1]) / 20; x[1] += 1
    return {t: v[0] / v[1] for t, v in cell.items() if v[1] >= 10}
RULES = {"现行": None, "且宽度≥40%": ("and", .4), "且宽度≥50%": ("and", .5), "且宽度≥60%": ("and", .6), "或宽度≥70%": ("or", .7)}
def run(d, g, rule, BR):
    key = "R2-20" if g == "A" else "H1"; base = d["reg"][key]
    if rule is None: reg = base
    else:
        op, th = rule; br = [BR.get(t) for t in d["dates"]]
        reg = [(b is None or (x and b >= th)) and x if op == "and" else (bool(x) or (b is not None and b >= th)) for x, b in zip(base, br)]
        reg = [bool(x) for x in reg]
    d["reg"]["ENTRY"] = reg
    if g == "A": return simy(d, {**C.Y.VAR["Y1"], "N": "ENTRY", "XN": "R2-20"}, C.FULL, 20, retain=True)
    return C.K.simulate_kd(d, {**C.T.BASE, "N": "ENTRY"}, C.FULL, 20, retain=True)
if __name__ == "__main__":
    C.init(); BR = breadth(); ks = sorted(BR)
    print(f"宽度：{ks[0]}～{ks[-1]}，最新 {BR[ks[-1]]*100:.0f}%；≥50% 的天数占 {sum(v>=.5 for v in BR.values())/len(BR)*100:.0f}%")
    out = {}
    for g, codes in (("A", A), ("B", B)):
        for c in codes:
            d = W.data_of(c); ref = W.run(d, g)
            d["reg"]["ENTRY"] = d["reg"]["R2-20" if g == "A" else "H1"]
            chk = simy(d, {**C.Y.VAR["Y1"], "N": "ENTRY", "XN": "R2-20"}, C.FULL, 20, retain=True) if g == "A" else C.K.simulate_kd(d, {**C.T.BASE, "N": "ENTRY"}, C.FULL, 20, retain=True)
            assert [x["nav"] for x in chk["nav"]] == [x["nav"] for x in ref["nav"]], c   # 自检
            for k, rule in RULES.items():
                r = run(d, g, rule, BR); m = Z.stats({x["date"]: x["nav"] for x in r["nav"]}); m["trades"] = sum(1 for t in r["trades"] if not t.get("forced_end")); out[(g, c, k)] = m
        print(f"\n## {g} 组（{len(codes)} 只平均）")
        for k in RULES:
            F = lambda key: statistics.mean(out[(g, c, k)][key] for c in codes)
            up = sum(out[(g, c, k)]["cal"] > out[(g, c, "现行")]["cal"] for c in codes); dn = sum(out[(g, c, k)]["mdd"] > out[(g, c, "现行")]["mdd"] for c in codes)
            yrs = {y: statistics.mean(out[(g, c, k)]["years"][y] for c in codes if y in out[(g, c, k)]["years"]) for y in ("2020", "2021", "2022", "2023", "2024", "2025", "2026")}
            print(f"  {k:9s} 年化 {F('cagr')*100:5.1f}% 回撤 {F('mdd')*100:6.1f}% 卡玛 {F('cal'):4.2f} 逐年均 {F('avg')*100:5.1f}% 交易 {F('trades'):5.1f} 卡玛变好 {up}/{len(codes)} 回撤变小 {dn}/{len(codes)} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in yrs.items()))
