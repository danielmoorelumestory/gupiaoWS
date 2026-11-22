"""用户问（2026-11-22）：买入时也判断一下近几日的量比。事前写定：
近 n 日量比 = 信号日在内近 n 日均额 ÷ 再往前 20 日均额（不与近 n 日重叠）；数据同 成交量择时.py（腾讯不复权 量×价）。
只改买入（原择时 + 原买入信号上再加量比条件），卖出不变：
  近3日≥1.0 / 近3日≥1.2 / 近5日≥1.0 / 近5日≥1.2 / 近5日 1.0–2.0（温和放量，排除爆量）/ 近5日<1.0（缩量，反向对照）
线上 A 组 13 只、B 组 11 只，研究面板截至 2026-11-10，单边 0.1%。自检：不加条件与现行一致。历史统计，不构成投资建议。"""
import importlib.util, statistics
def L(n, p): s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
V = L("V", "成交量择时.py"); Z, Q, C, W = V.Z, V.Q, V.C, V.W
def nratio(d, amt, n):
    a = [amt.get(t) for t in d["dates"]]; out = [None] * len(a)
    for i in range(n + 20, len(a)):
        cur = [x for x in a[i-n+1:i+1] if x]; prev = [x for x in a[i-n-19:i-n+1] if x]
        if len(cur) == n and len(prev) >= 15: out[i] = (sum(cur) / n) / (sum(prev) / len(prev))
    return out
RULES = {"现行": None, "近3日≥1.0": (3, lambda v: v >= 1.0), "近3日≥1.2": (3, lambda v: v >= 1.2), "近5日≥1.0": (5, lambda v: v >= 1.0),
         "近5日≥1.2": (5, lambda v: v >= 1.2), "近5日1.0–2.0": (5, lambda v: 1.0 <= v < 2.0), "近5日<1.0": (5, lambda v: v < 1.0)}
def run(d, g, mask):
    d["reg"]["ENTRY"] = mask
    if g == "A": return V.simA(d, {**C.Y.VAR["Y1"], "N": "ENTRY", "XN": "R2-20", "VX": None}, C.FULL, 20, retain=True)
    return V.simB(d, {**Z.BASE, "anyx": False, "N": "ENTRY", "VX": None}, C.FULL, 20, retain=True)
if __name__ == "__main__":
    C.init(); out = {}
    for g, codes in (("A", Q.A), ("B", Q.B)):
        for c in codes:
            d = W.data_of(c); amt = V.vol(c); base = d["reg"]["R2-20" if g == "A" else "H1"]; nr = {n: nratio(d, amt, n) for n in (3, 5)}
            assert [x["nav"] for x in run(d, g, base)["nav"]] == [x["nav"] for x in W.run(d, g)["nav"]], c
            for k, rule in RULES.items():
                mask = base if rule is None else [bool(x) and v is not None and rule[1](v) for x, v in zip(base, nr[rule[0]])]
                r = run(d, g, mask); m = Z.stats({x["date"]: x["nav"] for x in r["nav"]}); m["trades"] = sum(1 for t in r["trades"] if not t.get("forced_end")); out[(g, c, k)] = m
        print(f"\n## {g} 组（{len(codes)} 只平均）")
        for k in RULES:
            F = lambda key: statistics.mean(out[(g, c, k)][key] for c in codes)
            up = sum(out[(g, c, k)]["cal"] > out[(g, c, "现行")]["cal"] for c in codes); dn = sum(out[(g, c, k)]["mdd"] > out[(g, c, "现行")]["mdd"] for c in codes)
            yrs = {y: statistics.mean(out[(g, c, k)]["years"][y] for c in codes if y in out[(g, c, k)]["years"]) for y in ("2020", "2021", "2022", "2023", "2024", "2025", "2026")}
            print(f"  {k:10s} 年化 {F('cagr')*100:5.1f}% 回撤 {F('mdd')*100:6.1f}% 卡玛 {F('cal'):4.2f} 逐年均 {F('avg')*100:5.1f}% 交易 {F('trades'):5.1f} 卡玛变好 {up}/{len(codes)} 回撤变小 {dn}/{len(codes)} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in yrs.items()))
