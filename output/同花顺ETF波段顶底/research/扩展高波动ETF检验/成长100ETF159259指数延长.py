"""用户要求（2026-11-22）：159259（易方达国证成长100ETF，2025-08 上市）也回测一下。事前写定：
ETF 本身只有 1 年多，按 指数延长回测.py 的做法用跟踪指数延长：国证成长100 全收益指数 480080（国证指数官网日线，含分红再投资，
比其他候选用的中证价格指数略乐观；2024 年以前只有收盘价，开盘按前一日收盘、高低取开收两者，KD 为近似）。
跑 A（Y1·创业板择时）与 B（只认金叉·沪深300择时），单边 0.1%、前 120 根预热，评估 2013-01-04～2026-11-10（与 A/B 组研究面板同截止日），
另列一直持有；并用 ETF 自身数据跑同一时段做代理核对。历史统计，不构成投资建议。"""
import importlib.util, json, statistics
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
spw = importlib.util.spec_from_file_location("W", "行业观察池导出网页.py"); W = importlib.util.module_from_spec(spw); spw.loader.exec_module(W)
C, RM = X.C, X.RM
W0 = ("2013-01-04", X.END)
def rows480080():
    d = sorted(json.load(open("data/index_raw/cn480080.json"))["data"]["data"], key=lambda x: x[0]); rows, prev = [], None
    for day, _, h, o, l, c, *_ in d:
        if day > X.END or not c: continue
        o = o or prev or c; h = max(h or 0, o, c); l = min(l or 1e18, o, c)
        rows.append({"date": day, "open": str(o), "high": str(h), "low": str(l), "close": str(c), "adjusted_close": str(c), "share_factor": "1", "cumulative_cash": "0"}); prev = c
    return rows
def show(tag, nav, w):
    m = C.window_metrics(nav, w); ys = m["years"]
    print(f"  {tag:14s} 年化 {m['cagr']*100:6.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:5.2f} 逐年均 {statistics.mean(ys.values())*100:5.1f}% 赚钱 {sum(v>0 for v in ys.values())}/{len(ys)} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in ys.items()))
if __name__ == "__main__":
    C.init()
    p880 = RM.ratio_leg("510880"); r2 = RM.ma_state(RM.ratio(RM.ratio_leg("159915"), p880), 20); h1 = RM.ma_state(RM.ratio(RM.index_series("sh000300"), p880), 20)
    rows = rows480080(); d = X.entry("159259", rows, r2, h1)
    print(f"## 国证成长100全收益（480080）延长，{W0[0]}～{W0[1]}")
    for pl in "AB":
        r = X.sim(d, pl); show(f"{pl} " + ("创业板择时" if pl == "A" else "沪深300择时"), {x["date"]: x["nav"] for x in r["nav"]}, W0)
    base = None; hold = {}
    for x in rows:
        if x["date"] < W0[0]: continue
        v = float(x["close"]); base = base or v; hold[x["date"]] = v / base
    show("一直持有", hold, W0)
    print("\n## 代理核对：ETF 自身数据 vs 指数，同一时段（ETF 第 121 根起）")
    e = W.data_of("159259")
    for pl in "AB":
        re_ = W.run(e, pl); w = (re_["metric"]["first"], X.END); ri = X.sim(d, pl)
        show(f"{pl} ETF", {x["date"]: x["nav"] for x in re_["nav"]}, w); show(f"{pl} 指数", {x["date"]: x["nav"] for x in ri["nav"]}, w)
