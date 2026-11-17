"""用户提议（2026-11-16）：择时比值的分母（红利 510880）改成多只红利 ETF 的均值，或 红利+红利低波 均值，看能否更平滑。事前写定（跑之前）：
分母（腾讯后复权，等权每日再平衡合成；成员上市满 20 个交易日后才计入，之前按已有成员平均）：
- D0 现行：510880（研究数据）；D0h：510880 腾讯后复权（口径核对，应与 D0 几乎一样）。
- 红利4：510880、515080 中证红利招商、515180 红利易方达、159905 深红利工银。
- 红利+低波：510880、512890 红利低波华泰。
- 红利7：上面 4 只 + 512890、515100 红利低波100、515450 红利低波50。
分子不变：A 组择时用 创业板 159915；B 组用 沪深300 指数；均为 高于 20 日均线 为牛。
注意：515080/515180/512890/515100/515450 均 2019–2020 年才上市，2019 年以前各方案几乎等于 现行（159905 除外）。主要看 2020 年起。
测试：A 组 14 只 Y1、B 组 10 只 只认金叉；数据两套（ETF 自身、跟踪指数延长 2013 起）。
另看信号本身：每年切换次数（是否更平滑）、与现行同向天数。
合格（事先定）：2020 年起 ETF 版与指数版两套的组合卡玛都高于现行，且每年切换次数不多于现行。
单边 0.1% 成本。历史统计，不构成投资建议。
事后修正（2026-11-16，Codex 复测发现）：「单只平均」改为窗口内以 1 重新累计（C.window_metrics），原来直接截取全历史净值、窗口前盈亏混入；组合指标与合格判定不受影响。"""
import importlib.util, json, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import regime_multi as RM, tencent_hfq as TH
FG = json.load(open("全量逐年优秀AB_最终分组.json")); GA, GB = FG["A"], FG["B"]
SETS = {"D0h": ["sh510880"], "红利4": ["sh510880", "sh515080", "sh515180", "sz159905"], "红利+低波": ["sh510880", "sh512890"],
        "红利7": ["sh510880", "sh515080", "sh515180", "sz159905", "sh512890", "sh515100", "sh515450"]}
def composite(members):
    ser = {m: TH.load(m) for m in members}; first = {m: sorted(s)[20] for m, s in ser.items()}
    days = sorted(ser["sh510880"]); nav, out = 1.0, {days[0]: 1.0}
    for a, b in zip(days, days[1:]):
        rs = [ser[m][b]/ser[m][a] - 1 for m in members if a >= first[m] and a in ser[m] and b in ser[m]]
        if not rs: rs = [ser["sh510880"][b]/ser["sh510880"][a] - 1]
        nav *= 1 + statistics.mean(rs); out[b] = nav
    return out
def signals():
    cyb = RM.load_new("159915"); hs = RM.index_series("sh000300"); den = {"D0": RM.load_new("510880"), **{k: composite(v) for k, v in SETS.items()}}
    out = {}
    for k, d in den.items():
        out[f"R2:{k}"] = RM.ma_state(RM.ratio(cyb, d), 20); out[f"H1:{k}"] = RM.ma_state(RM.ratio(hs, d), 20)
    return out
KEYS = ["D0", "D0h", "红利4", "红利+低波", "红利7"]
LABEL = {"D0": "现行 510880", "D0h": "510880 后复权", "红利4": "红利4只均值", "红利+低波": "红利+红利低波", "红利7": "红利7只均值"}
def sim(d, plan):
    out = {}
    for k in KEYS:
        n = ("R2:" if plan == "A" else "H1:") + k
        r = C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": n}, C.FULL, 20, retain=True) if plan == "A" else C.K.simulate_kd(d, {**C.T.BASE, "N": n}, C.FULL, 20, retain=True)
        out[k] = {p["date"]: p["nav"] for p in r["nav"]}
    return out
def attach(d):
    for n, s in SIG.items(): d["reg"][n] = RM.last_known(s, d["dates"])
def etf_job(code):
    C.init(); d = C.T.M.PANEL[[k for k in C.T.M.PANEL if k[1:] == code][0]]; attach(d)
    return code, sim(d, "A" if code in GA else "B")
def idx_job(code):
    if code not in X.INDEX: return etf_job(code)
    p880 = RM.load_new("510880"); r2 = RM.ma_state(RM.ratio(RM.load_new("159915"), p880), 20); h1 = RM.ma_state(RM.ratio(RM.index_series("sh000300"), p880), 20)
    d = X.entry(code, X.index_rows(X.INDEX[code]), r2, h1); attach(d)
    return code, sim(d, "A" if code in GA else "B")
SIG = signals()
def report(title, res, W, keep):
    print(f"\n## {title}（{W[0]}～{W[1]}）")
    for g, members in (("A 组 Y1·创业板择时", GA), ("B 组 只认金叉·沪深300择时", GB)):
        print(f"  [{g}，{len(members)} 只]")
        for k in KEYS:
            m = C.metrics(C.portfolio(members, {c: C.daily(res[c][k]) for c in members}, W))
            single = statistics.mean(C.window_metrics(res[c][k], W)["cal"] for c in members)
            print(f"    {LABEL[k]:<12} 组合 年化 {m['cagr']*100:5.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:4.2f} 赚钱年 {m['pos']}/{len(m['years'])} 最差年 {m['worst']*100:+5.1f}% ｜ 单只平均卡玛 {single:4.2f}")
            keep[(g, k)] = m["cal"]
if __name__ == "__main__":
    print("## 择时信号本身（2020-01-02～2026-11-10）")
    flips = {}
    for side in ("R2", "H1"):
        base = SIG[f"{side}:D0"]
        for k in KEYS:
            s = SIG[f"{side}:{k}"]; ds = [d for d in sorted(s) if "2020-01-02" <= d <= X.END and s[d] is not None]; v = [s[d] for d in ds]
            f = sum(v[i] != v[i-1] for i in range(1, len(v))) / (len(v)/244); flips[(side, k)] = f
            print(f"  {'创业板' if side == 'R2' else '沪深300'}÷{LABEL[k]:<12} 牛市天数 {sum(v)/len(v)*100:4.1f}%  每年切换 {f:4.1f} 次  与现行同向 {sum(s[d] == base.get(d) for d in ds)/len(ds)*100:5.1f}%")
    with Pool(8) as p: E = dict(p.map(etf_job, GA + GB))
    kE = {}; report("1) ETF 自身历史，2020 年起", E, ("2020-01-02", X.END), kE); report("1') ETF 自身全历史", E, ("1900-01-01", X.END), {})
    with Pool(8) as p: I = dict(p.map(idx_job, GA + GB))
    kI = {}; report("2) 跟踪指数延长，2020 年起", I, ("2020-01-02", X.END), kI); report("2') 跟踪指数延长，2013 年起", I, ("2013-01-04", X.END), {})
    print("\n## 合格判定（2020 年起两套组合卡玛都高于现行，且每年切换不多于现行）")
    for g, side in (("A 组 Y1·创业板择时", "R2"), ("B 组 只认金叉·沪深300择时", "H1")):
        ok = [k for k in KEYS[2:] if kE[(g, k)] > kE[(g, "D0")] and kI[(g, k)] > kI[(g, "D0")] and flips[(side, k)] <= flips[(side, "D0")]]
        print(f"  {g}：{'、'.join(LABEL[k] for k in ok) if ok else '无'}")
