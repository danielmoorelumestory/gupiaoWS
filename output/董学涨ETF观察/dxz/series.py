"""纯计算：把份额/净值/行情对齐到交易日历，生成逐日行与派生指标。无网络、无 IO。

口径（全部写进输出 meta，前端照抄展示）：
- share：交易所披露场内份额（份）。nav：同日单位净值（元/份）。close：同日收盘价（元）。
- scale_nav = share × 同日 nav（元），主口径；nav 缺失时不算。
- scale_close = share × 同日 close（元），仅作“收盘价估算”备用口径，单独字段，不与 scale_nav 混用。
- d1：share_t − 前一交易日 share；前一交易日（按交易日历）无份额则为 null（不跨缺口）。
- net_sub_est = d1 × nav_t（元）：净申赎**近似**，不是现金净流量事实，更不等于任何机构买入。
- k 日变化：share_t − share_{t−k 个交易日}，两端任一缺失或区间内存在份额折算/拆分标记则为 null。
- 份额折算：净值源分红送配说明含“份额折算”或 份额比≈1/净值比（偏离<3% 且份额变动>30%）时标记 split，
  该日 d1/net_sub_est 置 null。
- amount_ratio20 = amount_t / 前 20 个交易日成交额均值，前 20 日任一缺失则 null。
"""
from __future__ import annotations

from bisect import bisect_left

KS = (1, 5, 20)


def detect_split(prev_share, share, prev_nav, nav, event: str | None) -> bool:
    if event and "份额折算" in event:  # 如“每份基金份额折算0.49977589份”；现金分红不是折算
        return True
    if not (prev_share and share and prev_nav and nav):
        return False
    rs = share / prev_share
    if abs(rs - 1) < 0.3:
        return False
    rn = nav / prev_nav
    return abs(rs * rn - 1) < 0.03


def build_rows(calendar, shares, navs, bars, events=None):
    """calendar: 升序交易日；shares/navs/bars: {date: ...}。只输出 [首个有份额日, 最后有份额或行情日]。"""
    events = events or {}
    cal = sorted(set(calendar))
    sd = sorted(d for d in shares if d in set(cal))
    if not sd:
        return []
    last = max([sd[-1]] + [d for d in bars if d in set(cal)])
    i0, i1 = bisect_left(cal, sd[0]), bisect_left(cal, last)
    days = cal[i0:i1 + 1]
    rows = []
    for i, d in enumerate(days):
        s, nv = shares.get(d), navs.get(d)
        b = bars.get(d) or {}
        row = {"d": d, "share": s, "nav": nv, "close": b.get("close"), "amount": b.get("amount"),
               "volume": b.get("volume"),
               "scale_nav": round(s * nv, 2) if s and nv else None,
               "scale_close": round(s * b["close"], 2) if s and b.get("close") else None,
               "d1": None, "net_sub_est": None, "split": False, "event": events.get(d)}
        if i > 0:
            ps, pn = shares.get(days[i - 1]), navs.get(days[i - 1])
            if s and ps:
                row["split"] = detect_split(ps, s, pn, nv, events.get(d))
                if not row["split"]:
                    row["d1"] = round(s - ps, 2)
                    if nv:
                        row["net_sub_est"] = round((s - ps) * nv, 2)
        rows.append(row)
    for i, row in enumerate(rows):
        for k in KS:
            key = f"chg{k}"
            row[key] = None
            if i - k < 0 or row["share"] is None or rows[i - k]["share"] is None:
                continue
            if any(rows[j]["split"] for j in range(i - k + 1, i + 1)):
                continue
            row[key] = round(row["share"] - rows[i - k]["share"], 2)
        row["amount_ratio20"] = None
        if row["amount"] is not None and i >= 20:
            prev = [rows[j]["amount"] for j in range(i - 20, i)]
            if all(a is not None for a in prev) and sum(prev) > 0:
                row["amount_ratio20"] = round(row["amount"] / (sum(prev) / 20), 4)
    return rows


def summarize(rows):
    """全样本摘要：覆盖、缺日、最新、历史位置。

    份额折算会改变份额单位（M1）：最高/分位只在“最后一次折算日（含）之后”的可比区间内计算，
    并给出 comparable_from；跨折算的“首末份额差”不提供。原始逐日份额仍原样保留在 rows。
    """
    have = [r for r in rows if r["share"] is not None]
    if not have:
        return {"count": 0}
    latest = have[-1]
    splits = [r["d"] for r in rows if r["split"]]
    comp_from = splits[-1] if splits else have[0]["d"]
    comp = [r for r in have if r["d"] >= comp_from]
    vals = [r["share"] for r in comp]
    mx = max(comp, key=lambda r: r["share"])
    pct = sum(1 for v in vals if v <= latest["share"]) / len(vals)
    missing = [r["d"] for r in rows if r["share"] is None and r["d"] <= latest["d"]]
    return {
        "first": have[0]["d"], "last": latest["d"], "count": len(have),
        "trading_days": len([r for r in rows if r["d"] <= latest["d"]]),
        "missing_days": missing,
        "latest": {k: latest.get(k) for k in ("d", "share", "nav", "scale_nav", "scale_close",
                                              "d1", "net_sub_est", "chg1", "chg5", "chg20")},
        "comparable_from": comp_from,
        "comparable_count": len(comp),
        "max": {"d": mx["d"], "share": mx["share"]},
        "pct_rank": round(pct, 4),
        "splits": splits,
    }
