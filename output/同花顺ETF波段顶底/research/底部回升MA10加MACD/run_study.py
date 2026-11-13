"""Fixed five-strategy comparison; standard library, cached inputs only."""
from collections import defaultdict
from datetime import date
import json

from rules import ROOT, PROTOCOL, STRATEGIES, BASE_MAP, features, helpers, simulate, verify_dependencies


def main():
    verify_dependencies()
    old_protocol, panel = helpers.load_inputs()
    assert old_protocol["inputs"] == PROTOCOL["inputs"]
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    metrics, trades, navs, feature_rows, diagnostics = [], [], [], [], []
    primary = defaultdict(list)
    for code, (source, rows, _) in panel.items():
        feat = features(rows)
        feature_rows.extend({"code": code, "date": r["date"], "row_index": i, **f}
                            for i, (r, f) in enumerate(zip(rows, feat)))
        for segment, (first, last) in PROTOCOL["segments"].items():
            for cost in PROTOCOL["cost_bps_round_trip"]:
                for strategy in STRATEGIES:
                    meta = {"code": code, "label": source["label"], "segment": segment,
                            "strategy": strategy, "cost_bps_round_trip": cost}
                    result = simulate(rows, feat, strategy, first, last, cost)
                    metrics.append({**meta, **result["metrics"]})
                    trades.extend({**meta, **t} for t in result["trades"])
                    if cost == 10:
                        navs.extend({**meta, **n} for n in result["nav"])
                        if strategy == "MACD_STATE":
                            tr = list(result["trace"].values())
                            natural = [t for t in result["trades"] if not t["forced_end"]]
                            diagnostics.append({"code": code, "segment": segment,
                                "held_closes": sum(x["held"] for x in tr),
                                "below_ma_without_fresh_death_closes": sum(x["price_branch"] and not x["sell"] for x in tr),
                                "natural_price_only_exits": sum(t["exit_price_below_ma"] and not t["exit_top_branch"] for t in natural),
                                "natural_top_only_exits": sum(t["exit_top_branch"] and not t["exit_price_below_ma"] for t in natural),
                                "natural_both_exits": sum(t["exit_top_branch"] and t["exit_price_below_ma"] for t in natural)})
                    if segment == "historical_holdout":
                        primary[(strategy, cost)].append(result)
    aggregates = {k: helpers.aggregate(accounts) for k, accounts in primary.items()}
    aggregate_metrics, aggregate_nav, yearly = [], [], []
    for (strategy, cost), result in aggregates.items():
        aggregate_metrics.append({"strategy": strategy, "cost_bps_round_trip": cost, **result["metrics"]})
        aggregate_nav.extend({"strategy": strategy, "cost_bps_round_trip": cost, **n} for n in result["nav"])
        if cost == 10:
            previous, years = 1.0, defaultdict(list)
            for n in result["nav"]:
                years[n["date"][:4]].append(n)
            for year, ns in years.items():
                yearly.append({"year": year, "strategy": strategy,
                               "net_return": ns[-1]["nav"]/previous-1, "last": ns[-1]["date"]})
                previous = ns[-1]["nav"]
    comparisons = []
    for comparator in ("OLD_SAME", "OLD_WAIT", "MA10_ONLY", "BUY_HOLD"):
        boot = helpers.bootstrap(aggregates[("MACD_STATE", 10)]["nav"],
                                 aggregates[(comparator, 10)]["nav"], PROTOCOL["bootstrap"])
        positive = 0
        for code in panel:
            subset = [m for m in metrics if m["code"] == code and m["segment"] == "historical_holdout"
                      and m["cost_bps_round_trip"] == 10]
            positive += (next(m for m in subset if m["strategy"] == "MACD_STATE")["cagr"]
                         > next(m for m in subset if m["strategy"] == comparator)["cagr"])
        diff = aggregates[("MACD_STATE", 10)]["metrics"]["cagr"]-aggregates[(comparator, 10)]["metrics"]["cagr"]
        comparisons.append({"comparator": comparator, "primary": comparator == "OLD_SAME",
                            "cagr_difference": diff, "positive_etfs": positive, "bootstrap": boot,
                            "historical_return_support": diff > 0 and boot["cagr_difference_ci_low"] > 0 and positive > len(panel)/2})
    result_summary = {"protocol_sha256": helpers.digest(ROOT / "protocol.json"),
                      "audit_sha256": PROTOCOL["inputs"]["audit_sha256"],
                      "period": PROTOCOL["segments"]["historical_holdout"],
                      "primary_cost_bps_round_trip": 10, "eligible_etfs": len(panel),
                      "comparisons": comparisons, "retrospective": True, "parameter_search": False}
    for name, result in (("metrics.csv", metrics), ("trades.csv.gz", trades),
                         ("daily_nav_cost10.csv.gz", navs), ("features.csv.gz", feature_rows),
                         ("holding_diagnostics.csv", diagnostics), ("aggregate_metrics.csv", aggregate_metrics),
                         ("aggregate_nav.csv.gz", aggregate_nav), ("yearly_cost10.csv", yearly)):
        helpers.save_csv(out / name, result)
    (out / "summary.json").write_text(json.dumps(result_summary, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"metric_rows": len(metrics), "trade_records": len(trades), "saved": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
