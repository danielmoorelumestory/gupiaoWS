"""B + K−D，但 K−D 只作用于 10 日线那部分。事前写定（跑之前）：
- B+KD10：买入 = 牛市 且（MACD 金叉【不加过滤】 或「当天收盘站上10日线 且 K−D ≥ 5.3」）→ 次日开盘买；
  卖出 = 死叉，或 MACD 空头时（收盘跌破10日线 或 K < D），当天尾盘卖。
- 对照：现行、B、B+KD买卖（K−D 同时过滤金叉买入）、C。其余规则同前；样本全部已知高波动 40 只；汇总用平均值；
  另报去掉 588170 的 39 只（含卡玛比 bootstrap 区间）与 2025 年起。"""
import math, random, statistics
from multiprocessing import Pool
import B加KD对照 as K, run_extended as X
T = K.T; G = T.G; C = T.C
src = G.src.replace("def simulate_rg(", "def simulate_k10(", 1)
for old, new in [
    ('    def exit_sig(i):\n', '    mlong=data["mlong"];kd=data["_kd"]\n    def exit_sig(i):\n        if config.get("ma10x") and not mlong[i] and (below[i] or (config.get("kdx") and kd[i] < 0)): return True\n'),
    ('return config["bullin"]=="ANY" or gold[i]', 'return config["bullin"]=="ANY" or gold[i] or (config.get("ma10in") and i>0 and above[i] and not above[i-1] and kd[i] >= 5.3)')]:
    assert src.count(old) == 1; src = src.replace(old, new)
_ns = dict(vars(G.engine)); exec(src, _ns); simulate_k10 = _ns["simulate_k10"]
NEWK = "B+KD10"
VAR = {**K.VAR, NEWK: {**T.BASE, "ma10in": True, "ma10x": True, "kdx": True}}
KEYS = ["现行", "B", "B+KD买卖", NEWK, "C确认后买"]
WINDOWS = K.WINDOWS
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        r = simulate_k10(d, VAR[key], w, 20) if key == NEWK else K.simulate_kd(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=T.init) as p: res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
    R = {(k, w): o for k, w, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    for gname, grp in (("全部高波动 40 只", GRP), ("去掉 588170 的 39 只", [c for c in GRP if c != "P588170"])):
        print(f"\n######## {gname}")
        for wn, a, z in WINDOWS:
            if gname.startswith("去掉") and wn not in ("全历史", "2025 年起"): continue
            w = (a, z); base = R[("现行", w)]; ms = [base[c] for c in grp if c in base]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<8} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%  n={len(cs)}"
                if k == NEWK:
                    for ref in ("现行", "B"):
                        bo = R[(ref, w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                        S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                        d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                        dd = sorted(mean(o[c]["mdd"] for c in s) - mean(bo[c]["mdd"] for c in s) for s in S)
                        line += f"\n             较{ref}：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  回撤差 95%[{dd[25]*100:+.1f},{dd[974]*100:+.1f}]（正 = 更浅）  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                        if wn == "全历史":
                            pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                            dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                            line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                print(line)
