# CAD — calibración empírica del régimen dual (informe de mesa, 2026-09-09)

Método: `ingest/calibrate.py` reproduce los bloques Banco Central y Tesoro **semana a semana con los datos que existían ese día** (975 semanas B2, 2008-01 → 2026-09; Receiver General diario desde 2015-04; subastas Valet desde 1998) y contrasta cada puntuación con lo que pasó después. Nada se elige con datos futuros: corte entrenamiento < 2021 / prueba ≥ 2021 en la versión piloto (re-ejecutado con el corte común 2025-01-01 y el bloque A + B en la v2 de `calibration/cad/`), y walk-forward por bloques de dos años. Verdad primaria: retorno forward de USD/CAD a 5, 10 y 20 sesiones (+ = CAD más débil; hipótesis de la mesa: INYECCIÓN → CAD débil, DRENAJE → CAD fuerte). Verdad secundaria: Δ del spread CORRA − tipo de depósito a 20 sesiones. Datos: Valet (B2, CORRA, FXUSDCAD desde 2017 + IEXE0101 noon 2005–2016), Receiver General (`sqt-dcb-arch.csv` + actual), grupos Valet `AUC_TBILL_RESULTS` (2.268 subastas) y `AUC_BOND_RESULTS` (899). Detalle numérico completo en `calibration/cad/report.md`, `calibration.json`, `scores.csv`.

## Lo que la historia demuestra

**1. El CAD sólo es calibrable desde marzo de 2020.** Antes del sistema de suelo los saldos de liquidación eran ~C$250 M y el bloque BC marcaba DRENAJE el 97 % de las semanas (anclas 50–70 bn sin sentido en corredor). Cualquier umbral "histórico" que use 2008–2019 está contaminado. Muestra válida: 337 semanas (2020-03-23 → 2026-09-02).

**2. Bug real encontrado por el replay (corregido en `ingest/blocks.py`).** El flujo fiscal proxy = −Δ(saldo BoC + depósitos a plazo) usaba la suma por fechas comunes; el archivo RG no tiene depósitos a plazo entre sep-2020 y feb-2024 (celda vacía = cero), así que el flujo fiscal quedó **congelado 3,5 años** (7d = 18.687 M, Z = −0,83 en todas las semanas de 2021–2023). Ahora la celda vacía cuenta como 0. En vivo no afectaba (hay depósitos a plazo desde 2024) pero sí a cualquier percentil de 156 semanas que mirara hacia atrás.

**3. Contra el tipo de cambio, ningún umbral sobrevive.** Ni el bloque BC ni el Tesoro, a 5/10/20/40/60/120 sesiones, dentro ni fuera de muestra: ρ de Spearman entre −0,09 y +0,09, p > 0,09 en todos los casos; ningún corte de la rejilla −1,5…+1,5 separa los retornos forward con |t| ≥ 2 conservando el signo en la prueba; la regresión dual no da coeficientes significativos. Los signos de los pocos coeficientes marginales son además **contrarios** a la hipótesis (BC más alto → CAD ligeramente más fuerte a 10 sesiones, t = −1,8). Conclusión institucional: **en el CAD, el régimen de liquidez a 1–24 semanas no es un predictor del cruce**; es una descripción del estado de la liquidez, no una señal de tipo de cambio. Vender lo contrario sería inventar.

**4. Lo que sí es real y estable: la distribución de los propios estados en la era del suelo.** Percentiles de la puntuación semanal (n = 337), estables año a año (tabla en el apéndice):

| bloque | p10 | p20 | p33 | p50 | p67 | p80 | p90 | % DRAIN con ±0,5 | % INJECTION con ±0,5 |
|---|---|---|---|---|---|---|---|---|---|
| Banco Central | −1,33 | −1,00 | −0,71 | −0,03 | +0,09 | +0,90 | +1,29 | 34 % | 23 % |
| Tesoro (RG diario) | −1,47 | −0,59 | −0,20 | +0,03 | +0,30 | +0,62 | +1,24 | 23 % | 24 % |

Acuerdo entre los dos bloques (era del suelo): ambos NEUTRAL 26 %, ambos DRAIN 16 %, ambos INJECTION 11 %, conflicto abierto (uno inyecta y otro drena) sólo 5 % de las semanas; el resto son parciales (uno neutral).

**5. Verdad secundaria (funding):** BC vs Δ spread CORRA − depósito a 4 semanas, era del suelo: ρ = −0,12 (p = 0,03) — un BC en inyección precede una ligera **compresión** del spread hacia el suelo; el Tesoro no muestra relación (p = 0,13). Es débil pero tiene el signo correcto y es la única relación forward que sobrevive.

**6. Subastas (Valet, 1998 → hoy): anclas empíricas sólidas, sin efecto FX robusto.**

| instrumento | bid-to-cover p5 / p10 / mediana / p90 | últimos 3 años p10 / mediana | tail (pb) p50 / p90 / p95 |
|---|---|---|---|
| Letras (T-bills, n = 2.268) | 1,67 / 1,76 / 2,06 / 2,47 | 1,68 / 1,99 | 0,55 / 1,40 / 1,87 |
| Bonos nominales (n = 899) | 2,09 / 2,16 / 2,38 / 2,68 | 2,10 / 2,36 | 0,30 / 0,79 / 1,11 |

Una subasta "débil" (b/c ≤ p10) no precede ningún movimiento distinto del CAD (t entre −0,7 y +1,8, sin signo estable). Las subastas "fuertes" de letras (≥ p90) sí separan los retornos, pero con **signo invertido entre eras** (+0,79 % antes de 2021, −0,45 % después): no es un umbral real, es una regularidad de época. Propuesta: anclas de subasta por frecuencia histórica, no por FX: WATCH ≤ p10 (letras 1,76 / bonos 2,16), STRESS ≤ p5 (1,67 / 2,09), tail WATCH ≥ p90 (1,4 pb / 0,8 pb), STRESS ≥ p95 (1,9 / 1,1).

## Propuesta para el config (a decidir por la mesa)

Umbrales del régimen dual del CAD **por frecuencia histórica de la era del suelo**, no por predicción: bloque INJECTION ≥ p80 (BC +0,90 · Tesoro +0,62), DRAIN ≤ p20 (BC −1,00 · Tesoro −0,59), con histéresis de salida en p67 / p33 (BC +0,09 / −0,71 · Tesoro +0,30 / −0,20). Con esto cada bloque pasa ~20 % del tiempo en cada régimen extremo, por construcción y verificado año a año (2020–2026 dentro de 17–37 %). Los ±0,5 provisionales daban BC DRAIN 34 % / INJECTION 23 % (asimétrico: la escala del BC está sesgada al negativo). Pesos duales: como ninguno de los dos bloques demuestra poder explicativo sobre el cruce, **no hay base empírica para 0,6/0,4 ni para ningún otro peso**; propongo dejar el régimen general en la regla de acuerdo (los dos inyectan / los dos drenan) y, en conflicto abierto (5 % de las semanas), NEUTRAL explícito con la etiqueta "conflicto BC/Tesoro" hasta que otra verdad lo resuelva. Esto es lo único que la historia sostiene hoy.

## Lo que hace falta decidir antes de seguir con GBP

La verdad "tipo de cambio a 1–4 semanas" no funciona para el CAD y probablemente tampoco para el resto (la liquidez doméstica es un factor lento y el cruce lo mueven el USD y el petróleo). Opciones para las siete restantes, en orden de lo que yo haría: (a) calibrar por frecuencia de la era operativa de cada banco central (el equivalente del punto 4: real, estable, sin pesos inventados) y validar sólo la coherencia entre bloques; (b) añadir como verdad de funding el spread de estrés de cada moneda (punto 5), que es la variable que el régimen dice describir; (c) mantener la prueba FX pero a horizontes trimestrales y con el USD amplio descontado — se puede hacer, pero en el CAD ya falló a 120 sesiones.

## Corrección conjunta (v2, tras la triangulación)

Re-ejecutado con el bloque A + B y el corte común 2025-01-01. A: BC p20 −1,00 / p80 +0,90 (INJ 20 % / DRAIN 22 %), Tesoro −0,59 / +0,62 (20 % / 20 %) — idénticos al piloto. B: BC a 4 semanas ρ −0,12, p 0,027, p bootstrap 0,009, pero q FDR conjunto 0,15 / 0,09: **no sobrevive** la corrección por 32 pruebas; sugerencia con signo MMT. Etiqueta `frecuencia_de_era`.
