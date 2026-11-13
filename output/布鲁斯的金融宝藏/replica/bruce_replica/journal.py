"""交易记录表模板，栏目按第26集 01:20–03:58 画面逐栏还原（Codex 抽帧核对）。

原表分三块：基本面（实际填的是资金面信号）、技术面、结论与仓单。
原表并排有两组仓单栏，这里改成一行一张仓单，同一天多张仓单就写多行。
「数据日期」「规则版本」「备注」三栏是研究者加的审计字段，原表没有。
"""
from __future__ import annotations

import csv
from pathlib import Path

CAPITAL = ["资本1(股债息差)", "资本2(未公开)", "AD(宽广度)", "筹码", "基本面总结"]
TECH = ["轨道趋势", "轨道内位置", "KDJ", "MACD(VWMACD)", "技术面总结"]
ORDER = ["行动", "仓单", "手数", "单价", "总金额", "止损位", "最大亏损", "当前价格",
         "账面盈亏", "盈亏比例", "平仓盈亏", "delta", "波幅"]
ACCOUNT = ["初始/账面盈亏", "入袋盈亏"]
AUDIT = ["数据日期", "规则版本", "备注"]
COLUMNS = ["日期", *CAPITAL, *TECH, "结论", *ORDER, *ACCOUNT, *AUDIT]


def init(path: str | Path) -> Path:
    """新建空记录表（已存在则不覆盖）。用 utf-8-sig 编码，Excel 可直接打开。"""
    p = Path(path)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(COLUMNS)
    return p


def append(path: str | Path, row: dict) -> None:
    """追加一行。未知栏目会报错，避免写错列。"""
    unknown = set(row) - set(COLUMNS)
    if unknown:
        raise KeyError(f"记录表没有这些栏目：{sorted(unknown)}")
    p = init(path)
    with p.open("a", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=COLUMNS).writerow(row)


def max_loss(entry: float, stop: float, lots: float, multiplier: float = 1.0) -> float:
    """按止损位算计划内最大亏损。原表样例：单价395、止损320、100手，记 -7500。

    这是按计划止损成交的亏损，不是最坏情况；期权买方的最坏情况是亏完全部权利金。
    合约乘数原表样例没有体现，默认 1，实际使用时按合约填写。
    """
    return (stop - entry) * lots * multiplier
