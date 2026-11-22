"""交易所官方 ETF 场内份额（日频）采集。

来源与口径（解析规则改写自 output/同花顺ETF资金/app/auto_daily.py 的 parse_sse_rows /
parse_szse_xlsx，复制到此处以保证独立运行）：
- 上交所 commonQuery.do sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L，只能按 STAT_DATE
  单日查询全市场；TOT_VOL 单位“万份”（两位小数）→ ×10000 = 份。行内 STAT_DATE 必须等于请求日。
- 深交所 ShowReport CATALOGID=scsj_fund_jjgm 区间 XLSX；实测区间过长（>约一年）返回空，
  因此按自然季度分段请求。表头“基金规模(份)”/“(万份)”按表头单位换算，未识别单位整批拒绝。
- 缺项一律不补 0；与请求日不符的行拒绝；冲突重复行拒绝。

缓存：data/cache/sse/<date>.json、data/cache/szse/<YYYYQn>.json。已结束且抓取时间晚于季末
7 天的季度视为终版不再重取；当前季度每次重取，失败沿用旧缓存并报告。
"""
from __future__ import annotations

import io
import os
import time
from datetime import date as _date

from .common import (SourceError, http, norm_code, norm_date, now_iso, num, read_json,
                     write_json_atomic)

SSE_URL = "http://query.sse.com.cn/commonQuery.do"
SSE_SQLID = "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L"
SSE_PAGE_URL = "https://www.sse.com.cn/market/funddata/volumn/etfvolumn/"
SZSE_XLSX_URL = "https://www.szse.cn/api/report/ShowReport"
SZSE_PAGE_URL = "https://www.szse.cn/market/fund/volume/etf/index.html"
SZSE_CATALOG = "scsj_fund_jjgm"


# ------------------------------------------------------------------ 解析（纯函数）

def parse_sse(raw, d: str, codes) -> tuple[dict, dict, list]:
    """上交所响应 → ({code: 份}, {code: 简称}, errors)。只收 codes 内、STAT_DATE==d 的行。"""
    if not isinstance(raw, dict) or not isinstance(raw.get("result"), list):
        raise SourceError("上交所响应缺少 result 列表")
    want = set(codes)
    out, names, errs, conflicts = {}, {}, [], set()
    mismatched = 0
    for row in raw["result"]:
        if not isinstance(row, dict):
            continue
        code = norm_code(row.get("SEC_CODE"))
        if code not in want:
            continue
        if norm_date(row.get("STAT_DATE")) != d:
            mismatched += 1
            continue
        wan = num(row.get("TOT_VOL"))
        if wan is None or wan <= 0:
            errs.append(f"上交所 {d} {code} 份额无效 {row.get('TOT_VOL')!r}，未采用")
            continue
        v = round(wan * 10000, 2)
        if code in out and out[code] != v:
            conflicts.add(code)
        out[code] = v
        names[code] = str(row.get("SEC_NAME") or "").strip()
    for c in conflicts:
        out.pop(c, None)
        errs.append(f"上交所 {d} {c} 冲突重复行，已拒绝")
    if mismatched:
        errs.append(f"上交所 {d} 有 {mismatched} 行日期与请求日不符，已拒绝")
    return out, names, errs


def unit_factor(header: str) -> float:
    h = str(header or "").replace(" ", "").replace("<br>", "")
    if "万份" in h:
        return 10000.0
    if "(份)" in h or "（份）" in h:
        return 1.0
    raise SourceError(f"深交所份额列单位无法识别：{header!r}")


def parse_szse_rows(rows, codes, lo: str, hi: str) -> tuple[dict, dict, list]:
    """深交所 XLSX 行（含表头）→ ({date: {code: 份}}, {code: 简称}, errors)。"""
    rows = list(rows)
    hi_idx = None
    for i, r in enumerate(rows[:20]):
        cells = [str(c or "").strip() for c in r]
        if any("基金代码" in c for c in cells) and any("日期" in c for c in cells):
            hi_idx = i
            break
    if hi_idx is None:
        raise SourceError("深交所 XLSX 未找到含“日期”“基金代码”的表头")
    head = [str(c or "").strip() for c in rows[hi_idx]]
    di = next(i for i, c in enumerate(head) if "日期" in c)
    ci = next(i for i, c in enumerate(head) if "基金代码" in c)
    ni = next((i for i, c in enumerate(head) if "简称" in c), None)
    vi = next((i for i, c in enumerate(head) if "规模" in c or "份额" in c), None)
    if vi is None:
        raise SourceError("深交所 XLSX 未找到规模/份额列")
    factor = unit_factor(head[vi])
    want = set(codes)
    out, names, errs, conflicts = {}, {}, [], set()
    outside = 0
    for r in rows[hi_idx + 1:]:
        g = lambda i: r[i] if i is not None and len(r) > i else None  # noqa: E731
        code = norm_code(g(ci))
        if code not in want:
            continue
        d = norm_date(g(di))
        if d is None:
            errs.append(f"深交所 {code} 有日期无效行，已忽略")
            continue
        if d < lo or d > hi:
            outside += 1
            continue
        v = num(g(vi))
        if v is None or v <= 0:
            errs.append(f"深交所 {d} {code} 份额无效 {g(vi)!r}，未采用")
            continue
        val = round(v * factor, 2)
        day = out.setdefault(d, {})
        if code in day and day[code] != val:
            conflicts.add((d, code))
        day[code] = val
        if ni is not None:
            names[code] = str(g(ni) or "").strip()
    for d, c in conflicts:
        out[d].pop(c, None)
        errs.append(f"深交所 {d} {c} 冲突重复行，已拒绝")
    if outside:
        errs.append(f"深交所返回 {outside} 行不在请求区间 {lo}~{hi}，已忽略")
    return out, names, errs


def parse_szse_xlsx(content: bytes, codes, lo, hi):
    import warnings

    import openpyxl
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # 该文件 dimension 声明错误，read_only 模式只读到 1 行，必须 read_only=False（auto_daily 实测）
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=False, data_only=True)
    except Exception as e:  # noqa: BLE001
        raise SourceError(f"深交所 XLSX 无法解析：{type(e).__name__}") from e
    ws = wb[wb.sheetnames[0]]
    return parse_szse_rows(ws.iter_rows(values_only=True), codes, lo, hi)


# ------------------------------------------------------------------ 采集

def quarter_ranges(start: str, end: str) -> list[tuple[str, str, str, str]]:
    """[(key, lo, hi, 季末)] 自然季度切片，lo/hi 裁剪到 [start, end]。"""
    from datetime import timedelta
    s, e = _date.fromisoformat(start), _date.fromisoformat(end)
    out = []
    y, q = s.year, (s.month - 1) // 3 + 1
    while True:
        qs = _date(y, 3 * q - 2, 1)
        if qs > e:
            break
        nxt = _date(y + 1, 1, 1) if q == 4 else _date(y, 3 * q + 1, 1)
        qe = nxt - timedelta(days=1)
        out.append((f"{y}Q{q}", max(qs, s).isoformat(), min(qe, e).isoformat(), qe.isoformat()))
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def fetch_sse(sess, dates, codes, cache_dir, log, pause=0.3, refresh_recent: int = 10):
    """逐交易日抓上交所。返回 ({date:{code:份}}, names)。最近 refresh_recent 个交易日若缓存不完整则重取。"""
    out, names = {}, {}
    cdir = os.path.join(cache_dir, "sse")
    recent = set(list(dates)[-refresh_recent:]) if refresh_recent else set()
    for d in dates:
        p = os.path.join(cdir, f"{d}.json")
        c = read_json(p)
        if isinstance(c, dict) and c.get("date") == d and isinstance(c.get("shares"), dict):
            have = {k: v for k, v in c["shares"].items() if num(v) and num(v) > 0}
            # 完整命中；或较早日期的已核验缓存（缺项多为当时未上市），只对最近 refresh_recent 个日期重取
            if all(k in have for k in codes) or (have and d not in recent):
                out[d] = have
                names.update(c.get("names") or {})
                continue
        else:
            have = {}
        try:
            r = http(sess, "GET", SSE_URL, params={
                "sqlId": SSE_SQLID, "isPagination": "true", "STAT_DATE": d,
                "pageHelp.pageSize": "10000", "pageHelp.pageNo": "1", "pageHelp.beginPage": "1",
                "pageHelp.cacheSize": "1", "pageHelp.endPage": "1"},
                headers={"Referer": "http://www.sse.com.cn/"})
            got, nm, errs = parse_sse(r.json(), d, codes)
        except (SourceError, ValueError) as e:
            log.append(f"上交所份额 {d} 获取失败：{e}" + ("；沿用旧缓存" if have else ""))
            if have:
                out[d] = have
            continue
        log.extend(errs)
        merged = {**have, **got}
        if merged:
            out[d] = merged
            names.update(nm)
            write_json_atomic(p, {"date": d, "fetched_at": now_iso(), "shares": merged, "names": nm})
        missing = [c for c in codes if c not in merged]
        if missing:
            log.append(f"上交所 {d} 缺 {','.join(missing)}（未上市/未披露/未发布），未补值")
        if pause:
            time.sleep(pause)
    return out, names


def merge_quarter(old: dict | None, new: dict) -> tuple[dict, list]:
    """按 日期×代码 合并（H2）：新值覆盖同日同码旧值；新结果缺失的日期/代码保留旧值并报告。"""
    old = old or {}
    merged = {d: dict(m) for d, m in old.items()}
    lost = []
    for d, m in new.items():
        merged.setdefault(d, {}).update(m)
    for d, m in old.items():
        miss = [c for c in m if c not in (new.get(d) or {})]
        if miss:
            lost.append((d, miss))
    return merged, lost


def fetch_szse(sess, start, end, codes, cache_dir, log, today: str, pause=0.5):
    """按季度取深交所份额。空/部分响应不会覆盖已有有效缓存：与旧缓存按 日期×代码 合并后再写。
    返回 (shares, names, issues)；issues 记录失败/沿用缓存/缺失。"""
    out, names, issues = {}, {}, []
    cdir = os.path.join(cache_dir, "szse")
    for key, lo, hi, qend in quarter_ranges(start, end):
        p = os.path.join(cdir, f"{key}.json")
        c = read_json(p)
        old = c.get("shares") if isinstance(c, dict) and isinstance(c.get("shares"), dict) else None
        final = (old is not None
                 and str(c.get("lo") or "9") <= lo and str(c.get("hi") or "0") >= hi
                 and str(c.get("fetched_at", ""))[:10] > _date.fromordinal(
                     _date.fromisoformat(qend).toordinal() + 7).isoformat()
                 and all(k in (c.get("codes") or []) for k in codes))
        if final:
            got = old
        else:
            try:
                r = http(sess, "GET", SZSE_XLSX_URL, params={
                    "SHOWTYPE": "xlsx", "CATALOGID": SZSE_CATALOG, "TABKEY": "tab1",
                    "txtStart": lo, "txtEnd": hi, "jjlb": "ETF", "random": f"{time.time():.6f}"},
                    headers={"Referer": SZSE_PAGE_URL}, timeout=60)
                new, nm, errs = parse_szse_xlsx(r.content, codes, lo, hi)
                log.extend(errs)
                names.update(nm)
                got, lost = merge_quarter(old, new)
                if not new:
                    msg = f"深交所 {key} 返回 0 行观察池数据" + (f"；沿用 {c.get('fetched_at')} 缓存" if old else "")
                    log.append(msg)
                    issues.append(msg)
                elif lost:
                    msg = (f"深交所 {key} 本次响应缺 {len(lost)} 个日期的部分代码（如 {lost[0][0]} {','.join(lost[0][1])}），"
                           f"已保留 {c.get('fetched_at')} 缓存中的值")
                    log.append(msg)
                    issues.append(msg)
                if new:
                    write_json_atomic(p, {"key": key, "lo": min(lo, str((c or {}).get("lo") or lo)),
                                          "hi": max(hi, str((c or {}).get("hi") or hi)), "codes": list(codes),
                                          "fetched_at": now_iso(), "shares": got,
                                          "names": {**((c or {}).get("names") or {}), **nm}})
            except SourceError as e:
                got = old or {}
                msg = f"深交所 {key} 获取失败：{e}；" + (f"沿用 {c.get('fetched_at')} 缓存" if old else "该季度无数据")
                log.append(msg)
                issues.append(msg)
            if pause:
                time.sleep(pause)
        if isinstance(c, dict):
            names.update({k: v for k, v in (c.get("names") or {}).items() if k not in names})
        for d, m in got.items():
            if lo <= d <= hi and d <= today:
                out.setdefault(d, {}).update(m)
    return out, names, issues
