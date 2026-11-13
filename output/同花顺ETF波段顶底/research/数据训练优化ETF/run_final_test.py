"""Dependency-guarded one-time primary historical test, then two transfer ETFs."""
import csv
import gzip
import io
import json

from engine import ROOT,P,digest,load_panel,prepare,save_csv,simulate
from search import test
from reference import independent_features,independent_intervals,independent_ledger


def main():
    manifest=json.loads((ROOT/"pretest_dependencies.json").read_text())
    repo=ROOT.parents[3]
    for name,expected in manifest["sha256"].items():assert digest(repo/name)==expected,name
    test(load_panel())
    audit=json.loads((ROOT/"corrected_data/data_audit.json").read_text())
    lock=json.loads((ROOT/"selection_lock.json").read_text())
    configs={s["id"]:s["config"] for s in lock["selections"]};configs.update(lock["controls"])
    metrics=[];trades=navs=0;error=0.
    for item in audit["symbols"]:
        if item["code"] not in ("512690","515220"):continue
        assert item["status"]=="eligible" and not item["hfq_mismatches"]
        path=ROOT/"corrected_data"/item["normalized_file"];assert digest(path)==item["normalized_sha256"]
        rows=list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))
        data=prepare(rows,item);features=independent_features(rows)
        for key,c in configs.items():
            result=simulate(data,c,P["windows"]["test"],20,True)
            valid,spans=independent_intervals(rows,features,c,P["windows"]["test"],P)
            ref=independent_ledger(rows,spans,valid,20)
            assert len(result["trades"])==len(spans)
            for actual,expected in zip(result["nav"],ref["nav"]):
                e=abs(actual["nav"]-expected);error=max(error,e);assert e<1e-9
            trades+=len(spans);navs+=len(valid)
            metrics.append({"config":key,"code":item["code"],"name":item["name"],**result["metric"]})
    save_csv(ROOT/"results/supplemental_corrected_etfs.csv",metrics)
    (ROOT/"results/verification_supplement.json").write_text(json.dumps({"status":"PASS","metrics":len(metrics),"trades":trades,"daily_nav":navs,"max_error":error,
        "use":"frozen-parameter transfer only; excluded from training, selection and primary test pool"},indent=2)+"\n")
    print("supplementary transfer verified")


if __name__=="__main__":main()
