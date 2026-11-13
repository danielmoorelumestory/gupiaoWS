"""Add only the user's V<=45 entry filter to the frozen MACD-state rule."""
from pathlib import Path
import hashlib
import importlib.util
import json

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent / "底部回升MA10加MACD"
PROTOCOL = json.loads((ROOT / "protocol.json").read_text())
spec = importlib.util.spec_from_file_location("_frozen_macd_state", PREVIOUS / "rules.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
helpers = base.helpers
features = base.features
STRATEGIES = ("MACD_CAP45", "MACD_STATE", "MA10_ONLY", "BUY_HOLD")


def verify_dependencies():
    for name, key in (("rules.py", "parent_rules_sha256"),
                      ("protocol.json", "parent_protocol_sha256"),
                      ("results/metrics.csv", "parent_metrics_sha256")):
        assert hashlib.sha256((PREVIOUS / name).read_bytes()).hexdigest() == PROTOCOL[key]
    base.verify_dependencies()


def cap_allowed(value):
    return value is not None and value <= PROTOCOL["entry_cap"]


def simulate(rows, feat, strategy, first, last, cost_bps=10, liquidate_end=True):
    if strategy not in STRATEGIES:
        raise ValueError(strategy)
    if strategy == "MACD_CAP45":
        # The shared engine uses above_ma only in its entry condition. Preserve
        # all V/MACD/MA-below values and the complete frozen sell/position ledger.
        entry_filtered = [{**f, "above_ma": f["above_ma"] and cap_allowed(f["value"])} for f in feat]
        result = base.simulate(rows, entry_filtered, "MACD_STATE", first, last, cost_bps, liquidate_end)
        assert all(cap_allowed(t["entry_signal_value"]) for t in result["trades"])
    else:
        result = base.simulate(rows, feat, strategy, first, last, cost_bps, liquidate_end)
    return result
