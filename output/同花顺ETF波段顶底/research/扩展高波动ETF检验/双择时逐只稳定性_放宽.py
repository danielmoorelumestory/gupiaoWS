"""事后放宽（2026-11-18）：上一版要求 2021 年前至少 2 个完整年，只剩 23 只可比。此处不分前后段，所有 ETF 只要有 ≥3 个完整年：
全期卡玛高于更好的单策略 且 逐年胜 ≥60% 且 无一年差 10pp 以上 → 记为稳定更好；反向同理。属事后放宽，结论仅供参考。历史统计，不构成投资建议。"""
import importlib.util
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("S", "双择时逐只稳定性.py"); S = importlib.util.module_from_spec(sp); sp.loader.exec_module(S)
C, V = S.C, S.V
def _job(k): return S.P.job(k)
if __name__ == "__main__":
    C.init(); names = {k[1:]: v["item"]["name"] for k, v in C.T.M.PANEL.items()}
    with Pool(8) as p: res = dict(p.map(_job, list(C.T.M.PANEL)))
    tot = 0; G = {v: [] for v in V}; B = {v: 0 for v in V}
    for c in res:
        if not res[c]["单用A"][0]: continue
        ca, cb = (C.window_metrics(res[c][k][0], S.WF)["cal"] for k in ("单用A", "单用B")); ref = "单用A" if ca >= cb else "单用B"
        yb = S.yearly(res[c][ref][0]); ys = sorted(yb)[1:]; ys = [y for y in ys if y != "2026"]
        if len(ys) < 3: continue
        tot += 1
        for v in V:
            ya = S.yearly(res[c][V[v]][0]); d = [ya[y] - yb[y] for y in ys]; cal = C.window_metrics(res[c][V[v]][0], S.WF)["cal"]
            win = sum(x > 0 for x in d)/len(d)
            if cal > max(ca, cb) and win >= 0.6 and min(d) > -0.10: G[v].append((c, names[c], ref, cal, max(ca, cb), win, " ".join(f"{y[2:]}:{x*100:+.0f}" for y, x in zip(ys, d))))
            if cal < max(ca, cb) and win <= 0.4 and max(d) < 0.10: B[v] += 1
    print(f"≥3 个完整年的 ETF：{tot} 只")
    for v in V:
        print(f"\n## {v}：双择时稳定更好 {len(G[v])} 只 ｜ 单策略稳定更好 {B[v]} 只")
        for g in sorted(G[v], key=lambda x: x[4] - x[3]): print(f"  {g[0]} {g[1]:<12} 对照={g[2]} 卡玛 {g[3]:.2f} vs {g[4]:.2f} 逐年胜 {g[5]*100:.0f}% ｜ 逐年差 {g[6]}")
