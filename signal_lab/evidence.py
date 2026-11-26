"""Deterministic evidence records and offline-safe report exports."""
from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
from html import escape
import json
from typing import Any

import pandas as pd

CALCULATION_VERSION = "signal-lab-movement-v1"
QUALITY_LIMITATION = (
    "The 95% usable-minute threshold is a configurable prototype policy, not clinically validated. "
    "Record completeness does not establish wear completeness; unknown wear remains a limitation."
)

METRIC_SPECS = {
    "observed_daily_steps": {
        "label": "Median observed daily steps", "units": "steps per day",
        "definition": "The median of each qualifying day's observed usable step counts.",
        "formula": "median(sum(usable observed minute-step counts) for qualifying days)",
        "aggregation": "Median separately across the fixed baseline and recent calendar windows.",
    },
    "peak_1min_cadence": {
        "label": "Median daily peak 1-minute cadence", "units": "steps per minute",
        "definition": "The median daily maximum usable minute-step count.",
        "formula": "median(max(usable minute-step count) for qualifying days)",
        "aggregation": "Median separately across the fixed baseline and recent calendar windows.",
    },
    "top30_cadence": {
        "label": "Median daily top-30 cadence", "units": "steps per minute",
        "definition": "The median daily mean of the 30 highest usable minute-step counts, including recorded zeros.",
        "formula": "median(mean(30 highest usable minute-step counts) for qualifying days)",
        "aggregation": "Median separately across the fixed baseline and recent calendar windows.",
    },
    "long_bout_share": {
        "label": "Steps in 15+ minute bouts", "units": "percent of observed steps",
        "definition": "The percentage of observed steps that occurred in positive usable bouts lasting at least 15 consecutive minutes.",
        "formula": "100 x total steps in 15+ minute bouts / total observed steps",
        "aggregation": "Ratio of totals separately across qualifying days in each fixed calendar window.",
    },
}


def canonical_input_bytes(records: pd.DataFrame) -> bytes:
    """Stable bytes for generated demos or dataframe callers without original bytes."""
    copy = records.copy()
    for column in copy.columns:
        if pd.api.types.is_datetime64_any_dtype(copy[column]):
            copy[column] = copy[column].map(lambda value: value.isoformat() if pd.notna(value) else "")
    return copy.to_csv(index=False, lineterminator="\n").encode("utf-8")


def input_fingerprint(raw_bytes: bytes) -> str:
    """SHA-256 fingerprint of analyzed input bytes; it is not sensor authentication."""
    return sha256(raw_bytes).hexdigest()


def _source_metadata(records: pd.DataFrame) -> dict[str, str | None]:
    def value(column: str) -> str | None:
        if column not in records:
            return None
        values = records[column].dropna()
        return str(values.iloc[0]) if not values.empty else None
    return {"source": value("source"), "device": value("device")}


def _windows(comparison: dict[str, Any]) -> dict[str, dict[str, str | int | None]]:
    if comparison.get("status") != "ok":
        return {"baseline": {"start": None, "end": None, "calendar_days": 20},
                "recent": {"start": None, "end": None, "calendar_days": 10}}
    anchor = date.fromisoformat(comparison["anchor_date"])
    return {
        "baseline": {"start": str(anchor - timedelta(days=29)), "end": str(anchor - timedelta(days=10)), "calendar_days": 20},
        "recent": {"start": str(anchor - timedelta(days=9)), "end": str(anchor), "calendar_days": 10},
    }


def _coverage(quality: pd.DataFrame, start: str | None, end: str | None) -> dict[str, Any]:
    if not start or not end:
        return {"contributing_days": 0, "median_usable_coverage": None, "minimum_usable_coverage": None}
    days = quality[(quality.local_date >= date.fromisoformat(start)) & (quality.local_date <= date.fromisoformat(end)) & quality.qualifies]
    if days.empty:
        return {"contributing_days": 0, "median_usable_coverage": None, "minimum_usable_coverage": None}
    return {"contributing_days": int(len(days)), "median_usable_coverage": float(days.coverage.median()), "minimum_usable_coverage": float(days.coverage.min())}


def _safe(value: Any) -> Any:
    if isinstance(value, dict): return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, list): return [_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, date)): return str(value)
    if value is pd.NA or (isinstance(value, float) and pd.isna(value)): return None
    if hasattr(value, "item"): return _safe(value.item())
    return value


def _explanation(metric: dict[str, Any]) -> str:
    if metric["status"] == "withheld":
        baseline = metric["qualifying_days"]["baseline"]
        recent = metric["qualifying_days"]["recent"]
        return f"Withheld: {metric['withholding_reason']} Baseline has {baseline} qualifying days (requires 14); recent has {recent} (requires 7)."
    change = metric["absolute_change"]
    units = metric["units"]
    if metric["identifier"] == "long_bout_share":
        change_text = f"{change:+.1f} percentage points"
    else:
        change_text = f"{change:+.1f} {units}"
    relative = metric["relative_change"]
    relative_text = "Relative change is undefined because the baseline is zero." if relative is None else f"Relative change: {relative:+.1f}%."
    return f"Recent value: {metric['recent_value']:.1f} {units}; baseline: {metric['baseline_value']:.1f} {units}; change: {change_text}. {relative_text} This is a descriptive comparison, not a health or clinical interpretation."


def build_evidence_report(*, records: pd.DataFrame, daily: pd.DataFrame, quality: pd.DataFrame,
                          comparison: dict[str, Any], raw_input: bytes | None = None,
                          timezone: str = "Asia/Kolkata", is_synthetic: bool = False) -> dict[str, Any]:
    """Build separate calculated results, evidence metadata, and explanations from engine output."""
    raw = raw_input if raw_input is not None else canonical_input_bytes(records)
    fingerprint = input_fingerprint(raw)
    windows = _windows(comparison)
    source = _source_metadata(records)
    context = {"calculation_version": CALCULATION_VERSION, "timezone": timezone, "windows": windows, "source": source}
    calculated_results: dict[str, dict[str, Any]] = {}
    evidence_metadata: dict[str, dict[str, Any]] = {}
    explanations: dict[str, str] = {}
    comparison_metrics = comparison.get("metrics", {})
    for identifier, spec in METRIC_SPECS.items():
        result = comparison_metrics.get(identifier, {"status": "withheld", "reason": comparison.get("reason", "No completed local dates are available.")})
        status = result["status"]
        qualifying = {"baseline": int(result.get("baseline_qualifying_days", 0)), "recent": int(result.get("recent_qualifying_days", 0))}
        stable_context = json.dumps({"input": fingerprint, "metric": identifier, **context}, sort_keys=True, separators=(",", ":"))
        evidence_id = sha256(stable_context.encode("utf-8")).hexdigest()[:24]
        calculated = {
            "identifier": identifier, "calculation_version": CALCULATION_VERSION, "status": status,
            "baseline_value": result.get("baseline"), "recent_value": result.get("recent"),
            "absolute_change": result.get("absolute_change"), "relative_change": result.get("relative_change"), "units": spec["units"],
        }
        metadata = {
            "identifier": identifier, "calculation_version": CALCULATION_VERSION, "evidence_id": evidence_id,
            "input_sha256": fingerprint, "input_fingerprint_note": "Identifies analyzed bytes; it does not authenticate sensor measurements.",
            "baseline_window": windows["baseline"], "recent_window": windows["recent"], "qualifying_days": qualifying,
            "coverage": {"baseline": _coverage(quality, windows["baseline"]["start"], windows["baseline"]["end"]),
                         "recent": _coverage(quality, windows["recent"]["start"], windows["recent"]["end"])},
            "source_device": source, "definition": spec["definition"], "formula": spec["formula"],
            "aggregation_method": spec["aggregation"], "assumptions_and_limitations": [QUALITY_LIMITATION],
            "withholding_reason": result.get("reason") if status == "withheld" else None,
        }
        combined = {**calculated, **metadata}
        calculated_results[identifier] = calculated
        evidence_metadata[identifier] = metadata
        explanations[identifier] = _explanation(combined)
    report = {
        "report_version": CALCULATION_VERSION, "input_sha256": fingerprint,
        "input_fingerprint_note": "An input fingerprint identifies analyzed bytes; it does not authenticate sensor measurements.",
        "synthetic_data": is_synthetic, "timezone": timezone, "source_device": source,
        "quality_policy": QUALITY_LIMITATION, "calculated_results": calculated_results,
        "evidence_metadata": evidence_metadata, "explanations": explanations,
    }
    return _safe(report)


def report_json(report: dict[str, Any]) -> bytes:
    """Serialize valid JSON without NaN or Infinity."""
    return json.dumps(_safe(report), indent=2, sort_keys=True, allow_nan=False).encode("utf-8")


def html_report(report: dict[str, Any]) -> bytes:
    """Build a self-contained, escaped, print-friendly offline report."""
    safe = _safe(report)
    def text(value: Any) -> str: return escape("Not available" if value is None else str(value))
    synthetic = "Synthetic demo data - not participant data." if safe["synthetic_data"] else "User-provided data."
    cards = []
    for identifier, result in safe["calculated_results"].items():
        meta = safe["evidence_metadata"][identifier]
        label = METRIC_SPECS[identifier]["label"]
        if result["status"] == "withheld":
            body = f"<strong>Withheld</strong><p>{text(meta['withholding_reason'])}</p>"
        else:
            relative = "undefined (zero baseline)" if result["relative_change"] is None else f"{result['relative_change']:+.1f}%"
            body = f"<strong>{text(result['recent_value'])} {text(result['units'])}</strong><p>Baseline {text(result['baseline_value'])}; change {text(result['absolute_change'])}; relative {text(relative)}.</p>"
        cards.append(f"<section class='card'><h2>{text(label)}</h2>{body}<p class='muted'>{text(safe['explanations'][identifier])}</p><p class='muted'>Evidence ID: {text(meta['evidence_id'])}<br>Formula: {text(meta['formula'])}</p></section>")
    source = safe["source_device"]
    html = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>SIGNAL LAB evidence report</title><style>
body{{font-family:Arial,sans-serif;background:#0B1020;color:#F7F8FA;margin:0;padding:32px}}main{{max-width:1000px;margin:auto}}header,.card{{background:#141E30;border:1px solid #26344B;border-radius:14px;padding:20px;margin:14px 0}}h1{{margin:0;color:#52DECF}}h2{{font-size:17px;margin:0 0 10px}}.muted{{color:#AAB6C8;font-size:13px;line-height:1.45}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}@media print{{body{{background:white;color:#111;padding:0}}header,.card{{background:white;border-color:#bbb;break-inside:avoid}}h1{{color:#075f58}}.muted{{color:#444}}}}</style></head>
<body><main><header><h1>SIGNAL LAB</h1><p>Your steps have a story - evidence report</p><p class='muted'>{text(synthetic)} Source: {text(source['source'])}; device: {text(source['device'])}. Input SHA-256: {text(safe['input_sha256'])}</p><p class='muted'>{text(safe['quality_policy'])}</p></header><div class='grid'>{''.join(cards)}</div></main></body></html>"""
    return html.encode("utf-8")
