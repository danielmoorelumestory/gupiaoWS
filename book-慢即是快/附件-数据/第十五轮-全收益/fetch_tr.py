"""第十五轮：抓取全收益（含分红再投资）指数日线，原始响应存 raw/，清洗后存 CSV（date,close）。
来源：中证指数有限公司官网行情接口 https://www.csindex.com.cn/csindex-home/perf/index-perf
用法：python3 fetch_tr.py   （在本目录运行）"""
import json, csv, urllib.request, datetime, pathlib
ROOT = pathlib.Path(__file__).resolve().parent
CSI = {"H00300": "沪深300全收益", "H00922": "中证红利全收益", "H00905": "中证500全收益",
       "000300": "沪深300（价格，用于对照）", "000922": "中证红利（价格，用于对照）"}
def csindex(code, start="20080101", end="20260930"):
    url = f"https://www.csindex.com.cn/csindex-home/perf/index-perf?indexCode={code}&startDate={start}&endDate={end}"
    raw = urllib.request.urlopen(url, timeout=60).read()
    (ROOT / "raw" / f"csindex_{code}.json").write_bytes(raw)
    rows = [(f"{r['tradeDate'][:4]}-{r['tradeDate'][4:6]}-{r['tradeDate'][6:]}", float(r["close"])) for r in json.loads(raw)["data"] if r.get("close")]
    return url, sorted(rows)
if __name__ == "__main__":
    log = []
    for code, name in CSI.items():
        url, rows = csindex(code)
        with open(ROOT / f"{code}.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["date", "close"]); w.writerows(rows)
        log.append([code, name, url, datetime.datetime.now().isoformat(timespec="seconds"), len(rows), rows[0][0], rows[-1][0]])
        print(code, name, len(rows), rows[0][0], rows[-1][0])
    with open(ROOT / "抓取记录.csv", "a", newline="") as f:
        csv.writer(f).writerows(log)

# ---- 追加：创业板R（深交所全收益，腾讯行情接口）与标普500全收益（Yahoo Finance）----
import time
from zoneinfo import ZoneInfo
def tencent(code):
    rows = {}
    for y in range(2010, 2027):
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,{y}-01-01,{y}-12-31,800,qfq"
        raw = urllib.request.urlopen(url, timeout=30).read()
        (ROOT / "raw" / f"tencent_{code}_{y}.json").write_bytes(raw)
        data = json.loads(raw)["data"]
        if isinstance(data, dict) and code in data:
            for r in data[code].get("qfqday") or data[code].get("day") or []: rows[r[0]] = float(r[2])
        time.sleep(0.2)
    return "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" + code + ",day,<年>-01-01,<年>-12-31,800,qfq", sorted(rows.items())
def yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?period1=1199145600&period2=1790899200&interval=1d"
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    (ROOT / "raw" / f"yahoo_{symbol.strip('^')}.json").write_bytes(raw)
    res = json.loads(raw)["chart"]["result"][0]; ny = ZoneInfo("America/New_York")
    closes = res["indicators"]["quote"][0]["close"]
    return url, sorted((datetime.datetime.fromtimestamp(t, ny).date().isoformat(), float(c)) for t, c in zip(res["timestamp"], closes) if c is not None)
import urllib.parse
def main2():
    log = []
    for code, name, fn in (("sz399606", "创业板R（全收益）", tencent), ("^SP500TR", "标普500全收益（美元）", yahoo), ("^GSPC", "标普500价格（美元，用于对照）", yahoo)):
        url, rows = fn(code)
        out = code.strip("^")
        with open(ROOT / f"{out}.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["date", "close"]); w.writerows(rows)
        log.append([code, name, url, datetime.datetime.now().isoformat(timespec="seconds"), len(rows), rows[0][0], rows[-1][0]])
        print(code, name, len(rows), rows[0][0], rows[-1][0])
    with open(ROOT / "抓取记录.csv", "a", newline="") as f:
        csv.writer(f).writerows(log)
