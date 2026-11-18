"""用户澄清（2026-11-18）：不搭配其他资产，只用纯择时（单只 ETF 的仓位 0~100%）减小回撤。事前写定（跑之前，跑完不改）：
标的、窗口、成本、时间对齐同 美股ETF降回撤.py（仓位 t-1 收盘决定作用于 t 日；美股信号只用美股日期 < 决定日；0.1%×换手；空仓收益 0）。
信号都用对应美股指数（纳指 ETF 用 NDX，标普 ETF 用 INX）：
  T200     指数 > 200 日线满仓，否则空仓（参照）
  T200B    带 2% 缓冲：跌破 200 日线×0.98 才空仓，站上 ×1.02 才满仓
  M10      月末指数 > 210 日线（约 10 个月线）则下月满仓，否则空仓
  MOM12    月末指数近 252 日涨幅 > 0 则下月满仓
  X50      50 日线 > 200 日线满仓
  VOL      指数 20 日年化波动 > 30% 空仓，回到 < 20% 再满仓
  VOLT     VOL 与 T200 任一空仓即空仓
  CRASH    指数 5 日跌幅 ≥ 6% 空仓，之后指数站上 20 日线再满仓
  V15i     仓位 = min(1, 15% / 指数 20 日年化波动)，|Δw|<0.1 不调
  V15iT    V15i，且指数在 200 日线下时仓位减半
合格：3 只 × 2 窗口都满足：最大回撤比一直持有小至少 1/4（相对），且卡玛不低于一直持有。另报年化差与回撤发生时间。
历史统计，不构成投资建议。"""
import importlib.util, math, statistics
sp = importlib.util.spec_from_file_location("D", "美股ETF降回撤.py"); D = importlib.util.module_from_spec(sp); sp.loader.exec_module(D)
U, W, C, X, RM, T = D.U, D.W, D.C, D.X, D.RM, D.T
import datetime
def known(series_map, dates):  # 美股日期 t 的值 → A 股 t+1 日起可用
    return RM.last_known(U.shift(series_map), dates)
def mdd_when(nav, w):
    ks = [k for k in sorted(nav) if w[0] <= k <= w[1]]; peak = nav[ks[0]]; pk = ks[0]; best = (0, "", "")
    for k in ks:
        if nav[k] > peak: peak, pk = nav[k], k
        dd = nav[k] / peak - 1
        if dd < best[0]: best = (dd, pk, k)
    return f"{best[1][:7]}→{best[2][:7]}"
if __name__ == "__main__":
    C.init(); NDX, INX = T.load("us.NDX"), T.load("us.INX"); res = {}
    for code, (name, idx) in U.ETFS.items():
        E = D.px(code); I = NDX if idx == "us.NDX" else INX; ds_us = sorted(I); iv = [I[t] for t in ds_us]
        def ma(n): return {t: (statistics.fmean(iv[i-n+1:i+1]) if i >= n-1 else None) for i, t in enumerate(ds_us)}
        MA200, MA210, MA50, MA20 = ma(200), ma(210), ma(50), ma(20)
        r = [None] + [iv[i] / iv[i-1] - 1 for i in range(1, len(iv))]
        VOL = {t: (statistics.pstdev(r[i-19:i+1]) * math.sqrt(252) if i >= 20 else None) for i, t in enumerate(ds_us)}
        R5 = {t: (iv[i] / iv[i-5] - 1 if i >= 5 else None) for i, t in enumerate(ds_us)}
        R252 = {t: (iv[i] / iv[i-252] - 1 if i >= 252 else None) for i, t in enumerate(ds_us)}
        # 美股侧逐日状态机
        def fsm(step):
            out = {}; s = True
            for t in ds_us: s = step(t, s); out[t] = s
            return out
        st = {}
        st["T200"] = {t: (I[t] > MA200[t]) if MA200[t] else None for t in ds_us}
        st["T200B"] = fsm(lambda t, s: s if not MA200[t] else (False if I[t] < MA200[t] * 0.98 else True if I[t] > MA200[t] * 1.02 else s))
        def monthly(cond):
            out = {}; cur = True
            for i, t in enumerate(ds_us):
                if i + 1 < len(ds_us) and ds_us[i+1][:7] != t[:7]:
                    c = cond(t); cur = cur if c is None else c
                out[t] = cur
            return out
        st["M10"] = monthly(lambda t: (I[t] > MA210[t]) if MA210[t] else None)
        st["MOM12"] = monthly(lambda t: (R252[t] > 0) if R252[t] is not None else None)
        st["X50"] = {t: (MA50[t] > MA200[t]) if MA200[t] else None for t in ds_us}
        st["VOL"] = fsm(lambda t, s: s if VOL[t] is None else (False if VOL[t] > 0.30 else True if VOL[t] < 0.20 else s))
        st["CRASH"] = fsm(lambda t, s: s if R5[t] is None or MA20[t] is None else (False if R5[t] <= -0.06 else True if (not s and I[t] > MA20[t]) else s))
        dates = [t for t in sorted(E) if t >= "2014-07-15"]
        K = {k: known(v, dates) for k, v in st.items()}; KV = known(VOL, dates)
        P = {"E": E}
        def binary(k): return lambda i: {"E": 1.0} if K[k][i-1] else {}
        def v15(half):
            s = {"w": 1.0}
            def f(i):
                v = KV[i-1]; w = min(1.0, 0.15 / v) if v and v > 0 else 1.0
                if half and not K["T200"][i-1]: w *= 0.5
                if abs(w - s["w"]) >= 0.1 or (w == 1.0 and s["w"] != 1.0 and abs(w - s["w"]) > 0): s["w"] = w
                return {"E": s["w"]}
            return f
        runs = {"一直持有": D.run_w(dates, P, lambda i: {"E": 1.0})}
        for k in ["T200", "T200B", "M10", "MOM12", "X50", "VOL"]: runs[k] = D.run_w(dates, P, binary(k))
        runs["VOLT"] = D.run_w(dates, P, lambda i: {"E": 1.0} if K["VOL"][i-1] and K["T200"][i-1] else {})
        runs["CRASH"] = D.run_w(dates, P, binary("CRASH"))
        runs["V15i"] = D.run_w(dates, P, v15(False)); runs["V15iT"] = D.run_w(dates, P, v15(True))
        print(f"\n######## {code} {name}")
        for wn, w in U.WINS.items():
            print(f"## {wn}")
            for k, nav in runs.items():
                m = C.window_metrics(nav, w); res[(code, wn, k)] = m
                print(f"  {k:8s} 年化 {m['cagr']*100:6.1f}% 回撤 {m['mdd']*100:6.1f}%（{mdd_when(nav, w)}） 卡玛 {m['cal']:5.2f} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    print("\n######## 合格检查（回撤相对小 ≥25% 且 卡玛 ≥ 一直持有；格内为 回撤缩小比例/卡玛差/年化差pp）")
    for k in [k for k in runs if k != "一直持有"]:
        ok = True; cells = []
        for code in U.ETFS:
            for wn in U.WINS:
                m, h = res[(code, wn, k)], res[(code, wn, "一直持有")]
                cut = 1 - m["mdd"] / h["mdd"]; dc = m["cal"] - h["cal"]; da = (m["cagr"] - h["cagr"]) * 100; good = cut >= 0.25 and dc >= 0; ok &= good
                cells.append(f"{code[-3:]}{wn[2:4]}:{cut*100:.0f}%/{dc:+.2f}/{da:+.1f}{'✓' if good else '✗'}")
        print(f"  {'合格' if ok else '  - '} {k:6s} " + " ".join(cells))
