"""用跟踪指数把 A/B 候选的回测往前延长（2026-11-16，用户认为 2020 年起太短）。事前写定（跑之前）：
数据：中证指数官网的指数日线（价格指数，不含分红，比 ETF 略保守）；指数发布日前的数据是指数公司回溯计算的，可能偏好看。
  没有开盘价的指数用前一日收盘当开盘、高低价取开收两者（KD 指标因此是近似值）。
  美股、港股（非中证）、国证、中华交易服务等取不到的，仍用 ETF 本身数据。
做法：有指数的候选，全程用指数跑各自方案（A：Y1·创业板择时；B：只认金叉·沪深300择时；单边 0.1% 成本，前 120 根预热）。
  择时：创业板择时 2011-12 以前无数据按牛市处理（与研究引擎一致），所以评估从 2013 年起。
检验：
1. 代理质量：ETF 上市后的同一时期，指数跑出的逐年收益与 ETF 跑出的逐年收益比较（相关、平均差）。
2. 10 只组合（AB组合_10只.json）与 A/B 全部 24 只，2013-01-04～2026-11-10 逐年、最大回撤、卡玛，以及同 10 只一直持有。
3. 样本外：按 AB组合构建_规则对照 的 R2 规则，只用 2019-12-31 以前（延长后）的数据挑 10 只，看 2020-01-02～2026-11-10；与 24 只等权、随机 10 只比较。
历史统计，不构成投资建议。"""
import json, gzip, math, random, statistics, itertools, urllib.request, importlib.util, sys
from pathlib import Path
from multiprocessing import Pool
def load(name, path):
    sp = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
C = load("C", "AB组合构建.py"); RC = load("RC", "AB组合构建_规则对照.py")
import regime_multi as RM, cs_common as CS, filter_common as FC, regime_common as RG
INDEX = {"513310": "931790", "588200": "000685", "159869": "930901", "159851": "930986", "513090": "930709", "512670": "399973", "516150": "930598",
         "562500": "H30590", "512480": "H30184", "588000": "000688", "159819": "930713", "159667": "931866", "516510": "930851", "159939": "000993",
         "159998": "930651", "512720": "930651", "159852": "930601", "515000": "931087", "515980": "931071", "515210": "930606", "515050": "931079",
         "159781": "931643", "513120": "931787", "512400": "000819"}
RAW = Path("data/index_raw"); RAW.mkdir(parents=True, exist_ok=True)
END = "2026-11-10"
def fetch(code):
    p = RAW / f"{code}.json.gz"
    if not p.exists():
        u = f"https://www.csindex.com.cn/csindex-home/perf/index-perf?indexCode={code}&startDate=20050101&endDate=20261110"
        p.write_bytes(gzip.compress(urllib.request.urlopen(u, timeout=60).read(), mtime=0))
    return json.loads(gzip.decompress(p.read_bytes()))["data"]
def index_rows(code):
    d = sorted(fetch(code), key=lambda x: x["tradeDate"])
    if len(d) > 1 and d[0]["tradeDate"] == "20050101": d = d[1:]   # 接口把起始日回显成一条
    rows, prev = [], None
    for x in d:
        day = f'{x["tradeDate"][:4]}-{x["tradeDate"][4:6]}-{x["tradeDate"][6:]}'
        if day > END or not x.get("close") or float(x["close"]) <= 0: continue   # 个别日子收盘为 0（数据错误）跳过
        c = float(x["close"]); o = float(x["open"]) if x.get("open") and float(x["open"]) > 0 else (prev or c)
        h = float(x["high"]) if x.get("high") and float(x["high"]) > 0 else max(o, c); l = float(x["low"]) if x.get("low") and float(x["low"]) > 0 else min(o, c)
        h, l = max(h, o, c), min(l, o, c)
        rows.append({"date": day, "open": str(o), "high": str(h), "low": str(l), "close": str(c), "adjusted_close": str(c), "share_factor": "1", "cumulative_cash": "0"})
        prev = c
    return rows
def entry(code, rows, r2, h1):
    d = CS.engine.prepare(rows, {"code": code}); FC.add_filters({code: d}, {y: None for y in range(2000, 2030)})  # 只需 KD；A20 过滤不用
    c = [float(r["adjusted_close"]) for r in rows]; d["below20"] = RG._ma_flag(c, 20, False)
    gold, dead = d["macds"][(12, 26, 9)]; s = False; ml = []
    for g, x in zip(gold, dead):
        s = True if g else (False if x else s); ml.append(s)
    d["mlong"] = ml
    d["reg"] = {"R2-20": RM.last_known(r2, d["dates"]), "H1": RM.last_known(h1, d["dates"]), "ALL": [True]*len(rows)}
    return d
def sim(d, plan, w=C.FULL):
    return C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": "R2-20"}, w, 20, retain=True) if plan == "A" else C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, w, 20, retain=True)
def work(code):
    p880 = RM.ratio_leg("510880"); r2 = RM.ma_state(RM.ratio(RM.ratio_leg("159915"), p880), 20); h1 = RM.ma_state(RM.ratio(RM.index_series("sh000300"), p880), 20)
    rows = index_rows(INDEX[code]); d = entry(code, rows, r2, h1); r = sim(d, C.PLAN[code])
    nav = {x["date"]: x["nav"] for x in r["nav"]}
    base = None; hold = {}
    for row in rows:
        if row["date"] < r["metric"]["first"]: continue
        v = float(row["adjusted_close"]); base = base or v; hold[row["date"]] = v/base
    return code, nav, hold, rows[0]["date"]
def etf_work(key): return C.work(key)
def _init(): C.init()
def yearly(nav, w):
    m = C.metrics({d: v for d, v in nav.items() if w[0] <= d <= w[1]} and C.portfolio(["x"], {"x": C.daily({d: v for d, v in nav.items() if w[0] <= d <= w[1]})}, w))
    return m["years"] if m else {}
if __name__ == "__main__":
    for c in sorted(set(INDEX.values())): fetch(c)
    C.init(); keys = [k for k in C.T.M.PANEL if k[1:] in C.PLAN]
    with Pool(8, initializer=_init) as p: etf = p.map(etf_work, keys)
    with Pool(8) as p: idx = p.map(work, list(INDEX))
    RE = {c: C.daily(nav) for c, nav, _ in etf}; HE = {c: C.daily(h) for c, _, h in etf}
    RI = {c: C.daily(nav) for c, nav, _, _ in idx}; HI = {c: C.daily(h) for c, _, h, _ in idx}; start = {c: s for c, _, _, s in idx}
    R = {**RE, **RI}; H = {**HE, **HI}
    nm = lambda c: f"{c}{C.NAMES[c]}({C.PLAN[c]})"
    print("## 1. 代理质量：ETF 上市后同期，指数版 vs ETF 版 各年收益（按方案）")
    diffs, pairs = [], []
    for c in INDEX:
        e0 = min(RE[c]); ye = C.metrics(C.portfolio([c], RE, (e0, END)))["years"]; yi = C.metrics(C.portfolio([c], RI, (e0, END)))["years"]
        common = [y for y in ye if y in yi and y > e0[:4]]  # 首年不完整不比
        for y in common: pairs.append((ye[y], yi[y])); diffs.append(yi[y] - ye[y])
        print(f"  {nm(c):<22} 指数起 {start[c]}  " + " ".join(f"{y[2:]}:{ye[y]*100:+.0f}/{yi[y]*100:+.0f}" for y in common))
    print(f"  全部 {len(pairs)} 个年份：相关 {statistics.correlation(*zip(*pairs)):.2f}；指数版减 ETF 版 平均 {statistics.mean(diffs)*100:+.1f} 个百分点，中位 {statistics.median(diffs)*100:+.1f}")
    W = ("2013-01-04", END); AB = C.G["A"] + C.G["B"]; ten = [m["code"] for m in json.load(open("AB组合_10只.json"))["members"]]
    def line(title, members, Rs=R, w=W):
        m = C.metrics(C.portfolio(members, Rs, w)); print(f"  {title:<24} 年化 {m['cagr']*100:5.1f}%  回撤 {m['mdd']*100:6.1f}%  卡玛 {m['cal']:.2f}  赚钱年 {m['pos']}/{len(m['years'])}  最差年 {m['worst']*100:+5.1f}%\n      逐年 " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items())); return m
    print("\n## 2. 延长后 2013 年起（有指数的用指数，其余用 ETF；成员未有数据的年份不占权重）")
    print("  每年有数据的成员数（10 只）：" + " ".join(f"{y}:{sum(any(d[:4] == str(y) for d in R[c]) for c in ten)}" for y in range(2013, 2027)))
    line("10 只组合（按方案）", ten); line("同 10 只一直持有", ten, H); line("A/B 24 只（按方案）", AB); line("A/B 24 只一直持有", AB, H)
    print("\n  10 只成员逐年（按方案）")
    for c in ten:
        m = C.metrics(C.portfolio([c], R, W)); print(f"  {nm(c):<22}{'（指数）' if c in INDEX else '（ETF） '} 年化 {m['cagr']*100:5.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:.2f}  " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    print("\n  分阶段（10 只组合 / 24 只 / 10 只持有）")
    for wn, a, z in C.Z.K.WINDOWS[1:]:
        if a < W[0]: a = W[0]
        if a >= z: continue
        ms = [C.metrics(C.portfolio(g, Rs, (a, z))) for g, Rs in ((ten, R), (AB, R), (ten, H))]
        print(f"  {wn:<20} " + " / ".join(f"累计 {(m['years'] and math.prod(1+v for v in m['years'].values())-1)*100:+6.1f}% 回撤 {m['mdd']*100:5.1f}%" for m in ms))
    print("\n## 3. 样本外：只用 2019-12-31 以前（延长后）的数据按 R2 规则挑 10 只，看 2020-01-02～2026-11-10")
    LR = {}
    for c in C.PLAN:
        if c in INDEX: rows = index_rows(INDEX[c])
        else: rows = C.T.M.PANEL[[k for k in C.T.M.PANEL if k[1:] == c][0]]["rows"]
        s = {r["date"]: float(r["adjusted_close"]) for r in rows}; ds = sorted(s); LR[c] = {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
    sel, _ = RC.rule(R, LR, "2019-12-31", 4); print("  当时选出：" + "、".join(nm(c) for c in sel))
    OOS = ("2020-01-02", END)
    line("样本外·当时挑的 10 只", sel, R, OOS); line("样本外·A/B 24 只", AB, R, OOS); line("样本外·当时 10 只持有", sel, H, OOS)
    rnd = random.Random(20261116); cals = sorted(C.metrics(C.portfolio(rnd.sample([c for c in AB if min(R[c]) <= "2019-12-31"], 10), R, OOS))["cal"] for _ in range(2000))
    print(f"  随机 10 只（2019 年前已有数据的 A/B 成员中抽）样本外卡玛：中位 {cals[1000]:.2f}  5%～95% [{cals[100]:.2f}, {cals[1900]:.2f}]")
