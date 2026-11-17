"""事后追加（2026-11-16，看完 AB组合构建 结果后）：贪心按组合卡玛挑选在样本外输给「24 只全部等权」，
且受上市时间影响（晚上市的成员早年不占权重，回撤看起来更小）。改试不做组合优化的简单规则，同样做样本外检验：
- R1：相关 ≥0.90 聚类（细分主题），每类取卡玛最高者，按卡玛取前 10（截止日前至少 2 个完整年）。
- R2：R1 再加限制：相关 ≥0.80 的同一大类最多 4 只（科技大类不至于全占）。
- 随机：从 A/B 24 只里随机取 10 只（2000 次），看样本外卡玛的分布。
挑选只用 ≤2023-12-31 的数据；样本外 2024-01-02～2026-11-10。注意 A/B 名单本身用了到 2026 的数据，所以「24 只」不算真正样本外。
最后用全部数据按同一规则给出 10 只。历史统计，不构成投资建议。"""
import random, statistics, itertools, math, json, importlib.util
from multiprocessing import Pool
spec = importlib.util.spec_from_file_location("C", "AB组合构建.py"); C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
def _init(): C.init()
def _work(k): return C.work(k)
def rule(R, LR, cut, cap):
    Rc = {c: {d: v for d, v in R[c].items() if d <= cut} for c in R}
    codes = [c for c in R if len(Rc[c]) >= 488]
    cal = {c: C.metrics(C.portfolio([c], Rc, ("1900-01-01", cut)))["cal"] for c in codes}
    LRc = {c: {d: v for d, v in LR[c].items() if d <= cut} for c in codes}
    fine = C.cluster(codes, LRc, .90); broad = C.cluster(codes, LRc, .80)
    big = {c: i for i, g in enumerate(broad) for c in g}
    reps = sorted((max(g, key=lambda c: cal[c]) for g in fine), key=lambda c: -cal[c])
    out, used = [], {}
    for c in reps:
        if cap and used.get(big[c], 0) >= cap: continue
        out.append(c); used[big[c]] = used.get(big[c], 0) + 1
        if len(out) == 10: break
    return out, cal
if __name__ == "__main__":
    C.init(); keys = [k for k in C.T.M.PANEL if k[1:] in C.PLAN]
    with Pool(8, initializer=_init) as p: res = p.map(_work, keys)
    R = {c: C.daily(nav) for c, nav, _ in res}; H = {c: C.daily(h) for c, _, h in res}
    pool, new, audit = C.X.build(); rows = {**{k: v["rows"] for k, v in pool.items()}, **{k: v["rows"] for k, v in new.items()}}
    def lr(rs):
        s = C.RM.series_from_rows(rs); ds = sorted(s); return {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
    LR = {c: lr(rows[c]) for c in C.PLAN}; nm = lambda c: f"{c}{C.NAMES[c]}({C.PLAN[c]})"
    OOS = ("2024-01-02", "2026-11-10"); AB = C.G["A"] + C.G["B"]
    def line(title, m): print(f"  {title:<24} 年化 {m['cagr']*100:5.1f}%  回撤 {m['mdd']*100:6.1f}%  卡玛 {m['cal']:.2f}  赚钱年 {m['pos']}/{len(m['years'])}  最差年 {m['worst']*100:+5.1f}%  逐年 " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    print("## 样本外（挑选只用 ≤2023-12-31）")
    for name, cap in (("R1", 0), ("R2", 4)):
        sel, _ = rule(R, LR, "2023-12-31", cap); print(f"  {name} 当时选出：" + "、".join(nm(c) for c in sel)); line(f"{name} 样本外", C.metrics(C.portfolio(sel, R, OOS)))
    line("A/B 24 只 样本外", C.metrics(C.portfolio(AB, R, OOS)))
    rnd = random.Random(20261116); cals = sorted(C.metrics(C.portfolio(rnd.sample(AB, 10), R, OOS))["cal"] for _ in range(2000))
    print(f"  随机 10 只（24 只中抽）样本外卡玛：中位 {cals[1000]:.2f}  5%～95% [{cals[100]:.2f}, {cals[1900]:.2f}]")
    print("\n## 用全部数据按 R2 规则选出的 10 只（评估 2020-01-02～2026-11-10 与 2021-01-04 起）")
    sel, cal = rule(R, LR, "2026-11-10", 4)
    for c in sel:
        m = C.metrics(C.portfolio([c], R, C.EVAL)); print(f"  {nm(c):<22} 卡玛 {cal[c]:.2f}  年化 {m['cagr']*100:5.1f}%  回撤 {m['mdd']*100:6.1f}%  " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    for w in (C.EVAL, ("2021-01-04", "2026-11-10")):
        line(f"R2 10 只 {w[0][:4]}起", C.metrics(C.portfolio(sel, R, w))); line(f"同 10 只持有 {w[0][:4]}起", C.metrics(C.portfolio(sel, H, w))); line(f"A/B 24 只 {w[0][:4]}起", C.metrics(C.portfolio(AB, R, w)))
    us = [statistics.correlation(*zip(*[(LR[a][d], LR[b][d]) for d in LR[a] if d in LR[b]])) for a, b in itertools.combinations(sel, 2)]
    cs = [statistics.correlation(*zip(*[(R[a][d], R[b][d]) for d in R[a] if d in R[b]])) for a, b in itertools.combinations(sel, 2)]
    print(f"  成员两两相关：标的 平均 {statistics.mean(us):.2f} 最高 {max(us):.2f}；按方案每日收益 平均 {statistics.mean(cs):.2f} 最高 {max(cs):.2f}")
    json.dump({"rule": "R2", "members": [{"code": c, "name": C.NAMES[c], "plan": C.PLAN[c]} for c in sel]}, open("AB组合_10只.json", "w"), ensure_ascii=False, indent=1)
