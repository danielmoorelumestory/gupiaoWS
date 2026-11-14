"""导出前端用 data.json：flow 元→亿元，拼指数，算 KPI，带免责 note。"""
import json
from datetime import datetime

from compute import cumulative
from store import read_agg_series, read_index_map

_YI = 1e8
NOTE = ("自建估算（份额差×NAV），非同花顺原口径；无盘中数据，T+1；深市历史约6个月。"
        "红=净流入、绿=净流出。")


def build_data_json(conn) -> dict:
    series_raw = read_agg_series(conn)
    idx = read_index_map(conn)
    series = []
    all_yi, broad_yi = [], []
    for r in series_raw:
        a = r["flow_all"] / _YI
        b = r["flow_broad"] / _YI
        all_yi.append(a)
        broad_yi.append(b)
        close = idx.get(r["date"])
        series.append({
            "date": r["date"],
            "flow_all": round(a, 2),
            "flow_broad": round(b, 2),
            "index": round(close, 2) if close is not None else None,
        })

    def kpi(vals: list[float]) -> dict:
        return {
            "yesterday": round(vals[-1], 2) if vals else 0.0,
            "cum60": round(cumulative(vals, 60), 2) if vals else 0.0,
        }

    return {
        "updated": datetime.now().isoformat(timespec="seconds"),
        "note": NOTE,
        "series": series,
        "kpi": {"all": kpi(all_yi), "broad": kpi(broad_yi)},
    }


def write_data_json(conn, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_data_json(conn), f, ensure_ascii=False, indent=2)
