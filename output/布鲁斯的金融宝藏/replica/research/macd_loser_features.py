"""MACD 低质量金叉的特征研究（运行前写定，跑完不改）。
交易：63 只 ETF（页面清单+半导体）所有 MACD 金叉交易，信号日 t 次日开盘买，死叉信号日 j 次日开盘卖，含 0.2% 成本；上市后第 60 个交易日起。
样本切分：信号日 < 2023-01-01 为“发现段”，≥ 2023-01-01 为“验证段”。分档切点只用发现段确定。
特征（全部为信号日收盘可得）：
  fall60 距 60 日最高收盘跌幅；pos200 收盘/MA200−1；dea_n DEA/收盘；ma60_slope MA60/20 日前 MA60−1；adx ADX14；vol20 20 日年化波动；
  cross60 过去 60 日（含当日）MACD 交叉次数；gap 上次死叉到本次金叉的交易日数；prev_ret 同一 ETF 上一笔 MACD 交易收益；
  kd K−D（KDJ 9,3,3）；rsi RSI14；mkt200 上证收盘/MA200−1；pe_pct 沪深300 整体 PE 10 年分位（月末值次日生效）。
判定：某档在发现段平均收益明显低于整体，且在验证段同一档也低于整体，才视为可能有用；同时报告每个特征与收益的秩相关（两段分别）。"""
import json, numpy as np, pandas as pd
exec(open("research/macd_rsi_kdj.py").read().split("ENTRY = {")[0])
sh = pd.read_csv("data/index_sh000001_ohlc.csv", parse_dates=["date"]).set_index("date").close
mkt200 = sh / sh.rolling(200).mean() - 1
pe = pd.read_csv("data/hs300_pe_lg_monthly.csv", parse_dates=["日期"]).set_index("日期").sort_index()["滚动市盈率"]
pv = pe.values; pct = [np.nan if i < 59 else (lambda h: (h < pv[i]).mean())(pv[max(0, i-119): i+1]) for i in range(len(pv))]
pe_pct = pd.Series(pct, index=pe.index)
def adx14(hi, lo, c):
    up = hi.diff(); dn = -lo.diff(); pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([hi - lo, (hi - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    a = lambda s: pd.Series(s, index=c.index).ewm(alpha=1/14, adjust=False).mean()
    atr = a(tr); pdi = 100 * a(pdm) / atr; ndi = 100 * a(ndm) / atr; dx = 100 * (pdi - ndi).abs() / (pdi + ndi)
    return a(dx)
rows = []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code); i0 = 60
    if len(d) < 120: continue
    x = indicators(d, adj); f = adj / d.close; hi, lo = d.high * f, d.low * f
    idx = d.index; ao = (d.open * adj / d.close).values; dif, dea = x["dif"], x["dea"]; m = dif > dea
    cross = pd.Series(np.r_[False, m[1:] != m[:-1]], index=idx)
    feats = pd.DataFrame({
        "fall60": adj / adj.rolling(60, min_periods=1).max() - 1, "pos200": adj / adj.rolling(200).mean() - 1, "dea_n": pd.Series(dea, index=idx) / adj,
        "ma60_slope": adj.rolling(60).mean() / adj.rolling(60).mean().shift(20) - 1, "adx": adx14(hi, lo, adj),
        "vol20": np.log(adj).diff().rolling(20).std() * np.sqrt(244), "cross60": cross.rolling(60, min_periods=1).sum(),
        "kd": x["K"] - x["D"], "rsi": x["rsi"], "mkt200": mkt200.reindex(idx).ffill(),
        "pe_pct": pe_pct.dropna().reindex(pe_pct.dropna().index.union(idx)).ffill().reindex(idx).shift(1)}, index=idx)
    last_dead, prev_ret = None, np.nan
    for t in range(1, len(d) - 1):
        if not m[t] and m[t-1]: last_dead = t
        if t >= i0 and m[t] and not m[t-1]:
            j = t
            while j < len(d) - 1 and m[j]: j += 1
            if j >= len(d) - 1: break
            ret = ao[j + 1] / ao[t + 1] * 0.999 ** 2 - 1
            rows.append(dict(code=code, name=name, date=idx[t], ret=ret, win=ret > 0, days=j - t, gap=(t - last_dead) if last_dead is not None else np.nan, prev_ret=prev_ret, **feats.iloc[t].to_dict()))
            prev_ret = ret
T = pd.DataFrame(rows); T.to_csv("research/macd_loser_trades.csv", index=False)
A, B = T[T.date < "2023-01-01"], T[T.date >= "2023-01-01"]
print(f"交易：发现段（<2023）{len(A)} 笔，平均 {A.ret.mean()*100:+.2f}%，胜率 {A.win.mean()*100:.0f}%；验证段（≥2023）{len(B)} 笔，平均 {B.ret.mean()*100:+.2f}%，胜率 {B.win.mean()*100:.0f}%")
F = ["fall60", "pos200", "dea_n", "ma60_slope", "adx", "vol20", "cross60", "gap", "prev_ret", "kd", "rsi", "mkt200", "pe_pct"]
names = {"fall60": "距60日高点跌幅", "pos200": "相对200日线", "dea_n": "DEA/价格", "ma60_slope": "60日线20日斜率", "adx": "ADX14", "vol20": "20日波动率",
         "cross60": "60日内交叉次数", "gap": "距上次死叉天数", "prev_ret": "上一笔收益", "kd": "K−D", "rsi": "RSI14", "mkt200": "上证相对200日线", "pe_pct": "沪深300 PE分位"}
summary = []
for c in F:
    a = A.dropna(subset=[c]); b = B.dropna(subset=[c])
    qs = np.unique(np.quantile(a[c], [0.2, 0.4, 0.6, 0.8]))
    cut = lambda s: np.searchsorted(qs, s.values, side="right")
    a = a.assign(q=cut(a[c])); b = b.assign(q=cut(b[c]))
    ra, rb = a[c].rank().corr(a.ret.rank()), b[c].rank().corr(b.ret.rank())
    print(f"\n[{names[c]}]  秩相关：发现段 {ra:+.3f}，验证段 {rb:+.3f}   切点 {', '.join(f'{v:.3g}' for v in qs)}")
    print(f"   {'档':<4}{'发现段笔数':>8}{'平均':>8}{'胜率':>6} | {'验证段笔数':>8}{'平均':>8}{'胜率':>6}")
    for q in sorted(set(a.q)):
        za, zb = a[a.q == q], b[b.q == q]
        print(f"   Q{q+1:<3}{len(za):8d}{za.ret.mean()*100:+8.2f}{za.win.mean()*100:5.0f}% | {len(zb):8d}{zb.ret.mean()*100:+8.2f}{zb.win.mean()*100:5.0f}%")
    worst = a.groupby("q").ret.mean().idxmin(); best = a.groupby("q").ret.mean().idxmax()
    summary.append(dict(feat=names[c], ra=ra, rb=rb, worst=f"Q{worst+1}", wa=a[a.q == worst].ret.mean() - a.ret.mean(), wb=b[b.q == worst].ret.mean() - b.ret.mean(), nb=(b.q == worst).sum()))
S = pd.DataFrame(summary)
print("\n==== 汇总：发现段最差档，在两段相对整体平均的差（百分点）；同向且验证段也明显为负才算可能有用")
for _, r in S.sort_values("wb").iterrows():
    print(f"   {r.feat:<12} 秩相关 {r.ra:+.3f}/{r.rb:+.3f}  最差档 {r.worst}  发现段 {r.wa*100:+6.2f}  验证段 {r.wb*100:+6.2f}（{r.nb} 笔）")
