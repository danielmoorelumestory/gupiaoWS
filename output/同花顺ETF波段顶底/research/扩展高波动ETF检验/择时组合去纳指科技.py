"""用户决定（2026-11-18）：159509 纳指科技（美股，与 A 股择时无逻辑关联）移出 B 组与择时组合。
重算择时组合（10 只去掉 159509 后 9 只，不补人）的网页说明数字：2020 年起 ETF 版、2013 年起指数延长版；先复现 10 只原数字作校验。
口径与 指数延长回测.py 完全相同。历史统计，不构成投资建议。"""
import importlib.util, json
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
def _init(): C.init()
def _etf(k): return C.work(k)
def _idx(c): return X.work(c)
if __name__ == "__main__":
    C.init(); ten = [m["code"] for m in json.load(open("AB组合_10只.json"))["members"]]
    keys = [k for k in C.T.M.PANEL if k[1:] in ten]
    with Pool(8, initializer=_init) as p: etf = p.map(_etf, keys)
    with Pool(8) as p: idx = p.map(_idx, [c for c in X.INDEX if c in ten])
    RE = {c: C.daily(nav) for c, nav, _ in etf}; HE = {c: C.daily(h) for c, _, h in etf}
    RI = {c: C.daily(nav) for c, nav, _, _ in idx}; HI = {c: C.daily(h) for c, _, h, _ in idx}
    R = {**RE, **RI}; H = {**HE, **HI}
    def show(t, mem, Rs, w):
        m = C.metrics(C.portfolio(mem, Rs, w))
        print(f"  {t:<26} 年化 {m['cagr']*100:5.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:.2f} 赚钱年 {m['pos']}/{len(m['years'])} 最差年 {m['worst']*100:+5.1f}% ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    nine = [c for c in ten if c != "159509"]
    for t, mem in (("10 只（原）", ten), ("9 只（去 159509）", nine)):
        show(t + " ETF 2020 起", mem, RE, ("2020-01-02", X.END)); show(t + " 延长 2013 起", mem, R, ("2013-01-04", X.END)); show(t + " 延长 一直持有", mem, H, ("2013-01-04", X.END))
