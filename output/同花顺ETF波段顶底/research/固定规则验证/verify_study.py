"""离线核验输入哈希、信号、时点、持仓去重，以及独立逐日份额/现金账本。"""
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json

ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise SystemExit("核验失败：" + message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    summary = json.loads((ROOT / "results/summary.json").read_text())
    audit = json.loads((ROOT / "data_audit.json").read_text())
    for name, key in [("protocol.json", "protocol_sha256"), ("data_audit.json", "audit_sha256"),
                      ("analysis_design.json", "analysis_design_sha256")]:
        require(digest(ROOT/name) == summary[key], f"{name}已改变")
    for name, sha in audit["raw_file_sha256"].items():
        require(digest(ROOT/name) == sha, f"原始响应{name}已改变")
    data, prices, positions = {}, {}, {}
    for source in audit["symbols"]:
        if source["status"] != "eligible":
            continue
        path = ROOT / source["normalized_file"]
        require(digest(path) == source["normalized_sha256"], f"规范数据{source['code']}已改变")
        rows = list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))
        data[source["code"]] = rows
        prices[source["code"]] = [Fraction(r["adjusted_close"]) for r in rows]
        positions[source["code"]] = {r["date"]: i for i, r in enumerate(rows)}
    events = list(csv.DictReader(io.StringIO(gzip.decompress((ROOT / "results/events.csv.gz").read_bytes()).decode())))
    grouped = defaultdict(list)
    max_return_error = max_mae_error = 0.0

    def exact_value(c, index):
        changes = [c[i]-c[i-1] for i in range(index-12, index+1)]
        a = sum(abs(x) for x in changes)
        return 100*sum(max(x, 0) for x in changes)/a if a else None

    for event in events:
        code, rule = event["code"], event["rule"]
        rows, c = data[code], prices[code]
        signal = positions[code][event["signal_date"]]
        entry, exit_ = int(event["entry_index"]), int(event["exit_index"])
        horizon = int(event["horizon"])
        require(entry == signal+1 and exit_ == signal+horizon, "成交时点或持有期错位")
        require(rows[entry]["date"] == event["entry_date"] and rows[exit_]["date"] == event["exit_date"], "成交日期不符")
        require(rows[exit_]["date"] <= "2026-11-10", "使用了截止日后行情")
        previous, current = exact_value(c, signal-1), exact_value(c, signal)
        require(previous is not None and current is not None, "信号窗口无效")
        valid = (previous >= 30 > current if rule == "A" else
                 previous < 30 <= current and (rule == "B" or c[signal] > c[signal-1]))
        require(valid, f"{code} {event['signal_date']}信号不符")
        if event["segment"] == "development":
            require(event["signal_date"] < "2021-01-01" and event["exit_date"] < "2021-01-01", "开发段跨界")
        else:
            require(event["signal_date"] >= "2021-01-01", "留出段跨界")
        # 独立账本：初始一元买份额，逐日变更份额并累加现金；不直接用端点公式。
        shares = 1/float(rows[entry]["open"])
        cash, low_equity = 0.0, 1.0
        for j in range(entry, exit_+1):
            if j > entry:
                ratio = float(rows[j]["share_factor"])/float(rows[j-1]["share_factor"])
                shares *= ratio
                cash += shares/float(rows[j]["share_factor"])*(float(rows[j]["cumulative_cash"])-float(rows[j-1]["cumulative_cash"]))
            low_equity = min(low_equity, shares*float(rows[j]["low"])+cash)
        total = shares*float(rows[exit_]["close"])+cash
        error = abs((total-1)-float(event["gross_return"]))
        mae_error = abs((low_equity-1)-float(event["mae_gross"]))
        max_return_error, max_mae_error = max(max_return_error, error), max(max_mae_error, mae_error)
        require(error < 1e-10 and mae_error < 1e-10, "独立账本收益或MAE不符")
        grouped[(code, rule, horizon, event["segment"])].append((entry, exit_))
    for key, windows in grouped.items():
        ordered = sorted(windows)
        require(all(b[0] > a[1] for a, b in zip(ordered, ordered[1:])), f"{key}持有窗口重叠")
    output = {"status": "passed", "raw_inputs_hashed": len(audit["raw_file_sha256"]),
              "eligible_etfs": len(data), "events_verified": len(events),
              "max_independent_return_error": max_return_error,
              "max_independent_mae_error": max_mae_error,
              "checked": ["input hashes", "exact Fraction signal", "next-open execution", "holding horizon",
                          "split boundary purge", "no per-rule holding overlap", "daily share/cash ledger"]}
    (ROOT / "results/verification.json").write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
