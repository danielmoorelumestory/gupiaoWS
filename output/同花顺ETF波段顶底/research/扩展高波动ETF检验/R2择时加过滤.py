"""R2 择时（创业板159915÷红利510880 高于20日线为牛，熊不开新仓、死叉尾盘卖）上再加 A20 或 K−D 入场过滤。
事前写定（跑之前）：
- 过滤只作用于牛市金叉当天：牛市 且 金叉 且 过滤通过 才买；熊市照旧不开新仓；卖出同 R2（死叉尾盘卖，T+1 次日开盘）。
- A20、K−D 定义与阈值同 filter_common.py（K−D≥5.3；A20 用原主池滚动 3 年 20% 分位）。
- 主结论看池外高波动 10 只全历史：卡玛中位、年化中位、与 R2 的年化中位差 95% 区间（ETF 聚类 bootstrap 1000 次，种子 20261113）。
- 原主池高波动 31 只参与过选 R2，仅作参考；7 段牛熊为诊断。"""
import math, random, statistics
from multiprocessing import Pool
import regime_multi as M, run_extended as X
G = M.G; C = M.C
src = G.src.replace("def simulate_rg(", "def simulate_rgf(", 1)
old = 'return config["bullin"]=="ANY" or gold[i]'
assert src.count(old) == 1
src = src.replace(old, 'return (config["bullin"]=="ANY" or gold[i]) and data["flt"][config["flt"]][i]')
_ns = dict(vars(G.engine)); exec(src, _ns); simulate_rgf = _ns["simulate_rgf"]
KEYS = ["MACD", "MACD+A20", "MACD+KD", "R2", "R2+A20", "R2+KD", "HOLD"]
def run(job):
    key, w = job; out = {}
    for code, d in M.PANEL.items():
        if key == "MACD": r = C.simulate_cs(d, C.grid[C.MACD_KEY], w, 20)
        elif key == "HOLD": r = C.engine.simulate(d, C.HOLD, w, 20)
        elif key.startswith("MACD+"):
            r = X.F.simulate_f(d, {**C.blank, "entry": "MACDF", "exit": "X2", "macd": [12,26,9], "flt": key[5:]}, w, 20)
        else:
            f = key[3:] if "+" in key else "NONE"
            r = simulate_rgf(d, {**M.cfg("R2-20", "T1熊不开新仓"), "flt": f}, w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def check(job):  # R2 不加过滤时必须与原 simulate_rg 完全一致
    w = job; bad = 0
    for code, d in M.PANEL.items():
        a = G.simulate_rg(d, M.cfg("R2-20", "T1熊不开新仓"), w, 20); b = simulate_rgf(d, {**M.cfg("R2-20", "T1熊不开新仓"), "flt": "NONE"}, w, 20)
        if (a and a["metric"]) != (b and b["metric"]): bad += 1
    return bad
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    SEL = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31]
    TEST = ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=M.init) as p:
        assert sum(p.map(check, [("1900-01-01", "2026-11-10")])) == 0; print("自检通过：R2 无过滤 = 原 R2")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in X.WINDOWS])
    R = {(k, w): o for k, w, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    for gname, grp in (("池外高波动10（主结论）", TEST), ("原主池高波动31（参考）", SEL)):
        print(f"\n######## {gname}")
        for wn, a, z in X.WINDOWS:
            w = (a, z); ms = [R[("R2", w)][c] for c in grp if c in R[("R2", w)]]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}中位）")
            base = R[("R2", w)]
            for k in KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                v = statistics.median(o[c][use] for c in cs); dd = statistics.median(o[c]["mdd"] for c in cs)
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<9} {v*100:7.2f}%  回撤 {dd*100:6.1f}%" + (f"  卡玛 {statistics.median(cl):.3f}" if wn == "全历史" else "") + f"  n={len(cs)}"
                if k in ("R2+A20", "R2+KD"):
                    pc = [c for c in cs if c in base and base[c][use] is not None]; rnd = random.Random(20261113)
                    d = sorted(statistics.median(o[c][use] for c in s) - statistics.median(base[c][use] for c in s) for s in ([rnd.choice(pc) for _ in pc] for _ in range(1000)))
                    line += f"  较R2 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > base[c][use] for c in pc)}/{len(pc)}"
                print(line)
