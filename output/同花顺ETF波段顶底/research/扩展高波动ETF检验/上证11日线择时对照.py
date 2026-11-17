"""用户提议（2026-11-16）：择时改为「上证指数收盘在 11 日均线之上为牛」，测试 A、B 两组。事前写定（跑之前）：
择时：SH11 = 上证指数(sh000001) 收盘 > 11 日均线为牛，否则熊；与现行择时同样用当日收盘判断、次日生效方式（last_known）。
对照：A 组 14 只用 Y1 方案，择时 ∈ {现行 R2 创业板÷红利 20 日线, SH11, 不择时}；B 组 10 只用只认金叉方案，择时 ∈ {现行 H1 沪深300÷红利 20 日线, SH11, 不择时}。
数据两套：
 1) ETF 自身历史（与选组时相同；注意两组是在现行择时下选出来的，现行择时在此有先天优势）；
 2) 跟踪指数延长到 2013 年起（取不到指数的用 ETF）：2013–2019 年大多不在选组样本里，更公平。
指标：每只全历史年化/回撤/卡玛的组内平均；组内等权每日再平衡组合的年化、回撤、卡玛、逐年、分阶段；择时牛市天数占比与每年切换次数。
单边 0.1% 成本。历史统计，不构成投资建议。
事后修正（2026-11-16，Codex 复测发现）：「单只平均」改为窗口内以 1 重新累计（C.window_metrics），原来直接截取全历史净值、窗口前盈亏混入；组合指标与合格判定不受影响。"""
import importlib.util, json, math, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import regime_multi as RM
FG = json.load(open("全量逐年优秀AB_最终分组.json"))
GA, GB = FG["A"], FG["B"]
SH = RM.ma_state(RM.index_series("sh000001"), 11)
REGS = {"A": ["R2-20", "SH11", "ALL"], "B": ["H1", "SH11", "ALL"]}
LABEL = {"R2-20": "现行·创业板择时", "H1": "现行·沪深300择时", "SH11": "上证11日线", "ALL": "不择时"}
def simulate(d, plan, n):
    if plan == "A": return C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": n}, C.FULL, 20, retain=True)
    return C.K.simulate_kd(d, {**C.T.BASE, "N": n}, C.FULL, 20, retain=True)
def etf_job(code):
    C.init(); d = C.T.M.PANEL[[k for k in C.T.M.PANEL if k[1:] == code][0]]
    d["reg"]["SH11"] = RM.last_known(SH, d["dates"]); d["reg"]["ALL"] = [True] * len(d["dates"])
    plan = "A" if code in GA else "B"
    return code, {n: {p["date"]: p["nav"] for p in simulate(d, plan, n)["nav"]} for n in REGS[plan]}
def idx_job(code):
    if code not in X.INDEX: return etf_job(code)
    p880 = RM.load_new("510880"); r2 = RM.ma_state(RM.ratio(RM.load_new("159915"), p880), 20); h1 = RM.ma_state(RM.ratio(RM.index_series("sh000300"), p880), 20)
    d = X.entry(code, X.index_rows(X.INDEX[code]), r2, h1); d["reg"]["SH11"] = RM.last_known(SH, d["dates"])
    plan = "A" if code in GA else "B"
    return code, {n: {p["date"]: p["nav"] for p in simulate(d, plan, n)["nav"]} for n in REGS[plan]}
def regime_stats():
    p880 = RM.load_new("510880")
    sig = {"R2-20": RM.ma_state(RM.ratio(RM.load_new("159915"), p880), 20), "H1": RM.ma_state(RM.ratio(RM.index_series("sh000300"), p880), 20), "SH11": SH}
    print("## 择时信号本身（2013-01-04～2026-11-10）")
    for n, s in sig.items():
        ds = [d for d in sorted(s) if "2013-01-04" <= d <= X.END and s[d] is not None]; v = [s[d] for d in ds]
        flips = sum(v[i] != v[i-1] for i in range(1, len(v)))
        print(f"  {LABEL[n]:<14} 牛市天数 {sum(v)/len(v)*100:4.1f}%  切换 {flips} 次（每年约 {flips/(len(v)/244):.0f} 次）")
    a = sig["SH11"]; 
    for n in ("R2-20", "H1"):
        ds = [d for d in sorted(a) if "2013-01-04" <= d <= X.END and a[d] is not None and sig[n].get(d) is not None]
        print(f"  上证11日线 与 {LABEL[n]} 同向天数 {sum(a[d] == sig[n][d] for d in ds)/len(ds)*100:.1f}%")
def report(title, res, W):
    print(f"\n## {title}（{W[0]} 起）")
    for g, members, regs in (("A 组 Y1", GA, REGS["A"]), ("B 组 只认金叉", GB, REGS["B"])):
        print(f"  [{g}，{len(members)} 只]")
        for n in regs:
            R = {c: C.daily(res[c][n]) for c in members}
            single = [s for s in (C.window_metrics(res[c][n], W) for c in members) if s]  # 窗口内无数据的成员不计
            m = C.metrics(C.portfolio(members, R, W))
            print(f"    {LABEL[n]:<14} 组合 年化 {m['cagr']*100:5.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:4.2f} 赚钱年 {m['pos']}/{len(m['years'])} 最差年 {m['worst']*100:+5.1f}% ｜ 单只平均 年化 {statistics.mean(s['cagr'] for s in single)*100:5.1f}% 回撤 {statistics.mean(s['mdd'] for s in single)*100:6.1f}% 卡玛 {statistics.mean(s['cal'] for s in single):4.2f}")
            print(f"        逐年 " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
def stages(res):
    print("\n## 分阶段（指数延长版，组合累计收益 / 最大回撤）")
    for g, members, regs in (("A 组", GA, REGS["A"]), ("B 组", GB, REGS["B"])):
        print(f"  [{g}] " + " ｜ ".join(LABEL[n] for n in regs))
        for wn, a, z in C.Z.K.WINDOWS[1:]:
            a = max(a, "2013-01-04")
            if a >= z: continue
            cells = []
            for n in regs:
                nav = C.portfolio(members, {c: C.daily(res[c][n]) for c in members}, (a, z)); v = list(nav.values())
                peak, mdd = 1.0, 0.0
                for x in v: peak = max(peak, x); mdd = min(mdd, x/peak - 1)
                cells.append(f"{(v[-1]-1)*100:+6.1f}% / {mdd*100:5.1f}%")
            print(f"    {wn:<20} " + " ｜ ".join(cells))
if __name__ == "__main__":
    regime_stats()
    with Pool(8) as p: E = dict(p.map(etf_job, GA + GB))
    report("1) ETF 自身历史", E, ("2010-01-01", X.END)); report("1') ETF 自身历史，统一从 2020 年起", E, ("2020-01-02", X.END))
    with Pool(8) as p: I = dict(p.map(idx_job, GA + GB))
    report("2) 跟踪指数延长", I, ("2013-01-04", X.END)); report("2') 跟踪指数延长，只看选组样本外的 2013–2019", I, ("2013-01-04", "2019-12-31"))
    stages(I)
