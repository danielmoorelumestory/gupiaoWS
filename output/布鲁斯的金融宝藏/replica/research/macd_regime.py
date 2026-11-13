"""按大环境（牛/震荡/熊）评估并使用 MACD（运行前写定，跑完不改）。
环境（t 日收盘可知）：牛 = 收盘 > MA200 且 MA200 > 20 日前的 MA200；熊 = 收盘 < MA200 且 MA200 < 20 日前；其余震荡。
  两个口径：大盘 = 上证指数；自身 = ETF 复权价（需 200 日历史，之前不判定，按震荡处理）。
诊断：按前一日收盘的环境把每天的收益归类，分别算一直持有与纯 MACD（收 0.1%）在该环境下的年化。
策略（t 日收盘的环境与 MACD 状态决定 t+1 开盘仓位）：
  P1 牛持有 / 震荡 MACD / 熊空仓；P2 牛持有 / 震荡、熊 MACD；P3 牛、震荡 MACD / 熊空仓。
样本、成交、成本同前：页面清单+半导体，上市后第 60 个交易日起，汇总只统计回测期≥3 年。"""
import json, numpy as np, pandas as pd
src = open("research/macd_etf.py").read()
exec(src.split("picked = json.load")[0]); END = "2026-11-10"
exec("def events" + src.split("def events")[1].split("rows, logs = [], {}")[0])
good = set(pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}).query("good").code)

def regime(close):
    ma = close.rolling(200).mean(); up = ma > ma.shift(20)
    r = pd.Series("震荡", index=close.index); r[(close > ma) & up] = "牛"; r[(close < ma) & ~up & ma.notna()] = "熊"; return r
sh = pd.read_csv("data/index_sh000001_ohlc.csv", parse_dates=["date"]).set_index("date").close
mkt = regime(sh)

def daily_navs(d, dv, mult, st, i0, cost):
    """返回逐日净值增长倍数（与 backtest 一致的撮合），用于按环境拆分。"""
    o, c, D, M, s = d.open.values, d.close.values, dv.values, mult.values, st.values
    hold = False; g = []
    for k in range(i0, len(d)):
        want = bool(s[k - 1]); x = 1.0
        if hold: x *= (o[k] + D[k]) * M[k] / c[k - 1]
        if want != hold: x *= 1 - cost; hold = want
        if hold: x *= c[k] / o[k]
        g.append(x)
    return np.array(g)

rows, diag = [], []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code); i0 = 60
    if len(d) < 120: continue
    idx = d.index; years = (idx[-1] - idx[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    macd = macd_state(adj); always = pd.Series(True, index=idx)
    reg = {"大盘": mkt.reindex(idx).ffill().fillna("震荡"), "自身": regime(adj)}
    r = dict(code=code, name=name, years=years, good=code in good)
    gh = daily_navs(d, dv, mult, always, i0, 0.0); gm = daily_navs(d, dv, mult, macd, i0, 0.001)
    for lens, rg in reg.items():
        prev = rg.shift(1).iloc[i0:].values           # 当天收益属于前一日收盘判定的环境
        for state in ("牛", "震荡", "熊"):
            msk = prev == state
            if msk.sum() < 20: continue
            diag.append(dict(code=code, good=code in good, long=years >= 3, lens=lens, state=state, days=msk.sum(), share=msk.mean(),
                             hold=np.prod(gh[msk]) ** (244 / msk.sum()) - 1, macd=np.prod(gm[msk]) ** (244 / msk.sum()) - 1))
        pol = {"P1": (rg == "牛") | ((rg == "震荡") & macd), "P2": (rg == "牛") | ((rg != "牛") & macd), "P3": (rg != "熊") & macd}
        for k, st in pol.items():
            st = st.astype(bool); n, tr = backtest(d, dv, mult, st, i0, 0.001)
            a, _ = backtest(d.iloc[:mid + 1], dv.iloc[:mid + 1], mult.iloc[:mid + 1], st.iloc[:mid + 1], i0, 0.001); b, _ = backtest(d, dv, mult, st, mid, 0.001)
            r[f"{lens}{k}"], r[f"{lens}{k}_dd"], r[f"{lens}{k}_h1"], r[f"{lens}{k}_h2"] = ann(n), mdd(n), ann(a), ann(b)
    for k, st in (("H", always), ("M", macd)):
        n, _ = backtest(d, dv, mult, st, i0, 0.0 if k == "H" else 0.001)
        a, _ = backtest(d.iloc[:mid + 1], dv.iloc[:mid + 1], mult.iloc[:mid + 1], st.iloc[:mid + 1], i0, 0.0 if k == "H" else 0.001); b, _ = backtest(d, dv, mult, st, mid, 0.0 if k == "H" else 0.001)
        r[k], r[k + "_dd"], r[k + "_h1"], r[k + "_h2"] = ann(n), mdd(n), ann(a), ann(b)
    rows.append(r)
t = pd.DataFrame(rows); g = pd.DataFrame(diag); t.to_csv("research/macd_regime_results.csv", index=False); g.to_csv("research/macd_regime_diag.csv", index=False)

print("==== 诊断：各环境下的年化（中位数，%；只算回测≥3年的 ETF）")
for lens in ("大盘", "自身"):
    for label, sel in (("全部", g.long), ("MACD优秀", g.good)):
        x = g[(g.lens == lens) & sel]
        print(f"  [{lens}·{label}]")
        for state in ("牛", "震荡", "熊"):
            y = x[x.state == state]
            print(f"     {state:<3} 占时间 {y.share.median()*100:4.0f}%  持有 {y.hold.median()*100:+7.1f}  MACD {y.macd.median()*100:+7.1f}  MACD 更好 {(y.macd > y.hold).sum():2d}/{len(y)}")
names = {"H": "一直持有", "M": "纯MACD", "P1": "牛持有/震荡MACD/熊空仓", "P2": "牛持有/其余MACD", "P3": "牛震荡MACD/熊空仓"}
for label, sel in (("回测≥3年全部", t[t.years >= 3]), ("MACD优秀 17 只", t[t.good])):
    print(f"\n==== 策略对比：{label}（{len(sel)} 只）")
    print(f"   {'策略':<22}{'年化中位':>8}{'年化均值':>8}{'胜纯MACD':>9}{'胜持有':>8}{'前后半都胜MACD':>13}{'回撤中位':>8}")
    for k in ("H", "M"):
        print(f"   {names[k]:<20}{sel[k].median()*100:+8.2f}{sel[k].mean()*100:+8.2f}{'':>9}{'':>8}{'':>13}{sel[k+'_dd'].median()*100:8.1f}")
    for lens in ("大盘", "自身"):
        for k in ("P1", "P2", "P3"):
            c = f"{lens}{k}"
            print(f"   {lens+'·'+names[k]:<20}{sel[c].median()*100:+8.2f}{sel[c].mean()*100:+8.2f}{(sel[c]>sel.M).sum():>6}/{len(sel)}{(sel[c]>sel.H).sum():>5}/{len(sel)}{((sel[c+'_h1']>sel.M_h1)&(sel[c+'_h2']>sel.M_h2)).sum():>10}/{len(sel)}{sel[c+'_dd'].median()*100:8.1f}")
sw = (mkt != mkt.shift()).loc["2013":].sum() / (len(mkt.loc["2013":]) / 244)
print(f"\n大盘环境（上证）2013 年以来平均每年切换 {sw:.1f} 次；各环境占时间：", (mkt.loc["2013":].value_counts(normalize=True) * 100).round(0).to_dict())
