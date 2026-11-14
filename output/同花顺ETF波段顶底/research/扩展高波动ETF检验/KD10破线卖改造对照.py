"""B+KD10 买入不变，改造「破10日线卖」。事前写定（跑之前）：
买入（所有变体相同）：牛市 且（MACD 金叉 或「当天收盘站上10日线 且 K−D ≥ 5.3」）→ 次日开盘买；熊市不开新仓。
卖出 = MACD 死叉当天尾盘卖，另加以下「MACD 空头时」的破线条件（均当天尾盘卖；买入当天触发则次日开盘卖）：
- E0 原版：收盘 < 10 日线。
- X0 不设破线卖：只等死叉（参考）。
- X1 两天确认：连续 2 天收盘 < 10 日线。
- X2 缓冲：收盘 < 10 日线 − 0.5×ATR14。
- X3 只止损：收盘 < 10 日线 且 收盘 < 买入价。
- X4 改 20 日线：收盘 < 20 日线。
对照：现行（只认金叉）。合格标准（事先定）：39 只（去掉 588170）全历史卡玛比平均 高于 现行 与 E0，且熊 2021-02～2024-01 年化平均不低于现行。
样本全部高波动 40 只；汇总用平均值；另报各段与 2025 年起。另做 E0 的卖出拆解（诊断）。"""
import math, random, statistics
from multiprocessing import Pool
import B加KD对照 as K, run_extended as X
T = K.T; G = T.G; F = X.F
src = G.src.replace("def simulate_rg(", "def simulate_x(", 1)
for old, new in [
    ('    def exit_sig(i):\n', '''    mlong=data["mlong"];kd=data["_kd"];atr=data["atr"];ma10=data["ma10"];cadj=data["cadj"]
    def brk(i):
        x=config["x"]
        if x=="E0": return below[i]
        if x=="X0": return False
        if x=="X1": return i>0 and below[i] and below[i-1]
        if x=="X2": return math.isfinite(atr[i]) and cadj[i] < ma10[i]-0.5*atr[i]
        if x=="X3": return below[i] and active is not None and cl[i] < active["entry_price"]
        if x=="X4": return ma20b[i]
    def exit_sig(i):
        if not mlong[i] and brk(i): return True
'''),
    ('return config["bullin"]=="ANY" or gold[i]', 'return config["bullin"]=="ANY" or gold[i] or (i>0 and above[i] and not above[i-1] and kd[i] >= 5.3)')]:
    assert src.count(old) == 1; src = src.replace(old, new)
_ns = dict(vars(G.engine)); _ns["math"] = math; exec(src, _ns); simulate_x = _ns["simulate_x"]
def add(d):
    rows = d["rows"]; c = [float(r["adjusted_close"]) for r in rows]; f = [c[i]/float(r["close"]) for i, r in enumerate(rows)]
    hi = [float(r["high"])*f[i] for i, r in enumerate(rows)]; lo = [float(r["low"])*f[i] for i, r in enumerate(rows)]
    tr = [math.nan] + [max(hi[i]-lo[i], abs(hi[i]-c[i-1]), abs(lo[i]-c[i-1])) for i in range(1, len(c))]
    d["atr"] = F._wilder(tr); d["cadj"] = c; d["ma10"] = [sum(c[i-9:i+1])/10 if i >= 9 else math.nan for i in range(len(c))]
def init():
    T.init()
    for d in T.M.PANEL.values(): add(d)
XS = ["E0", "X0", "X1", "X2", "X3", "X4"]
VAR = {"现行": None, **{x: {**T.BASE, "x": x} for x in XS}}
KEYS = list(VAR); WINDOWS = K.WINDOWS
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = K.simulate_kd(d, T.BASE, w, 20) if key == "现行" else simulate_x(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def check(w):  # E0 必须与 B+KD10（去掉 K−D 卖）一致
    import KD10卖出作用检查 as Q
    return sum((Q.Q.simulate_k10(d, Q.VAR["B+KD10不含KD卖"], w, 20) or {}).get("metric") != (simulate_x(d, VAR["E0"], w, 20) or {}).get("metric") for d in T.M.PANEL.values())
def anatomy(code):
    d = T.M.PANEL[code]; gold, dead = d["macds"][(12, 26, 9)]
    r = simulate_x(d, VAR["E0"], ("1900-01-01", "2026-11-10"), 20, retain=True); out = []
    for t in r["trades"]:
        if t["forced_end"]: continue
        xs = t["exit_signal_index"]; xi = t["exit_index"]
        # 破线卖出后 20 个交易日内的最高收盘涨幅（相对卖出价），衡量「卖飞」
        fut = d["cadj"][xi+1:xi+21]; up = (max(fut) / d["cadj"][xi] - 1) if fut else math.nan
        out.append(dict(entry="金叉" if gold[t["entry_signal_index"]] else "站上10日", exit="死叉" if dead[xs] else "破10日", ret=t["net_return"], days=xi - t["entry_index"], up20=up))
    return out
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=init) as p:
        assert sum(p.map(check, [("1900-01-01", "2026-11-10")])) == 0; print("自检通过：E0 = B+KD10")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
        an = [t for ts in p.map(anatomy, GRP) for t in ts]
    print("\n## E0 卖出拆解（诊断，40 只全历史已完成交易）")
    for e in ("金叉", "站上10日"):
        for x in ("死叉", "破10日"):
            s = [t for t in an if t["entry"] == e and t["exit"] == x]
            if s: print(f"  {e}买→{x}卖  {len(s):4d} 笔  胜率 {sum(t['ret']>0 for t in s)/len(s)*100:4.1f}%  平均 {statistics.mean(t['ret'] for t in s)*100:+5.2f}%  持有 {statistics.mean(t['days'] for t in s):4.1f} 天  卖后20日内最高再涨 平均 {statistics.mean(t['up20'] for t in s if math.isfinite(t['up20']))*100:4.1f}%  其中再涨≥10% 的 {sum(t['up20']>=.1 for t in s)} 笔")
    R = {(k, w): o for k, w, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
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
                if k.startswith("X"):
                    for ref in ("现行", "E0"):
                        bo = R[(ref, w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                        S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                        d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                        line += f"\n        较{ref}：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                        if wn == "全历史":
                            pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                            dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                            line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
    print("\n## 合格判定（39 只）")
    full, bear = ("1900-01-01", "2026-11-10"), ("2021-02-19", "2024-01-31")
    cm = lambda k: mean(cal(R[(k, full)][c]) for c in G39 if c in R[(k, full)] and cal(R[(k, full)][c]) is not None)
    bm = lambda k: mean(R[(k, bear)][c]["cagr"] for c in G39 if c in R[(k, bear)] and R[(k, bear)][c]["cagr"] is not None)
    for k in XS[1:]:
        ok = cm(k) > cm("现行") and cm(k) > cm("E0") and bm(k) >= bm("现行")
        print(f"  {k}: 卡玛 {cm(k):.3f}（现行 {cm('现行'):.3f}，E0 {cm('E0'):.3f}）  熊市年化 {bm(k)*100:.2f}%（现行 {bm('现行')*100:.2f}%） → {'合格' if ok else '不合格'}")
