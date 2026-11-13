"""中期层里公式明确、数据公开的几项。阈值大多未给出，函数只负责计算和定位，不下结论。

- 股债息差及标准差通道（他称「债券系统」）：研判第1集 2026-09-16、第11集 04:09–04:38、第18集 01:38。
  息差上穿上轨是股市底（他举 2024/9、2025/4），跌破下轨是股市顶（他举 2020 年底），
  刚过中轨、未到上轨则未确认。他说用全市场市盈率加权的收益率；窗口、倍数未给出，做成参数。
  用沪深300 股债利差、750 日 2 倍通道检验过：他举的顶底时点基本都落在对应的轨道上，见 README。
- 总市值/GDP：第11集 03:58–04:07，画面标 1.00 高估、0.70 低估、0.50 极低估。
- 换手率 5% 以上个股占比：第18集 01:48–02:06，定义明确，底部阈值未给出。
- 期权 PCR：第14集、第18集只说看「全市场 PCR」的柱子和上轨，口径未给出，这里只提供比值。
"""
from __future__ import annotations

import pandas as pd


def equity_bond_spread(pe: pd.Series, bond_yield_pct: pd.Series) -> pd.Series:
    """股债息差（百分点）= 100/PE - 10年期国债收益率(%)。用 E/P 是研究者自选。"""
    y = bond_yield_pct.reindex(pe.index).ffill()
    return (100.0 / pe - y).rename("spread")


def std_band(series: pd.Series, window: int = 750, k: float = 2.0) -> pd.DataFrame:
    """滚动均值加减 k 倍标准差的通道。window=750（约三年）和 k=2 均为研究者自选。"""
    mid = series.rolling(window, min_periods=window // 2).mean()
    sd = series.rolling(window, min_periods=window // 2).std(ddof=0)
    out = pd.DataFrame({"value": series, "mid": mid, "upper": mid + k * sd, "lower": mid - k * sd})
    out["zone"] = "下轨与中轨之间"
    out.loc[series >= mid, "zone"] = "中轨与上轨之间"
    out.loc[series >= out["upper"], "zone"] = "触及上轨"
    out.loc[series <= out["lower"], "zone"] = "跌破下轨"
    out.loc[mid.isna(), "zone"] = None
    return out


def mktcap_gdp_zone(ratio: float) -> str:
    """总市值/GDP 的区间。分界线 1.00 / 0.70 / 0.50 来自第11集 04:00 画面。"""
    if ratio >= 1.00:
        return "高估区"
    if ratio <= 0.50:
        return "极低估区"
    if ratio <= 0.70:
        return "低估区"
    return "高估线与低估线之间"


def high_turnover_share(df: pd.DataFrame, threshold: float = 5.0, turnover_col: str = "turnover") -> float:
    """换手率高于 threshold(%) 的个股占全部有换手数据个股的比例。5% 来自第18集口述。"""
    t = df[turnover_col].dropna()
    return float((t > threshold).sum() / len(t)) if len(t) else float("nan")


def put_call_ratio(put: float, call: float) -> float:
    """认沽/认购。用成交量、成交额还是持仓量由调用方决定，他没有说明。"""
    return float(put) / float(call) if call else float("nan")


def spread_reading(zone: str | None) -> str:
    """股债息差所在区间对应他的中长期说法。"""
    return {
        "触及上轨": "股市相对债券极便宜：他的中长期底部信号",
        "跌破下轨": "债券吸引力远大于股市：他的中长期顶部信号",
        "中轨与上轨之间": "过了中轨、未到上轨：底部未确认（他 9/16 称从中轨到上轨至少还要两个月）",
        "下轨与中轨之间": "中轨以下：偏贵，未到顶部信号",
    }.get(zone, "数据不足")


def band_episodes(band: pd.DataFrame, zone: str, gap_days: int = 30) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """把处于某个区间的日子合并成时段；相隔不到 gap_days 个自然日的并成一段。"""
    days = band.index[band["zone"] == zone]
    out: list[list[pd.Timestamp]] = []
    for d in days:
        if out and (d - out[-1][1]).days < gap_days:
            out[-1][1] = d
        else:
            out.append([d, d])
    return [(a, b) for a, b in out]


def etf_amount_ma(amounts: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """几只宽基 ETF 成交额合计及其 n 日均线（数据证伪第5集 01:29 画面代码，N=20）。

    他拿这张图当**反例**：ETF 合计成交额看不出「国家队进场」。不是择时信号。
    """
    total = amounts.sum(axis=1)
    return pd.DataFrame({"total": total, "ma": total.rolling(n).mean()})


def percentile_band(series: pd.Series, years: int = 10, low: float = 0.2, high: float = 0.8) -> dict:
    """最新值在近 years 年里的位置，以及 low/high 分位对应的数值。年数和分位都是研究者自选。"""
    s = series.dropna()
    w = s[s.index >= s.index[-1] - pd.DateOffset(years=years)]
    return {"value": float(s.iloc[-1]), "low": float(w.quantile(low)), "high": float(w.quantile(high)),
            "pct": float((w <= s.iloc[-1]).mean())}
