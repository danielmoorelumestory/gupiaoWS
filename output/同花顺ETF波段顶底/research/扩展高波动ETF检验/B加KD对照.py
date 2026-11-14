"""B 方案加 K−D。事前写定（跑之前）：
- B：牛市 且（MACD 金叉 或 当天收盘站上10日线）→ 次日开盘买；卖出 = 死叉，或 MACD 空头时收盘跌破10日线，当天尾盘卖。
- B+KD买：B 的买入信号当天还要 K−D ≥ 5.3（KDJ 9,3,3，复权高低收；阈值同此前研究）才买；卖出同 B。
- B+KD买卖：买入同 B+KD买；卖出再加一条：MACD 空头时 K < D（KDJ 死叉状态）也当天尾盘卖。
- 对照：现行（只认金叉）、C（站上后确认再买）。熊市不开新仓；买入当天触发卖出则次日开盘卖；20bp 往返成本。
- 样本：全部已知高波动 40 只；汇总用平均值；差值 95% 区间 ETF 聚类 bootstrap 1000 次（种子 20261113）；另报 2025 年起。"""
import math, random, statistics
from multiprocessing import Pool
import R2站上10日线买对照 as T, run_extended as X
G = T.G; C = T.C
src = G.src.replace("def simulate_rg(", "def simulate_kd(", 1)
for old, new in [
    ('    def exit_sig(i):\n', '    mlong=data["mlong"];kd=data["_kd"]\n    def exit_sig(i):\n        if config.get("ma10x") and not mlong[i] and (below[i] or (config.get("kdx") and kd[i] < 0)): return True\n'),
    ('return config["bullin"]=="ANY" or gold[i]', 'return (config["bullin"]=="ANY" or gold[i] or (config.get("ma10in") and i>0 and above[i] and not above[i-1]) or (config.get("ma10conf") and i>1 and above[i] and above[i-1] and not above[i-2])) and (not config.get("kdin") or kd[i] >= 5.3)')]:
    assert src.count(old) == 1; src = src.replace(old, new)
_ns = dict(vars(G.engine)); exec(src, _ns); simulate_kd = _ns["simulate_kd"]
BASE = T.BASE; Bc = {**BASE, "ma10in": True, "ma10x": True}
VAR = {"现行": BASE, "B": Bc, "B+KD买": {**Bc, "kdin": True}, "B+KD买卖": {**Bc, "kdin": True, "kdx": True}, "C确认后买": {**BASE, "ma10conf": True, "ma10x": True}}
KEYS = ["MACD", *VAR, "HOLD"]
WINDOWS = X.WINDOWS + [("2025 年起", "2025-01-02", "2026-11-10")]
def run(job):
    key, w = job; out = {}
    for code, d in T.M.PANEL.items():
        if key == "MACD": r = C.simulate_cs(d, C.grid[C.MACD_KEY], w, 20)
        elif key == "HOLD": r = C.engine.simulate(d, C.HOLD, w, 20)
        else: r = simulate_kd(d, VAR[key], w, 20)
        if r: out[code] = r["metric"]
    return key, w, out
def check(w):
    return sum((T.simulate_rgm(d, T.VAR[k1], w, 20) or {}).get("metric") != (simulate_kd(d, VAR[k2], w, 20) or {}).get("metric")
               for d in T.M.PANEL.values() for k1, k2 in (("现行", "现行"), ("B同A加空头破10日卖", "B")))
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=T.init) as p:
        assert sum(p.map(check, [("1900-01-01", "2026-11-10")])) == 0; print("自检通过：现行、B 与之前一致")
        res = p.map(run, [(k, (a, z)) for k in KEYS for _, a, z in WINDOWS])
    R = {(k, w): o for k, w, o in res}
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m["cagr"] is not None and m["mdd"] < 0 else None
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    for wn, a, z in WINDOWS:
        w = (a, z); base = R[("现行", w)]; ms = [base[c] for c in GRP if c in base]
        if len(ms) < 3: continue
        use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
        print(f"\n## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
        for k in KEYS:
            o = R[(k, w)]; cs = [c for c in GRP if c in o and o[c][use] is not None]
            cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
            line = f"  {k:<8} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  胜率 {mean(o[c]['wr'] for c in cs if o[c]['wr'] is not None)*100:4.1f}%  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:4.1f}%  n={len(cs)}"
            for ref in (("现行", "B") if k.startswith("B+") else ()):
                bo = R[(ref, w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261113)
                S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                dd = sorted(mean(o[c]["mdd"] for c in s) - mean(bo[c]["mdd"] for c in s) for s in S)
                line += f"\n             较{ref}：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  回撤差 95%[{dd[25]*100:+.1f},{dd[974]*100:+.1f}]（正 = 更浅）  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                if wn == "全历史":
                    ex = [c for c in pc if c != "P588170"]
                    line += f"  去掉588170后收益差 {(mean(o[c][use] for c in ex) - mean(bo[c][use] for c in ex))*100:+.2f}"
            print(line)
