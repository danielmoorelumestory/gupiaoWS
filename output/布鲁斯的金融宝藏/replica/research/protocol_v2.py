"""protocol.py 的修正版：只修 07-codex-检验审计.md 指出的客观实现问题，规格不变。
1 统一用交易所日历（沪深300 价格日线），剔除全收益文件里的异常日期；息差缺失日沿用上一个已知读数。
2 E 去掉末尾不完整的月份；换手按权重漂移后的实际调仓量算，两个组合、股债两条腿都收费；回撤按日频算。
3 D 按原定规格：月末估值观测，取最近 750 个交易日范围内的月度点、历史跨度至少 375 个交易日；反转用 250 个交易日；两个指数取共同评价月份。
4 自助法统计量改名，并补一个在「无差别」假设下中心化的单侧比例，四个主检验做 Holm 校正。"""
import numpy as np, pandas as pd
H, MIN_TRAIN, RNG = 120, 60, np.random.default_rng(20261110)
def load(f, col): return pd.read_csv(f, parse_dates=["date"]).set_index("date")[col]
cal = load("data/index_sh000300.csv", "close").loc["2005-04-08":].index            # 交易所日历
def on_cal(x): return x[~x.index.duplicated()].reindex(cal)
def fwd(x, h=H): return x.shift(-(h + 1)) / x.shift(-1) - 1
def month_ends(idx, complete_only=True):
    s = pd.Series(idx, index=idx); me = pd.DatetimeIndex(s.groupby([idx.year, idx.month]).last().values)
    return me[:-1] if complete_only else me                                       # 最后一个月还没走完，不算
def oos(df, y, cols_list):
    df = df.dropna(subset=[y] + sorted({c for cs in cols_list for c in cs})); out = {i: [] for i in range(len(cols_list))}; dates = []
    for yr in sorted(set(df.index.year)):
        cut = pd.Timestamp(yr, 1, 1); tr = df[df["mature"] < cut]; te = df[df.index.year == yr]
        if len(tr) < MIN_TRAIN or te.empty: continue
        for i, cols in enumerate(cols_list):
            X = np.column_stack([np.ones(len(tr))] + [tr[c].values for c in cols]); b = np.linalg.lstsq(X, tr[y].values, rcond=None)[0]
            Xt = np.column_stack([np.ones(len(te))] + [te[c].values for c in cols]); out[i] += list(te[y].values - Xt @ b)
        dates += list(te.index)
    return pd.DataFrame(out, index=dates)
def boot(d, block, seed):
    rng = np.random.default_rng(seed); d = np.asarray(d); n = len(d); k = int(np.ceil(n / block)); means = np.empty(5000)
    for j in range(5000):
        st = rng.integers(0, n, k); means[j] = d[np.concatenate([(s + np.arange(block)) % n for s in st])[:n]].mean()
    return np.percentile(means, [2.5, 97.5]), (means - d.mean() >= d.mean()).mean()   # 区间；中心化后的单侧比例
PVALS = {}
def report(d, name, scale, unit, main=None):
    d = pd.Series(d).dropna(); line = f"  {name}: {len(d)} 个月（{d.index[0].date()}–{d.index[-1].date()}），平均 {d.mean()*scale:+.3f}{unit}"
    for blk in (12, 24):
        ci, p = boot(d.values, blk, 1000 + blk); line += f" | {blk}月区块 95%区间 [{ci[0]*scale:+.3f}, {ci[1]*scale:+.3f}]，中心化单侧比例 {p:.3f}"
        if main and blk == 12: PVALS[main] = p
    print(line)
def mse_gain(err, a, b): return err[a] ** 2 - err[b] ** 2
bondy = on_cal(load("data/cn10y.csv", "cn10y")).ffill(); bw = on_cal(load("data/cbond_treasury_7-10Y_wealth.csv", "value")).ffill()
def tr_index(f): x = load(f, "close"); return on_cal(x[x.index.isin(cal)]).ffill()   # 剔除 2018-06-18、2005-01-01 等非交易日
base = pd.read_csv("data/equity_bond_spread.csv", parse_dates=["date"]).set_index("date")
print(f"日历 {len(cal)} 个交易日；息差表缺 {int(base['spread'].reindex(cal).isna().sum())} 天：{[str(x.date()) for x in cal[base['spread'].reindex(cal).isna()]]}")
sp = base["spread"]; m_ = sp.rolling(750, min_periods=375).mean(); sd_ = sp.rolling(750, min_periods=375).std(ddof=0)
ey = (sp + bondy.reindex(sp.index)); zey_raw = (ey - ey.rolling(750, min_periods=375).mean()) / ey.rolling(750, min_periods=375).std(ddof=0)
d = pd.DataFrame(index=cal); d["z"] = ((sp - m_) / sd_).reindex(cal).ffill(); d["zey"] = zey_raw.reindex(cal).ffill()   # 缺失日沿用上一个已知读数
d["px"] = load("data/index_sh000300.csv", "close").reindex(cal); d["tr"] = tr_index("data/tr_H00300.csv"); d["bw"] = bw; d["y10"] = bondy
d["r250"] = d.px / d.px.shift(250) - 1; d["dy250"] = -(d.y10 - d.y10.shift(250))
d["Ystock"] = fwd(d.tr); d["Ybond"] = fwd(d.bw); d["Y"] = d.Ystock - d.Ybond; d["mature"] = pd.Series(cal, index=cal).shift(-(H + 1))
m = d.loc[month_ends(cal)]
print("\n=== 方向 A（主检验：在前一年涨跌之外，加入息差偏离后预测误差的改善，正数=有用；单位 万分之一）")
e = oos(m, "Y", [[], ["r250"], ["r250", "z"]]); print(f"  MSE: 仅均值 {np.mean(e[0]**2)*1e4:.1f} / 加反转 {np.mean(e[1]**2)*1e4:.1f} / 再加息差 {np.mean(e[2]**2)*1e4:.1f}")
report(mse_gain(e, 1, 2), "M1 → M2", 1e4, "", main="A"); report(mse_gain(e, 0, 1), "（参考）M0 → M1 反转本身", 1e4, "")
print("  事件层面（次日起 120 个交易日，股票全收益 − 国债财富）：")
idx, last = [], -10**9
for i in np.flatnonzero(((sp - m_) / sd_ >= 2).reindex(cal).fillna(False).values):
    if i - last >= 20: idx.append(i)
    last = i
ev = d.iloc[idx][["Ystock", "Ybond", "Y"]]; ok = d.z.notna() & d.Y.notna()
print(f"    9 次平均 股票 {ev.Ystock.mean()*100:+.1f}% 国债 {ev.Ybond.mean()*100:+.1f}% 相对 {ev.Y.mean()*100:+.1f}%，跑赢 {(ev.Y>0).sum()}/{len(ev)}；同期全部日子 相对 {d.Y[ok].mean()*100:+.1f}%，跑赢比例 {(d.Y[ok]>0).mean()*100:.1f}%")
grp, g = [], []
for i in idx:
    if g and i <= g[-1] + H + 1: g.append(i)
    else:
        if g: grp.append(g)
        g = [i]
grp.append(g); gm = [d.Y.iloc[x].mean() for x in grp]
print(f"    按持有期重叠合并后剩 {len(grp)} 组，组均值的平均 {np.mean(gm)*100:+.1f}%，跑赢 {sum(v>0 for v in gm)}/{len(gm)}；逐组剔除后的平均在 {min(np.mean(gm[:k]+gm[k+1:]) for k in range(len(gm)))*100:+.1f}% 到 {max(np.mean(gm[:k]+gm[k+1:]) for k in range(len(gm)))*100:+.1f}% 之间")
print("    各组：", [f"{cal[x[0]].date()}({len(x)}次) {v*100:+.1f}%" for x, v in zip(grp, gm)])
print("\n=== 方向 C（主检验：在反转 + 盈利收益率偏离之外，加入过去一年利率降幅）")
e = oos(m, "Y", [["r250", "zey"], ["r250", "zey", "dy250"]]); print(f"  MSE: {np.mean(e[0]**2)*1e4:.1f} → {np.mean(e[1]**2)*1e4:.1f}"); report(mse_gain(e, 0, 1), "基准 → 加利率降幅", 1e4, "", main="C")
print("\n=== 方向 D（原定规格：月末估值、最近 750 个交易日内的月度点、跨度至少 375 个交易日；共同评价月份）")
def monthly(pe_file, tr_file, px_file):
    pe = pd.read_csv(pe_file, parse_dates=["日期"]).set_index("日期"); pe = pe[pe.index.isin(cal)]
    s = 100 / pe["滚动市盈率"] - bondy.reindex(pe.index); pos = cal.get_indexer(pe.index); z = []
    for j, pj in enumerate(pos):
        w = s[(pos > pj - 750) & (pos <= pj)]; z.append((s.iloc[j] - w.mean()) / w.std(ddof=0) if pj - pos[0] >= 375 and len(w) > 2 else np.nan)
    px = load(px_file, "close").reindex(cal).ffill(); tr = tr_index(tr_file)
    q = pd.DataFrame({"z": z, "r250": (px / px.shift(250) - 1).reindex(pe.index), "Y": (fwd(tr) - fwd(bw)).reindex(pe.index), "mature": pd.Series(cal, index=cal).shift(-(H + 1)).reindex(pe.index)}, index=pe.index)
    return q[q.index.isin(month_ends(cal))]
q3, q5 = monthly("data/csi300_pe_lg.csv", "data/tr_H00300.csv", "data/index_sh000300.csv"), monthly("data/pe_lg_sh000905.csv", "data/tr_H00905.csv", "data/index_sh000905.csv")
start = max(q3.dropna().index[0], q5.dropna().index[0]); q3, q5 = q3[q3.index >= start], q5[q5.index >= start]
e3, e5 = oos(q3, "Y", [["r250"], ["r250", "z"]]), oos(q5, "Y", [["r250"], ["r250", "z"]]); common = e3.index.intersection(e5.index)
report(mse_gain(e5.loc[common], 0, 1), "中证500 M1 → M2", 1e4, "", main="D"); report(mse_gain(e3.loc[common], 0, 1), "沪深300（同口径同月份）", 1e4, "")
print("\n=== 方向 E（仓位 = 50% + clip(z,0,2)/4；与事前固定权重比；单位 每月百分点）")
rs, rb = d.tr.pct_change(), d.bw.pct_change(); me = month_ends(cal); wsig = (0.5 + d.z.clip(0, 2) / 4).loc[me].dropna(); loc = cal.get_indexer
def run(cost):
    rows, daily = [], {k: [] for k in ("dyn", "fix", "half", "stock")}; pre = {}
    for i in range(len(wsig) - 1):
        t0, t1 = wsig.index[i], wsig.index[i + 1]; a, b = loc([t0])[0] + 1, loc([t1])[0] + 1
        hist = wsig[wsig.index < pd.Timestamp(t0.year, 1, 1)]
        if len(hist) < MIN_TRAIN or b >= len(cal): continue
        S_, B_ = rs.iloc[a + 1:b + 1], rb.iloc[a + 1:b + 1]; cs, cb = (1 + S_).cumprod(), (1 + B_).cumprod(); out = {}
        for k, w in (("dyn", wsig.iloc[i]), ("fix", hist.mean()), ("half", 0.5), ("stock", 1.0)):
            trade = abs(w - pre[k]) if k in pre else 0.0                         # 首次建仓不计；之后按漂移后的实际权重算调仓量
            path = (1 - 2 * cost * trade) * (w * cs + (1 - w) * cb)              # 卖一边买一边，两条腿都收费，月初扣
            out[k] = path.iloc[-1] - 1; daily[k].append(path / path.shift(1).fillna(1 - 0) if False else path)
            pre[k] = w * cs.iloc[-1] / (w * cs.iloc[-1] + (1 - w) * cb.iloc[-1]); out[k + "_t"] = trade
        rows.append((cal[b], wsig.iloc[i], hist.mean(), out)); 
    p = pd.DataFrame([{**{"w": w, "wf": wf}, **o} for _, w, wf, o in rows], index=[r[0] for r in rows])
    def dd(k):
        eq, lvl = [1.0], 1.0
        for path in daily[k]: eq += list(lvl * path.values); lvl *= path.iloc[-1]
        eq = np.array(eq); return (eq / np.maximum.accumulate(eq) - 1).min()
    return p, dd
for cost in (0.0, 0.001):
    p, dd = run(cost); report(p.dyn - p.fix, f"单边 {cost*1e4:.0f}bp 动态 − 事前固定权重", 100, "%", main="E" if cost == 0 else None)
    def ann(r): return f"年化 {((1 + r).prod() ** (12 / len(r)) - 1)*100:.1f}%"
    print(f"    动态（平均股票 {p.w.mean()*100:.0f}%，月均调仓 {p.dyn_t.mean()*100:.1f}%）{ann(p.dyn)} 波动 {p.dyn.std()*np.sqrt(12)*100:.1f}% 日频最大回撤 {dd('dyn')*100:.1f}%；事前固定（{p.wf.mean()*100:.0f}%，调仓 {p.fix_t.mean()*100:.1f}%）{ann(p.fix)} 波动 {p.fix.std()*np.sqrt(12)*100:.1f}% 回撤 {dd('fix')*100:.1f}%；五五开 {ann(p.half)} 回撤 {dd('half')*100:.1f}%；全仓股票 {ann(p.stock)} 回撤 {dd('stock')*100:.1f}%")
print("\n=== Holm 校正（四个主检验，12 月区块，中心化单侧比例；B 未做）")
order = sorted(PVALS.items(), key=lambda x: x[1]); run_max = 0
for r, (k, p) in enumerate(order): adj = min(1, p * (len(order) - r)); run_max = max(run_max, adj); print(f"  {k}: 原始 {p:.3f} → 校正后 {run_max:.3f}  {'通过' if run_max < 0.05 else '未通过'}")
