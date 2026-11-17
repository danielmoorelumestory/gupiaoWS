"""用户提议（2026-11-16）：择时比值的均线从 20 日改成 18 日。事前写定（跑之前）：
主比较：18 日 vs 现行 20 日。为判断是否只是参数巧合，另跑 14/16/18/20/22/25 日的敏感性（只作参考，不据此挑最优）。
A 组 14 只：Y1 + 创业板÷红利(510880 研究数据) 高于 N 日均线；B 组 10 只：只认金叉 + 沪深300÷红利 高于 N 日均线。
数据两套：ETF 自身（2020 年起、全历史）；跟踪指数延长（2020 年起、2013 年起）。
合格（事先定）：18 日在 2020 年起 ETF 版与指数版的组合卡玛都高于 20 日，且 2013 年起指数版不低于 20 日；
并且 16 日、20 日附近不是断崖（相邻天数卡玛不出现大起大落），否则视为参数巧合。
单边 0.1% 成本。历史统计，不构成投资建议。
事后修正（2026-11-16，Codex 复测发现）：「单只平均」改为窗口内以 1 重新累计（C.window_metrics），原来直接截取全历史净值、窗口前盈亏混入；组合指标与合格判定不受影响。"""
import importlib.util, json, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import regime_multi as RM
FG = json.load(open("全量逐年优秀AB_最终分组.json")); GA, GB = FG["A"], FG["B"]
NS = [14, 16, 18, 20, 22, 25]
p880 = RM.load_new("510880"); R2R = RM.ratio(RM.load_new("159915"), p880); H1R = RM.ratio(RM.index_series("sh000300"), p880)
SIG = {**{f"R2-{n}": RM.ma_state(R2R, n) for n in NS}, **{f"H1-{n}": RM.ma_state(H1R, n) for n in NS}}
def sim(d, plan):
    for k, s in SIG.items(): d["reg"][k] = RM.last_known(s, d["dates"])
    out = {}
    for n in NS:
        key = f"{'R2' if plan == 'A' else 'H1'}-{n}"
        r = C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": key}, C.FULL, 20, retain=True) if plan == "A" else C.K.simulate_kd(d, {**C.T.BASE, "N": key}, C.FULL, 20, retain=True)
        out[n] = {p["date"]: p["nav"] for p in r["nav"]}
    return out
def etf_job(code):
    C.init(); d = C.T.M.PANEL[[k for k in C.T.M.PANEL if k[1:] == code][0]]
    return code, sim(d, "A" if code in GA else "B")
def idx_job(code):
    if code not in X.INDEX: return etf_job(code)
    r2 = RM.ma_state(R2R, 20); h1 = RM.ma_state(H1R, 20)
    return code, sim(X.entry(code, X.index_rows(X.INDEX[code]), r2, h1), "A" if code in GA else "B")
def report(title, res, W, keep):
    print(f"\n## {title}（{W[0]}～{W[1]}）")
    for g, members in (("A 组 Y1·创业板择时", GA), ("B 组 只认金叉·沪深300择时", GB)):
        print(f"  [{g}]")
        for n in NS:
            m = C.metrics(C.portfolio(members, {c: C.daily(res[c][n]) for c in members}, W))
            single = statistics.mean(C.window_metrics(res[c][n], W)["cal"] for c in members)
            print(f"    {n:2d} 日{'（现行）' if n == 20 else '      '} 组合 年化 {m['cagr']*100:5.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:4.2f} 赚钱年 {m['pos']}/{len(m['years'])} 最差年 {m['worst']*100:+5.1f}% ｜ 单只平均卡玛 {single:4.2f}")
            keep[(g, n)] = m["cal"]
if __name__ == "__main__":
    print("## 择时信号本身（2020-01-02～2026-11-10）")
    for side, name in (("R2", "创业板÷红利"), ("H1", "沪深300÷红利")):
        base = SIG[f"{side}-20"]
        for n in NS:
            s = SIG[f"{side}-{n}"]; ds = [d for d in sorted(s) if "2020-01-02" <= d <= X.END and s[d] is not None]; v = [s[d] for d in ds]
            print(f"  {name} {n:2d} 日：牛市天数 {sum(v)/len(v)*100:4.1f}%  每年切换 {sum(v[i] != v[i-1] for i in range(1, len(v)))/(len(v)/244):4.1f} 次  与 20 日同向 {sum(s[d] == base[d] for d in ds)/len(ds)*100:5.1f}%")
    with Pool(8) as p: E = dict(p.map(etf_job, GA + GB))
    kE = {}; report("1) ETF 自身，2020 年起", E, ("2020-01-02", X.END), kE); report("1') ETF 自身，全历史", E, ("1900-01-01", X.END), {})
    with Pool(8) as p: I = dict(p.map(idx_job, GA + GB))
    kI = {}; report("2) 跟踪指数延长，2020 年起", I, ("2020-01-02", X.END), kI); kL = {}; report("2') 跟踪指数延长，2013 年起", I, ("2013-01-04", X.END), kL)
    print("\n## 合格判定（18 日 vs 20 日）")
    for g in ("A 组 Y1·创业板择时", "B 组 只认金叉·沪深300择时"):
        ok = kE[(g, 18)] > kE[(g, 20)] and kI[(g, 18)] > kI[(g, 20)] and kL[(g, 18)] >= kL[(g, 20)]
        print(f"  {g}：{'合格' if ok else '不合格'}（ETF2020 {kE[(g,18)]:.2f} vs {kE[(g,20)]:.2f}；指数2020 {kI[(g,18)]:.2f} vs {kI[(g,20)]:.2f}；指数2013 {kL[(g,18)]:.2f} vs {kL[(g,20)]:.2f}）")
