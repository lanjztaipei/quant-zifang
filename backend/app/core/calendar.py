"""XNYS trading calendar helpers (pure function with injected `now`)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import cast
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

from app.core.errors import ValidationError

ET_TZ = ZoneInfo("America/New_York")
CLOSE_BUFFER = timedelta(minutes=15)


@lru_cache(maxsize=4)
def _get_xnys_calendar(end_year: int | None = None) -> xcals.ExchangeCalendar:
    if end_year is None:
        return xcals.get_calendar("XNYS")
    return xcals.get_calendar("XNYS", end=f"{end_year}-12-31")


def get_latest_closed_session(now: datetime) -> date:
    """Return the latest fully closed XNYS trading session date for `now`.

    A trading session counts as closed once `now >= session_close + 15 minutes`
    (respecting early closes such as the day after Thanksgiving at 13:00 ET).
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValidationError("now 必須包含時區資訊")

    now_et = now.astimezone(ET_TZ)
    today_et = now_et.date()

    cal = _get_xnys_calendar()
    if today_et > cal.last_session.date():
        cal = _get_xnys_calendar(today_et.year + 1)

    ts_today = pd.Timestamp(today_et)
    if cal.is_session(ts_today):
        close_utc = cal.session_close(ts_today).to_pydatetime()
        if now >= close_utc + CLOSE_BUFFER:
            return today_et
        return cast(date, cal.previous_session(ts_today).date())

    return cast(date, cal.date_to_session(ts_today, direction="previous").date())
