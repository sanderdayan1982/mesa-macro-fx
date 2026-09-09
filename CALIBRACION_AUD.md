# AUD — calibración empírica del régimen dual (A + B), 2026-09-09

Replay as-of semanal 2014-01 → 2026-09 (661 semanas, `ingest/calibrate.py --ccy aud --fixtures fixtures/aud_hist`). Datos primarios capturados hoy del RBA (Reserve Bank of Australia) y de la AOFM (Australian Office of Financial Management): tablas A1 (balance semanal desde 2013-07), A3 (ES — Exchange Settlement balances diarias desde 2013-11), F1/F2 (tipos diarios desde 2011/2013), A2, D1/D3 (agregados desde 1959/1976); AUD/USD diario 2010–2026 (XLS históricos F11.1 del RBA + CSV actual); tenders de la AOFM desde el Data Hub: bonos 1982–2026 (1.947 con cobertura), notas 2000–2026 (1.372), indexados (318). Verdad A + B; FX (AUD por USD) como control. Detalle en `calibration/aud/`.

## Eras y muestra válida

Tres eras y ninguna calibración vale a caballo entre ellas: corredor con ES ≈ A$2–3 bn hasta marzo de 2020 (BC DRENAJE el **100 %** de las semanas — el ancla 70–100 bn no existía); suelo con TFF (Term Funding Facility) y compras 2020-03 → 2025-04 (263 semanas, BC INYECCIÓN 76 % porque las ES estaban muy por encima de cualquier rango); y el **marco de reservas amplias desde el 9-abr-2025** (OMO a adjudicación plena a target + 10 pb, sin objetivo de ES; ancla Jacobs 70–100 bn): **74 semanas**. Es la única era comparable con el config actual, y es corta: todo lo que sigue va con esa etiqueta.

## Control FX

Muestra completa: BC ρ −0,06/−0,08/−0,11 a 5/10/20 sesiones (p 0,004 a 20, **signo contrario** a la hipótesis: BC alto → AUD fuerte), Tesoro ≈ 0. En la era actual el BC da ρ +0,27 a 5 sesiones (p 0,02, n 73) con el signo correcto, pero no se repite a 10/20, no sobrevive el walk-forward y n es de 73 semanas: no es un umbral. Sin pesos duales.

## A. Frecuencia en la era de reservas amplias (74 semanas)

BC: puntuación discreta con cinco valores — −1,0 (1 %) · −0,5 (5 %) · 0,0 (19 %) · **+0,67 (50 %)** · +1,33 (24 %). Con ±0,5 el bloque marca INYECCIÓN el **74 %** de las semanas: el componente "ES sobre el rango 70–100 bn → +0,75" es un nivel (las ES están en 170 bn), el mismo defecto que en la GBP. Cortes naturales: **INJECTION ≥ +1,33** (24 %; 2025 y 2026 coinciden en p80 = 1,33), **DRAIN ≤ 0,0** (26 %; el 0 aparece cuando los flujos diarios de ES son negativos y el nivel ya no suma), con −0,5 como STRESS de drenaje (6 %).

Tesoro (−Δ depósitos del Gobierno en el RBA, acumulado 4 semanas por percentil): distribución continua y bien centrada — p10 −1,24 · p20 **−1,02** · p50 +0,12 · p80 **+0,57** · p90 +1,16; con ±0,5 reparte 30 % / 27 %, y por año p20/p80 −0,78/+0,54 (2025) y −1,13/+0,61 (2026). Propuesta: INJECTION ≥ +0,57 (salida +0,46) · DRAIN ≤ −1,02 (salida −0,43).

## B. Verdad de funding (AONIA − cash rate target)

Nada en la era actual: BC ρ +0,01 / +0,05 (4/12 semanas), Tesoro −0,07 / −0,08, todas p > 0,5 con n 62–70. En la muestra completa el BC da ρ +0,34 a 20 sesiones, pero con **signo contrario** y mezclando eras (AONIA bajo el target en el suelo, sobre el target con el marco nuevo), así que no cuenta. El spread AUD cambió de régimen con el marco de abril de 2025; habrá que reevaluar B cuando la era tenga ≥ 150 semanas.

## Subastas AOFM: anclas por era, sin efecto FX estable

| instrumento | histórico p5 / p10 / mediana / p90 | últimos 3 años p10 / mediana | tail (pb) p50 / p90 / p95 | ancla propuesta |
|---|---|---|---|---|
| Bonos (1982–) | 1,94 / 2,22 / 3,38 / 4,99 | 2,74 / 3,54 | 0,3 / 1,6 / 4,8 | WATCH ≤ 2,7 · STRESS ≤ 2,2 · tail WATCH ≥ 1,6 · STRESS ≥ 4,8 |
| Notas (2000–) | 2,55 / 2,84 / 4,46 / 6,81 | 2,77 / 3,80 | 1,3 / 3,5 / 4,5 | WATCH ≤ 2,8 · STRESS ≤ 2,5 · tail WATCH ≥ 3,5 · STRESS ≥ 4,5 |
| Indexados (1994–) | 2,26 / 2,55 / 3,70 / 5,46 | 2,90 / 3,87 | 0,7 / 1,9 / 2,4 | WATCH ≤ 2,9 · STRESS ≤ 2,3 |

El efecto "subasta débil → AUD" a 5 sesiones sale muy significativo en la muestra completa (t −4,97) pero **viene de los años 80–2000** y cambia de signo por eras (2010–19: 0,0; 2020–25: +0,36; era actual: sin muestra suficiente). Igual que en CAD y GBP: la subasta describe la demanda del papel, no el cruce.

## Propuesta para `config/aud.json`

`regime.dual.block_thresholds`: BC INJECTION ≥ +1,33 / DRAIN ≤ 0,0 (salida +0,67 / +0,67 — el 0,67 es el estado modal), Tesoro INJECTION ≥ +0,57 / DRAIN ≤ −1,02; régimen general por regla de acuerdo, conflicto = NEUTRAL etiquetado; sin pesos duales. Anclas de subasta en `fiscal.thresholds` como arriba. Misma nota de diseño v0.3 que en la GBP: el "+0,75 por ES sobre el rango" debería pesar 0,25 y que la inyección la digan los flujos (Δ ES, OMO, depósitos). Y una advertencia de muestra: 74 semanas es poco; estos cortes se recalibran cuando la era llegue a 150.

## Corrección conjunta (v2, tras la triangulación)

FDR conjunto: ninguna prueba B del AUD baja de q 0,64. Etiqueta `provisional_era_corta` (74 semanas; congelar hasta 150).
