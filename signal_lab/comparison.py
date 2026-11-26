"""Fixed-window, quality-gated within-person comparisons."""
from __future__ import annotations

from datetime import date, timedelta
import math
import pandas as pd


def _change(baseline: float, recent: float, *, share: bool = False) -> dict:
    absolute = recent - baseline
    if baseline == 0:
        return {"baseline": baseline, "recent": recent, "absolute_change": absolute,
                "relative_change": None, "relative_note": "undefined because baseline is zero"}
    return {"baseline": baseline, "recent": recent, "absolute_change": absolute,
            "relative_change": (absolute / baseline) * (100 if not share else 1),
            "relative_note": "percentage points" if share else "percent"}


def _median_metric(frame: pd.DataFrame, column: str, minimum: int) -> tuple[float | None, int]:
    values = frame[column].dropna()
    return (float(values.median()), len(values)) if len(values) >= minimum else (None, len(values))


def _long_share(frame: pd.DataFrame) -> float | None:
    total = frame["observed_daily_steps"].sum(min_count=1)
    if pd.isna(total) or total == 0:
        return None
    return float(100 * frame["long_bout_steps"].sum() / total)


def compare_windows(daily: pd.DataFrame, quality: pd.DataFrame) -> dict:
    """Compare fixed 20/10 calendar-date windows ending at last completed represented date."""
    combined = daily.merge(quality[["local_date", "qualifies", "completed"]], on="local_date", how="inner")
    completed_dates = combined.loc[combined["completed"], "local_date"]
    if completed_dates.empty:
        return {"status": "withheld", "reason": "no completed local calendar date is represented"}
    anchor = max(completed_dates)
    recent_dates = {anchor - timedelta(days=i) for i in range(10)}
    baseline_dates = {anchor - timedelta(days=i) for i in range(10, 30)}
    baseline = combined[combined.local_date.isin(baseline_dates) & combined.qualifies]
    recent = combined[combined.local_date.isin(recent_dates) & combined.qualifies]
    result = {"status": "ok", "anchor_date": str(anchor), "baseline_calendar_days": 20,
              "recent_calendar_days": 10, "metrics": {}}
    for column, label in [("observed_daily_steps", "observed_daily_steps"),
                          ("peak_1min_cadence", "peak_1min_cadence"), ("top30_cadence", "top30_cadence")]:
        base, base_n = _median_metric(baseline, column, 14)
        rec, rec_n = _median_metric(recent, column, 7)
        if base is None or rec is None:
            result["metrics"][label] = {"status": "withheld", "baseline_qualifying_days": base_n,
                                         "recent_qualifying_days": rec_n, "reason": "requires 14 baseline and 7 recent qualifying days"}
        else:
            result["metrics"][label] = {"status": "available", "baseline_qualifying_days": base_n,
                                         "recent_qualifying_days": rec_n, **_change(base, rec)}
    base_share, recent_share = _long_share(baseline), _long_share(recent)
    if len(baseline) < 14 or len(recent) < 7 or base_share is None or recent_share is None:
        result["metrics"]["long_bout_share"] = {"status": "withheld", "baseline_qualifying_days": len(baseline),
            "recent_qualifying_days": len(recent), "reason": "requires 14/7 qualifying days and observed steps in both windows"}
    else:
        result["metrics"]["long_bout_share"] = {"status": "available", "baseline_qualifying_days": len(baseline),
            "recent_qualifying_days": len(recent), **_change(base_share, recent_share, share=True)}
    return result


def rhythm_status() -> dict:
    return {"status": "withheld", "reason": "Rhythm metrics require suitable wear evidence and a separately validated rhythm module; IS, IV, and M10 are not calculated."}
