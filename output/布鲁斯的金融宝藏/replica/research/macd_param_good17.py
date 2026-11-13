"""MACD优秀 17 只上的参数比较。运行前写定，跑完不改：每只 ETF 从上市后第 70 个交易日到 2026-11-10，按交易日对半分为前半/后半。
①全组统一选参：前半段各 ETF 年化中位数最高（并列看均值）的组合，到后半段对照 12/26/9；②逐只各自选参（前半最优）到后半；
③各维度平均的前后半方向；④事先给的三组慢参数 10/50/15、15/35/12、20/40/12 与 12/26/9 的全期、前半、后半。
网格与撮合同 macd_param_scan.py。注意：17 只是按 12/26/9 全期表现选出的，标准参数在此先天占优。"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "research")
exec(open("research/macd_param_scan.py", encoding="utf-8").read().split("D = {}")[0])
G17 = ["515790","159851","562500","512480","588200","513130","512200","159852","516160","512880","513090","159667","159792","159883","512070","159865","159869"]
NAMES = {c: n for c, n, *_ in ITEMS}
STD = (12, 26, 9); SLOW = [(10, 50, 15), (15, 35, 12), (20, 40, 12)]
rows = []
for code in G17:
    d, dv, mm, c = load(code); o, cl = d.open.values, d.close.values
    on = np.r_[1.0, (o[1:] + dv[1:]) * mm[1:] / cl[:-1]]; intra = cl / o
    i0 = 70; mid = i0 + (len(d) - i0) // 2; spans = {"全期": (i0, len(d)), "前半": (i0, mid), "后半": (mid, len(d))}
    cache = {}
    for p in GRID:
        f, s, g = p
        for n in (f, s):
            if n not in cache: cache[n] = ema(c, n)
        dif = cache[f] - cache[s]; st = (dif > ema(dif, g)).astype(np.int8)
        r = dict(code=code, p=p, split=str(d.index[mid].date()))
        for k, (a, b) in spans.items():
            nv = nav(st, on, intra, a, b); r[k] = ann(nv, (d.index[b - 1] - d.index[a]).days); r[k + "dd"] = (nv / np.maximum.accumulate(np.maximum(nv, 1)) - 1).min()
        rows.append(r)
T = pd.DataFrame(rows); T.to_pickle("research/macd_param_good17.pkl")
P = lambda v: f"{v*100:+.2f}%"
agg = T.groupby("p")[["前半", "后半", "全期"]].median(); aggm = T.groupby("p")[["前半", "后半", "全期"]].mean()
order = agg.assign(m=aggm["前半"]).sort_values(["前半", "m"], ascending=False); best = order.index[0]
def line(p, tag):
    x = T[T.p == p].set_index("code"); y = T[T.p == STD].set_index("code")
    return (f"  {tag:<14}{str(p):<14} 前半 中位 {P(x['前半'].median())} 均值 {P(x['前半'].mean())}｜后半 中位 {P(x['后半'].median())} 均值 {P(x['后半'].mean())} 回撤中位 {x['后半dd'].median()*100:.1f}%"
            + ("" if p == STD else f" 胜标准 {(x['后半'] > y['后半']).sum()}/17") + f"｜全期 均值 {P(x['全期'].mean())}")
print(f"17 只，各自对半切分（切分日从 {T.split.min()} 到 {T.split.max()}）；网格 {len(GRID)} 组")
print("\n① 全组统一选参（前半段中位数最高）")
print(line(STD, "标准")); print(line(best, "前半第1"))
for i in range(1, 5): print(line(order.index[i], f"前半第{i+1}"))
rk2 = agg.sort_values("后半", ascending=False)
print(f"  前半名次与后半名次秩相关 {agg['前半'].rank().corr(agg['后半'].rank()):+.2f}；后半段里 前半第1 排第 {list(rk2.index).index(best)+1}，12/26/9 排第 {list(rk2.index).index(STD)+1}（共 {len(agg)}）；12/26/9 在前半排第 {list(order.index).index(STD)+1}")
B = T.groupby("p")["后半"].mean(); others = [p for p in B.index if p != STD]
wins = T.groupby("p").apply(lambda z: (z.set_index("code")["后半"] > T[T.p == STD].set_index("code")["后半"].reindex(z.code).values).sum())
print(f"  后半段 194 个非标准组合中：均值高于标准 {(B[others] > B[STD]).mean():.0%}；胜 ≥9/17 {(wins[others] >= 9).mean():.0%}")
print("\n② 逐只各自选参（前半最优 → 后半）")
pick = T.loc[T.groupby("code")["前半"].idxmax()].set_index("code"); std = T[T.p == STD].set_index("code").reindex(pick.index)
for c, r in pick.iterrows(): print(f"  {c} {NAMES[c][:8]:<9} 选 {str(r.p):<13} 前半 {P(r['前半'])}（标准 {P(std.loc[c, '前半'])}） 后半 {P(r['后半'])}（标准 {P(std.loc[c, '后半'])}）")
print(f"  合计：前半均值 {P(pick['前半'].mean())}（标准 {P(std['前半'].mean())}）；后半均值 {P(pick['后半'].mean())}（标准 {P(std['后半'].mean())}），后半胜标准 {(pick['后半'] > std['后半']).sum()}/17")
print("\n③ 各维度平均（17 只中位数：前半 → 后半）")
for k, vals in ((0, [5, 8, 10, 12, 15, 20]), (1, [20, 26, 30, 35, 40, 50, 60]), (2, [5, 7, 9, 12, 15])):
    print(f"  {['快线','慢线','信号'][k]}：" + "  ".join(f"{v}: {agg[[p[k] == v for p in agg.index]]['前半'].mean()*100:+.1f}→{agg[[p[k] == v for p in agg.index]]['后半'].mean()*100:+.1f}" for v in vals))
print("\n④ 事先给定的慢参数")
for p in [STD] + SLOW: print(line(p, "标准" if p == STD else "慢参数"))
print("\n逐只全期年化（12/26/9 / 10/50/15 / 15/35/12 / 20/40/12）与后半段")
W = T[T.p.isin([STD] + SLOW)].pivot(index="code", columns="p")
for c in G17: print(f"  {c} {NAMES[c][:8]:<9} 全期 " + " ".join(f"{W.loc[c, ('全期', p)]*100:+6.1f}" for p in [STD] + SLOW) + "  后半 " + " ".join(f"{W.loc[c, ('后半', p)]*100:+6.1f}" for p in [STD] + SLOW))
