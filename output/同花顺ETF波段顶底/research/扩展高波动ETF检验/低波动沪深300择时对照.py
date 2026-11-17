"""低波动 ETF 改用沪深300 择时。事前写定（跑之前）：
样本：原主池年化波动 < 31% 的 30 只；另报主题去重（相关≥0.93 合并，保留历史最长）。
择时信号（均线未形成按牛，某日无值沿用之前最近一天）：
- R2：创业板159915 ÷ 红利510880 高于 20 日均线（现用）。
- H1：沪深300 指数 ÷ 红利510880（前复权）高于 20 日均线。
- H2：沪深300 指数 高于自身 20 日均线。
规则：纯MACD（不择时）；现行规则（牛市金叉买、熊市不开新仓、死叉尾盘卖）× R2/H1/H2；Y1 规则 × R2/H1/H2。
合格标准（事先定）：现行·H1 或 现行·H2 的全历史卡玛比平均高于 现行·R2，且熊 2021-02～2024-01 年化平均不低于 现行·R2。汇总用平均值。"""
import math, random, statistics, itertools
from multiprocessing import Pool
import importlib.util, run_extended as X, regime_multi as RM
spec = importlib.util.spec_from_file_location("Y", "B加KD10择时破线卖对照.py"); Y = importlib.util.module_from_spec(spec); spec.loader.exec_module(Y)
T = Y.T; K = Y.K
VAR = {"纯MACD": {**T.BASE, "N": "ALL"}, "现行·R2": T.BASE, "现行·H1": {**T.BASE, "N": "H1"}, "现行·H2": {**T.BASE, "N": "H2"},
       "Y1·R2": Y.VAR["Y1"], "Y1·H1": {**Y.VAR["Y1"], "N": "H1"}, "Y1·H2": {**Y.VAR["Y1"], "N": "H2"}}
KEYS = list(VAR); WINDOWS = K.WINDOWS; FULL = ("1900-01-01", "2026-11-10")
def init():
    T.init(); hs = RM.index_series("sh000300"); p880 = RM.load_new("510880")
    h1 = RM.ma_state(RM.ratio(hs, p880), 20); h2 = RM.ma_state(hs, 20)
    for d in T.M.PANEL.values():
        d["reg"]["ALL"] = [True] * len(d["dates"]); d["reg"]["H1"] = RM.last_known(h1, d["dates"]); d["reg"]["H2"] = RM.last_known(h2, d["dates"])
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = K.simulate_kd(d, VAR[key], w, 20) if key.startswith(("纯MACD", "现行")) else Y.simulate_y(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    LOW = ["P"+k for k, d in pool.items() if vol(d["rows"]) < .31]
    def lr(rs):
        s = RM.series_from_rows(rs); ds = sorted(s); return {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
    LR = {g: lr(pool[g[1:]]["rows"]) for g in LOW}; parent = {g: g for g in LOW}
    def find(a):
        while parent[a] != a: a = parent[a]
        return a
    for a, b in itertools.combinations(LOW, 2):
        c = [x for x in LR[a] if x in LR[b]]
        if len(c) >= 120 and statistics.correlation([LR[a][x] for x in c], [LR[b][x] for x in c]) >= .93: parent[find(a)] = find(b)
    gs = {}
    for g in LOW: gs.setdefault(find(g), []).append(g)
    DEDUP = [max(g, key=lambda c: len(pool[c[1:]]["rows"])) for g in gs.values()]
    print(f"## 低波动样本 {len(LOW)} 只：" + " ".join(f"{c[1:]}{pool[c[1:]].get('name','')}" for c in LOW))
    print(f"   去重后 {len(DEDUP)} 组；合并：" + "；".join(" ".join(c[1:] for c in g) for g in gs.values() if len(g) > 1))
    with Pool(8, initializer=init) as p: res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
    R = {(k, w): o for k, w, o in res}
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    for gname, grp in ((f"低波动 {len(LOW)} 只", LOW), (f"低波动去重 {len(DEDUP)} 只", DEDUP)):
        print(f"\n######## {gname}")
        for wn, a, z in WINDOWS:
            if gname.startswith("低波动去重") and wn != "全历史": continue
            w = (a, z); ms = [R[("纯MACD", w)][c] for c in grp if c in R[("纯MACD", w)]]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<6} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%  n={len(cs)}"
                if k in ("现行·H1", "现行·H2", "Y1·H1", "Y1·H2"):
                    for ref in (k.split("·")[0] + "·R2",):
                        bo = R[(ref, w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                        S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                        d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                        line += f"\n         较{ref}：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                        if wn == "全历史":
                            pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                            dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                            line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
    print("\n## 合格判定（低波动全部）")
    bear = ("2021-02-19", "2024-01-31")
    cm = lambda k: mean(cal(R[(k, FULL)][c]) for c in LOW if c in R[(k, FULL)] and cal(R[(k, FULL)][c]) is not None)
    bm = lambda k: mean(R[(k, bear)][c]["cagr"] for c in LOW if c in R[(k, bear)] and R[(k, bear)][c]["cagr"] is not None)
    for k in ("现行·H1", "现行·H2", "Y1·H1", "Y1·H2"):
        ref = k.split("·")[0] + "·R2"; ok = cm(k) > cm(ref) and bm(k) >= bm(ref)
        print(f"  {k}: 卡玛 {cm(k):.3f}（{ref} {cm(ref):.3f}）  熊市年化 {bm(k)*100:.2f}%（{ref} {bm(ref)*100:.2f}%） → {'合格' if ok else '不合格'}{'' if k.startswith('现行') else '（参考）'}")
    def share(n): return mean(sum(T.M.PANEL[c]["reg"][n][120:]) / max(1, len(T.M.PANEL[c]["dates"]) - 120) for c in LOW)
