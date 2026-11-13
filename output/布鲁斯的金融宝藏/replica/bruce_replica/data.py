"""取数与本地存储。数据源为 AKShare（开源、免登录）；计算模块不依赖这里，可换成任何数据源。

全市场快照只能取到「当下」的截面，历史上每天的涨跌家数拿不到，
所以需要每个交易日收盘后跑一次，把当天读数攒进 breadth_daily.csv，攒够约 40 天后 MCL 才可用。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_SPOT_COLS = {"代码": "code", "名称": "name", "最新价": "close", "涨跌幅": "pct_chg", "成交量": "volume",
              "成交额": "amount", "换手率": "turnover", "总市值": "total_mv", "昨收": "prev_close"}


def fetch_snapshot() -> pd.DataFrame:
    """沪深京全部 A 股的当日截面（东方财富，经 AKShare）。约需数分钟。"""
    import akshare as ak

    raw = ak.stock_zh_a_spot_em()
    df = raw.rename(columns=_SPOT_COLS)[list(_SPOT_COLS.values())]
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def filter_pool(df: pd.DataFrame, include_bj: bool = True) -> pd.DataFrame:
    """股票池。他只说「全市场」，是否含北交所未给出，默认包含。"""
    if include_bj:
        return df
    return df[df["code"].str[0].isin(list("036"))]


def save_snapshot(df: pd.DataFrame, day: date, data_dir: Path = DATA_DIR) -> Path:
    p = data_dir / "snapshots" / f"{day:%Y%m%d}.csv.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)
    return p


def load_snapshot(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"code": str})


def upsert_daily(day: date, values: dict, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """把当天读数写入每日汇总表（同一天重复跑会覆盖），返回按日期排序的全表。"""
    p = data_dir / "breadth_daily.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([{"date": f"{day:%Y-%m-%d}", **values}])
    if p.exists():
        old = pd.read_csv(p, dtype={"date": str})
        row = pd.concat([old[old["date"] != row["date"].iloc[0]], row])
    row = row.sort_values("date").reset_index(drop=True)
    row.to_csv(p, index=False)
    return row


def fetch_index_daily(symbol: str = "sh000001") -> pd.DataFrame:
    """指数日线（新浪，经 AKShare）。默认上证指数，他第19集分析用的就是上证。"""
    import akshare as ak

    df = ak.stock_zh_index_daily(symbol=symbol)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")[["open", "high", "low", "close", "volume"]].astype(float)


_OPT_COLS = {"合约标的代码": "underlying", "合约标的名称": "name", "总成交额": "amount", "认购成交量": "call_vol",
             "认沽成交量": "put_vol", "未平仓认购合约数": "call_oi", "未平仓认沽合约数": "put_oi"}


def fetch_sse_option_stats(day: date) -> pd.DataFrame:
    """上交所 ETF 期权某日的分标的统计（认购/认沽成交量与持仓量）。非交易日返回空表。"""
    import akshare as ak

    try:
        raw = ak.option_daily_stats_sse(date=f"{day:%Y%m%d}")
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.rename(columns=_OPT_COLS)[list(_OPT_COLS.values())].copy()
    df["underlying"] = df["underlying"].astype(str).str.zfill(6)
    df.insert(0, "date", f"{day:%Y-%m-%d}")
    return df


def backfill_sse_options(start: date, end: date, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """把 [start, end] 内缺的交易日补进 option_sse_daily.csv，返回全表。交易日历取自上证指数日线。"""
    p = data_dir / "option_sse_daily.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(p, dtype={"date": str, "underlying": str}) if p.exists() else pd.DataFrame()
    have = set(old["date"]) if len(old) else set()
    days = [d.date() for d in fetch_index_daily().index if start <= d.date() <= end]
    new = [fetch_sse_option_stats(d) for d in days if f"{d:%Y-%m-%d}" not in have]
    out = pd.concat([old, *[n for n in new if len(n)]], ignore_index=True) if new else old
    out = out.sort_values(["date", "underlying"]).reset_index(drop=True)
    out.to_csv(p, index=False)
    return out


def fetch_equity_bond_spread() -> pd.DataFrame:
    """沪深300 股债利差日线（乐咕乐股，经 AKShare，2005 年起）：盈利收益率减 10 年国债收益率，单位百分点。

    他说的是「全市场」口径，这里是沪深300，是免费日频数据里最接近的。
    """
    import akshare as ak

    raw = ak.stock_ebs_lg()
    df = pd.DataFrame({"spread": raw["股债利差"].astype(float).values * 100.0,
                       "index": raw["沪深300指数"].astype(float).values},
                      index=pd.to_datetime(raw["日期"]).rename("date"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_DIR / "equity_bond_spread.csv")
    return df


_CFFEX_URL = "http://www.cffex.com.cn/sj/hqsj/rtj/{d:%Y%m}/{d:%d}/{d:%Y%m%d}_1.csv"


def fetch_cffex_option_stats(day: date) -> pd.DataFrame:
    """中金所某日股指期权按品种（IO 沪深300、HO 上证50、MO 中证1000）汇总的认购/认沽成交量、成交额、持仓量。

    来源是中金所官网的日统计文件。非交易日或取不到时返回空表。输出列与上交所那张表一致，多一组 *_amt。
    """
    import io

    import requests

    try:
        resp = requests.get(_CFFEX_URL.format(d=day), headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if resp.status_code != 200 or b"-C-" not in resp.content:
            return pd.DataFrame()
        raw = pd.read_csv(io.BytesIO(resp.content), encoding="gbk")
    except Exception:
        return pd.DataFrame()
    raw.columns = [c.strip() for c in raw.columns]
    code = raw["合约代码"].astype(str).str.strip()
    opt = raw[code.str.contains(r"-[CP]-")].copy()
    code = code[opt.index]
    opt["underlying"] = code.str[:2]
    opt["cp"] = code.str.extract(r"-([CP])-")[0].map({"C": "call", "P": "put"})
    for c in ("成交量", "成交金额", "持仓量"):
        opt[c] = pd.to_numeric(opt[c], errors="coerce").fillna(0.0)
    g = opt.groupby(["underlying", "cp"])[["成交量", "成交金额", "持仓量"]].sum().unstack("cp")
    out = pd.DataFrame({f"{cp}_{k}": g[(col, cp)] for col, k in (("成交量", "vol"), ("成交金额", "amt"), ("持仓量", "oi"))
                        for cp in ("call", "put")}).reset_index()
    out.insert(0, "date", f"{day:%Y-%m-%d}")
    return out


def backfill_cffex_options(start: date, end: date, data_dir: Path = DATA_DIR, pause: float = 0.3) -> pd.DataFrame:
    """把 [start, end] 内缺的交易日补进 option_cffex_daily.csv，返回全表。"""
    import time

    p = data_dir / "option_cffex_daily.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(p, dtype={"date": str}) if p.exists() else pd.DataFrame()
    have = set(old["date"]) if len(old) else set()
    new = []
    for d in (x.date() for x in fetch_index_daily().index if start <= x.date() <= end):
        if f"{d:%Y-%m-%d}" in have:
            continue
        new.append(fetch_cffex_option_stats(d))
        time.sleep(pause)
    out = pd.concat([old, *[n for n in new if len(n)]], ignore_index=True) if new else old
    out = out.sort_values(["date", "underlying"]).reset_index(drop=True)
    out.to_csv(p, index=False)
    return out


_HIST_COLS = {"日期": "date", "涨跌幅": "pct_chg", "成交量": "volume", "成交额": "amount", "换手率": "turnover"}


def backfill_stock_hist(codes: list[str], start: date, end: date, data_dir: Path = DATA_DIR,
                        workers: int = 6, retries: int = 2, subdir: str = "hist") -> tuple[int, list[str]]:
    """逐只下载个股不复权日线（东方财富，经 AKShare），每只存 hist/<代码>.csv。已有的跳过，可断点续跑。

    返回（本次新下载的只数，失败的代码）。全市场约六千只，并发 6 时约需半小时。
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    import akshare as ak

    out_dir = data_dir / subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    def one(code: str) -> str | None:
        p = out_dir / f"{code}.csv"
        if p.exists():
            return None
        for i in range(retries + 1):
            try:
                df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=f"{start:%Y%m%d}",
                                        end_date=f"{end:%Y%m%d}", adjust="")
                df = df.rename(columns=_HIST_COLS)[list(_HIST_COLS.values())] if len(df) else pd.DataFrame(columns=list(_HIST_COLS.values()))
                df.to_csv(p, index=False)
                return "ok"
            except Exception:
                time.sleep(1.5 * (i + 1))
        return "fail:" + code

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, codes))
    return sum(r == "ok" for r in res), [r[5:] for r in res if r and r.startswith("fail:")]


def breadth_from_hist(data_dir: Path = DATA_DIR, include_bj: bool = True, subdir: str = "hist") -> pd.DataFrame:
    """把 hist/ 下的个股日线汇总成每日宽广度表，列与 breadth_daily.csv 相同。

    股票池是下载时还在上市的股票，期间已退市的不在内，所以越早的日期家数越少、略有偏差。
    """
    frames = []
    for p in sorted((data_dir / subdir).glob("*.csv")):
        if not include_bj and p.stem[0] not in "036":
            continue
        df = pd.read_csv(p, dtype={"date": str})
        if len(df):
            frames.append(df)
    a = pd.concat(frames, ignore_index=True)
    a = a[a["volume"] > 0]
    up, dn = a["pct_chg"] > 0, a["pct_chg"] < 0
    g = pd.DataFrame({
        "n_up": up.groupby(a["date"]).sum(), "n_down": dn.groupby(a["date"]).sum(),
        "n_all": a.groupby("date")["pct_chg"].size(),
        "amt_up": a["amount"].where(up, 0).groupby(a["date"]).sum(), "amt_dn": a["amount"].where(dn, 0).groupby(a["date"]).sum(),
        "vol_up": a["volume"].where(up, 0).groupby(a["date"]).sum(), "vol_dn": a["volume"].where(dn, 0).groupby(a["date"]).sum(),
        "turnover_gt5_share": (a["turnover"] > 5).groupby(a["date"]).mean(),
    })
    out = pd.DataFrame({
        "n_up": g["n_up"], "n_down": g["n_down"], "n_flat": g["n_all"] - g["n_up"] - g["n_down"],
        "up_ratio": g["n_up"] / g["n_all"], "ad_ratio": g["n_up"] / g["n_down"],
        "trin_amount": (g["n_up"] / g["n_down"]) / (g["amt_up"] / g["amt_dn"]),
        "trin_volume": (g["n_up"] / g["n_down"]) / (g["vol_up"] / g["vol_dn"]),
        "down_amount_share": g["amt_dn"] / (g["amt_up"] + g["amt_dn"]),
        "turnover_gt5_share": g["turnover_gt5_share"],
    })
    return out.reset_index()


def merge_breadth_history(hist: pd.DataFrame, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """把回补的历史并入 breadth_daily.csv。已有的日期（每日快照算的）保留不动，只补缺的。"""
    p = data_dir / "breadth_daily.csv"
    old = pd.read_csv(p, dtype={"date": str}) if p.exists() else pd.DataFrame(columns=hist.columns)
    out = pd.concat([old, hist[~hist["date"].isin(set(old["date"]))]], ignore_index=True)
    out = out.sort_values("date").reset_index(drop=True)
    out.to_csv(p, index=False)
    return out


def fetch_mktcap_gdp() -> pd.DataFrame:
    """A 股总市值与 GDP（乐咕乐股，经 AKShare，2005 年起日频），单位亿元，附比值 ratio。"""
    import akshare as ak

    raw = ak.stock_buffett_index_lg()
    df = pd.DataFrame({"mktcap": raw["总市值"].astype(float).values, "gdp": raw["GDP"].astype(float).values},
                      index=pd.to_datetime(raw["日期"]).rename("date"))
    df["ratio"] = df["mktcap"] / df["gdp"]
    return df


def fetch_index_pe(symbol: str = "沪深300") -> pd.DataFrame:
    """指数市盈率历史（乐咕乐股）：静态、滚动及各自的等权、中位数口径。"""
    import akshare as ak

    raw = ak.stock_index_pe_lg(symbol=symbol)
    return raw.set_index(pd.to_datetime(raw["日期"]).rename("date")).drop(columns=["日期"])


def fetch_all_a_valuation() -> pd.DataFrame:
    """全部 A 股的等权平均与中位数市盈率（TTM）、市净率（乐咕乐股，月频加最新一日）。"""
    import akshare as ak

    pe = ak.stock_a_ttm_lyr().set_index("date")[["averagePETTM", "middlePETTM"]]
    pb = ak.stock_a_all_pb().set_index("date")[["equalWeightAveragePB", "middlePB"]]
    out = pe.join(pb, how="outer")
    out.index = pd.to_datetime(out.index)
    out.columns = ["pe_equal", "pe_median", "pb_equal", "pb_median"]
    return out


BROAD_ETFS = ("510300", "510050", "588000")   # 数据证伪第5集 01:29 画面代码里的三只


def fetch_etf_amount(codes: tuple[str, ...] = BROAD_ETFS, start: str = "20240101") -> pd.DataFrame:
    """几只 ETF 的日成交额（亿元），每只一列。"""
    import akshare as ak

    cols = {}
    for c in codes:
        d = ak.fund_etf_hist_em(symbol=c, period="daily", start_date=start, end_date=f"{date.today():%Y%m%d}", adjust="")
        cols[c] = pd.Series(d["成交额"].astype(float).values / 1e8, index=pd.to_datetime(d["日期"]))
    return pd.DataFrame(cols).rename_axis("date")
