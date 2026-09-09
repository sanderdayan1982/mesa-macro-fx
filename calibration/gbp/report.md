# GBP — calibración empírica del régimen dual (BC / Tesoro / general)

Generado 2026-09-09T08:58:33Z · 1028 semanas (2007-01-03 → 2026-09-02) · corte entrenamiento/prueba 2025-01-01 · verdad: GBP per USD (1 / XUDLUSS) — + = GBP weaker

Hipótesis de la mesa (MMT/Mosler): INYECCIÓN → la divisa se debilita después (retorno forward positivo del cruce divisa-por-USD); DRENAJE → se fortalece. Un umbral sólo se propone si separa los retornos forward con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba y cubre ≥ 10 % de las semanas.

Ruptura estructural: 2009-03-05 — QE + reserves remunerated at Bank Rate: floor system (reserves-averaging corridor before)

Ruptura estructural: 2022-11-01 — APF gilt sales start (active QT); reserves scarcity framework (PMRR 365–515bn) from 2024

Ruptura estructural: 2022-11-01 — era start set on the command line


## 1. ¿Explican los bloques el tipo de cambio? (Spearman, muestra completa)

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 sesiones | -0.041 | 0.190 | 1027 | 0.017 | 0.582 | 1027 |
| 10 sesiones | -0.052 | 0.094 | 1026 | 0.030 | 0.337 | 1026 |
| 20 sesiones | -0.066 | 0.034 | 1024 | 0.046 | 0.142 | 1024 |

Submuestra desde la ruptura (2022-11-01, 201 semanas):

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 | -0.093 | 0.189 | 200 | 0.086 | 0.226 | 200 |
| 10 | -0.071 | 0.320 | 199 | 0.090 | 0.208 | 199 |
| 20 | -0.043 | 0.548 | 197 | 0.097 | 0.173 | 197 |

## 2. Bloque central_bank — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2007–2008 ρ=-0.05 (n=106) · 2009–2010 ρ=-0.06 (n=104) · 2011–2012 ρ=-0.03 (n=104) · 2013–2014 ρ=-0.02 (n=105) · 2015–2016 ρ=0.06 (n=104) · 2017–2018 ρ=0.03 (n=104) · 2019–2020 ρ=-0.12 (n=105) · 2021–2022 ρ=-0.06 (n=104) · 2023–2024 ρ=-0.01 (n=104) · 2025–2026 ρ=-0.14 (n=87)
- 10 sesiones: 2007–2008 ρ=-0.05 (n=106) · 2009–2010 ρ=-0.08 (n=104) · 2011–2012 ρ=-0.06 (n=104) · 2013–2014 ρ=0.03 (n=105) · 2015–2016 ρ=0.00 (n=104) · 2017–2018 ρ=0.01 (n=104) · 2019–2020 ρ=-0.20 (n=105) · 2021–2022 ρ=-0.03 (n=104) · 2023–2024 ρ=0.02 (n=104) · 2025–2026 ρ=-0.14 (n=86)
- 20 sesiones: 2007–2008 ρ=0.01 (n=106) · 2009–2010 ρ=-0.02 (n=104) · 2011–2012 ρ=-0.06 (n=104) · 2013–2014 ρ=0.06 (n=105) · 2015–2016 ρ=-0.14 (n=104) · 2017–2018 ρ=-0.10 (n=104) · 2019–2020 ρ=-0.21 (n=105) · 2021–2022 ρ=-0.01 (n=104) · 2023–2024 ρ=-0.01 (n=104) · 2025–2026 ρ=-0.03 (n=84)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=-0.129 p=0.000 n=1007

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 2. Bloque fiscal — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2007–2008 ρ=0.12 (n=106) · 2009–2010 ρ=-0.00 (n=104) · 2011–2012 ρ=0.08 (n=104) · 2013–2014 ρ=-0.01 (n=105) · 2015–2016 ρ=0.07 (n=104) · 2017–2018 ρ=0.02 (n=104) · 2019–2020 ρ=-0.06 (n=105) · 2021–2022 ρ=-0.03 (n=104) · 2023–2024 ρ=-0.03 (n=104) · 2025–2026 ρ=0.12 (n=87)
- 10 sesiones: 2007–2008 ρ=0.26 (n=106) · 2009–2010 ρ=-0.04 (n=104) · 2011–2012 ρ=0.07 (n=104) · 2013–2014 ρ=0.03 (n=105) · 2015–2016 ρ=0.09 (n=104) · 2017–2018 ρ=0.07 (n=104) · 2019–2020 ρ=-0.03 (n=105) · 2021–2022 ρ=-0.12 (n=104) · 2023–2024 ρ=-0.12 (n=104) · 2025–2026 ρ=0.18 (n=86)
- 20 sesiones: 2007–2008 ρ=0.48 (n=106) · 2009–2010 ρ=-0.09 (n=104) · 2011–2012 ρ=0.14 (n=104) · 2013–2014 ρ=0.04 (n=105) · 2015–2016 ρ=0.08 (n=104) · 2017–2018 ρ=0.15 (n=104) · 2019–2020 ρ=-0.08 (n=105) · 2021–2022 ρ=-0.22 (n=104) · 2023–2024 ρ=-0.13 (n=104) · 2025–2026 ρ=0.19 (n=84)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=-0.029 p=0.362 n=1007

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 3. Pesos duales (OLS del retorno forward sobre los dos bloques estandarizados; walk-forward)

- 5 sesiones: {"beta_cb": -0.0351, "beta_fi": 0.0204, "t_cb": -0.77, "t_fi": 0.44, "n_train": 940, "n_test": 87, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 10 sesiones: {"beta_cb": -0.0821, "beta_fi": 0.0312, "t_cb": -1.3, "t_fi": 0.5, "n_train": 940, "n_test": 86, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 20 sesiones: {"beta_cb": -0.1641, "beta_fi": 0.1141, "t_cb": -1.93, "t_fi": 1.34, "n_train": 940, "n_test": 84, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}

## A. Umbrales por frecuencia de la era operativa (desde 2022-11-01, 201 semanas)

| bloque | n | p10 | p20 | p33 | p50 | p67 | p80 | p90 | %% DRAIN a −0,5 | %% INJ a +0,5 | propuesta enter/exit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| central_bank | 201 | -0.5 | -0.17 | -0.17 | 0.17 | 0.5 | 0.5 | 1.17 | 0.1 | 0.5 | INJ ≥ 1.17 (salida 0.83) · DRAIN ≤ -0.5 (salida -0.17) |
| fiscal | 201 | -1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.19 | 0.08 | INJ ≥ 1.0 (salida 1.0) · DRAIN ≤ -1.0 (salida -1.0) |

Convención de percentil: numpy.percentile default = linear interpolation between order statistics (on a discrete score the p80 can fall between two attainable values; the nearest attainable value is reported alongside).
- central_bank — corte de mesa (fuente única para el config): INJ ≥ 1.17 / DRAIN ≤ -0.5 → 15% / 10% de las semanas de la era · regla: natural gaps of the 7-value discrete score (INJ 15 %, DRAIN 10 % of the QT era) · propuesta automática p80/p20: 0.5 / -0.17 (p80 alcanzable más próximo 0.5, p20 -0.17)
- fiscal — corte de mesa (fuente única para el config): INJ ≥ 1.0 / DRAIN ≤ -1.0 → 8% / 19% de las semanas de la era · regla: ternary band by design (±1); funding-validated at 12 weeks · propuesta automática p80/p20: 0.0 / 0.0 (p80 alcanzable más próximo 0.0, p20 0.0)

Estabilidad año a año — central_bank: 2023 p20 -0.17 / p50 -0.17 / p80 0.5 · 2024 p20 -0.43 / p50 0.17 / p80 0.5 · 2025 p20 -0.17 / p50 0.5 / p80 1.17 · 2026 p20 -0.17 / p50 0.5 / p80 1.17

Estabilidad año a año — fiscal: 2023 p20 0.0 / p50 0.0 / p80 0.0 · 2024 p20 0.0 / p50 0.0 / p80 0.0 · 2025 p20 -1.0 / p50 0.0 / p80 0.0 · 2026 p20 -1.0 / p50 0.0 / p80 0.0

## B. Verdad de funding — puntuación del bloque vs Δ spread de estrés (4 y 12 semanas; hipótesis: INJECTION comprime, DRAIN ensancha → ρ negativa)

- central_bank, 4 semanas: ρ=0.032 p=0.6600 (p block-bootstrap 8 s: 0.7086; rejilla de 62 cortes) n=197 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- central_bank, 12 semanas: ρ=-0.107 p=0.1440 (p block-bootstrap 8 s: 0.2889; rejilla de 62 cortes) n=189 · umbral INJECTION que sobrevive: ≥ 0.2 (Δ train -0.15, t -2.25; Δ test -0.13) · DRAIN: ≤ 0.4 (Δ train 0.15, t 2.25; Δ test 0.13)
- fiscal, 4 semanas: ρ=-0.173 p=0.0153 (p block-bootstrap 8 s: 0.1104; rejilla de 62 cortes) n=197 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 12 semanas: ρ=-0.241 p=0.0008 (p block-bootstrap 8 s: 0.0665; rejilla de 62 cortes) n=189 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno

## 4. Subastas — anclas empíricas y validación

### gilts_conventional (n=916, 1998-05-20 → 2026-08-25)

- bid-to-cover: p5 1.458 · p10 1.58 · p25 1.84 · mediana 2.22 · p75 2.63 · p90 3.12 · últimos 3 años (n=159): p10 2.774 mediana 3.13
- tail (pb): p50 0.4 · p75 0.7 · p90 1.1 · p95 1.6
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.165 t 1.03 · fuertes (≥ p90): Δ 0.156 t 1.54
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.403 t 1.31 · fuertes (≥ p90): Δ 0.056 t 0.29
- ρ bid-to-cover vs retorno forward 20: -0.027 (p 0.406, n 914)
### gilts_index-linked (n=323, 1998-11-25 → 2026-09-03)

- bid-to-cover: p5 1.52 · p10 1.64 · p25 1.93 · mediana 2.25 · p75 2.675 · p90 3.17 · últimos 3 años (n=46): p10 2.94 mediana 3.245
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ -0.630 t -2.85 · fuertes (≥ p90): Δ 0.102 t 0.59
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.273 t 0.52 · fuertes (≥ p90): Δ -0.202 t -0.56
- ρ bid-to-cover vs retorno forward 20: -0.102 (p 0.067, n 321)
### tbills (n=3625, 2001-05-04 → 2026-09-04)

- bid-to-cover: p5 1.91 · p10 2.23 · p25 2.76 · mediana 3.62 · p75 5.07 · p90 6.88 · últimos 3 años (n=465): p10 2.514 mediana 3.45
- tail (pb): p50 1.31 · p75 2.419 · p90 4.974 · p95 8.015
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.110 t 1.02 · fuertes (≥ p90): Δ -0.036 t -0.54
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.253 t 1.56 · fuertes (≥ p90): Δ -0.139 t -1.14
- ρ bid-to-cover vs retorno forward 20: -0.059 (p 0.000, n 3610)
