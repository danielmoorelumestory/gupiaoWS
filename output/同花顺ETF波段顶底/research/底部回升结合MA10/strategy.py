"""Fixed long/cash strategy; signals at close, fills at next observed open.

All calculations run offline. Decimal comparisons avoid false crossings at
equality. Dividend entitlements stay in a separate, non-reinvested reserve.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path
import math
import statistics
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2] / "布鲁斯的金融宝藏/replica"))
from bruce_replica.etf_band import etf_band

STRATEGIES = ("COMBO_WAIT", "MA10_ONLY", "BUY_HOLD", "COMBO_SAME")


def features(rows):
    closes = [Decimal(r["adjusted_close"]) for r in rows]
    values = etf_band([str(c) for c in closes], 13)
    means = [sum(closes[i-9:i+1])/10 if i >= 9 else None
             for i in range(len(rows))]
    return [{"value": v, "above_ma": m is not None and c > m,
             "below_ma": m is not None and c < m,
             "ma10": str(m) if m is not None else None}
            for c, v, m in zip(closes, values, means)]


def summary(nav, trades, total_fees):
    if not nav:
        raise ValueError("empty segment")
    days = (date.fromisoformat(nav[-1]["date"])-date.fromisoformat(nav[0]["date"])).days
    years = days/365.25
    peak, drawdown = 1.0, 0.0
    for row in nav:
        peak = max(peak, row["nav"])
        drawdown = min(drawdown, row["nav"]/peak-1)
    completed = [t for t in trades if not t["forced_end"]]
    return {"first": nav[0]["date"], "last": nav[-1]["date"],
            "sessions": len(nav), "calendar_days": days,
            "final_nav": nav[-1]["nav"], "total_return": nav[-1]["nav"]-1,
            "cagr": math.expm1(math.log(nav[-1]["nav"])/years) if days >= 365 else None,
            "max_drawdown": drawdown,
            "time_exposure": statistics.fmean(r["held_session"] for r in nav),
            "capital_exposure": statistics.fmean(r["capital_exposure"] for r in nav),
            "entries": len(trades), "natural_exits": len(completed),
            "forced_exits": len(trades)-len(completed),
            "natural_win_rate": (statistics.fmean(t["net_total_return"] > 0 for t in completed)
                                 if completed else None),
            "mean_holding_sessions": (statistics.fmean(t["holding_sessions"] for t in trades)
                                      if trades else None),
            "fees_initial_capital": total_fees,
            "dividend_reserve": nav[-1]["dividend_reserve"]}


def simulate(rows, feat, strategy, first, last, cost_bps=10, liquidate_end=True):
    if strategy not in STRATEGIES:
        raise ValueError(strategy)
    indices = [i for i, r in enumerate(rows)
               if first <= r["date"] <= last and i >= 13]
    if not indices:
        raise ValueError("no eligible rows")
    side = cost_bps/20000
    cash, reserve, shares, fees = 1.0, 0.0, 0.0, 0.0
    pending, armed, active = None, False, None
    trades, nav, orders = [], [], []

    def sell(i, price, signal_index, forced):
        nonlocal cash, shares, active, fees
        fee = shares*price*side
        cash = shares*price-fee
        fees += fee
        earned = reserve-active["reserve_at_entry"]
        trades.append({**active, "exit_index": i, "exit_date": rows[i]["date"],
                       "exit_signal_index": signal_index,
                       "exit_signal_date": rows[signal_index]["date"] if signal_index is not None else "",
                       "exit_price": price, "exit_shares": shares, "exit_fee": fee,
                       "exit_cash": cash, "earned_dividends": earned,
                       "net_total_return": (cash+earned)/active["entry_cash"]-1,
                       "holding_sessions": i-active["entry_index"]+int(forced),
                       "forced_end": forced})
        shares, active = 0.0, None

    for i in indices:
        r, f = rows[i], feat[i]
        scale, coupon = float(r["share_factor"]), float(r["cumulative_cash"])
        # A holder from yesterday earns today's entitlement before today's open.
        if shares and i > indices[0]:
            previous = rows[i-1]
            old_scale = float(previous["share_factor"])
            reserve += shares/old_scale*(coupon-float(previous["cumulative_cash"]))
            shares *= scale/old_scale
        if pending is not None:
            action, signal_i = pending
            if float(r["volume"]) > 0:
                price = float(r["open"])
                if action == "buy":
                    assert not shares
                    quantity = cash/(price*(1+side))
                    fee = quantity*price*side
                    active = {"entry_index": i, "entry_date": r["date"],
                              "entry_signal_index": signal_i,
                              "entry_signal_date": rows[signal_i]["date"],
                              "entry_price": price, "entry_cash": cash,
                              "entry_shares": quantity, "entry_fee": fee,
                              "reserve_at_entry": reserve}
                    shares, cash, armed = quantity, 0.0, False
                    fees += fee
                else:
                    assert shares
                    sell(i, price, signal_i, False)
            pending = None
        equity = cash+reserve+shares*float(r["close"])
        held = bool(shares)
        exposure = shares*float(r["close"])/equity
        if i == indices[-1] and shares and liquidate_end:
            sell(i, float(r["close"]), None, True)
            equity = cash+reserve
        nav.append({"date": r["date"], "row_index": i, "nav": equity,
                    "trading_cash": cash, "dividend_reserve": reserve,
                    "shares": shares, "held_session": int(held),
                    "capital_exposure": exposure})
        if i == indices[-1]:
            continue
        value = f["value"]
        previous_v = feat[i-1]["value"] if i else None
        action = None
        if shares:
            armed = False
            if strategy != "BUY_HOLD" and f["below_ma"]:
                action = "sell"
                armed = value is not None and value < 30
        elif strategy == "BUY_HOLD":
            if i == indices[0]:
                action = "buy"
        elif strategy == "MA10_ONLY":
            if f["above_ma"]:
                action = "buy"
        else:
            if ((value is not None and value < 30)
                    or (previous_v is not None and previous_v < 30)):
                armed = True
            recovered = value is not None and value >= 30
            crossed = recovered and previous_v is not None and previous_v < 30
            ready = (armed and recovered) if strategy == "COMBO_WAIT" else crossed
            if ready and f["above_ma"]:
                action = "buy"
        if action:
            pending = action, i
            orders.append({"signal_index": i, "signal_date": r["date"], "action": action})
    result = {"nav": nav, "trades": trades, "orders": orders}
    if liquidate_end:
        result["metrics"] = summary(nav, trades, fees)
    return result
