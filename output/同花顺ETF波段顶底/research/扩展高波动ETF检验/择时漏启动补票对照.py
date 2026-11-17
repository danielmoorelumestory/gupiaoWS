"""用户问题（2026-11-16）：启动当天/前两天择时还是熊，买点被过滤，错过上升段的开头，怎么解决。事前写定（跑之前）：
方案（只改买入，卖出规则不变；A 组 14 只用 Y1·创业板择时，B 组 10 只用只认金叉·沪深300择时）：
- 现行。
- 补票N（N=1/2/3/5）：今天择时为牛、且过去 N 个交易日内出现过「被熊市挡掉的原始买点」（A：金叉或站上10日线且K−D≥5.3；B：金叉），
  并且至今 MACD 仍在金叉状态（中间没死叉；A 另要求今天收盘仍在 10 日线上）→ 次日开盘补买。
- 转牛补票：择时由熊转牛的当天，若 MACD 处于金叉状态（A 另要求在 10 日线上）→ 次日开盘买（不限信号出现多久以前）。
- 宽容0.5% / 宽容1%：择时比值不低于 20 日均线×(1−0.5%/1%) 就算牛（让择时早一点转牛，但也晚一点转熊，卖出也受影响）。
数据：1) ETF 自身历史；2) 跟踪指数延长到 2013 年起（取不到指数的用 ETF）。
指标：组内等权每日再平衡组合的年化、回撤、卡玛、赚钱年；单只平均卡玛；相对现行多出来的交易笔数、平均收益、胜率。
合格（事先定）：两套数据下组合卡玛都高于现行，且单只平均卡玛不低于现行。共 7 个方案×2 组，多重比较，小幅领先不算数。
单边 0.1% 成本。历史统计，不构成投资建议。
事后修正（2026-11-16，Codex 复测发现）：「单只平均」改为窗口内以 1 重新累计（C.window_metrics），原来直接截取全历史净值、窗口前盈亏混入；组合指标与合格判定不受影响。"""
import importlib.util, json, math, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C; Y = C.Y; K = C.K
import regime_multi as RM
FG = json.load(open("全量逐年优秀AB_最终分组.json")); GA, GB = FG["A"], FG["B"]
PATCH = '''    _entry0=entry_sig
    _ml=data["mlong"]
    def _raw(i):
        return gold[i] or (config["raw"]=="Y" and i>0 and above[i] and not above[i-1] and data["_kd"][i] >= 5.3)
    def entry_sig(i):
        if _entry0(i): return True
        if not reg[i] or not _ml[i] or (config["raw"]=="Y" and not above[i]): return False
        if config.get("cu"):
            return any((reg[j] is False or reg[j] is None or not reg[j]) and _raw(j) for j in range(max(0,i-config["cu"]),i))
        if config.get("flip"):
            return i>0 and not reg[i-1]
        return False
    def close_trade('''
def build(src, name):
    s = src.replace("    def close_trade(", PATCH, 1); s = s.replace(s[s.index("def simulate"):s.index("(")], "def " + name, 1)
    ns = dict(vars(C.T.G.engine)); ns["math"] = math; exec(s, ns); return ns[name]
simY = build(Y.src, "sim_y2"); simK = build(K.src, "sim_k2")
def tol_state(series, n, tol):
    ds = sorted(series); v = [series[d] for d in ds]; out = {}; s = 0.0
    for i, d in enumerate(ds):
        s += v[i]
        if i >= n: s -= v[i-n]
        out[d] = (v[i] >= s/n*(1-tol)) if i >= n-1 else None
    return out
VARS = ["现行", "补票1", "补票2", "补票3", "补票5", "转牛补票", "宽容0.5%", "宽容1%"]
def cfg(plan, v):
    base = {**Y.VAR["Y1"], "N": "R2-20", "raw": "Y"} if plan == "A" else {**C.T.BASE, "N": "H1", "raw": "K"}
    if v.startswith("补票"): base["cu"] = int(v[2:])
    if v == "转牛补票": base["flip"] = True
    if v.startswith("宽容"): base["N"] = ("R2" if plan == "A" else "H1") + v[2:]
    return base
def regs():
    p880 = RM.load_new("510880"); r2r = RM.ratio(RM.load_new("159915"), p880); h1r = RM.ratio(RM.index_series("sh000300"), p880)
    out = {}
    for t in (0.005, 0.01):
        out[f"R2{t*100:g}%"] = tol_state(r2r, 20, t); out[f"H1{t*100:g}%"] = tol_state(h1r, 20, t)
    return out
def run_all(d, plan):
    for k, s in regs().items(): d["reg"][k] = RM.last_known(s, d["dates"])
    out = {}
    for v in VARS:
        c = cfg(plan, v); r = (simY if plan == "A" else simK)(d, c, C.FULL, 20, retain=True)
        out[v] = ({p["date"]: p["nav"] for p in r["nav"]}, [(t["entry_date"], t["net_return"]) for t in r["trades"]])
    return out
def etf_job(code):
    C.init(); d = C.T.M.PANEL[[k for k in C.T.M.PANEL if k[1:] == code][0]]
    return code, run_all(d, "A" if code in GA else "B")
def idx_job(code):
    if code not in X.INDEX: return etf_job(code)
    p880 = RM.load_new("510880"); r2 = RM.ma_state(RM.ratio(RM.load_new("159915"), p880), 20); h1 = RM.ma_state(RM.ratio(RM.index_series("sh000300"), p880), 20)
    return code, run_all(X.entry(code, X.index_rows(X.INDEX[code]), r2, h1), "A" if code in GA else "B")
def report(title, res, W):
    print(f"\n## {title}（{W[0]}～{W[1]}）")
    best = {}
    for g, members in (("A 组 Y1·创业板择时", GA), ("B 组 只认金叉·沪深300择时", GB)):
        print(f"  [{g}，{len(members)} 只]")
        for v in VARS:
            navs = {c: {d: x for d, x in res[c][v][0].items() if W[0] <= d <= W[1]} for c in members}
            m = C.metrics(C.portfolio(members, {c: C.daily(res[c][v][0]) for c in members}, W))
            single = statistics.mean(C.window_metrics(res[c][v][0], W)["cal"] for c, n in navs.items() if len(n) > 60)
            base = {(c, e) for c in members for e, _ in res[c]["现行"][1] if W[0] <= e <= W[1]}
            extra = [r for c in members for e, r in res[c][v][1] if W[0] <= e <= W[1] and (c, e) not in base]
            ex = f"多出 {len(extra):3d} 笔 平均 {statistics.mean(extra)*100:+5.1f}% 胜率 {sum(r>0 for r in extra)/len(extra)*100:3.0f}%" if extra and v != "现行" else ""
            print(f"    {v:<8} 组合 年化 {m['cagr']*100:5.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:4.2f} 赚钱年 {m['pos']}/{len(m['years'])} 最差年 {m['worst']*100:+5.1f}% ｜ 单只平均卡玛 {single:4.2f} ｜ {ex}")
            best[(g, v)] = (m["cal"], single)
    return best
if __name__ == "__main__":
    with Pool(8) as p: E = dict(p.map(etf_job, GA + GB))
    bE = report("1) ETF 自身历史", E, ("1900-01-01", X.END)); report("1') ETF 自身历史，2020 年起", E, ("2020-01-02", X.END))
    with Pool(8) as p: I = dict(p.map(idx_job, GA + GB))
    bI = report("2) 跟踪指数延长", I, ("2013-01-04", X.END))
    print("\n## 合格判定（两套数据组合卡玛都高于现行，且单只平均卡玛不低于现行）")
    for g in ("A 组 Y1·创业板择时", "B 组 只认金叉·沪深300择时"):
        ok = [v for v in VARS[1:] if bE[(g, v)][0] > bE[(g, "现行")][0] and bI[(g, v)][0] > bI[(g, "现行")][0] and bE[(g, v)][1] >= bE[(g, "现行")][1] and bI[(g, v)][1] >= bI[(g, "现行")][1]]
        print(f"  {g}：{'、'.join(ok) if ok else '无'}")
