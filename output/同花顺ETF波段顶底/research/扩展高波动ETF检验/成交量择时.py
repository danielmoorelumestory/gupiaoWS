"""用户问（2026-11-22）：能否用成交量做关联，或买入后看成交量判断是否卖出。事前写定：
数据：腾讯不复权日线（成交量 × 不复权收盘 ≈ 成交额，拆分不影响），量比 = 当日成交额 / 前 20 日均额（不含当日）。日期对齐研究面板，缺失日不触发。
买点（卖出不变）：
  放量买(量比≥1.0) / 放量买(量比≥1.2) / 缩量买(量比<1.0，反向对照)：在原择时+原买入信号上再要求信号日量比条件
卖点（买入不变，原卖点全保留，另加当日收盘卖）：
  放量破位卖：收阴 且 量比≥1.5 且 收盘<10日线
  放量大跌卖：当日跌≥3% 且 量比≥1.5
  缩量破位卖：近 5 日均额/前 20 日均额<0.7 且 收盘<10日线
线上 A 组 13 只（Y1·创业板择时）、B 组 11 只（金叉·沪深300择时），研究面板截至 2026-11-10，单边 0.1%。
注意：用的是全天成交量；14:45 提醒时只有部分成交量，实盘只能近似。自检：不加条件时与现行一致。历史统计，不构成投资建议。"""
import importlib.util, statistics, math, json, gzip
from pathlib import Path
def L(n, p): s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
Z = L("Z", "B组双熊破线卖对照.py"); Q = L("Q", "市场宽度叠加择时.py"); F3 = L("F3", "B组三方案_延长到最新.py")
C, W = Z.C, Z.W
CACHE = Path("data/raw/vol"); CACHE.mkdir(parents=True, exist_ok=True)
OLD = '        if below[i] and ((config["anyx"]'
ADD = '        if config.get("VX") and data["VX"][config["VX"]][i]: return True\n'
def build(src, eng, xn):
    assert src.count(OLD) == 1; s = src.replace(OLD, ADD + OLD)
    if xn: s = s.replace('(config["anyx"] and reg[i] is False)', '(config["anyx"] and data["reg"][config.get("XN") or config["N"]][i] is False)')
    ns = dict(vars(eng)); ns["math"] = math; exec(s, ns); return ns["simulate_y"]
simA = build(C.Y.src, C.Y.G.engine, True); simB = build(Z.B.src, Z.B.G.engine, False)
def vol(code):
    p = CACHE / f"{code}.json.gz"
    if not p.exists(): p.write_bytes(gzip.compress(json.dumps(F3.fetch(F3.mk(code), "")).encode(), mtime=0))
    return {x[0]: float(x[2]) * float(x[5]) for x in json.loads(gzip.decompress(p.read_bytes())) if len(x) > 5 and float(x[5]) > 0}
def features(d, amt):
    ds = d["dates"]; c = [float(r["adjusted_close"]) for r in d["rows"]]; a = [amt.get(t) for t in ds]; n = len(ds)
    vr, v5 = [None]*n, [None]*n
    for i in range(20, n):
        prev = [x for x in a[i-20:i] if x]
        if a[i] and len(prev) >= 15:
            m = sum(prev) / len(prev); vr[i] = a[i] / m
            last5 = [x for x in a[i-4:i+1] if x]
            if len(last5) == 5: v5[i] = sum(last5) / 5 / m
    ma10 = [None]*9 + [sum(c[i-9:i+1]) / 10 for i in range(9, n)]
    dn = [i > 0 and c[i] < c[i-1] for i in range(n)]; r1 = [0] + [c[i]/c[i-1] - 1 for i in range(1, n)]
    br = [ma10[i] is not None and c[i] < ma10[i] for i in range(n)]
    d["VX"] = {"放量破位卖": [dn[i] and vr[i] is not None and vr[i] >= 1.5 and br[i] for i in range(n)],
               "放量大跌卖": [r1[i] <= -.03 and vr[i] is not None and vr[i] >= 1.5 for i in range(n)],
               "缩量破位卖": [v5[i] is not None and v5[i] < .7 and br[i] for i in range(n)]}
    return vr
ENTRY = {"放量买(量比≥1.0)": lambda v: v is not None and v >= 1.0, "放量买(量比≥1.2)": lambda v: v is not None and v >= 1.2, "缩量买(量比<1.0)": lambda v: v is not None and v < 1.0}
KS = ["现行", *ENTRY, "放量破位卖", "放量大跌卖", "缩量破位卖"]
def run(d, g, k, vr):
    key = "R2-20" if g == "A" else "H1"; base = d["reg"][key]
    d["reg"]["ENTRY"] = [bool(x) and ENTRY[k](v) for x, v in zip(base, vr)] if k in ENTRY else base
    vx = k if k in d["VX"] else None
    if g == "A": return simA(d, {**C.Y.VAR["Y1"], "N": "ENTRY", "XN": "R2-20", "VX": vx}, C.FULL, 20, retain=True)
    return simB(d, {**Z.BASE, "anyx": False, "N": "ENTRY", "VX": vx}, C.FULL, 20, retain=True)
if __name__ == "__main__":
    C.init(); out = {}; cover = []
    for g, codes in (("A", Q.A), ("B", Q.B)):
        for c in codes:
            d = W.data_of(c); amt = vol(c); vr = features(d, amt); cover.append(sum(v is not None for v in vr) / len(vr))
            ref = W.run(d, g); assert [x["nav"] for x in run(d, g, "现行", vr)["nav"]] == [x["nav"] for x in ref["nav"]], c
            for k in KS:
                r = run(d, g, k, vr); m = Z.stats({x["date"]: x["nav"] for x in r["nav"]}); m["trades"] = sum(1 for t in r["trades"] if not t.get("forced_end")); out[(g, c, k)] = m
        print(f"\n## {g} 组（{len(codes)} 只平均）")
        for k in KS:
            F = lambda key: statistics.mean(out[(g, c, k)][key] for c in codes)
            up = sum(out[(g, c, k)]["cal"] > out[(g, c, "现行")]["cal"] for c in codes); dn = sum(out[(g, c, k)]["mdd"] > out[(g, c, "现行")]["mdd"] for c in codes)
            yrs = {y: statistics.mean(out[(g, c, k)]["years"][y] for c in codes if y in out[(g, c, k)]["years"]) for y in ("2020", "2021", "2022", "2023", "2024", "2025", "2026")}
            print(f"  {k:12s} 年化 {F('cagr')*100:5.1f}% 回撤 {F('mdd')*100:6.1f}% 卡玛 {F('cal'):4.2f} 逐年均 {F('avg')*100:5.1f}% 交易 {F('trades'):5.1f} 卡玛变好 {up}/{len(codes)} 回撤变小 {dn}/{len(codes)} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in yrs.items()))
    print(f"\n量比覆盖率：平均 {statistics.mean(cover)*100:.0f}%，最低 {min(cover)*100:.0f}%")

# ── 事后追加（2026-11-22，看完上面结果后才加）：B 组「放量大跌卖」略好，检查相邻参数是否稳定；A 组同样列出 ──
def robust():
    C.init(); res = {}
    grid = [(dp, vm) for dp in (.02, .03, .04) for vm in (1.2, 1.5, 2.0)]
    for g, codes in (("A", Q.A), ("B", Q.B)):
        for c in codes:
            d = W.data_of(c); amt = vol(c); vr = features(d, amt); cl = [float(r["adjusted_close"]) for r in d["rows"]]
            r1 = [0] + [cl[i]/cl[i-1] - 1 for i in range(1, len(cl))]
            base = Z.stats({x["date"]: x["nav"] for x in run(d, g, "现行", vr)["nav"]}); res[(g, c, "现行")] = base
            for dp, vm in grid:
                k = f"跌≥{dp*100:.0f}%量比≥{vm}"; d["VX"][k] = [r1[i] <= -dp and vr[i] is not None and vr[i] >= vm for i in range(len(cl))]
                res[(g, c, k)] = Z.stats({x["date"]: x["nav"] for x in run(d, g, k, vr)["nav"]})
        print(f"\n## 事后敏感性：{g} 组 放量大跌卖 参数网格（现行 年化/回撤/卡玛/逐年均 见上）")
        for dp, vm in grid:
            k = f"跌≥{dp*100:.0f}%量比≥{vm}"; F = lambda key: statistics.mean(res[(g, c, k)][key] for c in codes)
            up = sum(res[(g, c, k)]["cal"] > res[(g, c, "现行")]["cal"] for c in codes)
            print(f"  {k:14s} 年化 {F('cagr')*100:5.1f}% 回撤 {F('mdd')*100:6.1f}% 卡玛 {F('cal'):4.2f} 逐年均 {F('avg')*100:5.1f}% 卡玛变好 {up}/{len(codes)}")
if __name__ == "__main__": robust()
