"""诊断（跑后分析，不用于选参）：全部已知高波动 40 只，B（金叉或站上10日 + 空头破10日卖）相对现行（R2 只认金叉）的逐只逐年差异。
年收益 = 当年最后一个交易日净值 / 上年最后一个交易日净值 − 1（首年从起点算；不足 60 个交易日的首尾年不计）。"""
import math, statistics
from collections import defaultdict
from multiprocessing import Pool
import R2站上10日线买对照 as T, run_extended as X
FULL = ("1900-01-01", "2026-11-10")
def yearly(nav):
    by = defaultdict(list)
    for r in nav: by[r["date"][:4]].append(r["nav"])
    out = {}; prev = 1.0
    for y in sorted(by):
        if len(by[y]) >= 60: out[y] = by[y][-1] / prev - 1
        prev = by[y][-1]
    return out
def job(code):
    d = T.M.PANEL[code]
    a = T.simulate_rgm(d, T.VAR["现行"], FULL, 20, retain=True); b = T.simulate_rgm(d, T.VAR["B同A加空头破10日卖"], FULL, 20, retain=True)
    return code, a["metric"], b["metric"], yearly(a["nav"]), yearly(b["nav"])
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    V = {**{"P"+k: vol(d["rows"]) for k, d in pool.items()}, **{"N"+it["code"]: it["vol"] for it in audit if "vol" in it}}
    names = {**{"P"+k: d["item"]["name"] for k, d in pool.items()}, **{"N"+it["code"]: it["name"] for it in audit}}
    GRP = [c for c in V if c.startswith("P") and V[c] >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=T.init) as p: res = p.map(job, GRP)
    rows = []
    for code, ma, mb, ya, yb in res:
        if ma["cagr"] is None: continue
        ys = sorted(set(ya) & set(yb)); diff = {y: yb[y] - ya[y] for y in ys}
        rows.append(dict(code=code[1:], name=names[code], src="池外" if code[0] == "N" else "原主池", vol=V[code], first=ma["first"][:4], n=len(ys),
                         win=sum(v > 0.005 for v in diff.values()), lose=sum(v < -0.005 for v in diff.values()), avg=statistics.mean(diff.values()),
                         ca=ma["cagr"], cb=mb["cagr"], da=ma["mdd"], db=mb["mdd"], ea=ma["entries"], eb=mb["entries"], diff=diff))
    rows.sort(key=lambda r: -(r["cb"] - r["ca"]))
    yrs = sorted({y for r in rows for y in r["diff"]})
    def show(r):
        return (f"{r['code']} {r['name'][:8]:<8} {r['src']} 波动{r['vol']*100:4.1f}% 起{r['first']}  年化 现行{r['ca']*100:6.2f}% B{r['cb']*100:6.2f}% 差{(r['cb']-r['ca'])*100:+6.2f}  "
                f"回撤 {r['da']*100:6.1f}%→{r['db']*100:6.1f}%  B好/差/平 年数 {r['win']}/{r['lose']}/{r['n']-r['win']-r['lose']}  年均差{r['avg']*100:+5.1f}\n      逐年差: " + " ".join(f"{y[2:]}:{r['diff'][y]*100:+.0f}" for y in sorted(r['diff'])))
    print(f"共 {len(rows)} 只（年差 ±0.5 个百分点以内算平）\n")
    print("=== 全部按年化差排序 ===")
    for r in rows: print(show(r))
    print("\n=== 逐年都较稳定改善（B 好的年数 ≥ 70%，且年化差 > 0）===")
    for r in rows:
        if r["win"] >= .7 * r["n"] and r["cb"] > r["ca"]: print(f"  {r['code']} {r['name']}  {r['win']}/{r['n']} 年更好  年化差 {(r['cb']-r['ca'])*100:+.2f}")
    print("\n=== 逐年多数变差（B 差的年数 ≥ 50%，且年化差 < 0）===")
    for r in rows:
        if r["lose"] >= .5 * r["n"] and r["cb"] < r["ca"]: print(f"  {r['code']} {r['name']}  {r['lose']}/{r['n']} 年更差  年化差 {(r['cb']-r['ca'])*100:+.2f}")
    # 特征相关
    import statistics as st
    xs = [r["vol"] for r in rows]; ys_ = [r["cb"] - r["ca"] for r in rows]
    mx, my = st.mean(xs), st.mean(ys_); cov = sum((a-mx)*(b-my) for a, b in zip(xs, ys_)); r_ = cov / math.sqrt(sum((a-mx)**2 for a in xs) * sum((b-my)**2 for b in ys_))
    print(f"\n波动率与 B 年化改善的相关系数 {r_:+.2f}")
    print("逐年（全部标的平均差，B−现行，百分点）：" + " ".join(f"{y}:{st.mean(r['diff'][y] for r in rows if y in r['diff'])*100:+.1f}(n{sum(y in r['diff'] for r in rows)})" for y in yrs))
