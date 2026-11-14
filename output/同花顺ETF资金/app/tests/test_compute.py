import pytest
from compute import compute_daily_flow, aggregate_flow, cumulative


def test_flow_basic_sign():
    out = compute_daily_flow({"A": 110.0}, {"A": 100.0}, {"A": 2.0})
    assert out["A"] == pytest.approx(20.0)  # 份额增→正(流入)


def test_flow_negative_on_redemption():
    out = compute_daily_flow({"A": 90.0}, {"A": 100.0}, {"A": 2.0})
    assert out["A"] == pytest.approx(-20.0)  # 份额减→负(流出)


def test_flow_filters_split():
    # Δ/prev = 2.0 > 0.5 阈值 → 疑似折算，剔除
    assert "A" not in compute_daily_flow({"A": 300.0}, {"A": 100.0}, {"A": 1.0})


def test_flow_skips_missing_nav():
    assert compute_daily_flow({"A": 110.0}, {"A": 100.0}, {}) == {}


def test_flow_skips_new_listing():
    # 仅在 t 日（无前值）→ 跳过
    assert compute_daily_flow({"A": 100.0}, {}, {"A": 1.0}) == {}


def test_flow_skips_missing_today():
    # 仅在前值（当日缺份额/停牌）→ 跳过
    assert compute_daily_flow({}, {"A": 100.0}, {"A": 1.0}) == {}


def test_flow_skips_zero_prev():
    # 前值为 0 无法算比例 → 跳过
    assert compute_daily_flow({"A": 100.0}, {"A": 0.0}, {"A": 1.0}) == {}


def test_aggregate_splits_broad():
    allv, broad = aggregate_flow({"510300": 10.0, "512480": 5.0})
    assert allv == pytest.approx(15.0) and broad == pytest.approx(10.0)


def test_cumulative_last_n():
    assert cumulative([1.0, 2.0, 3.0, 4.0], 2) == pytest.approx(7.0)


def test_cumulative_n_exceeds_len():
    assert cumulative([1.0, 2.0], 5) == pytest.approx(3.0)
