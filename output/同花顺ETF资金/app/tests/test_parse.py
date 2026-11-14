import json, pathlib
import pytest
from parse import parse_sse_shares, parse_szse_shares, parse_nav
from universe import is_broad

FX = pathlib.Path(__file__).parent / "fixtures"
def load(n): return json.load(open(FX / n, encoding="utf-8"))

def test_parse_sse_shares_converts_wan_to_fen():
    out = parse_sse_shares(load("sse_shares.json"))
    assert out["510300"] == pytest.approx(4581768.77 * 10000)

def test_parse_szse_shares_returns_fen():
    out = parse_szse_shares(load("szse_shares.json"))
    assert out["159919"] == pytest.approx(1356501.66 * 10000)

def test_parse_szse_shares_only_etf():
    out = parse_szse_shares(load("szse_shares.json"))
    assert "159919" in out and all(isinstance(v, float) for v in out.values())

def test_parse_nav_picks_dwjz():
    assert parse_nav(load("nav.json")) == 4.1203

def test_parse_nav_missing_returns_none():
    assert parse_nav({"Data": {"LSJZList": []}}) is None
    assert parse_nav({}) is None

def test_is_broad_true_for_hs300_false_for_sector():
    assert is_broad("510300") and is_broad("159919")
    assert not is_broad("512480")
