"""同花顺 ETF 波段顶底的截图核验复现（非官方源码）。

100 * SUM(MAX(CLOSE-REF(CLOSE,1),0),13) / SUM(ABS(CLOSE-REF(CLOSE,1)),13)

周期 13、收盘价、等权滚动求和已经核验，不能换成递推 SMA。
只依赖标准库，可作为 bruce_replica 模块调用或单独运行。资料与来源：
output/同花顺ETF波段顶底/README.md。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from collections import deque
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

PERIOD = 13
HIGH_LINE = 70
LOW_LINE = 30
FORMULA_VERSION = "1.0.0"
Close = Decimal | float | int | str | None


def _price(value: Close) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"无效收盘价：{value!r}") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"收盘价须为有限正数：{value!r}")
    return result


def etf_band(closes: Iterable[Close], period: int = PERIOD) -> list[float | None]:
    """按时间升序计算，返回与输入等长的波段值；不修改输入、不四舍五入。

    完整窗口需要 period+1 个收盘价。None 中断窗口，不跨缺失价算涨跌；
    不足窗口或分母为零返回 None。这些边界处理是本项目的选择，未验证
    同花顺行为。Decimal 避免旧波动退出后浮点残差造成虚假的非零分母。
    """
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("period 须为正整数")
    changes: deque[Decimal] = deque()
    up_sum = abs_sum = Decimal(0)
    previous = None
    result = []
    for raw in closes:
        current = _price(raw)
        if current is None:
            previous = None
            changes.clear()
            up_sum = abs_sum = Decimal(0)
            result.append(None)
            continue
        if previous is None:
            previous = current
            result.append(None)
            continue
        change = current - previous
        previous = current
        changes.append(change)
        up_sum += max(change, Decimal(0))
        abs_sum += abs(change)
        if len(changes) > period:
            expired = changes.popleft()
            up_sum -= max(expired, Decimal(0))
            abs_sum -= abs(expired)
        result.append(float(100 * up_sum / abs_sum)
                      if len(changes) == period and abs_sum else None)
    return result


def zone(value: float | None) -> str:
    """严格 <30、>70；等号归中间区为项目约定，尚未核验官方边界。"""
    if value is None:
        return "无有效值"
    if value < LOW_LINE:
        return "低位区"
    if value > HIGH_LINE:
        return "高位区"
    return "中间区"


def load_prices(path: Path, symbol: str | None = None) -> tuple[list[dict], dict]:
    """读取 date/close CSV、同字段 JSON rows，或腾讯日线原始 JSON。

    只读取已经提供的价格，不自动补齐日期、不转换复权、不推定末行已收盘。
    """
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not {"date", "close"}.issubset(reader.fieldnames or []):
                raise ValueError("CSV 须包含 date、close 列")
            rows = [{"date": r["date"], "close": r["close"] or None} for r in reader]
        return rows, {"symbol": symbol, "source_series": "csv"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return payload["rows"], {"symbol": symbol or payload.get("symbol"), "source_series": "rows"}
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    if not data:
        raise ValueError("JSON 须含 rows，或腾讯 data[symbol].qfqday/day")
    if symbol is None:
        if len(data) != 1:
            raise ValueError("JSON 有多个标的，请提供 --symbol")
        symbol = next(iter(data))
    if symbol not in data:
        raise ValueError(f"JSON 中没有标的 {symbol}")
    item = data[symbol]
    key = next((k for k in ("qfqday", "day") if item.get(k)), None)
    if key is None:
        raise ValueError(f"{symbol} 没有有效日线")
    # 腾讯字段为 date/open/close/high/low/volume；close 是下标 2。
    rows = [{"date": r[0], "close": r[2]} for r in item[key]]
    return rows, {"symbol": symbol, "source_series": key}


def calculate_rows(rows: list[dict], period: int = PERIOD) -> list[dict]:
    """检查日期严格升序，输出逐日读数；缺失价格明确保留，不做填充。"""
    dates = [date.fromisoformat(r["date"]) for r in rows]
    if any(b <= a for a, b in zip(dates, dates[1:])):
        raise ValueError("日期须严格升序，不能重复")
    values = etf_band((r["close"] for r in rows), period)
    return [{"date": str(day), "close": None if r["close"] is None else str(r["close"]),
             "value": value, "display_value": None if value is None else f"{value:.3f}",
             "zone": zone(value)} for day, r, value in zip(dates, rows, values)]


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            if path.suffix.lower() == ".csv":
                writer = csv.DictWriter(stream, fieldnames=["date", "close", "value", "display_value", "zone"],
                                        lineterminator="\n")
                writer.writeheader()
                writer.writerows(payload["rows"])
            else:
                json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="本地日线 JSON 或 date/close CSV")
    parser.add_argument("--symbol", help="腾讯标的，例如 sh588060；文件只有一只时可省略")
    parser.add_argument("--period", type=int, default=PERIOD, help="默认已核验周期 13；其他周期未核验")
    parser.add_argument("--output", type=Path, help="导出全序列，.csv 为表格，其他后缀为 JSON")
    args = parser.parse_args(argv)
    try:
        if args.output and args.input.resolve() == args.output.resolve():
            raise ValueError("输出文件不能覆盖原始行情输入")
        rows, source = load_prices(args.input, args.symbol)
        if not rows:
            raise ValueError("行情输入为空")
        readings = calculate_rows(rows, args.period)
        payload = {"indicator": "ETF波段顶底", "formula_version": FORMULA_VERSION,
                   "provenance": "截图核验复现，非官方源码", **source,
                   "period": args.period, "high_line": HIGH_LINE, "low_line": LOW_LINE,
                   "final_bar_confirmed": False, "latest": readings[-1], "rows": readings}
        if args.output:
            _save(args.output, payload)
        print(json.dumps({k: v for k, v in payload.items() if k != "rows"},
                         ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
