# CAD — calibración empírica del régimen dual (BC / Tesoro / general)

Generado 2026-09-09T08:58:06Z · 975 semanas (2008-01-02 → 2026-09-02) · corte entrenamiento/prueba 2025-01-01 · verdad: USD/CAD (Valet FXUSDCAD; IEXE0101 noon before 2017) — + = CAD weaker

Hipótesis de la mesa (MMT/Mosler): INYECCIÓN → la divisa se debilita después (retorno forward positivo del cruce divisa-por-USD); DRENAJE → se fortalece. Un umbral sólo se propone si separa los retornos forward con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba y cubre ≥ 10 % de las semanas.

Ruptura estructural: 2020-03-23 — BoC moves to a floor system (settlement balances from ~C$250m to tens of billions; QE); CB anchors 50–70bn only meaningful after this date

Ruptura estructural: 2020-03-23 — era start set on the command line


## 1. ¿Explican los bloques el tipo de cambio? (Spearman, muestra completa)

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 sesiones | -0.028 | 0.378 | 974 | -0.005 | 0.909 | 594 |
| 10 sesiones | -0.018 | 0.569 | 973 | -0.056 | 0.173 | 593 |
| 20 sesiones | -0.039 | 0.226 | 971 | -0.020 | 0.633 | 591 |

Submuestra desde la ruptura (2020-03-23, 337 semanas):

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 | -0.055 | 0.317 | 336 | 0.020 | 0.709 | 336 |
| 10 | 0.088 | 0.108 | 335 | 0.010 | 0.862 | 335 |
| 20 | 0.071 | 0.198 | 333 | 0.025 | 0.653 | 333 |

## 2. Bloque central_bank — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2008–2009 ρ=0.16 (n=105) · 2010–2011 ρ=0.01 (n=104) · 2012–2013 ρ=-0.20 (n=104) · 2014–2015 ρ=-0.06 (n=105) · 2016–2017 ρ=-0.04 (n=104) · 2018–2019 ρ=-0.02 (n=104) · 2020–2021 ρ=-0.15 (n=105) · 2022–2023 ρ=0.05 (n=104) · 2024–2025 ρ=-0.14 (n=105) · 2026–2026 ρ=-0.17 (n=34)
- 10 sesiones: 2008–2009 ρ=0.09 (n=105) · 2010–2011 ρ=-0.09 (n=104) · 2012–2013 ρ=-0.10 (n=104) · 2014–2015 ρ=-0.14 (n=105) · 2016–2017 ρ=-0.15 (n=104) · 2018–2019 ρ=0.11 (n=104) · 2020–2021 ρ=-0.09 (n=105) · 2022–2023 ρ=0.21 (n=104) · 2024–2025 ρ=0.06 (n=105) · 2026–2026 ρ=-0.19 (n=33)
- 20 sesiones: 2008–2009 ρ=0.02 (n=105) · 2010–2011 ρ=-0.11 (n=104) · 2012–2013 ρ=-0.08 (n=104) · 2014–2015 ρ=-0.06 (n=105) · 2016–2017 ρ=-0.17 (n=104) · 2018–2019 ρ=0.16 (n=104) · 2020–2021 ρ=0.02 (n=105) · 2022–2023 ρ=0.12 (n=104) · 2024–2025 ρ=-0.04 (n=105) · 2026–2026 ρ=-0.14 (n=31)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=0.334 p=0.000 n=954

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 2. Bloque fiscal — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2008–2009 ρ=— (n=0) · 2010–2011 ρ=— (n=0) · 2012–2013 ρ=— (n=0) · 2014–2015 ρ=0.09 (n=38) · 2016–2017 ρ=-0.10 (n=104) · 2018–2019 ρ=-0.03 (n=104) · 2020–2021 ρ=-0.04 (n=105) · 2022–2023 ρ=0.13 (n=104) · 2024–2025 ρ=-0.10 (n=105) · 2026–2026 ρ=-0.02 (n=34)
- 10 sesiones: 2008–2009 ρ=— (n=0) · 2010–2011 ρ=— (n=0) · 2012–2013 ρ=— (n=0) · 2014–2015 ρ=-0.10 (n=38) · 2016–2017 ρ=-0.20 (n=104) · 2018–2019 ρ=-0.10 (n=104) · 2020–2021 ρ=-0.07 (n=105) · 2022–2023 ρ=0.13 (n=104) · 2024–2025 ρ=-0.00 (n=105) · 2026–2026 ρ=-0.14 (n=33)
- 20 sesiones: 2008–2009 ρ=— (n=0) · 2010–2011 ρ=— (n=0) · 2012–2013 ρ=— (n=0) · 2014–2015 ρ=-0.18 (n=38) · 2016–2017 ρ=-0.10 (n=104) · 2018–2019 ρ=0.03 (n=104) · 2020–2021 ρ=-0.03 (n=105) · 2022–2023 ρ=0.11 (n=104) · 2024–2025 ρ=-0.01 (n=105) · 2026–2026 ρ=-0.13 (n=31)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=-0.062 p=0.138 n=574

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 3. Pesos duales (OLS del retorno forward sobre los dos bloques estandarizados; walk-forward)

- 5 sesiones: {"beta_cb": -0.0421, "beta_fi": -0.0195, "t_cb": -0.92, "t_fi": -0.43, "n_train": 507, "n_test": 87, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 10 sesiones: {"beta_cb": 0.0186, "beta_fi": -0.094, "t_cb": 0.3, "t_fi": -1.5, "n_train": 507, "n_test": 86, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 20 sesiones: {"beta_cb": 0.0433, "beta_fi": -0.0241, "t_cb": 0.48, "t_fi": -0.27, "n_train": 507, "n_test": 84, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}

## A. Umbrales por frecuencia de la era operativa (desde 2020-03-23, 337 semanas)

| bloque | n | p10 | p20 | p33 | p50 | p67 | p80 | p90 | %% DRAIN a −0,5 | %% INJ a +0,5 | propuesta enter/exit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| central_bank | 337 | -1.33 | -1.0 | -0.71 | -0.03 | 0.09 | 0.9 | 1.29 | 0.34 | 0.23 | INJ ≥ 0.9 (salida 0.09) · DRAIN ≤ -1.0 (salida -0.71) |
| fiscal | 337 | -1.47 | -0.59 | -0.2 | 0.03 | 0.3 | 0.62 | 1.24 | 0.23 | 0.24 | INJ ≥ 0.62 (salida 0.3) · DRAIN ≤ -0.59 (salida -0.2) |

Convención de percentil: numpy.percentile default = linear interpolation between order statistics (on a discrete score the p80 can fall between two attainable values; the nearest attainable value is reported alongside).
- central_bank — corte de mesa (fuente única para el config): INJ ≥ 0.9 / DRAIN ≤ -1.0 → 20% / 22% de las semanas de la era · regla: p80/p20 of the floor era (337 wk), exit p67/p33 · propuesta automática p80/p20: 0.9 / -1.0 (p80 alcanzable más próximo 0.9, p20 -1.0)
- fiscal — corte de mesa (fuente única para el config): INJ ≥ 0.62 / DRAIN ≤ -0.59 → 20% / 20% de las semanas de la era · regla: p80/p20 of the floor era, exit p67/p33 · propuesta automática p80/p20: 0.62 / -0.59 (p80 alcanzable más próximo 0.62, p20 -0.59)

Estabilidad año a año — central_bank: 2020 p20 -0.98 / p50 -0.37 / p80 0.0 · 2021 p20 -0.87 / p50 -0.01 / p80 0.11 · 2022 p20 -0.89 / p50 -0.04 / p80 0.19 · 2023 p20 -0.96 / p50 -0.03 / p80 0.77 · 2024 p20 -1.33 / p50 -0.04 / p80 1.33 · 2025 p20 -1.32 / p50 0.04 / p80 1.26 · 2026 p20 -1.0 / p50 0.04 / p80 1.25

Estabilidad año a año — fiscal: 2020 p20 -0.2 / p50 0.09 / p80 0.59 · 2021 p20 -1.16 / p50 -0.08 / p80 0.86 · 2022 p20 -0.53 / p50 0.03 / p80 0.47 · 2023 p20 -0.35 / p50 -0.03 / p80 0.71 · 2024 p20 -1.78 / p50 -0.05 / p80 0.21 · 2025 p20 -0.42 / p50 0.21 / p80 0.64 · 2026 p20 -0.54 / p50 0.12 / p80 0.87

## B. Verdad de funding — puntuación del bloque vs Δ spread de estrés (4 y 12 semanas; hipótesis: INJECTION comprime, DRAIN ensancha → ρ negativa)

- central_bank, 4 semanas: ρ=-0.121 p=0.0274 (p block-bootstrap 8 s: 0.0085; rejilla de 62 cortes) n=333 · umbral INJECTION que sobrevive: ≥ -0.8 (Δ train -0.82, t -2.28; Δ test -0.72) · DRAIN: ≤ -0.1 (Δ train 0.84, t 2.44; Δ test 0.62)
- central_bank, 12 semanas: ρ=-0.068 p=0.2244 (p block-bootstrap 8 s: 0.1854; rejilla de 62 cortes) n=325 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 4 semanas: ρ=0.083 p=0.1313 (p block-bootstrap 8 s: 0.1000; rejilla de 62 cortes) n=333 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 12 semanas: ρ=0.107 p=0.0539 (p block-bootstrap 8 s: 0.0610; rejilla de 62 cortes) n=325 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno

## 4. Subastas — anclas empíricas y validación

### bills (n=2268, 1998-10-13 → 2026-09-08)

- bid-to-cover: p5 1.674 · p10 1.76 · p25 1.897 · mediana 2.059 · p75 2.245 · p90 2.465 · últimos 3 años (n=270): p10 1.678 mediana 1.993
- tail (pb): p50 0.55 · p75 0.87 · p90 1.4 · p95 1.873
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.281 t 1.95 · fuertes (≥ p90): Δ -0.006 t -0.08
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.517 t 2.22 · fuertes (≥ p90): Δ -0.297 t -2.19
- ρ bid-to-cover vs retorno forward 20: -0.056 (p 0.026, n 1590)
### bonds (n=899, 1998-10-28 → 2026-09-03)

- bid-to-cover: p5 2.085 · p10 2.159 · p25 2.265 · mediana 2.384 · p75 2.534 · p90 2.681 · últimos 3 años (n=164): p10 2.103 mediana 2.356
- tail (pb): p50 0.3 · p75 0.51 · p90 0.79 · p95 1.11
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.112 t 0.60 · fuertes (≥ p90): Δ -0.106 t -0.97
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.234 t 0.85 · fuertes (≥ p90): Δ -0.247 t -1.31
- ρ bid-to-cover vs retorno forward 20: -0.014 (p 0.700, n 775)
