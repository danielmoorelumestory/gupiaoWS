"""MACD 参数扫描，前段选参、后段检验。运行前写定，跑完不改：
网格：快 {5,8,10,12,15,20} × 慢 {20,26,30,35,40,50,60} × 信号 {5,7,9,12,15}，慢 ≥ 快+8。
发现段 2016-01-04 至 2022-12-30（起点 max(上市后第 70 个交易日, 2016-01-04)，需 ≥2 年）；验证段 2023-01-03 至 2026-11-10（2023-01-03 前已有 ≥60 个交易日的固定池）。
选参规则：发现段各 ETF 年化的中位数最高（并列看均值）。验证段只看一次，对照 12/26/9。另报：参数邻域稳健性、逐只 ETF 各自选参的验证表现。
口径：codex_macd_common.load 比例除权价算信号；未复权开盘成交，分红拆分归属前日持仓；t 收盘定、t+1 开盘成交；单边 0.1%；空仓零息。"""
import sys, json, itertools, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load
ITEMS = json.load(open("data/page_etfs_plus.json"))
res = pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}); GOOD = set(res.loc[res.good.astype(str) == "True", "code"])
GRID = [(f, s, g) for f, s, g in itertools.product([5, 8, 10, 12, 15, 20], [20, 26, 30, 35, 40, 50, 60], [5, 7, 9, 12, 15]) if s >= f + 8]
COST = 0.001
def ema(x, n):
    a = 2 / (n + 1); z = np.empty(len(x)); z[0] = x[0]
    for i in range(1, len(x)): z[i] = z[i - 1] + a * (x[i] - z[i - 1])
    return z
def nav(st, on, intra, i0, i1):
    """st: 收盘后目标仓位；第 k 天：持有→隔夜 on[k]、日内 intra[k]；买入只吃日内并扣费，卖出只吃隔夜并扣费。"""
    # 第 k 天开盘时的目标仓位 = st[k-1]；前一天收盘后是否在持仓 = st[k-2]；起点当天从现金开始
    hold_now = st[i0 - 1:i1 - 1].astype(bool); hold_before = np.r_[False, st[i0 - 1:i1 - 2].astype(bool)]
    r = np.ones(i1 - i0)
    both = hold_before & hold_now; buy = ~hold_before & hold_now; sell = hold_before & ~hold_now
    r[both] = on[i0:i1][both] * intra[i0:i1][both]
    r[buy] = intra[i0:i1][buy] * (1 - COST)
    r[sell] = on[i0:i1][sell] * (1 - COST)
    return np.cumprod(r)
def ann(n, days): return n[-1] ** (365.25 / max(days, 1)) - 1
D = {}
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); o, cl = d.open.values, d.close.values
    on = np.r_[1.0, (o[1:] + dv[1:]) * mm[1:] / cl[:-1]]; intra = cl / o
    a0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); a1 = d.index.searchsorted(pd.Timestamp("2022-12-31"))
    b0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
    D[code] = dict(name=name, d=d, c=c, on=on, intra=intra, A=(a0, a1) if a1 - a0 >= 488 else None, B=(b0, len(d)) if b0 >= 60 else None)
EMA = {}
rows = []
for code, z in D.items():
    c = z["c"]; cache = {}
    for f, s, g in GRID:
        if f not in cache: cache[f] = ema(c, f)
        if s not in cache: cache[s] = ema(c, s)
        dif = cache[f] - cache[s]; st = (dif > ema(dif, g)).astype(np.int8)
        r = dict(code=code, p=(f, s, g))
        for k in ("A", "B"):
            if z[k]:
                i0, i1 = z[k]; n = nav(st, z["on"], z["intra"], i0, i1)
                r[k] = ann(n, (z["d"].index[i1 - 1] - z["d"].index[i0]).days); r[k + "dd"] = (n / np.maximum.accumulate(np.maximum(n, 1)) - 1).min()
        rows.append(r)
T = pd.DataFrame(rows); T.to_pickle("research/macd_param_scan.pkl")
STD = (12, 26, 9)
A = T.dropna(subset=["A"]); nA = A.code.nunique()
agg = A.groupby("p").A.agg(["median", "mean"]).sort_values(["median", "mean"], ascending=False)
best = agg.index[0]
print(f"网格 {len(GRID)} 组；发现段 {nA} 只，验证段 {T.dropna(subset=['B']).code.nunique()} 只")
print(f"\n发现段（2016–2022）各组年化中位数排名前 10，及 12/26/9 的名次：")
for i, (p, r) in enumerate(agg.head(10).iterrows()): print(f"  {i+1:>2}. {p}  中位 {r['median']*100:+.2f}%  均值 {r['mean']*100:+.2f}%")
rk = list(agg.index).index(STD) + 1
print(f"  12/26/9 名次 {rk}/{len(agg)}，中位 {agg.loc[[STD], 'median'].iloc[0]*100:+.2f}%  均值 {agg.loc[[STD], 'mean'].iloc[0]*100:+.2f}%")
print(f"  全部组合中位数的分布：最低 {agg['median'].min()*100:+.2f}%，四分位 {agg['median'].quantile(.25)*100:+.2f}% / {agg['median'].median()*100:+.2f}% / {agg['median'].quantile(.75)*100:+.2f}%，最高 {agg['median'].max()*100:+.2f}%")
B = T.dropna(subset=["B"]); aggB = B.groupby("p").B.agg(["median", "mean"])
def show(p, tag):
    x = B[B.p == p].set_index("code"); y = B[B.p == STD].set_index("code")
    print(f"  {tag} {p}：年化中位 {x.B.median()*100:+.2f}% 均值 {x.B.mean()*100:+.2f}% 回撤中位 {x.Bdd.median()*100:.1f}%  胜 12/26/9 {(x.B > y.B.reindex(x.index)).sum()}/{len(x)}")
print(f"\n验证段（2023-01-03 起，{B.code.nunique()} 只）")
show(STD, "标准"); show(best, "发现段最优")
for i in range(1, 5): show(agg.index[i], f"发现段第{i+1}")
print(f"  发现段名次与验证段名次的秩相关（全部 {len(agg)} 组）：{agg['median'].rank().corr(aggB['median'].reindex(agg.index).rank()):+.2f}")
rkB = aggB.sort_values(["median", "mean"], ascending=False); print(f"  验证段里：发现段最优排第 {list(rkB.index).index(best)+1}，12/26/9 排第 {list(rkB.index).index(STD)+1}（共 {len(rkB)}）")
print(f"  验证段事后最优 {rkB.index[0]}：中位 {rkB.iloc[0]['median']*100:+.2f}%（这是看了答案才知道的）")
f0, s0, g0 = best
nb = [p for p in agg.index if abs(GRID.index(p) - GRID.index(best)) < 999 and (abs([5,8,10,12,15,20].index(p[0]) - [5,8,10,12,15,20].index(f0)) <= 1) and (abs([20,26,30,35,40,50,60].index(p[1]) - [20,26,30,35,40,50,60].index(s0)) <= 1) and (abs([5,7,9,12,15].index(p[2]) - [5,7,9,12,15].index(g0)) <= 1)]
print(f"\n稳健性：最优参数相邻格（各维 ±1 档）共 {len(nb)} 组，发现段中位数 {agg.loc[nb, 'median'].min()*100:+.2f}% ~ {agg.loc[nb, 'median'].max()*100:+.2f}%，验证段中位数 {aggB.loc[nb, 'median'].min()*100:+.2f}% ~ {aggB.loc[nb, 'median'].max()*100:+.2f}%")
print("\n按维度平均（发现段中位数 → 验证段中位数）：")
for k, vals in ((0, [5, 8, 10, 12, 15, 20]), (1, [20, 26, 30, 35, 40, 50, 60]), (2, [5, 7, 9, 12, 15])):
    nm = ["快线", "慢线", "信号"][k]
    print(f"  {nm}：" + "  ".join(f"{v}: {agg[[p[k] == v for p in agg.index]]['median'].mean()*100:+.2f}→{aggB[[p[k] == v for p in aggB.index]]['median'].mean()*100:+.2f}" for v in vals))
# 逐只各自选参
both = T.dropna(subset=["A", "B"])
pick = both.loc[both.groupby("code").A.idxmax()].set_index("code")
std = both[both.p == STD].set_index("code").reindex(pick.index)
print(f"\n逐只各自选参（{len(pick)} 只，发现段各自最优）：发现段年化均值 {pick.A.mean()*100:+.2f}%（12/26/9 {std.A.mean()*100:+.2f}%）；"
      f"验证段年化均值 {pick.B.mean()*100:+.2f}%、中位 {pick.B.median()*100:+.2f}%（12/26/9 {std.B.mean()*100:+.2f}% / {std.B.median()*100:+.2f}%），胜 12/26/9 {(pick.B > std.B).sum()}/{len(pick)}")
gp = pick[pick.index.isin(GOOD)]; gs = std[std.index.isin(GOOD)]
print(f"  其中 MACD优秀 {len(gp)} 只：验证段均值 {gp.B.mean()*100:+.2f}%（12/26/9 {gs.B.mean()*100:+.2f}%），胜 {(gp.B > gs.B).sum()}/{len(gp)}")
x = B[B.p == best].set_index("code"); y = B[B.p == STD].set_index("code")
print(f"\nMACD优秀 在验证段：发现段最优 {best} 均值 {x[x.index.isin(GOOD)].B.mean()*100:+.2f}%，12/26/9 {y[y.index.isin(GOOD)].B.mean()*100:+.2f}%")
