"""交易所份额响应与东财 NAV 响应的纯解析函数。单位统一产出：份额=份，NAV=元/份。"""
import re

_TAG = re.compile(r"<[^>]+>")


def parse_sse_shares(raw: dict) -> dict[str, float]:
    """上交所 commonQuery 响应 → {code: 份}。TOT_VOL 单位万份，×10000。"""
    out: dict[str, float] = {}
    for row in raw.get("result", []):
        code = row.get("SEC_CODE")
        vol = row.get("TOT_VOL")
        if code and vol not in (None, ""):
            try:
                out[code] = float(str(vol).replace(",", "")) * 10000
            except ValueError:
                pass
    return out


def parse_szse_shares(raw) -> dict[str, float]:
    """深交所 ShowReport(CATALOGID=1105) 响应 → {code: 份}。dqgm 单位万份，×10000；仅取 jjlb=ETF。"""
    out: dict[str, float] = {}
    blocks = raw if isinstance(raw, list) else [raw]
    for b in blocks:
        for row in b.get("data", []):
            if _TAG.sub("", str(row.get("jjlb", ""))).strip() != "ETF":
                continue
            code = _TAG.sub("", str(row.get("sys_key", ""))).strip()
            val = _TAG.sub("", str(row.get("dqgm", ""))).replace(",", "").strip()
            if code and val:
                try:
                    out[code] = float(val) * 10000
                except ValueError:
                    pass
    return out


def parse_nav(raw: dict) -> float | None:
    """东财 lsjz 响应 → 第一条(最近日)的 DWJZ(元/份)；无则 None。"""
    lst = (raw.get("Data") or {}).get("LSJZList") or []
    if not lst:
        return None
    try:
        return float(lst[0].get("DWJZ"))
    except (TypeError, ValueError):
        return None
