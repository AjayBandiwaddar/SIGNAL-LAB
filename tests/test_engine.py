from datetime import datetime, date
import pandas as pd
import pytest

from signal_lab.ingestion import InputValidationError, validate_records
from signal_lab.normalization import build_timeline
from signal_lab.quality import assess_daily_quality
from signal_lab.metrics import calculate_daily_metrics
from signal_lab.comparison import compare_windows, rhythm_status
from signal_lab.demo_data import complete_comparison_example, degraded_recent_example, hand_checkable_example

TZ = "Asia/Kolkata"

def prepared(frame): return build_timeline(validate_records(frame, timezone=TZ), timezone=TZ)

def test_bout_boundaries_and_missing_breaks():
    timeline = prepared(hand_checkable_example())
    _, bouts = calculate_daily_metrics(timeline)
    assert bouts.duration_minutes.tolist() == [4, 5, 9, 10, 14, 15]
    assert bouts.bucket.tolist() == ["<5 minutes", "5-<10 minutes", "5-<10 minutes", "10-<15 minutes", "10-<15 minutes", "15+ minutes"]
    sparse = pd.DataFrame({"timestamp": ["2025-01-01 00:00", "2025-01-01 00:02", "2025-01-01 00:03"], "steps": [3, 0, 4]})
    _, broken = calculate_daily_metrics(prepared(sparse))
    assert broken.duration_minutes.tolist() == [1, 1]

def test_missing_is_not_zero_and_top30_includes_zeroes():
    rows = [{"timestamp": f"2025-01-01 00:{i:02d}", "steps": i if i < 30 else None} for i in range(31)]
    daily, _ = calculate_daily_metrics(prepared(pd.DataFrame(rows)))
    assert daily.iloc[0].observed_daily_steps == sum(range(30))
    assert daily.iloc[0].top30_cadence == pytest.approx(sum(range(30)) / 30)

def test_duplicates_invalid_mixed_source_and_nonwear():
    duplicate = pd.DataFrame({"timestamp": ["2025-01-01 00:00", "2025-01-01 00:00"], "steps": [0, 0]})
    assert len(validate_records(duplicate, timezone=TZ)) == 1
    with pytest.raises(InputValidationError): validate_records(pd.DataFrame({"timestamp": ["2025-01-01 00:00", "2025-01-01 00:00"], "steps": [0, 1]}), timezone=TZ)
    with pytest.raises(InputValidationError): validate_records(pd.DataFrame({"timestamp": ["2025-01-01 00:00", "2025-01-01 00:01"], "steps": [1, 1], "source": ["a", "b"]}), timezone=TZ)
    with pytest.raises(InputValidationError): validate_records(pd.DataFrame({"timestamp": ["2025-01-01 00:00"], "steps": [1], "worn": [False]}), timezone=TZ)
    with pytest.raises(InputValidationError): validate_records(pd.DataFrame({"timestamp": ["2025-01-01 00:00"], "steps": [1.5]}), timezone=TZ)
    with pytest.raises(InputValidationError): validate_records(pd.DataFrame({"timestamp": ["2025-01-01 00:00", "2025-01-01T00:01:00+05:30"], "steps": [1, 1]}), timezone=TZ)

def test_current_day_dst_and_known_nonwear():
    dst = pd.DataFrame({"timestamp": pd.date_range("2025-11-02", periods=1500, freq="min", tz="America/New_York"), "steps": 0})
    timeline = build_timeline(validate_records(dst, timezone="America/New_York"), timezone="America/New_York")
    quality = assess_daily_quality(timeline, timezone="America/New_York", now=datetime(2025, 11, 3, 12))
    assert quality.iloc[0].expected_minutes == 1500
    today = assess_daily_quality(prepared(pd.DataFrame({"timestamp": pd.date_range("2025-01-02", periods=1440, freq="min"), "steps": 0})), now=datetime(2025, 1, 2, 12))
    assert not today.iloc[0].completed and not today.iloc[0].qualifies
    nonwear = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=1440, freq="min"), "steps": 0, "worn": [False] * 100 + [True] * 1340})
    q = assess_daily_quality(prepared(nonwear), now=datetime(2025, 1, 2))
    assert q.iloc[0].usable_minutes == 1340 and not q.iloc[0].qualifies

def test_comparisons_windows_zero_baseline_and_degraded():
    good = prepared(complete_comparison_example())
    quality = assess_daily_quality(good, now=datetime(2025, 3, 2), timezone=TZ)
    daily, _ = calculate_daily_metrics(good)
    comparison = compare_windows(daily, quality)
    assert comparison["metrics"]["observed_daily_steps"]["status"] == "available"
    bad = prepared(degraded_recent_example())
    bad_quality = assess_daily_quality(bad, now=datetime(2025, 3, 2), timezone=TZ)
    bad_daily, _ = calculate_daily_metrics(bad)
    assert compare_windows(bad_daily, bad_quality)["metrics"]["observed_daily_steps"]["status"] == "withheld"
    zeros = daily.copy(); zeros["observed_daily_steps"] = 0; zeros["peak_1min_cadence"] = 0
    out = compare_windows(zeros, quality)
    assert out["metrics"]["observed_daily_steps"]["relative_change"] is None
    assert rhythm_status()["status"] == "withheld"
