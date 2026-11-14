"""宽基 ETF 白名单（近似，人工维护）。"""
import json
import pathlib

_P = pathlib.Path(__file__).parent / "broad_base.json"
BROAD_BASE: set[str] = set(json.load(open(_P, encoding="utf-8"))["codes"])


def is_broad(code: str) -> bool:
    return code in BROAD_BASE
