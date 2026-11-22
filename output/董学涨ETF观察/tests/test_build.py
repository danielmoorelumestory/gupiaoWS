from datetime import datetime

from dxz.build import expected_latest, validate_etf_payload
from dxz.common import SH_TZ

CAL = ["2026-11-19", "2026-11-20", "2026-11-23"]


def test_expected_latest_respects_publish_time():
    assert expected_latest(CAL, datetime(2026, 11, 22, 10, tzinfo=SH_TZ)) == "2026-11-20"
    assert expected_latest(CAL, datetime(2026, 11, 23, 15, tzinfo=SH_TZ)) == "2026-11-20"
    assert expected_latest(CAL, datetime(2026, 11, 23, 19, tzinfo=SH_TZ)) == "2026-11-23"


def test_validate_rejects_future_and_unsorted():
    p = {"etfs": {"510300": {"rows": [{"d": "2026-11-20", "share": 1.0}, {"d": "2026-11-19", "share": 1.0}]},
                  "510050": {"rows": [{"d": "2026-11-30", "share": 1.0}]}}}
    errs = validate_etf_payload(p, "2026-11-22")
    assert any("升序" in e for e in errs) and any("未来" in e for e in errs)
