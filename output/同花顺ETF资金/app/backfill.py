"""历史回补：沪市用 STAT_DATE 逐交易日；深市历史用 akshare(一次性,约6个月,best-effort)。

依赖 akshare 时需先 `pip install akshare`。无 akshare 则仅回补沪市，深市从每日采集起向前累积。
"""
import logging

from compute import aggregate_flow, compute_daily_flow
import fetch
import store

log = logging.getLogger("backfill")


def _trading_days(conn, start: str, end: str) -> list[str]:
    """用上证指数日历作交易日序列。"""
    idx = fetch.fetch_sse_index(start, end)
    return [r["date"] for r in idx]


def backfill(conn, start: str, end: str) -> None:
    """按交易日回补沪市份额并计算每日 agg/index。深市历史需 akshare，见模块说明。"""
    days = _trading_days(conn, start, end)
    idx_map = {r["date"]: r["close"] for r in fetch.fetch_sse_index(start, end)}
    try:
        import akshare  # noqa: F401
        has_ak = True
    except ImportError:
        has_ak = False
        log.warning("akshare 未安装，仅回补沪市份额，深市历史缺口")

    prev_shares: dict[str, float] = {}
    for i, day in enumerate(days):
        shares = fetch.fetch_sse_shares(day)
        if has_ak:
            try:
                shares.update(_szse_shares_on(day))
            except Exception as e:  # noqa: BLE001
                log.warning("深市 %s 回补失败: %s", day, e)
        store.save_shares(conn, day, shares)
        if prev_shares:
            navs = fetch.fetch_navs(shares.keys(), day)
            flows = compute_daily_flow(shares, prev_shares, navs)
            all_f, broad_f = aggregate_flow(flows)
            store.save_agg(conn, day, all_f, broad_f)
        if day in idx_map:
            store.save_index(conn, day, idx_map[day])
        prev_shares = shares
        log.info("回补 %s (%d/%d)", day, i + 1, len(days))


def _szse_shares_on(day: str) -> dict[str, float]:
    """深市指定日份额（akshare fund_scale_daily_szse），单位转份。"""
    import akshare as ak
    df = ak.fund_scale_daily_szse(date=day.replace("-", ""))
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        code = str(row.get("基金代码") or row.get("证券代码") or "").zfill(6)
        wan = row.get("当前规模") or row.get("基金份额")
        if code and wan is not None:
            try:
                out[code] = float(wan) * 10000
            except (TypeError, ValueError):
                pass
    return out
