"""抓取池外候选 ETF 并按 Codex 口径复权（不写入 Codex 冻结目录）。"""
import csv, gzip, io, json, math, statistics, sys, time, urllib.request
from decimal import Decimal as D
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "数据训练优化ETF"))
from prepare_data import normalize_cash_factors
CUTOFF = "2026-11-10"
CANDS = [("159915","创业板"),("159949","创业板50"),("512100","中证1000"),("510500","中证500"),("588000","科创50"),("159939","信息技术"),
         ("159938","医药卫生"),("159998","计算机"),("515030","新能源车"),("515050","5G通信"),("512290","生物医药"),("512580","环保"),
         ("159825","农业"),("513100","纳指"),("159996","家电"),("159995","芯片"),("515000","科技"),("159920","恒生"),
         ("512760","芯片国泰"),("515700","新能车平安"),("512720","计算机国泰"),("515980","人工智能"),("159967","创业板成长"),("159781","科创创业50"),("512670","国防")]
UA = {"User-Agent": "Mozilla/5.0"}
def get(url, headers=UA, tries=2):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r: return r.read()
        except Exception as e:
            err = e; time.sleep(1.5)
    raise RuntimeError(f"{url}: {err}")
def sina_kline(code):
    path = HERE / f"data/raw/{code}-sina-kline.json.gz"
    if not path.exists():
        sym = ("sh" if code[0] == "5" else "sz") + code
        body = get(f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=10000", {**UA, "Referer": "https://finance.sina.com.cn/"})
        path.write_bytes(gzip.compress(body, mtime=0))
    js = json.loads(gzip.decompress(path.read_bytes()))
    return [{"date": r["day"][:10], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"]} for r in js if r["day"][:10] <= CUTOFF]
def tx_hfq(code):
    path = HERE / f"data/raw/{code}-tx-hfq.json.gz"
    sym = ("sh" if code[0] == "5" else "sz") + code
    if not path.exists():
        merged = {}
        for y in range(2004, 2027, 2):
            body = get(f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{y}-01-01,{y+1}-12-31,640,hfq")
            for r in json.loads(body)["data"].get(sym, {}).get("hfqday", []) or []:
                merged[r[0]] = r
            time.sleep(0.3)
        path.write_bytes(gzip.compress(json.dumps(sorted(merged.values())).encode(), mtime=0))
    return {r[0]: D(r[2]) for r in json.loads(gzip.decompress(path.read_bytes())) if r[0] <= CUTOFF}
def em_kline(code, fqt):
    path = HERE / f"data/raw/{code}-em-fqt{fqt}.json.gz"
    if not path.exists():
        if getattr(em_kline, "blocked", False): raise RuntimeError("eastmoney blocked")
        time.sleep(1)
        secid = ("1." if code[0] in "5" else "0.") + code
        body = get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55&klt=101&fqt={fqt}&beg=0&end=20500101")
        if not body.strip(): em_kline.blocked = True; raise RuntimeError("empty")
        path.write_bytes(gzip.compress(body, mtime=0))
    js = json.loads(gzip.decompress(path.read_bytes()))
    rows = []
    for line in js["data"]["klines"]:
        d, o, c, h, l = line.split(",")[:5]
        if d <= CUTOFF: rows.append({"date": d, "open": o, "high": h, "low": l, "close": c})
    return rows
def sina_factors(code):
    symbol = ("sh" if code.startswith("5") else "sz") + code
    path = HERE / f"data/raw/{code}-sina-hfq.js.gz"
    if not path.exists():
        path.write_bytes(gzip.compress(get(f"https://finance.sina.com.cn/realstock/company/{symbol}/hfq.js", {**UA, "Referer": "https://finance.sina.com.cn/"}), mtime=0))
    text = gzip.decompress(path.read_bytes()).decode("gb18030", errors="replace")
    assert text.startswith(f"var {symbol}hfq="), "factor symbol mismatch"
    payload, _ = json.JSONDecoder().raw_decode(text.split("=", 1)[1])
    fs = []
    for row in sorted(payload["data"], key=lambda r: r["d"]):
        if row["d"] > CUTOFF: continue
        f, s, u = D(row["f"]), D(row["s"]), D(row["u"])
        assert f == 1 and s > 0 and u >= 0
        assert not fs or u >= fs[-1][2]
        fs.append((row["d"], s, u))
    return fs
def prepare(code, name):
    import bisect
    src = "eastmoney"
    try: rows = em_kline(code, 0)
    except Exception:
        em_kline.blocked = True
        rows = sina_kline(code); src = "sina"
    cached = HERE.parents[2] / f"布鲁斯的金融宝藏/replica/data/etf_{code}_hfq.csv"
    try: hfq = {r["date"]: D(r["close"]) for r in em_kline(code, 2)}; hsrc = "eastmoney"
    except Exception:
      if cached.exists():
        hfq = {r["date"]: D(r["close"]) for r in csv.DictReader(cached.open()) if r["date"] <= CUTOFF}; hsrc = "cached-eastmoney-hfq"
      else:
        try: hfq = tx_hfq(code); hsrc = "tencent"
        except Exception: hfq = {}; hsrc = None
    fs = sina_factors(code); cap = normalize_cash_factors(fs); fd = [r[0] for r in fs]
    out, flags, mism, checked = [], [], 0, 0
    for i, r in enumerate(rows):
        o, h, l, c = (D(r[k]) for k in ("open","high","low","close"))
        assert min(o,h,l,c) > 0 and l <= min(o,c) <= max(o,c) <= h, (code, r)
        k = bisect.bisect_right(fd, r["date"]) - 1
        if k < 0: s, u = D(1), D(0)  # 首个因子之前：因子未变化
        else: _, s, u = cap[k]
        out.append({**r, "share_factor": str(s), "cumulative_cash": str(u), "adjusted_close": str(c*s+u)})
        if i:
            ps, pu = D(out[-2]["share_factor"]), D(out[-2]["cumulative_cash"])
            if s != ps:
                gap = abs((o*(s/ps)+(u-pu)/ps)/D(out[-2]["close"]) - 1)
                if gap > D("0.08"): flags.append((r["date"], str(gap)))
    # 东财后复权口径与新浪不同基准，比较日收益而非价格水平
    dates = [r["date"] for r in out if r["date"] in hfq]
    for a, b in zip(dates, dates[1:]):
        ra = float(D(out_map(out)[b]["adjusted_close"]) / D(out_map(out)[a]["adjusted_close"])) - 1
        rb = float(hfq[b] / hfq[a]) - 1; checked += 1
        if abs(ra - rb) > 0.003: mism += 1
    status = "eligible" if not flags and checked >= 200 and mism <= 0.005*checked else ("unchecked" if not flags and checked < 200 else "excluded")
    if status != "excluded":  # unchecked 也写出，供信号使用；主结论只用 eligible
        s_ = io.StringIO(newline=""); w = csv.DictWriter(s_, fieldnames=list(out[0]), lineterminator="\n"); w.writeheader(); w.writerows(out)
        (HERE / f"data/{code}.csv.gz").write_bytes(gzip.compress(s_.getvalue().encode(), mtime=0))
    c_ = [float(r["adjusted_close"]) for r in out]
    vol = statistics.pstdev([math.log(c_[i]/c_[i-1]) for i in range(1, len(c_))]) * math.sqrt(244)
    return {"code": code, "name": name, "status": status, "rows": len(out), "first": out[0]["date"], "last": out[-1]["date"],
            "vol": vol, "raw_source": src, "hfq_crosscheck": hsrc, "split_flags": flags, "return_checked": checked, "return_mismatch": mism, "groups": []}
_OM = {}
def out_map(out):
    key = id(out)
    if key not in _OM: _OM.clear(); _OM[key] = {r["date"]: r for r in out}
    return _OM[key]
if __name__ == "__main__":
    res = []
    for code, name in CANDS:
        try: res.append(prepare(code, name))
        except Exception as e: res.append({"code": code, "name": name, "status": f"error: {e}"})
        print(res[-1].get("code"), res[-1].get("name"), res[-1].get("status"), res[-1].get("raw_source"), res[-1].get("hfq_crosscheck"), res[-1].get("first"), res[-1].get("rows"), f"{res[-1].get('vol',0)*100:.1f}%", res[-1].get("return_mismatch"), "/", res[-1].get("return_checked"))
        time.sleep(0.4)
    json.dump(res, open(HERE / "data_audit.json", "w"), ensure_ascii=False, indent=1)
