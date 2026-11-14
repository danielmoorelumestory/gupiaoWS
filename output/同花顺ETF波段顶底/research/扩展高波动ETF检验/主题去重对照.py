"""按主题去重后重算 现行 / B+KD10原版(E0) / Y1。事前写定（跑之前）：
样本：全部高波动 41 只（原主池 31 + 池外 10）。日对数收益相关系数 ≥ 阈值（共同交易日 ≥120）的两只连成一组（连锁合并），
每组只保留历史最长（日线最多）的一只。主阈值 0.93，敏感性 0.90、0.95。
另报去重后再去掉 588170 的结果（588170 若单独成组则样本变小后影响更大，补充于首次运行后，属追加报告）。
另做主题整组 bootstrap（主阈值分组，保留全部 41 只，按组重抽 1000 次，种子 20261113）。汇总用平均值。"""
import math, random, statistics, itertools
from multiprocessing import Pool
import importlib.util, run_extended as X, regime_multi as RM
spec = importlib.util.spec_from_file_location("Y", "B加KD10择时破线卖对照.py"); Y = importlib.util.module_from_spec(spec); spec.loader.exec_module(Y)
T = Y.T; K = Y.K
KEYS = ["现行", "E0", "Y1"]; WINDOWS = K.WINDOWS; FULL = ("1900-01-01", "2026-11-10")
def init(): T.init()
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = Y.sim(d, key, w)
        if r: out[code] = r["metric"]
    return key, w, out
def groups(G, R, th):
    parent = {g: g for g in G}
    def find(a):
        while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for a, b in itertools.combinations(G, 2):
        c = [d for d in R[a] if d in R[b]]
        if len(c) >= 120 and statistics.correlation([R[a][d] for d in c], [R[b][d] for d in c]) >= th: parent[find(a)] = find(b)
    out = {}
    for g in G: out.setdefault(find(g), []).append(g)
    return list(out.values())
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    rows = {**{"P"+k: v["rows"] for k, v in pool.items()}, **{"N"+k: v["rows"] for k, v in new.items()}}
    def lr(rs):
        s = RM.series_from_rows(rs); ds = sorted(s); return {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
    LR = {g: lr(rows[g]) for g in GRP}
    with Pool(8, initializer=init) as p: res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
    R = {(k, w): o for k, w, o in res}
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    GS = {th: groups(GRP, LR, th) for th in (.90, .93, .95)}
    print("## 主阈值 0.93 的分组（保留者在前）")
    keep = {}
    for th, gs in GS.items():
        keep[th] = [max(g, key=lambda c: len(rows[c])) for g in gs]
    for g in sorted(GS[.93], key=len, reverse=True):
        k = max(g, key=lambda c: len(rows[c]))
        if len(g) > 1: print(f"  保留 {k[1:]}  合并 " + " ".join(c[1:] for c in g if c != k))
    print(f"  0.90 → {len(keep[.90])} 组；0.93 → {len(keep[.93])} 组；0.95 → {len(keep[.95])} 组；588170 是否保留（0.93）：{'P588170' in keep[.93]}")
    def table(grp, label, windows=WINDOWS):
        print(f"\n######## {label}（{len(grp)} 只）")
        for wn, a, z in windows:
            w = (a, z); ms = [R[("现行", w)][c] for c in grp if c in R[("现行", w)]]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            line = f"  {wn:<18}（{'年化' if use=='cagr' else '累计'}）"
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line += f"  {k} {mean(o[c][use] for c in cs)*100:6.2f}%/{mean(o[c]['mdd'] for c in cs)*100:5.1f}%" + (f"/卡玛{mean(cl):.3f}" if wn == "全历史" else "")
            print(line + f"  n={len(cs)}")
    for th in (.93, .90, .95):
        table(keep[th], f"去重 阈值{th:.2f}", WINDOWS if th == .93 else WINDOWS[:1])
        table([c for c in keep[th] if c != "P588170"], f"去重 阈值{th:.2f} 且去掉588170", WINDOWS if th == .93 else WINDOWS[:1])
    table(GRP, "未去重 全部", WINDOWS[:1]); table([c for c in GRP if c != "P588170"], "未去重 去掉588170", WINDOWS[:1])
    # 主题整组 bootstrap：Y1 对 现行、E0 的全历史 卡玛差 与 年化差
    gs = GS[.93]; rnd = random.Random(20261113); o = {k: R[(k, FULL)] for k in KEYS}
    print("\n## 主题整组 bootstrap（0.93 分组，41 只全部保留，按组重抽）")
    for ref in ("现行", "E0"):
        dc, dr = [], []
        for _ in range(1000):
            s = [c for g in (rnd.choice(gs) for _ in gs) for c in g]
            pk = [c for c in s if c in o["Y1"] and c in o[ref] and cal(o["Y1"][c]) is not None and cal(o[ref][c]) is not None]
            dc.append(mean(cal(o["Y1"][c]) - cal(o[ref][c]) for c in pk)); dr.append(mean(o["Y1"][c]["cagr"] - o[ref][c]["cagr"] for c in pk))
        dc.sort(); dr.sort()
        print(f"  Y1 较{ref}：卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]  年化差 95%[{dr[25]*100:+.1f},{dr[974]*100:+.1f}]")
