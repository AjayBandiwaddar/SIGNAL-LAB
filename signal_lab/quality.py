"""Transparent, configurable day-level data quality policy."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd


def assess_daily_quality(timeline: pd.DataFrame, *, timezone: str = "Asia/Kolkata", now: datetime | pd.Timestamp | None = None, threshold: float = 0.95) -> pd.DataFrame:
    """Assess completed local dates; threshold is prototype policy, not clinical validation."""
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    current = pd.Timestamp.now(tz=timezone) if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize(timezone)
    else:
        current = current.tz_convert(timezone)
    rows = []
    for date, day in timeline.groupby("local_date", sort=True):
        expected = len(day)
        usable = int(day["usable"].sum())
        completed = date < current.date()
        rows.append({"local_date": date, "expected_minutes": expected, "usable_minutes": usable,
                     "coverage": usable / expected if expected else 0.0, "completed": completed,
                     "qualifies": completed and usable / expected >= threshold,
                     "policy_note": "95% threshold is a configurable prototype policy, not clinically validated."})
    return pd.DataFrame(rows)
