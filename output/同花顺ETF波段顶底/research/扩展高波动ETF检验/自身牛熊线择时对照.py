"""用户选择（2026-11-17）：用 ETF 自身的牛熊线做择时。事前写定（跑之前）：
牛熊线：/Users/train/orca/projects/同花顺/ths_bull_bear.py 的 ema（20 日 EMA，原样导入）作用在该 ETF 自身复权收盘价上；另测 kama。
择时：当日收盘 > 自身牛熊线 为牛，否则熊（当日收盘判断，次日开盘成交，与现行一致）；前 20 根按牛（反正前 120 根只预热）。
方案（买卖规则不变，只换择时）：
- A：Y1；择时 ∈ {现行 创业板÷红利, 自身EMA20, 自身KAMA, 现行 且 自身EMA20（两者都牛才算牛）}
- B：只认金叉；择时 ∈ {现行 沪深300÷红利, 自身EMA20, 自身KAMA, 现行 且 自身EMA20}
样本：A 组 14（A 方案）、B 组 10（B 方案）；全部面板与高波动子集两套方案都跑（排除选样偏向）。
窗口：2020-01-02～2026-11-10 与 全历史；单只用窗口内重新累计指标（C.window_metrics），组合等权每日再平衡。
合格（事先定）：某择时在 A/B 组与全部面板（2020 年起）的组合卡玛都高于现行，且全部面板单只平均卡玛不低于现行。
单边 0.1% 成本。历史统计，不构成投资建议。"""
import importlib.util, json, math, statistics, sys
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import regime_multi as RM
sp2 = importlib.util.spec_from_file_location("THS", "/Users/train/orca/projects/同花顺/ths_bull_bear.py"); THS = importlib.util.module_from_spec(sp2); sys.modules["THS"] = THS; sp2.loader.exec_module(THS)
FG = json.load(open("全量逐年优秀AB_最终分组.json")); GA, GB = FG["A"], FG["B"]
TIM = ["现行", "自身EMA20", "自身KAMA", "现行且自身EMA20"]
def own(d, kind):
    c = [float(r["adjusted_close"]) for r in d["rows"]]; ln = THS.ema(c, 20) if kind == "ema" else THS.kama(c)
    return [True if i < 20 else c[i] > ln[i] for i in range(len(c))]
def job(key):
    C.init(); d = C.T.M.PANEL[key]
    e, k = own(d, "ema"), own(d, "kama")
    for side in ("R2-20", "H1"):
        base = d["reg"][side]
        d["reg"][f"{side}|现行"] = base; d["reg"][f"{side}|自身EMA20"] = e; d["reg"][f"{side}|自身KAMA"] = k
        d["reg"][f"{side}|现行且自身EMA20"] = [bool(b) and x for b, x in zip(base, e)]
    c = [float(r["adjusted_close"]) for r in d["rows"]]; lr = [math.log(c[i]/c[i-1]) for i in range(1, len(c)) if c[i-1] > 0]
    out = {"vol": statistics.pstdev(lr) * math.sqrt(244) if len(lr) > 20 else 0,
           "flips": sum(e[i] != e[i-1] for i in range(121, len(e))) / max(1, (len(e) - 121) / 244)}
    for t in TIM:
        ra = C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": f"R2-20|{t}"}, C.FULL, 20, retain=True)
        rb = C.K.simulate_kd(d, {**C.T.BASE, "N": f"H1|{t}"}, C.FULL, 20, retain=True)
        out[("A", t)] = {p["date"]: p["nav"] for p in ra["nav"]} if ra else {}
        out[("B", t)] = {p["date"]: p["nav"] for p in rb["nav"]} if rb else {}
    return key[1:], out
def table(res, codes, plan, W, title, keep):
    print(f"\n## {title}（{len(codes)} 只，{plan} 方案，{W[0]}～{W[1]}）")
    for t in TIM:
        cs = [c for c in codes if res[c][(plan, t)]]; ms = [m for m in (C.window_metrics(res[c][(plan, t)], W) for c in cs) if m]
        pm = C.metrics(C.portfolio(cs, {c: C.daily(res[c][(plan, t)]) for c in cs}, W))
        sc = statistics.mean(m["cal"] for m in ms)
        print(f"  {t:<14} 组合 年化 {pm['cagr']*100:5.1f}% 回撤 {pm['mdd']*100:6.1f}% 卡玛 {pm['cal']:4.2f} 赚钱年 {pm['pos']}/{len(pm['years'])} 最差年 {pm['worst']*100:+5.1f}% ｜ 单只平均 年化 {statistics.mean(m['cagr'] for m in ms)*100:5.1f}% 回撤 {statistics.mean(m['mdd'] for m in ms)*100:6.1f}% 卡玛 {sc:5.2f}")
        keep[(title, plan, t)] = (pm["cal"], sc)
if __name__ == "__main__":
    C.init(); keys = list(C.T.M.PANEL)
    with Pool(8) as p: res = dict(p.map(job, keys))
    print(f"自身牛熊线（EMA20）每年切换次数：全部面板平均 {statistics.mean(o['flips'] for o in res.values()):.1f} 次（对比：创业板择时约 27.5 次，沪深300择时约 25.1 次）")
    K = {}
    for W in (("2020-01-02", X.END), ("1900-01-01", X.END)):
        panel = [c for c in res if sum(1 for t in res[c][("A", "现行")] if t >= W[0]) >= 244]; hv = [c for c in panel if res[c]["vol"] >= 0.31]
        tag = W[0][:4]
        table(res, [c for c in GA if c in res], "A", W, f"A 组·{tag}", K); table(res, [c for c in GB if c in res], "B", W, f"B 组·{tag}", K)
        for plan in ("A", "B"):
            table(res, panel, plan, W, f"全部面板·{tag}", K); table(res, hv, plan, W, f"高波动(≥31%)·{tag}", K)
    print("\n## 合格判定（2020 年起：A 组、B 组、全部面板两套方案的组合卡玛都高于现行，且全部面板单只平均卡玛不低于现行）")
    for t in TIM[1:]:
        checks = [K[("A 组·2020", "A", t)][0] > K[("A 组·2020", "A", "现行")][0], K[("B 组·2020", "B", t)][0] > K[("B 组·2020", "B", "现行")][0]]
        for plan in ("A", "B"):
            checks += [K[("全部面板·2020", plan, t)][0] > K[("全部面板·2020", plan, "现行")][0], K[("全部面板·2020", plan, t)][1] >= K[("全部面板·2020", plan, "现行")][1]]
        print(f"  {t}：{'合格' if all(checks) else '不合格'}（通过 {sum(checks)}/{len(checks)} 项）")
