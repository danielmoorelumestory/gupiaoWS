"""Y1 的择时按标的所属板块换指数。事前写定（跑之前）：
样本：全部高波动 40 只剔除港股/美股/中韩 10 只（159131 159509 159518 159529 159636 159792 159892 513120 513130 513310），
余 A 股 30 只；主看去掉 588170 的 29 只。买卖规则全同 Y1，只换择时比值的分子（分母都是红利 510880，高于 20 日均线为牛）：
  创业板 = 159915，科创50 = 588000，深证100 = 159901，科创创业50 = 159781（均用 ETF 前复权价代表指数）。
分配方法：
- H 持仓法：用 2024～2025 年 8 个季度前十大持仓（东方财富，持仓板块占比_2024-2025前十大.json）按 A 股部分计板块占比：
  创业板 ≥50% → 创业板；科创板 ≥50% → 科创50；创业+科创 ≥50% → 科创创业50；
  否则主板为主：深主板 ≥ 沪主板 → 深证100，沪主板多 → 保持创业板（用户未指定）。
- C 相关法：2021-07-05～2026-11-10 期间与四个指数 ETF 的日对数收益相关系数最高者；共同交易日 <120 则保持创业板。
所分配指数在某日尚无信号（未上市或均线未形成）时，该日沿用 R2（创业板÷红利）。
合格标准（事先定）：29 只全历史卡玛比平均高于 Y1，且熊 2021-02～2024-01 年化平均不低于 Y1。汇总用平均值。"""
import math, random, statistics, json
from multiprocessing import Pool
import importlib.util, run_extended as X, regime_multi as RM
spec = importlib.util.spec_from_file_location("Y", "B加KD10择时破线卖对照.py"); Y = importlib.util.module_from_spec(spec); spec.loader.exec_module(Y)
T = Y.T; K = Y.K
IDX = {"创业板": "159915", "科创50": "588000", "深证100": "159901", "科创创业50": "159781"}
OVERSEAS = {"159131", "159509", "159518", "159529", "159636", "159792", "159892", "513120", "513130", "513310"}
SHARE = json.load(open("持仓板块占比_2024-2025前十大.json"))
def by_holding(code):
    s = SHARE.get(code)
    if not s: return "创业板"
    a = {k: v for k, v in s["share"].items() if k in ("创业板", "科创板", "深主板", "沪主板")}; t = sum(a.values()); a = {k: v/t for k, v in a.items()}
    cy, kc, sz, sh = (a.get(k, 0) for k in ("创业板", "科创板", "深主板", "沪主板"))
    if cy >= .5: return "创业板"
    if kc >= .5: return "科创50"
    if cy + kc >= .5: return "科创创业50"
    return "深证100" if sz >= sh else "创业板"
def logret(series):
    ds = sorted(series); return {ds[i]: math.log(series[ds[i]]/series[ds[i-1]]) for i in range(1, len(ds))}
def by_corr(own, idx_ret):
    r = logret(own); best, bc = "创业板", -2
    common = [d for d in r if "2021-07-05" <= d <= "2026-11-10" and all(d in v for v in idx_ret.values())]
    if len(common) < 120: return "创业板", None
    for name, v in idx_ret.items():
        x = [r[d] for d in common]; y = [v[d] for d in common]; c = statistics.correlation(x, y)
        if c > bc: best, bc = name, c
    return best, bc
ASSIGN = {}
def init():
    T.init(); p880 = RM.load_new("510880"); r2 = RM.ma_state(RM.ratio(RM.load_new("159915"), p880), 20)
    ser = {n: RM.load_new(c) for n, c in IDX.items()}; idx_ret = {n: logret(s) for n, s in ser.items()}
    sig = {}
    for n, s in ser.items():
        x = RM.ma_state(RM.ratio(s, p880), 20)
        sig[n] = {d: (x[d] if x.get(d) is not None else r2.get(d)) for d in set(r2) | set(x)}
    for key, d in T.M.PANEL.items():
        code = key[1:]; h = by_holding(code); c, cc = by_corr(RM.series_from_rows(d["rows"]), idx_ret)
        ASSIGN[key] = (h, c, cc)
        d["reg"]["HOLD"] = RM.last_known(sig[h], d["dates"]); d["reg"]["CORR"] = RM.last_known(sig[c], d["dates"])
VAR = {"现行": None, "Y1": Y.VAR["Y1"], "H持仓法": {**Y.VAR["Y1"], "N": "HOLD"}, "C相关法": {**Y.VAR["Y1"], "N": "CORR"}}
KEYS = list(VAR); WINDOWS = K.WINDOWS; FULL = ("1900-01-01", "2026-11-10")
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = K.simulate_kd(d, T.BASE, w, 20) if key == "现行" else Y.simulate_y(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def assign(_): return ASSIGN
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    A = [c for c in GRP if c[1:] not in OVERSEAS]; A29 = [c for c in A if c != "P588170"]
    with Pool(8, initializer=init) as p:
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS]); AS = p.map(assign, [0])[0]
    print(f"## 分配结果（A 股 {len(A)} 只）")
    for c in A:
        h, cr, cc = AS[c]; print(f"  {c[1:]}  持仓法 {h:<6} 相关法 {cr:<6}" + (f"（相关 {cc:.2f}）" if cc is not None else "（数据不足，保持创业板）"))
    from collections import Counter
    print("  持仓法计数 " + str(dict(Counter(AS[c][0] for c in A))) + "  相关法计数 " + str(dict(Counter(AS[c][1] for c in A))))
    R = {(k, w): o for k, w, o in res}
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    for gname, grp in (("A 股去掉 588170 的 29 只", A29), ("A 股 30 只", A)):
        print(f"\n######## {gname}")
        for wn, a, z in WINDOWS:
            if gname == "A 股 30 只" and wn != "全历史": continue
            w = (a, z); base = R[("现行", w)]; ms = [base[c] for c in grp if c in base]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<5} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  n={len(cs)}"
                if k in ("H持仓法", "C相关法"):
                    bo = R[("Y1", w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                    S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                    d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                    line += f"\n        较Y1：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}  相同 {sum(o[c][use] == bo[c][use] for c in pc)}"
                    if wn == "全历史":
                        pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                        dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                        line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
        if gname.startswith("A 股去掉"):
            print("\n## 逐只全历史年化（Y1 → 持仓法 / 相关法，只列分配到非创业板的）")
            o1 = R[("Y1", FULL)]; oh = R[("H持仓法", FULL)]; oc = R[("C相关法", FULL)]
            for c in grp:
                if AS[c][0] == "创业板" and AS[c][1] == "创业板": continue
                f = lambda o: f"{(o[c]['cagr'] or 0)*100:6.1f}%/{o[c]['mdd']*100:5.1f}%"
                print(f"  {c[1:]}  Y1 {f(o1)}  持仓法[{AS[c][0]}] {f(oh)}  相关法[{AS[c][1]}] {f(oc)}")
    print("\n## 合格判定（A 股 29 只）")
    bear = ("2021-02-19", "2024-01-31")
    cm = lambda k: mean(cal(R[(k, FULL)][c]) for c in A29 if c in R[(k, FULL)] and cal(R[(k, FULL)][c]) is not None)
    bm = lambda k: mean(R[(k, bear)][c]["cagr"] for c in A29 if c in R[(k, bear)] and R[(k, bear)][c]["cagr"] is not None)
    for k in ("H持仓法", "C相关法"):
        ok = cm(k) > cm("Y1") and bm(k) >= bm("Y1")
        print(f"  {k}: 卡玛 {cm(k):.3f}（Y1 {cm('Y1'):.3f}）  熊市年化 {bm(k)*100:.2f}%（Y1 {bm('Y1')*100:.2f}%） → {'合格' if ok else '不合格'}")
