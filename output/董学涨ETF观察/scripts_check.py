"""验收对账脚本：份额对协调者实测值、原始 PDF 页码对账、覆盖统计。只读 web/data 与 data/raw。

    .venv/bin/python -I scripts_check.py
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from dxz import reports as R  # noqa: E402

EXPECT = {  # 协调者 2026-11-22 用 auto_daily.collect_daily 匿名实测（份）
    ("510050", "2026-11-19"): 16660566800, ("510050", "2026-11-20"): 24134166800,
    ("510300", "2026-11-19"): 51540787700, ("510300", "2026-11-20"): 55184887700,
    ("159915", "2026-11-19"): 49907454936, ("159915", "2026-11-20"): 53174454936,
    ("588000", "2026-11-19"): 102434668200, ("588000", "2026-11-20"): 103628668200,
}
NAV20 = {"510050": 2.9042, "510300": 4.0286, "159915": 2.2269, "588000": 1.3024}

etf = json.load(open(os.path.join(ROOT, "web/data/etf.json"), encoding="utf-8"))
ok = True
print("== 份额对账（份）")
for (c, d), v in EXPECT.items():
    row = next((r for r in etf["etfs"][c]["rows"] if r["d"] == d), None)
    got = row and row["share"]
    match = got == v
    ok &= match
    print(f"{c} {d} 期望 {v:,} 实得 {got:,.0f} {'OK' if match else 'MISMATCH'}" if got else f"{c} {d} 缺")
for c, n in NAV20.items():
    row = next(r for r in etf["etfs"][c]["rows"] if r["d"] == "2026-11-20")
    print(f"{c} 2026-11-20 NAV 期望 {n} 实得 {row['nav']} {'OK' if row['nav'] == n else 'MISMATCH'}；"
          f"Δ份额 {row['d1']:,.0f} 份 × NAV = 净申赎近似 {row['net_sub_est'] / 1e8:.2f} 亿元")
    ok &= row["nav"] == n
print("== 覆盖")
for c, e in etf["etfs"].items():
    s = e["summary"]
    print(f"{c} {e['exchange_name']:<12} 首日 {s.get('first')} 末日 {s.get('last')} 有效 {s.get('count')} / 交易日 {s.get('trading_days')} 缺 {len(s.get('missing_days') or [])} 陈旧 {e['stale']}")

print("== 原始 PDF 页码对账")
CASES = [("510310", "510310_20250830_*.pdf", 1, ("中央汇金资产管理有限责任公司", 28538696695.0, 41.80, 56)),
         ("510310", "510310_20250830_*.pdf", 2, ("中央汇金投资有限责任公司", 27355388757.0, 40.07, 56)),
         ("510310", "510310_20260331_*.pdf", 1, ("中央汇金资产管理有限责任公司", 28538696695.0, 43.34, 75)),
         # 159915 2025 年报（深交所 2026-03-31），第 64 页已渲染成图片人工目视核对
         ("159915", "33722948-c0d2-4271-82b3-1f2f6921a3a2.PDF", 1, ("中央汇金投资有限责任公司", 11362962941.0, 36.07, 64)),
         ("159915", "33722948-c0d2-4271-82b3-1f2f6921a3a2.PDF", 2, ("中央汇金资产管理有限责任公司", 5656821265.0, 17.96, 64))]
NO_TOP10_2026 = [("510310", "510310_20260831_*.pdf")]
for code, pat, rank, exp in CASES:
    f = glob.glob(os.path.join(ROOT, "data/raw/reports", code, pat))[0]
    ex = R.extract(f)
    r = ex["top10"]["rows"][rank - 1]
    got = (r["name"], r["shares"], r["pct"], r["page"])
    ok &= got == exp
    print(os.path.basename(f), f"第{rank}名", got, "OK" if got == exp else f"MISMATCH 期望 {exp}")
for code, pat in NO_TOP10_2026:
    f = glob.glob(os.path.join(ROOT, "data/raw/reports", code, pat))[0]
    ex = R.extract(f)
    good = ex["status"] == "no_top10_section" and ex["huijin_mentions"] == 0
    ok &= good
    print(os.path.basename(f), "2026 中报：", ex["status"], "全文“中央汇金”出现次数", ex["huijin_mentions"], "OK" if good else "MISMATCH")
hold = json.load(open(os.path.join(ROOT, "web/data/holdings.json"), encoding="utf-8"))
print("== 报告状态", {s: sum(1 for r in hold["reports"] if r.get("status") == s) for s in
                    {r.get("status") for r in hold["reports"]}})
print("== 管理人核验", {c: (m["ok"], m["found"]) for c, m in (hold.get("managers") or {}).items()})
ok &= all(m["ok"] for m in (hold.get("managers") or {}).values())

print("== 审核第一轮 H1：588000 无汇金入榜不得显示 0")
for pt in hold["series"]["588000"]:
    if pt["status"] == "named_top10":
        good = pt["narrow_identified"] is False and pt["narrow_own_lb"] is None and pt["narrow_with_products_lb"] is None
        ok &= good
        print(pt["period_end"], "narrow_identified", pt["narrow_identified"], "narrow_own_lb", pt["narrow_own_lb"], "OK" if good else "BAD")
print("== H1：机构上限口径（510310）")
for pt in hold["series"]["510310"]:
    print(pt["period_end"], "机构", pt.get("inst_shares"), "上限", pt.get("inst_upper"), pt.get("inst_upper_basis"))
print("== H3：新鲜度")
fr = etf["freshness"]
print("calendar_ok", fr["calendar_ok"], "all_shares_fresh", fr["all_shares_fresh"], "rank_stale", fr["rank_stale"],
      "expected_latest", etf["expected_latest"], "rank_day", etf["rank_day"])
print("flags", fr["flags"] or "无")
print("== M1：折算后可比区间")
for c, e in etf["etfs"].items():
    s = e["summary"]
    if s.get("comparable_from") != s.get("first"):
        print(c, "折算日", s["splits"], "可比自", s["comparable_from"], "最高", s["max"], "分位", s["pct_rank"])
sys.exit(0 if ok else 1)
