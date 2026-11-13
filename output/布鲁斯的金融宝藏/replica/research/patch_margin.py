"""从交易所原始汇总补齐融资余额缺口：深交所逐日接口（亿元），上交所汇总接口（元）。只取数，不看收益。"""
import akshare as ak, pandas as pd, numpy as np, time
cal = pd.read_csv("data/index_sh000300.csv", parse_dates=["date"]).set_index("date").loc["2010-03-31":"2026-11-09"].index
sz = pd.read_csv("data/margin_sz.csv", parse_dates=["日期"]).set_index("日期")["融资余额"]; sh = pd.read_csv("data/margin_sh.csv", parse_dates=["日期"]).set_index("日期")["融资余额"]
bad_sz = [d for d in cal if not (sz.get(d, 0) > 0)]; bad_sh = [d for d in cal if not (sh.get(d, 0) > 0)]
check = [pd.Timestamp(x) for x in ("2012-06-29", "2015-06-12", "2019-03-29", "2024-10-18", "2025-06-19", "2026-10-30")]   # 既有数据的抽样核对日
rows = []
for d in bad_sz + check:
    val = (np.nan, np.nan)
    for k in range(5):
        try:
            r = ak.stock_margin_szse(date=d.strftime("%Y%m%d")); val = (float(r["融资余额"].iloc[0]), float(r["融资买入额"].iloc[0])) if len(r) else (np.nan, np.nan); break
        except Exception as e: time.sleep(3 + 2 * k)
    rows.append((d, *val, d in check)); time.sleep(0.4)
pd.DataFrame(rows, columns=["date", "融资余额_亿元", "融资买入额_亿元", "核对用"]).to_csv("data/margin_sz_patch_szse.csv", index=False)
rs = []
for d in bad_sh:
    try:
        r = ak.stock_margin_sse(start_date=d.strftime("%Y%m%d"), end_date=d.strftime("%Y%m%d")); rs.append((d, float(r["融资余额"].iloc[0]) if len(r) else np.nan))
    except Exception as e: rs.append((d, np.nan))
    time.sleep(0.4)
pd.DataFrame(rs, columns=["date", "融资余额_元"]).to_csv("data/margin_sh_patch_sse.csv", index=False)
print("done", len(rows), len(rs))
