# CHF — calibración empírica del régimen dual (A + B), 2026-09-09

Replay as-of semanal 2012-01 → 2026-09 (766 semanas; `ingest/calibrate.py --ccy chf --fixtures fixtures/chf_hist --era 2022-09-22`). Datos primarios capturados hoy del portal del SNB (Swiss National Bank): depósitos a la vista semanales desde 2009 (snbgwdchfsgw), reservas mínimas (snbgwdmigirow, bamire desde 2005), parámetros del sistema escalonado desde 2019-06 (snbgwdzid), SARON (Swiss Average Rate Overnight) desde 1999 (zirepo), balance mensual desde 1996 (snbbipo), base monetaria, transacciones FX trimestrales; operaciones de mercado monetario del fichero oficial gmges.xlsx (1.606 operaciones desde 2019-11: repos CT/CP y SNB Bills con vencimientos, de donde sale la escalera de vencimientos que el registro habría mostrado cada semana); subastas de la AFF/EFV (Administración Federal de Finanzas): GMBF/MMDRC (Money Market Debt Register Claims, 767 desde 2012) y bonos de la Confederación (302 desde 2011), leídas de los XLSX oficiales; USD/CHF diario del IADB del Banco de Inglaterra (XUDLSFD, francos por dólar, desde 2005; el portal del SNB sólo publica el cambio mensual). Retardos de publicación aplicados en el replay (balance +10 d, reservas mínimas +45 d, operaciones +31 d, FX trimestral +90 d). Detalle en `calibration/chf/`.

## Eras y muestra válida

Tres rupturas: suelo EUR/CHF hasta enero-2015; **tipos negativos (−0,75 %) con exención escalonada 2015-01 → 2022-09** (400 semanas, sin absorción: SNB Bills y repos absorbentes a cero, el bloque BC vive del 13 s de los depósitos a la vista); y la **era de remuneración escalonada con absorción activa desde el 22-sep-2022** (salida de tipos negativos, factor umbral 28 → … → 13,5; SNB Bills + repos absorbentes 70–80 bn): **207 semanas**, con una sub-era desde el 20-jun-2025 (política 0 %, ancla de absorción = política − 5 pb; 64 semanas). Es la única era donde las anclas del config (cuota de absorción, escalera de Bills, spread SARON − ancla) significan algo. Depósitos a la vista 641 bn → 425 bn en la era (la caída fue 2022-09 → 2025-01; desde entonces planos en 425–445 bn).

## Control FX: nada, como en las otras siete

BC ρ −0,03/−0,02/0,00 a 5/10/20 sesiones (muestra completa, p > 0,45); Tesoro ρ ≈ 0. En la era el BC da ρ +0,16 a 20 sesiones (p 0,02, n 202) con el signo correcto, pero no a 5/10, no sobrevive el walk-forward (2022–23 −0,09 · 2024–25 +0,21 · 2026 +0,13) y ningún corte de la rejilla pasa la prueba; sin pesos duales (OLS: ningún bloque significativo).

## A. Frecuencia en la era de absorción (207 semanas)

La puntuación BC es discreta y viene casi entera de dos componentes: la señal ternaria del **cambio de 13 semanas de los depósitos a la vista** (±1, banda p30/p70 a 260 semanas) y la **penalización por cuota de absorción** (−0,5 WATCH / −1,0 STRESS, percentil a 60 meses). Reparto: −1,5 (30 %) · −1,0 (11 %) · −0,5 (10 %) · 0,0 (27 %) · +0,5 (4 %) · +1,0 (18 %). Con ±0,5 el bloque marca **DRENAJE el 51 %** de las semanas e INYECCIÓN el 22 %. Dos artefactos de ventana explican la asimetría, no el régimen: (1) en 2023 la cuota de absorción (0 → 25 %) era ≥ p95 de una ventana de 60 meses llena de ceros → STRESS → −1,0 todas las semanas (35 de 52 semanas en −1,5); en 2024–26, con la ventana ya poblada (p10–p90 = 22–28 %), la misma cuota vale 0 o −0,5; (2) la banda de 13 s a 260 semanas sigue conteniendo la caída de 2022–24, así que en la sub-era de 0 % cualquier subida modesta sale RISK_ON: INYECCIÓN el **41 %** de las semanas desde 2025-06 con reservas planas. Cortes naturales de la escala: **INJECTION ≥ +1,0** (18 % de la era; 39 % de la sub-era), **DRAIN ≤ −1,0** (41 % de la era, 9 % de la sub-era), NEUTRAL entre −0,5 y +0,5 (la penalización de absorción sola no es un drenaje). Lo que la historia sí fija son los percentiles del propio Δ13s dentro de la era, que deberían sustituir a la ventana móvil de 260 semanas: p30 **−3,1 %** / p70 **+0,4 %** (era) y −1,3 % / +1,0 % (sub-era 0 %); y el salto semanal p10/p90 = −7,5 / +5,8 bn (p3/p97 −13,1 / +10,5) para FX_INTERVENTION_SUSPECT, que se disparó 2 veces en 207 semanas con la escalera de Bills descontada.

Tesoro (Δ mensual de los saldos de la Confederación en el SNB, banda p20/p80 a 60 meses, ±0,5 por diseño): 0 el 59 %, +0,5 (INYECCIÓN = la Confederación gasta) el 23 %, −0,5 el 18 %; por año 17–33 % / 11–33 %. Percentiles del flujo en la era: p10 −5,0 · p20 **−3,8** · p50 −1,1 · p80 **+1,9** · p90 +7,9 bn (sub-era −3,7 / +4,2). No admite más umbral que su banda.

## B. Verdad de funding (SARON − ancla de absorción, era: p10 −2 pb · mediana 0 · p90 +1)

El spread vive en 3 pb de rango (2 pb en la sub-era). Aun así el Tesoro separa a 12 semanas: Δ spread tras INYECCIÓN fiscal **−0,51 pb** (n 43) · NEUTRAL +0,19 (117) · **DRENAJE +0,37** (35), ρ −0,186 (p 0,009, n 195); a 4 semanas ρ −0,02 (nada). Misma lectura que en la GBP: un drenaje de la Confederación (impuestos/emisión por delante del gasto) precede un SARON más pegado al tipo de política; la banda fiscal del CHF **tiene validación de funding**. El BC no separa (INYECCIÓN +0,36 · NEUTRAL −0,36 · DRENAJE +0,16: no monótono; ρ +0,05 p 0,54).

## Subastas: anclas por frecuencia, sin efecto FX estable

| instrumento | histórico p5 / p10 / mediana / p90 | era (2022-09+) p5 / p10 / mediana | últimos 3 años p10 / mediana | ancla propuesta |
|---|---|---|---|---|
| MMDRC 3 m (AFF, 2012–, n 767) | 2,77 / 3,05 / 4,68 / 7,01 | 2,47 / 2,82 / 4,06 (mín. 1,42; 3 de 207 bajo 2,0) | 2,98 / 4,25 | WATCH ≤ 2,8 · STRESS ≤ 2,5 (el 2,0 / 1,5 del config no ha ocurrido casi nunca) |
| Bonos Confederación (2011–, n 302) | 1,14 / 1,19 / 1,62 / 2,51 | 1,13 / 1,19 / 1,53 (mín. 1,04; 8 de 87 con tramos propios > 30 %) | 1,19 / 1,53 | WATCH ≤ 1,2 (coincide con el config) · STRESS ≤ 1,13 |
| SNB Bills 28 d (gmges, 2022-09–, n 201) | 1,01 / 1,02 / 1,17 / 1,94 | — | 1,01 / 1,13 | ANOMALÍA ≤ 1,02 (el < 1,0 del config no se ha dado nunca; mín. 1,00) |

Efecto FX: MMDRC y bonos nada (t entre −0,9 y +1,3). Los SNB Bills "débiles" (≤ p10) preceden un USD/CHF más alto a 20 sesiones (Δ +0,87 %, t 2,4; ρ −0,17 p 0,017), pero 19 de las 21 subastas débiles caen en 2025–26 (yield al suelo −0,06 %, demanda fina en la sub-era de 0 %): es un artefacto de era, no un umbral. Ni la AFF ni el SNB publican rendimiento medio/marginal de forma que permita un tail; el yield MMDRC − SARON (mediana −8 pb en la sub-era) queda como flag informativo.

## Propuesta para `config/chf.json` (a decidir)

`regime.dual.block_thresholds`: BC INJECTION ≥ +1,0 / DRAIN ≤ −1,0 (salida ±0,5); Tesoro banda ±0,5; régimen general por regla de acuerdo, conflicto = NEUTRAL etiquetado; sin pesos duales. `sight_deposits_13w_change_pct`: anclar la ventana de percentiles al 2022-09-22 (o usar los cortes de la era −3,1 % / +0,4 %) en vez de 260 semanas móviles; `absorption_share`: percentil sólo con la ventana poblada (min_n 24 meses de era) y, como en GBP/AUD/JPY, que el nivel pese 0,25 y que la inyección la digan los flujos (Δ depósitos a la vista neto de vencimientos de Bills, repos CT/CP, FX). Anclas de subasta como en la tabla. B: la banda fiscal vale; la del BC no tiene verdad de funding todavía (3 pb de rango). Sub-era de 0 % con 64 semanas: recalibrar a 150.

## Corrección conjunta (v2, tras la triangulación)

FDR conjunto + block-bootstrap (`calibration/B_fdr.md`): Tesoro a 12 semanas p bootstrap 0,081, q FDR 0,07 / 0,35. La relación tiene el signo MMT pero no sobrevive la corrección: **sugerencia**, no validación; etiqueta `frecuencia_de_era` (banda por diseño).
