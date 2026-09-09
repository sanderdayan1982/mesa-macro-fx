# JPY — calibración empírica del régimen dual (A + B), 2026-09-09

Replay as-of semanal 2023-04 → 2026-09 (168 semanas; `ingest/calibrate.py --ccy jpy --fixtures fixtures/jpy_hist`). Datos primarios capturados hoy: el diario "Sources of Changes in Current Account Balances" del BoJ (Bank of Japan) reconstruido desde el archivo HTML de www3 (674 sesiones, 2023-01 → 2025-10) más los XLSX actuales; cuentas del BoJ cada diez días (99 balances, archivo HTML 2023–2025); TONA (Tokyo Overnight Average Rate) y USD/JPY 9:00 Tokio (FM08 FXERD01) del API de series temporales del BoJ desde 2015; tipo básico de préstamo por escalones verificados en el propio TONA (0,3 → 0,5 ago-2024 → 0,75 ene-2025 → 1,0 dic-2025 → 1,25 jun-2026); resultados de subastas del MoF (Ministry of Finance): JGB (Japanese Government Bond) por plazo desde 1979 (1.915) y letras desde 2009 (1.397). Detalle en `calibration/jpy/`.

## Era válida

Fin del NIRP (Negative Interest Rate Policy) y del YCC (Yield Curve Control) el 19-mar-2024; primera subida y suelo de tipos positivos con IOER (Interest On Excess Reserves) desde el **31-jul-2024**: 102 semanas de era comparable. Antes de eso el config no tiene sentido (tipos negativos, compras ilimitadas).

## Resultado central: el bloque BC del JPY no discrimina

La puntuación BC vale **+0,5 el 81 % de las semanas** de la era (0,0 el 15 %, +1,0 el 4 %; n 102). Causa: el ancla "exceso / requerido" está en ~35× (saldos en cuenta corriente 495 bn frente a un requerido diario de 13 bn), así que el componente "sobre el rango → +0,75" es una constante, y los demás componentes (Δ CAB 20 sesiones, Δ d/d, CLF — Complementary Lending Facility) rara vez salen de SAFE. Con ±0,5 el JPY está en "INYECCIÓN" permanente mientras el BoJ hace QT (compras 3 bn/mes → 2 bn/mes) — es el caso extremo del defecto ya visto en GBP y AUD. Lo que la historia permite decir: INJECTION ≥ +1,0 (4 %), DRAIN ≤ 0,0 (15 %), y que **el bloque hay que rediseñarlo** para la v0.3: la inyección/drenaje debe salir de los flujos (Δ CAB neto de banknotes, compras de JGB menos vencimientos = ritmo de QT de las cuentas decenales, operaciones de fondos) y el ratio exceso/requerido quedarse como dead-man a 0,25.

Tesoro (flujo diario "Treasury funds and others", Z de 250 sesiones × 0,75): distribución continua y estable — p10 −0,67 · p20 **−0,33** · p50 +0,08 · p80 **+0,30** · p90 +0,49; por año p20/p80: −0,29/+0,23 (2024), −0,21/+0,32 (2025), −0,44/+0,29 (2026). Con ±0,5 sólo marca 17 % DRENAJE / 10 % INYECCIÓN porque la escala está comprimida. Propuesta: INJECTION ≥ +0,30 (salida +0,17), DRAIN ≤ −0,33 (salida −0,12).

## B. Verdad de funding: no evaluable todavía

TONA − IOER en la era: p10 −2,4 pb · mediana −2,3 · p90 −2,2. El spread vive en 0,2 pb de rango; no hay varianza que explicar. BC ρ +0,22 a 12 semanas (p 0,04) con signo contrario y n 90 — descartado. Tesoro ρ ≈ 0. Habrá que usar otra verdad de funding para el yen (repo GC de la JSDA — Japan Securities Dealers Association — o el uso del CLF) cuando haya historia.

## Control FX

USD/JPY: BC ρ −0,06/−0,06/+0,08, Tesoro +0,03 en los tres horizontes, todo p > 0,3; ningún corte sobrevive; sin pesos duales.

## Subastas MoF: anclas por plazo (últimos 3 años, n ≈ 35 por plazo)

| plazo | p10 histórico / mediana | p10 3 años / mediana | ancla WATCH (≤ p10 3 a) · STRESS (≤ p5 hist.) |
|---|---|---|---|
| JGB 2 a | 1,79 / 3,71 | 3,09 / 3,70 | 3,1 · 1,5 |
| JGB 5 a | 2,47 / 3,51 | 3,13 / 3,70 | 3,1 · 2,0 |
| JGB 10 a | 2,26 / 3,27 | 2,86 / 3,24 | 2,9 · 2,0 |
| JGB 20 a | 2,17 / 3,28 | 2,97 / 3,28 | 3,0 · 1,9 |
| JGB 30 a | 2,96 / 3,47 | 2,95 / 3,41 | 2,9 · 2,9 (la cola larga apenas cambió) |
| JGB 40 a | 2,26 / 2,87 | 2,18 / 2,56 | 2,2 · 2,2 |
| Letras (3 m / 6 m / 1 a) | 2,95 / 4,10 | 2,72 / 3,24 | 2,7 · 2,7; tail WATCH ≥ 1,7 pb (p90) · STRESS ≥ 2,2 (p95) |

El MoF no publica rendimiento medio en JGB, por lo que no hay tail de bonos; el de letras sí. Efecto FX: las letras "fuertes" dan t = −34, que es un artefacto de era (las coberturas de 8× son de 2020–21, cuando el yen se apreciaba por otras razones); los JGB no muestran nada estable. Anclas por frecuencia, no por FX, igual que en las otras siete.

## Propuesta para `config/jpy.json`

`regime.dual.block_thresholds`: BC INJECTION ≥ +1,0 / DRAIN ≤ 0,0 (provisional, bloque a rediseñar en v0.3), Tesoro INJECTION ≥ +0,30 / DRAIN ≤ −0,33 con salida +0,17 / −0,12; régimen general por regla de acuerdo; sin pesos duales; anclas de subasta por plazo como arriba. Verdad de funding pendiente de una serie con varianza (repo GC JSDA desde 2025-06 en los fixtures; CLF).

## Corrección conjunta (v2, tras la triangulación)

Reparto corregido: +0,5 el 81 % (no 85 %), 0,0 el 15 %, +1,0 el 4 % (n 102). B: el BC a 12 semanas da ρ +0,22 con signo contrario y q FDR 0,17 / 0,35: nada. Etiqueta `provisional_era_corta` + bloque a rediseñar.
