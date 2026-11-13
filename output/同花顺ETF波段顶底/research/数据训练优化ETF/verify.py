"""Independently audit frozen inputs/features and locked candidate ledgers."""
from decimal import Decimal as D
import argparse
import bisect
import csv
import gzip
import io
import json

from engine import ROOT,P,digest,load_panel,simulate
from grid import controls
from reference import independent_features,independent_intervals,independent_ledger


def main():
    parser=argparse.ArgumentParser();parser.add_argument("phase",choices=("inputs","development","test"));args=parser.parse_args()
    out=ROOT/"results";out.mkdir(exist_ok=True)
    audit=json.loads((ROOT/"data_audit.json").read_text());assert digest(ROOT/"data_audit.json")==P["audit_sha256"]
    rows_checked=0
    for item in audit["symbols"]:
        raw_path=ROOT/item["raw_snapshot_file"]
        assert digest(raw_path)==item["raw_snapshot_sha256"]
        assert digest(ROOT/item["factor_file"])==item["factor_sha256"]
        raw=list(csv.DictReader(io.StringIO(gzip.decompress(raw_path.read_bytes()).decode())))
        if item["status"]!="eligible":continue
        path=ROOT/item["normalized_file"];assert digest(path)==item["normalized_sha256"]
        rows=list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))
        raw=[r for r in raw if r["date"]<=audit["cutoff"]]
        assert len(rows)==len(raw)
        fs=item["factor_records"];dates=[x[0] for x in fs]
        for a,b in zip(rows,raw):
            assert all(a[k]==b[k] for k in ("date","open","high","low","close"))
            index=bisect.bisect_right(dates,a["date"])-1;_,s,u=fs[index]
            assert D(a["adjusted_close"])==D(a["close"])*D(s)+D(u)
            assert D(a["share_factor"])==D(s) and D(a["cumulative_cash"])==D(u)
            rows_checked+=1
    report={"phase":args.phase,"status":"PASS","normalized_rows_checked":rows_checked}
    if args.phase=="inputs":
        (out/"verification_inputs.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report));return
    lock=json.loads((ROOT/"selection_lock.json").read_text())
    configs={s["id"]:s["config"] for s in lock["selections"]};configs.update(controls())
    panel=load_panel();max_error=0.;feature_rows=trade_count=nav_count=metric_count=0
    def close(a,b):
        nonlocal max_error
        error=abs(float(a)-float(b));max_error=max(max_error,error)
        assert error<1e-9*max(1,abs(float(b))),(a,b,error)
    saved_nav={};saved_trades={};saved_metrics={}
    if args.phase=="test":
        complete=json.loads((out/"test_complete.json").read_text());assert complete["selection_lock_sha256"]==digest(ROOT/"selection_lock.json")
        for filename,destination in (("test_nav.csv.gz",saved_nav),("test_trades.csv.gz",saved_trades)):
            for r in csv.DictReader(io.StringIO(gzip.decompress((out/filename).read_bytes()).decode())):
                destination.setdefault((r["config"],r["code"]),[]).append(r)
        for r in csv.DictReader(io.StringIO(gzip.decompress((out/"test_per_etf.csv.gz").read_bytes()).decode())):
            if r["phase"]=="test" and r["cost"]=="20":saved_metrics[(r["config"],r["code"])]=r
    for code,data in panel.items():
        rows=data["rows"];f=independent_features(rows)
        assert f["above"]==data["above"] and f["below"]==data["below"] and f["macds"]==data["macds"]
        for n,values in f["bands"].items():
            for a,b in zip(data["bands"][n],values):
                if b is None:assert a is None
                else:close(a,b)
        feature_rows+=len(rows)
        phases=("train","validation") if args.phase=="development" else ("test",)
        for phase in phases:
            for key,c in configs.items():
                calculated=independent_intervals(rows,f,c,P["windows"][phase],P)
                if calculated is None:continue
                valid,intervals=calculated;ref=independent_ledger(rows,intervals,valid,20)
                if args.phase=="development":
                    actual=simulate(data,c,P["windows"][phase],20,True)
                    nav,trades,metric=actual["nav"],actual["trades"],actual["metric"]
                else:
                    nav=saved_nav[(key,code)];trades=saved_trades.get((key,code),[]);metric=saved_metrics[(key,code)]
                assert len(nav)==len(ref["nav"]) and len(trades)==len(intervals)
                for n,expected in zip(nav,ref["nav"]):close(n["nav"],expected);nav_count+=1
                for t,part in zip(trades,ref["components"]):
                    signal,entry,exit_signal,exit_,forced=part["span"]
                    assert int(t["entry_signal_index"])==signal and int(t["entry_index"])==entry
                    assert int(t["exit_index"])==exit_
                    assert str(t["exit_signal_index"])==(str(exit_signal) if exit_signal is not None else ("None" if args.phase=="development" else ""))
                    assert str(t["forced_end"])==str(forced)
                    close(t["entry_cash"],part["before_cash"]);close(t["exit_cash"],part["sale"])
                    close(t["dividends"],part["coupon"]);close(t["net_return"],part["return"]);trade_count+=1
                close(metric["final_nav"],ref["final_nav"]);close(metric["mdd"],ref["mdd"])
                close(metric["fees"],ref["fees"]);close(metric["dividend_reserve"],ref["reserve"])
                assert int(metric["natural"])==ref["natural"] and int(metric["wins"])==ref["wins"]
                metric_count+=1
    report.update(feature_rows=feature_rows,trades=trade_count,daily_nav=nav_count,metrics=metric_count,max_numeric_error=max_error,
                  method="Fraction features, Decimal60 MACD, independent interval search and closed-form share/cash ledger")
    (out/f"verification_{args.phase}.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report))


if __name__=="__main__":main()
