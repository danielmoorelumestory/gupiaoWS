import pytest
from fetch import fetch_shares, fetch_navs, fetch_sse_index


@pytest.mark.live
def test_fetch_shares_returns_many():
    out = fetch_shares("2026-11-12")
    assert len(out) > 500 and out["510300"] > 0


@pytest.mark.live
def test_fetch_navs_has_hs300():
    assert fetch_navs(["510300"], "2026-11-12")["510300"] > 0


@pytest.mark.live
def test_fetch_sse_index_has_close():
    s = fetch_sse_index("2026-11-10", "2026-11-12")
    assert s and "close" in s[-1] and s[-1]["close"] > 0
