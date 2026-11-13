"""Verify Claude's complete per-ETF retest and immutable source pins."""
from pathlib import Path
import csv
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def files():
    return sorted(p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name!="bundle-manifest.json")


def main():
    path=ROOT/"bundle-manifest.json"
    if sys.argv[1:]==["--write"]:
        path.write_text(json.dumps({"sha256":{str(p.relative_to(ROOT)):digest(p) for p in files()}},ensure_ascii=False,indent=2)+"\n")
    manifest=json.loads(path.read_text())
    assert set(manifest["sha256"])=={str(p.relative_to(ROOT)) for p in files()}
    for name,expected in manifest["sha256"].items():assert digest(ROOT/name)==expected,name
    inputs=json.loads((ROOT/"inputs.json").read_text());source=REPO/inputs["source_directory"]
    for name,expected in inputs["pins"].items():assert digest(source/name)==expected,name
    for item in inputs["primary_etfs"]:assert digest(source/item["normalized_file"])==item["normalized_sha256"]
    verification=json.loads((ROOT/"claude/verification.json").read_text())
    assert verification["main_groups"]==366 and verification["diff_main_scope_366"]==0
    long=list(csv.DictReader((ROOT/"claude/retest_long_366.csv").open()))
    brief=list(csv.DictReader((ROOT/"claude/per_etf_61_brief.csv").open()))
    assert len(long)==366 and len(brief)==61
    print(json.dumps({"status":"PASS","archived_files":len(files()),"main_groups":366,"main_differences":0,
                      "extra_0bps_float_classification_differences":verification["diff_extra_scope"]}))


if __name__=="__main__":main()
