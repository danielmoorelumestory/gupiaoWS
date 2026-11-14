"""匿名采数：沪/深份额、东财 NAV、上证指数。只做网络调用，解析交给 parse.*。"""
from collections.abc import Iterable

import requests

from parse import parse_nav, parse_sse_shares, parse_szse_shares

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120 Safari/537.36")
_TIMEOUT = 30


def _session(referer: str, ajax: bool = False) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Referer": referer})
    if ajax:
        s.headers["X-Requested-With"] = "XMLHttpRequest"
    return s


def fetch_sse_shares(date: str) -> dict[str, float]:
    """上交所指定日全量 ETF 份额 → {code: 份}。date='YYYY-MM-DD'。"""
    s = _session("http://www.sse.com.cn/")
    r = s.get("http://query.sse.com.cn/commonQuery.do", params={
        "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L", "isPagination": "true",
        "STAT_DATE": date, "pageHelp.pageSize": "10000", "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1", "pageHelp.cacheSize": "1", "pageHelp.endPage": "1",
    }, timeout=_TIMEOUT)
    return parse_sse_shares(r.json())


def fetch_szse_shares(date: str) -> dict[str, float]:
    """深交所最新 ETF 份额 → {code: 份}。接口仅给最新日，date 仅作占位（历史由 akshare 回补）。"""
    s = _session("https://www.szse.cn/market/product/fund/list/index.html", ajax=True)
    out: dict[str, float] = {}
    pg = 1
    while True:
        r = s.get("https://www.szse.cn/api/report/ShowReport/data", params={
            "SHOWTYPE": "JSON", "CATALOGID": "1105", "TABKEY": "tab1", "PAGENO": str(pg),
        }, timeout=_TIMEOUT)
        block = r.json()[0]
        page = parse_szse_shares(block)
        out.update(page)
        try:
            pagecount = int(block.get("metadata", {}).get("pagecount") or 1)
        except (TypeError, ValueError):
            pagecount = 1
        if pg >= pagecount:
            break
        pg += 1
    return out


def fetch_shares(date: str) -> dict[str, float]:
    """沪+深合并份额 → {code: 份}。"""
    out = dict(fetch_sse_shares(date))
    out.update(fetch_szse_shares(date))
    return out


def fetch_navs(codes: Iterable[str], date: str) -> dict[str, float]:
    """逐 code 取当日单位净值 → {code: NAV}；缺失/失败的 code 不入表。"""
    out: dict[str, float] = {}
    s = _session("https://fundf10.eastmoney.com/")
    for code in codes:
        try:
            r = s.get("https://api.fund.eastmoney.com/f10/lsjz", params={
                "fundCode": code, "pageIndex": "1", "pageSize": "1",
                "startDate": date, "endDate": date,
            }, timeout=_TIMEOUT)
            nav = parse_nav(r.json())
        except (requests.RequestException, ValueError):
            nav = None
        if nav is not None:
            out[code] = nav
    return out


def fetch_sse_index(start: str, end: str) -> list[dict]:
    """上证指数日 K → [{'date','close'}]（含首尾，升序）。start/end='YYYY-MM-DD'。"""
    s = _session("https://quote.eastmoney.com/")
    r = s.get("https://push2his.eastmoney.com/api/qt/stock/kline/get", params={
        "secid": "1.000001", "fields1": "f1", "fields2": "f51,f53", "klt": "101",
        "fqt": "0", "beg": start.replace("-", ""), "end": end.replace("-", ""),
    }, timeout=_TIMEOUT)
    klines = (r.json().get("data") or {}).get("klines") or []
    out = []
    for k in klines:
        parts = k.split(",")
        out.append({"date": parts[0], "close": float(parts[1])})
    return out
