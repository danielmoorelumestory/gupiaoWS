"""用户猜想（2026-11-18）：A、B 两组同时使用两套择时策略，哪个发起的买入就按哪个卖出，持仓期间不重复交易。事前写定（跑之前）：
两套策略（规则不变）：
- 策略A = Y1（MACD 金叉 或 站上10日线且KD≥5.3 买；死叉卖；熊市不开新仓且破10日线卖）+ 创业板÷510880 > SMA20；
- 策略B = 只认金叉（金叉买、死叉卖，熊市不开新仓）+ 沪深300÷510880 > SMA20。
合并规则：每只 ETF 一个仓位、全仓；空仓时任一策略发出买入信号即买（次日开盘），记录发起方；持仓只看发起方的卖出信号（当日收盘或次日开盘，与引擎一致）；
持仓期间另一策略的信号一律忽略。同日两方都发买入：默认按该 ETF 所属组的策略（A 组→A，B 组→B，其他→A），另测「总是A优先」「总是B优先」。
成本单边 0.1%；分红/份额处理与引擎相同。先校验：只开一方时与引擎 simulate_y / simulate_kd 净值逐日一致。
样本：A 组 14、B 组 10、A+B 合并、全部面板与高波动子集；窗口 2020-01-02～2026-11-10 与全历史。
合格（事先定，2020 年起）：双择时（组内优先）在 A 组组合卡玛 > 单用A、在 B 组 > 单用B、在全部面板 > 单用A 与 单用B 两者，且全部面板单只平均卡玛不低于两者。
历史统计，不构成投资建议。"""
import importlib.util, json, math, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C; E = C.T.G.engine
FG = json.load(open("全量逐年优秀AB_最终分组.json")); GA, GB = FG["A"], FG["B"]
def sigs(d):
    above, below = d["above"], d["below"]; gold, dead = d["macds"][(12, 26, 9)]; kd = d["_kd"]
    ra, rb = d["reg"]["R2-20"], d["reg"]["H1"]
    def ex_a(i):
        if below[i] and ra[i] is False: return True
        return bool(dead[i])
    def en_a(i):
        if ra[i]: return bool(gold[i] or (i > 0 and above[i] and not above[i-1] and kd[i] >= 5.3))
        return False
    def ex_b(i): return bool(dead[i])
    def en_b(i): return bool(rb[i] and gold[i])
    return {"A": (en_a, ex_a), "B": (en_b, ex_b)}
def sim(d, active, prio, cost=20):
    span = E.bounds(d, C.FULL)
    if span is None: return None
    start, end = span; S = sigs(d)
    op, cl, s, u, dates = d["open"], d["close"], d["s"], d["u"], d["dates"]
    cash, reserve, q = 1.0, 0.0, 0.0; pending = None; owner = None; ent_i = None; nav = {}; cnt = {"A": 0, "B": 0}
    order = [prio] + [x for x in active if x != prio]
    for i in range(start, end + 1):
        if q and i > start:
            reserve += q/s[i-1]*(u[i]-u[i-1]); q *= s[i]/s[i-1]
        if pending:
            act, who = pending
            if act == "buy":
                q = cash/(op[i]*(1 + cost/20000)); cash = 0.0; owner = who; ent_i = i; cnt[who] += 1
            else:
                cash = q*op[i] - q*op[i]*cost/20000; q = 0.0; owner = None
            pending = None
        sold = False
        if q and i != end and ent_i != i and S[owner][1](i):
            cash = q*cl[i] - q*cl[i]*cost/20000; q = 0.0; owner = None; sold = True
        value = cash + reserve + q*cl[i]
        if i == end and q:
            cash = q*cl[i] - q*cl[i]*cost/20000; q = 0.0; value = cash + reserve
        nav[dates[i]] = value
        if i == end or sold: continue
        if q:
            if S[owner][1](i): pending = ("sell", owner)
        else:
            for who in order:
                if who in active and S[who][0](i): pending = ("buy", who); break
    return nav, cnt
VARS = {"单用A": (("A",), "A"), "单用B": (("B",), "B"), "双择时·组内优先": None, "双择时·A优先": (("A", "B"), "A"), "双择时·B优先": (("A", "B"), "B")}
def job(key):
    C.init(); d = C.T.M.PANEL[key]; code = key[1:]
    ra = C.Y.simulate_y(d, C.Y.VAR["Y1"], C.FULL, 20, retain=True); rb = C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True)
    out = {}
    for name, v in VARS.items():
        if v is None: v = (("A", "B"), "B" if code in GB and code not in GA else "A")
        r = sim(d, *v); out[name] = r if r else ({}, {"A": 0, "B": 0})
    chk = []
    for ref, nm in ((ra, "单用A"), (rb, "单用B")):
        if ref:
            a = {p["date"]: p["nav"] for p in ref["nav"]}; b = out[nm][0]
            chk.append(max(abs(a[t]/b[t] - 1) for t in a))
    c = [float(r["adjusted_close"]) for r in d["rows"]]; lr = [math.log(c[i]/c[i-1]) for i in range(1, len(c)) if c[i-1] > 0]
    out["vol"] = statistics.pstdev(lr)*math.sqrt(244) if len(lr) > 20 else 0; out["chk"] = max(chk) if chk else 0
    return code, out
def table(res, codes, W, title, K):
    print(f"\n## {title}（{len(codes)} 只，{W[0]}～{W[1]}）")
    for name in VARS:
        cs = [c for c in codes if res[c][name][0]]; ms = [m for m in (C.window_metrics(res[c][name][0], W) for c in cs) if m]
        pm = C.metrics(C.portfolio(cs, {c: C.daily(res[c][name][0]) for c in cs}, W)); sc = statistics.mean(m["cal"] for m in ms)
        na = sum(res[c][name][1]["A"] for c in cs); nb = sum(res[c][name][1]["B"] for c in cs)
        ys = " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in pm["years"].items()) if W[0] >= "2020" else ""
        print(f"  {name:<14} 组合 年化 {pm['cagr']*100:5.1f}% 回撤 {pm['mdd']*100:6.1f}% 卡玛 {pm['cal']:4.2f} 最差年 {pm['worst']*100:+5.1f}% ｜ 单只平均 年化 {statistics.mean(m['cagr'] for m in ms)*100:5.1f}% 回撤 {statistics.mean(m['mdd'] for m in ms)*100:6.1f}% 卡玛 {sc:5.2f} ｜ 全历史买入 A发起{na/len(cs):5.1f} B发起{nb/len(cs):5.1f} 次/只 ｜ {ys}")
        K[(title, W[0], name)] = (pm["cal"], sc)
if __name__ == "__main__":
    C.init(); keys = list(C.T.M.PANEL)
    with Pool(8) as p: res = dict(p.map(job, keys))
    print(f"校验：只开一方时与引擎净值最大相对误差 {max(o['chk'] for o in res.values()):.2e}")
    K = {}
    for W in (("2020-01-02", X.END), ("1900-01-01", X.END)):
        panel = [c for c in res if sum(1 for t in res[c]["单用A"][0] if t >= W[0]) >= 244]; hv = [c for c in panel if res[c]["vol"] >= 0.31]
        tag = W[0][:4]; ab = list(dict.fromkeys([c for c in GA + GB if c in res]))
        for title, cs in ((f"A 组·{tag}", [c for c in GA if c in res]), (f"B 组·{tag}", [c for c in GB if c in res]), (f"A+B 合并·{tag}", ab), (f"全部面板·{tag}", panel), (f"高波动(≥31%)·{tag}", hv)):
            table(res, cs, W, title, K)
    print("\n## 合格判定（2020 年起）")
    for name in ("双择时·组内优先", "双择时·A优先", "双择时·B优先"):
        g = lambda t, n: K[(t, "2020-01-02", n)]
        ck = [g("A 组·2020", name)[0] > g("A 组·2020", "单用A")[0], g("B 组·2020", name)[0] > g("B 组·2020", "单用B")[0],
              g("全部面板·2020", name)[0] > max(g("全部面板·2020", "单用A")[0], g("全部面板·2020", "单用B")[0]),
              g("全部面板·2020", name)[1] >= max(g("全部面板·2020", "单用A")[1], g("全部面板·2020", "单用B")[1])]
        print(f"  {name}：{'合格' if all(ck) else '不合格'}（{sum(ck)}/4）")
