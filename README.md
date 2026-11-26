# SIGNAL LAB — Personal Movement Intelligence
wHACKiest 2026 · Track 03 · Team LSD

A local-first workbench that turns minute-level step data into a **Personal Intelligence Brief**:
question first → evidence → your own context → intelligence, with an explicit "NOT ENOUGH RELIABLE DATA TO INTERPRET" outcome.

## Run it
```bash
# 1. backend (Python 3.10+)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --port 8000

# 2. frontend (Node 18+), second terminal
cd frontend && npm install && npm run dev      # http://localhost:5173  (proxies /api to :8000)
```
Upload a minute-level CSV, or a Fitbit-style `steps.json` (`dateTime`,`value`), or press **Use synthetic demo**.
For PMData P01, set the latest completed date to 2020-02-19 to reproduce the documented comparison.

## Test it
```bash
cd backend  && python -m pytest        # engine, API, and the P01 reference reproduction
cd frontend && npm test && npm run build
```
The P01 test reads the raw file from `$PMDATA_STEPS` (default `/mnt/user-data/uploads/steps.json`) and is skipped if absent.
PMData is CC BY-NC 4.0 (Thambawita et al., MMSys '20); it is **not** bundled. Repo fixtures are synthetic.

## What works
Import + column mapping + pre-analysis validation · quality audit (observed zero ≠ missing ≠ known non-wear ≠ unknown wear) ·
bout structure, peak 1-min and top-30 cadence, daily steps/variation/trend · 20/10-day baseline comparison ·
Insight Integrity Check (Comparison available / Observed data only / Withheld) · Context Lens (never touches calculations) ·
Evidence Ledger · five-part brief · session reset.

## What is deliberately not here
Sleep, heart and recovery (roadmap only, labelled) · rhythm IS/IV/M10 on real data (withheld: no independent wear evidence) ·
database, auth, cloud, LLM calls, PDF export. See `docs/METHODOLOGY.md`.
