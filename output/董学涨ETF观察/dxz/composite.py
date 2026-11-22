"""视频 19 只 ETF 观察池 · 份额合计观察指数（近似观察版，不是作者完整算法）。

定义（与研究 output/布鲁斯的金融宝藏/research/宽基ETF申赎算法核验20261122 的 A0 一致）：
    I(t)   = 100 × Σ19 Q_i(t) / Σ19 Q_i(基期)，基期固定 2025-11-20 = 100
    ΔS(t)  = Σ19 Q_i(t) − Σ19 Q_i(前一交易日)（份；页面显示亿份）
- Q 为交易所披露的场内份额（份）。19 只任一缺失 → 当日合计/指数为 null，不补 0、不缩池；
  当日或前一交易日不完整 → ΔS 为 null。
- 份额折算/拆分日（净值源 FHSP 含“折算/拆分”）：该日 ΔS 置 null（机械变化不是申赎）；
  折算日之前的指数水平含折算前份额，与之后不可直接比较（rows.pre_split 标记）。
- 基期不完整或合计 ≤0 → 全部指数为 null（base_ok=false，页面显示“不可计算”）。
- 份额跨基金直接相加 = 每份等权，只描述名义份额，不代表人民币资金流；不是全市场，也不是任何机构持仓。

数据：历史种子 data/seed19/composite_seed.json（来自研究目录已核验原始响应，含来源与哈希），
首次运行时写入 data/cache19/（不覆盖已有缓存）；之后复用 shares/nav 采集器做增量，独立于 12 只池的缓存。
"""
from __future__ import annotations

import os
import re
from datetime import date as _date, timedelta

from . import nav as navmod
from . import pool19 as p19
from . import shares as shmod
from .common import now_iso, now_sh, read_json, session, write_json_atomic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE19 = os.path.join(ROOT, "data", "cache19")
SEED = os.path.join(ROOT, "data", "seed19", "composite_seed.json")
OUT = os.path.join(ROOT, "web", "data", "composite.json")
MAIN_QUOTES = os.path.join(ROOT, "data", "cache", "quotes")
SPLIT_RE = re.compile(r"折算|拆分")


# ------------------------------------------------------------------ 纯计算

def split_days(events: dict) -> dict:
    """{code: {date: FHSP 文本}} → {code: [份额折算/拆分日]}。现金分红不算。"""
    return {c: sorted(d for d, t in (ev or {}).items() if SPLIT_RE.search(str(t or ""))) for c, ev in events.items()}


def compute(calendar, shares, codes, base_date, splits=None, start=None):
    """→ (rows, meta)。shares={code:{date:份}}；splits={code:[date]}。纯函数，无 IO。"""
    splits = splits or {}
    split_set = {(c, d) for c, ds in splits.items() for d in ds}
    split_dates = sorted({d for ds in splits.values() for d in ds})
    rows, prev_sum = [], None
    for d in calendar:
        if start and d < start:
            continue
        q = []
        for c in codes:
            v = (shares.get(c) or {}).get(d)
            q.append(v if isinstance(v, (int, float)) and v > 0 else None)
        n = sum(v is not None for v in q)
        complete = n == len(codes)
        s = sum(q) if complete else None
        sp = [c for c in codes if (c, d) in split_set]
        chg = (s - prev_sum) if (s is not None and prev_sum is not None and not sp) else None
        rows.append({"d": d, "n": n, "sum": s, "chg": chg, "split": sp, "q": q})
        prev_sum = s  # 不完整日 → None：下一日的 ΔS 也不可算（不跨缺口）
    base = next((r for r in rows if r["d"] == base_date), None)
    base_sum = base["sum"] if base else None
    base_ok = bool(base_sum and base_sum > 0)
    last_split = split_dates[-1] if split_dates else None
    for r in rows:
        r["idx"] = (100.0 * r["sum"] / base_sum) if (base_ok and r["sum"] is not None) else None
        r["pre_split"] = bool(last_split and r["d"] < last_split)
    complete_rows = [r for r in rows if r["sum"] is not None]
    meta = {
        "base_date": base_date, "base_sum": base_sum, "base_ok": base_ok,
        "base_error": None if base_ok else ("基期不在样本内" if base is None else
                                            f"基期 19 只不完整（{base['n']}/19）" if base["sum"] is None else "基期合计 ≤0"),
        "data_last": complete_rows[-1]["d"] if complete_rows else None,
        "any_last": next((r["d"] for r in reversed(rows) if r["n"] > 0), None),
        "members_last": {c: next((r["d"] for r in reversed(rows) if r["q"][i] is not None), None) for i, c in enumerate(codes)},
        "split_dates": [{"code": c, "date": d} for c, ds in sorted(splits.items()) for d in ds],
        "incomplete_days": [r["d"] for r in rows if 0 < r["n"] < len(codes)][-50:],
        "first_complete": complete_rows[0]["d"] if complete_rows else None,
        "members_first": {c: next((r["d"] for r in rows if r["q"][i] is not None), None) for i, c in enumerate(codes)},
        "early_incomplete": [{"d": r["d"], "missing": [c for i, c in enumerate(codes) if r["q"][i] is None]}
                             for r in rows if complete_rows and r["d"] < complete_rows[0]["d"]],
    }
    return rows, meta


# ------------------------------------------------------------------ 种子 → 缓存

def _quarter_key(d: str) -> str:
    return f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"


def init_cache_from_seed(seed_path=SEED, cache=CACHE19) -> dict:
    """首次运行把种子写成 shares/nav 采集器可识别的缓存格式。只写缺失文件，不覆盖已有缓存。"""
    seed = read_json(seed_path)
    if not seed:
        return {"seeded": False, "reason": "无种子文件"}
    at = seed["provenance"]["fetched_at"]
    wrote = 0
    sh = [c for c in p19.CODES19 if c[0] in "56"]
    sz = [c for c in p19.CODES19 if c[0] not in "56"]
    for d in seed["calendar"]:
        p = os.path.join(cache, "sse", f"{d}.json")
        if os.path.exists(p):
            continue
        m = {c: seed["shares"][c][d] for c in sh if d in seed["shares"].get(c, {})}
        if m:
            write_json_atomic(p, {"date": d, "fetched_at": at, "shares": m,
                                  "names": {c: seed["names"].get(c, "") for c in m}, "seed": True})
            wrote += 1
    qs = {}
    for d in seed["calendar"]:
        for c in sz:
            v = seed["shares"].get(c, {}).get(d)
            if v is not None:
                qs.setdefault(_quarter_key(d), {}).setdefault(d, {})[c] = v
    for key, m in qs.items():
        p = os.path.join(cache, "szse", f"{key}.json")
        if os.path.exists(p):
            continue
        y, q = int(key[:4]), int(key[-1])
        lo = _date(y, 3 * q - 2, 1).isoformat()
        hi = ((_date(y + 1, 1, 1) if q == 4 else _date(y, 3 * q + 1, 1)) - timedelta(days=1)).isoformat()
        # 已结束季度写季末（shares.fetch_szse 据此判终版不再重取）；未结束季度写实际最新日，之后由采集器重取
        hi_c = hi if hi < at[:10] else max(m)
        write_json_atomic(p, {"key": key, "lo": lo, "hi": hi_c, "codes": sz, "fetched_at": at, "shares": m,
                              "names": {c: seed["names"].get(c, "") for c in sz}, "seed": True})
        wrote += 1
    for c, v in seed["nav"].items():
        p = os.path.join(cache, "nav", f"{c}.json")
        if not os.path.exists(p):
            write_json_atomic(p, {"code": c, "fetched_at": at, "navs": v["navs"], "events": v["events"], "seed": True})
            wrote += 1
    if not os.path.exists(os.path.join(cache, "calendar.json")):
        write_json_atomic(os.path.join(cache, "calendar.json"), {"fetched_at": at, "source": "种子（BaoStock query_trade_dates）", "dates": seed["calendar"]})
    for k, closes in seed["index"].items():
        p = os.path.join(cache, "index", f"{k}.json")
        if not os.path.exists(p):
            write_json_atomic(p, {"code": k, "fetched_at": at, "closes": closes, "seed": True})
            wrote += 1
    return {"seeded": True, "files_written": wrote, "provenance": seed["provenance"]}


# ------------------------------------------------------------------ 采集

def fetch_index(client, key, start, end, cache, log):
    """BaoStock 价格指数日收盘（不复权）。增量：从缓存最新日前 10 天重取；失败沿用缓存。"""
    p = os.path.join(cache, "index", f"{key}.json")
    c = read_json(p) or {}
    have = dict(c.get("closes") or {})
    # 缓存已覆盖起点（容差 10 天）→ 只从最新日前 10 天增量；否则从起点整段回补
    covered = have and min(have) <= (_date.fromisoformat(start) + timedelta(days=10)).isoformat()
    lo = max(start, (_date.fromisoformat(max(have)) - timedelta(days=10)).isoformat()) if covered else start
    try:
        rows = client._rows(client.bs.query_history_k_data_plus(key, "date,code,close", start_date=lo, end_date=end,
                                                                frequency="d", adjustflag="3"))
        for r in rows:
            try:
                v = float(r.get("close"))
            except (TypeError, ValueError):
                continue
            if r.get("code") == key and v > 0:
                have[r["date"]] = v
        write_json_atomic(p, {"code": key, "fetched_at": now_iso(), "closes": dict(sorted(have.items()))})
        return have, {"ok": True}
    except Exception as e:  # noqa: BLE001
        log.append(f"指数 {key} 获取失败：{e}；沿用缓存 {c.get('fetched_at')}")
        return have, {"ok": False, "error": str(e)}


CAL19 = os.path.join(CACHE19, "calendar.json")


def merge_calendar(early, cal, start):
    """19 池日历 = 自有缓存里早于主日历首日的部分 + 主日历（主模块只取 2024 起，不能把 19 池裁短）。"""
    cal = list(cal or [])
    head = [d for d in (early or []) if d >= start and (not cal or d < cal[0])]
    return sorted(set(head + cal))


def calendar19(calendar=None, calendar_ok=None, log=None, start=None):
    """→ (dates, ok)。主流程传入的日历只用于“最新段”；HIST_START 起的早期日历由 data/cache19/calendar.json 独立保存，
    缺失时用 BaoStock 补取一次。单独运行（无传入）时自取全段，失败退回自有缓存 + 主模块缓存。"""
    log = log if log is not None else []
    start = start or p19.HIST_START
    own = (read_json(CAL19) or {}).get("dates") or []
    need_early = calendar and calendar[0] > start and not (own and own[0] <= start and own[-1] >= calendar[0])
    if calendar and not need_early:
        return merge_calendar(own, calendar, start), bool(calendar_ok)
    from . import quotes as qmod
    try:
        with qmod.BaoStock() as bs:
            end = calendar[0] if calendar else now_sh().date().isoformat()
            got = bs.trade_dates(start, end)
        if got:
            own = sorted(set(own) | set(got))
            write_json_atomic(CAL19, {"fetched_at": now_iso(), "source": "BaoStock query_trade_dates", "dates": own})
            if calendar:
                return merge_calendar(own, calendar, start), bool(calendar_ok)
            return [d for d in own if d >= start], True
    except Exception as e:  # noqa: BLE001
        log.append(f"19 池交易日历获取失败：{e}；沿用缓存")
    if calendar:
        log.append("19 池早期日历缺失，本次只覆盖主日历区间")
        return merge_calendar(own, calendar, start), bool(calendar_ok)
    cc = read_json(os.path.join(ROOT, "data", "cache", "calendar.json")) or {}
    return merge_calendar(own, cc.get("dates") or [], start), False


def update_composite(sess=None, calendar=None, calendar_ok=None, exp=None, log=None, start=None):
    """增量更新 19 池并原子写 web/data/composite.json。返回 stage 字典（ok=各源本次均成功）。
    任何异常由调用方捕获；产物校验失败时不覆盖旧 composite.json。"""
    log = log if log is not None else []
    sess = sess or session()
    today = now_sh().date().isoformat()
    start = start or p19.HIST_START
    seeded = init_cache_from_seed()
    standalone = calendar is None
    calendar, calendar_ok = calendar19(calendar, calendar_ok, log, start)
    if standalone and calendar_ok:
        from .build import expected_latest
        exp = expected_latest(calendar, now_sh())
    if not calendar:
        raise RuntimeError("无交易日历，19 池不计算，保留旧产物")
    upto = exp or calendar[-1]
    dates = [d for d in calendar if start <= d <= upto]
    codes = p19.CODES19
    sh = [c for c in codes if c[0] in "56"]
    sz = [c for c in codes if c[0] not in "56"]
    issues, shares, names = [], {c: {} for c in codes}, {}
    n0 = len(log)
    got, nm = shmod.fetch_sse(sess, dates, sh, CACHE19, log)
    names.update(nm)
    for d, m in got.items():
        for c, v in m.items():
            if c in shares:
                shares[c][d] = v
    sse_fail = [x for x in log[n0:] if x.startswith("上交所份额") and "失败" in x]
    got, nm, sz_issues = shmod.fetch_szse(sess, start, upto, sz, CACHE19, log, today)
    names.update(nm)
    cal = set(calendar)
    for d, m in got.items():
        for c, v in m.items():
            if c in shares and d in cal:
                shares[c][d] = v
    issues += sse_fail + sz_issues
    events, nav_fail = {}, []
    for c in codes:
        _, ev, st = navmod.fetch_nav(sess, c, start, today, CACHE19, log)
        events[c] = ev
        if not st.get("ok"):
            nav_fail.append(c)
    if nav_fail:
        issues.append("净值/折算信息本次抓取不完整（沿用缓存）：" + "、".join(nav_fail))
    bench, bench_fail = {}, []
    from . import quotes as qmod
    try:
        with qmod.BaoStock() as bs:
            for k in p19.PRICE_KEYS:
                bench[k], st = fetch_index(bs, k, start, today, CACHE19, log)
                if not st["ok"]:
                    bench_fail.append(k)
    except Exception as e:  # noqa: BLE001
        log.append(f"BaoStock 指数阶段失败：{e}；沿用缓存")
        for k in p19.PRICE_KEYS:
            if k not in bench:
                bench[k] = (read_json(os.path.join(CACHE19, "index", f"{k}.json")) or {}).get("closes") or {}
                bench_fail.append(k)
    if bench_fail:
        issues.append("价格行情本次抓取失败（沿用缓存）：" + "、".join(bench_fail))
    # 510300 收盘价：19 池自有 BaoStock 缓存（2022 起）；个别日缺时用主模块同源（BaoStock 不复权）行情缓存补，不用净值
    q510300 = {d: (b or {}).get("close") for d, b in ((read_json(os.path.join(MAIN_QUOTES, "510300.json")) or {}).get("bars") or {}).items()}
    q510300.update(bench.get("sh.510300") or {})

    splits = split_days(events)
    rows, meta = compute(dates, shares, codes, p19.BASE_DATE, splits)
    for r in rows:
        r["hs300"] = bench.get("sh.000300", {}).get(r["d"])
        r["sh"] = bench.get("sh.000001", {}).get(r["d"])
        r["etf510300"] = q510300.get(r["d"])
    stale = None if (exp is None or not calendar_ok) else (meta["data_last"] is None or meta["data_last"] < exp)
    flags = []
    if not calendar_ok:
        flags.append("交易日历本次获取失败：无法确认最新交易日，不判定“已到最新”")
    if stale:
        lag = [c for c, d in meta["members_last"].items() if d is None or d < exp]
        flags.append(f"19 只完整数据截至 {meta['data_last'] or '无'}，早于应有日期 {exp}" + (f"；落后成员：{'、'.join(lag)}" if lag else ""))
    if not meta["base_ok"]:
        flags.append(f"基期不可计算：{meta['base_error']}")
    flags += issues
    stage = {"ok": not issues, "at": now_iso(), "data_last": meta["data_last"], "expected_latest": exp,
             "stale": stale, "issues": issues[:30]}
    errs = validate(rows, codes, today)
    if errs:
        raise RuntimeError("19 池产物校验失败，保留旧产物：" + "；".join(errs[:5]))
    payload = {
        "generated_at": now_iso(), "pool_name": p19.POOL19_NAME,
        "members": [{**m, "market": "sh" if m["code"][0] in "56" else "sz", "exchange_name": names.get(m["code"], "")}
                    for m in p19.POOL19],
        "codes": codes, "definition": __doc__, "expected_latest": exp, "calendar_ok": calendar_ok, "stale": stale,
        "flags": flags, "stage": stage, "seed": seeded.get("provenance") if seeded.get("seeded") else None,
        "hist_start": start, "price_first": {k: (min(v) if v else None) for k, v in bench.items()},
        "benchmarks": p19.BENCHMARKS + [{"key": "etf510300", "label": "510300收盘价（不复权）", "unit": "元"}],
        **meta, "rows": rows,
    }
    write_json_atomic(OUT, payload)
    return stage


def validate(rows, codes, today):
    errs = []
    ds = [r["d"] for r in rows]
    if ds != sorted(ds) or len(ds) != len(set(ds)):
        errs.append("日期未严格升序")
    if ds and ds[-1] > today:
        errs.append(f"含未来日期 {ds[-1]}")
    if len(codes) != 19 or "588000" in codes:
        errs.append("成员不是固定 19 只")
    for r in rows:
        if len(r["q"]) != 19:
            errs.append(f"{r['d']} 成员列数 ≠19")
            break
    return errs
