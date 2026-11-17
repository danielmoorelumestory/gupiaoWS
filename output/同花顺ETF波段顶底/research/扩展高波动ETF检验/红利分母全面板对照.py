"""用户要求（2026-11-16）：为排除「A/B 名单是在 510880 择时下挑出来的」选样偏向，用全部研究面板重测分母。事前写定（跑之前）：
样本：研究面板全部 ETF（C.T.M.PANEL，不经挑选）；另报高波动子集（全历史年化波动≥31%）。
方案：每只 ETF 都跑两套——Y1 + 创业板÷分母；只认金叉 + 沪深300÷分母（与是否在 A/B 组无关）。
分母：D0 现行 510880（研究数据）；红利+低波（510880+512890）；红利4（510880/515080/515180/159905）；红利7（再加 512890/515100/515450）。
  合成同 红利均值分母择时对照.py，但按 Codex 复测修正准入：成员上市第 20 个报价日收盘后计入（[19]）。
窗口：2020-01-02～2026-11-10（各分母在 2019 年以前几乎相同，不比较更早）；窗口内不足 244 个交易日的 ETF 不计。
单只指标：窗口内以 1 重新累计（C.window_metrics）的年化、最大回撤、卡玛。
比较：每个替代分母 vs D0，逐只差值（卡玛、年化）的平均与中位、替代更好的只数占比；平均差的 95% 区间用 bootstrap（按 ETF 重抽 5000 次，种子 20261116）。
  另报全部样本等权组合的卡玛。
判读（事先定）：区间跨 0 → 两者无显著差别（之前 A/B 组上的差距可视为选样偏向/噪音）；区间整体 <0 → 510880 确实更好；整体 >0 → 均值更好。
注意：ETF 之间高度相关，按只重抽会让区间偏窄，区间刚好不跨 0 时也要谨慎。单边 0.1% 成本。历史统计，不构成投资建议。"""
import importlib.util, json, math, random, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import regime_multi as RM, tencent_hfq as TH
W = ("2020-01-02", X.END)
SETS = {"红利+低波": ["sh510880", "sh512890"], "红利4": ["sh510880", "sh515080", "sh515180", "sz159905"],
        "红利7": ["sh510880", "sh515080", "sh515180", "sz159905", "sh512890", "sh515100", "sh515450"]}
KEYS = ["D0", *SETS]
def composite(members):
    ser = {m: TH.load(m) for m in members}; first = {m: sorted(s)[19] for m, s in ser.items()}
    days = sorted(ser["sh510880"]); nav, out = 1.0, {days[0]: 1.0}
    for a, b in zip(days, days[1:]):
        rs = [ser[m][b]/ser[m][a] - 1 for m in members if a >= first[m] and a in ser[m] and b in ser[m]]
        nav *= 1 + statistics.mean(rs or [ser["sh510880"][b]/ser["sh510880"][a] - 1]); out[b] = nav
    return out
cyb = RM.load_new("159915"); hs = RM.index_series("sh000300")
DEN = {"D0": RM.load_new("510880"), **{k: composite(v) for k, v in SETS.items()}}
SIG = {**{f"R2:{k}": RM.ma_state(RM.ratio(cyb, d), 20) for k, d in DEN.items()}, **{f"H1:{k}": RM.ma_state(RM.ratio(hs, d), 20) for k, d in DEN.items()}}
def job(key):
    C.init(); d = C.T.M.PANEL[key]
    for n, s in SIG.items(): d["reg"][n] = RM.last_known(s, d["dates"])
    c = [float(r["adjusted_close"]) for r in d["rows"]]; lr = [math.log(c[i]/c[i-1]) for i in range(1, len(c)) if c[i-1] > 0]
    vol = statistics.pstdev(lr) * math.sqrt(244) if len(lr) > 20 else 0
    out = {"vol": vol}
    for plan in ("Y1", "金叉"):
        for k in KEYS:
            if plan == "Y1": r = C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": f"R2:{k}"}, C.FULL, 20, retain=True)
            else: r = C.K.simulate_kd(d, {**C.T.BASE, "N": f"H1:{k}"}, C.FULL, 20, retain=True)
            nav = {p["date"]: p["nav"] for p in r["nav"]} if r else {}
            out[(plan, k)] = nav
    return key[1:], out
def boot(diffs, rng):
    ms = sorted(statistics.mean(rng.choices(diffs, k=len(diffs))) for _ in range(5000)); return ms[125], ms[4875]
if __name__ == "__main__":
    C.init(); keys = list(C.T.M.PANEL)
    with Pool(8) as p: res = dict(p.map(job, keys))
    for plan, title in (("Y1", "Y1 + 创业板÷分母"), ("金叉", "只认金叉 + 沪深300÷分母")):
        for sub, cond in (("全部面板", lambda v: True), ("高波动(≥31%)", lambda v: v >= 0.31)):
            codes = [c for c, o in res.items() if cond(o["vol"]) and sum(1 for d in o[(plan, "D0")] if d >= W[0]) >= 244]
            M = {c: {k: C.window_metrics(res[c][(plan, k)], W) for k in KEYS} for c in codes}
            codes = [c for c in codes if all(M[c][k] for k in KEYS)]
            print(f"\n## {title}｜{sub}：{len(codes)} 只（2020-01-02～2026-11-10）")
            R = {k: {c: C.daily(res[c][(plan, k)]) for c in codes} for k in KEYS}
            for k in KEYS:
                cal = [M[c][k]["cal"] for c in codes]; cg = [M[c][k]["cagr"] for c in codes]; pm = C.metrics(C.portfolio(codes, R[k], W))
                line = f"  {k:<8} 单只卡玛 平均 {statistics.mean(cal):5.2f} 中位 {statistics.median(cal):5.2f}｜单只年化 平均 {statistics.mean(cg)*100:5.1f}%｜全部等权组合 年化 {pm['cagr']*100:5.1f}% 回撤 {pm['mdd']*100:6.1f}% 卡玛 {pm['cal']:4.2f}"
                if k != "D0":
                    dc = [M[c][k]["cal"] - M[c]["D0"]["cal"] for c in codes]; dg = [M[c][k]["cagr"] - M[c]["D0"]["cagr"] for c in codes]
                    rng = random.Random(20261116); lo, hi = boot(dc, rng); glo, ghi = boot(dg, rng)
                    verdict = "无显著差别" if lo <= 0 <= hi else ("510880 更好" if hi < 0 else "均值更好")
                    line += f"\n           vs D0：卡玛差 平均 {statistics.mean(dc):+.3f} [{lo:+.3f}, {hi:+.3f}] 中位 {statistics.median(dc):+.3f}｜年化差 平均 {statistics.mean(dg)*100:+.2f}pp [{glo*100:+.2f}, {ghi*100:+.2f}]｜替代更好 {sum(x > 0 for x in dc)}/{len(dc)} 只 → {verdict}"
                print(line)
