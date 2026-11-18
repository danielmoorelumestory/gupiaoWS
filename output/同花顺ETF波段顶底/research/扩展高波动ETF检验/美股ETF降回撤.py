"""用户要求（2026-11-18）：美股 ETF 择时没法多赚，那能否减小回撤。事前写定（跑之前，跑完不改）：
标的同 美股ETF自身择时.py：513100、159941（纳指），513500（标普500）。窗口 2015 起、2020 起，到 2026-11-10。
做法（仓位 w 在 t-1 收盘决定、作用于 t 日收益；美股信号只用美股日期 < 决定日 的收盘；换仓成本 0.1%×|Δw|；现金收益按 0）：
  V15/V20  波动率目标：w = min(1, 目标/ETF 近 20 日年化波动)，目标 15%/20%；|Δw|<0.1 不调。
  H200     半仓过滤：指数 > 200 日线满仓，否则半仓。
  S10      回撤止损：ETF 收盘较持有期最高点跌 10% 清仓；之后 ETF 收盘站上 50 日线再满仓。
  G40      固定配置：60% ETF + 40% 黄金 518880，每月首个交易日再平衡。
  B40      固定配置：60% ETF + 40% 国债 511010，每月再平衡。
  GB       50% ETF + 25% 黄金 + 25% 国债，每月再平衡。
  GB200    同 GB，但指数在 200 日线下时 ETF 那份转入国债。
合格（降回撤）：3 只 × 2 窗口都满足：最大回撤比一直持有小至少 1/4（相对），且卡玛不低于一直持有。另报年化少赚多少。
历史统计，不构成投资建议。"""
import importlib.util, math, statistics, datetime
sp = importlib.util.spec_from_file_location("U", "美股ETF自身择时.py"); U = importlib.util.module_from_spec(sp); sp.loader.exec_module(U)
W, C, X, RM, T = U.W, U.C, U.X, U.RM, U.T
def px(code):
    d = W.data_of(code); return {r["date"]: float(r["adjusted_close"]) for r in d["rows"]}
def run_w(dates, P, weights_of, cost=0.001):
    """weights_of(i) -> {资产: 权重}，在 dates[i-1] 收盘决定，作用于 dates[i]。"""
    nav = {dates[0]: 1.0}; v = 1.0; prev = {}
    for i in range(1, len(dates)):
        w = weights_of(i); turn = sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in set(w) | set(prev))
        r = sum(wk * (P[k][dates[i]] / P[k][dates[i-1]] - 1) for k, wk in w.items())
        v *= (1 + r) * (1 - cost * turn); nav[dates[i]] = v
        # 权重随价格漂移
        tot = sum(wk * P[k][dates[i]] / P[k][dates[i-1]] for k, wk in w.items()) + (1 - sum(w.values()))
        prev = {k: wk * P[k][dates[i]] / P[k][dates[i-1]] / tot for k, wk in w.items()} if tot else {}
    return nav
if __name__ == "__main__":
    C.init(); NDX, INX = T.load("us.NDX"), T.load("us.INX")
    G, B = px("518880"), None
    T.load("sh511010"); import json, gzip
    B = {x[0]: float(x[2]) for x in json.loads(gzip.decompress((T.RAW / "sh511010-tencent-hfq.json.gz").read_bytes())) if x[0] <= X.END}
    res = {}
    for code, (name, idx) in U.ETFS.items():
        E = px(code); I = NDX if idx == "us.NDX" else INX
        ma = U.shift(RM.ma_state(I, 200))
        dates = [t for t in sorted(E) if t in G and t in B and t >= "2014-07-15"]
        bull = RM.last_known(ma, dates)  # bull[i]：dates[i] 开盘前已知
        P = {"E": E, "G": G, "B": B}
        ret = [0] + [E[dates[i]] / E[dates[i-1]] - 1 for i in range(1, len(dates))]
        def vt(target):
            st = {"w": 1.0}
            def f(i):
                j = i - 1
                if j >= 20:
                    vol = statistics.pstdev(ret[j-19:j+1]) * math.sqrt(244); w = min(1.0, target / vol) if vol > 0 else 1.0
                    if abs(w - st["w"]) >= 0.1: st["w"] = w
                return {"E": st["w"]}
            return f
        def s10():
            st = {"in": True, "peak": E[dates[0]]}
            def f(i):
                j = i - 1; p = E[dates[j]]
                if st["in"]:
                    st["peak"] = max(st["peak"], p)
                    if p <= st["peak"] * 0.9: st["in"] = False
                elif j >= 50 and p > statistics.fmean(E[dates[k]] for k in range(j-49, j+1)): st["in"] = True; st["peak"] = p
                return {"E": 1.0} if st["in"] else {}
            return f
        def mix(wts, filt=False):
            st = {"w": dict(wts)}
            def f(i):
                if i == 1 or dates[i-1][:7] != dates[i-2][:7]:
                    w = dict(wts)
                    if filt and not bull[i-1]: w["B"] = w.get("B", 0) + w.pop("E")
                    st["w"] = w
                return st["w"]
            return f
        runs = {"一直持有": run_w(dates, P, lambda i: {"E": 1.0}),
                "V15": run_w(dates, P, vt(0.15)), "V20": run_w(dates, P, vt(0.20)),
                "H200": run_w(dates, P, lambda i: {"E": 1.0 if bull[i-1] else 0.5}),
                "S10": run_w(dates, P, s10()),
                "G40": run_w(dates, P, mix({"E": 0.6, "G": 0.4})), "B40": run_w(dates, P, mix({"E": 0.6, "B": 0.4})),
                "GB": run_w(dates, P, mix({"E": 0.5, "G": 0.25, "B": 0.25})), "GB200": run_w(dates, P, mix({"E": 0.5, "G": 0.25, "B": 0.25}, True))}
        print(f"\n######## {code} {name}")
        for wn, w in U.WINS.items():
            print(f"## {wn}")
            for k, nav in runs.items():
                m = C.window_metrics(nav, w); res[(code, wn, k)] = m
                print(f"  {k:8s} 年化 {m['cagr']*100:6.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:5.2f} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    print("\n######## 合格检查（回撤相对小 ≥25% 且 卡玛 ≥ 一直持有；格内为 回撤缩小比例/卡玛差/年化差pp）")
    for k in ["V15", "V20", "H200", "S10", "G40", "B40", "GB", "GB200"]:
        ok = True; cells = []
        for code in U.ETFS:
            for wn in U.WINS:
                m, h = res[(code, wn, k)], res[(code, wn, "一直持有")]
                cut = 1 - m["mdd"] / h["mdd"]; dc = m["cal"] - h["cal"]; da = (m["cagr"] - h["cagr"]) * 100; good = cut >= 0.25 and dc >= 0; ok &= good
                cells.append(f"{code[-3:]}{wn[2:4]}:{cut*100:.0f}%/{dc:+.2f}/{da:+.1f}{'✓' if good else '✗'}")
        print(f"  {'合格' if ok else '  - '} {k:6s} " + " ".join(cells))
