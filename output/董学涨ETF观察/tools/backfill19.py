"""一次性回补 19 池 2024 年以前的历史（HIST_START ~ 2023-12-29），保存官方原始响应并写入 data/cache19。

为什么单独做：产品种子（来自研究目录）只覆盖 2024-01-02 起；19 只中最晚成立的 560010（2022-07-28 成立）、
159629（2022-07-27 成立）2022-08 上市，之前不存在 19 只共同数据。此工具只取 2024 以前缺的部分，不重抓 2024 以后。

- 上交所：commonQuery 逐交易日（限速 0.4s），原始 JSON gzip 存 data/seed19/raw_pre2024/sse/<date>.json.gz
- 深交所：scsj_fund_jjgm 按季度 XLSX，原始文件存 data/seed19/raw_pre2024/szse/<YYYYQn>.xlsx.gz
- 交易日历：BaoStock query_trade_dates；指数/510300 收盘价：BaoStock 不复权日线（由 composite.fetch_index 写缓存）
- 净值/分红送配（含份额折算事件）：东方财富 lsjz（由 nav.fetch_nav 只取 HIST_START~2024-01-10 并与缓存合并）
manifest.json 记录每个原始文件的 URL、参数、抓取时间、sha256。已存在的原始文件直接复用（可断点续跑）。
用法：.venv/bin/python tools/backfill19.py
"""
import gzip
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dxz import composite as cm  # noqa: E402
from dxz import nav as navmod  # noqa: E402
from dxz import pool19 as p19  # noqa: E402
from dxz import quotes as qmod  # noqa: E402
from dxz import shares as shmod  # noqa: E402
from dxz.common import http, now_iso, read_json, session, write_json_atomic  # noqa: E402

RAW = os.path.join(ROOT, "data", "seed19", "raw_pre2024")
END = "2023-12-31"
MAN = os.path.join(RAW, "manifest.json")


def save_raw(rel, content: bytes, url, params, man):
    p = os.path.join(RAW, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(gzip.compress(content, mtime=0))
    man[rel] = {"url": url, "params": {k: v for k, v in params.items() if k != "random"}, "fetched_at": now_iso(),
                "sha256_raw": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def main():
    log, man = [], read_json(MAN) or {}
    sess = session()
    cal = cm.calendar19(None, None, log)[0]
    dates = [d for d in cal if p19.HIST_START <= d <= END]
    print(f"交易日 {len(dates)}：{dates[0]}~{dates[-1]}")
    sh = [c for c in p19.CODES19 if c[0] in "56"]
    sz = [c for c in p19.CODES19 if c[0] not in "56"]
    # 上交所逐日
    for i, d in enumerate(dates):
        rel = f"sse/{d}.json.gz"
        cp = os.path.join(cm.CACHE19, "sse", f"{d}.json")
        if rel in man and os.path.exists(os.path.join(RAW, rel)):
            raw = json.loads(gzip.open(os.path.join(RAW, rel)).read())
            at = man[rel]["fetched_at"]
        else:
            params = {"sqlId": shmod.SSE_SQLID, "isPagination": "true", "STAT_DATE": d, "pageHelp.pageSize": "10000",
                      "pageHelp.pageNo": "1", "pageHelp.beginPage": "1", "pageHelp.cacheSize": "1", "pageHelp.endPage": "1"}
            r = http(sess, "GET", shmod.SSE_URL, params=params, headers={"Referer": "http://www.sse.com.cn/"})
            raw = r.json()
            if not (raw.get("result") or []):  # 空响应不落盘为有效原始文件，重试一次
                time.sleep(2)
                r = http(sess, "GET", shmod.SSE_URL, params=params, headers={"Referer": "http://www.sse.com.cn/"})
                raw = r.json()
            save_raw(rel, r.content, shmod.SSE_URL, params, man)
            at = man[rel]["fetched_at"]
            time.sleep(0.4)
        got, nm, errs = shmod.parse_sse(raw, d, sh)
        log.extend(errs)
        if got:
            write_json_atomic(cp, {"date": d, "fetched_at": at, "shares": got, "names": nm, "raw": rel})
        else:
            log.append(f"上交所 {d} 原始响应无观察池数据（{len(raw.get('result') or [])} 行）")
        if i % 50 == 0:
            write_json_atomic(MAN, man)
            print(i, d, len(got))
    write_json_atomic(MAN, man)
    # 深交所按季度
    for key, lo, hi, qend in shmod.quarter_ranges(p19.HIST_START, END):
        rel = f"szse/{key}.xlsx.gz"
        if rel in man and os.path.exists(os.path.join(RAW, rel)):
            content, at = gzip.open(os.path.join(RAW, rel)).read(), man[rel]["fetched_at"]
        else:
            params = {"SHOWTYPE": "xlsx", "CATALOGID": shmod.SZSE_CATALOG, "TABKEY": "tab1", "txtStart": lo, "txtEnd": hi,
                      "jjlb": "ETF", "random": f"{time.time():.6f}"}
            r = http(sess, "GET", shmod.SZSE_XLSX_URL, params=params, headers={"Referer": shmod.SZSE_PAGE_URL}, timeout=60)
            content = r.content
            save_raw(rel, content, shmod.SZSE_XLSX_URL, params, man)
            at = man[rel]["fetched_at"]
            time.sleep(1)
        got, nm, errs = shmod.parse_szse_xlsx(content, sz, lo, hi)
        log.extend(errs)
        write_json_atomic(os.path.join(cm.CACHE19, "szse", f"{key}.json"),
                          {"key": key, "lo": lo, "hi": hi, "codes": sz, "fetched_at": at, "shares": got, "names": nm, "raw": rel})
        print(key, len(got), "日")
    write_json_atomic(MAN, man)
    # 净值/折算事件：只补 2024 以前，与现有缓存合并
    for c in p19.CODES19:
        _, ev, st = navmod.fetch_nav(sess, c, p19.HIST_START, "2024-01-10", cm.CACHE19, log)
        print("nav", c, st.get("ok"), {d: t for d, t in ev.items() if d < "2024"})
    # 指数与 510300 收盘价（BaoStock，自动从 HIST_START 回补）
    with qmod.BaoStock() as bs:
        for b in p19.PRICE_KEYS:
            have, st = cm.fetch_index(bs, b, p19.HIST_START, "2024-01-10", cm.CACHE19, log)
            print("index", b, st, min(have), len(have))
    print("\n".join(log[-40:]))


if __name__ == "__main__":
    main()
