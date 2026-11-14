"""预热期 120 根 → 30 根。事前写定（跑之前）：
策略：Y1（详情页现行：B+KD10 买；死叉 或 择时熊市破10日线 卖）与 现行（只认金叉）各跑预热 120、30 两种。
预热只改「前多少根不交易」；指标仍从上市第一根算起（与详情页、同花顺一致）。窗口最少行数仍 120。
主看全历史（窗口起点随预热不同，年化/卡玛的期间不同，仅作参考）；
关键诊断：Y1@30 中「信号出现在第 30～119 根」的上市初期交易，与其余交易比较胜率与平均每笔收益。
可接受标准（事先定）：40 只上市初期交易平均每笔收益 ≥ 0，且不低于其余交易平均每笔收益的一半；
39 只（去掉 588170）全历史卡玛比平均 Y1@30 不低于 Y1@120 超过 0.03。样本全部高波动 40 只；汇总用平均值。"""
import math, statistics
from multiprocessing import Pool
import importlib.util, run_extended as X
spec = importlib.util.spec_from_file_location("Y", "B加KD10择时破线卖对照.py"); Y = importlib.util.module_from_spec(spec); spec.loader.exec_module(Y)
T = Y.T; K = Y.K; P = T.G.engine.P
FULL = ("1900-01-01", "2026-11-10"); WIN = [("全历史", *FULL), ("2025 年起", "2025-01-02", "2026-11-10")]
def init(): T.init()
def run(job):
    key, wu, w = job; P["warmup_excluded_rows"] = wu; out = {}
    for code, d in T.M.PANEL.items():
        r = Y.sim(d, key, w)
        if r: out[code] = r["metric"]
    return key, wu, w, out
def early(code):
    P["warmup_excluded_rows"] = 30; d = T.M.PANEL[code]
    r = Y.simulate_y(d, Y.VAR["Y1"], FULL, 20, retain=True)
    return [dict(code=code, early=t["entry_signal_index"] < 120, ret=t["net_return"], date=t["entry_date"] if "entry_date" in t else d["dates"][t["entry_index"]]) for t in r["trades"] if not t["forced_end"]]
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=init) as p:
        res = p.map(run, [(k, wu, (a, z)) for k in ("现行", "Y1") for wu in (120, 30) for _, a, z in WIN])
        tr = [t for ts in p.map(early, GRP) for t in ts]
    R = {(k, wu, w): o for k, wu, w, o in res}
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    print("## Y1@30 上市初期交易诊断（40 只全历史已完成交易）")
    for lab, s in (("上市初期（信号在第30～119根）", [t for t in tr if t["early"]]), ("其余交易", [t for t in tr if not t["early"]])):
        print(f"  {lab}: {len(s)} 笔  胜率 {sum(t['ret']>0 for t in s)/len(s)*100:.1f}%  平均每笔 {mean(t['ret'] for t in s)*100:+.2f}%  中位 {statistics.median(t['ret'] for t in s)*100:+.2f}%")
    E = [t for t in tr if t["early"]]
    print("  上市初期交易按标的：" + "  ".join(f"{c[1:]} {sum(1 for t in E if t['code']==c)}笔/{sum(t['ret'] for t in E if t['code']==c)*100:+.1f}%" for c in GRP if any(t['code']==c for t in E)))
    G39 = [c for c in GRP if c != "P588170"]
    for gname, grp in (("去掉 588170 的 39 只", G39), ("全部高波动 40 只", GRP)):
        print(f"\n######## {gname}")
        for wn, a, z in WIN:
            print(f"## {wn}")
            for k in ("现行", "Y1"):
                for wu in (120, 30):
                    o = R[(k, wu, (a, z))]; cs = [c for c in grp if c in o and o[c]["cagr"] is not None]
                    cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                    print(f"  {k}@{wu:<3} 年化 {mean(o[c]['cagr'] for c in cs)*100:6.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%  卡玛 {mean(cl):.3f}  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  有年化的标的 {len(cs)}  有结果的标的 {sum(c in o for c in grp)}")
    c39 = lambda wu: mean(cal(R[("Y1", wu, FULL)][c]) for c in G39 if c in R[("Y1", wu, FULL)] and cal(R[("Y1", wu, FULL)][c]) is not None)
    oth = [t for t in tr if not t["early"]]
    ok = mean(t["ret"] for t in E) >= 0 and mean(t["ret"] for t in E) >= mean(t["ret"] for t in oth)/2 and c39(30) >= c39(120) - .03
    print(f"\n## 判定：上市初期平均每笔 {mean(t['ret'] for t in E)*100:+.2f}%（其余 {mean(t['ret'] for t in oth)*100:+.2f}%），39 只卡玛 Y1@30 {c39(30):.3f} vs Y1@120 {c39(120):.3f} → {'可接受' if ok else '不可接受'}")
