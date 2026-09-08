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
- Phase 3 GBP → AUD → JPY → CHF → NZD → USD (all live) → EUR. Phase 4 agents (`data/<ccy>/agent.json`). Phase 5 Desk / Cross-Market.

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

## NZD Command Center (config/nzd.json v0.2.1)

- Sources (all verified 2026-09-08): RBNZ statistics workbooks at stable URLs (`/-/media/project/sites/rbnz/files/statistics/series/...`), parsed BY SERIES ID: B2 daily wholesale rates (`INM.DP1.N` OCR, `INM.DD1.N` ODR, `INM.DD2.N` ORRF, `INM.DN.NZK` overnight interbank — sparse, bank bills `INM.DB01/02/03`, NZGB `INM.DG101/102/105/110`, swaps `INM.DS01/02/10`, `INM.DS61`), D12 standing facilities (daily settlement cash, ORRF use, FX swaps, bond lending), D3 open market operations (weekly reverse-repo OMO since 2026-04-02: 7d + 28d full allotment at OCR + 10 bp; LSAP sales to NZDM NZ$415m/month; early repurchases; BMLS), D10 influences on settlement cash (monthly, header-label parser), R1 balance sheet, R3 analytical accounts (Crown settlement accounts, settlement institutions' balances, monetary base), D30 holdings by sector (57% non-resident), D9 weekly turnover, C5 sector lending, C50 money & credit, L2 core funding ratio. NZDM: tender result HTML pages (`/tender/treasury-bill-tender-<n>`, `/tender/nominal-bond-tender-<n>`, 14:35 NZT; T-bills Tuesday T+1 with 3 series, bonds Thursday T+3 with 2–3 lines), listing pages (dates + upcoming tenders), dated XLSX histories and the bonds-on-issue file (coupon / maturity calendar) linked from `/investor-resources/data`.
- Layers: 1 RBNZ (settlement cash daily = WRESBAL analog with desk dead-man anchors 20/15/10/7 bn — never a regime trigger; OMO stock, reliance share, take-up; ORRF ≥ 100 m WATCH / ≥ 500 m STRESS; residual flow = ΔSC − ΔOMO − ΔFX swaps − ΔORRF as a coincident, noisy Crown proxy with a ± band vs D10 and tagged coupon / maturity / LSAP / settlement / tax days) → 2 Crown / NZDM (R3 CSA, D10 government cash influence, tender coverage volume-weighted, tail, allocation ratio, upcoming settlements = SUPPLY_AHEAD, non-resident share, long-end turnover share) → 3 banks (housing / business+agri / broad money y/y, CFR headroom as gate only) → 4 rates (bank bill 30d − OCR raw with 25/40/60 bp anchors and persistence, hike pricing = swap 1y − OCR shown beside it and gating SCARCITY, overnight − OCR on published days, bill curve slope, 2y − OCR, 10y − 2y, bond-swap 10y, 10y Δ5d).
- Regime: weights CB 0.40 · rates 0.30 · fiscal 0.15 · banking 0.15; LIQUIDITY_SCARCITY price-gated (bills ≥ STRESS persistent AND friction confirmed AND not hike pricing); OMO_DEPENDENCE overlay (2 of 4, persistence 2 runs); flags STANDING_FACILITY_USED, FX_SWAP_ACTIVE, OMO_TAKEUP_SURGE, OMO_RELIANCE_RISING, FLOOR_LEAK, FISCAL_BIG_DAY, SUPPLY_AHEAD, TENDER_WEAK, TENDER_TAIL, TBILL_UNDERALLOCATED, COUPON_PAYMENT_DAY, BOND_MATURITY_DAY, LSAP_SALE_DAY, TAX_DAY, FOREIGN_DEMAND_FADE, PHASE_*.
- Lanes: `.github/workflows/refresh-nzd.yml` — daily 04:00 UTC (+ retry 06:00), weekly_tue 03:00 UTC (T-bills), weekly_thu 03:00 UTC (OMO + bonds), weekly_mon 04:00 UTC (D9), monthly 3rd/15th/19th, backfill 1st. Every lane rebuilds all four blocks from `history/nzd/*.csv` + `history/nzd/_side.json` (tender rows, upcoming, bonds on issue, D3 rows).
- Offline test: `python -m ingest.run --ccy nzd --lane all --backfill --fixtures fixtures/nzd --no-rss && python -m ingest.validate --ccy nzd`
- Netlify: same site, dashboard at `/nzd/`. Units: files in NZ$ millions, dashboard in bn. Pending (Phase 3): L1 mismatch, S40 deposits, B20/B21 mortgage rates, D35 Kauri, NZDM ECP, Treasury monthly statements, BKBM public feed, IRD GST/PAYE dates, holiday-aware freshness (nominal daily = 4 days covers a long weekend).

## CHF Command Center (config/chf.json v0.2)

- Sources (all verified 2026-09-08 on the SNB data portal, no auth): cubes `snbgwdzid` (policy rate, SARON, special rate, tier rates, discount, threshold factor — daily T-1 10:00 CET), `snbgwdchfsgw` (weekly sight deposits: domestic banks GI / other UEB / total TG, Monday 10:00 CET), `snbgwdmigirow` (minimum-reserve sight deposits), `bamire` (minimum reserves, monthly), `snbbipo` (monthly balance sheet: FX investments, SNB Bills ES, absorbing repos VRGSF, supplying repos FRGSF, Confederation VB, foreign sight deposits GBI, swaps GSGSF), `snbmoba`, `snbfxtr` (quarterly FX transactions), `snbmonagg` (M1–M3), `bakredinausbm` / `babilpobm` (banks), `zikrepro` (published mortgage rates), `zirepo` (SAR/compound rates, ~3-week lag), `zimoma` (3m MMDRC monthly), warehouse `SNB1A.SNB.NSS.KZS.EID` (Confederation NSS curve, 11:00 CET), list `snbbillshreg` (SNB Bills register), `gmges.en.xlsx` (money-market operations by transaction, monthly), AFF/EFV `resultate-gmbf.xlsx` (MMDRC weekly auctions) and `resultate-anleihen.xlsx` (bond auctions). Cubes `zimopo` / `snbdevterm` proposed by reviewers do NOT exist; AFF publishes no monthly cash report.
- Layers: 1 SNB (weekly sight deposits, tier parameters, absorption stock/share, Bills ladder from the register scaled to the balance-sheet ES, FX-intervention proxy, gmges operations, quarterly FX purchases) → 2 Confederation (amounts due to the Confederation monthly = cash footprint, MMDRC bid-to-cover and yield − SARON, bond auctions, own holdings) → 3 banks (loans, mortgages, deposits, liquid assets, M3, mortgage rates) → 4 SARON − absorption anchor (policy − 5 bp; absolute 5/10/20 bp with 3-session persistence, percentile guard because SARON is pinned), tier band position, SAR3M, Confederation curve.
- Regime: weights CB 0.45 · rates 0.30 · fiscal 0.10 · banking 0.15; quantity dead-man switch = sight deposits / minimum reserve requirement (3× / 1.5× / 1.1×); STERILISATION_STRESS overlay (absorption share, SARON − anchor, MMDRC bid-to-cover, other sight deposits w/w); flags FX_INTERVENTION_SUSPECT, THRESHOLD_FACTOR_CHANGE, FLOOR_LEAK, SNB_SUPPLYING, FOREIGN_SIGHT_DEPOSITS_JUMP, BILLS_ROLL_OFF_AHEAD, CONFED_CASH_BIG_MOVE, MMDRC_DEMAND_WEAK, COLLATERAL_SCARCITY, MPA_WEEK, RESERVE_PERIOD_END.
- Lanes: `.github/workflows/refresh-chf.yml` — daily 10:00 UTC Mon–Fri, weekly Mon 09:45 UTC, weekly_thu Thu 10:00 UTC (EFV), monthly 13th + 23rd, quarterly 2nd of Jan/Apr/Jul/Oct, backfill 1st. Every lane rebuilds all four blocks from `history/chf/*.csv`.
- Offline test: `python -m ingest.run --ccy chf --lane all --backfill --fixtures fixtures/chf --no-rss && python -m ingest.validate --ccy chf`
- Netlify: same site, dashboard at `/chf/`. Units: files in CHF millions, dashboard in bn (10^9). Pending (Phase 3): SIX SARON compound CSV, EFV issuance-calendar PDFs, `ausstehende-anleihen.xlsx`, Quarterly Bulletin tier distribution, publication day of `snbbipo` (confirm on the first live run).

## USD Command Center (config/usd.json v0.1.0) — migration of the three USD dashboards

- Rule: EXACT metric set and thresholds of Sander's three dashboards (H.4.1 Liquidity Command Center v2.0, DTS Tracker v3.0, H.8/H.15 Monitor v2.1) — no AI triangulation. Desk percentiles appear only as secondary context.
- Sources (verified 2026-09-08): FRED keyless CSV endpoint `fredgraph.csv?id=<ID>&cosd=` (20 ids; API fallback with `FRED_API_KEY` secret, optional); Fiscal Data API (DTS `operating_cash_balance`, `deposits_withdrawals_operating_cash`, `debt_subject_to_limit`; no key; T-1 ~16:00 ET).
- Layers: 1 Fed H.4.1 (WALCL, TREAST, WSHOMCB, WLCFLPCL, WTREGEN, WRESBAL weekly + RRPONTTLD daily; Net Liquidity = WALCL − TGA − RRP; Δ% w/w ±2%; WRESBAL 3.0T/2.5T; TGA 750/900B; RRP 200B; primary credit +20%) → 2 DTS (TGA close, totals, debt, 6 deposit + 12 withdrawal line items with Daily/MTD/FYTD, Net Treasury Flow with 30-day Z, −ΔTGA, seasonal flags) → 3 H.8 (bank credit, loans & leases, C&I weekly TOTCI, deposits, borrowings H8B3094NCBA; statuses + traffic-light vote + 26-week Z heatmap + base-100 index) → 4 SOFR − IORB (5/15/30 bp) + H.15 (DFF, DTB3, DGS2, DGS10, 10Y−2Y, FF−3M on common dates, stance, H.15 signal, forex signal matrix).
- Corrections from the primary sources (documented in `config/usd.json` → `lineage.corrections_from_primary_sources`): FRED WRESBAL/WTREGEN are $ millions (the legacy H.4.1 multiplied them by 1000); H.8 borrowings id is `H8B3094NCBA` (legacy `TLBACBW027SBOG` = total liabilities); weekly C&I is `TOTCI` (legacy `BUSLOANS` is monthly, kept as display).
- Regime: weights CB 0.40 · rates 0.25 · fiscal 0.25 · banking 0.10 (desk proposal); reserves_metric WRESBAL (3.0–4.0T ample band, 2.5T crisis); stress spread SOFR − IORB, friction confirmed on 2 of 3 sessions > 15 bp.
- Lanes: `.github/workflows/refresh-usd.yml` — daily 16:20 ET (two crons cover EDT/EST) + retry 18:00 ET, weekly_thu 16:40 ET (H.4.1), weekly Fri 16:25 ET (H.8), monthly 2nd + backfill.
- Offline test: `python -m ingest.run --ccy usd --lane all --backfill --fixtures fixtures/usd --no-rss && python -m ingest.validate --ccy usd`
- Netlify: same site, dashboard at `/usd/`. Units: files in USD millions, dashboard in $B / $T.

## JPY Command Center (config/jpy.json v0.2.1)

- Sources (all verified 2026-09-08): BoJ daily "Sources of Changes in Current Account Balances and Market Operations" XLSX (`d_release/jd|jx|jp`, parsed by English label with aliases + structure hash — the old www3 page was suspended 2025-10-06), BoJ Accounts every ten days (HTML, thousand yen → 100m with a magnitude guard), the official BoJ Time-Series API (`stat-search.boj.or.jp/api/v1/getDataCode`: FM01 TONA daily; MD13 loans/deposits, MD02 money stock, MD01 base, MD06 monthly factor attribution incl. MASDM26 FX, MD08 CAB by sector), BoJ call-market `fcall.xlsx` snapshot, BoJ basic loan rate CSV (`cdab0101.csv`; policy = basic loan rate − 0.25, IOER = policy), MoF JGB yields CSV (`jgbcme.csv` + history), MoF auction results XLS (bid-to-cover per tenor), MoF monthly Receipts & Payments of Treasury Funds XLS (taxes, pension, FEFSA, JGB, T-Bills), MoF ITS weekly CSV (snapshot), JSDA Tokyo Repo Rate XLS (daily + history since 2012). Legacy XLS needs `xlrd` (requirements.txt).
- Layers: 1 Bank of Japan (CAB daily, excess vs required, ΔCAB, JGB purchases vs the MPM plan, pooled collateral, CLF, SLF, Accounts) → 2 MoF (treasury funds daily = DTS analogue, BoJ next-day projection, MoF monthly attribution, FEFSA = FX-intervention footprint, super-long bid-to-cover) → 3 loans / money stock / foreign banks' reserve share → 4 TONA − IOER (floor, persistence + absolute), TONA high, Tokyo Repo Rate − IOER (GC), term repo, JGB 2/10/20/30/40Y curve.
- Regime: weights CB 0.35 · rates 0.35 · fiscal 0.20 · banking 0.10; LIQUIDITY_SCARCITY price-gated only; QT_STRESS overlay (20Y−10Y, 30Y−10Y, SLF, GC, bid-to-cover); flags CLF_USED, FLOOR_LEAK, GC_ABOVE_FLOOR, SUPER_LONG_STRESS, JGB_PURCHASES_VS_PLAN_*, FX_INTERVENTION_SUSPECT, FISCAL_BIG_DAY, FOREIGN_BANK_YEN_SHORT.
- Lanes: `.github/workflows/refresh-jpy.yml` — daily 02:30 UTC (+ retry 03:30), daily_provisional 09:30 UTC, ten_day 3rd/13th/23rd, weekly Fri 04:00, monthly 15th, backfill 1st.
- Offline test: `python -m ingest.run --ccy jpy --lane all --backfill --fixtures fixtures/jpy --no-rss && python -m ingest.validate --ccy jpy`
- Netlify: same site, dashboard at `/jpy/`. Units: files in 100 million yen, dashboard in tn (10^12).

**2026-09-08 (v0.2.3)** — TONA/high/low spliced from the BoJ call-market summary (fcall, T-1) while the Time-Series API lags 2 business days (verified: API last value 09-04 at 22:22 JST 09-08); unit labels fixed in JSON (TONA volume, call outstanding, JGB purchases/issued/redeemed = 100m yen, not %).

**2026-09-08 (v0.2.2)** — BoJ daily XLSX label fix (indented rows carry empty cells in column B); projection (`jp`) fetched on the daily lane; MoF auction **calendar + per-auction result pages** parsed live (bid-to-cover, yield at lowest accepted, average yield, **tail in bp**) — the historical XLS lags ~2 months and has no average yield. New: `auction_tail_superlong_bp` (p85/p95 of 36 auctions, absolute 3/6/12 bp provisional), `auction_calendar` (days to next coupon auction, `SUPER_LONG_SUPPLY_AHEAD` ≤ 3 days), `SUPER_LONG_TAIL` flag, 'Last JGB auctions' table.
