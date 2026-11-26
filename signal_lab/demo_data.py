"""Reproducible synthetic fixtures; they are not participant data."""
from __future__ import annotations

from datetime import date, timedelta
import pandas as pd


def _day_rows(day: date, timezone: str, *, long_bout: bool = True) -> list[dict]:
    moments = pd.date_range(pd.Timestamp(day).tz_localize(timezone), periods=1440, freq="min")
    steps = [0] * 1440
    if long_bout:
        for i in range(8 * 60, 8 * 60 + 20): steps[i] = 80
    for i in range(18 * 60, 18 * 60 + 5): steps[i] = 20
    return [{"timestamp": stamp, "steps": count, "source": "Synthetic demo"} for stamp, count in zip(moments, steps)]


def complete_comparison_example(*, end_date: date = date(2025, 2, 28), timezone: str = "Asia/Kolkata") -> pd.DataFrame:
    """Thirty completed synthetic days, deliberately labelled as demo data."""
    rows = []
    for offset in range(30): rows.extend(_day_rows(end_date - timedelta(days=29 - offset), timezone, long_bout=offset >= 20))
    return pd.DataFrame(rows)


def degraded_recent_example(*, end_date: date = date(2025, 2, 28), timezone: str = "Asia/Kolkata") -> pd.DataFrame:
    """Thirty synthetic days, but only six qualifying recent days."""
    data = complete_comparison_example(end_date=end_date, timezone=timezone)
    # Four recent dates have 100 absent minutes: 90-minute coverage is below policy.
    bad_days = {end_date - timedelta(days=offset) for offset in (1, 3, 5, 7)}
    return data[~(data.timestamp.dt.date.isin(bad_days) & (data.timestamp.dt.minute < 100))].reset_index(drop=True)


def hand_checkable_example(*, timezone: str = "Asia/Kolkata") -> pd.DataFrame:
    """Synthetic one-day fixture with 4, 5, 9, 10, 14, and 15 minute bouts."""
    day = date(2025, 1, 15)
    rows = []
    cursor = 0
    for duration in (4, 5, 9, 10, 14, 15):
        for minute in range(duration):
            rows.append({"timestamp": pd.Timestamp(day).tz_localize(timezone) + pd.Timedelta(minutes=cursor + minute), "steps": minute + 1, "source": "Synthetic demo"})
        cursor += duration + 1
    return pd.DataFrame(rows)
