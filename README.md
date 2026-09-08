# Mesa Macro FX — G8 Liquidity Desk

Institutional decision-support desk (MMT/Mosler) for the G8 currencies. One command center per currency, one shared
engine, one config file per currency. **CAD is the flagship (Phase 2).** Nothing here executes trades.

```
config/cad.json            ← the only place thresholds, series IDs, weights and calendars live
schema/block.schema.json   ← contract between ingestion, frontend and agents
ingest/                    ← Python 3.9+ ingestion (Valet, Receiver General → data/cad/*.json)
data/cad/*.json            ← what the frontend and the agent read (committed by the workflow)
history/cad/*.csv          ← append-only full history per series (percentile windows)
logs/cad/                  ← oplog, alerts, revisions, regime_history
cad/index.html             ← CAD Command Center (static, reads ../data/cad/*.json)
index.html                 ← desk landing page
.github/workflows/refresh.yml
netlify.toml               ← publish "." ; no-cache on /data/*
fixtures/cad/              ← real snapshots (2026-09-08) for offline runs and tests
```

## Deploy (GitHub web UI → Netlify)
1. Create a repo `mesa-macro-fx` on GitHub and upload this folder (drag & drop keeps the structure; include `.github/`).
2. Netlify → *Add new site* → import the repo. Build command empty, publish directory `.` (netlify.toml already says so).
3. GitHub → *Actions* → **refresh-data** → *Run workflow* with `lane=all`, `backfill=true`. First run fetches the full
   history (Valet from 2005, Receiver General archive), writes `data/cad/`, validates against the schema, commits.
   Netlify redeploys automatically. Open `https://<site>.netlify.app/cad/`.
4. From then on the lanes run alone: weekly (Fri 20:00 WAT), daily (Mon–Fri 22:30 WAT), monthly (Mon 06:00 UTC),
   full revalidation on the 1st. The 1st-of-month run also keeps the schedule alive (GitHub disables crons after 60
   days without repository activity; workflow commits count as activity).

Secrets: none for CAD (Valet and open.canada.ca need no key). USD will need `FRED_API_KEY`.

## Run locally (macOS, /usr/bin/python3 3.9 works)
```
pip3 install -r requirements.txt
python3 -m ingest.run --ccy cad --lane all --backfill            # live
python3 -m ingest.run --ccy cad --lane all --backfill --fixtures fixtures/cad   # offline, real snapshot
python3 -m ingest.validate --ccy cad
python3 -m http.server 8765   →  http://localhost:8765/cad/
```

## Layers (fixed order in every currency)
1. **Central bank liquidity** — Net Liquidity = Total assets − GoC deposits − SRA; reserves vs BoC 50–70B range;
   QT/QE tracker; Advances (SLF) stress monitor; currency drain; balance-sheet phase.
2. **Treasury / fiscal equivalent** — Receiver General Daily Cash Balance: reserve impact, fiscal flow proxy,
   30-day Z, 7-day cumulative, fiscal regime; weekly Valet cross-check. Spending creates NFA, taxes destroy NFA,
   issuance drains reserves without changing NFA.
3. **Banking transmission** — chartered banks C1/C2 (monthly, ~75-day lag): deposits, personal loans, BoC deposits
   on bank books; StatCan credit aggregates pending; transmission signal.
4. **Rates & money market** — CORRA − deposit rate (deposit = target − 5 bp since 2025-01-30), band position,
   CORRA − target, dispersion p95−p5, 10Y−2Y, target − 3M.

Regime: weights CB 0.45 · rates 0.25 · fiscal 0.20 · banking 0.10. `LIQUIDITY_SCARCITY` = reserves below range AND
spread ≥ STRESS; `FLOOR_FRICTION` = reserves in range AND spread ≥ WATCH. Flags: `TRANSMISSION_FAILURE`, `PHASE_*`.

## Adding a currency
Copy `config/cad.json` → `config/gbp.json`, map the four blocks to the new sources, add a provider class in
`ingest/providers.py` if the API differs, add `gbp` to the workflow matrix, copy `cad/index.html` → `gbp/index.html`
and change `CCY`. The engine, thresholds, quality, alerts and schema are shared.

## Phase status
- Phase 1 Desk Standard + CAD source map: sealed (v0.3, triangulated 2026-09-08).
- Phase 2 CAD flagship: **this repo**. Pending: StatCan credit tables, auction net issuance, RG archive backfill on first live run.
- Phase 3 GBP → CHF → AUD → NZD → JPY → EUR. Phase 4 agents (`data/<ccy>/agent.json`). Phase 5 Desk / Cross-Market.
