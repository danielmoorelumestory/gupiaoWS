"""B+KD10 再加「波段顶底 > 50 不买」。事前写定（跑之前）：
波段顶底 = 最近 13 次收盘变化里 上涨路程 ÷ 总路程 × 100（与详情页 etfBand 相同，用前复权收盘）；
窗口不满或 13 次变化全为 0 时无值 → 不过滤。过滤看「信号当天」（次日开盘买）。
卖出全部同 B+KD10（死叉；MACD 空头时收盘破 10 日线；当天尾盘卖，买入当天触发则次日开盘卖）。
- E0：B+KD10 原版（金叉 或 站上10日线且 K−D≥5.3，牛市才买）。
- BD全：两类买入都要求 波段顶底 ≤ 50。
- BD10：只过滤「站上10日线」那类买入。
- BD金叉：只过滤「金叉」那类买入。
- 现行BD：现行（只认金叉）+ 波段顶底 ≤ 50（参考）。
对照：现行。合格标准（事先定）：39 只（去掉 588170）全历史卡玛比平均高于现行与 E0，且熊 2021-02～2024-01 年化平均不低于现行。
样本全部高波动 40 只；汇总用平均值。另报各类买入信号被过滤的比例与被过滤信号「若买入」的交易结果（诊断）。"""
import math, random, statistics
from multiprocessing import Pool
import B加KD对照 as K, run_extended as X
T = K.T; G = T.G
src = G.src.replace("def simulate_rg(", "def simulate_bd(", 1)
for old, new in [
    ('    def exit_sig(i):\n', '''    mlong=data["mlong"];kd=data["_kd"];band=data["band"]
    def okb(i, which):
        return which not in config["bd"] or band[i] is None or band[i] <= 50
    def exit_sig(i):
        if not mlong[i] and below[i]: return True
'''),
    ('return config["bullin"]=="ANY" or gold[i]', 'return (gold[i] and okb(i,"g")) or (config["ma10in"] and i>0 and above[i] and not above[i-1] and kd[i] >= 5.3 and okb(i,"m"))')]:
    assert src.count(old) == 1; src = src.replace(old, new)
_ns = dict(vars(G.engine)); _ns["math"] = math; exec(src, _ns); simulate_bd = _ns["simulate_bd"]
def etf_band(c):
    out = [None]*len(c)
    for i in range(13, len(c)):
        ch = [c[k]-c[k-1] for k in range(i-12, i+1)]; tot = sum(abs(x) for x in ch)
        out[i] = 100*sum(max(x, 0) for x in ch)/tot if tot > 0 else None
    return out
def init():
    T.init()
    for d in T.M.PANEL.values(): d["band"] = etf_band([float(r["adjusted_close"]) for r in d["rows"]])
VAR = {"现行": {**T.BASE, "ma10in": False, "bd": ""}, "现行BD": {**T.BASE, "ma10in": False, "bd": "g"},
       "E0": {**T.BASE, "ma10in": True, "bd": ""}, "BD全": {**T.BASE, "ma10in": True, "bd": "gm"},
       "BD10": {**T.BASE, "ma10in": True, "bd": "m"}, "BD金叉": {**T.BASE, "ma10in": True, "bd": "g"}}
KEYS = list(VAR); WINDOWS = K.WINDOWS; FULL = ("1900-01-01", "2026-11-10")
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = simulate_bd(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def check(_):  # E0 必须与已验证的 B+KD10 基准一致；现行必须与 simulate_kd 现行一致
    import KD10破线卖改造对照 as Z
    bad = 0
    for d in T.M.PANEL.values():
        if "atr" not in d: Z.add(d)
        bad += (Z.simulate_x(d, Z.VAR["E0"], FULL, 20) or {}).get("metric") != (simulate_bd(d, VAR["E0"], FULL, 20) or {}).get("metric")
        bad += (K.simulate_kd(d, T.BASE, FULL, 20) or {}).get("metric") != (simulate_bd(d, VAR["现行"], FULL, 20) or {}).get("metric")
    return bad
def anatomy(code):  # E0 的已完成交易按信号日波段顶底分组（诊断）
    d = T.M.PANEL[code]; gold, _ = d["macds"][(12, 26, 9)]
    r = simulate_bd(d, VAR["E0"], FULL, 20, retain=True)
    return [dict(kind="金叉" if gold[t["entry_signal_index"]] else "站上10日", band=d["band"][t["entry_signal_index"]], ret=t["net_return"]) for t in r["trades"] if not t["forced_end"]]
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=init) as p:
        assert p.map(check, [0])[0] == 0; print("自检通过：E0 = B+KD10，现行 = 现行")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
        an = [t for ts in p.map(anatomy, GRP) for t in ts]
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    print("\n## E0 已完成交易按信号日波段顶底分组（诊断，40 只全历史）")
    for k in ("金叉", "站上10日"):
        for lab, f in (("≤50", lambda b: b is not None and b <= 50), (">50", lambda b: b is not None and b > 50), ("无值", lambda b: b is None)):
            s = [t for t in an if t["kind"] == k and f(t["band"])]
            if s: print(f"  {k}买 波段顶底{lab:<3} {len(s):4d} 笔（占该类 {len(s)/sum(t['kind']==k for t in an)*100:4.1f}%）  胜率 {sum(t['ret']>0 for t in s)/len(s)*100:4.1f}%  平均 {mean(t['ret'] for t in s)*100:+5.2f}%  合计 {sum(t['ret'] for t in s)*100:+7.1f}%")
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
                line = f"  {k:<6} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%"
                if k.startswith("BD") or k == "现行BD":
                    for ref in (("现行",) if k == "现行BD" else ("现行", "E0")):
                        bo = R[(ref, w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                        S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                        d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                        line += f"\n         较{ref}：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                        if wn == "全历史":
                            pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                            dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                            line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
    print("\n## 合格判定（39 只）")
    bear = ("2021-02-19", "2024-01-31")
    cm = lambda k: mean(cal(R[(k, FULL)][c]) for c in G39 if c in R[(k, FULL)] and cal(R[(k, FULL)][c]) is not None)
    bm = lambda k: mean(R[(k, bear)][c]["cagr"] for c in G39 if c in R[(k, bear)] and R[(k, bear)][c]["cagr"] is not None)
    for k in ("BD全", "BD10", "BD金叉"):
        ok = cm(k) > cm("现行") and cm(k) > cm("E0") and bm(k) >= bm("现行")
        print(f"  {k}: 卡玛 {cm(k):.3f}（现行 {cm('现行'):.3f}，E0 {cm('E0'):.3f}）  熊市年化 {bm(k)*100:.2f}%（现行 {bm('现行')*100:.2f}%） → {'合格' if ok else '不合格'}")
    print(f"  现行BD（参考）: 卡玛 {cm('现行BD'):.3f}  熊市年化 {bm('现行BD')*100:.2f}%")
