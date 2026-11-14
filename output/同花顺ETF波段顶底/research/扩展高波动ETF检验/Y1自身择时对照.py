"""Y1 的择时信号由「创业板÷红利」换成标的自身。事前写定（跑之前）：
买卖规则全同 Y1（牛市：金叉 或 站上10日线且K−D≥5.3 → 次日开盘买；熊市不开新仓；卖 = 死叉 或 熊市且收盘破10日线）。只换择时：
- Y1：R2 = 159915 ÷ 510880（前复权）高于其 20 日均线为牛（详情页现行）。
- S1 自身比值：本 ETF ÷ 510880（前复权，只用两边都有的日期）高于其 20 日均线为牛。
- S2 自身绝对：本 ETF 前复权收盘 高于自身 20 日均线为牛。
均线未形成按牛；某日无值沿用之前最近一天（因果）。
合格标准（事先定）：39 只（去掉 588170）全历史卡玛比平均高于 Y1，且熊 2021-02～2024-01 年化平均不低于 Y1。
样本全部高波动 40 只；汇总用平均值；另报现行（只认金叉，R2）作参考。"""
import math, random, statistics
from multiprocessing import Pool
import importlib.util, run_extended as X, regime_multi as RM
spec = importlib.util.spec_from_file_location("Y", "B加KD10择时破线卖对照.py"); Y = importlib.util.module_from_spec(spec); spec.loader.exec_module(Y)
T = Y.T; K = Y.K
VAR = {"现行": None, "Y1": Y.VAR["Y1"], "S1": {**Y.VAR["Y1"], "N": "SELF-R"}, "S2": {**Y.VAR["Y1"], "N": "SELF-A"}}
KEYS = list(VAR); WINDOWS = K.WINDOWS; FULL = ("1900-01-01", "2026-11-10")
def init():
    T.init(); p880 = RM.load_new("510880")
    for d in T.M.PANEL.values():
        own = RM.series_from_rows(d["rows"])
        d["reg"]["SELF-R"] = RM.last_known(RM.ma_state(RM.ratio(own, p880), 20), d["dates"])
        d["reg"]["SELF-A"] = RM.last_known(RM.ma_state(own, 20), d["dates"])
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = K.simulate_kd(d, T.BASE, w, 20) if key == "现行" else Y.simulate_y(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def bullshare(code):
    d = T.M.PANEL[code]; return {k: sum(d["reg"][k][120:]) / max(1, len(d["dates"]) - 120) for k in ("R2-20", "SELF-R", "SELF-A")}
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=init) as p:
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS]); bs = p.map(bullshare, GRP)
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    print("## 牛市天数占比（诊断，40 只平均）  " + "  ".join(f"{k} {mean(b[k] for b in bs)*100:.1f}%" for k in ("R2-20", "SELF-R", "SELF-A")))
    R = {(k, w): o for k, w, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    G39 = [c for c in GRP if c != "P588170"]
    for gname, grp in (("去掉 588170 的 39 只", G39), ("全部高波动 40 只", GRP)):
        print(f"\n######## {gname}")
        for wn, a, z in WINDOWS:
            if gname.startswith("全部") and wn != "全历史": continue
            w = (a, z); base = R[("现行", w)]; ms = [base[c] for c in grp if c in base]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<4} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%"
                if k in ("S1", "S2"):
                    bo = R[("Y1", w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                    S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                    d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                    line += f"\n       较Y1：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                    if wn == "全历史":
                        pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                        dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                        line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
    print("\n## 合格判定（39 只）")
    bear = ("2021-02-19", "2024-01-31")
    cm = lambda k: mean(cal(R[(k, FULL)][c]) for c in G39 if c in R[(k, FULL)] and cal(R[(k, FULL)][c]) is not None)
    bm = lambda k: mean(R[(k, bear)][c]["cagr"] for c in G39 if c in R[(k, bear)] and R[(k, bear)][c]["cagr"] is not None)
    for k in ("S1", "S2"):
        ok = cm(k) > cm("Y1") and bm(k) >= bm("Y1")
        print(f"  {k}: 卡玛 {cm(k):.3f}（Y1 {cm('Y1'):.3f}，现行 {cm('现行'):.3f}）  熊市年化 {bm(k)*100:.2f}%（Y1 {bm('Y1')*100:.2f}%） → {'合格' if ok else '不合格'}")
