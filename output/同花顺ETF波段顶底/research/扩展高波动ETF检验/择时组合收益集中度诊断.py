"""事后诊断（2026-11-16，用户问：择时组合是不是靠几波大涨拉高年化）。不改任何规则，只拆解收益来源。
数据与 指数延长回测.py 相同（有指数用指数，港股低波红利/纳指科技用 ETF）。
1. 组合按年：去掉最好的 1/2/3 年后的年化。
2. 按笔：每只成员把收益最大的 N 笔交易持仓期间收益置 0（当作那几段没赚到也没亏），重算组合年化/回撤。
3. 每只：最大 3 笔交易占全部盈利笔对数收益的比重、胜率、盈亏比。历史统计，不构成投资建议。"""
import importlib.util, json, math, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import regime_multi as RM
TEN = [m["code"] for m in json.load(open("AB组合_10只.json"))["members"]]
def run(code):
    if code in X.INDEX:
        p880 = RM.load_new("510880"); r2 = RM.ma_state(RM.ratio(RM.load_new("159915"), p880), 20); h1 = RM.ma_state(RM.ratio(RM.index_series("sh000300"), p880), 20)
        r = X.sim(X.entry(code, X.index_rows(X.INDEX[code]), r2, h1), C.PLAN[code])
    else:
        C.init(); d = C.T.M.PANEL[[k for k in C.T.M.PANEL if k[1:] == code][0]]
        r = C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": "R2-20"}, C.FULL, 20, retain=True) if C.PLAN[code] == "A" else C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True)
    return code, {p["date"]: p["nav"] for p in r["nav"]}, [(t["entry_date"], t["exit_date"], t["net_return"]) for t in r["trades"]]
if __name__ == "__main__":
    with Pool(8) as p: out = p.map(run, TEN)
    R = {c: C.daily(n) for c, n, _ in out}; TR = {c: t for c, _, t in out}
    nm = lambda c: f"{c}{C.NAMES[c]}"
    for W in (("2013-01-04", X.END), ("2020-01-02", X.END)):
        m = C.metrics(C.portfolio(TEN, R, W)); ys = m["years"]; n = len(C.portfolio(TEN, R, W)) / 244
        print(f"\n## {W[0][:4]} 年起：年化 {m['cagr']*100:.1f}%  回撤 {m['mdd']*100:.1f}%  逐年中位 {statistics.median(ys.values())*100:+.1f}%")
        srt = sorted(ys, key=ys.get, reverse=True)
        for k in (1, 2, 3):
            keep = [ys[y] for y in ys if y not in srt[:k]]
            print(f"  去掉最好 {k} 年（{'、'.join(srt[:k])}）：剩余 {len(keep)} 年年化 {(math.prod(1+v for v in keep)**(1/len(keep))-1)*100:.1f}%")
        for N in (1, 3, 5):
            R2 = {}
            for c in TEN:
                top = sorted(TR[c], key=lambda t: t[2], reverse=True)[:N]
                R2[c] = {d: (0.0 if any(a < d <= b for a, b, _ in top) else v) for d, v in R[c].items()}
            m2 = C.metrics(C.portfolio(TEN, R2, W))
            print(f"  每只去掉最赚的 {N} 笔：年化 {m2['cagr']*100:.1f}%  回撤 {m2['mdd']*100:.1f}%  赚钱年 {m2['pos']}/{len(m2['years'])}")
    print("\n## 每只成员（全程）：笔数、胜率、盈亏比、最大 3 笔占全部盈利（对数）比重、去掉最大 3 笔后累计")
    for c in TEN:
        rs = [t[2] for t in TR[c]]; w = [x for x in rs if x > 0]; l = [x for x in rs if x <= 0]
        top = sorted(rs, reverse=True)[:3]; share = sum(math.log1p(x) for x in top) / sum(math.log1p(x) for x in w)
        tot = math.prod(1+x for x in rs) - 1; rest = math.prod(1+x for x in sorted(rs, reverse=True)[3:]) - 1
        print(f"  {nm(c):<12} {len(rs):3d} 笔 胜率 {len(w)/len(rs)*100:4.0f}% 盈亏比 {statistics.mean(w)/-statistics.mean(l):4.1f}  最大3笔 {'/'.join(f'{x*100:+.0f}%' for x in top)} 占盈利 {share*100:3.0f}%  累计 {tot*100:+6.0f}% → 去掉后 {rest*100:+5.0f}%  起 {TR[c][0][0][:4]}")
