"""东方财富公开基金历史净值（单位净值 DWJZ，元/份）。

- 接口 api.fund.eastmoney.com/f10/lsjz 服务端实测每页最多返回 20 行（请求更大 pageSize 也会被截短），
  因此按“实际返回行数”逐页翻页直到 TotalCount / 空页 / 页数上限；只接受 FSRQ 落在请求区间内的行。
- 同时保留 FHSP（分红送配说明）与 FHFCZ（折算比例），用于标记分红/份额折算日。
- 绝不用最新净值回填历史日期；缺日即缺。
缓存：data/cache/nav/<code>.json；增量更新从已有最新日期前 15 天开始重取（覆盖修订）。
"""
from __future__ import annotations

import os
import time
from datetime import date as _date, timedelta

from .common import SourceError, http, norm_date, now_iso, num, read_json, write_json_atomic

NAV_URL = "https://api.fund.eastmoney.com/f10/lsjz"
NAV_PAGE_URL = "https://fundf10.eastmoney.com/jjjz_{code}.html"
MAX_PAGES = 80


def parse_nav_page(raw, lo: str, hi: str):
    """→ (navs{date:nav}, events{date:text}, rows_count, total, errors)。"""
    if not isinstance(raw, dict):
        raise SourceError("净值响应格式异常")
    if raw.get("ErrCode") not in (None, 0, "0"):
        raise SourceError(f"净值接口错误 {raw.get('ErrCode')} {raw.get('ErrMsg') or ''}")
    rows = (raw.get("Data") or {}).get("LSJZList")
    if not isinstance(rows, list):
        raise SourceError("净值响应缺少 LSJZList")
    navs, events, errs = {}, {}, []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = norm_date(r.get("FSRQ"))
        if d is None:
            continue
        if d < lo or d > hi:
            errs.append(f"净值返回区间外日期 {d}，已拒绝")
            continue
        v = num(r.get("DWJZ"))
        if v is None or v <= 0:
            errs.append(f"净值 {d} 单位净值无效 {r.get('DWJZ')!r}，未采用")
        else:
            if d in navs and navs[d] != v:
                errs.append(f"净值 {d} 同日冲突值，已拒绝")
                navs[d] = None
            elif navs.get(d, 0) is not None:
                navs[d] = v
        # 实测 FHFCZ 在普通现金分红日也有值（=每份派现金额），不能据此判断份额折算；只保留 FHSP 原文
        ev = str(r.get("FHSP") or "").strip()
        if ev:
            events[d] = ev
    navs = {d: v for d, v in navs.items() if v is not None}
    try:
        total = int(raw.get("TotalCount"))
    except (TypeError, ValueError):
        total = None
    return navs, events, len(rows), total, errs


def fetch_nav(sess, code: str, start: str, end: str, cache_dir: str, log: list, pause=0.25):
    """返回 (navs{date:nav}, events{date:text}, meta)。失败沿用缓存并写 log。"""
    p = os.path.join(cache_dir, "nav", f"{code}.json")
    c = read_json(p) or {}
    navs = {d: v for d, v in (c.get("navs") or {}).items() if num(v) and num(v) > 0}
    events = dict(c.get("events") or {})
    lo = start
    if navs and min(navs) <= _date.fromordinal(_date.fromisoformat(start).toordinal() + 10).isoformat():
        lo = max(start, (_date.fromisoformat(max(navs)) - timedelta(days=15)).isoformat())
    page, size, got = 1, 20, 0
    new, new_ev = {}, {}
    ok = True
    while page <= MAX_PAGES:
        try:
            r = http(sess, "GET", NAV_URL, params={
                "fundCode": code, "pageIndex": str(page), "pageSize": str(size),
                "startDate": lo, "endDate": end},
                headers={"Referer": "https://fundf10.eastmoney.com/"})
            part, ev, n, total, errs = parse_nav_page(r.json(), lo, end)
        except (SourceError, ValueError) as e:
            log.append(f"净值 {code} 第{page}页获取失败：{e}；已取到的保留，其余沿用缓存")
            ok = False
            break
        for e in errs:
            log.append(f"净值 {code} {e}")
        for d, v in part.items():
            if d in new and new[d] != v:
                log.append(f"净值 {code} {d} 跨页冲突，已拒绝")
                new[d] = None
            elif d not in new:
                new[d] = v
        new_ev.update(ev)
        got += n
        if n == 0 or (total is not None and got >= total):
            break
        if page == 1 and n < size:
            if not (total and total > n):
                break
            size = n  # 服务端截短页大小：按实际页大小从第 2 页续翻
        elif page > 1 and n < size:
            break  # 最后一页
        page += 1
        if pause:
            time.sleep(pause)
    else:
        log.append(f"净值 {code} 超过 {MAX_PAGES} 页上限，未取完")
        ok = False
    for d, v in new.items():
        if v is None:
            navs.pop(d, None)
        else:
            navs[d] = v
    events.update(new_ev)
    if new:
        write_json_atomic(p, {"code": code, "fetched_at": now_iso(), "navs": dict(sorted(navs.items())),
                              "events": events})
    return navs, events, {"ok": ok, "fetched_at": now_iso() if new else c.get("fetched_at")}
