"""从 A/B 优选与「差一项」候选中挑约 10 只组成互补、逐年稳定的组合。事前写定（2026-11-16，跑之前，用户要求）：
候选 31 只：A 组 14 只（Y1·创业板择时）、B 组 10 只（只认金叉·沪深300择时），以及放宽补入的 7 只：
  512400 有色、515210 钢铁、515050 5G通信、159781 科创创业50 用 A 方案；513630 港股低波红利、513120 港股创新药、513290 纳指生物科技 用 B 方案。
每只按各自方案全历史回测（上市后第 121 根起至 2026-11-10，单边 0.1% 成本），取每日净值。
1. 主题聚类：标的日收益（前复权）相关 ≥ 0.80 归为一类（重叠 ≥120 天才计）；每类只留全历史卡玛最高的一只作代表。
2. 组合：成员等权，每日在已有数据的成员间再平衡（未上市的成员不占权重，空仓日收益为 0）。
3. 挑选：代表中按前向贪心，每次加入使组合在评估期（2020-01-02～2026-11-10）卡玛最高的一只，直到 10 只；另报 8、12 只。
4. 对照：同 10 只一直持有等权；24 只 A/B 全部按方案等权；不管相关、直接按卡玛取前 10 只。
5. 样本外检验：只用 2023-12-31 以前的数据重做 1～3 步，再看所选组合 2024-01-02～2026-11-10 的表现，并与全部 24 只等权比较。
名单与组合都用同一段历史挑出，样本内数字偏乐观。历史统计，不构成投资建议。"""
import json, math, statistics, itertools, importlib.util
from multiprocessing import Pool
import run_extended as X, regime_multi as RM
def load(name, path):
    sp = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
Z = load("Z", "低波动沪深300择时对照.py"); T, K, Y = Z.T, Z.K, Z.Y
FULL = ("1900-01-01", "2026-11-10"); EVAL = ("2020-01-02", "2026-11-10")
G = json.load(open("全量逐年优秀AB_最终分组.json"))
EXTRA = {"512400": "A", "515210": "A", "515050": "A", "159781": "A", "513630": "B", "513120": "B", "513290": "B"}
PLAN = {**{c: "A" for c in G["A"]}, **{c: "B" for c in G["B"]}, **EXTRA}
NAMES = {"513310": "中韩半导体", "588200": "科创芯片", "159869": "游戏", "159851": "金融科技", "512760": "芯片", "159819": "人工智能易方达", "562500": "机器人",
         "159667": "工业母机", "516510": "云计算", "159939": "信息技术", "159998": "计算机天弘", "159852": "软件", "159967": "创业板成长", "512720": "计算机国泰",
         "512480": "半导体", "588000": "科创50", "512670": "国防", "159509": "纳指科技", "516150": "稀土", "159732": "消费电子", "515000": "科技华宝",
         "515980": "人工智能华富", "159755": "电池", "513090": "香港证券", "512400": "有色", "515210": "钢铁", "515050": "5G通信", "159781": "科创创业50",
         "513630": "港股低波红利", "513120": "港股创新药", "513290": "纳指生物科技"}
def init(): Z.init()
def work(key):
    d = T.M.PANEL[key]; c = key[1:]
    r = (Y.simulate_y(d, {**Y.VAR["Y1"], "N": "R2-20"}, FULL, 20, retain=True) if PLAN[c] == "A" else K.simulate_kd(d, {**T.BASE, "N": "H1"}, FULL, 20, retain=True))
    nav = {p["date"]: p["nav"] for p in r["nav"]}
    rows = d["rows"]; i0 = r["metric"]["first"]
    hold = {}; base = None
    for row in rows:
        if row["date"] < i0: continue
        v = float(row["adjusted_close"]); base = base or v; hold[row["date"]] = v / base
    return c, nav, hold
def daily(series):
    ds = sorted(series); return {ds[i]: series[ds[i]]/series[ds[i-1]] - 1 for i in range(1, len(ds))}
def portfolio(members, R, w):
    days = sorted({d for m in members for d in R[m] if w[0] <= d <= w[1]})
    nav, out = 1.0, {}
    for d in days:
        rs = [R[m][d] for m in members if d in R[m]]
        nav *= 1 + (sum(rs)/len(rs) if rs else 0); out[d] = nav
    return out
def window_metrics(nav, w):
    """单只净值在窗口 w 内的指标：先转日收益、窗口内以 1 重新累计（含窗口首日相对前一交易日的收益）。
    （2026-11-16 Codex 复测发现：直接截取全历史净值传给 metrics 会把窗口前的盈亏混进来。）"""
    return metrics(portfolio(["x"], {"x": daily(nav)}, w))
def metrics(nav):
    if not nav: return None
    ds = sorted(nav); v = [nav[d] for d in ds]; peak, mdd = 1.0, 0.0
    for x in v: peak = max(peak, x); mdd = min(mdd, x/peak - 1)
    yrs = len(ds)/244; cagr = v[-1]**(1/yrs) - 1 if yrs > 0 else 0
    years = {}; prev = 1.0
    for y in sorted({d[:4] for d in ds}):
        last = [nav[d] for d in ds if d[:4] == y][-1]; years[y] = last/prev - 1; prev = last
    return {"cagr": cagr, "mdd": mdd, "cal": cagr/abs(mdd) if mdd < 0 else float("inf"), "years": years, "worst": min(years.values()), "pos": sum(x > 0 for x in years.values())}
def cluster(codes, LR, thr=.80):
    parent = {c: c for c in codes}
    def find(a):
        while parent[a] != a: a = parent[a]
        return a
    for a, b in itertools.combinations(codes, 2):
        cc = [x for x in LR[a] if x in LR[b]]
        if len(cc) >= 120 and statistics.correlation([LR[a][x] for x in cc], [LR[b][x] for x in cc]) >= thr: parent[find(a)] = find(b)
    gs = {}
    for c in codes: gs.setdefault(find(c), []).append(c)
    return list(gs.values())
def select(R, LR, cut, n_max=12):
    """cut：只用 ≤cut 的数据。返回（代表, 贪心顺序）。"""
    Rc = {c: {d: v for d, v in R[c].items() if d <= cut} for c in R}
    codes = [c for c in R if len(Rc[c]) >= 244]
    cal = {c: (metrics(portfolio([c], Rc, ("1900-01-01", cut))) or {}).get("cal", -9) for c in codes}
    groups = cluster(codes, {c: {d: v for d, v in LR[c].items() if d <= cut} for c in codes})
    reps = [max(g, key=lambda c: cal[c]) for g in groups]
    chosen = []; w = (EVAL[0], cut)
    while len(chosen) < min(n_max, len(reps)):
        best = max((c for c in reps if c not in chosen), key=lambda c: metrics(portfolio(chosen + [c], Rc, w))["cal"])
        chosen.append(best)
    return groups, reps, chosen, cal
if __name__ == "__main__":
    init(); keys = [k for k in T.M.PANEL if k[1:] in PLAN]; assert len(keys) == len(PLAN), set(PLAN) - {k[1:] for k in keys}
    with Pool(8, initializer=init) as p: res = p.map(work, keys)
    R = {c: daily(nav) for c, nav, _ in res}; H = {c: daily(h) for c, _, h in res}
    pool, new, audit = X.build(); rows = {**{k: v["rows"] for k, v in pool.items()}, **{k: v["rows"] for k, v in new.items()}}
    def lr(rs):
        s = RM.series_from_rows(rs); ds = sorted(s); return {ds[i]: math.log(s[ds[i]]/s[ds[i-1]]) for i in range(1, len(ds))}
    LR = {c: lr(rows[c]) for c in PLAN}
    nm = lambda c: f"{c}{NAMES[c]}({PLAN[c]})"
    def show(title, members, Rset=R, w=EVAL):
        m = metrics(portfolio(members, Rset, w))
        print(f"  {title:<26} 年化 {m['cagr']*100:5.1f}%  回撤 {m['mdd']*100:6.1f}%  卡玛 {m['cal']:.2f}  赚钱年 {m['pos']}/{len(m['years'])}  最差年 {m['worst']*100:+5.1f}%  逐年 " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
        return m
    groups, reps, chosen, cal = select(R, LR, EVAL[1])
    print(f"## 主题聚类（相关≥0.80）：31 只 → {len(groups)} 类")
    for g in sorted(groups, key=lambda g: -max(cal[c] for c in g)):
        rep = max(g, key=lambda c: cal[c]); print(f"  代表 {nm(rep)} 卡玛 {cal[rep]:.2f}" + (f"  ｜ 同类：{'、'.join(nm(c) for c in g if c != rep)}" if len(g) > 1 else ""))
    print("\n## 贪心加入顺序（每步组合卡玛，评估期 2020-01-02～2026-11-10）")
    for i in range(len(chosen)):
        m = metrics(portfolio(chosen[:i+1], R, EVAL)); print(f"  {i+1:2d}. {nm(chosen[i]):<22} 组合卡玛 {m['cal']:.2f}  最差年 {m['worst']*100:+5.1f}%")
    top10 = chosen[:10]
    print("\n## 组合表现（评估期，等权每日再平衡）")
    for n in (8, 10, 12): show(f"贪心前 {n} 只（按方案）", chosen[:n])
    show("同 10 只 一直持有", top10, H)
    show("A/B 全部 24 只（按方案）", G["A"] + G["B"])
    show("卡玛前 10（不管相关）", sorted(PLAN, key=lambda c: -cal.get(c, -9))[:10])
    print("\n## 10 只组合的成员（按方案逐年，评估期）")
    for c in top10:
        m = metrics(portfolio([c], R, EVAL)); print(f"  {nm(c):<22} 年化 {m['cagr']*100:5.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:.2f}  " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    cs = [statistics.correlation(*zip(*[(R[a][d], R[b][d]) for d in R[a] if d in R[b] and d >= EVAL[0]])) for a, b in itertools.combinations(top10, 2) if sum(d in R[b] for d in R[a]) >= 120]
    us = [statistics.correlation(*zip(*[(LR[a][d], LR[b][d]) for d in LR[a] if d in LR[b]])) for a, b in itertools.combinations(top10, 2)]
    print(f"\n  成员两两相关：标的本身 平均 {statistics.mean(us):.2f} 最高 {max(us):.2f}；按方案的每日收益 平均 {statistics.mean(cs):.2f} 最高 {max(cs):.2f}")
    print("\n## 样本外检验：只用 2023-12-31 以前数据挑选，看 2024-01-02～2026-11-10")
    _, _, chosen_is, _ = select(R, LR, "2023-12-31")
    print("  当时选出：" + "、".join(nm(c) for c in chosen_is[:10]))
    OOS = ("2024-01-02", "2026-11-10")
    show("样本外·当时挑的 10 只", chosen_is[:10], R, OOS)
    show("样本外·A/B 全部 24 只", G["A"] + G["B"], R, OOS)
    show("样本外·当时挑的10只持有", chosen_is[:10], H, OOS)
    json.dump({"members": [{"code": c, "name": NAMES[c], "plan": PLAN[c]} for c in top10], "ranked": chosen}, open("AB组合_10只.json", "w"), ensure_ascii=False, indent=1)
