"""B 的「站上10日线」买入改用三种当天强度指标过滤（各自单独替代 K−D）。事前写定（跑之前）：
- 买入 = 牛市 且（MACD 金叉【不过滤】 或「当天收盘站上10日线 且 强度过滤通过」）→ 次日开盘买；
  卖出 = 死叉，或 MACD 空头时收盘跌破10日线，当天尾盘卖。熊市不开新仓；20bp 往返成本。
- 三种强度过滤（均用前复权价，当天收盘可知）：
  CP 收盘位置：(收盘−最低)/(最高−最低) ≥ 0.6（最高=最低时视为不通过）
  RA 当日涨幅/ATR：(收盘−前收)/ATR14(Wilder) ≥ 0.5
  SL 10日线斜率：今天 10 日线 > 昨天 10 日线
- 对照：现行、B、B+KD10（K−D≥5.3 只过滤10日线买入，无 K−D 卖出）。
- 合格标准（事先定）：在去掉 588170 的 39 只上，全历史卡玛比平均 同时高于 现行 和 B+KD10，
  且「熊 2021-02～2024-01」年化平均 不低于 现行。另报全部 40 只、各段与 2025 年起。汇总用平均值。"""
import math, random, statistics
from multiprocessing import Pool
import B加KD对照 as K, run_extended as X
T = K.T; G = T.G
F = X.F
src = G.src.replace("def simulate_rg(", "def simulate_s10(", 1)
for old, new in [
    ('    def exit_sig(i):\n', '    mlong=data["mlong"];strong=data["strong"][config["sf"]]\n    def exit_sig(i):\n        if config.get("ma10x") and not mlong[i] and below[i]: return True\n'),
    ('return config["bullin"]=="ANY" or gold[i]', 'return config["bullin"]=="ANY" or gold[i] or (i>0 and above[i] and not above[i-1] and strong[i])')]:
    assert src.count(old) == 1; src = src.replace(old, new)
_ns = dict(vars(G.engine)); exec(src, _ns); simulate_s10 = _ns["simulate_s10"]
def add_strength(d):
    rows = d["rows"]; c = [float(r["adjusted_close"]) for r in rows]; f = [c[i]/float(r["close"]) for i, r in enumerate(rows)]
    hi = [float(r["high"])*f[i] for i, r in enumerate(rows)]; lo = [float(r["low"])*f[i] for i, r in enumerate(rows)]
    tr = [math.nan] + [max(hi[i]-lo[i], abs(hi[i]-c[i-1]), abs(lo[i]-c[i-1])) for i in range(1, len(c))]
    atr = F._wilder(tr); n = len(c)
    ma = [sum(c[i-9:i+1])/10 if i >= 9 else math.nan for i in range(n)]
    d["strong"] = {
        "NONE": [True]*n,
        "KD": [x >= 5.3 for x in d["_kd"]],
        "CP": [hi[i] > lo[i] and (c[i]-lo[i])/(hi[i]-lo[i]) >= .6 for i in range(n)],
        "RA": [i > 0 and math.isfinite(atr[i]) and atr[i] > 0 and (c[i]-c[i-1])/atr[i] >= .5 for i in range(n)],
        "SL": [i >= 10 and ma[i] > ma[i-1] for i in range(n)]}
def init():
    T.init()
    for d in T.M.PANEL.values(): add_strength(d)
VAR = {"现行": None, **{k: {**T.BASE, "ma10x": True, "sf": f} for k, f in (("B", "NONE"), ("B+KD10", "KD"), ("B+CP10", "CP"), ("B+RA10", "RA"), ("B+SL10", "SL"))}}
KEYS = list(VAR); WINDOWS = K.WINDOWS
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = K.simulate_kd(d, T.BASE, w, 20) if key == "现行" else simulate_s10(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def check(w):  # B 与之前一致
    return sum((K.simulate_kd(d, K.VAR["B"], w, 20) or {}).get("metric") != (simulate_s10(d, VAR["B"], w, 20) or {}).get("metric") for d in T.M.PANEL.values())
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=init) as p:
        assert sum(p.map(check, [("1900-01-01", "2026-11-10")])) == 0; print("自检通过：B 与之前一致")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
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
                line = f"  {k:<8} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  n={len(cs)}"
                if k in ("B+CP10", "B+RA10", "B+SL10"):
                    for ref in ("现行", "B+KD10"):
                        bo = R[(ref, w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                        S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                        d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                        line += f"\n             较{ref}：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                        if wn == "全历史":
                            pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                            dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                            line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
    print("\n## 合格判定（事先定的标准，39 只）")
    full, bear = ("1900-01-01", "2026-11-10"), ("2021-02-19", "2024-01-31")
    cm = lambda k: mean(cal(R[(k, full)][c]) for c in G39 if c in R[(k, full)] and cal(R[(k, full)][c]) is not None)
    bm = lambda k: mean(R[(k, bear)][c]["cagr"] for c in G39 if c in R[(k, bear)] and R[(k, bear)][c]["cagr"] is not None)
    for k in ("B+CP10", "B+RA10", "B+SL10"):
        ok = cm(k) > cm("现行") and cm(k) > cm("B+KD10") and bm(k) >= bm("现行")
        print(f"  {k}: 卡玛 {cm(k):.3f}（现行 {cm('现行'):.3f}，KD10 {cm('B+KD10'):.3f}）  熊市年化 {bm(k)*100:.2f}%（现行 {bm('现行')*100:.2f}%） → {'合格' if ok else '不合格'}")
