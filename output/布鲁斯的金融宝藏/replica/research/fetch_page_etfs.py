"""下载页面清单 62 只 ETF 的未复权日线（东财，失败改新浪），保存为 data/etf_{code}_raw.csv（已有则跳过）。"""
import json, os, time, pandas as pd, akshare as ak
for code, name, grp in json.load(open("data/page_etfs.json")):
    fn = f"data/etf_{code}_raw.csv"
    if os.path.exists(fn): continue
    df = None
    for attempt in range(3):
        try:
            d = ak.fund_etf_hist_em(symbol=code, period="daily", start_date="20000101", end_date="20261110", adjust="")
            df = pd.DataFrame({"date": pd.to_datetime(d["日期"]).dt.strftime("%Y-%m-%d"), "open": d["开盘"], "high": d["最高"], "low": d["最低"], "close": d["收盘"]}); break
        except Exception as e: time.sleep(2)
    if df is None:
        try:
            d = ak.fund_etf_hist_sina(symbol=("sh" if code[0] == "5" else "sz") + code)
            df = pd.DataFrame({"date": pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d"), "open": d["open"], "high": d["high"], "low": d["low"], "close": d["close"]})
            df = df[df.date <= "2026-11-10"]; print("新浪", code)
        except Exception as e: print("失败", code, name, e); continue
    df.to_csv(fn, index=False); print(code, name, len(df), df.date.iloc[0]); time.sleep(0.5)
