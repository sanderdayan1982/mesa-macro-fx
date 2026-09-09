# NZD — calibración empírica del régimen dual (A + B), 2026-09-09

Replay as-of semanal 2019-01 → 2026-09 (385 semanas; `ingest/calibrate.py --ccy nzd --fixtures fixtures/nzd_hist --era 2022-07-01`). Datos primarios capturados hoy, los libros de historia completa del RBNZ (Reserve Bank of New Zealand): hd12 (Standing Facilities diario desde 1999-03: settlement cash, ORRF — Overnight Reverse Repo Facility —, FX swaps; 6.906 sesiones), hd3 (todas las hojas de OMO — Open Market Operations —: reverse repos antiguos 3.044 filas, OMO semanal nuevo, ventas LSAP — Large Scale Asset Purchases —, recompras, BMLS), hd10 (influencias mensuales sobre el settlement cash desde 2008), hr1/hr3 (balance mensual), hb2 (cierre diario de tipos desde 2018-01: OCR — Official Cash Rate —, bank bills, bonos, swaps, interbancario overnight) y hb1 (NZD/USD diario desde 2018-01); y del NZDM (New Zealand Debt Management): historial de tenders de letras desde 1993 (4.138 líneas) y de bonos nominales desde 1983 (2.035). Los XLSX se leyeron en el navegador (zip + XML de las hojas → celdas) y se parsearon con los mismos parsers del runner en vivo. Retardos aplicados: D10 +31 d, R1/R3 +14 d. Detalle en `calibration/nzd/`.

## Dos defectos reales encontrados por el replay (corregidos)

1. **Histéresis de dos lados mal leída (`ingest/blocks_chf.py::_two_sided`, compartida por CHF y NZD).** La notación `exit_on: "p80/p20"` de los specs de dos lados (lado alto / lado bajo) la interpretaba el parser genérico como salida de WATCH en p80 y de STRESS en p20 (posiciones WATCH/STRESS): un STRESS por el lado alto nunca salía (siempre ≥ p20) y un WATCH por el lado bajo tampoco (siempre ≤ p80). En el replay `settlement_cash_wow` estaba en STRESS el **100 %** de las semanas y el bloque BC no podía sumar el +0,5 semanal. Corregido: cada lado recibe su propio percentil de salida. Afecta en vivo a `settlement_cash_wow`, `csa_mom`, `govt_cash_influence`, `tbill_yield_minus_ocr_bps`, `bank_bill_90d_minus_ocr_bps`, `hike_pricing_bps`, `curve_10y_2y_bps` (NZD) y a `sight_deposits_wow` / `other_sight_deposits_wow` (CHF) tras el primer print fuera de banda.
2. **Retornos forward antes del inicio de la historia FX (`calibrate.py::fwd_returns`).** Una fecha anterior al primer dato del cruce tomaba el retorno de la primera sesión disponible; con subastas desde 1983 y FX desde 2018 salían t de −12/−14 en las letras. Ahora esas fechas no cuentan (la FX del RBNZ empieza en 2018-01; el efecto de subastas se mide desde ahí).

## Eras y muestra válida

Corredor pre-COVID con settlement cash ≈ 7–8 bn hasta marzo-2020 (las anclas 20/15/10/7 bn lo dan en STRESS/CRISIS permanente: sin sentido); suelo LSAP 2020-03 → 2022-06 (settlement cash 7 → 50 bn); **desenvolvimiento del LSAP desde julio-2022** (ventas de bonos al NZDM, settlement cash 49 bn → 24 bn): **210 semanas**, es la era calibrable; y el nuevo marco de OMO semanal a adjudicación plena (OCR + 10 pb) desde el **2-abr-2026**: 22 semanas, sólo sub-era.

## Control FX: nada, como en las otras siete

BC ρ +0,06/+0,02/−0,06 (5/10/20 sesiones, p > 0,25); Tesoro −0,02/−0,03/−0,04; en la era ninguna p < 0,24; walk-forward a 20 sesiones −0,28 (2019–20) → −0,09 → +0,03 → −0,04: sin signo estable; ningún corte sobrevive; sin pesos duales.

## A. Frecuencia en la era de desenvolvimiento (210 semanas)

BC (puntuación discreta): −1,0 (11 %) · −0,5 (23 %) · −0,25 (4 %) · 0,0 (17 %) · +0,25 (24 %) · **+0,75 (20 %)** · +1,0 (0,5 %). Percentiles p10 −1,0 · p20 **−0,5** · p50 0,0 · p80 +0,35 (interpolación lineal de numpy sobre una escala discreta; el valor alcanzable más próximo es +0,25 y el siguiente +0,75) · p90 +0,75. Cortes naturales de la escala: **INJECTION ≥ +0,75** (20 %; por año 20–22 %, 18 % en 2026), **DRAIN ≤ −0,5** (35 %; 30 % en 2023, 38 % en 2024, 36 % en 2025, 44 % en 2026). Que el drenaje sea un tercio de las semanas es la verdad de la era (LSAP unwind, −25 bn), no un artefacto: el bloque ya usaba ±0,75 para su etiqueta interna y el `regime.dual` ±0,5, y la historia dice que el BC sólo llega a +0,75 cuando el settlement cash sube en la semana y en 20 sesiones a la vez. Un componente de nivel constante: `omo_reliance_share` sale WATCH en **209 de 210 semanas** (−0,25 fijo; la ventana "desde 2026-04-02 o 250 d" convierte cualquier nivel en p85) — misma nota v0.3 que en GBP/AUD/JPY/CHF: pesar 0,25 y dejar que los flujos digan la inyección. Percentiles del propio Δ5s del settlement cash en la era: p10 −4,1 / p90 +3,5 bn (p3/p97 −5,9 / +5,3), y en la sub-era −3,1 / +3,1.

Tesoro (D10 "government cash influence", banda p20/p80 a 60 meses, ±0,5 por diseño): 0 el 45 %, −0,5 (DRENAJE) el 32 %, +0,5 (INYECCIÓN) el 23 %; por año DRENAJE 28–44 %. Percentiles del flujo mensual en la era: p10 −4,4 · p20 **−1,3** · p50 +1,3 · p80 **+4,4** · p90 +5,1 bn (sub-era −3,4 / +3,3). No admite más umbral que su banda.

## B. Verdad de funding: el spread bank bill 30 d − OCR no sirve como verdad

En la era p10 −3 pb · mediana +11 · p90 +28, y en la sub-era 16 / 22 / 34: el spread lo mueve la expectativa de OCR (subidas de julio y septiembre de 2026), no el funding. BC ρ +0,07 / +0,06 (4/12 semanas, p > 0,3); Tesoro +0,10 (p 0,16) / −0,02, con medias condicionales no monótonas (DRENAJE −3,3 · NEUTRAL +3,3 · INYECCIÓN −1,4 pb). Ningún umbral sobrevive. Alternativa para v0.3: el interbancario overnight − OCR (INM.DN.NZK, 333 prints en la era, p5/p95 −13 / +13 pb), que sí es precio de funding aunque sea disperso.

## Subastas NZDM: anclas por era, efecto FX cambiante de signo

| instrumento | histórico p5 / p10 / mediana / p90 | era 2022-07+ p5 / p10 / mediana | últimos 3 años p10 / mediana | tail (pb) era p50 / p90 / p95 | ancla propuesta |
|---|---|---|---|---|---|
| Letras (1993–, n 4.138 líneas) | 1,25 / 1,60 / 3,20 / 5,03 | 1,20 / 1,30 / 2,71 (**24 %** de las líneas bajo 2,0) | 1,30 / 2,75 | 0,5 / 2,0 / 2,5 | WATCH ≤ 1,3 · STRESS ≤ 1,2 (el 2,0 / 1,5 del config marca WATCH una de cada cuatro) · tail WATCH ≥ 2,0 · STRESS ≥ 2,5 |
| Bonos nominales (1983–, n 2.035) | 1,30 / 1,59 / 2,92 / 4,84 | 1,57 / 1,79 / 3,17 (14 % bajo 2,0) | 1,86 / 3,33 | 0,75 / 1,9 / 2,5 | WATCH ≤ 1,8 · STRESS ≤ 1,6 · tail WATCH ≥ 2,0 (coincide con el config) · STRESS ≥ 2,5 · CRISIS ≥ 4 |

Efecto FX: las letras "débiles" (≤ p10) dan Δ +0,25 % a 5 sesiones (t 2,2) en la muestra 2018–2026, pero el signo cambia por eras (2018–20: −0,35, t −2,1; 2020–22: +0,63, t 2,9; era actual: +0,16, t 1,1): regularidad de época, no umbral. Bonos: nada (t entre −0,1 y 1,2). Como en las otras siete, la subasta describe la demanda del papel.

## Propuesta para `config/nzd.json` (a decidir)

`regime.dual.block_thresholds`: BC INJECTION ≥ +0,75 / DRAIN ≤ −0,5 (salida +0,25 / −0,25); Tesoro banda ±0,5; régimen general por regla de acuerdo, conflicto = NEUTRAL etiquetado; sin pesos duales. `omo_reliance_share` como nivel 0,25 y ventana poblada (min_n 26 semanas del marco nuevo) antes de percentiles. Anclas de tenders como en la tabla, manteniendo la regla N6 (2 de 3). Verdad de funding pendiente (interbancario overnight − OCR). Sub-era del marco nuevo con 22 semanas: recalibrar a 150. Y la corrección de la histéresis de dos lados se sube con el resto de ficheros de calibración (afecta al runner en vivo).

## Corrección conjunta (v2, tras la triangulación)

FDR conjunto: ninguna prueba B del NZD baja de q 0,35 (y el spread usado no es funding). Etiqueta `frecuencia_de_era` para el BC y `banda_por_diseño` para el Tesoro; sub-era del marco nuevo `provisional_era_corta`.
