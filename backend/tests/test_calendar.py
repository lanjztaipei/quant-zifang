"""Tests for XNYS_Calendar golden cases (CAL-01 through CAL-08)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.core.calendar import get_latest_closed_session
from app.core.errors import ValidationError

# Hardcoded directly from Quant_Zifang_Golden_Cases.xlsx -> XNYS_Calendar
XNYS_CASES = [
    (
        "CAL-01",
        "2026-11-23T11:00:00-05:00",
        "2026-11-23T16:00:00+00:00",
        date(2026, 11, 20),
    ),
    (
        "CAL-02",
        "2026-11-23T16:14:59-05:00",
        "2026-11-23T21:14:59+00:00",
        date(2026, 11, 20),
    ),
    (
        "CAL-03",
        "2026-11-23T16:15:00-05:00",
        "2026-11-23T21:15:00+00:00",
        date(2026, 11, 23),
    ),
    (
        "CAL-04",
        "2026-11-26T18:00:00-05:00",
        "2026-11-26T23:00:00+00:00",
        date(2026, 11, 25),
    ),
    (
        "CAL-05",
        "2026-11-27T13:14:00-05:00",
        "2026-11-27T18:14:00+00:00",
        date(2026, 11, 25),
    ),
    (
        "CAL-06",
        "2026-11-27T13:15:00-05:00",
        "2026-11-27T18:15:00+00:00",
        date(2026, 11, 27),
    ),
    (
        "CAL-07",
        "2026-11-29T10:00:00-05:00",
        "2026-11-29T15:00:00+00:00",
        date(2026, 11, 27),
    ),
    (
        "CAL-08",
        "2026-07-02T16:15:00-04:00",
        "2026-07-02T20:15:00+00:00",
        date(2026, 7, 2),
    ),
]


@pytest.mark.parametrize("case_id,now_et,now_utc,expected", XNYS_CASES)
def test_xnys_calendar_golden_cases(
    case_id: str, now_et: str, now_utc: str, expected: date
) -> None:
    dt_et = datetime.fromisoformat(now_et)
    dt_utc = datetime.fromisoformat(now_utc)
    assert get_latest_closed_session(dt_et) == expected, f"{case_id} (ET) mismatch"
    assert get_latest_closed_session(dt_utc) == expected, f"{case_id} (UTC) mismatch"


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        get_latest_closed_session(datetime(2026, 11, 23, 16, 15))
