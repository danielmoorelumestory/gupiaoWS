"""诊断：B+KD10 的 K−D 卖出条件（MACD 空头时 K<D 卖）是否起作用：对比去掉该条的版本，并统计因它多卖出的笔数。"""
import math, statistics
from multiprocessing import Pool
import B加KD只滤10日线对照 as Q, run_extended as X
T = Q.T
VAR = {"B+KD10": Q.VAR["B+KD10"], "B+KD10不含KD卖": {k: v for k, v in Q.VAR["B+KD10"].items() if k != "kdx"}}
FULL = ("1900-01-01", "2026-11-10")
def job(code):
    d = T.M.PANEL[code]; out = {}
    for k, cfg in VAR.items():
        r = Q.simulate_k10(d, cfg, FULL, 20, retain=True); out[k] = r
    # 因 K<D 而卖：出场信号日 MACD 空头、收盘不在10日线下、K<D
    kd, below, mlong, dead = d["_kd"], d["below"], d["mlong"], d["macds"][(12, 26, 9)][1]
    n = sum(1 for t in out["B+KD10"]["trades"] if not t["forced_end"] and not dead[t["exit_signal_index"]] and not below[t["exit_signal_index"]] and kd[t["exit_signal_index"]] < 0)
    return code, {k: r["metric"] for k, r in out.items()}, n, len(out["B+KD10"]["trades"])
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=T.init) as p: res = p.map(job, GRP)
    for lab, grp in (("40 只", res), ("去掉588170 39 只", [r for r in res if r[0] != "P588170"])):
        for k in VAR:
            ms = [m[k] for _, m, _, _ in grp if m[k]["cagr"] is not None]
            print(f"{lab} {k:<12} 年化 {statistics.mean(m['cagr'] for m in ms)*100:6.2f}%  回撤 {statistics.mean(m['mdd'] for m in ms)*100:6.1f}%  卡玛 {statistics.mean(m['cagr']/abs(m['mdd']) for m in ms):.3f}  买入次数 {statistics.mean(m['entries'] for m in ms):.1f}")
    same = sum(m["B+KD10"] == m["B+KD10不含KD卖"] for _, m, _, _ in res)
    print(f"\n结果完全相同的标的：{same}/{len(res)}；因 K<D 单独触发的卖出共 {sum(n for _, _, n, _ in res)} 笔（B+KD10 总交易 {sum(t for _, _, _, t in res)} 笔）")
