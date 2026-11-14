"""择时（R2）买入时点对照。事前写定（跑之前）：
- 次开买（现行）：牛市 且 MACD 金叉当天 → 次日开盘买。
- 收盘买：同样条件 → 当天收盘价买（假设尾盘已能估出当天金叉、当天择时为牛，按收盘价成交；不计估算误差和尾盘滑点）。
- 其余相同：熊市不开新仓；死叉当天尾盘卖（收盘买的次日起即可尾盘卖，符合 T+1；次开买的买入当天死叉则次日开盘卖）；20bp 往返成本。
- 参考：纯 MACD 次开买 / 纯 MACD 收盘买（不择时）。
- 汇总用平均值；主结论看池外高波动 10 只全历史，原主池高波动 31 只仅参考；差值 95% 区间为 ETF 聚类 bootstrap 1000 次（种子 20261113）；7 段牛熊为诊断。"""
import math, random, statistics
from multiprocessing import Pool
import regime_multi as M, run_extended as X
G = M.G; C = M.C
src = G.src.replace("def simulate_rg(", "def simulate_rgc(", 1)
old = "        value=cash+reserve+q*cl[i]\n"
assert src.count(old) == 1
src = src.replace(old, """        if config.get("closebuy") and not q and not sold_at_close and i!=end and entry_sig(i):
            q=cash/(cl[i]*(1+cost/20000));fee=q*cl[i]*cost/20000
            active={"entry_index":i,"entry_date":dates[i],"entry_signal_index":i,
                    "entry_signal_date":dates[i],"entry_price":cl[i],"entry_cash":cash,
                    "entry_reserve":reserve,"entry_shares":q,"entry_fee":fee}
            fees+=fee;cash=0.0;armed=None;seen_high=False;entries+=1
""" + old)
_ns = dict(vars(G.engine)); exec(src, _ns); simulate_rgc = _ns["simulate_rgc"]
BASE = M.cfg("R2-20", "T1熊不开新仓")
ALWAYS = {**BASE, "N": "R2-20", "bullin": "GOLD", "bearin": "GOLD", "bearx": "X2"}  # 熊市也照常金叉买 = 不择时
VAR = {"R2·次开买": BASE, "R2·收盘买": {**BASE, "closebuy": True}, "MACD·次开买": ALWAYS, "MACD·收盘买": {**ALWAYS, "closebuy": True}}
KEYS = [*VAR, "HOLD"]
def run(job):
    key, w = job; out = {}
    for code, d in M.PANEL.items():
        r = C.engine.simulate(d, C.HOLD, w, 20) if key == "HOLD" else simulate_rgc(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def check(w):  # 次开买 = 原 R2；不择时次开买 = 纯 MACD 尾盘卖
    bad = 0
    for d in M.PANEL.values():
        bad += (G.simulate_rg(d, BASE, w, 20) or {}).get("metric") != (simulate_rgc(d, BASE, w, 20) or {}).get("metric")
        a = (C.simulate_cs(d, C.grid[C.MACD_KEY], w, 20) or {}).get("metric"); b = (simulate_rgc(d, ALWAYS, w, 20) or {}).get("metric")
        bad += (a is None) != (b is None) or (a is not None and abs(a["final_nav"] - b["final_nav"]) > 1e-9)
    return bad
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    SEL = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31]
    TEST = ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=M.init) as p:
        assert sum(p.map(check, [("1900-01-01", "2026-11-10")])) == 0; print("自检通过：次开买 = 原 R2；不择时次开买 = 纯 MACD 尾盘卖")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in X.WINDOWS])
    R = {(k, w): o for k, w, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    for gname, grp in (("池外高波动10（主结论）", TEST), ("原主池高波动31（参考）", SEL)):
        print(f"\n######## {gname}")
        for wn, a, z in X.WINDOWS:
            w = (a, z); ms = [R[("R2·次开买", w)][c] for c in grp if c in R[("R2·次开买", w)]]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<9} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  n={len(cs)}"
                if k.endswith("收盘买"):
                    base = R[(k.replace("收盘买", "次开买"), w)]
                    pc = [c for c in cs if c in base and base[c][use] is not None]; rnd = random.Random(20261113)
                    S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                    d = sorted(mean(o[c][use] for c in s) - mean(base[c][use] for c in s) for s in S)
                    dd = sorted(mean(o[c]["mdd"] for c in s) - mean(base[c]["mdd"] for c in s) for s in S)
                    line += f"\n            较次开买：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  回撤差 95%[{dd[25]*100:+.1f},{dd[974]*100:+.1f}]（正 = 回撤更浅）  逐只胜 {sum(o[c][use] > base[c][use] for c in pc)}/{len(pc)}"
                print(line)
