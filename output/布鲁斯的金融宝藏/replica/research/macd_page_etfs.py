"""页面清单 62 只 ETF 的 MACD 回测，并按事前写定的规则挑出“MACD 优秀”。规则在运行前写定，跑完不改。
数据/撮合：与 macd_etf.py 相同（未复权价 + 东财分红拆分记录，分红记录须与除息日跳空吻合；信号用等比复权连续价，
  等价于前复权；t 日收盘定信号，t+1 开盘成交；MACD 12/26/9，DIF>DEA 持有；单边 0.1%；一直持有 0 费）。
起点：上市后第 60 个交易日开盘，至 2026-11-10。
“MACD 优秀”入选条件（全部满足）：
  1. 回测期 ≥ 3 年；
  2. 整段年化：MACD − 一直持有 ≥ +3 个百分点；
  3. 稳定性：把回测期按交易日对半分，前半段、后半段 MACD 年化都高于一直持有；
  4. 最大回撤：MACD 小于一直持有。"""
import json, pandas as pd, numpy as np
exec(open("research/macd_etf.py").read().split("picked = json.load")[0])
END = "2026-11-10"; EXTRA = {}
exec("def events" + open("research/macd_etf.py").read().split("def events")[1].split("rows, logs = [], {}")[0])
items = json.load(open("data/page_etfs.json")); rows = []
def seg(d, dv, mult, st, a, b):
    sub = d.iloc[:b]; h, _ = backtest(sub, dv.iloc[:b], mult.iloc[:b], pd.Series(True, index=sub.index), a, 0.0)
    m, _ = backtest(sub, dv.iloc[:b], mult.iloc[:b], st.iloc[:b], a, 0.001); return ann(m) - ann(h)
for code, name, grp in items:
    try: d, dv, mult, adj, log = load(code)
    except FileNotFoundError: print("缺数据", code, name); continue
    if len(d) < 120: print("太短", code, name, len(d)); continue
    st = macd_state(adj); i0 = 60
    h, _ = backtest(d, dv, mult, pd.Series(True, index=d.index), i0, 0.0); m, tr = backtest(d, dv, mult, st, i0, 0.001)
    years = (d.index[-1] - d.index[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    r = dict(code=code, name=name, grp=grp, start=d.index[i0].date(), years=years, hold=ann(h), macd=ann(m), hold_cum=h.iloc[-1]-1, macd_cum=m.iloc[-1]-1,
             hold_dd=mdd(h), macd_dd=mdd(m), n=len(tr), win=np.mean(np.array(tr) > 0) if tr else np.nan,
             h1=seg(d, dv, mult, st, i0, mid + 1) if years >= 1 else np.nan, h2=seg(d, dv, mult, st, mid, len(d)) if years >= 1 else np.nan,
             rejected=sum(x.startswith("剔除") for x in log))
    r["ex"] = r["macd"] - r["hold"]
    r["good"] = years >= 3 and r["ex"] >= 0.03 and r["h1"] > 0 and r["h2"] > 0 and r["macd_dd"] > r["hold_dd"]
    rows.append(r)
t = pd.DataFrame(rows).sort_values("ex", ascending=False); t.to_csv("research/macd_page_etfs_results.csv", index=False)
print(f"==== 页面清单 MACD 回测（上市后第 60 个交易日起至 {END}；年化/累计/回撤 %，前半/后半为年化差）")
for _, r in t.iterrows():
    print(f"{'★' if r.good else ' '} {r.code} {r['name']:<14}{r.grp:<8}{str(r.start):>11}{r.years:5.1f}年 持有{r.hold*100:+7.2f} MACD{r.macd*100:+7.2f} 差{r.ex*100:+7.2f} | 前半{r.h1*100:+7.2f} 后半{r.h2*100:+7.2f} | 累计 {r.hold_cum*100:+7.1f}/{r.macd_cum*100:+7.1f} | 回撤 {r.hold_dd*100:6.1f}/{r.macd_dd*100:6.1f} | {r.n}笔 胜率{r.win*100:3.0f}{' 剔除分红记录'+str(r.rejected) if r.rejected else ''}")
ok = t[t.years >= 3]
print(f"\n回测期≥3年 {len(ok)} 只：MACD 年化更高 {(ok.ex>0).sum()}，差≥3pp {(ok.ex>=0.03).sum()}，前后两半都更高 {((ok.h1>0)&(ok.h2>0)).sum()}，回撤更小 {(ok.macd_dd>ok.hold_dd).sum()}；入选 {t.good.sum()} 只")
print("入选：", "、".join(f"{r.code} {r['name']}" for _, r in t[t.good].iterrows()))
