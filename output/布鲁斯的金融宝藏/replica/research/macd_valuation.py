"""按估值分位判断大环境并使用 MACD（运行前写定，跑完不改）。
估值：沪深300 月度滚动市盈率（乐咕乐股），两个口径：整体 PE（滚动市盈率）、成分股 PE 中位数（滚动市盈率中位数）。
分位：每个月末，当前值在过去 120 个月（不足则用全部，至少 60 个月）中的百分位；该月末之后的交易日才生效（无未来信息）。
区间：<30% 低估；30%–70% 中性；>70% 高估。
诊断：按前一日收盘时的估值区间归类每日收益，算一直持有与纯 MACD 的年化。
策略：V1 低估持有/中性、高估 MACD；V2 低估、中性持有/高估 MACD；V3 低估持有/中性 MACD/高估空仓。
其余（样本、成交、成本、≥3 年汇总、前后半段）同 macd_regime.py。"""
import json, numpy as np, pandas as pd
exec(open("research/macd_regime.py").read().split("rows, diag = [], []")[0])
pe = pd.read_csv("data/hs300_pe_lg_monthly.csv", parse_dates=["日期"]).set_index("日期").sort_index()
def band(series):
    v = series.values; out = []
    for i in range(len(v)):
        hist = v[max(0, i - 119): i + 1]
        out.append(np.nan if len(hist) < 60 else (hist < v[i]).mean() + 0.5 * (hist == v[i]).mean() - 0.5 / len(hist))
    p = pd.Series(out, index=series.index)
    b = pd.Series("中性", index=p.index); b[p < 0.3] = "低估"; b[p > 0.7] = "高估"; b[p.isna()] = None
    return p, b
lenses = {}
for lens, col in (("整体PE", "滚动市盈率"), ("PE中位数", "滚动市盈率中位数")):
    p, b = band(pe[col]); lenses[lens] = (p, b)
def daily_band(b, idx):
    # 月末值从下一个交易日起生效：先在月末日期对齐，再整体后移一天
    s = b.dropna(); x = s.reindex(s.index.union(idx)).ffill().reindex(idx).shift(1)
    return x.fillna("中性")

rows, diag = [], []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code); i0 = 60
    if len(d) < 120: continue
    idx = d.index; years = (idx[-1] - idx[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    macd = macd_state(adj); always = pd.Series(True, index=idx)
    r = dict(code=code, name=name, years=years, good=code in good)
    gh = daily_navs(d, dv, mult, always, i0, 0.0); gm = daily_navs(d, dv, mult, macd, i0, 0.001)
    for k, st in (("H", always), ("M", macd)):
        c = 0.0 if k == "H" else 0.001; n, _ = backtest(d, dv, mult, st, i0, c)
        a, _ = backtest(d.iloc[:mid + 1], dv.iloc[:mid + 1], mult.iloc[:mid + 1], st.iloc[:mid + 1], i0, c); b_, _ = backtest(d, dv, mult, st, mid, c)
        r[k], r[k + "_dd"], r[k + "_h1"], r[k + "_h2"] = ann(n), mdd(n), ann(a), ann(b_)
    for lens, (p, b) in lenses.items():
        rg = daily_band(b, idx)
        prev = rg.shift(1).iloc[i0:].values
        for state in ("低估", "中性", "高估"):
            msk = prev == state
            if msk.sum() < 20: continue
            diag.append(dict(code=code, good=code in good, long=years >= 3, lens=lens, state=state, share=msk.mean(),
                             hold=np.prod(gh[msk]) ** (244 / msk.sum()) - 1, macd=np.prod(gm[msk]) ** (244 / msk.sum()) - 1))
        pol = {"V1": (rg == "低估") | ((rg != "低估") & macd), "V2": (rg != "高估") | ((rg == "高估") & macd), "V3": (rg == "低估") | ((rg == "中性") & macd)}
        for k, st in pol.items():
            st = st.astype(bool); n, _ = backtest(d, dv, mult, st, i0, 0.001)
            a, _ = backtest(d.iloc[:mid + 1], dv.iloc[:mid + 1], mult.iloc[:mid + 1], st.iloc[:mid + 1], i0, 0.001); b_, _ = backtest(d, dv, mult, st, mid, 0.001)
            r[f"{lens}{k}"], r[f"{lens}{k}_dd"], r[f"{lens}{k}_h1"], r[f"{lens}{k}_h2"] = ann(n), mdd(n), ann(a), ann(b_)
    rows.append(r)
t = pd.DataFrame(rows); g = pd.DataFrame(diag); t.to_csv("research/macd_valuation_results.csv", index=False); g.to_csv("research/macd_valuation_diag.csv", index=False)

for lens, (p, b) in lenses.items():
    bb = b.loc["2013":]; print(f"{lens}：2013 年以来各区间占比", (bb.value_counts(normalize=True) * 100).round(0).to_dict(), "；最近", b.index[-1].date(), f"分位 {p.iloc[-1]*100:.0f}%（{b.iloc[-1]}）")
    seg = (bb != bb.shift()).cumsum(); print("   区间变化：", "；".join(f"{x.index[0]:%Y-%m}起{x.iloc[0]}" for _, x in bb.groupby(seg)))
print("\n==== 诊断：各估值区间下的年化（中位数，%；只算回测≥3年的 ETF）")
for lens in lenses:
    for label, sel in (("全部", g.long), ("MACD优秀", g.good)):
        x = g[(g.lens == lens) & sel]; print(f"  [{lens}·{label}]")
        for state in ("低估", "中性", "高估"):
            y = x[x.state == state]
            if len(y): print(f"     {state} 占时间 {y.share.median()*100:4.0f}%  持有 {y.hold.median()*100:+7.1f}  MACD {y.macd.median()*100:+7.1f}  MACD 更好 {(y.macd > y.hold).sum():2d}/{len(y)}")
names = {"V1": "低估持有/其余MACD", "V2": "高估才用MACD/其余持有", "V3": "低估持有/中性MACD/高估空仓"}
for label, sel in (("回测≥3年全部", t[t.years >= 3]), ("MACD优秀 17 只", t[t.good])):
    print(f"\n==== 策略对比：{label}（{len(sel)} 只）")
    print(f"   {'策略':<24}{'年化中位':>8}{'年化均值':>8}{'胜纯MACD':>9}{'胜持有':>8}{'前后半都胜MACD':>13}{'回撤中位':>8}")
    for k, nm in (("H", "一直持有"), ("M", "纯MACD")):
        print(f"   {nm:<22}{sel[k].median()*100:+8.2f}{sel[k].mean()*100:+8.2f}{'':>30}{sel[k+'_dd'].median()*100:8.1f}")
    for lens in lenses:
        for k in names:
            c = f"{lens}{k}"
            print(f"   {lens+'·'+names[k]:<22}{sel[c].median()*100:+8.2f}{sel[c].mean()*100:+8.2f}{(sel[c]>sel.M).sum():>6}/{len(sel)}{(sel[c]>sel.H).sum():>5}/{len(sel)}{((sel[c+'_h1']>sel.M_h1)&(sel[c+'_h2']>sel.M_h2)).sum():>10}/{len(sel)}{sel[c+'_dd'].median()*100:8.1f}")
