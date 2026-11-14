"""择时（R2）牛市入场加「站上 10 日线」对照。事前写定（跑之前）：
- 现行：牛市 且 MACD 金叉当天 → 次日开盘买；卖出 = MACD 死叉当天尾盘卖。
- A 金叉或站上10日线：牛市 且（MACD 金叉 或 收盘由 10 日线下/平 转为上方）→ 次日开盘买；卖出不变（只等死叉）。
  注意：在 MACD 空头时因站上 10 日线买入，要等下一次金叉后的死叉才卖。
- B 同 A 入场；卖出加一条：MACD 处于空头（最近事件为死叉、未再金叉）时收盘跌破 10 日线也当天尾盘卖。
- 10 日线用前复权收盘（含当天）；熊市不开新仓；买入当天触发卖出则次日开盘卖；20bp 往返成本。
- 汇总用平均值；主结论看池外高波动 10 只全历史，原主池高波动 31 只仅参考；差值 95% 区间为 ETF 聚类 bootstrap 1000 次（种子 20261113）；7 段牛熊为诊断。"""
import math, random, statistics
from multiprocessing import Pool
import regime_multi as M, run_extended as X
G = M.G; C = M.C
src = G.src.replace("def simulate_rg(", "def simulate_rgm(", 1)
for old, new in [
    ('    def exit_sig(i):\n', '    mlong=data["mlong"]\n    def exit_sig(i):\n        if config.get("ma10x") and below[i] and not mlong[i]: return True\n'),
    ('return config["bullin"]=="ANY" or gold[i]', 'return config["bullin"]=="ANY" or gold[i] or (config.get("ma10in") and i>0 and above[i] and not above[i-1])')]:
    assert src.count(old) == 1; src = src.replace(old, new)
_ns = dict(vars(G.engine)); exec(src, _ns); simulate_rgm = _ns["simulate_rgm"]
def add_long(d):
    gold, dead = d["macds"][(12, 26, 9)]; s = False; out = []
    for g, x in zip(gold, dead):
        if g: s = True
        elif x: s = False
        out.append(s)
    d["mlong"] = out
def init():
    M.init()
    for d in M.PANEL.values(): add_long(d)
BASE = M.cfg("R2-20", "T1熊不开新仓")
VAR = {"现行": BASE, "A金叉或站上10日": {**BASE, "ma10in": True}, "B同A加空头破10日卖": {**BASE, "ma10in": True, "ma10x": True}}
KEYS = ["MACD", *VAR, "HOLD"]
def run(job):
    key, w = job; out = {}
    for code, d in M.PANEL.items():
        if key == "MACD": r = C.simulate_cs(d, C.grid[C.MACD_KEY], w, 20)
        elif key == "HOLD": r = C.engine.simulate(d, C.HOLD, w, 20)
        else: r = simulate_rgm(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def check(w):
    return sum((G.simulate_rg(d, BASE, w, 20) or {}).get("metric") != (simulate_rgm(d, BASE, w, 20) or {}).get("metric") for d in M.PANEL.values())
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    SEL = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31]
    LOW = ["P"+k for k, d in pool.items() if vol(d["rows"]) < .31]
    TEST = ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=init) as p:
        assert sum(p.map(check, [("1900-01-01", "2026-11-10")])) == 0; print("自检通过：现行 = 原 R2")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in X.WINDOWS])
    R = {(k, w): o for k, w, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    for gname, grp in (("池外高波动10（主结论）", TEST), ("原主池高波动31（参考）", SEL), ("原主池低波动（诊断，跑后追加）", LOW)):
        print(f"\n######## {gname}")
        for wn, a, z in X.WINDOWS:
            w = (a, z); base = R[("现行", w)]; ms = [base[c] for c in grp if c in base]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<12} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%  n={len(cs)}"
                if k[0] in "AB":
                    pc = [c for c in cs if c in base and base[c][use] is not None]; rnd = random.Random(20261113)
                    S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                    d = sorted(mean(o[c][use] for c in s) - mean(base[c][use] for c in s) for s in S)
                    dd = sorted(mean(o[c]["mdd"] for c in s) - mean(base[c]["mdd"] for c in s) for s in S)
                    line += f"\n               较现行：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  回撤差 95%[{dd[25]*100:+.1f},{dd[974]*100:+.1f}]（正 = 回撤更浅）  逐只胜 {sum(o[c][use] > base[c][use] for c in pc)}/{len(pc)}"
                print(line)
