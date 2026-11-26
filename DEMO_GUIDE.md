# SIGNAL LAB demo guide

## Three-minute judge walkthrough

1. Open the app, select **Complete synthetic demo**, and give session-processing consent.
2. Point out the source/date/quality strip, then open **Movement fingerprint**. Explain that cards compare fixed calendar windows from the same person's history, not a population target.
3. Open a card's **Evidence** panel. Show the definition, formula, qualifying-day counts, coverage limitation, evidence ID, and calculation version.
4. Open **Data quality**. Explain that missing minutes are not zeros and that the visible 95% threshold is a prototype policy.
5. Open **Evidence & export**. Show the structured JSON, daily metrics, bouts, self-contained HTML report, and example CSV downloads.
6. Switch to **Demo with missing data**. Show that the recent window has only six qualifying days and comparisons are withheld rather than replaced with older data.
7. Use **Clear session data** to return to the consent state.

## Suggested team explanations

- **Data/engine teammate:** minute-step validation, timezone/DST safety, missing versus zero, non-wear, and bout boundaries.
- **Analytics teammate:** daily metrics, the 20-day baseline/10-day recent calendar windows, and 14/7 eligibility requirements.
- **Product/UI teammate:** quality-first dashboard, evidence panels, consent/session reset, and downloadable offline report.
- **Evidence teammate:** input SHA-256 fingerprint, stable evidence IDs, what exports contain, and why withheld states are useful.

## Honest answers for judges

- **Does it use AI?** No. The application is deterministic Python analytics and does not make external AI requests.
- **Does it make medical claims?** No. It is descriptive, does not diagnose or infer causes, and does not claim clinical or statistical significance.
- **Does it connect to real wearables?** Not in this MVP. It accepts exported minute-level CSV data and does not authenticate sensor measurements.
- **Why are IS, IV, and M10 missing?** They are intentionally withheld until suitable wear evidence and a separately validated rhythm module are available.
- **Did you reproduce PMData P01?** No. PMData P01 results have not been reproduced unless the actual source data and method are independently verified.

## Demo safeguards

Keep the synthetic-data label visible. Do not claim that the synthetic example is real user data, a clinical validation, or evidence of health outcomes. The degraded demo is deliberate: it demonstrates the product's refusal to overstate a comparison when data quality is inadequate.
