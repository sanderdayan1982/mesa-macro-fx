# GBP — calibración empírica del régimen dual (A + B), 2026-09-09

Método A + B acordado con la mesa tras el CAD: (A) umbrales por frecuencia dentro de la era operativa vigente; (B) verdad de funding = Δ del spread de estrés (SONIA − Bank Rate) a 4 y 12 semanas. El tipo de cambio (GBP por USD, 1/XUDLUSS) se sigue midiendo como control, no como criterio. Replay as-of semanal 2007-01 → 2026-09 (1.027 semanas) con `ingest/calibrate.py --ccy gbp --fixtures fixtures/gbp_hist`. Datos primarios capturados hoy: IADB (Interactive Database del Banco de Inglaterra) semanal desde 2006, diario desde 1997 (SONIA, Bank Rate, gilts, XUDLUSS), mensual desde 1998; ONS (Office for National Statistics) PSF (Public Sector Finances) desde 1984; DMO (Debt Management Office) subastas de gilts D2.1A desde 1998 (1.239, parseadas del PDF oficial) y tenders de letras D2.2D desde 2001 (3.625, XML). Detalle en `calibration/gbp/`.

## Eras y muestra válida

Tres rupturas: corredor con promediado de reservas hasta marzo 2009 (BC en DRENAJE el 100 % de las semanas: sin sentido); suelo con QE (Quantitative Easing) 2009-03 → 2022-10 (712 semanas, BC DRENAJE 58 %); y **era QT (Quantitative Tightening) con ventas del APF (Asset Purchase Facility) desde 2022-11** (201 semanas), que es la única donde las anclas del config (PMRR — Preferred Minimum Range of Reserves 365–515 bn, ritmo de QT) significan algo. Reservas 950 bn → 644 bn en la era; el nivel nunca ha salido de SAFE (todavía sobre el PMRR).

## Control FX: nada, como en el CAD

BC ρ −0,04/−0,05/−0,07 (5/10/20 sesiones), Tesoro +0,02/+0,03/+0,05; en la era QT ninguna p < 0,17; ningún corte sobrevive; sin pesos duales. El régimen no predice el cable a semanas.

## A. Frecuencia en la era QT (201 semanas)

La puntuación BC es **discreta** (siete valores) porque sus componentes son niveles: reservas sobre el PMRR (+0,75), señal de liquidez neta (±1), ritmo de QT (0/−0,5/−1). Reparto: −0,83 (6 %) · −0,50 (4 %) · −0,17 (32 %) · +0,17 (8 %) · **+0,50 (32 %)** · +0,83 (2 %) · +1,17 (15 %). Con los ±0,5 provisionales el BC marca INYECCIÓN el **49 %** de las semanas de una era de QT: no es un régimen, es el nivel de reservas todavía sobre el rango. Percentiles: p20 −0,17 · p50 +0,17 · p80 +0,50 · p90 +1,17.

Tesoro: la puntuación ya es una banda ternaria (−1 / 0 / +1 por percentil p20/p80 del gasto neto interanual, tope ±1 por diseño mensual): 0 el 73 %, −1 el 19 %, +1 el 8 % de las semanas. No admite más umbral que su propia banda.

Propuesta por frecuencia (cortes en los huecos naturales de la escala, estables 2023–2026): **BC INJECTION ≥ +1,17** (15 % de las semanas; 8–31 % según el año), **BC DRAIN ≤ −0,50** (10 %; 8–21 %), NEUTRAL entre −0,17 y +0,83. Tesoro: se mantiene la banda (INJECTION +1 / DRAIN −1).

## B. Verdad de funding (SONIA − Bank Rate, era QT: p10 −7,2 pb · mediana −5,0 · p90 −2,0)

Dirección correcta en los dos bloques, magnitud pequeña porque el spread se mueve en un rango de 5 pb:

| bloque | Δ spread a 12 semanas tras INJECTION | tras NEUTRAL | tras DRAIN | ρ (12 s) | p |
|---|---|---|---|---|---|
| BC (≥ +0,5 / ≤ −0,5) | +0,26 pb (n 90) | +0,39 (78) | +0,45 (21) | −0,107 | 0,14 |
| Tesoro (banda) | +0,28 (17) | +0,29 (139) | **+0,53 (33)** | **−0,241** | **0,0008** |

A 4 semanas: Tesoro ρ −0,17 (p 0,015), BC sin relación. Lectura: un DRENAJE fiscal (gasto neto interanual bajo p20, es decir, emisión/impuestos por delante del gasto) precede un ensanchamiento del SONIA sobre el Bank Rate; la banda fiscal de la GBP **sí tiene validación de funding**, la única de las dos divisas hasta ahora. El BC sólo separa marginalmente (t 2,25 en entrenamiento, 0,15 pb).

## Subastas (DMO): anclas por era, no por historia completa

Los bid-to-cover de gilts cambiaron de nivel con el nuevo marco de subastas: mediana 2,22 en 1998–2026 pero **3,13 en los últimos 3 años** (n 159). Anclas propuestas sobre la era reciente: gilts convencionales WATCH ≤ 2,8 (p10 3 años) · STRESS ≤ 2,2 (p10 histórico, cola inferior) · tail WATCH ≥ 1,1 pb (p90) · STRESS ≥ 1,6 (p95); gilts indexados WATCH ≤ 2,9; letras (tenders semanales, 4 vencimientos) WATCH ≤ 2,5 (p10 3 años) · STRESS ≤ 1,9 (p5) · tail WATCH ≥ 5 pb (p90) · STRESS ≥ 8 (p95). Efecto FX de subastas débiles/fuertes: no estable (t entre −1,1 y +1,6; una anomalía en indexados a 5 sesiones que no se repite a 20). Como en el CAD, la subasta describe la demanda del papel, no el cable.

## Propuesta para `config/gbp.json` (a decidir)

`regime.dual.block_thresholds` del BC pasan de ±0,5 a **+1,17 / −0,50** (entrada) con salida en +0,83 / −0,17; Tesoro banda ±1; régimen general por regla de acuerdo, conflicto abierto = NEUTRAL etiquetado; sin pesos duales (no hay base). Anclas de subasta en `fiscal.thresholds` como arriba, con nota "percentiles DMO 2023–2026 / histórico 1998". Una consecuencia de diseño que conviene discutir: el componente "+0,75 por reservas sobre el PMRR" convierte un nivel en un flujo y explica el 49 % de "INYECCIÓN" en plena QT; la calibración lo neutraliza con el umbral, pero lo limpio sería que ese componente pese 0,25 (como el "in range" del CAD) y que la inyección la digan los flujos (Δ reservas, ILTR, CTRF). Lo dejo como propuesta v0.3 para cuando cerremos las ocho.

## Corrección conjunta (v2, tras la triangulación)

Con la corrección de Benjamini–Hochberg sobre las 32 pruebas B de las ocho divisas y el block-bootstrap de 8 semanas por autocorrelación (`calibration/B_fdr.md`): el Tesoro a 12 semanas conserva q = 0,009 con los p-valores brutos pero sube a q = 0,35 con el bootstrap (p bootstrap 0,067). La validación de funding de la GBP pasa a **sugerencia con signo correcto**, no a prueba: la etiqueta del config será `frecuencia_de_era` con nota de funding, no `funding_validado`.
