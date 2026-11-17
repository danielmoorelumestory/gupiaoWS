"""用户要求（2026-11-17）：用 /Users/train/orca/projects/同花顺/ths_bull_bear.py 的「牛熊线」回测。事前写定（跑之前）：
牛熊线（原样导入该文件的 ema/sma/kama/rsi/bull_bear，不改其代码）：收盘价的 20 日 EMA（另测 SMA20、KAMA）。
一、当作买卖策略（原样信号）：收盘跌破牛熊线且 RSI14<50 → N 买；收盘突破且 RSI14>50 → X 卖（高抛低吸）。
   成交：N 次日开盘买；X 当天收盘卖（与研究惯例一致，买入当天的 X 顺延到次日开盘卖）；单边 0.1% 成本；空仓见 N 才买，持仓见 X 才卖。
   另测：不加 RSI 过滤；反向用法（突破买、跌破卖 = 顺势），作对照。
   价格用研究口径复权（加回分红），开盘价按同日收盘的复权差平移。前 120 根只预热。
二、当作择时：把现行择时的「比值 > 20 日 SMA」换成「比值 > 牛熊线（EMA20 / KAMA）」，A 组 Y1、B 组只认金叉，其余不变。
样本：A 组 14、B 组 10（与现行方案对比）；全部面板与高波动子集（与现行方案、一直持有对比，排除选样偏向）。
窗口：2020-01-02～2026-11-10 与 全历史。单只用窗口内重新累计的指标（C.window_metrics）；组合等权每日再平衡。
判读（事先定）：一、若原样策略在全部面板上的单只平均卡玛与组合卡玛都高于现行方案，才值得进一步研究；
二、EMA/KAMA 择时须在 A/B 组与全面板 2020 年起组合卡玛都高于现行 SMA20 才算更好。历史统计，不构成投资建议。"""
import importlib.util, json, math, statistics, sys
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import regime_multi as RM
sp2 = importlib.util.spec_from_file_location("THS", "/Users/train/orca/projects/同花顺/ths_bull_bear.py"); THS = importlib.util.module_from_spec(sp2); sys.modules["THS"] = THS; sp2.loader.exec_module(THS)
FG = json.load(open("全量逐年优秀AB_最终分组.json")); GA, GB = FG["A"], FG["B"]
COST = 0.001
STRATS = {"原样EMA": dict(line="ema", rsi=True, rev=False), "原样SMA": dict(line="sma", rsi=True, rev=False), "原样KAMA": dict(line="kama", rsi=True, rev=False),
          "EMA无RSI": dict(line="ema", rsi=False, rev=False), "反向EMA(顺势)": dict(line="ema", rsi=False, rev=True)}
def strat_nav(d, cfg):
    rows = d["rows"]; dates = d["dates"]
    adj = [float(r["adjusted_close"]) for r in rows]; op = [float(r["open"]) + adj[i] - float(r["close"]) for i, r in enumerate(rows)]
    _, sigs = THS.bull_bear(adj, dates, line=cfg["line"], span=20, use_rsi_filter=cfg["rsi"])
    kind = {s.date: s.kind for s in sigs}
    buy, sell = ("X", "N") if cfg["rev"] else ("N", "X")
    nav, cash, sh, pend_b, pend_s, out, bought = 1.0, 1.0, 0.0, False, False, {}, -1
    for i, t in enumerate(dates):
        if pend_s and sh: cash = sh * op[i] * (1 - COST); sh = 0; pend_s = False
        if pend_b and not sh: sh = cash * (1 - COST) / op[i]; cash = 0; pend_b = False; bought = i
        if i >= 120:
            k = kind.get(t)
            if sh and k == sell:
                if bought == i: pend_s = True
                else: cash = sh * adj[i] * (1 - COST); sh = 0
            elif not sh and k == buy: pend_b = True
            out[t] = cash + sh * adj[i]
    return out
def hold_nav(d):
    adj = [float(r["adjusted_close"]) for r in d["rows"]]; return {t: adj[i]/adj[120] for i, t in enumerate(d["dates"]) if i >= 120}
p880 = RM.load_new("510880"); R2R = RM.ratio(RM.load_new("159915"), p880); H1R = RM.ratio(RM.index_series("sh000300"), p880)
def line_state(ratio, kind):
    ds = sorted(ratio); v = [ratio[x] for x in ds]; ln = THS._LINES[kind](v, 20) if kind != "kama" else THS.kama(v)
    return {x: (v[i] > ln[i]) if i >= 19 else None for i, x in enumerate(ds)}
SIG = {"R2-20": RM.ma_state(R2R, 20), "R2-ema": line_state(R2R, "ema"), "R2-kama": line_state(R2R, "kama"),
       "H1-20": RM.ma_state(H1R, 20), "H1-ema": line_state(H1R, "ema"), "H1-kama": line_state(H1R, "kama")}
TIM = {"现行SMA20": "20", "牛熊线EMA20": "ema", "牛熊线KAMA": "kama"}
def job(key):
    C.init(); d = C.T.M.PANEL[key]
    for n, s in SIG.items(): d["reg"][n] = RM.last_known(s, d["dates"])
    c = [float(r["adjusted_close"]) for r in d["rows"]]; lr = [math.log(c[i]/c[i-1]) for i in range(1, len(c)) if c[i-1] > 0]
    out = {"vol": statistics.pstdev(lr) * math.sqrt(244) if len(lr) > 20 else 0, "持有": hold_nav(d)}
    for k, cfg in STRATS.items(): out[k] = strat_nav(d, cfg)
    for name, suf in TIM.items():
        ra = C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": f"R2-{suf}"}, C.FULL, 20, retain=True)
        rb = C.K.simulate_kd(d, {**C.T.BASE, "N": f"H1-{suf}"}, C.FULL, 20, retain=True)
        out[f"A方案·{name}"] = {p["date"]: p["nav"] for p in ra["nav"]} if ra else {}
        out[f"B方案·{name}"] = {p["date"]: p["nav"] for p in rb["nav"]} if rb else {}
    return key[1:], out
def table(res, codes, keys, W, title):
    print(f"\n## {title}（{len(codes)} 只，{W[0]}～{W[1]}）")
    for k in keys:
        cs = [c for c in codes if res[c][k]]; ms = [C.window_metrics(res[c][k], W) for c in cs]; ms = [m for m in ms if m]
        pm = C.metrics(C.portfolio(cs, {c: C.daily(res[c][k]) for c in cs}, W))
        print(f"  {k:<18} 组合 年化 {pm['cagr']*100:5.1f}% 回撤 {pm['mdd']*100:6.1f}% 卡玛 {pm['cal']:4.2f} 赚钱年 {pm['pos']}/{len(pm['years'])} ｜ 单只平均 年化 {statistics.mean(m['cagr'] for m in ms)*100:5.1f}% 回撤 {statistics.mean(m['mdd'] for m in ms)*100:6.1f}% 卡玛 {statistics.mean(m['cal'] for m in ms):5.2f}")
if __name__ == "__main__":
    C.init(); keys = list(C.T.M.PANEL)
    with Pool(8) as p: res = dict(p.map(job, keys))
    S = list(STRATS)
    for W in (("2020-01-02", X.END), ("1900-01-01", X.END)):
        panel = [c for c in res if sum(1 for t in res[c]["持有"] if t >= W[0]) >= 244]; hv = [c for c in panel if res[c]["vol"] >= 0.31]
        print(f"\n######## 一、牛熊线当买卖策略  窗口 {W[0]} 起")
        table(res, panel, S + ["A方案·现行SMA20", "B方案·现行SMA20", "持有"], W, "全部面板")
        table(res, hv, S + ["A方案·现行SMA20", "B方案·现行SMA20", "持有"], W, "高波动(≥31%)")
        table(res, [c for c in GA if c in res], S + ["A方案·现行SMA20", "持有"], W, "A 组")
        table(res, [c for c in GB if c in res], S + ["B方案·现行SMA20", "持有"], W, "B 组")
        print(f"\n######## 二、牛熊线当择时（替换比值的 20 日 SMA）  窗口 {W[0]} 起")
        table(res, [c for c in GA if c in res], [f"A方案·{n}" for n in TIM], W, "A 组 Y1")
        table(res, [c for c in GB if c in res], [f"B方案·{n}" for n in TIM], W, "B 组 只认金叉")
        table(res, panel, [f"A方案·{n}" for n in TIM] + [f"B方案·{n}" for n in TIM], W, "全部面板")
    print("\n## 择时信号本身（2020 年起）")
    for side in ("R2", "H1"):
        for suf in ("20", "ema", "kama"):
            s = SIG[f"{side}-{suf}"]; ds = [t for t in sorted(s) if "2020-01-02" <= t <= X.END and s[t] is not None]; v = [s[t] for t in ds]
            base = SIG[f"{side}-20"]
            print(f"  {side}-{suf:<5} 牛市 {sum(v)/len(v)*100:4.1f}% 每年切换 {sum(v[i] != v[i-1] for i in range(1, len(v)))/(len(v)/244):4.1f} 次 与SMA20同向 {sum(s[t] == base[t] for t in ds)/len(ds)*100:5.1f}%")
