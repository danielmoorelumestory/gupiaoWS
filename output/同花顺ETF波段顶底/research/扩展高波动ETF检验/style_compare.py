"""风格比值成长端对比（诊断，非预设选参）：创业板/创业板50/科创50/科创创业50 ÷ 红利低波 或 红利，
比值 > 自身 20 日均线 = 偏进攻；模板 T1（熊市不开新仓，死叉尾盘卖）。共同窗口：2021-09-01～2026-11-10（全部信号已形成）。"""
import math, random, statistics
from multiprocessing import Pool
import regime_multi as M, run_extended as X
GROWTH = {"创业板": "159915", "创业板50": "159949", "科创50": "588000", "科创创业50": "159781"}
DEF = {"红利低波": "512890", "红利": "510880"}
SIGS = {}
def build_sig(pool):
    defs = {"红利低波": M.series_from_rows(pool["512890"]["rows"]), "红利": M.load_new("510880")}
    out = {}
    for gn, gc in GROWTH.items():
        g = M.load_new(gc)
        for dn, d in defs.items(): out[f"{gn}÷{dn}"] = M.ma_state(M.ratio(g, d), 20)
    return out
PANEL = None
def init():
    global PANEL, SIGS
    pool, new, audit = X.build(); SIGS = build_sig(pool)
    PANEL = {**{"P"+k: v for k, v in pool.items()}, **{"N"+k: v for k, v in new.items()}}
    for d in PANEL.values(): d["reg"] = {k: M.last_known(s, d["dates"]) for k, s in SIGS.items()}
def run(job):
    key, w = job; out = {}
    for code, d in PANEL.items():
        if key == "纯MACD": r = M.C.simulate_cs(d, M.C.grid[M.C.MACD_KEY], w, 20)
        elif key == "买入持有": r = M.C.engine.simulate(d, M.C.HOLD, w, 20)
        else: r = M.G.simulate_rg(d, M.cfg(key, "T1熊不开新仓"), w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
if __name__ == "__main__":
    pool, new, audit = X.build()
    keys = ["纯MACD", "买入持有"] + [f"{g}÷{d}" for g in GROWTH for d in DEF]
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    groups = {"池外高波动10": ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new],
              "原主池高波动31": ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31]}
    wins = [("共同窗口 2021-09～2026-11", "2021-09-01", "2026-11-10"), ("熊 2021-09～2024-01", "2021-09-01", "2024-01-31"), ("牛 2024-02～2026-11", "2024-02-01", "2026-11-10")]
    with Pool(8, initializer=init) as p: res = p.map(run, [(k, (a, z)) for k in keys for _, a, z in wins])
    R = {(k, w): o for k, w, o in res}
    for gname, grp in groups.items():
        print(f"\n######## {gname}")
        for wn, a, z in wins:
            base = R[("纯MACD", (a, z))]
            print(f"\n## {wn}（年化中位 / 回撤中位 / 卡玛中位 / 逐只胜纯MACD / 年化差95%区间）")
            rows = []
            for k in keys:
                o = R[(k, (a, z))]; cs = [c for c in grp if c in o and o[c]["cagr"] is not None]
                if not cs: continue
                cagr = statistics.median(o[c]["cagr"] for c in cs); mdd = statistics.median(o[c]["mdd"] for c in cs)
                cal = statistics.median(o[c]["cagr"]/abs(o[c]["mdd"]) for c in cs if o[c]["mdd"] < 0)
                extra = ""
                if k != "纯MACD":
                    pc = [c for c in cs if c in base and base[c]["cagr"] is not None]
                    rnd = random.Random(20261113)
                    dd = sorted(statistics.median(o[c]["cagr"] for c in s) - statistics.median(base[c]["cagr"] for c in s) for s in ([rnd.choice(pc) for _ in pc] for _ in range(1000)))
                    extra = f"  胜 {sum(o[c]['cagr'] > base[c]['cagr'] for c in pc)}/{len(pc)}  [{dd[25]*100:+.1f},{dd[974]*100:+.1f}]{' ★' if dd[25] > 0 else (' ✗' if dd[974] < 0 else '')}"
                rows.append((cal, f"  {k:<14} {cagr*100:7.2f}%  回撤 {mdd*100:6.1f}%  卡玛 {cal:6.3f}{extra}  n={len(cs)}"))
            for _, line in sorted(rows, key=lambda r: -r[0]): print(line)
    # 信号同步度：各比值与 R1 在共同窗口内状态一致的天数比例
    init()
    ref = SIGS["创业板50÷红利低波"]; ds = [d for d in sorted(ref) if "2021-09-01" <= d <= "2026-11-10"]
    print("\n## 与 R1（创业板50÷红利低波）状态一致的交易日比例 / 偏进攻天数占比")
    for k, s in SIGS.items():
        same = [s.get(d) == ref.get(d) for d in ds if s.get(d) is not None and ref.get(d) is not None]
        bull = [s.get(d) for d in ds if s.get(d) is not None]
        print(f"  {k:<14} 一致 {sum(same)/len(same)*100:5.1f}%  偏进攻 {sum(bull)/len(bull)*100:5.1f}%")
