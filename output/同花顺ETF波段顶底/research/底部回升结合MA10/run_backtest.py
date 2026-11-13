"""Offline fixed protocol run. No parameter search or data downloads."""
from collections import defaultdict
from datetime import date
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json
import math
import random
import statistics

from strategy import ROOT, STRATEGIES, features, simulate, summary

SOURCE = ROOT.parent / "固定规则验证"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs():
    protocol = json.loads((ROOT / "protocol.json").read_text())
    assert digest(SOURCE / "data_audit.json") == protocol["inputs"]["audit_sha256"]
    panel = {}
    for item in protocol["inputs"]["eligible_symbols"]:
        path = SOURCE / item["normalized_file"]
        assert digest(path) == item["normalized_sha256"], str(path)
        rows = list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))
        assert all(float(r["volume"]) > 0 for r in rows), "zero-volume input requires review"
        panel[item["code"]] = (item, rows, features(rows))
    return protocol, panel


def save_csv(path, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    data = stream.getvalue().encode()
    path.write_bytes(gzip.compress(data, mtime=0) if path.suffix == ".gz" else data)


def aggregate(accounts):
    dates = sorted({r["date"] for account in accounts for r in account["nav"]})
    maps = [{r["date"]: r for r in a["nav"]} for a in accounts]
    current = [{"nav": 1.0, "capital_exposure": 0.0, "held_session": 0,
                "dividend_reserve": 0.0} for _ in maps]
    output = []
    for day in dates:
        for j, mapping in enumerate(maps):
            if day in mapping:
                current[j] = mapping[day]
        total = sum(r["nav"] for r in current)
        output.append({"date": day, "nav": total/len(current),
                       "held_session": statistics.fmean(r["held_session"] for r in current),
                       "capital_exposure": sum(r["nav"]*r["capital_exposure"] for r in current)/total,
                       "dividend_reserve": statistics.fmean(r["dividend_reserve"] for r in current)})
    trades = [t for a in accounts for t in a["trades"]]
    metric = summary(output, trades, statistics.fmean(a["metrics"]["fees_initial_capital"] for a in accounts))
    # Counts refer to total trades in the nine independent accounts.
    return {"nav": output, "metrics": metric}


def bootstrap(nav_a, nav_b, settings):
    assert [r["date"] for r in nav_a] == [r["date"] for r in nav_b]
    pairs = [(math.log(nav_a[i]["nav"]/nav_a[i-1]["nav"]),
              math.log(nav_b[i]["nav"]/nav_b[i-1]["nav"])) for i in range(1, len(nav_a))]
    size = settings["block_sessions"]
    blocks = [(sum(p[0] for p in pairs[i:i+size]),
               sum(p[1] for p in pairs[i:i+size]), len(pairs[i:i+size]))
              for i in range(0, len(pairs), size)]
    years = (date.fromisoformat(nav_a[-1]["date"])-date.fromisoformat(nav_a[0]["date"])).days/365.25
    annual_sessions = len(pairs)/years
    rng, draws = random.Random(settings["seed"]), []
    for _ in range(settings["replicates"]):
        chosen = [blocks[rng.randrange(len(blocks))] for _ in blocks]
        a, b, count = map(sum, zip(*chosen))
        draws.append(math.expm1(a/count*annual_sessions)-math.expm1(b/count*annual_sessions))
    draws.sort()
    def quantile(p):
        position = p*(len(draws)-1)
        low, high = math.floor(position), math.ceil(position)
        return draws[low]+(draws[high]-draws[low])*(position-low)
    return {**settings, "blocks": len(blocks), "valid_draws": len(draws),
            "cagr_difference_ci_low": quantile(.025),
            "cagr_difference_ci_high": quantile(.975),
            "scope": "paired realized aggregate-return blocks; retrospective uncertainty only"}


def main():
    protocol, panel = load_inputs()
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    metrics, trades, navs = [], [], []
    primary = defaultdict(list)
    primary_cost = protocol["primary_cost_bps_round_trip"]
    for code, (item, rows, feat) in panel.items():
        for segment, (first, last) in protocol["segments"].items():
            for cost in protocol["cost_bps_round_trip"]:
                for strategy in STRATEGIES:
                    meta = {"code": code, "label": item["label"], "segment": segment,
                            "strategy": strategy, "cost_bps_round_trip": cost}
                    result = simulate(rows, feat, strategy, first, last, cost)
                    metrics.append({**meta, **result["metrics"]})
                    trades.extend({**meta, **t} for t in result["trades"])
                    if cost == primary_cost:
                        navs.extend({**meta, **n} for n in result["nav"])
                    if segment == "historical_holdout":
                        primary[(strategy, cost)].append(result)
    aggregates = {key: aggregate(accounts) for key, accounts in primary.items()}
    aggregate_metrics, aggregate_nav, yearly = [], [], []
    for (strategy, cost), result in aggregates.items():
        aggregate_metrics.append({"strategy": strategy, "cost_bps_round_trip": cost,
                                  **result["metrics"]})
        aggregate_nav.extend({"strategy": strategy, "cost_bps_round_trip": cost, **n}
                             for n in result["nav"])
        if cost == primary_cost:
            previous, by_year = 1.0, defaultdict(list)
            for n in result["nav"]:
                by_year[n["date"][:4]].append(n)
            for year, observations in by_year.items():
                yearly.append({"year": year, "strategy": strategy,
                               "net_return": observations[-1]["nav"]/previous-1,
                               "last": observations[-1]["date"]})
                previous = observations[-1]["nav"]
    boot = bootstrap(aggregates[("COMBO_WAIT", primary_cost)]["nav"],
                     aggregates[("MA10_ONLY", primary_cost)]["nav"], protocol["bootstrap"])
    positive = sum(next(m for m in metrics if m["code"] == code and m["segment"] == "historical_holdout"
                        and m["strategy"] == "COMBO_WAIT" and m["cost_bps_round_trip"] == primary_cost)["cagr"]
                   > next(m for m in metrics if m["code"] == code and m["segment"] == "historical_holdout"
                          and m["strategy"] == "MA10_ONLY" and m["cost_bps_round_trip"] == primary_cost)["cagr"]
                   for code in panel)
    difference = (aggregates[("COMBO_WAIT", primary_cost)]["metrics"]["cagr"]
                  - aggregates[("MA10_ONLY", primary_cost)]["metrics"]["cagr"])
    result_summary = {"protocol_sha256": digest(ROOT / "protocol.json"),
                      "input_audit_sha256": digest(SOURCE / "data_audit.json"),
                      "primary_period": protocol["segments"]["historical_holdout"],
                      "primary_cost_bps_round_trip": primary_cost,
                      "eligible_etfs": len(panel), "positive_etfs_combo_minus_ma": positive,
                      "primary_cagr_difference": difference, "bootstrap": boot,
                      "historical_return_support": (difference > 0 and boot["cagr_difference_ci_low"] > 0
                                                     and positive > len(panel)/2),
                      "retrospective": True, "parameter_search": False}
    save_csv(out / "metrics.csv", metrics)
    save_csv(out / "trades.csv.gz", trades)
    save_csv(out / "daily_nav_cost10.csv.gz", navs)
    save_csv(out / "aggregate_metrics.csv", aggregate_metrics)
    save_csv(out / "aggregate_nav.csv.gz", aggregate_nav)
    save_csv(out / "yearly_cost10.csv", yearly)
    (out / "summary.json").write_text(json.dumps(result_summary, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"metric_rows": len(metrics), "trades": len(trades),
                      "saved": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
