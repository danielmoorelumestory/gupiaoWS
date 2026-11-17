"""两个优选分组分开复测，并与一直持有、纯 MACD 金叉对照。事前写定（跑之前）：
- A 组 MACD优秀 20 只（MACD优秀清单_20只.json），择时 R2 = 创业板÷红利。
- B 组 沪深300择时优选 13 只（沪深300择时优选_全部结果.json 中 good），择时 H1 = 沪深300÷红利。
方案：一直持有（窗口首日开盘买入、持有到末日，前复权含分红，买卖各 0.1%）；纯MACD（不择时，金叉次日开盘买、死叉尾盘卖）；
现行（择时牛市金叉买、熊市不开新仓、死叉尾盘卖）；Y1 / Y11 / Y12（B+KD10 买入，死叉或择时熊市跌破 N 日线卖；N=10/11/12，买卖同一条线）。
窗口与引擎一致（上市后第 121 根起至 2026-11-10，另报分段）。汇总用平均值；另报主题去重（相关≥0.93，保留历史最长）。
两组都是用全历史结果挑出来的（A 组按纯 MACD 跑赢持有，B 组按 现行·H1 跑赢 现行·R2），组内比较偏乐观，只作描述。
追加（2026-11-15，用户要求）：Y1不择时 = Y1 买卖规则但择时恒为牛（熊市也开新仓、不触发熊市破线卖，只剩死叉卖）。
改用 11/12 日线的条件（事先定）：两组的全历史卡玛平均与去重卡玛平均都高于 Y1。bootstrap 种子 20261115。"""
import math, random, statistics, itertools, json
from multiprocessing import Pool
import importlib.util, run_extended as X, regime_multi as RM
def load(name, path):
    sp = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
Z = load("Z", "低波动沪深300择时对照.py"); Q = load("Q", "Y1均线周期11_12对照.py")
T = Z.T; K = Z.K; Y = Z.Y; FULL = ("1900-01-01", "2026-11-10"); WINDOWS = K.WINDOWS
A = [i["code"] for i in json.load(open("MACD优秀清单_20只.json"))["items"]]
B = [r["code"] for r in json.load(open("沪深300择时优选_全部结果.json")) if r["good"]]
NAMES = {**{i["code"]: i["name"] for i in json.load(open("MACD优秀清单_20只.json"))["items"]}, **{r["code"]: r["name"] for r in json.load(open("沪深300择时优选_全部结果.json"))}}
NAMES.update({"515000": "科技ETF华宝", "512720": "计算机ETF国泰"})
def plan(tm):
    return {"一直持有": ("HOLD",), "纯MACD": ("KD", "ALL"), "现行": ("KD", tm), "Y1不择时": ("Y", "ALL", 10), "Y1": ("Y", tm, 10), "Y11": ("Y", tm, 11), "Y12": ("Y", tm, 12)}
GROUPS = {"A": (A, "R2-20", "MACD优秀 · 创业板÷红利择时"), "B": (B, "H1", "沪深300择时优选 · 沪深300÷红利择时")}
AB = {}
def init():
    Z.init()
    for code, d in T.M.PANEL.items():
        if code[1:] in A or code[1:] in B: AB[code] = {n: Q.ab(d["rows"], n) for n in (10, 11, 12)}
def hold(d, w):
    rows = d["rows"]; idx = [i for i, x in enumerate(d["dates"]) if i >= 120 and w[0] <= x <= w[1]]
    if len(idx) < 2: return None
    f = [float(r["adjusted_close"])/float(r["close"]) for r in rows]; c = [float(r["adjusted_close"]) for r in rows]
    a = idx[0]; nav = [c[i]/(float(rows[a]["open"])*f[a])*.999 for i in idx]; nav[-1] *= .999
    peak, mdd = 0, 0
    for v in nav: peak = max(peak, v); mdd = min(mdd, v/peak-1)
    yrs = len(idx)/244; tot = nav[-1]-1
    return {"cagr": (nav[-1]**(1/yrs)-1) if yrs >= 1 else None, "total_return": tot, "mdd": mdd, "entries": 1, "wr": None, "time_exposure": 1.0, "years": yrs}
def run(job):
    g, key, w = job; codes, tm, _ = GROUPS[g]; p = plan(tm)[key]; out = {}
    for code, d in T.M.PANEL.items():
        if code[1:] not in codes: continue
        if p[0] == "HOLD": m = hold(d, w)
        elif p[0] == "KD":
            r = K.simulate_kd(d, {**T.BASE, "N": p[1]}, w, 20); m = r and r["metric"]
        else:
            n = p[2]; r = Y.simulate_y({**d, "above": AB[code][n][0], "below": AB[code][n][1]}, {**Y.VAR["Y1"], "N": p[1]}, w, 20); m = r and r["metric"]
        if m: out[code] = m
    return g, key, w, out
def check(_):
    bad = 0
    for code, d in T.M.PANEL.items():
        if code in AB: bad += (Y.simulate_y(d, Y.VAR["Y1"], FULL, 20) or {}).get("metric") != (Y.simulate_y({**d, "above": AB[code][10][0], "below": AB[code][10][1]}, {**Y.VAR["Y1"], "N": "R2-20"}, FULL, 20) or {}).get("metric")
    return bad
if __name__ == "__main__":
    pool, new, audit = X.build(); rows = {**{"P"+k: v["rows"] for k, v in pool.items()}, **{"N"+k: v["rows"] for k, v in new.items()}}
    def key_of(c): return "P"+c if "P"+c in rows else ("N"+c if "N"+c in rows else None)
    def lr(rs):
        s = RM.series_from_rows(rs); ds = sorted(s); return {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
    def dedup(G):
        LR = {g: lr(rows[g]) for g in G}; parent = {g: g for g in G}
        def find(a):
            while parent[a] != a: a = parent[a]
            return a
        for a, b in itertools.combinations(G, 2):
            cc = [x for x in LR[a] if x in LR[b]]
            if len(cc) >= 120 and statistics.correlation([LR[a][x] for x in cc], [LR[b][x] for x in cc]) >= .93: parent[find(a)] = find(b)
        gs = {}
        for g in G: gs.setdefault(find(g), []).append(g)
        return [max(g, key=lambda c: len(rows[c])) for g in gs.values()], [g for g in gs.values() if len(g) > 1]
    jobs = [(g, k, (a, z)) for g in GROUPS for k in plan("x") for _, a, z in WINDOWS]
    with Pool(8, initializer=init) as p:
        assert p.map(check, [0])[0] == 0; print("自检通过：Y1 10 日线重算一致")
        res = p.map(run, jobs)
    R = {(g, k, w): o for g, k, w, o in res}
    def mean(it):
        v = list(it); return statistics.mean(v) if v else float("nan")
    cal = lambda m: m["cagr"]/abs(m["mdd"]) if m and m["cagr"] is not None and m["mdd"] < 0 else None
    KEYS = list(plan("x")); summary = {}
    for g, (codes, tm, title) in GROUPS.items():
        G = [key_of(c) for c in codes]; assert None not in G, codes
        DD, merged = dedup(G)
        print(f"\n\n################ {title}：{len(G)} 只；去重后 {len(DD)} 只（合并：{'；'.join(' '.join(c[1:] for c in m) for m in merged) or '无'}）")
        for gname, grp, wins in (("全部", G, WINDOWS), ("去重", DD, WINDOWS[:1])):
            print(f"\n######## {gname} {len(grp)} 只")
            for wn, a, z in wins:
                w = (a, z); ms = [R[(g, "纯MACD", w)][c] for c in grp if c in R[(g, "纯MACD", w)]]
                if len(ms) < 3: continue
                use = "cagr" if sum(m["cagr"] is not None for m in ms) >= max(3, len(ms)//2) else "total_return"
                print(f"## {wn}（{'年化' if use=='cagr' else '累计'}平均）")
                for k in KEYS:
                    o = R[(g, k, w)]; cs = [c for c in grp if c in o and o[c][use] is not None]
                    cl = [x for x in (cal(o[c]) for c in cs) if x is not None]
                    if wn == "全历史": summary[(g, gname, k)] = mean(cl)
                    line = f"  {k:<5} {mean(o[c][use] for c in cs)*100:7.2f}%  回撤 {mean(o[c]['mdd'] for c in cs)*100:6.1f}%" + (f"  卡玛 {mean(cl):.3f}" if wn == "全历史" else "") + f"  买入次数 {mean(o[c]['entries'] for c in cs):5.1f}  持仓时间 {mean(o[c]['time_exposure'] for c in cs)*100:5.1f}%  n={len(cs)}"
                    for ref in (("一直持有", "纯MACD") if k not in ("一直持有", "纯MACD") else ()) + (("Y1",) if k == "Y1不择时" else ()) + (("Y1",) if k in ("Y11", "Y12") else ()):
                        bo = R[(g, ref, w)]; pc = [c for c in cs if c in bo and bo[c][use] is not None]; rnd = random.Random(20261115)
                        S = [[rnd.choice(pc) for _ in pc] for _ in range(1000)]
                        d = sorted(mean(o[c][use] for c in s) - mean(bo[c][use] for c in s) for s in S)
                        line += f"\n         较{ref}：收益差 95%[{d[25]*100:+.1f},{d[974]*100:+.1f}]{' ★' if d[25] > 0 else (' ✗' if d[974] < 0 else '')}  逐只胜 {sum(o[c][use] > bo[c][use] for c in pc)}/{len(pc)}"
                        if wn == "全历史":
                            pk = [c for c in pc if cal(o[c]) is not None and cal(bo[c]) is not None]
                            dc = sorted(mean(cal(o[c]) for c in s if c in pk) - mean(cal(bo[c]) for c in s if c in pk) for s in S)
                            line += f"  卡玛差 95%[{dc[25]:+.3f},{dc[974]:+.3f}]"
                    print(line)
        print(f"\n## 逐只全历史 年化/最大回撤")
        f = lambda m: f"{m['cagr']*100:6.1f}%/{m['mdd']*100:6.1f}%" if m and m["cagr"] is not None else "      —      "
        print("  " + " "*22 + "".join(f"{k:<15}" for k in KEYS))
        for c in G: print(f"  {c[1:]} {NAMES.get(c[1:], ''):<12}" + " ".join(f"{f(R[(g, k, FULL)].get(c))}" for k in KEYS))
    print("\n## 改用 11/12 日线判定（两组全部与去重卡玛都要高于 Y1）")
    for k in ("Y11", "Y12"):
        ok = all(summary[(g, n, k)] > summary[(g, n, "Y1")] for g in GROUPS for n in ("全部", "去重"))
        print(f"  {k}: " + "  ".join(f"{g}{n} {summary[(g, n, k)]:.3f}（Y1 {summary[(g, n, 'Y1')]:.3f}）" for g in GROUPS for n in ("全部", "去重")) + f" → {'改' if ok else '不改'}")
