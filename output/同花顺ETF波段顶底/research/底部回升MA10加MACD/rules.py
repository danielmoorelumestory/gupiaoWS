"""User-confirmed state exit, with the prior frozen portfolio ledger.

Entry: V crosses30 up and C>MA10. Exit: fresh MACD death-cross and
(C<MA10 or current V<70 after this holding has observed V>=70).
"""
from decimal import Decimal, localcontext
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent / "底部回升结合MA10"
PROTOCOL = json.loads((ROOT / "protocol.json").read_text())


def load_frozen(name, filename):
    path = PREVIOUS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # The frozen runner imports the frozen strategy by its original name.
    sys.path.insert(0, str(PREVIOUS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(PREVIOUS))
    return module


ledger = load_frozen("_frozen_ma10_ledger", "strategy.py")
helpers = load_frozen("_frozen_ma10_runner", "run_backtest.py")
STRATEGIES = ("MACD_STATE", "OLD_SAME", "OLD_WAIT", "MA10_ONLY", "BUY_HOLD")
BASE_MAP = {"OLD_SAME": "COMBO_SAME", "OLD_WAIT": "COMBO_WAIT",
            "MA10_ONLY": "MA10_ONLY", "BUY_HOLD": "BUY_HOLD"}


def verify_dependencies():
    for name, key in (("strategy.py", "frozen_engine_sha256"),
                      ("run_backtest.py", "frozen_runner_sha256"),
                      ("protocol.json", "frozen_previous_protocol_sha256")):
        assert hashlib.sha256((PREVIOUS / name).read_bytes()).hexdigest() == PROTOCOL[key]


def features(rows):
    base = ledger.features(rows)
    with localcontext() as context:
        context.prec = 40
        fast, slow, signal, previous_dif, previous_dea = None, None, None, None, None
        for r, f in zip(rows, base):
            close = Decimal(r["adjusted_close"])
            fast = close if fast is None else (2*close+11*fast)/13
            slow = close if slow is None else (2*close+25*slow)/27
            dif = fast-slow
            dea = dif if signal is None else (2*dif+8*signal)/10
            dead = previous_dif is not None and previous_dif >= previous_dea and dif < dea
            f.update(dif=str(dif), dea=str(dea), macd_histogram=str(2*(dif-dea)),
                     death_cross=dead, bearish=dif < dea)
            signal, previous_dif, previous_dea = dea, dif, dea
    return base


def plan(rows, feat, first, last):
    """Generate state-dependent sell flags, independent of price fills/fees.

    The frozen positive-volume input makes next-row scheduling deterministic.
    The ledger will check that its actual generated orders match this plan.
    """
    indices = [i for i, r in enumerate(rows) if first <= r["date"] <= last and i >= 13]
    held, pending, high_seen, top_date, down_date = False, None, False, "", ""
    trace, orders = {}, []
    for i in indices:
        r, f = rows[i], feat[i]
        assert float(r["volume"]) > 0
        if pending == "buy":
            held, high_seen, top_date, down_date = True, False, "", ""
        elif pending == "sell":
            held, high_seen, top_date, down_date = False, False, "", ""
        pending = None
        v = f["value"]
        previous = feat[i-1]["value"] if i else None
        if held:
            if v is not None and v >= 70:
                high_seen, top_date = True, r["date"]
            if high_seen and previous is not None and previous >= 70 and v is not None and v < 70:
                down_date = r["date"]
        price_branch = held and f["below_ma"]
        top_branch = held and high_seen and v is not None and v < 70
        sell = bool(held and f["death_cross"] and (price_branch or top_branch))
        trace[i] = {"held": held, "high_seen": high_seen, "top_date": top_date,
                    "down70_date": down_date, "price_branch": bool(price_branch),
                    "top_branch": bool(top_branch), "sell": sell}
        if i == indices[-1]:
            continue
        if sell:
            pending = "sell"
        elif not held and previous is not None and v is not None and previous < 30 <= v and f["above_ma"]:
            pending = "buy"
        if pending:
            orders.append({"signal_index": i, "signal_date": r["date"], "action": pending})
    return trace, orders


def simulate(rows, feat, strategy, first, last, cost_bps=10, liquidate_end=True):
    if strategy == "MACD_STATE":
        trace, expected_orders = plan(rows, feat, first, last)
        # Change only the sell flags. The old COMBO_SAME entry and complete
        # share/coupon/fee ledger remain the previously verified implementation.
        adapted = [{**f, "below_ma": trace.get(i, {}).get("sell", False)}
                   for i, f in enumerate(feat)]
        result = ledger.simulate(rows, adapted, "COMBO_SAME", first, last, cost_bps, liquidate_end)
        assert result["orders"] == expected_orders
    else:
        trace = {}
        result = ledger.simulate(rows, feat, BASE_MAP[strategy], first, last, cost_bps, liquidate_end)
    for t in result["trades"]:
        i = t["entry_signal_index"]
        exit_i = t["exit_signal_index"]
        f = feat[exit_i] if exit_i is not None else None
        state = trace.get(exit_i, {})
        t.update(entry_signal_value=feat[i]["value"], entry_signal_above_ma=feat[i]["above_ma"],
                 exit_signal_value=f["value"] if f else "",
                 exit_dif=f["dif"] if f else "", exit_dea=f["dea"] if f else "",
                 exit_fresh_death=f["death_cross"] if f else "",
                 exit_price_below_ma=f["below_ma"] if f else "",
                 exit_top_branch=state.get("top_branch", ""),
                 held_last_top_date=state.get("top_date", ""),
                 held_last_down70_date=state.get("down70_date", ""))
    result["trace"] = trace
    return result
