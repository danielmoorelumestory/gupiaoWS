"""用户要求（2026-11-18）：双择时并行对照按年统计；目标是每年收益都比较好。（事后追加的拆分统计，不改规则）
沿用 双择时并行对照.py 的策略与校验；增加「现行分组」= A 组用策略A、B 组用策略B（两组都有的按 A）。
每年等权组合收益（每日再平衡），并统计：亏损年数、收益<5% 的年数、最差年、逐年收益标准差。全历史每只从各自上市满预热起算。
历史统计，不构成投资建议。"""
import importlib.util, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("D", "双择时并行对照.py"); D = importlib.util.module_from_spec(sp); sp.loader.exec_module(D)
C, X, GA, GB = D.C, D.X, D.GA, D.GB
def _job(k): return D.job(k)
def row(res, codes, name, W):
    pick = (lambda c: "单用A" if c in GA else "单用B") if name == "现行分组" else (lambda c: name)
    cs = [c for c in codes if res[c][pick(c)][0]]
    return C.metrics(C.portfolio(cs, {c: C.daily(res[c][pick(c)][0]) for c in cs}, W))
if __name__ == "__main__":
    C.init()
    with Pool(8) as p: res = dict(p.map(_job, list(C.T.M.PANEL)))
    W = ("1900-01-01", X.END)
    ab = list(dict.fromkeys([c for c in GA + GB if c in res]))
    panel = [c for c in res if res[c]["单用A"][0]]
    for title, cs, names in (("A 组", [c for c in GA if c in res], list(D.VARS)), ("B 组", [c for c in GB if c in res], list(D.VARS)),
                             ("A+B 合并 24 只", ab, ["现行分组"] + list(D.VARS)), ("全部面板 78 只", panel, list(D.VARS))):
        ms = {n: row(res, cs, n, W) for n in names}; yrs = sorted({y for m in ms.values() for y in m["years"]})
        print(f"\n## {title}：每年等权组合收益（%）")
        print("  " + f"{'':<14}" + "".join(f"{y:>6}" for y in yrs) + "  ｜亏损年 <5%年 最差年 标准差 全期年化 回撤")
        for n, m in ms.items():
            v = [m["years"].get(y) for y in yrs]; vv = [x for x in v if x is not None]
            print("  " + f"{n:<14}" + "".join(f"{x*100:6.0f}" if x is not None else "     -" for x in v)
                  + f"  ｜{sum(x < 0 for x in vv):4d} {sum(x < 0.05 for x in vv):5d} {min(vv)*100:+6.1f} {statistics.pstdev(vv)*100:6.1f} {m['cagr']*100:6.1f}% {m['mdd']*100:6.1f}%")
