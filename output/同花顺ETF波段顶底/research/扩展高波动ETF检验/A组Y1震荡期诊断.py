"""事后诊断（2026-11-15，用户指出 A 组 Y1·创业板择时 在 震荡 2016-02～2018-01 累计 −0.6%，持有 +22%）。
只作解释，不改规则：看这段 R2 择时牛熊占比、各方案逐只累计、Y1 每笔交易按买入/卖出原因拆分，并对照 H1 择时。"""
import json, statistics, importlib.util
from multiprocessing import Pool
def load(name, path):
    sp = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
Z = load("Z", "低波动沪深300择时对照.py"); F = load("F", "分组复测_持有MACD对照.py")
T, K, Y = Z.T, Z.K, Z.Y
W = ("2016-02-01", "2018-01-26"); A = F.A
P = {"一直持有": None, "纯MACD": ("KD", "ALL"), "现行·R2": ("KD", "R2-20"), "现行·H1": ("KD", "H1"),
     "Y1不择时": ("Y", "ALL"), "Y1·R2": ("Y", "R2-20"), "Y1·H1": ("Y", "H1")}
def work(_):
    Z.init(); out = {}
    for code, d in T.M.PANEL.items():
        if code[1:] not in A: continue
        i0 = [i for i, x in enumerate(d["dates"]) if i >= 120 and W[0] <= x <= W[1]]
        if len(i0) < 60: continue
        reg = d["reg"]["R2-20"]; h1 = d["reg"]["H1"]
        row = {"bullR2": statistics.mean(bool(reg[i]) for i in i0), "bullH1": statistics.mean(bool(h1[i]) for i in i0), "days": len(i0)}
        for k, p in P.items():
            if p is None: m = F.hold(d, W); row[k] = m["total_return"]; continue
            r = (K.simulate_kd(d, {**T.BASE, "N": p[1]}, W, 20) if p[0] == "KD" else Y.simulate_y(d, {**Y.VAR["Y1"], "N": p[1]}, W, 20, retain=True))
            row[k] = r["metric"]["total_return"]; row[k+"_exp"] = r["metric"]["time_exposure"]
            if k == "Y1·R2":
                gold, dead = d["macds"][(12, 26, 9)]; tr = []
                for t in r["trades"]:
                    xs = t["exit_signal_index"]
                    ex = "到期" if t["forced_end"] else ("死叉" if dead[xs] else "熊市破线")
                    tr.append(("金叉" if gold[t["entry_signal_index"]] else "站上10日", ex, t["net_return"]))
                row["trades"] = tr
        out[code] = row
    return out
if __name__ == "__main__":
    with Pool(1) as p: R = p.map(work, [0])[0]
    mean = lambda v: statistics.mean(v) if v else float("nan")
    print(f"## 震荡 2016-02～2018-01，A 组有数据 {len(R)} 只")
    print(f"  R2（创业板÷红利）为牛的交易日占比 平均 {mean([r['bullR2'] for r in R.values()])*100:.1f}%；H1（沪深300÷红利）{mean([r['bullH1'] for r in R.values()])*100:.1f}%")
    print("\n## 各方案累计收益平均 / 持仓时间")
    for k in P: print(f"  {k:<8} {mean([r[k] for r in R.values()])*100:+6.1f}%" + (f"  持仓 {mean([r[k+'_exp'] for r in R.values()])*100:4.1f}%" if k+"_exp" in next(iter(R.values())) else ""))
    print("\n## 逐只累计（R2牛占比）")
    print("  " + " "*20 + "R2牛  " + "".join(f"{k:<9}" for k in P))
    for c, r in R.items(): print(f"  {c[1:]} {F.NAMES.get(c[1:], ''):<12} {r['bullR2']*100:3.0f}% " + "".join(f"{r[k]*100:+7.1f}% " for k in P))
    print("\n## Y1·R2 交易拆解（全部只合计）")
    tr = [t for r in R.values() for t in r["trades"]]; groups = {}
    for e, x, ret in tr: groups.setdefault((e, x), []).append(ret)
    for (e, x), v in sorted(groups.items()): print(f"  买入={e:<5} 卖出={x:<5} {len(v):3d} 笔  平均 {mean(v)*100:+5.2f}%  胜率 {sum(a > 0 for a in v)/len(v)*100:4.0f}%  合计 {sum(v)*100:+6.1f}%")
    print(f"  共 {len(tr)} 笔，平均每只 {len(tr)/len(R):.1f} 笔")
