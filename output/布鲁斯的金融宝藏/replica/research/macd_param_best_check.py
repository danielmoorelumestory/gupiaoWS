"""发现段最优 15/26/9 在验证段相对 12/26/9 的优势是否超出随机：①逐只差的分布；②195 组里随便挑一组“胜标准”的概率；③组合月度收益差的 6 个月分块自助区间。"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "research")
src = open("research/macd_param_scan.py", encoding="utf-8").read().split("EMA = {}")[0]
exec(src)
T = pd.read_pickle("research/macd_param_scan.pkl"); B = T.dropna(subset=["B"])
STD, BEST = (12, 26, 9), (15, 26, 9)
x = B[B.p == BEST].set_index("code").B; y = B[B.p == STD].set_index("code").B.reindex(x.index); dlt = x - y
print(f"① 逐只年化差（15/26/9 − 12/26/9，45 只）：均值 {dlt.mean()*100:+.2f}，中位 {dlt.median()*100:+.2f}，最小 {dlt.min()*100:+.1f}，最大 {dlt.max()*100:+.1f}，标准差 {dlt.std()*100:.1f} 个百分点；胜 {(dlt > 0).sum()}/45")
g = B.groupby("p"); wins = g.apply(lambda z: (z.set_index("code").B > B[B.p == STD].set_index("code").B.reindex(z.code).values).sum())
means = g.B.mean(); sm = means[STD]
others = [p for p in means.index if p != STD]
print(f"② 验证段 194 个非标准组合中：胜 ≥27/45 只的 {(wins[others] >= 27).mean():.0%}；年化均值高于标准的 {(means[others] > sm).mean():.0%}；两者都满足 {((wins[others] >= 27) & (means[others] > sm)).mean():.0%}")
# ③ 组合（初始等额）月度收益差
def port(p):
    navs = {}
    for code, z in D.items():
        if not z["B"]: continue
        c = z["c"]; f, s, g_ = p; dif = ema(c, f) - ema(c, s); st = (dif > ema(dif, g_)).astype(np.int8)
        i0, i1 = z["B"]; navs[code] = pd.Series(nav(st, z["on"], z["intra"], i0, i1), index=z["d"].index[i0:i1])
    return pd.DataFrame(navs).ffill().mean(axis=1)
pb, ps = port(BEST), port(STD)
mb, ms = pb.resample("ME").last().pct_change().fillna(pb.resample("ME").last().iloc[0] - 1), ps.resample("ME").last().pct_change().fillna(ps.resample("ME").last().iloc[0] - 1)
diff = (np.log1p(mb) - np.log1p(ms)).values; n = len(diff); rng = np.random.default_rng(0); L = 6; sims = []
for _ in range(5000):
    idx = np.concatenate([np.arange(s, s + L) % n for s in rng.integers(0, n, n // L + 1)])[:n]; sims.append(diff[idx].mean() * 12)
ann = lambda s: s.iloc[-1] ** (365.25 / (s.index[-1] - s.index[0]).days) - 1
print(f"③ 初始等额组合：15/26/9 年化 {ann(pb)*100:+.2f}%，12/26/9 {ann(ps)*100:+.2f}%；月度对数收益差年化 {diff.mean()*12*100:+.2f} 个百分点，6 个月分块自助 95% 区间 [{np.quantile(sims,.025)*100:+.2f}, {np.quantile(sims,.975)*100:+.2f}]，差为正的月份 {(diff > 0).mean():.0%}（共 {n} 个月）")
