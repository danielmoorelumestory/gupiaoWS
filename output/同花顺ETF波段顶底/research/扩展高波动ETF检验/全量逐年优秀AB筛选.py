"""全量 ETF 逐年稳定优秀筛选（A 方案 = Y1·创业板÷红利择时；B 方案 = 只认金叉·沪深300÷红利择时）。事前写定（2026-11-15，跑之前）：
样本：研究面板全部 ETF（不限波动率，用户要求全量），另标注年化波动。
逐年：每个自然年单独回测（年初空仓起算，年末平仓；当年在窗口内不足 120 个交易日的年份不计，2026 年截至 11-10）。
某方案对某只 ETF「逐年优秀」须全部满足：
  1. 计入年份 ≥ 3；
  2. 逐年收益平均 ≥ 10%；
  3. 正收益年份占比 ≥ 75%；
  4. 最差一年 ≥ −10%；
  5. 全历史卡玛（年化÷|最大回撤|）≥ 0.5。
归组：只 A 合格 → A 组；只 B 合格 → B 组；都合格 → 两组都列，并标注全历史卡玛较高的一方。
另报：逐年平均跑赢一直持有的年份占比（只作描述，不参与判定）；主题去重（相关≥0.93，保留历史最长）。
注意：入选用的就是这段历史，结果偏乐观，只能作候选，需要后续新数据验证。
【2026-11-18 起不再使用】现行分组见 网页口径重新分组.py（网页回测口径、只算已平仓、归组按逐年平均→年化→盈利年份/波动→回撤）。本文件保留作历史记录。"""
import json, csv, math, statistics, itertools, importlib.util
from multiprocessing import Pool
import run_extended as X, regime_multi as RM
def load(name, path):
    sp = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
Z = load("Z", "低波动沪深300择时对照.py"); F = load("F", "分组复测_持有MACD对照.py")
T, K, Y = Z.T, Z.K, Z.Y; FULL = ("1900-01-01", "2026-11-10"); YEARS = range(2005, 2027)
PLANS = {"A": lambda d, w: Y.simulate_y(d, {**Y.VAR["Y1"], "N": "R2-20"}, w, 20), "B": lambda d, w: K.simulate_kd(d, {**T.BASE, "N": "H1"}, w, 20)}
def init(): Z.init()
def work(code):
    d = T.M.PANEL[code]; out = {"code": code}
    c = [float(r["adjusted_close"]) for r in d["rows"]]
    out["vol"] = statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    for p, f in PLANS.items():
        r = f(d, FULL); m = r and r["metric"]
        out[p+"_full"] = m and {"cagr": m["cagr"], "mdd": m["mdd"], "years": m["years"], "first": m["first"]}
        out[p+"_yr"] = {}
        for y in YEARS:
            rr = f(d, (f"{y}-01-01", f"{y}-12-31"))
            if rr: out[p+"_yr"][y] = rr["metric"]["total_return"]
    out["H_yr"] = {}
    for y in YEARS:
        h = F.hold(d, (f"{y}-01-01", f"{y}-12-31"))
        if h and len([i for i, x in enumerate(d["dates"]) if i >= 120 and f"{y}-01-01" <= x <= f"{y}-12-31"]) >= 120: out["H_yr"][y] = h["total_return"]
    return out
def judge(o, p):
    yr = o[p+"_yr"]; full = o[p+"_full"]; v = list(yr.values())
    if not full or full["cagr"] is None or len(v) < 3: return None
    cal = full["cagr"]/abs(full["mdd"]) if full["mdd"] < 0 else float("inf")
    s = {"n": len(v), "avg": statistics.mean(v), "pos": sum(x > 0 for x in v)/len(v), "worst": min(v), "cal": cal, "cagr": full["cagr"], "mdd": full["mdd"],
         "beat": statistics.mean(yr[y] > o["H_yr"][y] for y in yr if y in o["H_yr"]) if any(y in o["H_yr"] for y in yr) else None}
    s["ok"] = s["avg"] >= .10 and s["pos"] >= .75 and s["worst"] >= -.10 and cal >= .5
    return s
if __name__ == "__main__":
    names = {r["代码"]: r["名称"] for r in csv.DictReader(open("../Claude逐只复测61ETF/claude/per_etf_61_brief.csv"))}
    for r in json.load(open("沪深300择时优选_全部结果.json")): names.setdefault(r["code"], r["name"])
    names.update(F.NAMES)
    init(); codes = list(T.M.PANEL)
    with Pool(8, initializer=init) as p: R = p.map(work, codes)
    pool, new, audit = X.build(); rows = {**{"P"+k: v["rows"] for k, v in pool.items()}, **{"N"+k: v["rows"] for k, v in new.items()}}
    res = []
    for o in R:
        a, b = judge(o, "A"), judge(o, "B")
        if not a and not b: continue
        res.append({"o": o, "A": a, "B": b})
    print(f"样本：面板 {len(codes)} 只；计入年份≥3 且有全历史年化 {len(res)} 只")
    def fmt(s): return f"逐年均 {s['avg']*100:+6.1f}%  正收益年 {s['pos']*100:3.0f}%  最差 {s['worst']*100:+6.1f}%  卡玛 {s['cal']:.2f}  年化 {s['cagr']*100:5.1f}%/{s['mdd']*100:6.1f}%  跑赢持有年 {s['beat']*100 if s['beat'] is not None else float('nan'):3.0f}%  ({s['n']}年)"
    out = []
    for g in ("A", "B"):
        sel = [r for r in res if r[g] and r[g]["ok"]]; sel.sort(key=lambda r: -r[g]["cal"])
        print(f"\n## {g} 方案逐年优秀：{len(sel)} 只")
        for r in sel:
            o = r["o"]; other = "B" if g == "A" else "A"; both = r[other] and r[other]["ok"]
            tag = ("两组都合格·" + ("本组卡玛更高" if r[g]["cal"] >= r[other]["cal"] else "另一组卡玛更高")) if both else ""
            print(f"  {o['code'][1:]} {names.get(o['code'][1:], ''):<14} 波动 {o['vol']*100:4.0f}%  {fmt(r[g])}  {tag}")
            print("       逐年 " + " ".join(f"{y%100:02d}:{v*100:+.0f}" for y, v in sorted(o[g+'_yr'].items())))
            out.append({"group": g, "code": o["code"][1:], "name": names.get(o["code"][1:], ""), "vol": round(o["vol"]*100, 1), "both": bool(both),
                        **{k: (round(v*100, 2) if k not in ("n", "cal", "ok") else (round(v, 3) if k == "cal" else v)) for k, v in r[g].items() if v is not None},
                        "years": {y: round(v*100, 2) for y, v in sorted(o[g+"_yr"].items())}})
    # 差一点的（4 项中只差 1 项）
    print("\n## 只差 1 项的（参考）")
    for g in ("A", "B"):
        for r in res:
            s = r[g]
            if not s or s["ok"]: continue
            miss = [n for n, ok in (("均≥10%", s["avg"] >= .10), ("正年≥75%", s["pos"] >= .75), ("最差≥−10%", s["worst"] >= -.10), ("卡玛≥0.5", s["cal"] >= .5)) if not ok]
            if len(miss) == 1: print(f"  {g} {r['o']['code'][1:]} {names.get(r['o']['code'][1:], ''):<14} 缺：{miss[0]}  {fmt(s)}")
    # 去重
    for g in ("A", "B"):
        G = ["P"+x["code"] if "P"+x["code"] in rows else "N"+x["code"] for x in out if x["group"] == g]
        if len(G) < 2: continue
        def lr(rs):
            s = RM.series_from_rows(rs); ds = sorted(s); return {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
        LR = {c: lr(rows[c]) for c in G}; parent = {c: c for c in G}
        def find(a):
            while parent[a] != a: a = parent[a]
            return a
        for a, b in itertools.combinations(G, 2):
            cc = [x for x in LR[a] if x in LR[b]]
            if len(cc) >= 120 and statistics.correlation([LR[a][x] for x in cc], [LR[b][x] for x in cc]) >= .93: parent[find(a)] = find(b)
        gs = {}
        for c in G: gs.setdefault(find(c), []).append(c)
        print(f"\n## {g} 组主题去重：{len(G)} → {len(gs)} 组；合并：" + ("；".join(" ".join(c[1:] for c in m) for m in gs.values() if len(m) > 1) or "无"))
    json.dump(out, open("全量逐年优秀AB_结果.json", "w"), ensure_ascii=False, indent=1)
