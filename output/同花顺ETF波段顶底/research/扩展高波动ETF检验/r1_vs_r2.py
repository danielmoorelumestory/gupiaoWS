"""R1 与 R2 逐只配对比较（诊断）。"""
import math, random, statistics
from multiprocessing import Pool
import regime_multi as M, run_extended as X
K1, K2 = "R1-20|T1熊不开新仓", "R2-20|T1熊不开新仓"
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    SEL = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31]
    TEST = ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    names = {**{"P"+k: d["item"]["name"] for k, d in pool.items()}, **{"N"+it["code"]: it["name"] for it in audit}}
    wins = [("全历史", "1900-01-01", "2026-11-10"), ("2019-02 起（两者都有信号）", "2019-02-01", "2026-11-10")]
    with Pool(8, initializer=M.init) as p: res = p.map(M.run, [(k, (a, z)) for k in (K1, K2, "MACD") for _, a, z in wins])
    R = {(k, w): o for k, w, o in res}
    for gname, grp in (("原主池高波动31（选定集）", SEL), ("池外高波动10（检验集）", TEST)):
        for wn, a, z in wins:
            o1, o2 = R[(K1, (a, z))], R[(K2, (a, z))]
            cs = [c for c in grp if c in o1 and c in o2 and o1[c]["cagr"] is not None and o2[c]["cagr"] is not None]
            d = [o2[c]["cagr"] - o1[c]["cagr"] for c in cs]
            rnd = random.Random(20261113)
            bs = sorted(statistics.median(o2[c]["cagr"] for c in s) - statistics.median(o1[c]["cagr"] for c in s) for s in ([rnd.choice(cs) for _ in cs] for _ in range(1000)))
            print(f"\n{gname} · {wn}：R1 年化中位 {statistics.median(o1[c]['cagr'] for c in cs)*100:.2f}%  R2 {statistics.median(o2[c]['cagr'] for c in cs)*100:.2f}%  "
                  f"R2−R1 中位差 95%[{bs[25]*100:+.1f},{bs[974]*100:+.1f}]  R2 胜 {sum(x > 0 for x in d)}/{len(d)}  回撤中位 R1 {statistics.median(o1[c]['mdd'] for c in cs)*100:.1f}% R2 {statistics.median(o2[c]['mdd'] for c in cs)*100:.1f}%")
            if wn == "全历史":
                for c in sorted(cs, key=lambda c: -(o2[c]["cagr"] - o1[c]["cagr"]))[:3]:
                    print(f"    差最大：{names[c][:10]} 起 {o1[c]['first']}  R1 {o1[c]['cagr']*100:.1f}% R2 {o2[c]['cagr']*100:.1f}%")
