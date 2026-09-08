# FASE 1 — NZD Command Center · Mapa de fuentes (verificado en primaria el 2026-09-08)

Desk Standard v0.3 · cuatro capas fijas · ninguna métrica se oculta (fresh / stale / proxy / degraded / unavailable) · sólo soporte a la decisión.
Sitio previsto: `mesa-macro-fx-g8-commands-centers.netlify.app/nzd/` · config `config/nzd.json` v0.1 (propuesta, pendiente de triangulación).

## 0. Qué hay que entender del NZD antes de mirar un solo dato

1. **Sistema de suelo puro.** El RBNZ (Reserve Bank of New Zealand) remunera TODO el settlement cash (saldos ESAS, Exchange Settlement Account System) al OCR (Official Cash Rate). Suelo = ODR (Overnight Deposit Rate) = OCR; techo = ORRF (Overnight Reverse Repurchase Facility) = OCR + 50 pb. No hay tiering ni reservas mínimas. La cantidad no manda: "lo que importa es el precio (OCR), no la cantidad" (marco RBNZ).
2. **El settlement cash se está vaciando.** Los bonos del LSAP (Large Scale Asset Purchase) vencen y el RBNZ vende NZ$ 415 m al mes a NZDM (New Zealand Debt Management); el FLP (Funding for Lending Programme) se repagó del todo en diciembre de 2025. Settlement cash 24,6 bn (07-sep-2026) frente a ~50 bn en 2022 y 7–8 bn antes del COVID.
3. **Nuevo marco desde el 2 de abril de 2026.** Tras la Liquidity Management Review (discurso 19-mar-2026, A. Richardson), el RBNZ suministra reservas con **OMO (open market operations) de reverse repo semanales, los jueves 11:30 NZT, a 7 y 28 días, full allotment, a OCR + 10 pb**. Como el precio es fijo, la señal está en la **cantidad tomada** (5,07 bn el 03-sep-2026 ≈ 20 % del settlement cash). No hay nivel objetivo numérico: "ample" se juzga por tipos cortos pegados al OCR y liquidación fluida.
4. **Ciclo de subidas.** OCR 2,25 % (nov-2025 → may-2026) → 2,50 % (08-jul-2026) → **2,75 % (02-sep-2026, MPS)**; CPI 4,1 % a/a (Q2-2026); "el OCR puede tener que subir más". Los spreads de bank bills contra OCR llevan expectativa de subida, no sólo estrés: hay que corregirlo (swap 1a − OCR).
5. **Sin caja diaria del Tesoro.** La Crown Settlement Account (CSA) sólo se publica mensual (R3, día 14) y el "Government cash influence" mensual (D10, último día del mes siguiente). La mesa deriva la huella fiscal diaria como residuo: Δ settlement cash − Δ OMO − Δ FX swaps − Δ ORRF.
6. **Tenders NZDM.** T-bills los martes 14:00–14:30 NZT; bonos los jueves 14:00–14:30 NZT (NZ$ 450 m por tender en septiembre 2026, liquidación T+3 hábiles); programa 2026/27 NZ$ 34 bn; sindicación 15-may-2038 NZ$ 7,0 bn (14-jul-2026). El 57 % de los NZGB nominales está en manos de no residentes (D30, jul-2026).

## 1. Capa 1 — Banco central (RBNZ)

| Serie | Fuente | Frecuencia / hora | Verificado 2026-09-08 |
|---|---|---|---|
| Settlement cash (ESAS) | D12 `hd12.xlsx` hoja *Standing Facilities* (col A fecha serial, B settlement cash, C ORRF, E FX swaps) | diaria, T-1, 15:00 NZT | 07-sep: **24 588** m; 6 905 filas desde 1999 |
| Uso ORRF (techo) | D12 col C | diaria | 0 |
| FX swaps RBNZ | D12 col E | diaria | 0 |
| Bond Lending Facility | D12 hoja *Bond Lending Facility* | por operación | 20-ago: 1 m NZGB |
| OMO reverse repo semanal | D3 `hd3.xlsx` hoja *Reverse Repo - OMO* (fecha, vencimiento, volumen, spread a OCR) | jueves 11:30 NZT; nuevo marco desde 02-abr-2026 | 03-sep: 5 023 m a 7 d + 45 m a 28 d, +0,10 |
| Stock OMO vivo | derivado de D3 (asignaciones − vencimientos) | diaria | ≈ 5,1 bn |
| Ventas LSAP a NZDM | D3 hoja *LSAP bond sales* (valor facial NZ$) | mensual, ~día 17 | 17-ago: 415 m; acumulado 20 830 m |
| Recompras anticipadas de NZGB | D3 hoja *Govt Bond Repurchases* | evento | feb-2026: 57 m (línea abr-2026) |
| BMLS holdings | D3 hoja *BMLS* | diaria | NZGB 20 m / LGFA 70 m |
| Balance R1 | `hr1.xlsx` | mensual, ~día 14 (jul publicado 14-ago; próximo 14-sep) | activos 73 237; LSAP 11 860; reverse repos 15 926; depósitos 55 428; circulante 10 241 |
| Cuentas analíticas R3 | `hr3.xlsx` | mensual, ~día 14 | Crown settlement accounts **29 080**; saldos de instituciones de liquidación 25 819; base monetaria 36 057; activos exteriores netos 44 085 |
| Influencias sobre el settlement cash D10 | `hd10.xlsx` | mensual, último día del mes siguiente (jul publicado 31-ago) | gov cash influence **+6 846**; bonos emitidos −7 840; T-bills −1 001 / +1 705; FX +266; net reverse repos +540; net FX swaps +1 154 |

Anclas de cantidad (propuesta de mesa, el RBNZ no publica nivel suficiente): ample > 20 bn · WATCH < 15 · STRESS < 10 · CRISIS < 7 bn — dead-man switch; la escasez se lee en precio. Métrica estructural nueva: **omo_reliance_share** = stock OMO / settlement cash (anclas 30 % / 45 %, propuesta).

## 2. Capa 2 — Tesoro / NZDM

| Serie | Fuente | Frecuencia | Verificado |
|---|---|---|---|
| Crown Settlement Account | R3 memo | mensual, día 14 | jul-2026 29 080 m |
| Government cash influence, bonos/T-bills emitidos y vencidos | D10 | mensual | ver arriba |
| Tender T-bills | NZDM `Tbills-tender-history-<fecha>.xlsx` (hoja única, cabecera fila 5; nombre de fichero con fecha → el parser lee la página *Data*) | martes 14:30 NZT | 08-sep tender 1887: ofrecido 100, pujado 255 (**2,55x**), wavg **2,8775 %**, vence 18-nov-2026 |
| Tender bonos nominales | `govtbonds-tender-history-<fecha>.xlsx` hoja *Nominals* (coverage ratio, wavg, highest accepted → **tail**) | jueves 14:30 NZT | 03-sep tender 1007, 15-may-2030 4,5 %: 275 m, pujado 1 115, **4,05x**, wavg 4,0227 %, tail 0,5 pb |
| Tender IIB | hoja *IIBs* | con los nominales según demanda | 27-ago tender 1006: 25 m, 4,32x |
| Calendario de tenders | statement mensual "Tender Schedule – <mes>" | última semana del mes anterior | sep-2026: 1007–1010 los 3/10/17/24, 450 m cada uno, 1 800 m total |
| Tenencias no residentes | D30 `hd30.xlsx` | mensual, ~día 18 | jul-2026: 118 400 de 206 463 nominales (57 %) |
| Estados financieros mensuales del Tesoro | treasury.govt.nz | mensual, ~6 semanas | 11 meses a 31-may-2026 = último; confirmación (Fase 3) |

Huella fiscal diaria = derivación de mesa `autonomous_flow_daily` (residuo del settlement cash tras operaciones RBNZ), reconciliada cada mes con D10.

## 3. Capa 3 — Transmisión bancaria

| Serie | Fuente | Frecuencia | Verificado |
|---|---|---|---|
| Crédito por sector (vivienda, empresas, agro, consumo) | C5 `hc5.xlsx` | mensual, último día del mes siguiente | jul-2026: vivienda 401 944 (+5,6 %), empresas 142 861 (+4,4 %), agro 65 238 (+2,4 %), consumo 14 425 (+1,9 %) |
| Broad money, crédito | C50 `hc50.xlsx` | mensual | broad money 458 490 (jul-2025 439 451) |
| Core funding ratio | L2 `hl2.xlsx` | mensual, ~día 3 | jul-2026: **89,2 %** (mínimo 75 %); core funding 525 269; préstamos 588 845 |
| Mismatch ratios 1s/1m | L1 | mensual | pendiente de inspección |
| Depósitos por sector, balance bancario | S40 / S10 | mensual | pendiente de ruta de fichero |
| Tipos hipotecarios | B20 / B21 / B30 | mensual | pendiente |

C65/C66 (flujos semanales de crédito) se **discontinuaron en abril de 2021** — no hay crédito semanal.

## 4. Capa 4 — Tipos y mercado monetario

B2 `hb2-daily-close.xlsx` hoja *Data*, fila "Series Id" (parser por id, nunca por columna); diario T-1 a las 15:00 NZT.

| Id | Serie | 07-sep-2026 |
|---|---|---|
| INM.DP1.N | OCR | 2,75 |
| INM.DD1.N | ODR (suelo) | 2,75 |
| INM.DD2.N | ORRF (techo) | 3,25 |
| INM.DN.NZK | Overnight interbank (sólo días con cruces; escaso) | 2,83 el 03-sep, 2,57 el 01-sep |
| INM.DB01/02/03.NZZV | Bank bills 30/60/90 d | 2,95 / 3,00 / 3,06 |
| INM.DG101/102/105/110.NZZCF | NZGB 1/2/5/10 a | 3,10 / 3,61 / 4,21 / 4,78 |
| INM.DS01…DS15.NZZC, DS61 | Swaps 1–15 a, spread 2-10 | 75 pb |
| D9 `hd9-weekly.xlsx` | Turnover semanal NZGB (lunes) | semana al 04-sep: 71 033 m |

Spread de estrés propuesto: **bank bill 30 d − OCR** (diario, persistente 3 sesiones; anclas 25/40/60 pb, propuesta) con confirmación por overnight interbank ≥ OCR + 10 o uso del ORRF, y corrección por `hike_pricing_bps` (swap 1 a − OCR). Complementos: BKBM 90 d − OCR (idea V3.1), 2s10s, bond-swap 10 a, Δ5d del 10 a.

## 5. Calendario y lanes

- MPC (Monetary Policy Committee): 28-oct-2026 (review), 09-dic-2026 (MPS); 2027: 10-feb, 17-mar (MPS), 05-may, 16-jun (MPS), 04-ago, 15-sep (MPS), 27-oct, 08-dic (MPS); 09-feb-2028. 14:00 NZT. Ocho decisiones al año desde 2027.
- Publicación diaria RBNZ después de las 15:00 NZT = 03:00 UTC (NZST) / 02:00 UTC (NZDT, desde el 27-sep-2026). Lane diario 04:00 UTC + reintento 06:00 UTC.
- Martes 03:00 UTC (tender T-bills), jueves 03:00 UTC (OMO + tender bonos), lunes (D9), mensual 3/15/19 + backfill día 1.

## 6. Qué se rescató y qué se descartó del NZD Command Center V3.1

Rescatado como idea: cambio semanal del settlement cash, CSA como disparador fiscal (pasa a mensual porque no existe semanal), *tender load ratio*, BKBM − OCR, 2s10s, crédito vivienda / productivo, core funding. Descartado: datos estáticos "live-ready", puntuación compuesta 0–100, refresco de 60 s, y los overlays de precio/externos (Global Dairy Trade, comercio Stats NZ, TWI) — no son liquidez; viven en la pestaña Desk cross-market.

## 7. Pendiente antes de Fase 2

Ver `config/nzd.json → pending_before_phase2`: anclas absolutas a triangular, convención de liquidación de T-bills, L1/S40/B20-21/swaps, calendario de vencimientos y cupones NZGB (fichero on-issue), festivos NZ, parser del Tesoro (Fase 3).

Fuentes primarias consultadas: rbnz.govt.nz/statistics (D12, D3, D10, R1, R3, B2, D9, D30, C5, C50, L2), rbnz.govt.nz key facilities (actualizado 02-abr-2026) y discurso Kanga News 19-mar-2026, rbnz.govt.nz OCR decision dates to Feb-2028, comunicado OCR 02-sep-2026, debtmanagement.treasury.govt.nz (Data, Media statements, Tender Schedule September 2026), treasury.govt.nz month-end financial statements.
