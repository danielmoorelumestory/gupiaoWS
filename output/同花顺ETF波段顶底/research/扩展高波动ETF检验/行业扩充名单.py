"""用户同意（2026-11-18）：补齐面板缺失的活跃行业（汽车、煤炭、白酒、家电、新能源车；无纯保险 ETF 故不补），再按「只加高波动」规则给出扩充名单。事前写定（跑之前）：
新增数据：腾讯后复权日线（OHLC 均为后复权，adjusted_close=close，份额/分红因子按 1/0），选各行业当前成交额最大者：
  汽车 516110、煤炭 515220、酒 512690、家电 159996、新能源车 515030。用 指数延长回测.entry 构建与引擎相同的指标（MACD、10/20 日线、KD、择时）。
候选池：面板 79 只 + 上述 5 只，按日收益相关 ≥0.93 连锁去重（同组含现行 A/B 成员则只留成员，否则留历史最长）。
扩充规则（与 全行业覆盖对照.py 的「只加高波动」一致）：非现行成员中全历史年化波动 ≥31% 的加入；策略按 2021 年底以前卡玛选 A/B（2021 年前不足 2 年数据的用 A）。
现行 A/B 成员保持原策略。报告：完整扩充名单（行业、波动、策略、2020 年起单独表现），以及 现行 24 / 扩充后 的每年等权组合收益与 2020 年起指标。
另报：若把新增 5 只全部加入（不论波动）的版本。历史统计，不构成投资建议。"""
import importlib.util, json, gzip, math, statistics, itertools
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("D", "双择时并行对照.py"); D = importlib.util.module_from_spec(sp); sp.loader.exec_module(D)
C, X, GA, GB = D.C, D.X, D.GA, D.GB
import regime_multi as RM, tencent_hfq as T
NEW = {"516110": ("sh516110", "汽车国泰", "汽车"), "515220": ("sh515220", "煤炭国泰", "周期资源"), "512690": ("sh512690", "酒鹏华", "大消费"),
       "159996": ("sz159996", "家电国泰", "大消费"), "515030": ("sh515030", "新能源车华夏", "高端制造")}
def _job(k): return D.job(k)
def new_job(code):
    sym = NEW[code][0]; T.load(sym)
    raw = json.loads(gzip.decompress((T.RAW / f"{sym}-tencent-hfq.json.gz").read_bytes()))
    rows = [{"date": x[0], "open": x[1], "high": x[3], "low": x[4], "close": x[2], "adjusted_close": x[2], "share_factor": "1", "cumulative_cash": "0"} for x in raw if x[0] <= X.END]
    p880 = RM.load_new("510880"); r2 = RM.ma_state(RM.ratio(RM.load_new("159915"), p880), 20); h1 = RM.ma_state(RM.ratio(RM.index_series("sh000300"), p880), 20)
    d = X.entry(code, rows, r2, h1)
    out = {}
    for pl in ("A", "B"):
        r = X.sim(d, pl); out["单用" + pl] = ({x["date"]: x["nav"] for x in r["nav"]}, {})
    c = [float(r["adjusted_close"]) for r in rows]
    out["vol"] = statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    out["_rows"] = rows
    return code, out
WF, W20, PRE = ("1900-01-01", X.END), ("2020-01-02", X.END), ("1900-01-01", "2021-12-31")
if __name__ == "__main__":
    C.init(); P = {k[1:]: v for k, v in C.T.M.PANEL.items()}
    with Pool(8) as p: res = dict(p.map(_job, list(C.T.M.PANEL))); res.update(dict(p.map(new_job, list(NEW))))
    name = {c: P[c]["item"]["name"].replace("ETF", "") for c in P}; grp = {c: "/".join(P[c]["item"]["groups"]) or "未分组" for c in P}
    rows = {c: P[c]["rows"] for c in P}
    for c, (s, n, g) in NEW.items(): name[c] = n + "(新补)"; grp[c] = g; rows[c] = res[c].pop("_rows")
    R = {}
    for c, rw in rows.items():
        a = [float(r["adjusted_close"]) for r in rw]; R[c] = {rw[i]["date"]: math.log(a[i]/a[i-1]) for i in range(1, len(a)) if a[i-1] > 0}
    par = {c: c for c in R}
    def f(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    for a, b in itertools.combinations(R, 2):
        cm = [t for t in R[a] if t in R[b]]
        if len(cm) >= 120 and statistics.correlation([R[a][t] for t in cm], [R[b][t] for t in cm]) >= 0.93: par[f(a)] = f(b)
    G = {}
    for c in R: G.setdefault(f(c), []).append(c)
    AB = set(GA) | set(GB); keep = []
    for g in G.values():
        mem = [c for c in g if c in AB]; keep += mem if mem else [max(g, key=lambda c: len(rows[c]))]
    for c in NEW:
        g = G[f(c)]
        if len(g) > 1: print(f"  新补 {c} {name[c]} 与 {[x + name[x] for x in g if x != c]} 相关≥0.93 归为一组，保留 {[x for x in g if x in keep]}")
    def choose(c):
        ma, mb = C.window_metrics(res[c]["单用A"][0], PRE), C.window_metrics(res[c]["单用B"][0], PRE)
        if not ma or not mb or sum(1 for t in res[c]["单用A"][0] if t <= "2021-12-31") < 488: return "A"
        return "A" if ma["cal"] >= mb["cal"] else "B"
    add = [c for c in keep if c not in AB and res[c]["单用A"][0]]
    hv = [c for c in add if res[c]["vol"] >= 0.31]
    s = lambda m: f"年化{m['cagr']*100:6.1f}% 回撤{m['mdd']*100:6.1f}% 卡玛{m['cal']:5.2f}" if m else "—"
    print("\n## 新补 5 只（2020 年起单独表现）")
    for c in NEW:
        print(f"  {c} {name[c]:<14} 波动{res[c]['vol']*100:3.0f}% 上市{rows[c][0]['date']} ｜A: {s(C.window_metrics(res[c]['单用A'][0], W20))} ｜B: {s(C.window_metrics(res[c]['单用B'][0], W20))} ｜按2021前选{choose(c)} ｜{'入选(高波动)' if c in hv else ('不入选(波动<31%)' if c in add else '去重剔除')}")
    print(f"\n## 扩充名单：现行 {len(AB)} 只 + 新增高波动 {len(hv)} 只 = {len(AB) + len(hv)} 只")
    print("  ### 新增（按行业）")
    for c in sorted(hv, key=lambda c: grp[c]):
        pl = choose(c); m = C.window_metrics(res[c]["单用" + pl][0], W20)
        print(f"  {c} {name[c]:<14} [{grp[c]}] 波动{res[c]['vol']*100:3.0f}% 上市{rows[c][0]['date']} 策略{pl} ｜2020起 {s(m)}")
    print("  ### 现行保留")
    for c in sorted(AB, key=lambda c: (c not in GA, c)): print(f"  {c} {name[c]:<14} 策略{'A' if c in GA else 'B'}")
    cur = {c: ("单用A" if c in GA else "单用B") for c in AB}
    PORT = {"现行 A/B 24 只": cur, "扩充·加高波动": {**cur, **{c: "单用" + choose(c) for c in hv}},
            "扩充·加高波动+新补5只全加": {**cur, **{c: "单用" + choose(c) for c in hv}, **{c: "单用" + choose(c) for c in NEW if c in add}},
            "只看新增高波动": {c: "单用" + choose(c) for c in hv}}
    out = {n: {w[0]: C.metrics(C.portfolio(list(m), {c: C.daily(res[c][k][0]) for c, k in m.items()}, w)) for w in (WF, W20)} for n, m in PORT.items()}
    yrs = sorted(out["现行 A/B 24 只"]["1900-01-01"]["years"])
    print("\n## 每年等权组合收益（%）")
    print("  " + f"{'':<22}" + "".join(f"{y[2:]:>5}" for y in yrs) + " ｜只数 亏损年 <5%年 最差年 全期年化 回撤 卡玛 ｜2020起 年化 回撤 卡玛")
    for n, m in out.items():
        a, b = m["1900-01-01"], m["2020-01-02"]; v = [a["years"].get(y) for y in yrs]; vv = [x for x in v if x is not None]
        print("  " + f"{n:<22}" + "".join(f"{x*100:5.0f}" if x is not None else "    -" for x in v) + f" ｜{len(PORT[n]):4d} {sum(x<0 for x in vv):4d} {sum(x<0.05 for x in vv):5d} {min(vv)*100:+6.1f} {a['cagr']*100:6.1f}% {a['mdd']*100:6.1f}% {a['cal']:4.2f} ｜ {b['cagr']*100:5.1f}% {b['mdd']*100:6.1f}% {b['cal']:4.2f}")
