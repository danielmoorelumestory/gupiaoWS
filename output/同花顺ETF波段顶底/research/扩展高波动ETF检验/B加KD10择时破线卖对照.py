"""B+KD10，破10日线卖改为看择时：择时牛市不因破线卖，择时熊市破线就卖。事前写定（跑之前）：
- E0：B+KD10 原版（死叉；或 MACD 空头时收盘破 10 日线 → 当天尾盘卖）。
- Y1：B+KD10 买入不变；卖出 = 死叉 或（当天择时熊市 且 收盘破 10 日线，不论 MACD 多空）→ 当天尾盘卖。
- Y2：Y1 再保留原版的「MACD 空头时破线卖」（牛市里站上10日买进、假突破的那类仍会卖）。
买入当天触发卖出则次日开盘卖（T+1）。择时熊市不开新仓。
合格标准（事先定）：39 只（去掉 588170）全历史卡玛比平均高于现行与 E0，且熊 2021-02～2024-01 年化平均不低于现行。
样本全部高波动 40 只；汇总用平均值。另做 Y1 卖出拆解（诊断）：多头时破线卖出的笔数、收益、卖后 20 日内最高再涨。"""
import math, random, statistics
from multiprocessing import Pool
import B加KD对照 as K, run_extended as X
T = K.T; G = T.G
src = G.src.replace("def simulate_rg(", "def simulate_y(", 1)
for old, new in [
    ('    def exit_sig(i):\n', '''    mlong=data["mlong"];kd=data["_kd"]
    def exit_sig(i):
        if below[i] and ((config["anyx"] and reg[i] is False) or (config["keep"] and not mlong[i])): return True
'''),
    ('return config["bullin"]=="ANY" or gold[i]', 'return gold[i] or (config["ma10in"] and i>0 and above[i] and not above[i-1] and kd[i] >= 5.3)')]:
    assert src.count(old) == 1; src = src.replace(old, new)
_ns = dict(vars(G.engine)); _ns["math"] = math; exec(src, _ns); simulate_y = _ns["simulate_y"]
VAR = {"现行": {**T.BASE, "ma10in": False, "anyx": False, "nox": True}, "E0": {**T.BASE, "ma10in": True, "anyx": False, "keep": True},
       "Y1": {**T.BASE, "ma10in": True, "anyx": True, "keep": False}, "Y2": {**T.BASE, "ma10in": True, "anyx": True, "keep": True}}
KEYS = list(VAR); WINDOWS = K.WINDOWS; FULL = ("1900-01-01", "2026-11-10")
def sim(d, k, w, **kw):
    return K.simulate_kd(d, T.BASE, w, 20, **kw) if k == "现行" else simulate_y(d, VAR[k], w, 20, **kw)
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = sim(d, key, w)
        if r: out[code] = r["metric"]
    return key, w, out
def check(_):
    import KD10破线卖改造对照 as Z
    bad = 0
    for d in T.M.PANEL.values():
        Z.add(d); bad += (Z.simulate_x(d, Z.VAR["E0"], FULL, 20) or {}).get("metric") != (simulate_y(d, VAR["E0"], FULL, 20) or {}).get("metric")
    return bad
AN = "Y1"
def anatomy(code):
    d = T.M.PANEL[code]; gold, dead = d["macds"][(12, 26, 9)]; c = [float(r["adjusted_close"]) for r in d["rows"]]
    r = simulate_y(d, VAR[AN], FULL, 20, retain=True); out = []
    for t in r["trades"]:
        if t["forced_end"]: continue
        xs = t["exit_signal_index"]; xi = t["exit_index"]; fut = c[xi+1:xi+21]
        ex = "死叉" if dead[xs] else ("破线·熊市" if d["reg"]["R2-20"][xs] is False else "破线·牛市MACD空头")
        out.append(dict(entry="金叉" if gold[t["entry_signal_index"]] else "站上10日", exit=ex, ret=t["net_return"], days=xi-t["entry_index"], up20=(max(fut)/c[xi]-1) if fut else math.nan))
    return out
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=T.init) as p:
        assert p.map(check, [0])[0] == 0; print("自检通过：E0 = B+KD10")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
        an = [t for ts in p.map(anatomy, GRP) for t in ts]
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    print("\n## Y1 卖出拆解（熊市 = 信号日择时为熊）（诊断，40 只全历史已完成交易）")
    for e in ("金叉", "站上10日"):
        for x in ("死叉", "破线·熊市", "破线·牛市MACD空头"):
            s = [t for t in an if t["entry"] == e and t["exit"] == x]
            if s: print(f"  {e}买→{x}卖  {len(s):4d} 笔  胜率 {sum(t['ret']>0 for t in s)/len(s)*100:4.1f}%  平均 {mean(t['ret'] for t in s)*100:+5.2f}%  持有 {mean(t['days'] for t in s):4.1f} 天  卖后20日内最高再涨 平均 {mean(t['up20'] for t in s if math.isfinite(t['up20']))*100:4.1f}%  再涨≥10% {sum(t['up20']>=.1 for t in s)} 笔")
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
                if k.startswith("Y"):
                    for ref in ("现行", "E0"):
                        bo = R[(ref, w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                        S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                        d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                        line += f"\n       较{ref}：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                        if wn == "全历史":
                            pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                            dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                            line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
    print("\n## 合格判定（39 只）")
    bear = ("2021-02-19", "2024-01-31")
    cm = lambda k: mean(cal(R[(k, FULL)][c]) for c in G39 if c in R[(k, FULL)] and cal(R[(k, FULL)][c]) is not None)
    bm = lambda k: mean(R[(k, bear)][c]["cagr"] for c in G39 if c in R[(k, bear)] and R[(k, bear)][c]["cagr"] is not None)
    for k in ("Y1", "Y2"):
        ok = cm(k) > cm("现行") and cm(k) > cm("E0") and bm(k) >= bm("现行")
        print(f"  {k}: 卡玛 {cm(k):.3f}（现行 {cm('现行'):.3f}，E0 {cm('E0'):.3f}）  熊市年化 {bm(k)*100:.2f}%（现行 {bm('现行')*100:.2f}%） → {'合格' if ok else '不合格'}")
