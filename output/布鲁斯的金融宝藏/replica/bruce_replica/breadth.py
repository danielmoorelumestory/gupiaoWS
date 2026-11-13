"""短线层：市场宽广度（红盘率）、阿姆士指标（TRIN）、麦克莱伦摆动（MCL）、均线上方个股占比。

依据：
- 阿姆士公式：第21集 00:48 画面，(上涨家数/下跌家数)/(上涨成交量/下跌成交量)。
  第16集口述用的是成交额，所以两种口径都算，分别命名。
- MCL：第22集 04:40 画面代码，DIF=上涨家数-下跌家数，MCL=EMA(DIF,19)-EMA(DIF,39)。
- 平盘和 ST 的处理博主没有给出（第22集 00:13 只说各人口径不同），做成开关。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BreadthReading:
    n_up: int
    n_down: int
    n_flat: int
    up_ratio: float            # 红盘率 = 上涨家数 / 全部有成交个股
    ad_ratio: float            # 上涨家数 / 下跌家数
    trin_amount: float         # 成交额口径的阿姆士
    trin_volume: float         # 成交量口径的阿姆士
    down_amount_share: float   # 下跌股成交额占（涨+跌）成交额的比例

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else float("nan")


def breadth_reading(
    df: pd.DataFrame,
    *,
    pct_col: str = "pct_chg",
    vol_col: str = "volume",
    amt_col: str = "amount",
    name_col: str | None = "name",
    exclude_st: bool = False,
    flat_as_down: bool = False,
) -> BreadthReading:
    """由一天的全市场个股截面算出红盘率和两种口径的阿姆士。

    exclude_st / flat_as_down 是口径开关，默认值为研究者自选：
    默认不剔除 ST、平盘股不计入涨跌两边（与第16集 80.9% 涨、17.6% 跌、家数比 4.6 的算法一致）。
    """
    d = df[[c for c in (pct_col, vol_col, amt_col, name_col) if c and c in df.columns]].copy()
    d = d.dropna(subset=[pct_col])
    d = d[d[amt_col].fillna(0) > 0]          # 停牌、无成交的不计
    if exclude_st and name_col and name_col in d.columns:
        d = d[~d[name_col].astype(str).str.upper().str.contains("ST")]
    up, down, flat = d[d[pct_col] > 0], d[d[pct_col] < 0], d[d[pct_col] == 0]
    if flat_as_down:
        down = pd.concat([down, flat])
    n_up, n_down, n_flat = len(up), len(down), len(flat)
    amt_up, amt_down = up[amt_col].sum(), down[amt_col].sum()
    vol_up, vol_down = up[vol_col].sum(), down[vol_col].sum()
    ad = _safe_div(n_up, n_down)
    return BreadthReading(
        n_up=n_up,
        n_down=n_down,
        n_flat=n_flat,
        up_ratio=_safe_div(n_up, len(d)),
        ad_ratio=ad,
        trin_amount=_safe_div(ad, _safe_div(amt_up, amt_down)),
        trin_volume=_safe_div(ad, _safe_div(vol_up, vol_down)),
        down_amount_share=_safe_div(amt_down, amt_up + amt_down),
    )


def trin(n_up: float, n_down: float, x_up: float, x_down: float) -> float:
    """标准阿姆士：(上涨家数/下跌家数)/(上涨成交/下跌成交)。成交可以是量或额。"""
    return _safe_div(_safe_div(n_up, n_down), _safe_div(x_up, x_down))


def up_side_share(up_ratio: float, trin_value: float) -> float:
    """已知红盘率 b 和阿姆士 T（无平盘），反推上涨股占成交的比例 b/(b+T(1-b))。

    用来读懂「只有 5% 红盘、阿姆士 0.3」这类读数：少数上涨股拿走了多少成交。
    """
    return _safe_div(up_ratio, up_ratio + trin_value * (1 - up_ratio))


def ema_cn(series: pd.Series, n: int) -> pd.Series:
    """国内行情软件的 EMA(X,N)：Y = (2X + (N-1)Y')/(N+1)，首值取第一个数据。"""
    return series.ewm(span=n, adjust=False).mean()


def mcclellan(net_advances: pd.Series, n1: int = 19, n2: int = 39) -> pd.DataFrame:
    """麦克莱伦摆动。输入为每日（上涨家数-下跌家数）。参数 19/39 来自第22集画面。

    至少需要约 39 个交易日的数据，前段数值受 EMA 初值影响，不宜使用。
    """
    e1, e2 = ema_cn(net_advances, n1), ema_cn(net_advances, n2)
    return pd.DataFrame({"ema1": e1, "ema2": e2, "mcl": e1 - e2})


def share_above_ma(close: pd.DataFrame, windows: tuple[int, ...] = (20, 60, 250)) -> pd.DataFrame:
    """每日收盘价高于 N 日均线的个股占比（P20/P60/P250）。

    close：行是日期、列是个股的收盘价宽表。
    第22集画面表有 P20/P60/P250 三列百分数、第23集说是 20/60/250 日均线；
    「高于均线的个股占比」这一严格定义是推断，画面没有给公式。
    """
    out = {}
    for w in windows:
        ma = close.rolling(w, min_periods=w).mean()
        valid = ma.notna() & close.notna()
        out[f"P{w}"] = ((close > ma) & valid).sum(axis=1) / valid.sum(axis=1).replace(0, np.nan)
    return pd.DataFrame(out)
