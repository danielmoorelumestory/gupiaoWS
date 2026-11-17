"""Y1 的 10 日线改为 11 日 / 12 日线。事前写定（跑之前）：
- Y1：B+KD10 买入（牛市 金叉 或 收盘由线下/平站上 10 日线且 K−D≥5.3）；卖出 = 死叉 或（择时熊市 且 收盘 < 10 日线）。（详情页现行）
- Y11 / Y12：买入的「站上」与卖出的「跌破」都改用 11 / 12 日线（主测试）。
- 诊断（不作合格判定）：Y1卖11 / Y1卖12 只改卖出用的均线，买入仍用 10 日线；Y11买 / Y12买 只改买入。
均线按前复权收盘 Decimal 计算，与引擎 10 日线写法一致；N 日线前 N−1 根无值（不在线上也不在线下）。
合格标准（事先定）：去掉 588170 的高波动样本，全历史卡玛平均高于 Y1 与现行，熊 2021-02～2024-01 年化平均不低于 Y1，
且主题去重（0.93）后卡玛平均也高于 Y1。样本全部高波动 41 只；汇总用平均值；主题整组 bootstrap（种子 20261115）。"""
import math, random, statistics
from decimal import Decimal
from multiprocessing import Pool
import importlib.util, run_extended as X, regime_multi as RM
spec = importlib.util.spec_from_file_location("Y", "B加KD10择时破线卖对照.py"); Y = importlib.util.module_from_spec(spec); spec.loader.exec_module(Y)
spec = importlib.util.spec_from_file_location("D", "主题去重对照.py"); D = importlib.util.module_from_spec(spec); spec.loader.exec_module(D)
T = Y.T; K = Y.K
VAR = {"现行": None, "Y1": (10, 10), "Y11": (11, 11), "Y12": (12, 12), "Y1卖11": (10, 11), "Y1卖12": (10, 12), "Y11买": (11, 10), "Y12买": (12, 10)}
KEYS = list(VAR); MAIN = ["Y11", "Y12"]; WINDOWS = K.WINDOWS; FULL = ("1900-01-01", "2026-11-10")
AB = {}
def ab(rows, n):
    c = [Decimal(r["adjusted_close"]) for r in rows]; above = [False]*len(c); below = above.copy()
    for i in range(n-1, len(c)):
        m = sum(c[i-n+1:i+1])/n; above[i], below[i] = c[i] > m, c[i] < m
    return above, below
def init():
    T.init()
    for code, d in T.M.PANEL.items(): AB[code] = {n: ab(d["rows"], n) for n in (10, 11, 12)}
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        if key == "现行": r = Y.sim(d, "现行", w)
        else:
            ni, no = VAR[key]; r = Y.simulate_y({**d, "above": AB[code][ni][0], "below": AB[code][no][1]}, Y.VAR["Y1"], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def check(_):
    bad = 0
    for code, d in T.M.PANEL.items():
        bad += AB[code][10] != (d["above"], d["below"])
        bad += (Y.sim(d, "Y1", FULL) or {}).get("metric") != (Y.simulate_y({**d, "above": AB[code][10][0], "below": AB[code][10][1]}, Y.VAR["Y1"], FULL, 20) or {}).get("metric")
    return bad
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    rows = {**{"P"+k: v["rows"] for k, v in pool.items()}, **{"N"+k: v["rows"] for k, v in new.items()}}
    def lr(rs):
        s = RM.series_from_rows(rs); ds = sorted(s); return {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
    LR = {g: lr(rows[g]) for g in GRP}
    with Pool(8, initializer=init) as p:
        assert p.map(check, [0])[0] == 0; print("自检通过：10 日线重算 = 引擎，Y1 结果一致")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
    R = {(k, w): o for k, w, o in res}
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    gs = D.groups(GRP, LR, .93); keep = [max(g, key=lambda c: len(rows[c])) for g in gs]
    G40 = [c for c in GRP if c != "P588170"]; K25 = [c for c in keep if c != "P588170"]
    def table(grp, label, windows):
        print(f"\n######## {label}（{len(grp)} 只）")
        for wn, a, z in windows:
            w = (a, z); ms = [R[("现行", w)][c] for c in grp if c in R[("现行", w)]]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<6} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%"
                if k not in ("现行", "Y1"):
                    bo = R[("Y1", w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261115)
                    S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                    d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                    line += f"\n         较Y1：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                    if wn == "全历史":
                        pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                        dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                        line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
    table(G40, "去掉 588170 的高波动", WINDOWS)
    table(GRP, "全部高波动", WINDOWS[:1])
    table(K25, "主题去重0.93 且去掉588170", WINDOWS[:1])
    print("\n## 主题整组 bootstrap（0.93 分组，41 只全部保留，按组重抽，对 Y1）")
    o = {k: R[(k, FULL)] for k in KEYS}
    for k in KEYS[2:]:
        rnd = random.Random(20261115); dc, dr = [], []
        for _ in range(1000):
            s = [c for g in (rnd.choice(gs) for _ in gs) for c in g]
            pk = [c for c in s if c in o[k] and c in o["Y1"] and cal(o[k][c]) is not None and cal(o["Y1"][c]) is not None]
            dc.append(mean(cal(o[k][c]) - cal(o["Y1"][c]) for c in pk)); dr.append(mean(o[k][c]["cagr"] - o["Y1"][c]["cagr"] for c in pk))
        dc.sort(); dr.sort(); print(f"  {k:<6} 卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]  年化差 95%[{dr[25]*100:+.1f},{dr[974]*100:+.1f}]")
    print("\n## 合格判定（主测试 Y11 / Y12）")
    bear = ("2021-02-19", "2024-01-31")
    cm = lambda k, g: mean(cal(R[(k, FULL)][c]) for c in g if c in R[(k, FULL)] and cal(R[(k, FULL)][c]) is not None)
    bm = lambda k: mean(R[(k, bear)][c]["cagr"] for c in G40 if c in R[(k, bear)] and R[(k, bear)][c]["cagr"] is not None)
    for k in MAIN:
        ok = cm(k, G40) > cm("现行", G40) and cm(k, G40) > cm("Y1", G40) and bm(k) >= bm("Y1") and cm(k, K25) > cm("Y1", K25)
        print(f"  {k}: 卡玛 {cm(k, G40):.3f}（现行 {cm('现行', G40):.3f}，Y1 {cm('Y1', G40):.3f}）  熊市年化 {bm(k)*100:.2f}%（Y1 {bm('Y1')*100:.2f}%）  去重卡玛 {cm(k, K25):.3f}（Y1 {cm('Y1', K25):.3f}） → {'合格' if ok else '不合格'}")
