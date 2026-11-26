"""Construction of DST-aware complete local-day minute grids."""
from __future__ import annotations

import pandas as pd


def build_timeline(records: pd.DataFrame, *, timezone: str = "Asia/Kolkata") -> pd.DataFrame:
    """Return every minute in every local date represented by validated records."""
    if records.empty:
        return records.copy()
    first_day = records["timestamp"].min().tz_convert(timezone).date()
    last_day = records["timestamp"].max().tz_convert(timezone).date()
    days = pd.date_range(first_day, last_day, freq="D")
    ranges = []
    for day in days:
        start = pd.Timestamp(day.date()).tz_localize(timezone)
        end = (pd.Timestamp(day.date()) + pd.Timedelta(days=1)).tz_localize(timezone)
        ranges.append(pd.date_range(start, end, freq="min", inclusive="left"))
    grid = pd.DataFrame({"timestamp": ranges[0].append(ranges[1:]) if len(ranges) > 1 else ranges[0]})
    result = grid.merge(records, on="timestamp", how="left", validate="one_to_one")
    result["local_date"] = result["timestamp"].dt.tz_convert(timezone).dt.date
    result["observed"] = result["steps"].notna()
    result["known_nonwear"] = result["worn"].eq(False).fillna(False)
    result["usable"] = result["observed"] & ~result["known_nonwear"]
    return result
