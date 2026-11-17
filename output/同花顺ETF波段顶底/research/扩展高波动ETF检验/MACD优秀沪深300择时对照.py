"""MACD优秀 分组 20 只改用沪深300 择时。事前写定（跑之前）：
样本：BusinessWeb MACD优秀 清单 20 只（MACD优秀清单_20只.json，按纯 MACD 跑赢一直持有入选，存在选样偏差，纯MACD 会天然偏好）。
择时：R2 = 创业板159915 ÷ 红利510880；H1 = 沪深300 指数 ÷ 红利510880；均高于 20 日均线为牛。
规则：纯MACD（不择时）；现行规则（牛市金叉买、熊市不开新仓、死叉尾盘卖）× R2/H1；Y1 × R2/H1。
合格标准（事先定）：现行·H1 的全历史卡玛比平均高于 现行·R2，且熊 2021-02～2024-01 年化平均不低于 现行·R2；Y1·H1 对 Y1·R2 同理。
另按 年化波动 ≥31% / <31% 分组报告；汇总用平均值，另报主题去重（相关≥0.93 合并，保留历史最长）。"""
import math, random, statistics, itertools, json
from multiprocessing import Pool
import importlib.util, run_extended as X, regime_multi as RM
sp = importlib.util.spec_from_file_location("Z", "低波动沪深300择时对照.py"); Z = importlib.util.module_from_spec(sp); sp.loader.exec_module(Z)
T = Z.T; K = Z.K; Y = Z.Y
VAR = {k: Z.VAR[k] for k in ("纯MACD", "现行·R2", "现行·H1", "Y1·R2", "Y1·H1")}
KEYS = list(VAR); WINDOWS = K.WINDOWS; FULL = ("1900-01-01", "2026-11-10")
CODES = [i["code"] for i in json.load(open("MACD优秀清单_20只.json"))["items"]]
NAMES = {i["code"]: i["name"] for i in json.load(open("MACD优秀清单_20只.json"))["items"]}
def init(): Z.init()
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        if code[1:] not in CODES: continue
        r = K.simulate_kd(d, VAR[key], w, 20) if key.startswith(("纯MACD", "现行")) else Y.simulate_y(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
if __name__ == "__main__":
    pool, new, audit = X.build(); rows = {**{"P"+k: v["rows"] for k, v in pool.items()}, **{"N"+k: v["rows"] for k, v in new.items()}}
    G = []
    for c in CODES:
        k = "P"+c if "P"+c in rows else ("N"+c if "N"+c in rows else None)
        if k is None: print("缺数据", c, NAMES[c]); continue
        G.append(k)
    def vol(rs):
        c = [float(r["adjusted_close"]) for r in rs]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    HI = [c for c in G if vol(rows[c]) >= .31]; LO = [c for c in G if c not in HI]
    def lr(rs):
        s = RM.series_from_rows(rs); ds = sorted(s); return {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
    LR = {g: lr(rows[g]) for g in G}; parent = {g: g for g in G}
    def find(a):
        while parent[a] != a: a = parent[a]
        return a
    for a, b in itertools.combinations(G, 2):
        cc = [x for x in LR[a] if x in LR[b]]
        if len(cc) >= 120 and statistics.correlation([LR[a][x] for x in cc], [LR[b][x] for x in cc]) >= .93: parent[find(a)] = find(b)
    gs = {}
    for g in G: gs.setdefault(find(g), []).append(g)
    DEDUP = [max(g, key=lambda c: len(rows[c])) for g in gs.values()]
    print(f"## 样本 {len(G)} 只（高波动 {len(HI)}：{' '.join(c[1:] for c in HI)}；低波动 {len(LO)}：{' '.join(c[1:] for c in LO)}）")
    print(f"   去重后 {len(DEDUP)} 组；合并：" + "；".join(" ".join(c[1:] for c in g) for g in gs.values() if len(g) > 1))
    with Pool(8, initializer=init) as p: res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
    R = {(k, w): o for k, w, o in res}
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    for gname, grp, wins in ((f"MACD优秀 {len(G)} 只", G, WINDOWS), (f"去重 {len(DEDUP)} 只", DEDUP, WINDOWS[:1]), (f"其中高波动 {len(HI)} 只", HI, WINDOWS[:1]), (f"其中低波动 {len(LO)} 只", LO, WINDOWS[:1])):
        print(f"\n######## {gname}")
        for wn, a, z in wins:
            w = (a, z); ms = [R[("纯MACD", w)][c] for c in grp if c in R[("纯MACD", w)]]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<6} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%  n={len(cs)}"
                if k.endswith("H1"):
                    ref = k.replace("H1", "R2"); bo = R[(ref, w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                    S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                    d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                    line += f"\n         较{ref}：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                    if wn == "全历史":
                        pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                        dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                        line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
    print("\n## 逐只全历史 年化/回撤")
    f = lambda m: f"{m['cagr']*100:6.1f}%/{m['mdd']*100:6.1f}%" if m and m["cagr"] is not None else "   —   "
    for c in sorted(G, key=lambda c: -(R[("现行·H1", FULL)][c]["cagr"] or -9)):
        print(f"  {c[1:]} {NAMES[c[1:]]:<12} {'高' if c in HI else '低'}  " + "  ".join(f"{k} {f(R[(k, FULL)].get(c))}" for k in KEYS))
    print("\n## 合格判定")
    bear = ("2021-02-19", "2024-01-31")
    cm = lambda k: mean(cal(R[(k, FULL)][c]) for c in G if c in R[(k, FULL)] and cal(R[(k, FULL)][c]) is not None)
    bm = lambda k: mean(R[(k, bear)][c]["cagr"] for c in G if c in R[(k, bear)] and R[(k, bear)][c]["cagr"] is not None)
    for k in ("现行·H1", "Y1·H1"):
        ref = k.replace("H1", "R2"); ok = cm(k) > cm(ref) and bm(k) >= bm(ref)
        print(f"  {k}: 卡玛 {cm(k):.3f}（{ref} {cm(ref):.3f}，纯MACD {cm('纯MACD'):.3f}）  熊市年化 {bm(k)*100:.2f}%（{ref} {bm(ref)*100:.2f}%） → {'合格' if ok else '不合格'}")
