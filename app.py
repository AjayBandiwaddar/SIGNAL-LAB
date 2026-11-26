"""SIGNAL LAB: a private, quality-aware movement report."""
from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from signal_lab.comparison import compare_windows, rhythm_status
from signal_lab.demo_data import complete_comparison_example, degraded_recent_example
from signal_lab.ingestion import InputValidationError, load_csv, validate_records
from signal_lab.metrics import calculate_daily_metrics
from signal_lab.normalization import build_timeline
from signal_lab.quality import assess_daily_quality

NAVY, SURFACE, TEAL, AMBER, TEXT, MUTED = "#0B1020", "#141E30", "#52DECF", "#F2BC68", "#F7F8FA", "#AAB6C8"
METRIC_LABELS = {
    "observed_daily_steps": "Median observed daily steps",
    "peak_1min_cadence": "Median daily peak 1-minute cadence",
    "top30_cadence": "Median daily top-30 cadence",
    "long_bout_share": "Steps in 15+ minute bouts",
}


def _style() -> None:
    st.markdown(f"""
    <style>
      .stApp {{ background: {NAVY}; color: {TEXT}; }}
      [data-testid="stSidebar"] {{ background: #10192A; border-right: 1px solid #26344B; }}
      [data-testid="stSidebar"] * {{ color: {TEXT}; }}
      .block-container {{ max-width: 1280px; padding-top: 2.4rem; padding-bottom: 3rem; }}
      h1, h2, h3 {{ color: {TEXT}; letter-spacing: -0.025em; }}
      p, label, .stCaption {{ color: {MUTED}; }}
      .eyebrow {{ color: {TEAL}; font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
      .hero-copy {{ color: {MUTED}; font-size: 1.04rem; max-width: 48rem; }}
      .surface {{ background: {SURFACE}; border: 1px solid #26344B; border-radius: 14px; padding: 1rem 1.1rem; margin: .5rem 0 1rem; }}
      .metric-label {{ color: {MUTED}; font-size: .82rem; min-height: 2.25rem; }}
      .metric-value {{ color: {TEXT}; font-size: 1.55rem; font-weight: 700; line-height: 1.35; }}
      .metric-note {{ color: {MUTED}; font-size: .82rem; margin-top: .35rem; }}
      .withheld {{ border-left: 3px solid {AMBER}; }}
      .stButton > button {{ background: {TEAL}; color: #071522; border: 0; border-radius: 8px; font-weight: 700; }}
      [data-testid="stMetric"] {{ background: {SURFACE}; border: 1px solid #26344B; border-radius: 12px; padding: .8rem; }}
      [data-testid="stTabs"] button {{ color: {MUTED}; }}
      [data-testid="stTabs"] button[aria-selected="true"] {{ color: {TEAL}; }}
      @media (max-width: 700px) {{ .block-container {{ padding-left: 1rem; padding-right: 1rem; }} }}
    </style>
    """, unsafe_allow_html=True)


def _reset() -> None:
    for key in ("consent", "analysis", "uploaded_bytes", "upload_error"):
        st.session_state.pop(key, None)
    st.session_state.upload_nonce = st.session_state.get("upload_nonce", 0) + 1


def _input_data(choice: str, uploaded, timezone: str) -> tuple[pd.DataFrame | None, str, str | None]:
    """Obtain data solely in this Streamlit session; uploads are never written to disk."""
    if choice == "Complete synthetic demo":
        return complete_comparison_example(timezone=timezone), "Synthetic demo — complete", None
    if choice == "Demo with missing data":
        return degraded_recent_example(timezone=timezone), "Synthetic demo — missing data", None
    if uploaded is None:
        return None, "Your CSV", "Choose a CSV to begin your report."
    try:
        raw = uploaded.getvalue()
        # Retain only this session's bytes; no disk writes and no shared cache.
        st.session_state.uploaded_bytes = raw
        return load_csv(raw.decode("utf-8"), timezone=timezone), uploaded.name, None
    except (UnicodeDecodeError, InputValidationError) as exc:
        return None, "Your CSV", f"We could not use that file: {exc}"


def _analyse(data: pd.DataFrame, timezone: str) -> dict:
    records = validate_records(data, timezone=timezone)
    timeline = build_timeline(records, timezone=timezone)
    quality = assess_daily_quality(timeline, timezone=timezone)
    daily, bouts = calculate_daily_metrics(timeline)
    return {"records": records, "timeline": timeline, "quality": quality, "daily": daily,
            "bouts": bouts, "comparison": compare_windows(daily, quality)}


def _meta(analysis: dict, label: str) -> None:
    records, quality = analysis["records"], analysis["quality"]
    dates = f"{records.timestamp.min().date():%d %b %Y} – {records.timestamp.max().date():%d %b %Y}"
    source = records.get("source", pd.Series(dtype=str)).dropna().iloc[0] if "source" in records and records.source.notna().any() else "Not supplied"
    device = records.get("device", pd.Series(dtype=str)).dropna().iloc[0] if "device" in records and records.device.notna().any() else "Not supplied"
    st.markdown(f'<div class="surface"><b>{label}</b> &nbsp;·&nbsp; {dates} &nbsp;·&nbsp; Source: {source} &nbsp;·&nbsp; Device: {device}<br><span style="color:{MUTED}">{int(quality.qualifies.sum())} qualifying days of {len(quality)} represented; 95% usable-minute prototype threshold.</span></div>', unsafe_allow_html=True)


def _metric_card(key: str, data: dict) -> None:
    metric = data["comparison"].get("metrics", {}).get(key)
    with st.container(border=False):
        if not metric or metric["status"] == "withheld":
            reason = metric["reason"] if metric else data["comparison"].get("reason", "No completed local dates are available.")
            st.markdown(f'<div class="surface withheld"><div class="metric-label">{METRIC_LABELS[key]}</div><div class="metric-value">Withheld</div><div class="metric-note">{reason}</div></div>', unsafe_allow_html=True)
            return
        suffix = " pp" if key == "long_bout_share" else ""
        recent, baseline, change = metric["recent"], metric["baseline"], metric["absolute_change"]
        relative = "Relative change unavailable" if metric["relative_change"] is None else f"{metric['relative_change']:+.1f}{' pp' if key == 'long_bout_share' else '%'}"
        st.markdown(f'<div class="surface"><div class="metric-label">{METRIC_LABELS[key]}</div><div class="metric-value">{recent:,.1f}{suffix}</div><div class="metric-note">Baseline {baseline:,.1f}{suffix} · Change {change:+,.1f}{suffix} · {relative}</div></div>', unsafe_allow_html=True)


def _window_dates(comparison: dict) -> tuple[set, set, pd.Timestamp | None]:
    if comparison.get("status") != "ok": return set(), set(), None
    anchor = pd.Timestamp(comparison["anchor_date"]).date()
    return ({anchor - timedelta(days=i) for i in range(10, 30)}, {anchor - timedelta(days=i) for i in range(10)}, pd.Timestamp(anchor - timedelta(days=9)))


def _fingerprint_tab(analysis: dict) -> None:
    comparison, daily, quality = analysis["comparison"], analysis["daily"], analysis["quality"]
    if comparison.get("status") == "ok":
        st.caption(f"Baseline: prior 20 calendar days · Recent: latest 10 completed days · Qualifying days shown per metric.")
    else:
        st.info(comparison["reason"])
    cols = st.columns(4)
    for column, key in zip(cols, METRIC_LABELS):
        with column: _metric_card(key, analysis)
    available = [v for v in comparison.get("metrics", {}).values() if v["status"] == "available"]
    st.markdown('<div class="surface"><b>What this report can say</b><br><span class="metric-note">' +
                (f"{len(available)} of 4 movement comparisons meet the data policy. Changes describe this person’s observed history; they are not health scores." if available else "The current history does not meet the fixed comparison policy, so no movement trend is claimed.") +
                "</span></div>", unsafe_allow_html=True)
    chart = daily.merge(quality[["local_date", "qualifies"]], on="local_date")
    chart["quality"] = chart.qualifies.map({True: "Qualifying", False: "Excluded"})
    fig = px.bar(chart, x="local_date", y="observed_daily_steps", color="quality", color_discrete_map={"Qualifying": TEAL, "Excluded": AMBER}, labels={"local_date": "Local date", "observed_daily_steps": "Observed steps"})
    _, _, boundary = _window_dates(comparison)
    if boundary is not None: fig.add_vline(x=boundary, line_dash="dash", line_color=TEXT, annotation_text="Recent window")
    fig.update_layout(**_plot_layout("Daily observed steps"), legend_title_text="Day status")
    st.plotly_chart(fig, use_container_width=True)
    _bout_chart(analysis)


def _bout_chart(analysis: dict) -> None:
    baseline_dates, recent_dates, _ = _window_dates(analysis["comparison"])
    if not baseline_dates:
        return
    quality = analysis["quality"]
    qualifying = set(quality.loc[quality.qualifies, "local_date"])
    bouts = analysis["bouts"]
    daily = analysis["daily"]
    rows = []
    for label, dates in (("Baseline", baseline_dates), ("Recent", recent_dates)):
        dates = dates & qualifying
        total = daily[daily.local_date.isin(dates)].observed_daily_steps.sum()
        if len(dates) == 0 or total == 0: continue
        amounts = bouts[bouts.local_date.isin(dates)].groupby("bucket").step_count.sum()
        for bucket in ("<5 minutes", "5-<10 minutes", "10-<15 minutes", "15+ minutes"):
            rows.append({"Window": label, "Bout duration": bucket, "Share of observed steps": 100 * amounts.get(bucket, 0) / total})
    if not rows:
        st.info("Bout-step shares are withheld because the eligible windows have no observed steps.")
        return
    fig = px.bar(pd.DataFrame(rows), x="Window", y="Share of observed steps", color="Bout duration", barmode="stack",
                 category_orders={"Bout duration": ["<5 minutes", "5-<10 minutes", "10-<15 minutes", "15+ minutes"]},
                 color_discrete_sequence=["#718096", "#5B8FB9", "#52DECF", "#F2BC68"])
    fig.update_layout(**_plot_layout("Bout-step share in qualifying windows"), yaxis_ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True)


def _quality_tab(analysis: dict) -> None:
    quality = analysis["quality"].copy()
    cols = st.columns(3)
    cols[0].metric("Qualifying days", f"{int(quality.qualifies.sum())} / {len(quality)}")
    cols[1].metric("Median usable coverage", f"{quality.coverage.median():.1%}")
    cols[2].metric("Excluded days", int((~quality.qualifies).sum()))
    fig = px.bar(quality, x="local_date", y="coverage", color="qualifies", color_discrete_map={True: TEAL, False: AMBER}, labels={"local_date": "Local date", "coverage": "Usable coverage"})
    fig.add_hline(y=.95, line_dash="dash", line_color=AMBER, annotation_text="95% prototype threshold")
    fig.update_layout(**_plot_layout("Daily usable-minute coverage"), yaxis_tickformat=".0%", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    table = quality[["local_date", "expected_minutes", "usable_minutes", "coverage", "completed", "qualifies"]].copy()
    table["coverage"] = table.coverage.map("{:.1%}".format)
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.markdown('<div class="surface"><b>How to read coverage</b><br><span class="metric-note">A recorded zero is an observed minute with no steps. A missing observation is not treated as zero. Documented non-wear is excluded from usable minutes. Unknown wear remains an explicit limitation: record completeness does not establish wear completeness.</span></div>', unsafe_allow_html=True)


def _evidence_tab(analysis: dict, label: str) -> None:
    st.subheader("Evidence and export")
    st.caption("The report retains the engine’s fixed-window policy and explicit withheld states.")
    rhythm = rhythm_status()
    st.markdown(f'<div class="surface withheld"><div class="metric-label">RHYTHM</div><div class="metric-value">IS / IV / M10 withheld</div><div class="metric-note">{rhythm["reason"]}</div></div>', unsafe_allow_html=True)
    report = analysis["daily"].merge(analysis["quality"], on="local_date").to_csv(index=False).encode("utf-8")
    st.download_button("Download daily evidence CSV", report, file_name="signal-lab-daily-evidence.csv", mime="text/csv")
    if label.startswith("Synthetic"):
        st.warning("Synthetic demo data only — not participant data and not PMData P01.")


def _plot_layout(title: str) -> dict:
    return {"title": {"text": title, "font": {"color": TEXT, "size": 17}}, "paper_bgcolor": SURFACE, "plot_bgcolor": SURFACE,
            "font": {"color": TEXT}, "margin": {"l": 10, "r": 10, "t": 48, "b": 10}, "xaxis": {"gridcolor": "#26344B"}, "yaxis": {"gridcolor": "#26344B"}}


def main() -> None:
    st.set_page_config(page_title="SIGNAL LAB", page_icon="◈", layout="wide")
    _style()
    with st.sidebar:
        st.markdown("## SIGNAL LAB")
        st.caption("Quality-aware movement fingerprints")
        choice = st.radio("Data selection", ["Complete synthetic demo", "Demo with missing data", "Upload my CSV"])
        timezone = st.selectbox("Local timezone", ["Asia/Kolkata", "America/New_York", "Europe/London", "UTC"])
        uploaded = st.file_uploader("CSV file", type=["csv"], key=f"csv_upload_{st.session_state.get('upload_nonce', 0)}") if choice == "Upload my CSV" else None
        st.caption("Required: timestamp, steps. Optional: source, device, worn. Counts are steps during each minute.")
        consent = st.checkbox("I consent to processing this data in this session", key="consent")
        if st.button("Clear session data", use_container_width=True):
            _reset(); st.rerun()
        st.markdown("---")
        st.caption("Uploads stay in this application session’s memory and are not written to disk or sent to external services. In local execution, processing is local; hosted deployments process data on the host. Reset clears retained app state, but does not claim secure erasure of memory.")
    st.markdown('<div class="eyebrow">Personal movement analytics</div>', unsafe_allow_html=True)
    st.title("SIGNAL LAB")
    st.markdown('<div class="hero-copy">Your steps have a story. This report turns minute-level records into a transparent movement fingerprint, with the evidence and data limits shown alongside every comparison.</div>', unsafe_allow_html=True)
    if not consent:
        st.markdown('<div class="surface withheld"><b>Ready when you are</b><br><span class="metric-note">Choose a dataset, review the session-processing notice, and give explicit consent to generate a report.</span></div>', unsafe_allow_html=True)
        return
    data, label, message = _input_data(choice, uploaded, timezone)
    if message:
        st.info(message)
        return
    assert data is not None
    try:
        analysis = _analyse(data, timezone)
    except InputValidationError as exc:
        st.error(f"We could not validate this data: {exc}")
        return
    _meta(analysis, label)
    if label.startswith("Synthetic"):
        st.caption("SYNTHETIC DEMO DATA — for demonstration only.")
    fingerprint, quality, evidence = st.tabs(["Movement fingerprint", "Data quality", "Evidence & export"])
    with fingerprint: _fingerprint_tab(analysis)
    with quality: _quality_tab(analysis)
    with evidence: _evidence_tab(analysis, label)


if __name__ == "__main__":
    main()
