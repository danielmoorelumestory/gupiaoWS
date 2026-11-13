"""Verify complete research, shared cached inputs and frozen engine dependencies."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]


def files():
    own = [p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts
           and p.name != "bundle-manifest.json"]
    protocol = json.loads((ROOT / "protocol.json").read_text())
    source = ROOT.parent / "固定规则验证"
    previous = ROOT.parent / "底部回升结合MA10"
    own.append(source / "data_audit.json")
    own.extend(source / s["normalized_file"] for s in protocol["inputs"]["eligible_symbols"])
    own.extend(previous / name for name in ("protocol.json", "strategy.py", "run_backtest.py", "results/metrics.csv"))
    own.append(ROOT.parents[2] / "布鲁斯的金融宝藏/replica/bruce_replica/etf_band.py")
    return sorted(own)


def main():
    path = ROOT / "bundle-manifest.json"
    if sys.argv[1:] == ["--write"]:
        entries = [{"path": str(p.relative_to(REPO)), "bytes": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files()]
        path.write_text(json.dumps({"base": "repository root", "files": entries}, ensure_ascii=False, indent=2)+"\n")
    manifest = json.loads(path.read_text())
    assert {str(p.relative_to(REPO)) for p in files()} == {e["path"] for e in manifest["files"]}
    for entry in manifest["files"]:
        data = (REPO / entry["path"]).read_bytes()
        assert len(data) == entry["bytes"], entry["path"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
    print(f"PASS: {len(manifest['files'])} archived files and frozen inputs")


if __name__ == "__main__":
    main()
