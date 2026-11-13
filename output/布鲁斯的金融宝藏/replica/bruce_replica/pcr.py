"""短线层：期权 PCR 加标准差通道（金融宝藏第3集 2026-09-22、第7集 2026-09-30）。

他明说的规则：
- PCR 击穿上轨 → 顶部，开空；击穿下轨 → 底部。逻辑是期权参与者是聪明钱，
  PCR 高代表聪明钱在买认沽，要顺着它，不当反向指标用。
- 没有信号就空仓。
- 单边行情里第一个反向信号多半只是回调，不是反转（他举 4/17 的误报）。
- 50 的 PCR 比 300 的重要，有提前量：300 击穿下轨而 50 没有击穿，下跌没有结束（他称回测出现过 4 次）。

口径（已用画面数值核对）：
- 他图上的「300 PCR」「50 PCR」是中金所股指期权 IO、HO 的**持仓量**认沽/认购比。
  金融宝藏第7集（9/30）画面右端：300 为 0.7491、50 为 0.7329；
  用中金所日统计算出的 9/30 值是 0.7491、0.7329，四位小数全对。
- 通道是 20 日、2 倍标准差（第3集画面的 `BB 20 2`）。50 的三条轨算出来是 0.6807/0.7153/0.7498，
  画面是 0.6815/0.7158/0.7502，差不到 0.001。300 的轨算出来 0.722–0.857，画面 0.730–0.845，差约 0.01，原因未查明。
- 9/28、9/29 IO 击穿下轨而 HO 没有，正是他 9/30 讲的「300 破、50 没破」。
- 他举的 13 个历史日期，用 IO 通道看：前后一两天内触轨且方向一致的有 5–6 个，
  其余多数方向一致但只到 1.2–1.7 倍；3/3、3/25、6/23 对不上。那些日期是他对着图回顾时口述的，本身不精确。

仍然没有的：左图「全市场 ETF 与期货期权加权」的加权方式。这里的「合计」只是把张数相加，不是他的算法。
上交所 ETF 期权的数据也能用（--source sse），但对不上他的数值。
"""
from __future__ import annotations

import pandas as pd

ETF50, ETF300 = "510050", "510300"   # 上交所 ETF 期权
HO, IO, MO = "HO", "IO", "MO"            # 中金所股指期权：上证50、沪深300、中证1000
TOP, BOTTOM, NONE = "击穿上轨（顶部/开空信号）", "击穿下轨（底部信号）", "无信号"


def pcr_series(stats: pd.DataFrame, underlying: str | None = None, basis: str = "oi") -> pd.Series:
    """按日的认沽/认购比。underlying=None 为表内全部标的合计（按张数相加，等于按规模加权）。

    basis："oi" 持仓量，"vol" 成交量。
    """
    x = stats if underlying is None else stats[stats["underlying"] == underlying]
    g = x.groupby("date")[[f"put_{basis}", f"call_{basis}"]].sum()
    return (g[f"put_{basis}"] / g[f"call_{basis}"]).rename("pcr")


def pcr_band(pcr: pd.Series, window: int = 20, k: float = 2.0) -> pd.DataFrame:
    """PCR 的滚动均值加减 k 倍标准差通道，并标出当日信号。"""
    mid = pcr.rolling(window).mean()
    sd = pcr.rolling(window).std(ddof=0)
    out = pd.DataFrame({"pcr": pcr, "mid": mid, "upper": mid + k * sd, "lower": mid - k * sd})
    out["signal"] = NONE
    out.loc[pcr >= out["upper"], "signal"] = TOP
    out.loc[pcr <= out["lower"], "signal"] = BOTTOM
    out.loc[mid.isna(), "signal"] = None
    return out


def recent_signal(band: pd.DataFrame, lookback: int = 3) -> str:
    """最近 lookback 个交易日内最新的一个非空信号；没有则为无信号。lookback=3 为研究者自选。"""
    tail = band["signal"].dropna().iloc[-lookback:]
    hits = tail[tail != NONE]
    return hits.iloc[-1] if len(hits) else NONE


def interpret(sig50: str, sig300: str, trend: str = "未知") -> str:
    """把 50 与 300 的信号合成他的说法。trend：当前单边趋势方向 "上行"/"下行"/"未知"，人工判断。"""
    if sig300 == BOTTOM and sig50 != BOTTOM:
        return "300 击穿下轨而 50 未击穿：按他的规则，下跌没有结束，不算底"
    if sig50 == BOTTOM:
        msg = "50 击穿下轨：底部信号" + ("（300 同步确认）" if sig300 == BOTTOM else "（300 尚未确认，50 有提前量）")
        return msg + ("；但处于单边下行，首个反向信号多半只是反弹" if trend == "下行" else "")
    if TOP in (sig50, sig300):
        msg = "击穿上轨：顶部信号，他的做法是买认沽"
        return msg + ("；但处于单边上行，首个反向信号多半只是回调" if trend == "上行" else "")
    return "无信号：按他的规则空仓等待"
