"""BaoStock 免费公开日线（不复权）与交易日历。盘后数据，非实时。

- query_history_k_data_plus(frequency="d", adjustflag="3")：close 元、volume 份、amount 元。
  amount 是成交额（买卖双方成交金额），不是资金净流入。
- query_trade_dates：交易日历，用于判断“前一交易日”与缺日。
参考 output/同花顺ETF资金/app/auto_history.py 的 BaoStock 会话用法（login/logout 在 finally）。
缓存：data/cache/quotes/<code>.json，增量从最新日前 10 天重取。
"""
from __future__ import annotations

import os
import socket
from datetime import date as _date, timedelta

from .common import SourceError, norm_date, now_iso, num, read_json, write_json_atomic


def bs_code(code: str) -> str:
    return ("sh." if code[0] in "56" else "sz.") + code


class BaoStock:
    def __init__(self, timeout=30):
        self.timeout = timeout

    def __enter__(self):
        import baostock as bs
        self.bs = bs
        self._old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout)
        lg = bs.login()
        if str(lg.error_code) != "0":
            socket.setdefaulttimeout(self._old)
            raise SourceError(f"BaoStock 登录失败：{lg.error_msg}")
        return self

    def __exit__(self, *a):
        try:
            self.bs.logout()
        finally:
            socket.setdefaulttimeout(self._old)

    def _rows(self, rs):
        if str(rs.error_code) != "0":
            raise SourceError(f"BaoStock 查询失败：{rs.error_msg}")
        out = []
        while rs.next():
            out.append(dict(zip(rs.fields, rs.get_row_data())))
        return out

    def trade_dates(self, start, end):
        rows = self._rows(self.bs.query_trade_dates(start_date=start, end_date=end))
        return sorted(r["calendar_date"] for r in rows if r.get("is_trading_day") == "1")

    def daily(self, code, start, end):
        return self._rows(self.bs.query_history_k_data_plus(
            bs_code(code), "date,code,close,volume,amount,adjustflag,tradestatus",
            start_date=start, end_date=end, frequency="d", adjustflag="3"))


def parse_daily(rows, code):
    """→ ({date:{close,volume,amount}}, errors)。停牌/非正收盘价/代码不符拒绝。"""
    out, errs = {}, []
    want = bs_code(code)
    for r in rows:
        d = norm_date(r.get("date"))
        if d is None or r.get("code") != want:
            errs.append(f"行情 {code} 行代码/日期异常 {r.get('code')} {r.get('date')}")
            continue
        if r.get("adjustflag") not in (None, "3"):
            errs.append(f"行情 {code} {d} 复权标记非 3，拒绝")
            continue
        if r.get("tradestatus") == "0":
            continue  # 停牌日
        close, vol, amt = num(r.get("close")), num(r.get("volume")), num(r.get("amount"))
        if close is None or close <= 0 or amt is None or amt < 0:
            errs.append(f"行情 {code} {d} 收盘价/成交额无效，拒绝")
            continue
        out[d] = {"close": close, "volume": vol, "amount": amt}
    return out, errs


def fetch_quotes(client, code, start, end, cache_dir, log):
    """返回 (bars, status)。status={ok, fetched_at, error, latest}；失败时 ok=False 并沿用缓存（H3）。"""
    p = os.path.join(cache_dir, "quotes", f"{code}.json")
    c = read_json(p) or {}
    have = dict(c.get("bars") or {})
    lo = start
    if have and min(have) <= (_date.fromisoformat(start) + timedelta(days=10)).isoformat():
        lo = max(start, (_date.fromisoformat(max(have)) - timedelta(days=10)).isoformat())
    try:
        got, errs = parse_daily(client.daily(code, lo, end), code)
        log.extend(errs)
        have.update(got)
        at = now_iso()
        write_json_atomic(p, {"code": code, "fetched_at": at, "bars": dict(sorted(have.items()))})
        return have, {"ok": True, "fetched_at": at, "error": None, "latest": max(have) if have else None}
    except Exception as e:  # noqa: BLE001
        log.append(f"行情 {code} 获取失败：{e}；沿用缓存 {c.get('fetched_at')}")
        return have, {"ok": False, "fetched_at": c.get("fetched_at"), "error": str(e),
                      "latest": max(have) if have else None}
