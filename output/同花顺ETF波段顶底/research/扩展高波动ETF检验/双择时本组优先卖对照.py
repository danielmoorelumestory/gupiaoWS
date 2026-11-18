"""用户要求（2026-11-18，更正后的规则）：仍双择时（A/B 任一策略发出买入即买，持仓不重复）。卖出：
- 本组策略发起的买入：按本组策略卖出；
- 另一策略发起的买入：本组策略或发起方策略，谁先出卖出信号就按谁卖（本组优先，同日都出按本组）。
（A 组→本组=策略A；B 组→本组=策略B；两组都有的按 A；其他面板 ETF 分别报「本组=A」「本组=B」。）事前写定：
其余（成交时点、成本、分红）与 双择时并行对照.py 相同。对照：现行分组（只用本组策略）、上一版双择时（谁发起谁卖）。
注：策略A 卖出 = 死叉 或（创业板择时熊且破10日线），策略B 卖出 = 死叉，A 的卖出条件包含 B；故 B 组上本规则与「谁发起谁卖」等价，A 组上等于「全部按 A 卖」。
统计：2020 年起与全历史组合指标、每年等权组合收益、亏损年数、<5% 年数、最差年。
合格（事先定）：A 组、B 组、A+B 合并上，2020 年起组合卡玛与全历史最差年都不差于现行分组。历史统计，不构成投资建议。"""
import importlib.util, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("D", "双择时并行对照.py"); D = importlib.util.module_from_spec(sp); sp.loader.exec_module(D)
C, X, GA, GB, E = D.C, D.X, D.GA, D.GB, D.E
def sim2(d, entry, own, cost=20):
    span = E.bounds(d, C.FULL)
    if span is None: return None
    start, end = span; S = D.sigs(d)
    op, cl, s, u, dates = d["open"], d["close"], d["s"], d["u"], d["dates"]
    cash, reserve, q = 1.0, 0.0, 0.0; pending = None; ent_i = None; who_in = None; nav = {}; cnt = {"A": 0, "B": 0}
    ex = lambda i: S[own][1](i) or (who_in != own and S[who_in][1](i))
    for i in range(start, end + 1):
        if q and i > start: reserve += q/s[i-1]*(u[i]-u[i-1]); q *= s[i]/s[i-1]
        if pending:
            act, who = pending
            if act == "buy": q = cash/(op[i]*(1 + cost/20000)); cash = 0.0; ent_i = i; who_in = who; cnt[who] += 1
            else: cash = q*op[i]*(1 - cost/20000); q = 0.0
            pending = None
        sold = False
        if q and i != end and ent_i != i and ex(i): cash = q*cl[i]*(1 - cost/20000); q = 0.0; sold = True
        value = cash + reserve + q*cl[i]
        if i == end and q: cash = q*cl[i]*(1 - cost/20000); q = 0.0; value = cash + reserve
        nav[dates[i]] = value
        if i == end or sold: continue
        if q:
            if ex(i): pending = ("sell", None)
        else:
            for who in [own] + [w for w in entry if w != own]:
                if who in entry and S[who][0](i): pending = ("buy", who); break
    return nav, cnt
def job(key):
    C.init(); d = C.T.M.PANEL[key]; code, base = D.job(key)
    for g in ("A", "B"):
        base[f"{g}·只用本组"] = sim2(d, (g,), g) or ({}, {})
        base[f"{g}·双择时本组优先卖"] = sim2(d, ("A", "B"), g) or ({}, {})
    ref = {"A": base["单用A"][0], "B": base["单用B"][0]}
    base["chk"] = max((max(abs(ref[g][t]/base[f"{g}·只用本组"][0][t] - 1) for t in ref[g]) if ref[g] else 0) for g in "AB")
    return code, base
grp = lambda c: "A" if c in GA else "B"
NAMES = ["现行分组", "双择时·谁发起谁卖", "双择时·本组优先卖"]
def series(res, c, n, g=None):
    g = g or grp(c)
    if n == "现行分组": return res[c][f"{g}·只用本组"]
    if n == "双择时·谁发起谁卖": return res[c]["双择时·A优先" if g == "A" else "双择时·B优先"]
    return res[c][f"{g}·双择时本组优先卖"]
def block(res, codes, title, g=None):
    out = {}; print(f"\n## {title}（{len(codes)} 只）")
    for W in (("2020-01-02", X.END), ("1900-01-01", X.END)):
        for n in NAMES:
            cs = [c for c in codes if series(res, c, n, g)[0]]
            out[(W[0], n)] = C.metrics(C.portfolio(cs, {c: C.daily(series(res, c, n, g)[0]) for c in cs}, W))
    yrs = sorted(out[("1900-01-01", NAMES[0])]["years"])
    print("  " + f"{'':<14}" + "".join(f"{y[2:]:>5}" for y in yrs) + " ｜亏损年 <5%年 最差年 全期年化  回撤  卡玛 ｜2020起 年化  回撤  卡玛 ｜每只买入 A发起 B发起")
    for n in NAMES:
        m = out[("1900-01-01", n)]; m2 = out[("2020-01-02", n)]; v = [m["years"][y] for y in yrs]
        cs = [c for c in codes if series(res, c, n, g)[0]]
        na = statistics.mean(series(res, c, n, g)[1].get("A", 0) for c in cs); nb = statistics.mean(series(res, c, n, g)[1].get("B", 0) for c in cs)
        print("  " + f"{n:<14}" + "".join(f"{x*100:5.0f}" for x in v) + f" ｜{sum(x<0 for x in v):4d} {sum(x<0.05 for x in v):5d} {min(v)*100:+6.1f} {m['cagr']*100:6.1f}% {m['mdd']*100:6.1f}% {m['cal']:4.2f} ｜ {m2['cagr']*100:5.1f}% {m2['mdd']*100:6.1f}% {m2['cal']:4.2f} ｜ {na:5.1f} {nb:5.1f}")
    return out
if __name__ == "__main__":
    C.init()
    with Pool(8) as p: res = dict(p.map(job, list(C.T.M.PANEL)))
    print(f"校验：只用本组时与引擎净值最大相对误差 {max(o['chk'] for o in res.values()):.2e}")
    ab = list(dict.fromkeys([c for c in GA + GB if c in res])); panel = [c for c in res if res[c]["单用A"][0]]
    K = {"A 组": block(res, [c for c in GA if c in res], "A 组"), "B 组": block(res, [c for c in GB if c in res], "B 组"), "A+B 合并": block(res, ab, "A+B 合并（各按本组）")}
    block(res, panel, "全部面板·本组=A", "A"); block(res, panel, "全部面板·本组=B", "B")
    print("\n## 合格判定：A 组、B 组、A+B 合并上 2020 年起卡玛 与 全历史最差年 都不差于现行分组")
    ck = [K[t][("2020-01-02", NAMES[2])]["cal"] >= K[t][("2020-01-02", NAMES[0])]["cal"] for t in K] + [K[t][("1900-01-01", NAMES[2])]["worst"] >= K[t][("1900-01-01", NAMES[0])]["worst"] for t in K]
    print(f"  双择时·本组优先卖：{'合格' if all(ck) else '不合格'}（{sum(ck)}/6）")
