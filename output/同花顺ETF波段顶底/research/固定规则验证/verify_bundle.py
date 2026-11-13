"""检查已归档研究包的文件完整性，不联网、不修改任何证据。"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / "bundle-manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        path = ROOT/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"文件缺失或已改变：{name}")
    print(json.dumps({"status": "passed", "files_verified": len(manifest["sha256"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
