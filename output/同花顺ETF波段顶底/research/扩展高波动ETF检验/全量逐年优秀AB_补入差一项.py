"""在 全量逐年优秀AB筛选 的基础上补入「差一项」标的。事前写定（2026-11-15，跑之前，用户要求）：
现有分组（两组都合格的按卡玛高者归组）：
  A：513310 588200 159869 159851 512760 159819 562500 159667 516510 159939 159998 159852 159967 512720
  B：512480 588000 512670 159509 516150 159732 515000 515980
候选：该方案 5 项条件只差 1 项，且尚未在任一组。
「比较优秀」：该方案 逐年均 ≥ 10% 且 全历史卡玛 ≥ 0.7。
「关联度不高」：与本组每一只现有标的的日收益相关系数都 < 0.80（重叠 ≥120 天才计）。
三者都满足 → 补入对应组。另报所有差一项候选的最高相关对象，供参考。
【2026-11-18 起不再使用】现行分组见 网页口径重新分组.py（网页回测口径、只算已平仓、归组按逐年平均→年化→盈利年份/波动→回撤）。本文件保留作历史记录。"""
import json, math, statistics, importlib.util
import run_extended as X, regime_multi as RM
spec = importlib.util.spec_from_file_location("S", "全量逐年优秀AB筛选.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
GRP = {"A": "513310 588200 159869 159851 512760 159819 562500 159667 516510 159939 159998 159852 159967 512720".split(),
       "B": "512480 588000 512670 159509 516150 159732 515000 515980".split()}
def _init(): S.init()
def _work(c): return S.work(c)
if __name__ == "__main__":
    from multiprocessing import Pool
    S.init(); codes = list(S.T.M.PANEL)
    with Pool(8, initializer=_init) as p: R = p.map(_work, codes)
    pool, new, audit = X.build(); rows = {**{"P"+k: v["rows"] for k, v in pool.items()}, **{"N"+k: v["rows"] for k, v in new.items()}}
    def lr(c):
        s = RM.series_from_rows(rows["P"+c] if "P"+c in rows else rows["N"+c]); ds = sorted(s); return {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
    def corr(a, b):
        A, B = lr(a), lr(b); cc = [x for x in A if x in B]
        return statistics.correlation([A[x] for x in cc], [B[x] for x in cc]) if len(cc) >= 120 else None
    names = json.load(open("全量逐年优秀AB_结果.json")); NM = {x["code"]: x["name"] for x in names}; NM.update(S.F.NAMES)
    import csv
    NM.update({r["代码"]: r["名称"] for r in csv.DictReader(open("../Claude逐只复测61ETF/claude/per_etf_61_brief.csv"))})
    for r in json.load(open("沪深300择时优选_全部结果.json")): NM.setdefault(r["code"], r["name"])
    used = set(GRP["A"]) | set(GRP["B"]); add = {"A": [], "B": []}
    print("## 差一项候选（未入组）")
    for o in R:
        c = o["code"][1:]
        if c in used: continue
        for g in ("A", "B"):
            s = S.judge(o, g)
            if not s or s["ok"]: continue
            miss = [n for n, ok in (("均≥10%", s["avg"] >= .10), ("正年≥75%", s["pos"] >= .75), ("最差≥−10%", s["worst"] >= -.10), ("卡玛≥0.5", s["cal"] >= .5)) if not ok]
            if len(miss) != 1: continue
            cs = [(m, corr(c, m)) for m in GRP[g]]; cs = [(m, v) for m, v in cs if v is not None]
            top = max(cs, key=lambda t: t[1]) if cs else (None, None)
            good = s["avg"] >= .10 and s["cal"] >= .7; low = top[1] is None or top[1] < .80
            ok = good and low
            if ok: add[g].append(c)
            print(f"  {'✔' if ok else ' '} {g} {c} {NM.get(c, ''):<14} 缺：{miss[0]:<8} 逐年均 {s['avg']*100:+5.1f}%  卡玛 {s['cal']:.2f}  最差 {s['worst']*100:+5.1f}%  正年 {s['pos']*100:3.0f}%  ({s['n']}年)"
                  f"  与本组最高相关 {top[0]} {NM.get(top[0], '') if top[0] else ''} {top[1]:.2f}" + ("" if good else "  ← 不够优秀") + ("" if low else "  ← 关联度高"))
    print(f"\n## 补入：A {add['A'] or '无'}；B {add['B'] or '无'}")
    json.dump({"A": GRP["A"] + add["A"], "B": GRP["B"] + add["B"], "added": add}, open("全量逐年优秀AB_最终分组.json", "w"), ensure_ascii=False, indent=1)
