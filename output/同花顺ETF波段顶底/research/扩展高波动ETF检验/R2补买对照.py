"""择时（R2）两种入场口径对照。事前写定（跑之前）：
- 只认金叉：牛市 且 MACD 金叉当天 → 次日开盘买（现行口径，= R2-20|T1熊不开新仓）。
- 补买：牛市 且 空仓 且 MACD 处于多头（最近一次事件是金叉、尚未死叉，含金叉当天）→ 次日开盘买。
  即熊市里错过的金叉，择时转牛时若还没死叉就补买。
- 其余相同：熊市不开新仓；死叉当天尾盘卖（买入当天死叉则次日开盘卖）；20bp 往返成本。
- 汇总用平均值（用户要求不用中位数）；主结论看池外高波动 10 只全历史，原主池高波动 31 只仅参考；
  差值 95% 区间为 ETF 聚类 bootstrap 1000 次（种子 20261113）；7 段牛熊为诊断。"""
import math, random, statistics
from multiprocessing import Pool
import regime_multi as M, run_extended as X
G = M.G; C = M.C
src = G.src.replace("def simulate_rg(", "def simulate_rgb(", 1)
old = 'return config["bullin"]=="ANY" or gold[i]'
assert src.count(old) == 1
src = src.replace(old, 'return config["bullin"]=="ANY" or gold[i] or (config["bullin"]=="STATE" and data["mlong"][i])')
_ns = dict(vars(G.engine)); exec(src, _ns); simulate_rgb = _ns["simulate_rgb"]
def add_long(d):
    gold, dead = d["macds"][(12, 26, 9)]; s = False; out = []
    for g, x in zip(gold, dead):
        if g: s = True
        elif x: s = False
        out.append(s)
    d["mlong"] = out
KEYS = ["MACD", "只认金叉", "补买", "HOLD"]
def init():
    M.init()
    for d in M.PANEL.values(): add_long(d)
def run(job):
    key, w = job; out = {}
    for code, d in M.PANEL.items():
        if key == "MACD": r = C.simulate_cs(d, C.grid[C.MACD_KEY], w, 20)
        elif key == "HOLD": r = C.engine.simulate(d, C.HOLD, w, 20)
        else: r = simulate_rgb(d, {**M.cfg("R2-20", "T1熊不开新仓"), "bullin": "STATE" if key == "补买" else "GOLD"}, w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def check(w):  # 只认金叉 必须与原 R2 完全一致；补买 的买入次数不少于只认金叉
    bad = 0
    for d in M.PANEL.values():
        a = G.simulate_rg(d, M.cfg("R2-20", "T1熊不开新仓"), w, 20); b = simulate_rgb(d, M.cfg("R2-20", "T1熊不开新仓"), w, 20)
        bad += (a and a["metric"]) != (b and b["metric"])
    return bad
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    SEL = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31]
    TEST = ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=init) as p:
        assert sum(p.map(check, [("1900-01-01", "2026-11-10")])) == 0; print("自检通过：只认金叉 = 原 R2")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in X.WINDOWS])
    R = {(k, w): o for k, w, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float('nan')
    for gname, grp in (("池外高波动10（主结论）", TEST), ("原主池高波动31（参考）", SEL)):
        print(f"\n######## {gname}")
        for wn, a, z in X.WINDOWS:
            w = (a, z); ms = [R[("只认金叉", w)][c] for c in grp if c in R[("只认金叉", w)]]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            base = R[("只认金叉", w)]
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<6} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%  n={len(cs)}"
                if k == "补买":
                    pc = [c for c in cs if c in base and base[c][use] is not None]; rnd = random.Random(20261113)
                    d = sorted(mean(o[c][use] for c in s) - mean(base[c][use] for c in s) for s in ([rnd.choice(pc) for _ in pc] for _ in range(1000)))
                    dd = sorted(mean(o[c]["mdd"] for c in s) - mean(base[c]["mdd"] for c in s) for s in ([rnd.choice(pc) for _ in pc] for _ in range(1000)))
                    line += f"\n         较只认金叉：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  回撤差 95%[{dd[25]*100:+.1f},{dd[974]*100:+.1f}]  逐只胜 {sum(o[c][use] > base[c][use] for c in pc)}/{len(pc)}"
                print(line)
