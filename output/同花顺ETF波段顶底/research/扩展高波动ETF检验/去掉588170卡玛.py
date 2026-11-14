"""诊断：去掉 588170（数据不足两年、单只拉高平均）后比较 现行 / B / B+KD买 / C 的年化、回撤、卡玛比。"""
import math, statistics, random
from multiprocessing import Pool
import B加KD对照 as K, run_extended as X
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    w = ("1900-01-01", "2026-11-10")
    with Pool(8, initializer=K.T.init) as p: res = p.map(K.run, [(k, w) for k in ("现行", "B", "B+KD买", "C确认后买")])
    R = {k: o for k, _, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"])
    ex = [c for c in GRP if c != "P588170" and c in R["现行"] and R["现行"][c]["cagr"] is not None]
    rnd = random.Random(20261113); S = [[rnd.choice(ex) for _ in ex] for _ in range(1000)]
    for k in R:
        o = R[k]; line = f"去掉588170（{len(ex)}只） {k:<8} 年化 {statistics.mean(o[c]['cagr'] for c in ex)*100:6.2f}%  回撤 {statistics.mean(o[c]['mdd'] for c in ex)*100:6.1f}%  卡玛 {statistics.mean(cal(o[c]) for c in ex):.3f}"
        if k != "现行":
            d = sorted(statistics.mean(cal(o[c]) for c in s) - statistics.mean(cal(R['现行'][c]) for c in s) for s in S)
            line += f"  卡玛较现行 95%[{d[25]:+.3f},{d[974]:+.3f}]"
        print(line)
