"""一键更新：采集 → 校验 → 原子写 web/data/*.json。各阶段失败沿用缓存并在 status 中披露。"""
from __future__ import annotations

import os
import re
import traceback
from datetime import date as _date, timedelta

from . import nav as navmod
from . import pool as poolmod
from . import quotes as qmod
from . import reports as repmod
from . import series as sermod
from . import shares as shmod
from .common import now_iso, now_sh, read_json, session, write_json_atomic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "web", "data")
DEFAULT_START = "2024-01-02"

SOURCES = [
    {"key": "sse_shares", "label": "上交所 ETF 规模（场内份额，日频，官方）", "url": shmod.SSE_PAGE_URL,
     "method": "commonQuery.do sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L 按 STAT_DATE 单日查询；TOT_VOL 万份×10000=份"},
    {"key": "szse_shares", "label": "深交所基金规模（场内份额，日频，官方）", "url": shmod.SZSE_PAGE_URL,
     "method": "ShowReport CATALOGID=scsj_fund_jjgm 按季度区间导出 XLSX；表头“基金规模(份)”"},
    {"key": "nav", "label": "东方财富基金历史净值（公开）", "url": "https://fundf10.eastmoney.com/",
     "method": "api.fund.eastmoney.com/f10/lsjz 按实际页大小翻页，只取 FSRQ 精确日 DWJZ（元/份）"},
    {"key": "quotes", "label": "BaoStock 日线（公开，盘后，不复权）", "url": "http://www.baostock.com",
     "method": "query_history_k_data_plus frequency=d adjustflag=3：close 元、amount 元（成交额≠净流入）"},
    {"key": "reports", "label": "交易所基金定期报告原文 PDF", "url": "https://www.sse.com.cn/disclosure/fund/announcement/",
     "method": "上交所 COMMON_SSE_PL_JJXX_ETFGG_L / 深交所 annList fundinfoNotice_disc 自动发现年报与中报，下载原文后确定性规则抽取"},
]


def expected_latest(calendar, now=None, check_hour=18):
    """检查阈值：北京时间 check_hour 点前不把当日列为“应已有份额”的日期。

    这只是本工具判断陈旧的阈值，不是上游“18:00 后必有终值”的发布承诺；晚于阈值仍未发布时，
    页面显示为“尚未取到”，而不是断言数据源出错。
    """
    now = now or now_sh()
    today = now.date().isoformat()
    past = [d for d in calendar if d <= today]
    if not past:
        return None
    if past[-1] == today and now.hour < check_hour:
        return past[-2] if len(past) > 1 else None
    return past[-1]


def freshness(codes, shares, navs, bars, exp, calendar_ok, rank_day, quote_status, nav_status):
    """按 源×成员 报告真实最新日期与抓取状态，并汇总显著标记（H3）。"""
    members, flags = {}, []
    for c in codes:
        sl = max(shares[c]) if shares[c] else None
        nl = max(navs[c]) if navs[c] else None
        ql = max(bars[c]) if bars.get(c) else None
        m = {"share_last": sl, "nav_last": nl, "quote_last": ql,
             "quotes_ok": (quote_status.get(c) or {}).get("ok"),
             "quotes_error": (quote_status.get(c) or {}).get("error"),
             "nav_ok": (nav_status.get(c) or {}).get("ok")}
        if sl is None:
            m["share_state"] = "no_data"
        elif exp is None:
            m["share_state"] = "unknown"
        else:
            m["share_state"] = "fresh" if sl >= exp else "stale"
        m["nav_lag"] = bool(sl and (nl is None or nl < sl))
        m["quote_lag"] = bool(exp and (ql is None or ql < exp))
        members[c] = m
    def lst(key, val=True):
        return [c for c, m in members.items() if m.get(key) == val]
    if not calendar_ok:
        flags.append("交易日历本次获取失败，沿用缓存日历：无法确认最新交易日，不判定“已到最新”")
    for c in lst("share_state", "no_data"):
        flags.append(f"{c} 无份额数据")
    st = lst("share_state", "stale")
    if st:
        flags.append("份额陈旧：" + "、".join(f"{c}(至{members[c]['share_last']})" for c in st))
    nv = lst("nav_lag")
    if nv:
        flags.append("净值落后于份额（规模/净申赎缺）：" + "、".join(f"{c}(至{members[c]['nav_last']})" for c in nv))
    ql = lst("quote_lag")
    if ql:
        flags.append("行情落后：" + "、".join(f"{c}(至{members[c]['quote_last']})" for c in ql))
    bad_q = lst("quotes_ok", False)
    if bad_q:
        flags.append("行情本次抓取失败、沿用缓存：" + "、".join(bad_q))
    bad_n = lst("nav_ok", False)
    if bad_n:
        flags.append("净值本次抓取不完整、沿用缓存：" + "、".join(bad_n))
    rank_stale = bool(exp and (rank_day is None or rank_day < exp))
    if rank_stale:
        flags.append(f"成交排名日 {rank_day or '无'} 早于应有日期 {exp}")
    all_fresh = calendar_ok and all(m["share_state"] == "fresh" for m in members.values())
    return {"members": members, "flags": flags, "rank_stale": rank_stale, "calendar_ok": calendar_ok,
            "all_shares_fresh": all_fresh}


def validate_etf_payload(payload, today):
    errs = []
    for code, e in payload["etfs"].items():
        ds = [r["d"] for r in e["rows"]]
        if ds != sorted(ds) or len(ds) != len(set(ds)):
            errs.append(f"{code} 日期未严格升序")
        if ds and ds[-1] > today:
            errs.append(f"{code} 含未来日期 {ds[-1]}")
        for r in e["rows"]:
            if r["share"] is not None and not r["share"] > 0:
                errs.append(f"{code} {r['d']} 份额非正")
                break
    return errs


def update(start=DEFAULT_START, with_reports=True, log_print=print):
    log, stages = [], {}
    now = now_sh()
    today = now.date().isoformat()
    codes = poolmod.CODES
    sess = session()

    # 1 交易日历 + 行情
    calendar, bars, qstat = [], {}, {}
    cal_cache = os.path.join(CACHE, "calendar.json")
    calendar_ok = False
    try:
        with qmod.BaoStock() as bs:
            calendar = bs.trade_dates(start, today)
            calendar_ok = bool(calendar)
            write_json_atomic(cal_cache, {"fetched_at": now_iso(), "dates": calendar})
            for c in codes:
                bars[c], qstat[c] = qmod.fetch_quotes(bs, c, start, today, CACHE, log)
    except Exception as e:  # noqa: BLE001
        log.append(f"BaoStock 阶段失败：{e}；沿用缓存")
        if not calendar_ok:
            cc = read_json(cal_cache) or {}
            calendar = cc.get("dates") or []
            log.append(f"交易日历沿用 {cc.get('fetched_at')} 缓存（截至 {calendar[-1] if calendar else '无'}）")
        for c in codes:
            if c not in bars:
                cq = read_json(os.path.join(CACHE, "quotes", f"{c}.json")) or {}
                bars[c] = cq.get("bars") or {}
                qstat[c] = {"ok": False, "fetched_at": cq.get("fetched_at"), "error": str(e),
                            "latest": max(bars[c]) if bars[c] else None}
    q_ok = all((qstat.get(c) or {}).get("ok") for c in codes)
    stages["quotes"] = {"ok": q_ok, "at": now_iso(),
                        "failed": [c for c in codes if not (qstat.get(c) or {}).get("ok")]}
    stages["calendar"] = {"ok": calendar_ok, "last": calendar[-1] if calendar else None}
    if not calendar:
        raise RuntimeError("无交易日历（BaoStock 失败且无缓存），中止，保留旧产物")
    log_print(f"交易日 {len(calendar)} 个：{calendar[0]}~{calendar[-1]}")
    # 日历失败时不能拿缓存日历尾日当“应有最新日”
    exp = expected_latest(calendar, now) if calendar_ok else None
    fetch_upto = exp or calendar[-1]
    fetch_dates = [d for d in calendar if d <= fetch_upto]

    # 2 份额
    sh = [c for c in codes if poolmod.market(c) == "sh"]
    sz = [c for c in codes if poolmod.market(c) == "sz"]
    shares, names = {c: {} for c in codes}, {}
    n0 = len(log)
    share_issues = []
    try:
        got, nm = shmod.fetch_sse(sess, fetch_dates, sh, CACHE, log)
        names.update(nm)
        for d, m in got.items():
            for c, v in m.items():
                if c in shares:
                    shares[c][d] = v
        got, nm, share_issues = shmod.fetch_szse(sess, start, fetch_upto, sz, CACHE, log, today)
        names.update(nm)
        cal = set(calendar)
        for d, m in got.items():
            for c, v in m.items():
                if c in shares and d in cal:
                    shares[c][d] = v
        sse_fail = [x for x in log[n0:] if x.startswith("上交所份额") and "失败" in x]
        stages["shares"] = {"ok": not sse_fail and not share_issues, "at": now_iso(),
                            "issues": (sse_fail + share_issues)[:50]}
    except Exception as e:  # noqa: BLE001
        log.append(f"份额阶段异常：{e}")
        stages["shares"] = {"ok": False, "error": str(e)}
    log_print("份额完成")

    # 3 净值
    navs, events, nstat = {}, {}, {}
    for c in codes:
        navs[c], events[c], nstat[c] = navmod.fetch_nav(sess, c, start, today, CACHE, log)
    stages["nav"] = {"ok": all(nstat[c]["ok"] for c in codes), "at": now_iso(),
                     "failed": [c for c in codes if not nstat[c]["ok"]]}
    log_print("净值完成")

    # 4 组装
    etfs = {}
    for p in poolmod.POOL:
        c = p["code"]
        evs = {d: re.sub(r"\s*折算比例\S+$", "", v) for d, v in events[c].items()}  # 兼容旧缓存格式
        rows = sermod.build_rows(calendar, shares[c], navs[c], bars.get(c) or {}, evs)
        summ = sermod.summarize(rows)
        nm = names.get(c, "")
        name_ok = bool(nm) and p["expect"] in nm
        if nm and not name_ok:
            log.append(f"名称核验：{c} 交易所简称“{nm}”不含“{p['expect']}”")
        if summ.get("count", 0) == 0:
            log.append(f"{c} 无任何份额数据（未上市/接口不含该代码）")
        etfs[c] = {**p, "exchange_name": nm, "name_check": name_ok, "summary": summ, "rows": rows}
    rank_day = None
    for d in reversed(calendar):
        if d <= today and all((bars.get(c) or {}).get(d) for c in codes):
            rank_day = d
            break
    fr = freshness(codes, shares, navs, bars, exp, calendar_ok, rank_day, qstat, nstat)
    for c in codes:
        st = fr["members"][c]["share_state"]
        # 无数据/陈旧 → stale=True；日历无法确认 → stale=None（未知），页面不得写“已到最新”
        etfs[c]["stale"] = None if st == "unknown" else st != "fresh"
        etfs[c]["freshness"] = fr["members"][c]
    ranking = []
    for c in codes:
        r = next((x for x in etfs[c]["rows"] if x["d"] == rank_day), None) if rank_day else None
        ranking.append({"code": c, "name": etfs[c]["name"], "d": rank_day,
                        "amount": r and r["amount"], "amount_ratio20": r and r["amount_ratio20"],
                        "share": r and r["share"], "chg1": r and r["chg1"], "chg5": r and r["chg5"],
                        "chg20": r and r["chg20"], "net_sub_est": r and r["net_sub_est"],
                        "pct_rank": etfs[c]["summary"].get("pct_rank"),
                        "pct_rank_from": etfs[c]["summary"].get("comparable_from")})
    ranking.sort(key=lambda x: -(x["amount"] or -1))

    payload = {"generated_at": now_iso(), "pool_name": poolmod.POOL_NAME, "start": start,
               "expected_latest": exp, "calendar_last": calendar[-1], "rank_day": rank_day,
               "freshness": fr, "ranking": ranking,
               "etfs": etfs, "sources": SOURCES[:4], "stages": stages,
               "notes": sermod.__doc__}
    errs = validate_etf_payload(payload, today)
    if errs:
        log.extend(errs)
        raise RuntimeError("份额产物校验失败，保留旧产物：" + "；".join(errs[:5]))
    write_json_atomic(os.path.join(OUT, "etf.json"), payload)
    log_print("etf.json 已写入")

    # 4b 视频 19 只 ETF 观察池（独立池、独立缓存 data/cache19；失败不影响 12 只池产物，旧 composite.json 保留）
    stages["composite"] = run_composite(sess, calendar, calendar_ok, exp, log)
    log_print(f"19 池：{'完成' if stages['composite'].get('ok') else '有问题'}，数据截至 {stages['composite'].get('data_last')}")

    # 5 报告
    if with_reports:
        try:
            reps, issues = repmod.collect(sess, codes, "2024-01-01", today, RAW, CACHE, log)
            if reps:
                write_json_atomic(os.path.join(OUT, "holdings.json"), build_holdings(reps, issues))
            stages["reports"] = {"ok": bool(reps) and not issues, "at": now_iso(), "count": len(reps),
                                 "issues": issues}
        except Exception as e:  # noqa: BLE001
            log.append(f"报告阶段失败：{e}\n{traceback.format_exc()}")
            stages["reports"] = {"ok": False, "error": str(e)}
    else:  # --no-reports：沿用上次报告阶段状态（报告由单独任务维护），不丢失其失败/问题信息
        prev = (read_json(os.path.join(OUT, "status.json")) or {}).get("stages") or {}
        if prev.get("reports"):
            stages["reports"] = dict(prev["reports"], carried=True)
    write_json_atomic(os.path.join(OUT, "status.json"),
                      # generated_at = 本次份额/行情产物生成时间；updated_at = 任一产物（含仅报告）最近写入时间，
                      # 页面用 updated_at 判断“有新数据”
                      {"generated_at": payload["generated_at"], "updated_at": now_iso(), "expected_latest": exp,
                       "stages": stages,
                       "flags": fr["flags"], "log": log[-400:], "log_total": len(log)})
    return payload, log


def run_composite(sess=None, calendar=None, calendar_ok=None, exp=None, log=None):
    """19 池阶段：异常转为 stage.ok=False（附错误），绝不抛出影响主流程。"""
    from . import composite as compmod
    log = log if log is not None else []
    try:
        return compmod.update_composite(sess, calendar, calendar_ok, exp, log)
    except Exception as e:  # noqa: BLE001
        log.append(f"19 池阶段失败：{e}\n{traceback.format_exc()}")
        prev = read_json(compmod.OUT) or {}
        return {"ok": False, "at": now_iso(), "error": str(e), "data_last": prev.get("data_last"),
                "expected_latest": exp, "issues": [f"本次失败，页面显示旧产物（数据截至 {prev.get('data_last') or '无'}）"]}


def update_composite_only(log_print=print):
    """run.py composite：只更新 19 池，并把阶段结果并入 status.json（页面据此显示失败/陈旧）。"""
    log = []
    stage = run_composite(log=log)
    st = read_json(os.path.join(OUT, "status.json")) or {}
    st.setdefault("stages", {})["composite"] = stage
    st["updated_at"] = now_iso()
    write_json_atomic(os.path.join(OUT, "status.json"), st)
    return stage, log


def update_reports(log_print=print):
    log = []
    reps, issues = repmod.collect(session(), poolmod.CODES, "2024-01-01", now_sh().date().isoformat(),
                                  RAW, CACHE, log)
    if reps:
        write_json_atomic(os.path.join(OUT, "holdings.json"), build_holdings(reps, issues))
    st = read_json(os.path.join(OUT, "status.json")) or {}
    st["updated_at"] = now_iso()  # 只更新报告也要让页面看到“有新数据”；generated_at 仍是行情产物时间
    st.setdefault("stages", {})["reports"] = {"ok": bool(reps) and not issues, "at": now_iso(),
                                              "count": len(reps), "issues": issues}
    write_json_atomic(os.path.join(OUT, "status.json"), st)
    write_json_atomic(os.path.join(CACHE, "reports_log.json"), {"at": now_iso(), "log": log})
    return reps, log


def build_holdings(reps, issues=None):
    """按代码分组；附汇金实体跨期对比（H1 数据契约见 reports.holder_summary）。

    每期点位：
    - narrow_identified / narrow_own_lb / narrow_with_products_lb / products：只在 named_top10 时有值；
      未识别时 narrow_own_lb=None（未知，≠0）。
    - inst_shares（原文机构合计）与 inst_upper（上限线索）及其 inst_upper_basis；不满足扣除条件时
      inst_upper = 完整机构合计。
    另给每只基金 latest_named（最近一期已验收具名报告）与全局 coverage，供页面动态展示（M2）。
    """
    by = {}
    for r in reps:
        by.setdefault(r["code"], []).append(r)
    series, latest_named = {}, {}
    for code, rs in by.items():
        rs.sort(key=lambda x: x["period_end"])
        pts = []
        for r in rs:
            s = r.get("summary")
            pt = {"period_end": r["period_end"], "kind": r["kind"], "announce_date": r["announce_date"],
                  "status": r.get("status"), "status_reason": r.get("status_reason"), "url": r["url"],
                  "reused_cache": bool(r.get("reused_cache")), "last_error": r.get("last_error")}
            if r.get("status") == "named_top10" and s:
                for k in ("narrow_identified", "narrow_labels", "narrow_own_lb", "products", "products_lb",
                          "narrow_with_products_lb", "broad_lb", "entities", "scope_note"):
                    pt[k] = s.get(k)
            st = r.get("structure") or {}
            if st.get("valid"):
                pt["inst_shares"] = st["inst_shares"]
                pt["total_shares"] = st["total_shares"]
                pt["inst_upper"] = st.get("inst_upper", st["inst_shares"])
                pt["inst_upper_basis"] = st.get("inst_upper_basis") or "完整机构合计"
            pts.append(pt)
        series[code] = pts
        named = [p for p in pts if p["status"] == "named_top10"]
        latest_named[code] = named[-1]["period_end"] if named else None
    managers = {}
    for p in poolmod.POOL:
        ms = sorted({r.get("manager") for r in by.get(p["code"], []) if r.get("manager")})
        managers[p["code"]] = {"expected": p["manager"], "found": ms,
                               "ok": bool(ms) and all(m.startswith(p["manager"]) for m in ms)}
    from collections import Counter
    cov = {"status_counts": dict(Counter(r.get("status") for r in reps)),
           "latest_named_min": min((v for v in latest_named.values() if v), default=None),
           "latest_named_max": max((v for v in latest_named.values() if v), default=None),
           "funds_without_named": [c for c, v in latest_named.items() if not v],
           "periods": {}}
    for r in reps:
        cov["periods"].setdefault(r["period_end"], Counter())[r.get("status")] += 1
    cov["periods"] = {k: dict(v) for k, v in sorted(cov["periods"].items())}
    return {"generated_at": now_iso(), "reports": reps, "series": series, "managers": managers,
            "latest_named": latest_named, "coverage": cov, "issues": issues or {},
            "sources": [SOURCES[4]], "rules": repmod.__doc__}
