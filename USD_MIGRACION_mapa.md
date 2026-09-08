# USD — migración de los tres dashboards a la mesa (config/usd.json v0.1.0, 2026-09-08)

Regla de Sander: **exactamente las métricas y umbrales** de los tres dashboards, sin triangulación con otras IA. Todo lo que aparece aquí se verificó en la fuente primaria el 2026-09-08 (FRED por CSV sin clave; Fiscal Data API).

## Mapa 1:1 → cuatro capas

| Dashboard legado | Métrica / regla | Capa · métrica en la mesa |
|---|---|---|
| H.4.1 v2.0 | Fed Net Liquidity = WALCL − WTREGEN − RRPONTTLD | 1 · `net_liquidity` (semanal, fechas H.4.1; RRP = última observación ≤ fecha; semanas sin TGA/RRP se omiten, nunca cero) |
| H.4.1 | Weekly Net Liquidity Δ% ≥ +2 % RISK-ON · ≤ −2 % RISK-OFF | 1 · `net_liquidity_wow_pct` (señal absoluta ±2 %; percentil sólo informa) |
| H.4.1 | Reserve Balances WRESBAL < 3.0T NERVOUS · < 2.5T CRITICAL | 1 · `reserves` (WATCH < 3.0T, CRISIS < 2.5T) + `reserves_status` (AMPLE/NERVOUS/CRITICAL) |
| H.4.1 | TGA WTREGEN ≥ 750B DRAIN WATCH · ≥ 900B HEAVY DRAIN · > 800B = HIGH DRAIN (matriz) | 1 · `tga` (WATCH/STRESS) + `tga_status` |
| H.4.1 | ON RRP ≥ 200B WATCH | 1 · `on_rrp` (diario) + `rrp_status` |
| H.4.1 | Primary Credit WLCFLPCL +20 % semanal = PANIC | 1 · `primary_credit` + `primary_credit_wow_pct` (CRISIS > 20) |
| H.4.1 | WALCL, TREAST, WSHOMCB (assets tracker), tabla semanal, stacked drains TGA + RRP | 1 · `total_assets`, `treasury_securities`, `mbs`, `total_assets_wow`, `drains_total`, history 52 semanas |
| H.4.1 | Tabla de límites, Forex Signal Matrix, speedometer, spread table, signal log | 1 · tarjeta de límites · 4 · `forex_signal_matrix`, speedometer, tabla 10 sesiones · HISTORY signal log |
| DTS v3.0 | TGA Closing Balance, Debt Held by the Public, Total Public Debt | 2 · `tga_closing`, `tga_opening`, `debt_public`, `debt_intragov`, `debt_total`, `debt_limit` |
| DTS | 6 depósitos + 12 retiros (Daily / MTD / FYTD) | 2 · `dep_*` (6), `wd_*` (12) con campos `mtd` y `fytd`; tarjetas-tabla por grupo |
| DTS | Net Spending = Withdrawals − Debt Redemptions; Net Deposits = Deposits − Debt Issues; NTF = NS − ND (signo Mosler) | 2 · `net_spending`, `net_deposits`, `net_treasury_flow` (+ `_mtd`, `_fytd`) |
| DTS | Z-score 30 d, media, σ, 7-day cumulative, ΔTGA reserve impact = −ΔTGA, seasonal flags | 2 · `net_treasury_flow.zscore/badge`, `ntf_mean_30d`, `ntf_sd_30d`, `net_treasury_flow_7d`, `tga_reserve_impact`, `seasonal_flag` |
| H.8 v2.1 | Bank Credit, Loans & Leases, C&I, Deposits, Borrowings + Δ% semanal con estados | 3 · `bank_credit`, `loans_leases`, `ci_loans` (**TOTCI**), `deposits`, `borrowings` (**H8B3094NCBA**) + `*_wow_pct.badge` |
| H.8 | Heatmap Z 26 semanas, índice base 100, semáforo (≥ 3 verdes / ≥ 3 rojos / < 3 válidas) | 3 · `history.heatmap`, `*_idx`, `transmission_signal` |
| H.15 v2.1 | DFF, DTB3, DGS2, DGS10; 10Y−2Y; FF−3M (fechas comunes); stance; señal H.15 | 4 · `fed_funds`, `tbill_3m`, `ust_2y`, `ust_10y`, `curve_10y_2y_bps`, `ff_minus_3m_bps`, `fed_funds_stance`, `rates_signal` |
| H.4.1 | SOFR − IORB 0–5 safe · 15–30 stress · > 30 crisis (NORMAL / STRESS / CRITICAL; USD WATCH / USD BULLISH) | 4 · `sofr_minus_iorb_bps` (spread de estrés del régimen; WATCH > 5, STRESS > 15, CRISIS > 30) |

Añadidos de la mesa (contexto, no cambian niveles): percentiles/Z en cada tarjeta, `ust_10y_5d_change_bps`, `tga_dod`, fase de balance (Δ WALCL 13 semanas), régimen fiscal (NTF 7 d + Z), calendario FOMC/festivos, alertas/escenarios del estándar.

## Correcciones desde la fuente primaria (no son triangulación)

1. **Unidades H.4.1**: FRED publica WRESBAL y WTREGEN en **millones** (2,894,531 = 2,89 T; 967,935 = 968 B); sólo RRPONTTLD va en miles de millones. El `UNITS` de v2.0 multiplicaba WRESBAL/WTREGEN ×1000 → reservas siempre "AMPLE" y Net Liquidity ≈ −1 T. Con las unidades correctas la lectura de hoy es **WRESBAL 2,89 T = NERVOUS** y **TGA 968 B = HEAVY DRAIN** bajo tus propios umbrales.
2. **H.8 Borrowings**: `TLBACBW027SBOG` es *Total Liabilities*; el de préstamos es `H8B3094NCBA` (semanal, SA, $M; `BOWACBW027SBOG` discontinuado).
3. **H.8 C&I**: `BUSLOANS` es mensual; el semanal del H.8 es `TOTCI`. BUSLOANS se conserva como tarjeta mensual.
4. **DTS**: las filas de totales llegan con `transaction_catg = "null"` (una de depósitos y otra de retiros por fecha) — el buscador de "total" del Tracker sólo funcionaba por el fallback de `operating_cash_balance`; aquí se usan ambos y se reconcilian (exacto el 2026-09-04: 17,562 / 32,567). "Dept of Defense (DoD) - misc" y "HHS - misc" existen en las dos caras: se filtra por tipo.

## Lectura offline 2026-09-08 (fixtures capturados en vivo)

NEUTRAL 0,343. Fed **DRAIN −0,7** (WRESBAL 2,89 T NERVOUS, TGA 968 B HEAVY DRAIN, RRP 0,6 B LOW, NL Δ% −0,19 %, primary credit +8 %, fase STEADY). Tesoro NEUTRAL (NTF +2,5 B, Z −0,41, 7 d +164,6 B, TGA cierre 888,9 B). Bancos **GREEN** (5/5 verdes; borrowings −1,4 %). Tipos **GREEN** (SOFR − IORB 0 pb, 10Y−2Y +41, FF−3M −14, EFFR 3,63 ELEVATED). Flags PHASE_STEADY, TGA_HEAVY_DRAIN. Calidad 99.
