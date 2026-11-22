"""审核第一轮（.dev-team/dong-etf-review-round1.md）H2/H3/M1 回归测试。全部用临时目录，不碰真实缓存。"""
import io
import json
import os
from datetime import datetime

import openpyxl
import pytest

from dxz import build as B
from dxz import quotes as Q
from dxz import reports as R
from dxz import shares as S
from dxz.common import SH_TZ
from dxz.series import build_rows, summarize


# ---------------------------------------------------------------- H2 深交所空/部分响应不覆盖缓存

def xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(("日期", "基金代码", "基金简称", "基金规模(份)"))
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


class XResp:
    status_code = 200

    def __init__(self, content):
        self.content = content


class XSess:
    def __init__(self, content):
        self.content = content

    def request(self, method, url, **kw):
        return XResp(self.content)


def seed_quarter(cache, shares):
    os.makedirs(os.path.join(cache, "szse"), exist_ok=True)
    with open(os.path.join(cache, "szse", "2026Q4.json"), "w") as f:
        json.dump({"key": "2026Q4", "lo": "2026-10-01", "hi": "2026-11-20", "codes": ["159915", "159919"],
                   "fetched_at": "2026-11-21T20:00:00+08:00", "shares": shares}, f)


OLD = {"2026-11-19": {"159915": 1.0, "159919": 2.0}, "2026-11-20": {"159915": 3.0, "159919": 4.0}}


@pytest.mark.parametrize("rows,expect_20", [
    ([], {"159915": 3.0, "159919": 4.0}),                                   # 成功 HTTP 但 0 行
    ([("2026-11-20", "159915", "x", "9.00")], {"159915": 9.0, "159919": 4.0}),  # 只有部分代码/日期
])
def test_szse_empty_or_partial_keeps_cached_values(tmp_path, rows, expect_20):
    cache = str(tmp_path)
    seed_quarter(cache, OLD)
    log = []
    out, _, issues = S.fetch_szse(XSess(xlsx(rows)), "2026-10-01", "2026-11-20", ["159915", "159919"],
                                  cache, log, "2026-11-22", pause=0)
    assert out["2026-11-19"] == {"159915": 1.0, "159919": 2.0}   # 旧有效值仍在
    assert out["2026-11-20"] == expect_20
    assert issues                                               # 沿用/缺失必须有记录
    saved = json.load(open(os.path.join(cache, "szse", "2026Q4.json")))["shares"]
    assert saved["2026-11-19"] == {"159915": 1.0, "159919": 2.0}  # 缓存没有被残缺批次覆盖


# ---------------------------------------------------------------- H2 报告缓存合并

GOOD = {"period_end": "2025-12-31", "status": "named_top10", "fetched_at": "2026-11-22T10:00", "url": "u"}
GOOD2 = {"period_end": "2026-06-30", "status": "no_top10_section", "fetched_at": "2026-11-22T10:00", "url": "u2"}


def test_reports_empty_discovery_keeps_cache():
    merged, issues = R.merge_reports([GOOD, GOOD2], [], discovered_ok=True, now="T")
    assert [m["period_end"] for m in merged] == ["2025-12-31", "2026-06-30"] and issues
    merged, issues = R.merge_reports([GOOD], [], discovered_ok=False, now="T")
    assert merged[0]["status"] == "named_top10" and issues


def test_reports_failed_extract_does_not_replace_valid_record():
    bad = {"period_end": "2025-12-31", "status": "download_or_extract_failed", "error": "timeout"}
    merged, issues = R.merge_reports([GOOD, GOOD2], [bad], discovered_ok=True, now="T")
    m = {x["period_end"]: x for x in merged}
    assert m["2025-12-31"]["status"] == "named_top10" and m["2025-12-31"]["reused_cache"]
    assert m["2025-12-31"]["last_error"] == "timeout"
    assert m["2026-06-30"]["missing_in_discovery"] == "T"       # 子集发现不丢旧报告期
    assert len(issues) == 2


def test_collect_reports_stage_not_ok_on_issues(tmp_path, monkeypatch):
    cache = str(tmp_path / "cache")
    os.makedirs(os.path.join(cache, "reports"))
    with open(os.path.join(cache, "reports", "510310.json"), "w") as f:
        json.dump([{**GOOD, "code": "510310"}], f)

    def boom(*a, **k):
        raise R.SourceError("HTTP 503")
    monkeypatch.setattr(R, "discover_sse", boom)
    reps, issues = R.collect(None, ["510310"], "2024-01-01", "2026-11-22", str(tmp_path / "raw"), cache, [])
    assert reps[0]["status"] == "named_top10" and issues["510310"]


# ---------------------------------------------------------------- H2 扫描版/身份/章节核验

FILL = "本基金为指数型基金，基金管理人严格遵守法律法规。" * 40


def fake_pdf(monkeypatch, pages):
    monkeypatch.setattr(R, "pdf_texts", lambda path: pages)


def test_scanned_pdf_is_unreadable_not_no_top10(monkeypatch):
    fake_pdf(monkeypatch, [""] * 60)
    ex = R.extract("x.pdf", {"period_end": "2026-06-30", "kind": "中期报告"})
    assert ex["status"] == "unreadable"


def test_no_top10_requires_identity_and_holder_section(monkeypatch):
    body = ["某基金2026年中期报告\n" + FILL] + [FILL] * 9
    fake_pdf(monkeypatch, body)
    ex = R.extract("x.pdf", {"period_end": "2026-06-30", "kind": "中期报告"})
    assert ex["status"] == "unverified"                      # 没有持有人章节 → 不能断言“未列示”
    toc = "8  基金份额持有人信息 ............................................ 68"
    fake_pdf(monkeypatch, [body[0] + "\n" + toc] + body[1:])
    assert R.extract("x.pdf", {"period_end": "2026-06-30", "kind": "中期报告"})["status"] == "unverified"  # 目录行不算章节
    sec = "8  基金份额持有人信息 \n8.1  期末基金份额持有人户数及持有人结构\n持有份额 1,000.00 60.00% 2,000.00 40.00%\n注：x"
    fake_pdf(monkeypatch, body[:5] + [sec + "\n" + FILL] + body[6:])
    assert R.extract("x.pdf", {"period_end": "2026-06-30", "kind": "中期报告"})["status"] == "no_top10_section"
    # 身份不符（首页是 2025 年报）
    fake_pdf(monkeypatch, ["某基金2025年年度报告\n" + FILL] + body[1:5] + [sec + "\n" + FILL] + body[6:])
    assert R.extract("x.pdf", {"period_end": "2026-06-30", "kind": "中期报告"})["status"] == "unverified"


# ---------------------------------------------------------------- H3 新鲜度

def test_expected_latest_is_threshold_and_calendar_failure_unknown():
    cal = ["2026-11-19", "2026-11-20"]
    shares = {"510300": {"2026-11-19": 1.0}, "159915": {}}
    navs = {"510300": {"2026-11-19": 1.0}, "159915": {}}
    bars = {"510300": {"2026-11-19": {}}, "159915": {}}
    exp = B.expected_latest(cal, datetime(2026, 11, 21, 9, tzinfo=SH_TZ))
    fr = B.freshness(["510300", "159915"], shares, navs, bars, exp, True, "2026-11-19",
                     {"510300": {"ok": False, "error": "x"}}, {"510300": {"ok": True}})
    m = fr["members"]
    assert m["510300"]["share_state"] == "stale" and m["159915"]["share_state"] == "no_data"
    assert fr["rank_stale"] and not fr["all_shares_fresh"]
    assert any("行情本次抓取失败" in f for f in fr["flags"]) and any("无份额数据" in f for f in fr["flags"])
    fr2 = B.freshness(["510300"], shares, navs, bars, None, False, "2026-11-19", {}, {})
    assert fr2["members"]["510300"]["share_state"] == "unknown" and not fr2["all_shares_fresh"]
    assert any("无法确认最新交易日" in f for f in fr2["flags"])


def test_nav_lag_flagged():
    fr = B.freshness(["510300"], {"510300": {"2026-11-20": 1.0}}, {"510300": {"2026-11-19": 1.0}},
                     {"510300": {"2026-11-20": {}}}, "2026-11-20", True, "2026-11-20", {}, {})
    assert fr["members"]["510300"]["nav_lag"] and any("净值落后" in f for f in fr["flags"])


def test_fetch_quotes_reports_failure(tmp_path):
    class Bad:
        def daily(self, *a):
            raise RuntimeError("socket timeout")
    bars, st = Q.fetch_quotes(Bad(), "510300", "2026-01-01", "2026-11-20", str(tmp_path), [])
    assert st["ok"] is False and "timeout" in st["error"]


# ---------------------------------------------------------------- M1 折算

def test_summary_history_position_only_after_last_split():
    cal = ["2024-09-18", "2024-09-19", "2024-09-20", "2024-09-23"]
    shares = {cal[0]: 100.0, cal[1]: 120.0, cal[2]: 60.0, cal[3]: 55.0}
    navs = {cal[0]: 1.6, cal[1]: 1.6, cal[2]: 3.2, cal[3]: 3.2}
    s = summarize(build_rows(cal, shares, navs, {}, {cal[2]: "每份基金份额折算0.5份"}))
    assert s["splits"] == [cal[2]] and s["comparable_from"] == cal[2]
    assert s["max"] == {"d": cal[2], "share": 60.0}          # 不拿折算前 120 当“历史最高”
    assert s["pct_rank"] == 0.5
