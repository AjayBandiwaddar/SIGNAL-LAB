"""Daily movement-bout and cadence metrics, with no missing-value imputation."""
from __future__ import annotations

import pandas as pd


def _bucket(duration: int) -> str:
    if duration < 5: return "<5 minutes"
    if duration < 10: return "5-<10 minutes"
    if duration < 15: return "10-<15 minutes"
    return "15+ minutes"


def movement_bouts(timeline: pd.DataFrame) -> pd.DataFrame:
    bouts = []
    for date, day in timeline.groupby("local_date", sort=True):
        active = (day["usable"] & (day["steps"] > 0)).fillna(False).to_numpy()
        start = None
        for index, value in enumerate(list(active) + [False]):
            if value and start is None: start = index
            if not value and start is not None:
                section = day.iloc[start:index]
                duration = index - start
                bouts.append({"local_date": date, "start": section.iloc[0]["timestamp"], "duration_minutes": duration,
                              "step_count": int(section["steps"].sum()), "bucket": _bucket(duration)})
                start = None
    return pd.DataFrame(bouts, columns=["local_date", "start", "duration_minutes", "step_count", "bucket"])


def calculate_daily_metrics(timeline: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return daily measures and individual bouts."""
    bouts = movement_bouts(timeline)
    rows = []
    for date, day in timeline.groupby("local_date", sort=True):
        usable = day.loc[day["usable"], "steps"].astype("Int64")
        observed_steps = int(usable.sum()) if len(usable) else None
        day_bouts = bouts[bouts["local_date"] == date]
        rows.append({"local_date": date, "observed_daily_steps": observed_steps,
                     "peak_1min_cadence": int(usable.max()) if len(usable) else None,
                     "top30_cadence": float(usable.nlargest(30).mean()) if len(usable) >= 30 else None,
                     "long_bout_steps": int(day_bouts.loc[day_bouts["bucket"] == "15+ minutes", "step_count"].sum()),
                     "bout_count": len(day_bouts)})
    return pd.DataFrame(rows), bouts
