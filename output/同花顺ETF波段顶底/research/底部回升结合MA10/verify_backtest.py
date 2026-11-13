"""Independent Fraction signals and closed-form shares/coupon ledger.

Does not call simulate/summary/features for its reference calculations.
Verifies every saved trade and every primary-cost daily NAV, plus all final
account metrics and portfolio sums. Signal intervals are found by searching
the next eligible entry and first MA break rather than replaying engine orders.
"""
from datetime import date
from fractions import Fraction as F
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json
import math

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "固定规则验证"


def read_csv(path):
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    return list(csv.DictReader(io.StringIO(data.decode())))


def independent_signals(rows):
    prices = [F(r["adjusted_close"]) for r in rows]
    v, above, below = [], [], []
    for i, price in enumerate(prices):
        if i < 13:
            v.append(None)
        else:
            changes = [prices[j]-prices[j-1] for j in range(i-12, i+1)]
            absolute = sum(abs(x) for x in changes)
            v.append(100*sum(max(0, x) for x in changes)/absolute if absolute else None)
        mean = sum(prices[i-9:i+1])/10 if i >= 9 else price
        above.append(price > mean)
        below.append(price < mean)
    return v, above, below


def intervals(rows, signals, strategy, first, last):
    v, above, below = signals
    valid = [i for i, r in enumerate(rows) if first <= r["date"] <= last and i >= 13]
    start, end = valid[0], valid[-1]
    output, cursor = [], start
    while cursor < end:
        low_seen, found = False, None
        for i in range(cursor, end):
            if strategy == "BUY_HOLD":
                ready = i == start
            elif strategy == "MA10_ONLY":
                ready = above[i]
            else:
                low_seen |= ((v[i] is not None and v[i] < 30)
                             or (v[i-1] is not None and v[i-1] < 30))
                recovers = v[i] is not None and v[i] >= 30
                ready = above[i] and recovers and (low_seen if strategy == "COMBO_WAIT"
                                                   else v[i-1] is not None and v[i-1] < 30)
            if ready:
                found = i
                break
        if found is None:
            break
        entry = found+1
        breaks = ([i for i in range(entry, end) if below[i]] if strategy != "BUY_HOLD" else [])
        exit_ = breaks[0]+1 if breaks else end
        output.append((found, entry, breaks[0] if breaks else None, exit_, not breaks))
        if not breaks:
            break
        cursor = exit_
    return valid, output


def main():
    protocol = json.loads((ROOT / "protocol.json").read_text())
    saved_summary = json.loads((ROOT / "results/summary.json").read_text())
    assert hashlib.sha256((ROOT / "protocol.json").read_bytes()).hexdigest() == saved_summary["protocol_sha256"]
    all_trades = read_csv(ROOT / "results/trades.csv.gz")
    metrics = read_csv(ROOT / "results/metrics.csv")
    saved_nav = read_csv(ROOT / "results/daily_nav_cost10.csv.gz")
    def key(r):
        return r["code"], r["segment"], r["strategy"], int(r["cost_bps_round_trip"])
    trade_map, nav_map = {}, {}
    for t in all_trades:
        trade_map.setdefault(key(t), []).append(t)
    for n in saved_nav:
        nav_map.setdefault(key(n), []).append(n)
    max_error, nav_count, trade_count, final_navs = 0.0, 0, 0, {}
    def close(a, b):
        nonlocal max_error
        error = abs(float(a)-float(b))
        max_error = max(max_error, error)
        assert error <= 2e-11*max(1, abs(float(b))), (a, b, error)
    for source in protocol["inputs"]["eligible_symbols"]:
        path = SOURCE / source["normalized_file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["normalized_sha256"]
        rows = read_csv(path)
        sig = independent_signals(rows)
        for metric in [m for m in metrics if m["code"] == source["code"]]:
            k = key(metric)
            cost = k[3]
            side = F(cost, 20000)
            valid, spans = intervals(rows, sig, k[2], *protocol["segments"][k[1]])
            recorded = trade_map.get(k, [])
            assert len(recorded) == len(spans), (k, len(recorded), len(spans))
            cash, reserve, components = F(1), F(0), []
            for span, trade in zip(spans, recorded):
                signal, enter, exit_signal, exit_, forced = span
                assert int(trade["entry_signal_index"]) == signal
                assert int(trade["entry_index"]) == enter
                assert int(trade["exit_index"]) == exit_
                assert trade["exit_signal_index"] == (str(exit_signal) if exit_signal is not None else "")
                assert trade["forced_end"] == str(forced)
                a, b = rows[enter], rows[exit_]
                price = F(b["close"] if forced else b["open"])
                quantity = cash/(F(a["open"])*(1+side))
                base_shares = quantity/F(a["share_factor"])
                coupon = base_shares*(F(b["cumulative_cash"])-F(a["cumulative_cash"]))
                sale = base_shares*F(b["share_factor"])*price*(1-side)
                close(trade["entry_cash"], cash)
                close(trade["entry_shares"], quantity)
                close(trade["exit_cash"], sale)
                close(trade["earned_dividends"], coupon)
                close(trade["net_total_return"], (sale+coupon)/cash-1)
                components.append((span, cash, reserve, base_shares, sale, coupon))
                cash, reserve = sale, reserve+coupon
                trade_count += 1
            close(metric["final_nav"], cash+reserve)
            close(metric["dividend_reserve"], reserve)
            assert int(metric["natural_exits"]) == sum(not s[-1] for s in spans)
            days = (date.fromisoformat(rows[valid[-1]]["date"])-date.fromisoformat(rows[valid[0]]["date"])).days
            if days >= 365:
                close(metric["cagr"], math.expm1(math.log(float(cash+reserve))/(days/365.25)))
            else:
                assert metric["cagr"] == ""
            if cost != 10:
                continue
            recorded_nav = nav_map[k]
            assert len(recorded_nav) == len(valid)
            peak, worst, ci = 1.0, 0.0, 0
            for i, n in zip(valid, recorded_nav):
                cap, div, market = F(1), F(0), F(0)
                for span, before_cap, before_div, base_shares, sale, coupon in components:
                    _, enter, _, exit_, forced = span
                    if i < enter:
                        break
                    if i >= exit_:
                        cap, div = sale, before_div+coupon
                    else:
                        cap = F(0)
                        div = before_div+base_shares*(F(rows[i]["cumulative_cash"])-F(rows[enter]["cumulative_cash"]))
                        market = base_shares*F(rows[i]["share_factor"])*F(rows[i]["close"])
                        break
                value = cap+div+market
                close(n["nav"], value)
                assert n["date"] == rows[i]["date"]
                peak = max(peak, float(value))
                worst = min(worst, float(value)/peak-1)
                nav_count += 1
            close(metric["max_drawdown"], worst)
            if k[1] == "historical_holdout":
                final_navs[(k[2], k[3], k[0])] = float(cash+reserve)
    # Independently reconstruct each aggregate daily NAV as the equal-initial-
    # capital sum of saved account NAVs, carrying marks only across quote gaps.
    agg_nav = read_csv(ROOT / "results/aggregate_nav.csv.gz")
    aggregate_checks = 0
    for strategy in ("COMBO_WAIT", "MA10_ONLY", "BUY_HOLD", "COMBO_SAME"):
        series = [n for n in agg_nav if n["strategy"] == strategy and int(n["cost_bps_round_trip"]) == 10]
        maps = [{n["date"]: float(n["nav"]) for n in nav_map[(s["code"], "historical_holdout", strategy, 10)]}
                for s in protocol["inputs"]["eligible_symbols"]]
        held = [1.0]*len(maps)
        for n in series:
            held = [m.get(n["date"], old) for m, old in zip(maps, held)]
            close(n["nav"], sum(held)/len(held))
            aggregate_checks += 1
    report = {"status": "PASS", "independent": "Fraction signals, interval search, closed-form share/coupon ledger",
              "metrics_checked": len(metrics), "trades_checked": trade_count,
              "daily_account_nav_checked": nav_count, "aggregate_nav_checked": aggregate_checks,
              "max_absolute_numeric_error": max_error}
    (ROOT / "results/independent_verification.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
