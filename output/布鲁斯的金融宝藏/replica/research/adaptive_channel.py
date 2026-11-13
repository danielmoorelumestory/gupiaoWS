"""按 08-codex-算法方案.md 第二、三节锁定的规格实现：AR(1) 校准的指数加权通道，与原 750 日通道做配对比较。
不含任何可调参数；每年年初只用此前的息差估 φ，历史已发布的 z 不回改。"""
import numpy as np, pandas as pd
H, MIN_TRAIN, FIRST_YEAR = 120, 60, 2011
def load(f, col): return pd.read_csv(f, parse_dates=["date"]).set_index("date")[col]
cal = load("data/index_sh000300.csv", "close").loc["2005-04-08":].index
def on_cal(x): return x[~x.index.duplicated()].reindex(cal)
def fit_ar1(s, cut):
    v = s[s.index < cut]; a, b = v.values[:-1], v.values[1:]; ok = ~np.isnan(a) & ~np.isnan(b); a, b = a[ok], b[ok]   # 只用相邻两日都有值的一日转移
    phi = ((a - a.mean()) * (b - b.mean())).sum() / ((a - a.mean()) ** 2).sum(); c = b.mean() - phi * a.mean(); q = np.mean((b - c - phi * a) ** 2)
    return phi, c, q, len(a)
def new_z(s):
    """s: 日历上的息差（缺失为 NaN）。返回 (z, 参数表)。"""
    z = pd.Series(np.nan, index=s.index); rows = []; last = np.nan
    for yr in range(FIRST_YEAR, s.index[-1].year + 1):
        cut = pd.Timestamp(yr, 1, 1); phi, c, q, n = fit_ar1(s, cut)
        if not (0 < phi < 1 and q > 0): raise SystemExit(f"{yr} 年参数不可用 φ={phi}")       # 规格：不裁剪、不兜底，直接记可用性失败
        rows.append((yr, s[s.index < cut].dropna().index[-1].date(), n, phi, q, -np.log(2) / np.log(phi)))
        W = m = M2 = 0.0
        for t, v in s[s.index < pd.Timestamp(yr + 1, 1, 1)].items():                          # 从头回放只为初始化，本年才记录
            W *= phi; M2 *= phi
            if not np.isnan(v):
                W += 1; d = v - m; m += d / W; M2 += d * (v - m)
                if t >= cut and M2 / W > 0: last = (v - m) / np.sqrt(M2 / W)
            if t >= cut: z[t] = last
    return z, pd.DataFrame(rows, columns=["年份", "估计截止日", "有效转移对数", "phi", "q", "半衰期(日)"])
def oos(df, y, cols_list):
    out = {i: [] for i in range(len(cols_list))}; dates = []
    for yr in sorted(set(df.index.year)):
        cut = pd.Timestamp(yr, 1, 1); tr = df[df["mature"] < cut]; te = df[df.index.year == yr]
        if len(tr) < MIN_TRAIN or te.empty: continue
        for i, cols in enumerate(cols_list):
            X = np.column_stack([np.ones(len(tr))] + [tr[c].values for c in cols]); b = np.linalg.lstsq(X, tr[y].values, rcond=None)[0]
            out[i] += list(te[y].values - np.column_stack([np.ones(len(te))] + [te[c].values for c in cols]) @ b)
        dates += list(te.index)
    return pd.DataFrame(out, index=dates)
def boot(d, block, seed, B=5000):
    rng = np.random.default_rng(seed); n = len(d); k = int(np.ceil(n / block)); means = np.empty(B)
    for j in range(B): means[j] = d[np.concatenate([(s0 + np.arange(block)) % n for s0 in rng.integers(0, n, k)])[:n]].mean()
    return np.percentile(means, [2.5, 97.5]), (1 + (means - d.mean() >= d.mean()).sum()) / (B + 1)
def events(z, sign, start):
    flag = (z >= 2) if sign > 0 else (z <= -2); idx, last = [], -10**9
    for i in np.flatnonzero(flag.fillna(False).values):
        if i - last >= 20 and cal[i] >= start: idx.append(i)
        last = i
    return idx
def describe(name, z, Y, start):
    for sign, lab in ((1, "触上轨"), (-1, "破下轨")):
        idx = events(z, sign, start); y = Y.iloc[idx].dropna()
        if not idx: print(f"    {name} {lab}：0 次"); continue
        grp, g = [], []
        for i in [i for i in idx if not np.isnan(Y.iloc[i])]:
            if g and i <= g[-1] + H + 1: g.append(i)
            else:
                if g: grp.append(g)
                g = [i]
        if g: grp.append(g)
        gm = [Y.iloc[x].mean() for x in grp]
        print(f"    {name} {lab}：{len(idx)} 次（已到期 {len(y)}），事件平均 {y.mean()*100:+.1f}%、跑赢 {(y>0).sum()}/{len(y)}；合并为 {len(grp)} 组，组平均 {np.mean(gm)*100:+.1f}%、跑赢 {sum(v>0 for v in gm)}/{len(gm)}" + (f"；逐组剔除 {min(np.mean(gm[:k]+gm[k+1:]) for k in range(len(gm)))*100:+.1f}% 到 {max(np.mean(gm[:k]+gm[k+1:]) for k in range(len(gm)))*100:+.1f}%" if len(gm) > 1 else ""))
        print("      ", [f"{cal[i].date()} {'—' if np.isnan(Y.iloc[i]) else f'{Y.iloc[i]*100:+.0f}%'}" for i in idx])
if __name__ == "__main__":
    raw = pd.read_csv("data/equity_bond_spread.csv", parse_dates=["date"]).set_index("date")["spread"]; s = raw.reindex(cal)
    zn, par = new_z(s); print("每年年初的估计（只用此前数据）：\n" + par.round({"phi": 5, "q": 5, "半衰期(日)": 0}).to_string(index=False))
    for yr in (2015, 2019, 2023):                                                             # 前缀不变性：截断数据不改变已发布的 z
        zt, _ = new_z(s[s.index < pd.Timestamp(yr + 1, 1, 1)]); assert np.allclose(zt.dropna(), zn.reindex(zt.index).dropna()), yr
    print("前缀不变性检查通过（截到 2015、2019、2023 年末，已发布的新 z 与完整数据逐点一致）")
    zo = ((raw - raw.rolling(750, min_periods=375).mean()) / raw.rolling(750, min_periods=375).std(ddof=0)).reindex(cal).ffill()
    for n, z in (("旧 z", zo[zn.notna()]), ("新 z", zn.dropna())): print(f"  {n}：|z|≥2 占 {(z.abs()>=2).mean()*100:.1f}%，≥2 占 {(z>=2).mean()*100:.1f}%，≤−2 占 {(z<=-2).mean()*100:.1f}%，偏度 {z.skew():+.2f}，新旧相关 {zo.corr(zn):.3f}")
    px = load("data/index_sh000300.csv", "close").reindex(cal); tr = load("data/tr_H00300.csv", "close"); tr = on_cal(tr[tr.index.isin(cal)]).ffill(); bw = on_cal(load("data/cbond_treasury_7-10Y_wealth.csv", "value")).ffill()
    f = lambda x: x.shift(-(H + 1)) / x.shift(-1) - 1
    d = pd.DataFrame({"zo": zo, "zn": zn, "r250": px / px.shift(250) - 1, "Y": f(tr) - f(bw), "mature": pd.Series(cal, index=cal).shift(-(H + 1))})
    me = pd.Series(cal, index=cal).groupby([cal.year, cal.month]).last().values[:-1]; m = d.loc[me].dropna()      # 完整月末；新旧 z 共同存在
    e = oos(m, "Y", [[], ["r250"], ["r250", "zo"], ["r250", "zn"]]); mse = (e ** 2).mean() * 1e4; dd = (e[2] ** 2 - e[3] ** 2)
    print(f"\n主检验：共同训练起点 {m.index[0].date()}，样本外 {len(e)} 个月（{e.index[0].date()}–{e.index[-1].date()}）")
    print(f"  MSE（万分之一）：仅均值 {mse[0]:.1f} / 加反转 {mse[1]:.1f} / 反转+旧 z {mse[2]:.1f} / 反转+新 z {mse[3]:.1f}")
    print(f"  主统计量 MSE(旧) − MSE(新) = {dd.mean()*1e4:+.2f}")
    for blk, seed in ((12, 1012), (24, 1024)): ci, p = boot(dd.values, blk, seed); print(f"    {blk} 月区块：95% 区间 [{ci[0]*1e4:+.2f}, {ci[1]*1e4:+.2f}]，中心化单侧比例 {p:.3f}")
    print("\n事件描述（次日起 120 个交易日，股票全收益 − 国债财富；自样本外起点起）："); start = e.index[0]
    ok = (cal >= start) & d.Y.notna().values; print(f"    同期全部日子：平均 {d.Y[ok].mean()*100:+.1f}%，跑赢比例 {(d.Y[ok]>0).mean()*100:.0f}%")
    describe("旧通道", zo, d.Y, start); describe("新通道", zn, d.Y, start)
    print(f"\n当前（{cal[-1].date()}）：旧 z {zo.iloc[-1]:+.2f}，新 z {zn.iloc[-1]:+.2f}")
