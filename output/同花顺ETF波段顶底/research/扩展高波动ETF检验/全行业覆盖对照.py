"""用户要求（2026-11-18）：A/B 两组行业是否覆盖全面，是否扩充，最好把活跃行业都包含（不好预测哪个行业会突然活跃）。事前写定（跑之前）：
现状：A/B 24 只集中在 TMT（入选用的是同一段历史，偏向过去最强的科技），医药、A股券商、新能源、有色黄金、消费、银行地产、港股科技等均缺席。
扩充池：研究面板 79 只按日收益相关 ≥0.93 连锁去重（同组若含现行 A/B 成员则只留成员，否则留历史最长者），得到「全行业覆盖池」。
新增成员用哪套策略（三种都报）：①全用策略A（Y1+创业板择时，默认）；②全用策略B（只认金叉+沪深300择时）；③按 2021 年底以前全历史卡玛选 A/B（不足 2 年数据的用 A）——③只用 2022 年前信息，2022 年起可视为样本外。
现行 A/B 成员保持原策略。另报只加高波动（≥31%）新增的版本。
组合：等权每日再平衡（未上市的不计入）。统计 2020 年起与全历史：每年收益、亏损年数、<5% 年数、最差年、年化、回撤、卡玛；以及新增各只单独 2020 年起 A/B 卡玛。
判断（事先定）：扩充后 2020 年起卡玛不低于现行的 80%，且全历史最差年不更差，才算「扩充代价可接受」。历史统计，不构成投资建议。"""
import importlib.util, json, math, statistics, itertools
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("D", "双择时并行对照.py"); D = importlib.util.module_from_spec(sp); sp.loader.exec_module(D)
C, X, GA, GB = D.C, D.X, D.GA, D.GB
def _job(k): return D.job(k)
WF, W20 = ("1900-01-01", X.END), ("2020-01-02", X.END)
if __name__ == "__main__":
    C.init(); P = {k[1:]: v for k, v in C.T.M.PANEL.items()}
    with Pool(8) as p: res = dict(p.map(_job, list(C.T.M.PANEL)))
    name = {c: P[c]["item"]["name"].replace("ETF", "") for c in P}; grp = {c: "/".join(P[c]["item"]["groups"]) for c in P}
    R = {}
    for c in P:
        a = [float(r["adjusted_close"]) for r in P[c]["rows"]]; R[c] = {P[c]["dates"][i]: math.log(a[i]/a[i-1]) for i in range(1, len(a)) if a[i-1] > 0}
    par = {c: c for c in P}
    def f(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    for a, b in itertools.combinations(P, 2):
        cm = [t for t in R[a] if t in R[b]]
        if len(cm) >= 120 and statistics.correlation([R[a][t] for t in cm], [R[b][t] for t in cm]) >= 0.93: par[f(a)] = f(b)
    G = {}
    for c in P: G.setdefault(f(c), []).append(c)
    AB = set(GA) | set(GB); keep = []
    for g in G.values():
        mem = [c for c in g if c in AB]
        keep += mem if mem else [max(g, key=lambda c: len(P[c]["rows"]))]
    add = [c for c in keep if c not in AB and res[c]["单用A"][0]]
    print(f"面板 79 只去重后 {len(keep)} 只；现行 A/B {len(AB)} 只；可新增 {len(add)} 只")
    def cal(c, k, w): m = C.window_metrics(res[c][k][0], w); return m
    pre = ("1900-01-01", "2021-12-31")
    def choose(c):
        ma, mb = cal(c, "单用A", pre), cal(c, "单用B", pre)
        n = sum(1 for t in res[c]["单用A"][0] if t <= "2021-12-31")
        if not ma or not mb or n < 488: return "A"
        return "A" if ma["cal"] >= mb["cal"] else "B"
    print("\n## 新增各只（2020 年起单独表现；按行业）")
    for c in sorted(add, key=lambda c: grp[c]):
        ma, mb = cal(c, "单用A", W20), cal(c, "单用B", W20)
        s = lambda m: f"年化{m['cagr']*100:5.1f}% 回撤{m['mdd']*100:6.1f}% 卡玛{m['cal']:5.2f}" if m else "—"
        print(f"  {c} {name[c]:<12} [{grp[c] or '未分组'}] 波动{res[c]['vol']*100:3.0f}% 上市{P[c]['item']['first']} ｜A: {s(ma)} ｜B: {s(mb)} ｜③选{choose(c)}")
    cur = {c: ("单用A" if c in GA else "单用B") for c in AB if c in res}
    hv = [c for c in add if res[c]["vol"] >= 0.31]
    PORT = {"现行 A/B 24 只": cur,
            "扩充·新增全用A": {**cur, **{c: "单用A" for c in add}},
            "扩充·新增全用B": {**cur, **{c: "单用B" for c in add}},
            "扩充·新增按2021前选": {**cur, **{c: "单用" + choose(c) for c in add}},
            "扩充·只加高波动·按2021前选": {**cur, **{c: "单用" + choose(c) for c in hv}},
            "只看新增·按2021前选": {c: "单用" + choose(c) for c in add}}
    out = {n: {w[0]: C.metrics(C.portfolio(list(m), {c: C.daily(res[c][k][0]) for c, k in m.items()}, w)) for w in (WF, W20)} for n, m in PORT.items()}
    yrs = sorted(out["现行 A/B 24 只"]["1900-01-01"]["years"])
    print("\n## 每年等权组合收益（%）")
    print("  " + f"{'':<24}" + "".join(f"{y[2:]:>5}" for y in yrs) + " ｜只数 亏损年 <5%年 最差年 全期年化 回撤 卡玛 ｜2020起 年化 回撤 卡玛")
    base = out["现行 A/B 24 只"]
    for n, m in out.items():
        a, b = m["1900-01-01"], m["2020-01-02"]; v = [a["years"].get(y) for y in yrs]; vv = [x for x in v if x is not None]
        ok = "" if n.startswith("现行") else ("  ✓代价可接受" if b["cal"] >= 0.8*base["2020-01-02"]["cal"] and a["worst"] >= base["1900-01-01"]["worst"] else "  ✗")
        print("  " + f"{n:<24}" + "".join(f"{x*100:5.0f}" if x is not None else "    -" for x in v) + f" ｜{len(PORT[n]):4d} {sum(x<0 for x in vv):4d} {sum(x<0.05 for x in vv):5d} {min(vv)*100:+6.1f} {a['cagr']*100:6.1f}% {a['mdd']*100:6.1f}% {a['cal']:4.2f} ｜ {b['cagr']*100:5.1f}% {b['mdd']*100:6.1f}% {b['cal']:4.2f}{ok}")
