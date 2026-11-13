"""技术面层：一目均衡表、VWMACD、布林带、CCI、唐奇安通道、KDJ。

输入统一为带 open/high/low/close/volume 列的 DataFrame（按日期升序）。
参数出处：第19集 01:35–01:59 画面（一目 7/22/44、VWMACD 12/26/9、BOLL 20、CCI 14）。
唐奇安和 KDJ 只在第26集表头出现，周期没有给出，默认值为研究者自选。
"""
from __future__ import annotations

import pandas as pd

from .breadth import ema_cn


def ichimoku(df: pd.DataFrame, n1: int = 7, n2: int = 22, n3: int = 44) -> pd.DataFrame:
    """一目均衡表。7/22/44 是他画面上的参数，不是常见的 9/26/52。"""
    hh = lambda n: df["high"].rolling(n).max()
    ll = lambda n: df["low"].rolling(n).min()
    tenkan = (hh(n1) + ll(n1)) / 2
    kijun = (hh(n2) + ll(n2)) / 2
    span_a = ((tenkan + kijun) / 2).shift(n2)
    span_b = ((hh(n3) + ll(n3)) / 2).shift(n2)
    out = pd.DataFrame({"tenkan": tenkan, "kijun": kijun, "span_a": span_a, "span_b": span_b})
    top, bottom = out[["span_a", "span_b"]].max(axis=1), out[["span_a", "span_b"]].min(axis=1)
    out["cloud_pos"] = "云中"
    out.loc[df["close"] > top, "cloud_pos"] = "云上"
    out.loc[df["close"] < bottom, "cloud_pos"] = "云下"
    out.loc[top.isna(), "cloud_pos"] = None
    return out


def vwmacd(df: pd.DataFrame, short: int = 12, long: int = 26, mid: int = 9) -> pd.DataFrame:
    """成交量加权 MACD，按第19集 01:45 画面代码：

    VC1=SUM(C*V,SHORT)/SUM(V,SHORT); VC2=SUM(C*V,LONG)/SUM(V,LONG);
    DIF=VC1-VC2; DEA=EMA(DIF,MID); MACD=(DIF-DEA)*2
    """
    cv = df["close"] * df["volume"]
    vc1 = cv.rolling(short).sum() / df["volume"].rolling(short).sum()
    vc2 = cv.rolling(long).sum() / df["volume"].rolling(long).sum()
    dif = vc1 - vc2
    dea = ema_cn(dif.dropna(), mid).reindex(df.index)
    return pd.DataFrame({"dif": dif, "dea": dea, "macd": (dif - dea) * 2})


def bollinger(df: pd.DataFrame, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """布林带。周期 20 来自画面；标准差倍数 k 画面未给出，2 为研究者自选。"""
    mid = df["close"].rolling(n).mean()
    sd = df["close"].rolling(n).std(ddof=0)
    return pd.DataFrame({"mid": mid, "upper": mid + k * sd, "lower": mid - k * sd})


def cci(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """CCI，周期 14 来自画面。"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma = tp.rolling(n).mean()
    md = tp.rolling(n).apply(lambda x: abs(x - x.mean()).mean(), raw=True)
    return ((tp - ma) / (0.015 * md)).rename("cci")


def donchian(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """唐奇安通道。周期未给出，20 为研究者自选。position 对应记录表的「轨道内位置」。"""
    upper, lower = df["high"].rolling(n).max(), df["low"].rolling(n).min()
    mid = (upper + lower) / 2
    out = pd.DataFrame({"upper": upper, "mid": mid, "lower": lower})
    out["position"] = "中轨偏上"
    out.loc[df["close"] < mid, "position"] = "中轨偏下"
    out.loc[df["close"] >= upper, "position"] = "上轨"
    out.loc[df["close"] <= lower, "position"] = "下轨"
    out.loc[upper.isna(), "position"] = None
    return out


def kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """KDJ。参数未给出，9/3/3 为研究者自选（行情软件默认）。"""
    low_n, high_n = df["low"].rolling(n).min(), df["high"].rolling(n).max()
    rsv = ((df["close"] - low_n) / (high_n - low_n) * 100).dropna()
    k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    d = k.ewm(alpha=1 / m2, adjust=False).mean()
    return pd.DataFrame({"k": k, "d": d, "j": 3 * k - 2 * d}).reindex(df.index)


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """日线合成周线（周五为周末）。他用周线定中线趋势、日线找入场点（第19集）。"""
    idx = pd.DatetimeIndex(df.index)
    g = df.set_axis(idx).resample("W-FRI")
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "volume": g["volume"].sum(),
    })
    return out.dropna(subset=["close"])


def snapshot(df: pd.DataFrame) -> dict:
    """最新一根 K 线上各指标的读数，供记录表「技术面」各栏填写时参考。"""
    ich, vm, bb, cc, dc, kd = ichimoku(df), vwmacd(df), bollinger(df), cci(df), donchian(df), kdj(df)
    last = df.index[-1]
    return {
        "date": str(last)[:10],
        "close": float(df["close"].iloc[-1]),
        "一目_云位置": ich["cloud_pos"].iloc[-1],
        "VWMACD_DIF": round(float(vm["dif"].iloc[-1]), 2),
        "VWMACD_DEA": round(float(vm["dea"].iloc[-1]), 2),
        "VWMACD_快慢线在零轴": "上方" if min(vm["dif"].iloc[-1], vm["dea"].iloc[-1]) > 0
        else ("下方" if max(vm["dif"].iloc[-1], vm["dea"].iloc[-1]) < 0 else "跨零轴"),
        "布林_位置": "上轨上方" if df["close"].iloc[-1] > bb["upper"].iloc[-1]
        else ("下轨下方" if df["close"].iloc[-1] < bb["lower"].iloc[-1]
              else ("中轨上方" if df["close"].iloc[-1] >= bb["mid"].iloc[-1] else "中轨下方")),
        "CCI": round(float(cc.iloc[-1]), 1),
        "唐奇安_轨道内位置": dc["position"].iloc[-1],
        "KDJ_K": round(float(kd["k"].iloc[-1]), 1),
        "KDJ_D": round(float(kd["d"].iloc[-1]), 1),
        "KDJ_J": round(float(kd["j"].iloc[-1]), 1),
    }
