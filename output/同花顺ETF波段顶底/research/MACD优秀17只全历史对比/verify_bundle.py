"""Verify the archived lifetime17 study and its formula/ledger dependencies."""
from pathlib import Path
import csv
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
SOURCE=ROOT.parent/"数据训练优化ETF"


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def files():
    own=[p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name!="bundle-manifest.json"]
    own.extend(SOURCE/p for p in ("engine.py","grid.py","reference.py","prepare_data.py","protocol.json","selection_lock.json"))
    own.append(ROOT.parents[2]/"布鲁斯的金融宝藏/replica/bruce_replica/etf_band.py")
    return sorted(own)


def main():
    path=ROOT/"bundle-manifest.json"
    if sys.argv[1:]==["--write"]:
        path.write_text(json.dumps({"base":"repository root","sha256":{str(p.relative_to(REPO)):digest(p) for p in files()}},ensure_ascii=False,indent=2)+"\n")
    manifest=json.loads(path.read_text())
    assert set(manifest["sha256"])=={str(p.relative_to(REPO)) for p in files()}
    for name,expected in manifest["sha256"].items():assert digest(REPO/name)==expected,name
    spec=json.loads((ROOT/"protocol.json").read_text())
    assert digest(SOURCE/"selection_lock.json")==spec["source_pin"]
    audit=json.loads((ROOT/"data_audit.json").read_text())
    assert len(audit["symbols"])==17 and all(x["last"]==spec["cutoff_requested"] for x in audit["symbols"])
    for item in audit["symbols"]:
        assert digest(ROOT/f"data/{item['code']}.csv.gz")==item["merged_sha256"]
        assert digest(SOURCE/f"data/{item['code']}.csv.gz")==item["source_sha256"]
    rows=list(csv.DictReader((ROOT/"results/lifetime_long.csv").open()))
    assert len(rows)==51
    check=json.loads((ROOT/"results/verification.json").read_text());assert check["status"]=="PASS"
    print(json.dumps({"status":"PASS","files":len(files()),"etfs":17,"metrics":51,"closing_date":spec["cutoff_requested"]}))


if __name__=="__main__":main()
