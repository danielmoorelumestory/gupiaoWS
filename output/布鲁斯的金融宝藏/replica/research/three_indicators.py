"""按 09-codex-三指标规格.md 实现：200 日均线（下行风险）、破净股占比（正向增量）、融资余额/20日成交额（负向增量）。
规格之外不运行任何别的均线、分母、阈值或组合。"""
import numpy as np, pandas as pd, sys
H, MIN_TRAIN, B = 120, 60, 19999
def load(f, col, date="date"): x = pd.read_csv(f, parse_dates=[date]).set_index(date)[col]; return x
cal = load("data/index_sh000300.csv", "close").loc["2005-01-04":].index
pos = pd.Series(np.arange(len(cal)), index=cal)
def on_cal(x): x = x[x.index.isin(cal)]; return x[~x.index.duplicated()].reindex(cal)
px = load("data/index_sh000300.csv", "close").reindex(cal); tr = on_cal(load("data/tr_H00300.csv", "close")); bw = on_cal(load("data/cbond_treasury_7-10Y_wealth.csv", "value"))
assert tr.loc["2005-01-04":].isna().sum() == 0, "全收益有缺口"; assert bw.loc["2007-01-04":].isna().sum() == 0, "国债财富有缺口"
grp = pd.Series(cal, index=cal).groupby([cal.year, cal.month]).last(); me = pd.DatetimeIndex(grp.values)
if not (cal[-1].month != (cal[-1] + pd.offsets.BDay(1)).month and False): me = me[:-1]          # 数据截止 2026-11-10，当月未走完，不计
prev = lambda t: cal[pos[t] - 1]                                                                # 前一真实交易日
def boot(d, block, seed):
    """d 按连续日历月排列，可含 NaN；循环区块抽位置，对有效值取均值。"""
    d = np.asarray(d, float); n = len(d); k = int(np.ceil(n / block)); rng = np.random.default_rng(seed); mean = np.nanmean(d); out = np.empty(B)
    for j in range(B): out[j] = np.nanmean(d[np.concatenate([(s + np.arange(block)) % n for s in rng.integers(0, n, k)])[:n]])
    return np.nanpercentile(out, [2.5, 97.5]), (1 + np.sum(out - mean >= mean)) / (B + 1)
P = {}
def verdict(name, d, seeds, scale, unit):
    d = pd.Series(d); full = d.reindex(pd.period_range(d.index[0], d.index[-1], freq="M").to_timestamp("M").map(lambda x: x)) if False else d
    mean = np.nanmean(d.values); line = f"  主统计量平均 {mean*scale:+.4f}{unit}（有效 {int(d.notna().sum())} 个月，缺失 {int(d.isna().sum())}）"
    for blk, seed in zip((12, 24), seeds):
        ci, p = boot(d.values, blk, seed); line += f"\n    {blk} 月区块：95% 区间 [{ci[0]*scale:+.4f}, {ci[1]*scale:+.4f}]，中心化单侧比例 {p:.4f}"
        if blk == 12: P[name] = p; lo = ci[0]
    print(line); print("  判定：" + ("失败（主均值不为正）" if mean <= 0 else ("区间下限为正，待多重比较校正" if lo > 0 else "未证实（方向为正，区间含零）")))
    by = d.groupby(d.index.year).agg(["mean", "count"]); loo = [np.nanmean(d[d.index.year != y].values) for y in by.index]
    print("  逐年平均：" + "  ".join(f"{y}:{v*scale:+.2f}" for y, v in by["mean"].items())); print(f"  整年剔除后的主均值范围：{min(loo)*scale:+.4f} 到 {max(loo)*scale:+.4f}")
# ---------------------------------------------------------------- 一、200 日均线
print("=" * 20, "一、200 日均线（全收益、月末、100% 股票或 100% 国债）")
sma = tr.rolling(200, min_periods=200).mean(); sig = (tr > sma).astype(float).where(sma.notna()).loc[me].dropna()
def simulate(target_fn, cost):
    """target_fn(i, t0) -> 目标股票权重；返回逐段净收益、日频净值、日频股票权重、换手、费用。"""
    rets, path, wts, turn, fee = [], [1.0], [], [], []; pre = None; nav = 1.0
    for i in range(len(seg)):
        t0, a, b = seg[i]; w = target_fn(i, t0)
        if w is None: rets.append(np.nan); continue
        trade = 1.0 if pre is None else 2 * abs(w - pre)                                          # 首次从现金建仓两腿合计 100%；其后两腿各 |Δw|
        c = cost * trade; s = (tr.iloc[a + 1:b + 1].values / tr.iloc[a]) ; g = (bw.iloc[a + 1:b + 1].values / bw.iloc[a])
        v = (1 - c) * (w * s + (1 - w) * g); rets.append(v[-1] - 1); path += list(nav * v); nav *= v[-1]
        wts += list(w * s / (w * s + (1 - w) * g)); pre = wts[-1]; turn.append(trade / 2 if trade != 1.0 or pre is None else np.nan); fee.append(c)
    return np.array(rets), np.array(path), np.array(wts), np.nanmean(turn[1:]) if len(turn) > 1 else np.nan, np.sum(fee)
seg = []
for i in range(len(sig) - 1):
    t0, t1 = sig.index[i], sig.index[i + 1]; a, b = pos[t0] + 1, pos[t1] + 1
    if b < len(cal) and not np.isnan(bw.iloc[a]): seg.append((t0, a, b))
def wf(t0): h = sig[sig.index < pd.Timestamp(t0.year, 1, 1)]; return h.mean() if len(h) >= 1 else None
seg = [x for x in seg if wf(x[0]) is not None]; idx = pd.DatetimeIndex([cal[b] for _, _, b in seg])
print(f"  评价 {len(seg)} 个完整月间区间：首个信号 {seg[0][0].date()}、{cal[seg[0][1]].date()} 收盘进入；末段 {cal[seg[-1][2]].date()} 收盘结束")
def stats(r, path, w):
    yrs = len(r) / 12; dd = (path / np.maximum.accumulate(path) - 1).min()
    return f"净年化 {(np.prod(1 + r) ** (1 / yrs) - 1)*100:5.2f}%  波动 {np.std(r, ddof=1)*np.sqrt(12)*100:5.1f}%  日频最大回撤 {dd*100:6.1f}%  月下行二阶矩 {np.mean(np.minimum(r, 0) ** 2)*1e4:6.2f}  平均股票权重 {np.mean(w)*100:3.0f}%"
for cost in (0.001, 0.0):
    dyn = simulate(lambda i, t0: sig[t0], cost); fix = simulate(lambda i, t0: wf(t0), cost)
    print(f"\n  —— 每条腿单边 {cost*1e4:.0f}bp" + ("（主情景）" if cost else "（敏感性）"))
    print(f"    200 日线规则    {stats(dyn[0], dyn[1], dyn[2])}  月均调仓 {dyn[3]*100:.1f}%  累计费用 {dyn[4]*100:.2f}%")
    print(f"    事前固定权重    {stats(fix[0], fix[1], fix[2])}  月均调仓 {fix[3]*100:.1f}%  累计费用 {fix[4]*100:.2f}%")
    if cost:
        for nm, w in (("股债各半", 0.5), ("全仓股票", 1.0), ("全仓国债", 0.0), (f"同平均暴露静态", float(np.mean(dyn[2])))):
            o = simulate(lambda i, t0, w=w: w, cost); print(f"    {nm:<10}{'' if nm != '同平均暴露静态' else '(事后归因)'}  {stats(o[0], o[1], o[2])}")
            if nm == "同平均暴露静态": print(f"      对同平均暴露参照的下行二阶矩差（点估计，未检验）：{(np.mean(np.minimum(o[0],0)**2) - np.mean(np.minimum(dyn[0],0)**2))*1e4:+.2f}")
        print(f"    平均月对数收益差（规则 − 事前固定）：{np.mean(np.log1p(dyn[0]) - np.log1p(fix[0]))*100:+.3f}%")
        d = pd.Series(np.minimum(fix[0], 0) ** 2 - np.minimum(dyn[0], 0) ** 2, index=idx); verdict("MA", d, (2012, 2024), 1e4, "（万分之一）")
print(f"  当前状态（{sig.index[-1].date()} 月末）：{'在均线上方' if sig.iloc[-1] else '在均线下方'}；最新一日 {cal[-1].date()} 全收益 {tr.iloc[-1]:.0f} / 均线 {sma.iloc[-1]:.0f}")
# ---------------------------------------------------------------- 共同：收益标签与基准
f = lambda x: x.shift(-(H + 1)) / x.shift(-1) - 1
lab = pd.DataFrame({"Y": f(tr) - f(bw), "r250": px / px.shift(250) - 1, "mature": pd.Series(cal, index=cal).shift(-(H + 1))}).loc[me]
def incremental(name, X, sign, seeds):
    df = lab.assign(X=X.reindex(lab.index)); df = df[df.index >= X.dropna().index[0]]; valid = df.dropna(subset=["Y", "r250", "X"]); recs = []; err = {}
    for yr in sorted(set(valid.index.year)):
        cut = pd.Timestamp(yr, 1, 1); trn = valid[valid["mature"] < cut]; te = valid[valid.index.year == yr]
        if len(trn) < MIN_TRAIN or te.empty: continue
        X0 = np.column_stack([np.ones(len(trn)), trn.r250]); b0 = np.linalg.lstsq(X0, trn.Y, rcond=None)[0]
        X1 = np.column_stack([X0, trn.X]); b1 = np.linalg.lstsq(X1, trn.Y, rcond=None)[0]; g = b1[2]
        if np.ptp(trn.X.values) == 0 or g * sign < 0: b1 = np.append(b0, 0.0)                    # 符号不符或退化：新增系数置 0，回到基准
        for t, r in te.iterrows(): err[t] = (r.Y - trn.Y.mean(), r.Y - b0 @ [1, r.r250], r.Y - b1 @ [1, r.r250, r.X])
        recs.append((yr, len(trn), g, b1[2], trn.X.min(), trn.X.max()))
    e = pd.DataFrame(err, index=["mean", "b0", "b1"]).T; months = df.index[(df.index >= e.index[0]) & (df.index <= e.index[-1])]; e = e.reindex(months)
    print(f"  特征起点 {X.dropna().index[0].date()}；样本外 {months[0].date()}–{months[-1].date()} 共 {len(months)} 个月，其中缺特征 {int(e['b0'].isna().sum())} 个：{[str(x.date()) for x in months[e['b0'].isna()]][:8]}")
    print(f"  MSE（万分之一）：仅均值 {np.nanmean(e['mean']**2)*1e4:.1f} / 反转基准 {np.nanmean(e['b0']**2)*1e4:.1f} / 加入{name} {np.nanmean(e['b1']**2)*1e4:.1f}")
    print("  每年新增系数（无约束估计→实际采用）：" + "  ".join(f"{y}:{g:+.3f}→{u:+.3f}" for y, n, g, u, lo, hi in recs)); print(f"  被约束归零的年份数：{sum(1 for r in recs if r[3] == 0)}/{len(recs)}")
    verdict(name, e["b0"] ** 2 - e["b1"] ** 2, seeds, 1e4, "（万分之一）"); return recs
# ---------------------------------------------------------------- 二、破净股占比
print("\n" + "=" * 20, "二、破净股占比（水平值、前一交易日、系数须为正）")
raw = pd.read_csv("data/below_net_asset_all.csv", parse_dates=["date"]).drop_duplicates()
conflict = raw[raw.duplicated("date", keep=False)]["date"].unique(); raw = raw[~raw["date"].isin(conflict)].set_index("date")
raw = raw[(raw.total_company > 0) & (raw.below_net_asset >= 0) & (raw.below_net_asset <= raw.total_company)]; Bd = (raw.below_net_asset / raw.total_company).reindex(cal)
print(f"  数据：同日冲突而剔除 {[str(pd.Timestamp(x).date()) for x in conflict]}；日历内缺 {int(Bd.loc[raw.index[0]:raw.index[-1]].isna().sum())} 天；最新 {raw.index[-1].date()} 为 {Bd.dropna().iloc[-1]*100:.2f}%")
XB = pd.Series({t: Bd.get(prev(t), np.nan) for t in me}); incremental("破净占比", XB, +1, (3012, 3024)); 
# ---------------------------------------------------------------- 三、融资余额
print("\n" + "=" * 20, "三、融资余额 ÷ 20 日平均成交额（取对数、前一交易日、系数须为负）")
try:
    sh = load("data/margin_sh.csv", "融资余额", "日期"); sz = load("data/margin_sz.csv", "融资余额", "日期"); sz = sz[sz > 0]; sh = sh[sh > 0]
    pz = pd.read_csv("data/margin_sz_patch_szse.csv", parse_dates=["date"]); ps = pd.read_csv("data/margin_sh_patch_sse.csv", parse_dates=["date"])
    chk = pz[pz["核对用"]].set_index("date")["融资余额_亿元"] * 1e8; print("  深市既有数据与交易所原始值核对（相对差）：" + "  ".join(f"{d.date()}:{(sz[d]/v-1)*100:+.3f}%" for d, v in chk.items() if d in sz.index and v > 0))
    add = pz[~pz["核对用"]].set_index("date")["融资余额_亿元"].dropna() * 1e8; add = add[add > 0]; sz = pd.concat([sz, add[~add.index.isin(sz.index)]]).sort_index()
    adds = ps.set_index("date")["融资余额_元"].dropna(); adds = adds[adds > 0]; sh = pd.concat([sh, adds[~adds.index.isin(sh.index)]]).sort_index()
    mcal = cal[(cal >= "2010-03-31") & (cal <= "2026-11-05")]; L = (sh.reindex(cal) + sz.reindex(cal))
    print(f"  补齐后日历内仍缺：沪 {int(sh.reindex(mcal).isna().sum())} 天、深 {int(sz.reindex(mcal).isna().sum())} 天：{[str(d.date()) for d in mcal[L.reindex(mcal).isna()]][:12]}")
    amt = on_cal(load("data/csindex_000985.csv", "成交金额", "日期")) * 1e8; A20 = amt.rolling(20, min_periods=20).mean()
    XF_d = np.log(L / A20); XF = pd.Series({t: XF_d.get(prev(t), np.nan) for t in me}); XF = XF[XF.index >= "2010-04-30"]
    miss = [t for t in XF.index if np.isnan(XF[t])]
    print(f"  月末特征缺失 {len(miss)} 个：{[str(t.date()) for t in miss]}；最新 {XF.dropna().index[-1].date()}：余额 {L[prev(XF.dropna().index[-1])]/1e8:.0f} 亿，相当于 {np.exp(XF.dropna().iloc[-1]):.2f} 个日均成交额")
    if miss: print("  ※ 关键月末补不齐，按规格本项记数据不足，p 置 1"); P["融资"] = 1.0
    else:
        recs = incremental("融资压力", XF, -1, (4012, 4024)); x1415 = XF["2014":"2015"]; print(f"  2014–2015 特征范围 {x1415.min():.2f} 到 {x1415.max():.2f}（全样本 {XF.min():.2f} 到 {XF.max():.2f}）")
except FileNotFoundError as ex: print("  补丁文件未就绪：", ex); P["融资"] = 1.0
# ---------------------------------------------------------------- Holm
def holm(ps, title):
    print(f"\n{title}"); order = sorted(ps.items(), key=lambda x: x[1]); run = 0
    for r, (k, p) in enumerate(order): run = max(run, min(1, p * (len(order) - r))); print(f"  {k}: 原始 {p:.4f} → 校正后 {run:.4f}  {'通过' if run < 0.05 else '未通过'}")
holm(P, "本轮三项家族 Holm 校正（12 月区块）")
holm({**P, "旧A": 0.895, "旧C": 0.969, "旧D": 0.723, "旧E": 0.078, "旧AR1通道": 0.600}, "八项总账 Holm 校正（以此为准）")
