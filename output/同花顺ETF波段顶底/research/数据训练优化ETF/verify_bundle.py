"""Verify all archived study files, external formula dependency, and test pin."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def files():
    own=[p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name!="bundle-manifest.json"]
    own.append(ROOT.parents[2]/"布鲁斯的金融宝藏/replica/bruce_replica/etf_band.py")
    return sorted(own)


def main():
    manifest_path=ROOT/"bundle-manifest.json"
    if sys.argv[1:]==["--write"]:
        manifest_path.write_text(json.dumps({"base":"repository root","sha256":{str(p.relative_to(REPO)):digest(p) for p in files()}},ensure_ascii=False,indent=2)+"\n")
    manifest=json.loads(manifest_path.read_text())
    assert set(manifest["sha256"])=={str(p.relative_to(REPO)) for p in files()}
    for name,expected in manifest["sha256"].items():assert digest(REPO/name)==expected,name
    pretest=json.loads((ROOT/"pretest_dependencies.json").read_text())
    for name,expected in pretest["sha256"].items():assert digest(REPO/name)==expected,name
    complete=json.loads((ROOT/"results/test_complete.json").read_text())
    assert complete["selection_lock_sha256"]==digest(ROOT/"selection_lock.json")
    print(json.dumps({"status":"PASS","files_verified":len(manifest["sha256"]),"test_selection_pin":"PASS","pretest_dependencies":"PASS"}))


if __name__=="__main__":main()
