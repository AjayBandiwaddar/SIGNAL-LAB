import json

from signal_lab.comparison import compare_windows
from signal_lab.demo_data import complete_comparison_example, degraded_recent_example
from signal_lab.evidence import build_evidence_report, html_report, report_json
from signal_lab.ingestion import validate_records
from signal_lab.metrics import calculate_daily_metrics
from signal_lab.normalization import build_timeline
from signal_lab.quality import assess_daily_quality


def _report(frame, *, timezone="Asia/Kolkata"):
    records = validate_records(frame, timezone=timezone)
    timeline = build_timeline(records, timezone=timezone)
    quality = assess_daily_quality(timeline, timezone=timezone)
    daily, bouts = calculate_daily_metrics(timeline)
    comparison = compare_windows(daily, quality)
    return build_evidence_report(records=records, daily=daily, quality=quality, comparison=comparison,
                                 timezone=timezone, is_synthetic=True), comparison


def test_evidence_is_complete_stable_and_matches_engine_results():
    report, comparison = _report(complete_comparison_example())
    again, _ = _report(complete_comparison_example())
    expected = {"observed_daily_steps", "peak_1min_cadence", "top30_cadence", "long_bout_share"}
    assert set(report["calculated_results"]) == expected
    for identifier in expected:
        result = report["calculated_results"][identifier]
        evidence = report["evidence_metadata"][identifier]
        assert {"identifier", "calculation_version", "status", "baseline_value", "recent_value", "absolute_change", "relative_change", "units"} <= set(result)
        assert {"evidence_id", "input_sha256", "baseline_window", "recent_window", "qualifying_days", "coverage", "source_device", "formula", "aggregation_method", "assumptions_and_limitations"} <= set(evidence)
        assert evidence["evidence_id"] == again["evidence_metadata"][identifier]["evidence_id"]
        assert result["recent_value"] == comparison["metrics"][identifier].get("recent")
    changed, _ = _report(complete_comparison_example(), timezone="UTC")
    assert report["evidence_metadata"]["observed_daily_steps"]["evidence_id"] != changed["evidence_metadata"]["observed_daily_steps"]["evidence_id"]


def test_json_is_valid_and_percentage_points_and_withholding_are_explained():
    complete, _ = _report(complete_comparison_example())
    parsed = json.loads(report_json(complete))
    assert parsed["input_sha256"] == complete["input_sha256"]
    assert "percentage points" in complete["explanations"]["long_bout_share"]
    degraded, _ = _report(degraded_recent_example())
    explanation = degraded["explanations"]["observed_daily_steps"]
    assert "Withheld" in explanation and "requires 7" in explanation


def test_html_export_escapes_user_text_and_has_no_external_resources():
    frame = complete_comparison_example()
    frame["source"] = "<script>alert('x')</script>"
    report, _ = _report(frame)
    rendered = html_report(report).decode("utf-8")
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "https://" not in rendered and "http://" not in rendered
