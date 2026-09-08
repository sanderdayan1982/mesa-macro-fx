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
- Phase 3 GBP → AUD → JPY (live) → CHF → NZD → USD migration → EUR. Phase 4 agents (`data/<ccy>/agent.json`). Phase 5 Desk / Cross-Market.

## GBP Command Center (config/gbp.json v0.2.1)

- Sources: Bank of England IADB CSV (Weekly Report B1.1.2, Money & Credit, daily rates/FX) and ONS Public Sector Finances JSON. No manual ingest, no FRED, no Blobs.
- Layers: 1 Bank of England (reserves vs PMRR £365–515bn, Policy Balance Sheet, STR/ILTR, APF QT pace, CTRF) → 2 HM Treasury / ONS (net spending = expenditure − receipts, CGNCR Z) → 3 Money & Credit flows (M4Lex, PNFC, individuals, household M4, approvals) → 4 SONIA − Bank Rate (floor, persistence rule), OSF ceiling, 5/10/20Y gilt curve.
- Lanes: `.github/workflows/refresh-gbp.yml` — weekly Thu 15:30 UTC, daily 10:30 UTC, monthly 22nd + 2nd, backfill on the 1st. One batched IADB request per lane, ≥ 2.5 s apart, never parallel; a non-CSV answer marks the batch degraded and keeps the last good JSON.
- Offline test: `python -m ingest.run --ccy gbp --lane all --backfill --fixtures fixtures/gbp --no-rss && python -m ingest.validate --ccy gbp`
- Netlify: second site from the same repo (publish ".", e.g. `gbp-command-center`), dashboard at `/gbp/`.

## AUD Command Center (config/aud.json v0.2.1)

- Sources: RBA statistical tables CSV — A3 ES balances (DAILY: total, surplus, standing facility at +25, OMO repos), A1 weekly balance sheet (ES, Australian Government deposits = TGA analogue, assets, AUD investments), A2 corridor, F1 daily (AONIA, BBSW), F2 weekly-updated AGS curve, D1/D3 monthly aggregates. AOFM tenders and OMO take-up parser pending (Phase 3).
- Anchor: RBA demand estimate for reserves $70–100bn (Jacobs, "The Road to Ample", 25 Aug 2026); OMO full allotment at target + 10 bp since 9 Apr 2025; open repo ends early 2027.
- Lanes: `.github/workflows/refresh-aud.yml` — daily 02:30 UTC, weekly Fri 08:00 UTC, monthly 2nd, backfill 1st.
- Offline test: `python -m ingest.run --ccy aud --lane all --backfill --fixtures fixtures/aud --no-rss && python -m ingest.validate --ccy aud`

## JPY Command Center (config/jpy.json v0.2.1)

- Sources (all verified 2026-09-08): BoJ daily "Sources of Changes in Current Account Balances and Market Operations" XLSX (`d_release/jd|jx|jp`, parsed by English label with aliases + structure hash — the old www3 page was suspended 2025-10-06), BoJ Accounts every ten days (HTML, thousand yen → 100m with a magnitude guard), the official BoJ Time-Series API (`stat-search.boj.or.jp/api/v1/getDataCode`: FM01 TONA daily; MD13 loans/deposits, MD02 money stock, MD01 base, MD06 monthly factor attribution incl. MASDM26 FX, MD08 CAB by sector), BoJ call-market `fcall.xlsx` snapshot, BoJ basic loan rate CSV (`cdab0101.csv`; policy = basic loan rate − 0.25, IOER = policy), MoF JGB yields CSV (`jgbcme.csv` + history), MoF auction results XLS (bid-to-cover per tenor), MoF monthly Receipts & Payments of Treasury Funds XLS (taxes, pension, FEFSA, JGB, T-Bills), MoF ITS weekly CSV (snapshot), JSDA Tokyo Repo Rate XLS (daily + history since 2012). Legacy XLS needs `xlrd` (requirements.txt).
- Layers: 1 Bank of Japan (CAB daily, excess vs required, ΔCAB, JGB purchases vs the MPM plan, pooled collateral, CLF, SLF, Accounts) → 2 MoF (treasury funds daily = DTS analogue, BoJ next-day projection, MoF monthly attribution, FEFSA = FX-intervention footprint, super-long bid-to-cover) → 3 loans / money stock / foreign banks' reserve share → 4 TONA − IOER (floor, persistence + absolute), TONA high, Tokyo Repo Rate − IOER (GC), term repo, JGB 2/10/20/30/40Y curve.
- Regime: weights CB 0.35 · rates 0.35 · fiscal 0.20 · banking 0.10; LIQUIDITY_SCARCITY price-gated only; QT_STRESS overlay (20Y−10Y, 30Y−10Y, SLF, GC, bid-to-cover); flags CLF_USED, FLOOR_LEAK, GC_ABOVE_FLOOR, SUPER_LONG_STRESS, JGB_PURCHASES_VS_PLAN_*, FX_INTERVENTION_SUSPECT, FISCAL_BIG_DAY, FOREIGN_BANK_YEN_SHORT.
- Lanes: `.github/workflows/refresh-jpy.yml` — daily 02:30 UTC (+ retry 03:30), daily_provisional 09:30 UTC, ten_day 3rd/13th/23rd, weekly Fri 04:00, monthly 15th, backfill 1st.
- Offline test: `python -m ingest.run --ccy jpy --lane all --backfill --fixtures fixtures/jpy --no-rss && python -m ingest.validate --ccy jpy`
- Netlify: same site, dashboard at `/jpy/`. Units: files in 100 million yen, dashboard in tn (10^12).

**2026-09-08 (v0.2.3)** — TONA/high/low spliced from the BoJ call-market summary (fcall, T-1) while the Time-Series API lags 2 business days (verified: API last value 09-04 at 22:22 JST 09-08); unit labels fixed in JSON (TONA volume, call outstanding, JGB purchases/issued/redeemed = 100m yen, not %).

**2026-09-08 (v0.2.2)** — BoJ daily XLSX label fix (indented rows carry empty cells in column B); projection (`jp`) fetched on the daily lane; MoF auction **calendar + per-auction result pages** parsed live (bid-to-cover, yield at lowest accepted, average yield, **tail in bp**) — the historical XLS lags ~2 months and has no average yield. New: `auction_tail_superlong_bp` (p85/p95 of 36 auctions, absolute 3/6/12 bp provisional), `auction_calendar` (days to next coupon auction, `SUPER_LONG_SUPPLY_AHEAD` ≤ 3 days), `SUPER_LONG_TAIL` flag, 'Last JGB auctions' table.
