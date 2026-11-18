"""用户要求（2026-11-18）：择时比值刚好贴着 20 日均线（牛熊分界）时，判牛、判熊、维持原状还是等一天最好？
起因：创新药 159992 在 2025-11-28 沪深300÷红利 相对均线偏离研究 +0.003%、页面 −0.011%，两边判断相反，多/少一笔 −2.1% 的交易。
之前（微弱翻转不操作对照.py、择时漏启动补票对照.py）测过 0.2%～1% 的滞后带、等一天、宽容带（偏牛），均不合格。本次补测数据误差级的窄带和「偏熊」。
事前写定（跑之前）：
- 偏离 = 比值/SMA20 − 1；|偏离| < θ 记为「贴线」。θ ∈ {0.02%, 0.05%, 0.1%}。
- 四种贴线处理（与现行「比值 > 均线即牛」对比）：
  偏牛：贴线一律算牛；偏熊：贴线一律算熊（不开新仓，A 方案熊市破 10 日线卖）；
  维持原状：贴线时沿用前一天的牛熊；等一天：贴线当天沿用前一天，第二天按真实状态。
- 只改择时（A 方案创业板÷510880、B 方案沪深300÷510880），MACD 与 10 日线等其他条件不变。
- 样本（网页现行名单）：A 组 14 只（A 方案）、B 组 9 只（B 方案）、行业观察池 12 只（各自方案：cyb→A、hs→B）。
- 窗口 2020-01-02～2026-11-10 与全历史；组合等权每日再平衡；单边 0.1% 成本。
- 合格：三组 2020 年起组合卡玛都高于现行，且三组单只平均卡玛都不低于现行（6 项全过）。
历史统计，不构成投资建议。"""
import importlib.util, json, statistics, sys, os
from multiprocessing import Pool
sys.argv = sys.argv[:1] + ["/dev/null"]
sp = importlib.util.spec_from_file_location("W", "行业观察池导出网页.py"); W = importlib.util.module_from_spec(sp); sp.loader.exec_module(W)
X = W.X; C = X.C
import regime_multi as RM
WEB = os.path.expanduser("~/work/gupiaoWS/BusinessWeb/.worktrees/etf-review-row-click/src/data")
GA = [i["code"] for i in json.load(open(f"{WEB}/etfMacdGood.json"))["items"]]
GB = [i["code"] for i in json.load(open(f"{WEB}/etfHs300Timing.json"))["items"]]
GW = {i["code"]: ("A" if i["plan"] == "cyb" else "B") for i in json.load(open(f"{WEB}/etfWatchPool.json"))["items"]}
p880 = RM.load_new("510880"); RAT = {"R2-20": RM.ratio(RM.load_new("159915"), p880), "H1": RM.ratio(RM.index_series("sh000300"), p880)}
def reg_dev(r):
    ds = sorted(r); v = [r[x] for x in ds]; out = {}; s = 0.0
    for i, x in enumerate(ds):
        s += v[i]
        if i >= 20: s -= v[i-20]
        out[x] = (v[i] > s/20, v[i]/(s/20) - 1) if i >= 19 else (None, 0.0)
    return ds, out
DEV = {k: reg_dev(r) for k, r in RAT.items()}
def reg_mode(key, mode, th):
    ds, o = DEV[key]; out = {}; prev_out = None; prev_raw = None
    for x in ds:
        st, dv = o[x]
        if st is None: out[x] = None; continue
        near = abs(dv) < th
        if mode == "现行" or not near: cur = st
        elif mode == "偏牛": cur = True
        elif mode == "偏熊": cur = False
        elif mode == "维持原状": cur = prev_out if prev_out is not None else st
        else: cur = prev_raw if prev_raw is not None else st  # 等一天：贴线当天沿用前一天真实状态
        out[x] = cur; prev_out = cur; prev_raw = st
    return out
SETS = [("现行", 0)] + [(m, th) for m in ("偏牛", "偏熊", "维持原状", "等一天") for th in (0.0002, 0.0005, 0.001)]
LAB = ["现行（比值>均线即牛）" if m == "现行" else f"{m} 贴线<{th*100:g}%" for m, th in SETS]
def data(code):
    C.init(); return W.data_of(code)
def job(code):
    d = data(code); out = {}
    plans = {"A"} if code in GA else set()
    if code in GB: plans.add("B")
    if code in GW: plans.add(GW[code])
    for (m, th), lab in zip(SETS, LAB):
        for plan in plans:
            N = "R2-20" if plan == "A" else "H1"
            rg = RM.last_known(reg_mode(N, m, th), d["dates"])
            dd = {**d, "reg": {**d["reg"], N: rg}}
            r = C.Y.simulate_y(dd, C.Y.VAR["Y1"], C.FULL, 20, retain=True) if plan == "A" else C.K.simulate_kd(dd, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True)
            out[(plan, lab)] = ({p["date"]: p["nav"] for p in r["nav"]}, len(r["trades"]), {t["entry_date"] for t in r["trades"]}) if r else ({}, 0, set())
    return code, out
def table(res, items, Wd, title, K):
    print(f"\n## {title}（{len(items)} 只，{Wd[0]}～{Wd[1]}）")
    base = {c: res[c][(p, LAB[0])][2] for c, p in items}
    for t in LAB:
        cs = [(c, p) for c, p in items if res[c][(p, t)][0]]
        ms = [m for m in (C.window_metrics(res[c][(p, t)][0], Wd) for c, p in cs) if m]
        pm = C.metrics(C.portfolio([c for c, _ in cs], {c: C.daily(res[c][(p, t)][0]) for c, p in cs}, Wd)); sc = statistics.mean(m["cal"] for m in ms)
        diff = sum(len(res[c][(p, t)][2] ^ base[c]) for c, p in cs)
        print(f"  {t:<18} 组合 年化 {pm['cagr']*100:5.1f}% 回撤 {pm['mdd']*100:6.1f}% 卡玛 {pm['cal']:4.2f} 赚钱年 {pm['pos']}/{len(pm['years'])} ｜ 单只平均 年化 {statistics.mean(m['cagr'] for m in ms)*100:5.1f}% 卡玛 {sc:5.2f} ｜ 买入日不同 {diff:3d} 笔")
        K[(title, t)] = (pm["cal"], sc)
if __name__ == "__main__":
    codes = sorted(set(GA) | set(GB) | set(GW))
    with Pool(8) as p: res = dict(p.map(job, codes))
    print("## 择时贴线天数（2020 年起，|偏离| < θ 的交易日 / 牛熊切换当天）")
    for N in ("R2-20", "H1"):
        ds, o = DEV[N]; xs = [x for x in ds if x >= "2020-01-02" and o[x][0] is not None]
        sw = [abs(o[ds[i]][1]) for i in range(1, len(ds)) if ds[i] >= "2020-01-02" and o[ds[i]][0] is not None and o[ds[i-1]][0] is not None and o[ds[i]][0] != o[ds[i-1]][0]]
        print(f"  {N}: " + "，".join(f"<{th*100:g}% 共 {sum(abs(o[x][1]) < th for x in xs)} 天（切换日 {sum(v < th for v in sw)}/{len(sw)}）" for th in (0.0002, 0.0005, 0.001)))
    groups = {"A 组": [(c, "A") for c in GA], "B 组": [(c, "B") for c in GB], "行业观察池": list(GW.items())}
    K = {}
    for Wd in (("2020-01-02", X.END), ("1900-01-01", X.END)):
        for g, items in groups.items(): table(res, items, Wd, f"{g}·{Wd[0][:4]}", K)
    print("\n## 合格判定（2020 年起；三组组合卡玛高于现行 + 三组单只平均卡玛不低于现行）")
    for t in LAB[1:]:
        ck = []
        for g in groups: ck += [K[(f"{g}·2020", t)][0] > K[(f"{g}·2020", LAB[0])][0], K[(f"{g}·2020", t)][1] >= K[(f"{g}·2020", LAB[0])][1]]
        print(f"  {t:<18} {'合格' if all(ck) else '不合格'}（{sum(ck)}/6）")
