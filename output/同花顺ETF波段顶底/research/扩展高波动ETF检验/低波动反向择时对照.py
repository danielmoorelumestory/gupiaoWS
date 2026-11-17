"""低波动 ETF：择时反过来用（择时熊市才买、择时牛市不开新仓）。事前写定（跑之前）：
样本：原主池中年化波动 < 31% 的 ETF（低波动组）。择时 R2 = 创业板159915 ÷ 红利510880 高于 20 日均线为牛。
- 纯MACD：不择时，金叉买、死叉尾盘卖。
- 现行：R2 牛市金叉买，熊市不开新仓，死叉尾盘卖。
- Y1：详情页规则原样（牛市：金叉 或 站上10日线且K−D≥5.3 买；卖 = 死叉 或 熊市且破10日线）。
- INV：Y1 完全镜像——R2 熊市才买（金叉 或 站上10日线且K−D≥5.3），R2 牛市不开新仓；卖 = 死叉 或 R2 牛市且破10日线。
- INV-a：R2 熊市才买（同上），卖出只认死叉。
次日开盘买；卖出当天尾盘，买入当天触发则次日开盘（T+1）。
合格标准（事先定）：INV 或 INV-a 的全历史卡玛比平均高于 纯MACD、现行、Y1 三者，且熊 2021-02～2024-01 年化平均不低于纯MACD。
另报主题去重结果（日收益相关 ≥0.93 连锁合并，每组保留历史最长）。汇总用平均值。"""
import math, random, statistics, itertools
from multiprocessing import Pool
import importlib.util, run_extended as X, regime_multi as RM
spec = importlib.util.spec_from_file_location("Y", "B加KD10择时破线卖对照.py"); Y = importlib.util.module_from_spec(spec); spec.loader.exec_module(Y)
T = Y.T; K = Y.K
VAR = {"纯MACD": {**T.BASE, "N": "ALL"}, "现行": T.BASE, "Y1": Y.VAR["Y1"],
       "INV": {**Y.VAR["Y1"], "N": "INV"}, "INV-a": {**Y.VAR["Y1"], "N": "INV", "anyx": False, "keep": False}}
KEYS = list(VAR); WINDOWS = K.WINDOWS; FULL = ("1900-01-01", "2026-11-10")
def init():
    T.init()
    for d in T.M.PANEL.values():
        r = d["reg"]["R2-20"]; d["reg"]["INV"] = [not x for x in r]; d["reg"]["ALL"] = [True] * len(r)
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = K.simulate_kd(d, VAR[key], w, 20) if key in ("纯MACD", "现行") else Y.simulate_y(d, VAR[key], w, 20)
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
                if k.startswith("INV"):
                    for ref in ("纯MACD", "Y1"):
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
    for k in ("INV", "INV-a"):
        ok = all(cm(k) > cm(r) for r in ("纯MACD", "现行", "Y1")) and bm(k) >= bm("纯MACD")
        print(f"  {k}: 卡玛 {cm(k):.3f}（纯MACD {cm('纯MACD'):.3f}，现行 {cm('现行'):.3f}，Y1 {cm('Y1'):.3f}）  熊市年化 {bm(k)*100:.2f}%（纯MACD {bm('纯MACD')*100:.2f}%） → {'合格' if ok else '不合格'}")
