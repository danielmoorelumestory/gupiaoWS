"""原主池高波动 31 只：纯 MACD / 宽度分段 / R1 / R2 / 买入持有 按牛熊分段（诊断，这 31 只参与过 R1 的选定）。"""
import math, random, statistics
from multiprocessing import Pool
import regime_multi as M
import run_extended as X
KEYS = ["MACD", "B20-60|T1熊不开新仓", "R1-20|T1熊不开新仓", "R2-20|T1熊不开新仓", "HOLD"]
SHORT = {"MACD": "纯MACD", "B20-60|T1熊不开新仓": "宽度分段", "R1-20|T1熊不开新仓": "R1比值", "R2-20|T1熊不开新仓": "R2比值", "HOLD": "买入持有"}
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    SEL = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31]
    with Pool(8, initializer=M.init) as p: res = p.map(M.run, [(k, (a, z)) for k in KEYS for _, a, z in X.WINDOWS])
    R = {(k, w): o for k, w, o in res}
    print(f"原主池高波动 {len(SEL)} 只")
    for wn, a, z in X.WINDOWS:
        base = R[("MACD", (a, z))]; ms = [base[c] for c in SEL if c in base]
        if not ms: print(f"\n## {wn}：无样本"); continue
        use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
        print(f"\n## {wn}（{'年化' if use == 'cagr' else '累计'}中位 / 回撤中位）样本 {len(ms)} 只")
        for k in KEYS:
            o = R[(k, (a, z))]; codes = [c for c in SEL if c in o and o[c][use] is not None]
            v = statistics.median(o[c][use] for c in codes); dd = statistics.median(o[c]["mdd"] for c in codes)
            line = f"  {SHORT[k]:<6} {v*100:7.2f}%  回撤 {dd*100:6.1f}%"
            if k != "MACD":
                pc = [c for c in codes if c in base and base[c][use] is not None]
                if len(pc) >= 3:
                    rnd = random.Random(20261113)
                    d = sorted(statistics.median(o[c][use] for c in s) - statistics.median(base[c][use] for c in s) for s in ([rnd.choice(pc) for _ in pc] for _ in range(1000)))
                    line += f"  较纯MACD 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > base[c][use] for c in pc)}/{len(pc)}"
            print(line)
