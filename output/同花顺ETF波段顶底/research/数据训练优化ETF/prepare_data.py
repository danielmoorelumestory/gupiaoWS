"""Freeze cached OHLC plus independently fetched cumulative share/cash factors.

No strategy returns calculated here. Never choose corporate-action dates by
fitting price jumps. A factor applies on the first quote dated >= factor date.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import bisect
import argparse
import csv
import gzip
import hashlib
import io
import json
import urllib.request

ROOT = Path(__file__).resolve().parent
ORIGINAL_ROOT = ROOT
SOURCE = ROOT.parents[2] / "布鲁斯的金融宝藏/replica/data"
CUTOFF = "2026-11-10"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_factors(code):
    path = ROOT / f"data/raw/{code}-sina-hfq.js.gz"
    symbol = ("sh" if code.startswith("5") else "sz")+code
    url = f"https://finance.sina.com.cn/realstock/company/{symbol}/hfq.js"
    frozen_path = ORIGINAL_ROOT / f"data/raw/{code}-sina-hfq.js.gz"
    if not path.exists() and frozen_path.exists():
        path.write_bytes(frozen_path.read_bytes())
    if path.exists():
        body = gzip.decompress(path.read_bytes())
    else:
        error = None
        for _ in range(2):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"})
                with urllib.request.urlopen(req, timeout=18) as response:
                    body = response.read()
                path.write_bytes(gzip.compress(body, mtime=0))
                break
            except Exception as exc:
                error = exc
        else:
            raise RuntimeError(str(error))
    text = body.decode("gb18030", errors="replace")
    assert text.startswith(f"var {symbol}hfq="), "factor symbol mismatch"
    payload, _ = json.JSONDecoder().raw_decode(text.split("=", 1)[1])
    factors = []
    for row in sorted(payload["data"], key=lambda r: r["d"]):
        if row["d"] > CUTOFF:
            continue
        f, s, u = D(row["f"]), D(row["s"]), D(row["u"])
        assert f == 1 and s > 0 and u >= 0 and s.is_finite() and u.is_finite(), "unsupported factor"
        assert not factors or u >= factors[-1][2], "nonmonotone cash factor"
        factors.append((row["d"], s, u))
    assert factors
    return factors, url, path


def normalize_cash_factors(factors):
    """Provider u sums raw per-share payouts; ledger cash is per original unit.

    Convert first: K_t=sum((u_k-u_prev)*s_k). The existing ledger deliberately
    consumes K, not the provider's unweighted u. This also covers a payout on
    a split effective date, when the current share factor applies.
    """
    previous_u, capital_cash = D(0), D(0)
    result = []
    for day, shares, unweighted_u in factors:
        capital_cash += (unweighted_u-previous_u)*shares
        result.append((day, shares, capital_cash))
        previous_u = unweighted_u
    return result


def prepare(item):
    code = item["code"]
    raw_path, event_path = SOURCE/f"etf_{code}_raw.csv", SOURCE/f"etf_{code}_events.json"
    rows = [r for r in csv.DictReader(raw_path.open()) if r["date"] <= CUTOFF]
    assert rows and all(a["date"] < b["date"] for a, b in zip(rows, rows[1:])), "date order"
    fs, url, factor_path = get_factors(code)
    capital_factors = normalize_cash_factors(fs)
    factor_dates = [r[0] for r in fs]
    normalized, actions = [], []
    for i, r in enumerate(rows):
        o, h, low, close = [D(r[k]) for k in ("open", "high", "low", "close")]
        assert all(x.is_finite() and x > 0 for x in (o,h,low,close)) and low <= min(o,close) <= max(o,close) <= h
        k = bisect.bisect_right(factor_dates, r["date"])-1
        assert k >= 0, "missing starting factor"
        _, s, u = capital_factors[k]
        adjusted = close*s+u
        normalized.append({**r, "share_factor": str(s), "cumulative_cash": str(u), "adjusted_close": str(adjusted)})
        if i:
            previous = normalized[-2]
            old_s, old_u = D(previous["share_factor"]), D(previous["cumulative_cash"])
            if s != old_s or u != old_u:
                actions.append({"effective_quote": r["date"], "factor_date": factor_dates[k],
                                "share_ratio": str(s/old_s), "cash_per_old_share": str((u-old_u)/old_s),
                                "old_close": previous["close"], "new_open": r["open"]})
    # Price continuity is an audit flag only, never used to remap action dates.
    split_flags = []
    for a in actions:
        ratio = D(a["share_ratio"])
        if ratio != 1:
            gap = abs((D(a["new_open"])*ratio+D(a["cash_per_old_share"]))/D(a["old_close"])-1)
            if gap > D("0.08"):
                split_flags.append({**a, "absolute_action_adjusted_gap": str(gap)})
    hfq_path = SOURCE/f"etf_{code}_hfq.csv"
    raw_snapshot = ROOT/f"data/raw/{code}-raw-cache.csv.gz"
    raw_snapshot.write_bytes(gzip.compress(raw_path.read_bytes(), mtime=0))
    hfq_snapshot = ROOT/f"data/raw/{code}-hfq-cache.csv.gz"
    if hfq_path.exists():
        hfq_snapshot.write_bytes(gzip.compress(hfq_path.read_bytes(), mtime=0))
    crosscheck, mismatches = 0, []
    if hfq_path.exists():
        hmap = {r["date"]: r for r in csv.DictReader(hfq_path.open())}
        for r in normalized:
            if r["date"] not in hmap:
                continue
            vendor = D(hmap[r["date"]]["close"])
            difference = abs(vendor-D(r["adjusted_close"]))
            crosscheck += 1
            if difference > max(D("0.003"), abs(vendor)*D("0.001")):
                mismatches.append({"date": r["date"], "factor_price": r["adjusted_close"], "vendor": str(vendor)})
    status = "eligible"
    if split_flags or (crosscheck and len(mismatches) > .005*crosscheck):
        status = "quarantined_action_or_hfq_disagreement"
    out = ROOT/f"data/{code}.csv.gz"
    if status == "eligible":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(normalized[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(normalized)
        out.write_bytes(gzip.compress(stream.getvalue().encode(), mtime=0))
    return {**item, "status": status, "rows": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"],
            "normalized_file": str(out.relative_to(ROOT)) if status == "eligible" else None,
            "normalized_sha256": digest(out) if status == "eligible" else None,
            "cached_raw_file": str(raw_path), "cached_raw_sha256": digest(raw_path),
            "raw_snapshot_file":str(raw_snapshot.relative_to(ROOT)), "raw_snapshot_sha256":digest(raw_snapshot),
            "cached_events_sha256": digest(event_path), "cached_events_policy": "not used to map actions or delete dividends",
            "factor_source": url, "factor_file": str(factor_path.relative_to(ROOT)), "factor_sha256": digest(factor_path),
            "factor_records": [[d,str(s),str(u)] for d,s,u in fs],
            "capital_factor_records": [[d,str(s),str(u)] for d,s,u in capital_factors],
            "cash_semantics":"source u unweighted per-share; normalized cumulative_cash K=sum(delta_u*s_at_event)",
            "mapped_actions": actions,
            "action_gap_flags": split_flags, "hfq_crosschecked_rows": crosscheck,
            "hfq_sha256": digest(hfq_path) if hfq_path.exists() else None,
            "hfq_snapshot_file":str(hfq_snapshot.relative_to(ROOT)) if hfq_path.exists() else None,
            "hfq_snapshot_sha256":digest(hfq_snapshot) if hfq_path.exists() else None,
            "hfq_mismatches": mismatches, "volume": "not present; observed quote rows assumed executable"}


def main():
    global ROOT
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-root",type=Path,default=ORIGINAL_ROOT)
    args=parser.parse_args();ROOT=args.output_root.resolve()
    if ROOT==ORIGINAL_ROOT and (ROOT/"data_audit.json").exists():
        raise SystemExit("Frozen audit exists; use --output-root for a corrected version without overwriting the training archive")
    (ROOT/"data/raw").mkdir(parents=True, exist_ok=True)
    universe = json.loads((ORIGINAL_ROOT/"evidence/universe.json").read_text())
    eligible, excluded = [], []
    items = []
    for item in universe["etfs"]:
        if item["code"] == "511880":
            excluded.append({**item, "reason": "money ETF outside equity-swing training, no cached OHLC; fixed exclusion before returns"})
        else:
            items.append(item)
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(prepare, item): item for item in items}
        for future in as_completed(pending):
            item = pending[future]
            try:
                record = future.result()
            except Exception as exc:
                record = {**item, "status": "data_error", "error": f"{type(exc).__name__}: {exc}"}
            eligible.append(record)
            print(item["code"], record["status"], record.get("rows"), "hfq_errors",len(record.get("hfq_mismatches",[])),flush=True)
    audit = {"prepared_at_utc": datetime.now(timezone.utc).isoformat(), "universe_sha256":digest(ORIGINAL_ROOT/"evidence/universe.json"),
             "cutoff":CUTOFF, "policy":"raw + Sina exact-date factors; capital cash K=sum(delta_u*s_at_event), raw_close*s+K; no price-fitting or dividend deletion", 
             "eligible_rule":"no action-adjusted open gap>8%; if cached hfq exists, >0.5% price mismatches above max(.003,.1%) quarantines",
             "symbols":sorted(eligible,key=lambda x:x["code"]), "excluded_structural":excluded}
    (ROOT/"data_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n")
    print("AUDIT_SAVED",sum(r["status"]=="eligible" for r in eligible),"of",len(eligible),flush=True)


if __name__ == "__main__":
    main()
