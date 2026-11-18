"""用户要求（2026-11-17）：A/B 组偏进攻，择时过滤掉的时间改买红利 ETF，或保险、公用事业、电力、煤炭等防守方向，收益如何。事前写定（跑之前）：
原策略不变（A 方案 Y1+创业板÷510880；B 方案只认金叉+沪深300÷510880），只改「空仓那部分钱」放哪里：
- 何时放防守：某只 ETF 前一日收盘与当日收盘都空仓 → 当日拿防守 ETF 的收盘→收盘涨跌幅（尾盘买入防守、尾盘卖出，与原策略买卖同一时刻衔接）。
  两种口径：①熊市空仓：前一日择时为熊且空仓（用户说的「择时过滤掉的时间」）；②全部空仓：只要空仓就放。
- 成本：每次进入/退出防守各扣 0.1%。
防守候选（腾讯后复权，含分红）：现金(0) 作基准；货币 511880；红利 510880；红利低波 512890；银行 512800；煤炭 515220（2020-03 起，之前按现金）；
证券保险 512070（注：无纯保险 ETF，此为非银含券商，不算真正防守，仅作参考）；电力 159611（2022-01 起，单独看 2022 年起窗口）；防守篮子 = 红利低波+银行+煤炭等权。
公用事业 ETF（159301）2024-07 才上市，太短不测。
样本：A 组 14（A 方案）、B 组 10（B 方案）、全部面板与高波动子集（两方案）。窗口：2020-01-02～2026-11-10；另报 2022-01-10 起（含电力）。
合格（事先定）：某防守在 2020 年起 A 组、B 组、全部面板两方案的组合卡玛都高于「现金」，且同时高于「货币 511880」。
事后修正（跑完第一版后，2026-11-17）：
- 防守 ETF 当日无数据（未上市）时按现金处理且不收切换成本（第一版误收了成本，使电力/煤炭上市前也被扣费）。
- 事后追加口径 ③熊市进、买入出：熊市且空仓时进入防守，之后一直拿着，直到主策略买入才卖（第一版①在择时每次转牛都卖出，切换太频繁、成本吃掉收益）。
历史统计，不构成投资建议。"""
import importlib.util, json, math, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import tencent_hfq as T
FG = json.load(open("全量逐年优秀AB_最终分组.json")); GA, GB = FG["A"], FG["B"]
DEF = {"货币511880": "sh511880", "红利510880": "sh510880", "红利低波512890": "sh512890", "银行512800": "sh512800", "煤炭515220": "sh515220", "证券保险512070": "sh512070", "电力159611": "sz159611"}
PX = {k: T.load(s) for k, s in DEF.items()}
DR = {k: C.daily(v) for k, v in PX.items()}
DR["防守篮子"] = {t: statistics.mean(DR[k][t] for k in ("红利低波512890", "银行512800", "煤炭515220") if t in DR[k]) for t in DR["红利低波512890"]}
NAMES = ["现金"] + list(DR)
COST = 0.001
def job(key):
    C.init(); d = C.T.M.PANEL[key]
    c = [float(r["adjusted_close"]) for r in d["rows"]]; lr = [math.log(c[i]/c[i-1]) for i in range(1, len(c)) if c[i-1] > 0]
    out = {"vol": statistics.pstdev(lr) * math.sqrt(244) if len(lr) > 20 else 0}
    for plan in ("A", "B"):
        r = C.Y.simulate_y(d, C.Y.VAR["Y1"], C.FULL, 20, retain=True) if plan == "A" else C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True)
        reg = dict(zip(d["dates"], d["reg"]["R2-20" if plan == "A" else "H1"]))
        out[plan] = [(p["date"], p["nav"], p["held_session"], bool(reg[p["date"]])) for p in r["nav"]] if r else []
    return key[1:], out
def blend(rows, dname, mode):
    """返回 (日收益 dict, 防守天数占比)。"""
    R = {}; act_prev = False; nd = 0
    for i in range(1, len(rows)):
        t0, n0, h0, b0 = rows[i-1]; t, n1, h1, _ = rows[i]
        r = n1/n0 - 1
        idle = h0 == 0 and h1 == 0 and dname != "现金" and t in DR[dname]
        act = idle and (mode == "全部空仓" or not b0 or (mode == "熊市进买入出" and act_prev))
        if act: r += DR[dname].get(t, 0.0); nd += 1
        if act != act_prev: r -= COST
        R[t] = r; act_prev = act
    return R, nd / max(1, len(rows) - 1)
def table(res, codes, plan, W, mode, title, K):
    print(f"\n## {title}（{len(codes)} 只，{plan} 方案，{mode}，{W[0]} 起）")
    for dn in NAMES:
        R = {}; sh = []
        for c in codes:
            rows = [x for x in res[c][plan] if x[0] >= W[0]] if False else res[c][plan]
            R[c], s = blend(rows, dn, mode); sh.append(s)
        pm = C.metrics(C.portfolio(codes, R, W))
        ys = " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in pm["years"].items())
        print(f"  {dn:<12} 年化 {pm['cagr']*100:5.1f}% 回撤 {pm['mdd']*100:6.1f}% 卡玛 {pm['cal']:4.2f} 最差年 {pm['worst']*100:+5.1f}% ｜ 逐年 {ys}")
        K[(title, plan, mode, W[0], dn)] = pm["cal"]
    return statistics.mean(sh)
if __name__ == "__main__":
    C.init(); keys = list(C.T.M.PANEL)
    with Pool(8) as p: res = dict(p.map(job, keys))
    K = {}
    for W in (("2020-01-02", X.END), ("2022-01-10", X.END)):
        panel = [c for c in res if res[c]["A"] and sum(1 for x in res[c]["A"] if x[0] >= W[0]) >= 244]; hv = [c for c in panel if res[c]["vol"] >= 0.31]
        for mode in ("熊市空仓", "熊市进买入出", "全部空仓"):
            print(f"\n######## 窗口 {W[0]} 起 · 放防守口径：{mode}")
            for title, codes, plans in (("A 组", [c for c in GA if c in res], "A"), ("B 组", [c for c in GB if c in res], "B"), ("全部面板", panel, "AB"), ("高波动(≥31%)", hv, "AB")):
                for plan in plans:
                    s = table(res, codes, plan, W, mode, title, K)
                    print(f"  （平均有 {s*100:.0f}% 的交易日放在防守里）")
    print("\n## 合格判定（2020 年起：A 组、B 组、全部面板两方案组合卡玛都高于 现金 且高于 货币511880）")
    W0 = "2020-01-02"
    for mode in ("熊市空仓", "熊市进买入出", "全部空仓"):
        for dn in NAMES[2:]:
            cells = [("A 组", "A"), ("B 组", "B"), ("全部面板", "A"), ("全部面板", "B")]
            ck = [K[(t, p, mode, W0, dn)] > max(K[(t, p, mode, W0, "现金")], K[(t, p, mode, W0, "货币511880")]) for t, p in cells]
            print(f"  {mode} · {dn:<12} {'合格' if all(ck) else '不合格'}（{sum(ck)}/4）  卡玛 " + " ".join(f"{t}{p}:{K[(t, p, mode, W0, dn)]:.2f}" for t, p in cells))
