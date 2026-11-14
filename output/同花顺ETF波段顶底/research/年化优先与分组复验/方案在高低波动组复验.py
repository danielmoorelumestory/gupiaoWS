"""把之前定下的方案原样（不重选参数）放到高/低波动组复验。分组口径同 高波动训练协议.md。
已删除在高波动组明显更差的方案：纯MACD次开卖、仅MA10、原混合规则USER、Codex A、Codex B、日线分段N250。"""
import json, csv, math, random, statistics
from multiprocessing import Pool
import cs_common as C, regime_common as G, filter_common as F
from cs_common import P, summarize
b = C.blank
SCHEMES = {  # 名称: (类型, config, 尾盘卖)
  "纯MACD12/26/9·尾盘卖（基准）": ("e", C.grid[C.MACD_KEY], True),
  "年化优先·训练第一 E3/X3 16/35/9": ("e", {**b,"entry":"E3","exit":"X3","n":9,"hi":80,"macd":[16,35,9]}, True),
  "周线分段 WZ/GOLD/X2/E3/X4": ("r", {**b,"macd":[12,26,9],"entry":"REG","exit":"REG","N":"WZ-live","bullin":"GOLD","bullx":"X2","bearin":"E3","bearx":"X4"}, True),
  "宽度分段 B20-60/GOLD/X2/空仓": ("r", {**b,"macd":[12,26,9],"entry":"REG","exit":"REG","N":"B20-60","bullin":"GOLD","bullx":"X2","bearin":"NONE","bearx":"X2"}, True),
  "MACD+K−D≥5.3·尾盘卖": ("f", {**b, "entry":"MACDF", "exit":"X2", "macd":[12,26,9], "flt":"KD"}, True),
  "MACD+A20·尾盘卖": ("f", {**b, "entry":"MACDF", "exit":"X2", "macd":[12,26,9], "flt":"A20"}, True),
  "买入持有": ("e", C.HOLD, False),
}
PANEL = None
def init():
    global PANEL; PANEL = F.add_filters(G.add_reg(C.load_panel()))[0]
def run(job):
    name, w = job; kind, c, cs = SCHEMES[name]; win = P["windows"][w]
    per = {}
    for code, d in PANEL.items():
        if kind == "r": r = G.simulate_rg(d, c, win, 20)
        elif kind == "f": r = F.simulate_f(d, c, win, 20)
        else: r = (C.simulate_cs if cs else C.engine.simulate)(d, c, win, 20)
        if r: per[code] = r["metric"]
    return name, w, per
if __name__ == "__main__":
    # 自检：过滤=NONE 时必须等于纯 MACD 尾盘卖
    init()
    for code, d in list(PANEL.items())[:61]:
        a = F.simulate_f(d, {**b, "entry":"MACDF", "exit":"X2", "macd":[12,26,9], "flt":"NONE"}, P["windows"]["test"], 20); m = C.simulate_cs(d, C.grid[C.MACD_KEY], P["windows"]["test"], 20)
        assert (a is None) == (m is None) and (a is None or abs(a["metric"]["final_nav"]-m["metric"]["final_nav"]) < 1e-12), code
    print("自检通过：过滤=NONE 复现纯MACD尾盘卖；A20 年度阈值：", {y: round(v,4) for y, v in F.add_filters(C.load_panel())[1].items() if v is not None})
    for c in SCHEMES.values():
        if c[0] == "e" and c[1]["entry"] != "HOLD" and c[1]["entry"] != "MA": assert C.identifier(c[1]) in C.grid, c
    sel = json.load(open("高波动_selection.json")); H1, H2 = set(sel["H1"]), set(sel["H2"])
    panel = C.load_panel(); L1, L2 = set(), set()
    for k, d in panel.items():
        for cut, H, L in (("2022-07-01", H1, L1), ("2024-07-01", H2, L2)):
            if sum(dt < cut for dt in d["dates"]) >= 120 and k not in H: L.add(k)
    with Pool(8, initializer=init) as pool: res = pool.map(run, [(n, w) for n in SCHEMES for w in ("train","validation","test")])
    R = {(n, w): per for n, w, per in res}
    groups = {"train": (H1, L1), "validation": (H1, L1), "test": (H2, L2)}
    def med(per, grp, key="cagr"):
        v = [per[c][key] for c in per if c in grp and per[c][key] is not None]; return statistics.median(v) if v else None
    def ci(a, m, grp):
        codes = [c for c in a if c in grp and a[c]["cagr"] is not None and m[c]["cagr"] is not None]
        rnd = random.Random(20261113)
        d = sorted(statistics.median(a[c]["cagr"] for c in s) - statistics.median(m[c]["cagr"] for c in s) for s in ([rnd.choice(codes) for _ in codes] for _ in range(1000)))
        return d[25], d[974], sum(a[c]["cagr"] > m[c]["cagr"] for c in codes), len(codes)
    rows = []
    base = "纯MACD12/26/9·尾盘卖（基准）"
    for gi, gname in ((0, "高波动"), (1, "低波动")):
        print(f"\n## {gname}组  年化中位（回撤中位）｜ 相对基准年化差95%区间 / 逐只胜")
        for n in SCHEMES:
            cells = []
            for w in ("train","validation","test"):
                grp = groups[w][gi]; per = R[(n, w)]
                cg, md = med(per, grp), med(per, grp, "mdd")
                s = f"{cg*100:6.2f}%({md*100:5.1f}%)"
                if n != base:
                    lo, hi, win, tot = ci(per, R[(base, w)], grp); s += f" [{lo*100:+.1f},{hi*100:+.1f}] {win}/{tot}"
                cells.append(s)
                rows.append({"组": gname, "方案": n, "阶段": w, "年化中位": cg, "回撤中位": md})
            print(f"{n:<34}| 训练 {cells[0]:<32}| 验证 {cells[1]:<32}| 测试(已见) {cells[2]}")
    with open("方案在高低波动组复验.csv", "w", newline="") as f:
        w_ = csv.DictWriter(f, fieldnames=list(rows[0])); w_.writeheader(); w_.writerows(rows)
    print("\n高波动组ETF数（训练/验证用L1，测试用L2）：", len(H1), len(H2), " 低波动：", len(L1), len(L2))
