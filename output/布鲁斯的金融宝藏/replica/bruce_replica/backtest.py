"""把他明说的规则写死，在历史上检验。只回答一个问题：信号出现之后，指数的走向是否比平时更偏向他说的方向。

做法（都是研究者设定，他没有给过）：
- 连续触发的日子合并成一次「事件」，相隔不到 gap 个交易日算同一次，取第一天。
- 信号按当天收盘确认，从下一个交易日起算收益，不用未来数据。
- 每个事件看之后 5/10/20/60/120/250 个交易日的指数涨跌，与「任意一天之后同样天数」的平均水平比较。
- 样本数很少时只列数字，不下结论。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def events(flag: pd.Series, gap: int = 10) -> list:
    """把布尔序列里为真的日子合并成事件，返回每个事件的首日。gap 按序列里的行数计。"""
    pos = np.flatnonzero(flag.fillna(False).to_numpy())
    out, last = [], None
    for i in pos:
        if last is None or i - last >= gap:
            out.append(flag.index[i])
        last = i
    return out


def forward_returns(price: pd.Series, dates: list, horizons: tuple[int, ...]) -> pd.DataFrame:
    """每个日期之后 h 个交易日的涨跌幅。到期日超出样本的记为空。"""
    loc = price.index.get_indexer(dates)
    data = {}
    for h in horizons:
        end = loc + h
        ok = end < len(price)
        r = np.full(len(loc), np.nan)
        r[ok] = price.to_numpy()[end[ok]] / price.to_numpy()[loc[ok]] - 1.0
        data[h] = r
    return pd.DataFrame(data, index=pd.Index(dates, name="date"))


def summarize(price: pd.Series, dates: list, horizons: tuple[int, ...], expect: int, start=None) -> pd.DataFrame:
    """事件后的涨跌与全样本基准对比。expect=+1 表示他预期上涨，-1 表示预期下跌。

    start：基准只统计该日期之后的样本，应与信号可用的起点一致。
    """
    fr = forward_returns(price, dates, horizons)
    base_price = price if start is None else price[price.index >= start]
    rows = []
    for h in horizons:
        r = fr[h].dropna()
        base = (base_price.shift(-h) / base_price - 1.0).dropna()
        rows.append({
            "之后交易日": h, "事件数": len(r),
            "平均涨跌": r.mean() if len(r) else np.nan,
            "中位涨跌": r.median() if len(r) else np.nan,
            "方向对的比例": float((np.sign(r) == expect).mean()) if len(r) else np.nan,
            "基准平均涨跌": base.mean(),
            "基准同方向比例": float((np.sign(base) == expect).mean()),
        })
    return pd.DataFrame(rows).set_index("之后交易日")


def state_strategy(price: pd.Series, enter: pd.Series, exit_: pd.Series, start_in: bool = False) -> dict:
    """进场信号出现后持有指数，出场信号出现后空仓，其间保持上一状态。信号次日生效，不计成本和利息。"""
    state, pos = start_in, []
    for e, x in zip(enter.fillna(False).to_numpy(), exit_.fillna(False).to_numpy()):
        if e:
            state = True
        elif x:
            state = False
        pos.append(state)
    held = pd.Series(pos, index=price.index).shift(1, fill_value=start_in)
    ret = price.pct_change().fillna(0.0)
    eq_s, eq_b = (1 + ret.where(held, 0.0)).cumprod(), (1 + ret).cumprod()
    years = (price.index[-1] - price.index[0]).days / 365.25

    def stats(eq: pd.Series) -> dict:
        return {"年化": eq.iloc[-1] ** (1 / years) - 1, "最大回撤": float((eq / eq.cummax() - 1).min())}

    return {"策略": stats(eq_s), "买入持有": stats(eq_b), "持仓时间占比": float(held.mean()),
            "切换次数": int((held != held.shift()).sum() - 1)}
