# AUD — calibración empírica del régimen dual (BC / Tesoro / general)

Generado 2026-09-09T09:02:17Z · 662 semanas (2014-01-01 → 2026-09-02) · corte entrenamiento/prueba 2025-01-01 · verdad: AUD per USD (1 / FXRUSD) — + = AUD weaker

Hipótesis de la mesa (MMT/Mosler): INYECCIÓN → la divisa se debilita después (retorno forward positivo del cruce divisa-por-USD); DRENAJE → se fortalece. Un umbral sólo se propone si separa los retornos forward con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba y cubre ≥ 10 % de las semanas.

Ruptura estructural: 2020-03-19 — RBA package: TFF, bond purchases, ES balances from ~A$2–3bn to hundreds of billions (floor)

Ruptura estructural: 2025-04-09 — ample-reserves framework: full-allotment OMO at target + 10 bp, no ES target (calibration era)

Ruptura estructural: 2025-04-09 — era start set on the command line


## 1. ¿Explican los bloques el tipo de cambio? (Spearman, muestra completa)

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 sesiones | -0.060 | 0.121 | 661 | -0.011 | 0.772 | 661 |
| 10 sesiones | -0.084 | 0.031 | 660 | -0.008 | 0.837 | 660 |
| 20 sesiones | -0.112 | 0.004 | 658 | 0.016 | 0.682 | 658 |

Submuestra desde la ruptura (2025-04-09, 74 semanas):

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 | 0.271 | 0.020 | 73 | 0.096 | 0.420 | 73 |
| 10 | 0.195 | 0.100 | 72 | 0.005 | 0.970 | 72 |
| 20 | 0.171 | 0.156 | 70 | 0.030 | 0.808 | 70 |

## 2. Bloque central_bank — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2014–2015 ρ=0.00 (n=105) · 2016–2017 ρ=-0.03 (n=104) · 2018–2019 ρ=-0.17 (n=104) · 2020–2021 ρ=-0.17 (n=105) · 2022–2023 ρ=-0.07 (n=104) · 2024–2025 ρ=0.21 (n=105) · 2026–2026 ρ=0.26 (n=34)
- 10 sesiones: 2014–2015 ρ=-0.04 (n=105) · 2016–2017 ρ=0.03 (n=104) · 2018–2019 ρ=-0.23 (n=104) · 2020–2021 ρ=-0.22 (n=105) · 2022–2023 ρ=-0.19 (n=104) · 2024–2025 ρ=0.08 (n=105) · 2026–2026 ρ=0.27 (n=33)
- 20 sesiones: 2014–2015 ρ=-0.01 (n=105) · 2016–2017 ρ=-0.02 (n=104) · 2018–2019 ρ=-0.18 (n=104) · 2020–2021 ρ=-0.20 (n=105) · 2022–2023 ρ=-0.11 (n=104) · 2024–2025 ρ=0.19 (n=105) · 2026–2026 ρ=0.15 (n=31)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=0.337 p=0.000 n=641

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 2. Bloque fiscal — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2014–2015 ρ=-0.02 (n=105) · 2016–2017 ρ=0.09 (n=104) · 2018–2019 ρ=-0.13 (n=104) · 2020–2021 ρ=-0.05 (n=105) · 2022–2023 ρ=-0.03 (n=104) · 2024–2025 ρ=0.08 (n=105) · 2026–2026 ρ=-0.03 (n=34)
- 10 sesiones: 2014–2015 ρ=0.04 (n=105) · 2016–2017 ρ=0.13 (n=104) · 2018–2019 ρ=-0.03 (n=104) · 2020–2021 ρ=-0.05 (n=105) · 2022–2023 ρ=-0.12 (n=104) · 2024–2025 ρ=-0.01 (n=105) · 2026–2026 ρ=-0.04 (n=33)
- 20 sesiones: 2014–2015 ρ=0.04 (n=105) · 2016–2017 ρ=0.02 (n=104) · 2018–2019 ρ=-0.02 (n=104) · 2020–2021 ρ=-0.03 (n=105) · 2022–2023 ρ=0.03 (n=104) · 2024–2025 ρ=0.10 (n=105) · 2026–2026 ρ=-0.08 (n=31)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=-0.027 p=0.491 n=641

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 3. Pesos duales (OLS del retorno forward sobre los dos bloques estandarizados; walk-forward)

- 5 sesiones: {"beta_cb": -0.0838, "beta_fi": 0.0305, "t_cb": -1.29, "t_fi": 0.47, "n_train": 574, "n_test": 87, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 10 sesiones: {"beta_cb": -0.1379, "beta_fi": -0.0309, "t_cb": -1.53, "t_fi": -0.34, "n_train": 574, "n_test": 86, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 20 sesiones: {"beta_cb": -0.2188, "beta_fi": 0.0322, "t_cb": -1.83, "t_fi": 0.27, "n_train": 574, "n_test": 84, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}

## A. Umbrales por frecuencia de la era operativa (desde 2025-04-09, 74 semanas)

| bloque | n | p10 | p20 | p33 | p50 | p67 | p80 | p90 | %% DRAIN a −0,5 | %% INJ a +0,5 | propuesta enter/exit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| central_bank | 74 | 0.0 | 0.0 | 0.67 | 0.67 | 0.67 | 1.33 | 1.33 | 0.07 | 0.74 | INJ ≥ 1.33 (salida 0.67) · DRAIN ≤ 0.0 (salida 0.67) |
| fiscal | 74 | -1.24 | -1.02 | -0.43 | 0.12 | 0.46 | 0.57 | 1.16 | 0.3 | 0.27 | INJ ≥ 0.57 (salida 0.46) · DRAIN ≤ -1.02 (salida -0.43) |

Convención de percentil: numpy.percentile default = linear interpolation between order statistics (on a discrete score the p80 can fall between two attainable values; the nearest attainable value is reported alongside).
- central_bank — corte de mesa (fuente única para el config): INJ ≥ 1.33 / DRAIN ≤ 0.0 → 24% / 26% de las semanas de la era · regla: natural gaps of the 5-value discrete score (INJ 24 %, DRAIN 26 %); era 74 wk — provisional until 150 · propuesta automática p80/p20: 1.33 / 0.0 (p80 alcanzable más próximo 1.33, p20 0.0)
- fiscal — corte de mesa (fuente única para el config): INJ ≥ 0.57 / DRAIN ≤ -1.02 → 20% / 20% de las semanas de la era · regla: p80/p20 of the ample-reserves era, exit p67/p33 · propuesta automática p80/p20: 0.57 / -1.02 (p80 alcanzable más próximo 0.56, p20 -0.99)

Estabilidad año a año — central_bank: 2025 p20 0.4 / p50 0.67 / p80 1.33 · 2026 p20 0.0 / p50 0.67 / p80 1.33

Estabilidad año a año — fiscal: 2025 p20 -0.78 / p50 0.15 / p80 0.54 · 2026 p20 -1.13 / p50 0.11 / p80 0.61

## B. Verdad de funding — puntuación del bloque vs Δ spread de estrés (4 y 12 semanas; hipótesis: INJECTION comprime, DRAIN ensancha → ρ negativa)

- central_bank, 4 semanas: ρ=0.013 p=0.9137 (p block-bootstrap 8 s: 0.7186; rejilla de 62 cortes) n=70 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- central_bank, 12 semanas: ρ=0.052 p=0.6894 (p block-bootstrap 8 s: 0.6082; rejilla de 62 cortes) n=62 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 4 semanas: ρ=-0.072 p=0.5559 (p block-bootstrap 8 s: 0.4203; rejilla de 62 cortes) n=70 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 12 semanas: ρ=-0.079 p=0.5431 (p block-bootstrap 8 s: 0.4188; rejilla de 62 cortes) n=62 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno

## 4. Subastas — anclas empíricas y validación

### bonds (n=1947, 1982-08-05 → 2026-09-09)

- bid-to-cover: p5 1.941 · p10 2.215 · p25 2.71 · mediana 3.375 · p75 4.182 · p90 4.994 · últimos 3 años (n=254): p10 2.741 mediana 3.541
- tail (pb): p50 0.3 · p75 0.6 · p90 1.6 · p95 4.8
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.145 t 0.58 · fuertes (≥ p90): Δ -0.085 t -0.75
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ -0.758 t -2.43 · fuertes (≥ p90): Δ -0.057 t -0.25
- ρ bid-to-cover vs retorno forward 20: -0.038 (p 0.158, n 1368)
### notes (n=1372, 2000-07-12 → 2026-09-03)

- bid-to-cover: p5 2.546 · p10 2.838 · p25 3.527 · mediana 4.457 · p75 5.551 · p90 6.81 · últimos 3 años (n=321): p10 2.765 mediana 3.8
- tail (pb): p50 1.275 · p75 2.17 · p90 3.548 · p95 4.51
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ -0.068 t -0.40 · fuertes (≥ p90): Δ 0.214 t 1.42
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ -0.405 t -1.32 · fuertes (≥ p90): Δ 0.365 t 1.35
- ρ bid-to-cover vs retorno forward 20: 0.046 (p 0.116, n 1185)
### indexed (n=318, 1994-08-25 → 2026-09-03)

- bid-to-cover: p5 2.257 · p10 2.546 · p25 3.081 · mediana 3.7 · p75 4.557 · p90 5.463 · últimos 3 años (n=61): p10 2.9 mediana 3.873
- tail (pb): p50 0.67 · p75 1.145 · p90 1.9 · p95 2.416
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ -0.267 t -0.88 · fuertes (≥ p90): Δ -0.033 t -0.15
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.437 t 0.79 · fuertes (≥ p90): Δ -0.205 t -0.40
- ρ bid-to-cover vs retorno forward 20: -0.073 (p 0.231, n 269)
