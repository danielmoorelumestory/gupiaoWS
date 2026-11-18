"""用户要求（2026-11-17）：MACD 或择时信号当天翻转但幅度很小（如红柱刚变微绿），当天不操作，看第二天。事前写定（跑之前）：
幅度定义：
- MACD：柱 = 2×(DIF−DEA)（同花顺显示口径），幅度 = |柱| ÷ 当日复权收盘价。金叉/死叉当天幅度 < θm 记为「微弱翻转」。
- 择时：比值相对其 20 日均线的偏离 = 比值/SMA20 − 1；牛熊切换当天 |偏离| < θr 记为「微弱翻转」。
两种处理（与现行「翻转即算」对比）：
- 等一天（用户说法）：微弱翻转当天视为没变；第二天若仍在新的一侧（柱同号 / 比值仍在均线同侧），第二天算翻转（不论幅度）；否则作废。
- 滞后带（对照）：只有幅度 ≥ θ 才算翻转，幅度不够就一直维持原状态，直到够了为止。
阈值（事前定）：θm ∈ {0.05%, 0.1%, 0.2%}；θr ∈ {0.2%, 0.5%, 1.0%}；合并版用 θm=0.1% + θr=0.5%。
只改 MACD 金叉死叉与择时，不改 10 日线等其他条件；买卖规则不变：A 方案 Y1+创业板÷510880，B 方案只认金叉+沪深300÷510880。
样本：A 组 14（A 方案）、B 组 10（B 方案）、全部面板 78 只与高波动子集（两套方案都跑）。
窗口 2020-01-02～2026-11-10 与全历史；单只用 C.window_metrics；组合等权每日再平衡；单边 0.1% 成本。
合格（事先定）：某设置在 A 组、B 组及全部面板两套方案（2020 年起）的组合卡玛都高于现行，且全部面板单只平均卡玛不低于现行。
历史统计，不构成投资建议。"""
import importlib.util, json, math, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import regime_multi as RM
FG = json.load(open("全量逐年优秀AB_最终分组.json")); GA, GB = FG["A"], FG["B"]
MK = (12, 26, 9)
p880 = RM.load_new("510880"); RAT = {"R2-20": RM.ratio(RM.load_new("159915"), p880), "H1": RM.ratio(RM.index_series("sh000300"), p880)}
def reg_dev(r):
    ds = sorted(r); v = [r[x] for x in ds]; out = {}; s = 0.0
    for i, x in enumerate(ds):
        s += v[i]
        if i >= 20: s -= v[i-20]
        out[x] = (v[i] > s/20, v[i]/(s/20) - 1) if i >= 19 else (None, 0.0)
    return ds, out
DEV = {k: reg_dev(r) for k, r in RAT.items()}
def reg_filtered(key, mode, th):
    ds, o = DEV[key]; out = {}; prev = None; state = None
    for x in ds:
        st, dv = o[x]
        if st is None: out[x] = None; continue
        if mode == "现行" or th == 0: cur = st
        elif mode == "等一天": cur = prev if (prev is not None and st != prev and abs(dv) < th) else st
        else:  # 滞后带
            if state is None: state = st
            elif st != state and abs(dv) >= th: state = st
            cur = state
        out[x] = cur; prev = st  # 等一天：与「前一天真实状态」比较，第二天直接取真实状态
    return out
REGC = {}
def macd_filtered(d, mode, th):
    c = [float(r["adjusted_close"]) for r in d["rows"]]; g0, d0 = d["macds"][MK]
    f = s = c[0]; dea = 0.0; bar = []
    for x in c:
        f = (2*x + 11*f)/13; s = (2*x + 25*s)/27; dif = f - s; dea = (2*dif + 8*dea)/10; bar.append(2*(dif - dea)/x)
    n = len(c)
    if mode == "现行" or th == 0: return g0, d0
    g, de = [False]*n, [False]*n
    if mode == "等一天":
        for i in range(n):
            if g0[i]:
                if bar[i] >= th: g[i] = True
                elif i+1 < n and bar[i+1] > 0: g[i+1] = True
            if d0[i]:
                if -bar[i] >= th: de[i] = True
                elif i+1 < n and bar[i+1] < 0: de[i+1] = True
    else:
        st = 1 if bar[0] > 0 else -1
        for i in range(1, n):
            if st < 0 and bar[i] >= th: st = 1; g[i] = True
            elif st > 0 and -bar[i] >= th: st = -1; de[i] = True
    return g, de
def small_share(d, th):
    c = [float(r["adjusted_close"]) for r in d["rows"]]; g0, d0 = d["macds"][MK]
    f = s = c[0]; dea = 0.0; k = t = 0
    for i, x in enumerate(c):
        f = (2*x + 11*f)/13; s = (2*x + 25*s)/27; dif = f - s; dea = (2*dif + 8*dea)/10
        if i >= 120 and (g0[i] or d0[i]): t += 1; k += abs(2*(dif - dea)/x) < th
    return k, t
SETS = [("现行", 0, 0)] + [(m, a, b) for m in ("等一天", "滞后带") for a, b in [(0.0005, 0), (0.001, 0), (0.002, 0), (0, 0.002), (0, 0.005), (0, 0.01), (0.001, 0.005)]]
def label(m, a, b):
    if m == "现行": return "现行（翻转即算）"
    return f"{m} " + " + ".join(([f"MACD<{a*100:g}%"] if a else []) + ([f"择时<{b*100:g}%"] if b else []))
def job(key):
    C.init(); d = C.T.M.PANEL[key]
    assert d["reg"]["R2-20"] == RM.last_known(reg_filtered("R2-20", "现行", 0), d["dates"])
    assert d["reg"]["H1"] == RM.last_known(reg_filtered("H1", "现行", 0), d["dates"])
    c = [float(r["adjusted_close"]) for r in d["rows"]]; lr = [math.log(c[i]/c[i-1]) for i in range(1, len(c)) if c[i-1] > 0]
    out = {"vol": statistics.pstdev(lr) * math.sqrt(244) if len(lr) > 20 else 0, "small": {a: small_share(d, a) for a in (0.0005, 0.001, 0.002)}}
    for m, a, b in SETS:
        gd = macd_filtered(d, m if a else "现行", a)
        for plan, N in (("A", "R2-20"), ("B", "H1")):
            rg = RM.last_known(reg_filtered(N, m if b else "现行", b), d["dates"])
            dd = {**d, "macds": {**d["macds"], MK: gd}, "reg": {**d["reg"], N: rg}}
            r = C.Y.simulate_y(dd, C.Y.VAR["Y1"], C.FULL, 20, retain=True) if plan == "A" else C.K.simulate_kd(dd, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True)
            out[(plan, label(m, a, b))] = ({p["date"]: p["nav"] for p in r["nav"]}, r["metric"]["entries"]) if r else ({}, 0)
    return key[1:], out
LAB = [label(*s) for s in SETS]
def table(res, codes, plan, W, title, K):
    print(f"\n## {title}（{len(codes)} 只，{plan} 方案，{W[0]}～{W[1]}）")
    for t in LAB:
        cs = [c for c in codes if res[c][(plan, t)][0]]; ms = [m for m in (C.window_metrics(res[c][(plan, t)][0], W) for c in cs) if m]
        pm = C.metrics(C.portfolio(cs, {c: C.daily(res[c][(plan, t)][0]) for c in cs}, W)); sc = statistics.mean(m["cal"] for m in ms)
        tr = statistics.mean(res[c][(plan, t)][1] for c in cs)
        print(f"  {t:<26} 组合 年化 {pm['cagr']*100:5.1f}% 回撤 {pm['mdd']*100:6.1f}% 卡玛 {pm['cal']:4.2f} 赚钱年 {pm['pos']}/{len(pm['years'])} ｜ 单只平均 年化 {statistics.mean(m['cagr'] for m in ms)*100:5.1f}% 回撤 {statistics.mean(m['mdd'] for m in ms)*100:6.1f}% 卡玛 {sc:5.2f} ｜ 全历史平均买入 {tr:5.1f} 次")
        K[(title, plan, t)] = (pm["cal"], sc)
if __name__ == "__main__":
    C.init(); keys = list(C.T.M.PANEL)
    with Pool(8) as p: res = dict(p.map(job, keys))
    print("## 微弱翻转占比（全部面板，前 120 根后）")
    for a in (0.0005, 0.001, 0.002):
        k = sum(o["small"][a][0] for o in res.values()); t = sum(o["small"][a][1] for o in res.values()); print(f"  MACD 金叉死叉当天 |柱|/价 < {a*100:g}%：{k}/{t} = {k/t*100:.1f}%")
    for N in ("R2-20", "H1"):
        ds, o = DEV[N]; fl = [abs(o[ds[i]][1]) for i in range(1, len(ds)) if o[ds[i]][0] is not None and o[ds[i-1]][0] is not None and o[ds[i]][0] != o[ds[i-1]][0] and ds[i] >= "2020-01-02"]
        print(f"  择时 {N} 2020 年起切换 {len(fl)} 次，偏离 <0.2% {sum(x<0.002 for x in fl)/len(fl)*100:.0f}% ，<0.5% {sum(x<0.005 for x in fl)/len(fl)*100:.0f}% ，<1% {sum(x<0.01 for x in fl)/len(fl)*100:.0f}%")
    K = {}
    for W in (("2020-01-02", X.END), ("1900-01-01", X.END)):
        panel = [c for c in res if sum(1 for t in res[c][("A", LAB[0])][0] if t >= W[0]) >= 244]; hv = [c for c in panel if res[c]["vol"] >= 0.31]; tag = W[0][:4]
        table(res, [c for c in GA if c in res], "A", W, f"A 组·{tag}", K); table(res, [c for c in GB if c in res], "B", W, f"B 组·{tag}", K)
        for plan in ("A", "B"): table(res, panel, plan, W, f"全部面板·{tag}", K); table(res, hv, plan, W, f"高波动(≥31%)·{tag}", K)
    print("\n## 合格判定（2020 年起）")
    for t in LAB[1:]:
        ck = [K[("A 组·2020", "A", t)][0] > K[("A 组·2020", "A", LAB[0])][0], K[("B 组·2020", "B", t)][0] > K[("B 组·2020", "B", LAB[0])][0]]
        for plan in ("A", "B"): ck += [K[("全部面板·2020", plan, t)][0] > K[("全部面板·2020", plan, LAB[0])][0], K[("全部面板·2020", plan, t)][1] >= K[("全部面板·2020", plan, LAB[0])][1]]
        print(f"  {t:<26} {'合格' if all(ck) else '不合格'}（{sum(ck)}/{len(ck)}）")
