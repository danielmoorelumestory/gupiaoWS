"""按已锁定方案运行事件研究；不寻优、不生成真实下单指令。标准库。"""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json
import math
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2] / "布鲁斯的金融宝藏/replica"))
from bruce_replica.etf_band import etf_band

PROTOCOL = json.loads((ROOT / "protocol.json").read_text())
DESIGN = json.loads((ROOT / "analysis_design.json").read_text())
RULES = ("A", "B", "B_plus")


def signals(prices):
    values = etf_band(prices, PROTOCOL["formula_period"])
    flags = []
    for i, value in enumerate(values):
        previous = values[i-1] if i else None
        valid = value is not None and previous is not None
        up = bool(valid and previous < 30 <= value)
        flags.append({"A": bool(valid and previous >= 30 > value), "B": up,
                      "B_plus": up and float(prices[i]) > float(prices[i-1])})
    return values, flags


def segment(signal_date, entry_date, exit_date):
    split = PROTOCOL["split_date"]
    if signal_date < split and exit_date < split:
        return "development"
    if signal_date >= split and entry_date >= split and exit_date >= split:
        return "historical_holdout"
    return None


def opportunity(rows, signal_i, horizon):
    """下一交易行开盘进，第h个持有交易行收盘出；现金权益不再投资。"""
    entry, exit_ = signal_i+1, signal_i+horizon
    if exit_ >= len(rows):
        return None
    a, b = rows[entry], rows[exit_]
    part = segment(rows[signal_i]["date"], a["date"], b["date"])
    if part is None or float(a["volume"]) <= 0 or float(b["volume"]) <= 0:
        return None
    scale = float(a["share_factor"])
    cash_base = float(a["cumulative_cash"])
    paid = float(a["open"])*scale
    value = (float(b["close"])*float(b["share_factor"])
             + float(b["cumulative_cash"])-cash_base)
    worst = min([1.0] + [(float(row["low"])*float(row["share_factor"])
                        + float(row["cumulative_cash"])-cash_base)/paid
                       for row in rows[entry:exit_+1]])-1
    return {"signal_date": rows[signal_i]["date"], "entry_date": a["date"],
            "exit_date": b["date"], "entry_index": entry, "exit_index": exit_,
            "segment": part, "horizon": horizon, "gross_return": value/paid-1,
            "mae_gross": worst,
            "price_up": float(rows[signal_i]["adjusted_close"]) > float(rows[signal_i-1]["adjusted_close"])}


def deduplicate(events):
    retained = []
    last_exit = -1
    for event in events:
        if event["entry_index"] > last_exit:
            retained.append(event)
            last_exit = event["exit_index"]
    return retained


def average(values):
    return statistics.fmean(values) if values else None


def summarize(events, baseline, cost_bps):
    net = [e["gross_return"]-cost_bps/10000 for e in events]
    return {"events": len(net), "mean_net": average(net),
            "median_net": statistics.median(net) if net else None,
            "win_rate_net": sum(v > 0 for v in net)/len(net) if net else None,
            "baseline_gross": baseline,
            "mean_net_excess": average(net)-baseline if net and baseline is not None else None,
            "mean_mae_gross": average([e["mae_gross"] for e in events]),
            "worst_mae_gross": min((e["mae_gross"] for e in events), default=None)}


def bootstrap_primary(events, common, dates):
    """按固定20交易日日期块重采样，同期ETF和两规则一起取样。"""
    settings = DESIGN["bootstrap"]
    date_block = {d: i//settings["block_sessions"] for i, d in enumerate(dates)}
    nblocks = max(date_block.values())+1 if date_block else 0
    sums = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    for event in events:
        if (event["segment"] != "historical_holdout" or event["horizon"] != 10
                or event["rule"] not in ("B", "B_plus") or event["code"] not in common):
            continue
        cell = sums[(event["code"], event["rule"])][date_block[event["signal_date"]]]
        cell[0] += event["gross_return"]
        cell[1] += 1
    rng = random.Random(settings["seed"])
    draws = []
    for _ in range(settings["replicates"]):
        weights = Counter(rng.randrange(nblocks) for _ in range(nblocks)) if nblocks else {}
        differences = []
        for code in common:
            means = []
            for rule in ("B", "B_plus"):
                numerator = denominator = 0
                for block, (total, count) in sums[(code, rule)].items():
                    numerator += weights.get(block, 0)*total
                    denominator += weights.get(block, 0)*count
                if not denominator:
                    break
                means.append(numerator/denominator)
            if len(means) != 2:
                break
            differences.append(means[1]-means[0])
        if common and len(differences) == len(common):
            draws.append(statistics.fmean(differences))
    draws.sort()

    def quantile(p):
        if not draws:
            return None
        pos = p*(len(draws)-1)
        lo, hi = math.floor(pos), math.ceil(pos)
        return draws[lo]*(hi-pos)+draws[hi]*(pos-lo) if lo != hi else draws[lo]

    return {**settings, "blocks": nblocks, "common_etfs": len(common), "valid_draws": len(draws),
            "ci_low": quantile(0.025), "ci_high": quantile(0.975),
            "scope": "historical descriptive uncertainty, not confirmation on unseen forward data"}


def save_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    audit = json.loads((ROOT / "data_audit.json").read_text())
    eligible = [s for s in audit["symbols"] if s["status"] == "eligible"]
    metrics, events, filtered, baselines, all_dates = [], [], [], {}, set()
    coverage = []
    for source in eligible:
        path = ROOT / source["normalized_file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["normalized_sha256"]:
            raise ValueError(f"输入校验失败：{path}")
        rows = list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))
        code = source["code"]
        values, flags = signals([r["adjusted_close"] for r in rows])
        all_dates.update(r["date"] for r in rows if r["date"] >= PROTOCOL["split_date"])
        coverage.append({"code": code, "label": source["label"], "rows": len(rows),
                         "first": rows[0]["date"], "last": rows[-1]["date"],
                         "valid_values": sum(x is not None for x in values)})
        for horizon in PROTOCOL["holding_sessions"]:
            possible = []
            for i in range(PROTOCOL["formula_period"]+1, len(rows)-horizon):
                if values[i] is None or values[i-1] is None:
                    continue
                event = opportunity(rows, i, horizon)
                if event is not None:
                    possible.append((i, {**event, "code": code, "label": source["label"]}))
            for part in ("development", "historical_holdout"):
                candidates = [(i, e) for i, e in possible if e["segment"] == part]
                baseline = average([e["gross_return"] for _, e in candidates])
                baselines[(code, horizon, part)] = baseline
                retained = {}
                for rule in RULES:
                    retained[rule] = deduplicate([e for i, e in candidates if flags[i][rule]])
                    events.extend({**e, "rule": rule} for e in retained[rule])
                    for cost in PROTOCOL["round_trip_cost_bps"]:
                        metrics.append({"code": code, "label": source["label"], "segment": part,
                                        "horizon": horizon, "cost_bps": cost, "rule": rule,
                                        "baseline_opportunities": len(candidates),
                                        **summarize(retained[rule], baseline, cost)})
                if horizon == 10:
                    b_events = retained["B"]
                    kept = [e for e in b_events if e["price_up"]]
                    excluded = [e for e in b_events if not e["price_up"]]
                    filtered.append({"code": code, "label": source["label"], "segment": part,
                                     "B_events": len(b_events), "kept_price_up": len(kept),
                                     "excluded_nonup": len(excluded),
                                     "kept_mean_gross": average([e["gross_return"] for e in kept]),
                                     "excluded_mean_gross": average([e["gross_return"] for e in excluded])})
    primary = [m for m in metrics if m["segment"] == "historical_holdout"
               and m["horizon"] == 10 and m["cost_bps"] == 10]
    comparisons = []
    for code in [s["code"] for s in eligible]:
        by_rule = {m["rule"]: m for m in primary if m["code"] == code}
        if all(by_rule[r]["events"] for r in ("B", "B_plus")):
            b, bp = by_rule["B"], by_rule["B_plus"]
            comparisons.append({"code": code, "label": b["label"], "B_events": b["events"],
                                "B_plus_events": bp["events"], "B_mean_net": b["mean_net"],
                                "B_plus_mean_net": bp["mean_net"],
                                "delta_mean_net": bp["mean_net"]-b["mean_net"],
                                "B_mean_net_excess": b["mean_net_excess"],
                                "B_plus_mean_net_excess": bp["mean_net_excess"]})
    common = [c["code"] for c in comparisons]
    bootstrap = bootstrap_primary(events, common, sorted(all_dates))
    aggregate = []
    common_aggregate = []
    for part in ("development", "historical_holdout"):
        for horizon in PROTOCOL["holding_sessions"]:
            for cost in PROTOCOL["round_trip_cost_bps"]:
                stratum = [m for m in metrics if m["segment"] == part and m["horizon"] == horizon
                           and m["cost_bps"] == cost]
                common_codes = [s["code"] for s in eligible if all(
                    any(m["code"] == s["code"] and m["rule"] == r and m["events"] for m in stratum)
                    for r in RULES)]
                for rule in RULES:
                    group = [m for m in metrics if m["segment"] == part and m["horizon"] == horizon
                             and m["cost_bps"] == cost and m["rule"] == rule and m["events"]]
                    aggregate.append({"segment": part, "horizon": horizon, "cost_bps": cost, "rule": rule,
                                      "etfs_with_events": len(group), "events": sum(m["events"] for m in group),
                                      "equal_weight_mean_net": average([m["mean_net"] for m in group]),
                                      "equal_weight_mean_net_excess": average([m["mean_net_excess"] for m in group]),
                                      "equal_weight_win_rate": average([m["win_rate_net"] for m in group]),
                                      "equal_weight_mean_mae": average([m["mean_mae_gross"] for m in group])})
                    same_group = [m for m in group if m["code"] in common_codes]
                    common_aggregate.append({"segment": part, "horizon": horizon, "cost_bps": cost,
                                             "rule": rule, "common_etfs": len(common_codes),
                                             "events": sum(m["events"] for m in same_group),
                                             "equal_weight_mean_net": average([m["mean_net"] for m in same_group]),
                                             "equal_weight_mean_net_excess": average([m["mean_net_excess"] for m in same_group]),
                                             "equal_weight_win_rate": average([m["win_rate_net"] for m in same_group]),
                                             "equal_weight_mean_mae": average([m["mean_mae_gross"] for m in same_group])})
    (ROOT / "results").mkdir(exist_ok=True)
    save_csv(ROOT / "results/per_etf.csv", metrics)
    save_csv(ROOT / "results/aggregate.csv", aggregate)
    save_csv(ROOT / "results/aggregate_common_all3.csv", common_aggregate)
    save_csv(ROOT / "results/primary_B_plus_vs_B.csv", comparisons)
    save_csv(ROOT / "results/paired_filter_diagnostic.csv", filtered)
    event_stream = io.StringIO(newline="")
    if events:
        writer = csv.DictWriter(event_stream, fieldnames=list(events[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(events)
    (ROOT / "results/events.csv.gz").write_bytes(gzip.compress(event_stream.getvalue().encode(), mtime=0))
    mean_delta = average([c["delta_mean_net"] for c in comparisons])
    positive = sum(c["delta_mean_net"] > 0 for c in comparisons)
    historical_support = bool(mean_delta is not None and mean_delta > 0
                              and bootstrap["ci_low"] is not None and bootstrap["ci_low"] > 0
                              and positive > len(common)/2 and len(eligible) >= 8)
    output = {"protocol_sha256": hashlib.sha256((ROOT / "protocol.json").read_bytes()).hexdigest(),
              "audit_sha256": hashlib.sha256((ROOT / "data_audit.json").read_bytes()).hexdigest(),
              "analysis_design_sha256": hashlib.sha256((ROOT / "analysis_design.json").read_bytes()).hexdigest(),
              "planned_etfs": len(PROTOCOL["panel"]), "eligible_etfs": len(eligible),
              "excluded": [r for r in audit["symbols"] if r["status"] != "eligible"],
              "coverage": coverage, "primary_comparisons": comparisons,
              "primary_equal_weight_delta": mean_delta, "primary_positive_etfs": positive,
              "primary_common_etfs": len(common), "bootstrap": bootstrap,
              "historical_support_under_prespecified_criterion": historical_support,
              "confirmed_out_of_sample_improvement": False,
              "limitations": ["retrospective holdout; known recent market, not truly unseen",
                              "current-survivor fixed panel; no delisted ETFs",
                              "event study, not portfolio compounded return",
                              "cost scenarios and daily theoretical fills, not broker quotes",
                              "cash dividend economic entitlement at ex-date, not payment-date ledger",
                              "signal adjustment not verified against each ETF's App qfq"]}
    (ROOT / "results/summary.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k not in ("excluded", "coverage", "primary_comparisons")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
