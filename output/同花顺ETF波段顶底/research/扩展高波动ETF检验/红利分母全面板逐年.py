"""事后追加（2026-11-16，用户追问：510880 是平均更好还是每年都更好）。数据与规则同 红利分母全面板对照.py，只把结果按自然年拆开：
每年：全部面板/高波动子集的等权组合当年收益与当年最大回撤；逐只当年收益差（替代−D0）的平均，以及替代更好的只数占比。历史统计，不构成投资建议。"""
import importlib.util, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("P", "红利分母全面板对照.py"); P = importlib.util.module_from_spec(sp); sp.loader.exec_module(P)
C = P.C
def _job(key): return P.job(key)
def ymdd(nav):
    peak, mdd = 0, 0.0
    for v in nav.values(): peak = max(peak, v); mdd = min(mdd, v/peak - 1)
    return mdd
if __name__ == "__main__":
    C.init(); keys = list(C.T.M.PANEL)
    with Pool(8) as p: res = dict(p.map(_job, keys))
    for plan, title in (("Y1", "Y1 + 创业板÷分母"), ("金叉", "只认金叉 + 沪深300÷分母")):
        for sub, cond in (("全部面板", lambda v: True), ("高波动(≥31%)", lambda v: v >= 0.31)):
            print(f"\n## {title}｜{sub}")
            print("  年份  " + "  ".join(f"{k:>16}" for k in P.KEYS) + "   ｜ 逐只：替代更好的占比（红利+低波/红利4/红利7）")
            for y in range(2020, 2027):
                W = (f"{y}-01-01", min(f"{y}-12-31", P.X.END))
                codes = [c for c, o in res.items() if cond(o["vol"]) and sum(1 for d in o[(plan, "D0")] if W[0] <= d <= W[1]) >= 120]
                cells = []
                for k in P.KEYS:
                    nav = C.portfolio(codes, {c: C.daily(res[c][(plan, k)]) for c in codes}, W)
                    cells.append(f"{(list(nav.values())[-1]-1)*100:+6.1f}% /{ymdd(nav)*100:5.1f}%")
                wins = []
                for k in P.KEYS[1:]:
                    d = [(C.window_metrics(res[c][(plan, k)], W) or {}).get("cagr", 0) - (C.window_metrics(res[c][(plan, "D0")], W) or {}).get("cagr", 0) for c in codes]
                    wins.append(f"{sum(x > 1e-9 for x in d)}/{len(d)}")
                print(f"  {y}  " + "  ".join(f"{c:>16}" for c in cells) + "   ｜ " + " ".join(wins))
