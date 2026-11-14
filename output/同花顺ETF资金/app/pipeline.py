"""日度编排：采份额→算净流入→落库→导出 data.json。供 cron 每日收盘后调用。

用法: python3 pipeline.py [YYYY-MM-DD]（默认今天）
"""
import logging
import os
import sys
import time
from datetime import date as _date

from compute import aggregate_flow, compute_daily_flow
import fetch
import store
from export import write_data_json

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(_HERE, "etf_flow.db")
DEFAULT_JSON = os.path.join(_HERE, "data.json")

log = logging.getLogger("pipeline")


def _retry(fn, *args, tries: int = 3, delay: float = 3.0):
    last = None
    for i in range(tries):
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("调用失败(%d/%d): %s", i + 1, tries, e)
            if i < tries - 1:
                time.sleep(delay)
    raise last


def run_daily(conn, date: str, data_path: str = DEFAULT_JSON) -> None:
    """采集 date 当日份额，结合前一交易日算净流入，落库并重导出 data.json。"""
    shares = _retry(fetch.fetch_shares, date)
    store.save_shares(conn, date, shares)

    prev_date = store.latest_date_before(conn, date)
    if prev_date:
        prev_shares = store.read_shares(conn, prev_date)
        navs = _retry(fetch.fetch_navs, shares.keys(), date)
        flows = compute_daily_flow(shares, prev_shares, navs)
        all_f, broad_f = aggregate_flow(flows)
        store.save_agg(conn, date, all_f, broad_f)
        log.info("%s 净流入 全A=%.2f亿 宽基=%.2f亿", date, all_f / 1e8, broad_f / 1e8)
    else:
        log.info("%s 无前一交易日份额，仅落库份额", date)

    try:
        idx = _retry(fetch.fetch_sse_index, date, date)
        if idx:
            store.save_index(conn, date, idx[-1]["close"])
    except Exception as e:  # noqa: BLE001
        log.warning("指数采集失败: %s", e)

    write_data_json(conn, data_path)
    log.info("已导出 %s", data_path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    date = sys.argv[1] if len(sys.argv) > 1 else _date.today().isoformat()
    conn = store.init_db(DEFAULT_DB)
    run_daily(conn, date)


if __name__ == "__main__":
    main()
