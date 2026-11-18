"""用户要求（2026-11-18）：在这些 ETF 里，有没有在「双择时·谁发起谁卖」「双择时·本组优先卖」下表现稳定、特别好的。事前写定（跑之前）：
逐只比较，对照 = 该 ETF 的「更好的单策略」（只用A、只用B 两者里全历史卡玛更高者）。双择时变体：谁发起谁卖（同日 A 优先 / B 优先）、本组优先卖（本组=A / 本组=B），共 4 种，取对该 ETF 最好的一种另行标注（存在挑选偏差）。
「稳定更好」须同时满足：①前段（2021 年及以前）与后段（2022 年起）卡玛都高于对照；②逐年收益胜过对照的年份 ≥ 60%；③没有任何一年比对照差 10 个百分点以上；④两段都至少有 2 个完整年。
为判断是不是运气：同样标准反过来数「对照稳定胜过双择时」的只数，以及打乱年份标签的随机基准不做（样本太小），只做对称比较。
口径：单只净值，用 C.window_metrics 在各段内重新累计；逐年收益按自然年。历史统计，不构成投资建议。"""
import importlib.util, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("P", "双择时本组优先卖对照.py"); P = importlib.util.module_from_spec(sp); sp.loader.exec_module(P)
C, X = P.C, P.X
V = {"谁发起谁卖·A优先": "双择时·A优先", "谁发起谁卖·B优先": "双择时·B优先", "本组优先卖·本组=A": "A·双择时本组优先卖", "本组优先卖·本组=B": "B·双择时本组优先卖"}
def _job(k): return P.job(k)
W1, W2, WF = ("1900-01-01", "2021-12-31"), ("2022-01-01", X.END), ("1900-01-01", X.END)
def yearly(nav):
    m = C.window_metrics(nav, WF); return m["years"] if m else {}
def evaluate(res, c, vname, ref):
    a, b = res[c][V[vname]][0], res[c][ref][0]
    ya, yb = yearly(a), yearly(b); ys = [y for y in ya if y in yb and y != min(ya)]  # 去掉首个（预热后不完整）年份
    m1a, m1b, m2a, m2b = (C.window_metrics(x, w) for x, w in ((a, W1), (b, W1), (a, W2), (b, W2)))
    n1 = len([y for y in ys if y <= "2021"]); n2 = len([y for y in ys if y >= "2022"]) - (1 if "2026" in ys else 0)
    if not (m1a and m1b and m2a and m2b) or n1 < 2 or n2 < 2: return None
    diff = [ya[y] - yb[y] for y in ys]
    return {"d1": m1a["cal"] - m1b["cal"], "d2": m2a["cal"] - m2b["cal"], "win": sum(x > 0 for x in diff)/len(diff), "worst": min(diff), "best": max(diff),
            "cal": C.window_metrics(a, WF)["cal"], "calref": C.window_metrics(b, WF)["cal"], "ya": ya, "yb": yb, "ys": ys}
def stable(e, sign=1):
    if not e: return False
    if sign > 0: return e["d1"] > 0 and e["d2"] > 0 and e["win"] >= 0.6 and e["worst"] > -0.10
    return e["d1"] < 0 and e["d2"] < 0 and e["win"] <= 0.4 and e["best"] < 0.10
if __name__ == "__main__":
    C.init()
    with Pool(8) as p: res = dict(p.map(_job, list(C.T.M.PANEL)))
    names = {k[1:]: v["item"]["name"] for k, v in C.T.M.PANEL.items()}
    rows = []
    for c in res:
        if not res[c]["单用A"][0]: continue
        ca, cb = (C.window_metrics(res[c][k][0], WF)["cal"] for k in ("单用A", "单用B"))
        ref = "单用A" if ca >= cb else "单用B"
        ev = {v: evaluate(res, c, v, ref) for v in V}
        rows.append((c, ref, ev))
    valid = [r for r in rows if any(r[2].values())]
    print(f"可比 ETF：{len(valid)} 只（两段都至少 2 个完整年）")
    for v in V:
        good = [r for r in valid if stable(r[2][v], 1)]; bad = [r for r in valid if stable(r[2][v], -1)]; n = sum(1 for r in valid if r[2][v])
        print(f"\n## {v}：双择时稳定更好 {len(good)} 只 ｜ 对照(单策略)稳定更好 {len(bad)} 只 ｜ 共 {n} 只")
        for c, ref, ev in sorted(good, key=lambda r: -r[2][v]["d2"]):
            e = ev[v]; nm = names.get(c, "") if isinstance(names, dict) else ""
            yy = " ".join(f"{y[2:]}:{(e['ya'][y]-e['yb'][y])*100:+.0f}" for y in e["ys"])
            print(f"  {c} {nm:<10} 对照={ref} 全期卡玛 {e['cal']:.2f} vs {e['calref']:.2f} ｜ 前段卡玛差 {e['d1']:+.2f} 后段 {e['d2']:+.2f} ｜ 逐年胜 {e['win']*100:.0f}% 最差年差 {e['worst']*100:+.0f}pp ｜ 逐年差 {yy}")
    print("\n## 任一变体稳定更好（并集，含挑选偏差）")
    anyg = [r for r in valid if any(stable(r[2][v], 1) for v in V)]; anyb = [r for r in valid if any(stable(r[2][v], -1) for v in V)]
    print(f"  双择时任一变体稳定更好：{len(anyg)} 只；单策略稳定胜过任一变体：{len(anyb)} 只")
    for c, ref, ev in anyg: print(f"  {c} {names.get(c, '') if isinstance(names, dict) else ''} → " + "、".join(v for v in V if stable(ev[v], 1)))
