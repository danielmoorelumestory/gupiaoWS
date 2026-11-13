"""获取预先指定面板并审查价格/份额/现金因子，不计算策略收益。标准库。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import bisect
import csv
import gzip
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT / "protocol.json").read_text())
RAW = ROOT / "data/raw"
RAW.mkdir(parents=True, exist_ok=True)
PRIOR_TRANSPORT_FAILURES = set()
if (ROOT / "data_audit-before-tencent.json").exists():
    PRIOR_TRANSPORT_FAILURES = {r["code"] for r in json.loads(
        (ROOT / "data_audit-before-tencent.json").read_text())["symbols"] if r["status"] == "data_error"}


def obtain(name, url):
    path = RAW / name
    if path.exists():
        return gzip.decompress(path.read_bytes())
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                   "Referer": "https://quote.eastmoney.com/"})
    last = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                body = response.read()
            path.write_bytes(gzip.compress(body, mtime=0))
            return body
        except Exception as exc:
            last = exc
            time.sleep(0.5)
    raise RuntimeError(str(last))


def tencent_quotes(code, adjustment):
    symbol = ("sh" if code.startswith("5") else "sz") + code
    merged, urls = {}, []
    mode = "hfq" if adjustment == 2 else ""
    for year in range(2010, 2027, 2):
        start = f"{year}-01-01"
        end = f"{year+2}-01-01" if year < 2026 else "2026-11-11"
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,{start},{end},700,{mode}"
        body = obtain(f"{code}-tencent-{adjustment}-{year}.json.gz", url)
        payload = json.loads(body)
        if payload.get("code") != 0:
            raise ValueError(f"腾讯日线请求失败：{payload.get('msg')}")
        data = payload.get("data")
        item = data.get(symbol, {}) if isinstance(data, dict) else {}
        bars = item.get("hfqday", item.get("day", [])) if adjustment == 2 else item.get("day", [])
        for a in bars:
            if not PROTOCOL["history_start"] <= a[0] <= PROTOCOL["data_cutoff"]:
                continue
            o, c, h, lo = map(Decimal, a[1:5])
            if any(not v.is_finite() or v <= 0 for v in (o, c, h, lo)) or not lo <= min(o, c) <= max(o, c) <= h:
                raise ValueError(f"腾讯OHLC无效：{a[0]}")
            row = dict(date=a[0], open=o, high=h, low=lo, close=c, volume=Decimal(a[5]))
            if a[0] in merged and merged[a[0]] != row:
                raise ValueError(f"腾讯分片重叠但价格不同：{a[0]}")
            merged[a[0]] = row
        urls.append(url)
    rows = [merged[d] for d in sorted(merged)]
    if not rows:
        raise ValueError("腾讯分片没有行情")
    return rows, f"Tencent:{code}", urls


def quotes(code, adjustment):
    if code in PRIOR_TRANSPORT_FAILURES and not (RAW / f"{code}-em-{adjustment}.json.gz").exists():
        return tencent_quotes(code, adjustment)
    params = dict(secid=f"{'1' if code.startswith('5') else '0'}.{code}", klt="101",
                  fqt=str(adjustment), beg=PROTOCOL["history_start"].replace("-", ""),
                  end=PROTOCOL["data_cutoff"].replace("-", ""), lmt="100000",
                  fields1="f1,f2,f3,f4,f5,f6", fields2="f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61")
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
    body = obtain(f"{code}-em-{adjustment}.json.gz", url)
    data = json.loads(body).get("data")
    if not data or data.get("code") != code:
        raise ValueError("行情返回为空或标的代码不符")
    rows = []
    for line in data["klines"]:
        a = line.split(",")
        if not PROTOCOL["history_start"] <= a[0] <= PROTOCOL["data_cutoff"]:
            continue
        o, c, h, lo = map(Decimal, a[1:5])
        if any(not x.is_finite() or x <= 0 for x in (o, c, h, lo)) or not lo <= min(o, c) <= max(o, c) <= h:
            raise ValueError(f"OHLC无效：{a[0]}")
        rows.append(dict(date=a[0], open=o, high=h, low=lo, close=c, volume=Decimal(a[5])))
    if not rows or any(b["date"] <= a["date"] for a, b in zip(rows, rows[1:])):
        raise ValueError("行情日期非严格升序或为空")
    return rows, data.get("name"), url


def factors(code):
    symbol = ("sh" if code.startswith("5") else "sz") + code
    url = f"https://finance.sina.com.cn/realstock/company/{symbol}/hfq.js"
    text = obtain(f"{code}-sina-factors.js.gz", url).decode("gb18030", errors="replace")
    if not text.startswith(f"var {symbol}hfq="):
        raise ValueError("份额/现金因子响应标的不符")
    payload, _ = json.JSONDecoder().raw_decode(text.split("=", 1)[1])
    rows = sorted(payload.get("data", []), key=lambda x: x["d"])
    out = []
    for r in rows:
        if r["d"] > PROTOCOL["data_cutoff"]:
            continue
        f, s, u = Decimal(r["f"]), Decimal(r["s"]), Decimal(r["u"])
        if f != 1 or not s.is_finite() or s <= 0 or not u.is_finite() or u < 0:
            raise ValueError(f"未支持或无效因子：{r}")
        if out and u < out[-1][2]:
            raise ValueError(f"累积现金非单调，须人工审查：{r}")
        out.append((r["d"], s, u))
    if not out:
        raise ValueError("没有可用份额/现金因子")
    return out, url


def prepare(item):
    code = item["code"]
    raw, name, raw_url = quotes(code, 0)
    hfq, _, hfq_url = quotes(code, 2)
    fs, factor_url = factors(code)
    if [r["date"] for r in raw] != [r["date"] for r in hfq]:
        raise ValueError("未复权与后复权日期集合不同")
    dates = [r[0] for r in fs]
    mismatches, max_difference, records = [], Decimal(0), []
    for r, h in zip(raw, hfq):
        k = bisect.bisect_right(dates, r["date"]) - 1
        if k < 0:
            raise ValueError("首行前没有基准因子")
        _, s, u = fs[k]
        adjusted = r["close"] * s + u
        difference = abs(adjusted-h["close"])
        max_difference = max(max_difference, difference)
        tolerance = max(Decimal("0.003"), abs(h["close"])*Decimal("0.001"))
        if difference > tolerance:
            mismatches.append(dict(date=r["date"], raw=str(r["close"]), factor_price=str(adjusted),
                                   vendor_hfq=str(h["close"]), difference=str(difference)))
        records.append({**r, "share_factor": s, "cumulative_cash": u,
                        "adjusted_close": adjusted, "provider_hfq_close": h["close"]})
    audit = {**item, "provider_name": name, "rows": len(records), "first": records[0]["date"],
             "last": records[-1]["date"], "factor_records": [[d, str(s), str(u)] for d, s, u in fs],
             "factor_mismatch_count": len(mismatches), "factor_max_abs_difference": str(max_difference),
             "factor_mismatches": mismatches, "sources": [raw_url, hfq_url, factor_url]}
    if len(mismatches) > len(records)*0.005:
        audit["status"] = "quarantined_factor_disagreement"
    else:
        audit["status"] = "eligible"
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
        path = ROOT / f"data/{code}.csv.gz"
        path.write_bytes(gzip.compress(stream.getvalue().encode(), mtime=0))
        audit["normalized_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        audit["normalized_file"] = str(path.relative_to(ROOT))
    return audit


def main():
    result = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(prepare, item): item for item in PROTOCOL["panel"]}
        for future in as_completed(pending):
            item = pending[future]
            try:
                record = future.result()
            except Exception as exc:
                record = {**item, "status": "data_error", "error": f"{type(exc).__name__}: {exc}"}
            result.append(record)
            print(item["code"], record["status"], record.get("rows", 0),
                  "factor_mismatches", record.get("factor_mismatch_count"), flush=True)
    result.sort(key=lambda x: x["code"])
    output = {"prepared_at_utc": datetime.now(timezone.utc).isoformat(),
              "protocol_sha256": hashlib.sha256((ROOT / "protocol.json").read_bytes()).hexdigest(),
              "data_design_sha256": hashlib.sha256((ROOT / "data_design.json").read_bytes()).hexdigest(),
              "data_design_amendment_sha256": hashlib.sha256((ROOT / "data_design_amendment_01.json").read_bytes()).hexdigest(),
              "transport_amendment_sha256": hashlib.sha256((ROOT / "data_design_amendment_02.json").read_bytes()).hexdigest(),
              "symbols": result,
              "raw_file_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(RAW.glob("*.gz"))}}
    (ROOT / "data_audit.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print("eligible", sum(r["status"] == "eligible" for r in result), "/", len(result))


if __name__ == "__main__":
    main()
