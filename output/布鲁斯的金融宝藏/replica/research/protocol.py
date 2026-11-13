"""按 06-codex-息差优化方案.md 第三节锁定的协议检验方向 A、C、D、E。
月末观测；目标从下一交易日收盘起算 120 个交易日；扩展训练、每年年初更新、至少 60 个已成熟标签；
成对时间区块自助法（12 个月，24 个月作敏感性）。不搜索任何参数。"""
import numpy as np, pandas as pd
H, MIN_TRAIN, RNG = 120, 60, np.random.default_rng(20261110)
def load(f, col): return pd.read_csv(f, parse_dates=["date"]).set_index("date")[col]
def zscore(x, w, mp): m = x.rolling(w, min_periods=mp).mean(); sd = x.rolling(w, min_periods=mp).std(ddof=0); return (x - m) / sd
def fwd(x, h=H): return x.shift(-(h + 1)) / x.shift(-1) - 1          # 下一交易日收盘买入，持有 h 日
def month_ends(idx): s = pd.Series(idx, index=idx); return pd.DatetimeIndex(s.groupby([idx.year, idx.month]).last().values)
def oos(df, y, cols_list):
    """df: 月末特征，带 mature(标签成熟日)。返回各模型的样本外预测误差。"""
    df = df.dropna(subset=[y] + sorted({c for cs in cols_list for c in cs})); out = {i: [] for i in range(len(cols_list))}; dates = []
    for yr in sorted(set(df.index.year)):
        cut = pd.Timestamp(yr, 1, 1); tr = df[df["mature"] < cut]; te = df[df.index.year == yr]
        if len(tr) < MIN_TRAIN or te.empty: continue
        for i, cols in enumerate(cols_list):
            X = np.column_stack([np.ones(len(tr))] + [tr[c].values for c in cols]); b = np.linalg.lstsq(X, tr[y].values, rcond=None)[0]
            Xt = np.column_stack([np.ones(len(te))] + [te[c].values for c in cols]); out[i] += list(te[y].values - Xt @ b)
        dates += list(te.index)
    return pd.DataFrame({i: v for i, v in out.items()}, index=dates)
def block_ci(d, block):
    d = np.asarray(d); n = len(d); k = int(np.ceil(n / block)); means = []
    for _ in range(5000):
        st = RNG.integers(0, n, k); idx = np.concatenate([(s + np.arange(block)) % n for s in st])[:n]; means.append(d[idx].mean())
    means = np.array(means); return np.percentile(means, [2.5, 97.5]), (means <= 0).mean()
def compare(err, a, b, name):
    d = err[a] ** 2 - err[b] ** 2          # 正数 = 后一个模型更好
    line = f"  {name}: 样本外 {len(d)} 个月（{err.index[0].date()}–{err.index[-1].date()}），MSE {np.mean(err[a]**2)*1e4:.1f} → {np.mean(err[b]**2)*1e4:.1f}，改善 {d.mean()*1e4:+.2f}"
    for blk in (12, 24):
        ci, p = block_ci(d.values, blk); line += f" | {blk}月区块 95%区间 [{ci[0]*1e4:+.2f}, {ci[1]*1e4:+.2f}] 不为正的概率 {p:.2f}"
    print(line); return d.mean()
bondy = load("data/cn10y.csv", "cn10y"); bw = load("data/cbond_treasury_7-10Y_wealth.csv", "value")
base = pd.read_csv("data/equity_bond_spread.csv", parse_dates=["date"]).set_index("date")
d = pd.DataFrame({"spread": base["spread"], "px": base["index"]}); d["tr"] = load("data/tr_H00300.csv", "close").reindex(d.index).ffill()
d["bw"] = bw.reindex(d.index).ffill(); d["y10"] = bondy.reindex(d.index).ffill()
d["z"] = zscore(d.spread, 750, 375); d["zey"] = zscore(d.spread + d.y10, 750, 375)
d["r250"] = d.px / d.px.shift(250) - 1; d["dy250"] = -(d.y10 - d.y10.shift(250))
d["Ystock"] = fwd(d.tr); d["Ybond"] = fwd(d.bw); d["Y"] = d.Ystock - d.Ybond; d["Ypx"] = fwd(d.px)
d["mature"] = pd.Series(d.index, index=d.index).shift(-(H + 1))
m = d.loc[month_ends(d.index)]
print("=== 方向 A：股票全收益 − 国债财富收益（120 日），息差在简单反转之外有没有增量")
e = oos(m, "Y", [[], ["r250"], ["r250", "z"]])
compare(e, 0, 1, "M0 仅均值 → M1 加前一年涨跌"); a_gain = compare(e, 1, 2, "M1 → M2 再加息差偏离(主检验)"); compare(e, 0, 2, "M0 → M2")
e = oos(m, "Ystock", [[], ["r250"], ["r250", "z"]]); compare(e, 1, 2, "（参考）目标换成股票全收益本身")
e = oos(m, "Y", [[], ["z"]]); compare(e, 0, 1, "（参考）不控制反转，只用息差偏离")
ok = d.z.notna() & d.Y.notna(); print(f"  同期基准（全部日子）：股票 {d.Ystock[ok].mean()*100:+.1f}%  国债 {d.Ybond[ok].mean()*100:+.1f}%  相对 {d.Y[ok].mean()*100:+.1f}%，股票跑赢的比例 {(d.Y[ok]>0).mean()*100:.0f}%")
idx, last = [], -10**9
for i in np.flatnonzero((d.z >= 2).values):
    if i - last >= 20: idx.append(i)
    last = i
ev = d.iloc[idx][["Ystock", "Ybond", "Y", "r250"]]; print("  触上轨事件（次日起 120 日）：\n" + (ev * 100).round(1).to_string()); print(f"  事件平均：股票 {ev.Ystock.mean()*100:+.1f}%  国债 {ev.Ybond.mean()*100:+.1f}%  相对 {ev.Y.mean()*100:+.1f}%，股票跑赢 {(ev.Y>0).sum()}/{len(ev)}")
print("\n=== 方向 C：把股票估值和利率变化分开，利率变化有没有增量")
e = oos(m, "Y", [["r250", "zey"], ["r250", "zey", "dy250"]]); compare(e, 0, 1, "基准(反转+盈利收益率偏离) → 再加过去一年利率降幅(主检验)")
e = oos(m, "Y", [["r250", "zey"], ["r250", "z"]]); compare(e, 0, 1, "（参考）盈利收益率偏离 → 换成息差偏离")
print("\n=== 方向 D：迁移到中证500（月频估值，36 个月窗口、至少 18 个月）")
def monthly(pe_file, tr_file, px_file=None, name=""):
    pe = pd.read_csv(pe_file, parse_dates=["日期"]).set_index("日期"); tr = load(tr_file, "close"); days = tr.index
    q = pd.DataFrame({"spread": 100 / pe["滚动市盈率"] - bondy.reindex(pe.index, method="ffill"), "px": pe["指数"]}).iloc[:-1]
    q["z"] = zscore(q.spread, 36, 18); q["r250"] = q.px / q.px.shift(12) - 1
    pos = days.searchsorted(q.index); pos = np.clip(pos, 0, len(days) - 1); tb = bw.reindex(days).ffill()
    def f(x, p): a, b = p + 1, p + 1 + H; return np.where(b < len(x), x.values[np.minimum(b, len(x) - 1)] / x.values[np.minimum(a, len(x) - 1)] - 1, np.nan)
    q["Y"] = f(tr, pos) - f(tb, pos); q["mature"] = [days[p + 1 + H] if p + 1 + H < len(days) else pd.NaT for p in pos]
    e = oos(q, "Y", [["r250"], ["r250", "z"]]); return compare(e, 0, 1, f"{name} M1 → M2")
monthly("data/csi300_pe_lg.csv", "data/tr_H00300.csv", name="沪深300（同样月频口径）"); monthly("data/pe_lg_sh000905.csv", "data/tr_H00905.csv", name="中证500（主检验）")
print("\n=== 方向 E：仓位 = 50% + clip(z,0,2)/4，其余放国债；月末定、次日调")
r_s = d.tr.pct_change(); r_b = d.bw.pct_change(); me = month_ends(d.index); w_sig = (0.5 + d.z.clip(0, 2) / 4).loc[me].dropna()
rows = []
for i in range(len(w_sig) - 1):
    t0, t1 = w_sig.index[i], w_sig.index[i + 1]; seg = (d.index > d.index[d.index.get_loc(t0) + 1]) & (d.index <= d.index[min(d.index.get_loc(t1) + 1, len(d) - 1)])
    hist = w_sig[w_sig.index < pd.Timestamp(t0.year, 1, 1)]
    if len(hist) < MIN_TRAIN or r_b[seg].isna().any(): continue
    S_, B_ = (1 + r_s[seg]).prod() - 1, (1 + r_b[seg]).prod() - 1; w, wf = w_sig.iloc[i], hist.mean(); wprev = w_sig.iloc[i - 1]
    rows.append((t1, w, wf, w * S_ + (1 - w) * B_, wf * S_ + (1 - wf) * B_, 0.5 * S_ + 0.5 * B_, S_, abs(w - wprev)))
p = pd.DataFrame(rows, columns=["date", "w", "wf", "dyn", "fix", "half", "stock", "turn"]).set_index("date")
for cost in (0.0, 0.001):
    dd = (p.dyn - cost * p.turn) - p.fix; ci, pr = block_ci(dd.values, 12); ci2, pr2 = block_ci(dd.values, 24)
    print(f"  单边成本 {cost*1e4:.0f}bp：{len(p)} 个月（{p.index[0].date()}–{p.index[-1].date()}），动态比固定权重每月多 {dd.mean()*100:+.3f}% | 12月区块 [{ci[0]*100:+.3f}, {ci[1]*100:+.3f}] 不为正概率 {pr:.2f} | 24月区块 [{ci2[0]*100:+.3f}, {ci2[1]*100:+.3f}] {pr2:.2f}")
def ann(r): eq = (1 + r).cumprod(); return f"年化 {(eq.iloc[-1] ** (12 / len(r)) - 1)*100:.1f}%  波动 {r.std()*np.sqrt(12)*100:.0f}%  最大回撤 {((eq/eq.cummax()-1).min())*100:.0f}%"
print(f"  动态(平均股票仓位 {p.w.mean()*100:.0f}%)：{ann(p.dyn)}\n  事前固定权重(平均 {p.wf.mean()*100:.0f}%)：{ann(p.fix)}\n  五五开：{ann(p.half)}\n  全仓股票：{ann(p.stock)}")
