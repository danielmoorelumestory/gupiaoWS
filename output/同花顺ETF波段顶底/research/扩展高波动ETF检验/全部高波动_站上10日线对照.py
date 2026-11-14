"""全部已知高波动 ETF（原主池高波动 30 + 池外已核对 10 = 40 只；另附含 2 只未核对的 42 只）合并汇总：
纯 MACD / 现行（R2 只认金叉）/ A 金叉或站上10日 / B A 加空头破10日卖。规则同 R2站上10日线买对照.py，汇总用平均值。
注：两组之前分别看过，合并属于跑后汇总（诊断）。"""
import math, random, statistics
from multiprocessing import Pool
import R2站上10日线买对照 as T, run_extended as X
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    SEL = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31]
    TEST = ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    UNCHK = ["N"+it["code"] for it in audit if it.get("status") == "unchecked" and it.get("vol", 0) >= .31 and it["code"] in new]
    with Pool(8, initializer=T.init) as p:
        res = p.map(T.run, [(k, (a, z)) for k in T.KEYS for _, a, z in X.WINDOWS])
    R = {(k, w): o for k, w, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    for gname, grp in ((f"全部已知高波动（已核对 {len(SEL)+len(TEST)} 只）", SEL + TEST), (f"含未核对（{len(SEL)+len(TEST)+len(UNCHK)} 只）", SEL + TEST + UNCHK)):
        print(f"\n######## {gname}")
        for wn, a, z in X.WINDOWS:
            if gname.startswith("含") and wn != "全历史": continue
            w = (a, z); base = R[("现行", w)]; ms = [base[c] for c in grp if c in base]
            if len(ms) < 3: continue
            use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
            print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
            for k in T.KEYS:
                o = R[(k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                line = f"  {k:<12} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%  n={len(cs)}"
                if k[0] in "AB":
                    pc = [c for c in cs if c in base and base[c][use] is not None]; rnd = random.Random(20261113)
                    S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                    d = sorted(mean(o[c][use] for c in s) - mean(base[c][use] for c in s) for s in S)
                    dd = sorted(mean(o[c]["mdd"] for c in s) - mean(base[c]["mdd"] for c in s) for s in S)
                    dc = sorted(mean(cal(o[c]) for c in s if cal(o[c]) is not None and cal(base[c]) is not None) - mean(cal(base[c]) for c in s if cal(o[c]) is not None and cal(base[c]) is not None) for s in S) if wn == "全历史" else None
                    line += f"\n               较现行：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  回撤差 95%[{dd[25]*100:+.1f},{dd[974]*100:+.1f}]（正 = 更浅）" + (f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]" if dc else "") + f"  逐只胜 {sum(o[c][use] > base[c][use] for c in pc)}/{len(pc)}"
                print(line)
