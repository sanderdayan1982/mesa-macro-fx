# EUR — calibración empírica del régimen dual (BC / Tesoro / general)

Generado 2026-09-09T09:03:24Z · 558 semanas (2016-01-01 → 2026-09-04) · corte entrenamiento/prueba 2025-01-01 · verdad: EUR per USD (1 / ECB EXR USD/EUR reference) — + = EUR weaker

Hipótesis de la mesa (MMT/Mosler): INYECCIÓN → la divisa se debilita después (retorno forward positivo del cruce divisa-por-USD); DRENAJE → se fortalece. Un umbral sólo se propone si separa los retornos forward con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba y cubre ≥ 10 % de las semanas.

Ruptura estructural: 2015-03-09 — APP starts (PSPP): excess liquidity from 0.1 to 4.7 tn by 2022; DFR −0.20 → −0.50

Ruptura estructural: 2022-09-14 — DFR positive (0.75 %) after the July exit from negative rates; TLTRO repayments and APP/PEPP run-off → excess liquidity falls from 4.7 to 2.2 tn — floor-under-QT era (calibration era)

Ruptura estructural: 2022-09-14 — era start set on the command line


## 1. ¿Explican los bloques el tipo de cambio? (Spearman, muestra completa)

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 sesiones | 0.039 | 0.363 | 557 | 0.003 | 0.937 | 557 |
| 10 sesiones | 0.053 | 0.214 | 556 | -0.033 | 0.435 | 556 |
| 20 sesiones | 0.028 | 0.512 | 554 | -0.037 | 0.386 | 554 |

Submuestra desde la ruptura (2022-09-14, 208 semanas):

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 | -0.054 | 0.436 | 207 | 0.080 | 0.251 | 207 |
| 10 | -0.012 | 0.861 | 206 | 0.079 | 0.262 | 206 |
| 20 | -0.053 | 0.453 | 204 | -0.018 | 0.796 | 204 |

## 2. Bloque central_bank — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2016–2017 ρ=0.07 (n=105) · 2018–2019 ρ=0.07 (n=104) · 2020–2021 ρ=-0.09 (n=105) · 2022–2023 ρ=0.14 (n=104) · 2024–2025 ρ=-0.04 (n=104) · 2026–2026 ρ=-0.19 (n=35)
- 10 sesiones: 2016–2017 ρ=0.04 (n=105) · 2018–2019 ρ=0.12 (n=104) · 2020–2021 ρ=-0.14 (n=105) · 2022–2023 ρ=0.20 (n=104) · 2024–2025 ρ=0.01 (n=104) · 2026–2026 ρ=-0.11 (n=34)
- 20 sesiones: 2016–2017 ρ=0.02 (n=105) · 2018–2019 ρ=0.03 (n=104) · 2020–2021 ρ=-0.31 (n=105) · 2022–2023 ρ=0.23 (n=104) · 2024–2025 ρ=-0.02 (n=104) · 2026–2026 ρ=-0.17 (n=32)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=-0.182 p=0.000 n=537

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 2. Bloque fiscal — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2016–2017 ρ=-0.02 (n=105) · 2018–2019 ρ=-0.06 (n=104) · 2020–2021 ρ=-0.03 (n=105) · 2022–2023 ρ=0.05 (n=104) · 2024–2025 ρ=0.01 (n=104) · 2026–2026 ρ=0.23 (n=35)
- 10 sesiones: 2016–2017 ρ=-0.04 (n=105) · 2018–2019 ρ=-0.18 (n=104) · 2020–2021 ρ=-0.05 (n=105) · 2022–2023 ρ=0.01 (n=104) · 2024–2025 ρ=0.05 (n=104) · 2026–2026 ρ=0.17 (n=34)
- 20 sesiones: 2016–2017 ρ=0.03 (n=105) · 2018–2019 ρ=-0.32 (n=104) · 2020–2021 ρ=0.09 (n=105) · 2022–2023 ρ=-0.06 (n=104) · 2024–2025 ρ=0.01 (n=104) · 2026–2026 ρ=-0.09 (n=32)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=-0.170 p=0.000 n=537

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 3. Pesos duales (OLS del retorno forward sobre los dos bloques estandarizados; walk-forward)

- 5 sesiones: {"beta_cb": 0.0554, "beta_fi": -0.0221, "t_cb": 1.2, "t_fi": -0.48, "n_train": 470, "n_test": 87, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 10 sesiones: {"beta_cb": 0.0973, "beta_fi": -0.0355, "t_cb": 1.53, "t_fi": -0.56, "n_train": 470, "n_test": 86, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 20 sesiones: {"beta_cb": 0.0496, "beta_fi": -0.0572, "t_cb": 0.58, "t_fi": -0.66, "n_train": 470, "n_test": 84, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}

## A. Umbrales por frecuencia de la era operativa (desde 2022-09-14, 208 semanas)

| bloque | n | p10 | p20 | p33 | p50 | p67 | p80 | p90 | %% DRAIN a −0,5 | %% INJ a +0,5 | propuesta enter/exit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| central_bank | 208 | -0.8 | -0.64 | -0.43 | -0.25 | -0.08 | 0.12 | 0.27 | 0.3 | 0.04 | INJ ≥ 0.25 (salida -0.08) · DRAIN ≤ -0.6 (salida -0.43) |
| fiscal | 208 | -0.11 | -0.04 | 0.17 | 0.34 | 0.56 | 0.7 | 0.89 | 0.0 | 0.38 | INJ ≥ 0.7 (salida 0.56) · DRAIN ≤ -0.04 (salida 0.17) |

Convención de percentil: numpy.percentile default = linear interpolation between order statistics (on a discrete score the p80 can fall between two attainable values; the nearest attainable value is reported alongside).
- central_bank — corte de mesa (fuente única para el config): INJ ≥ 0.25 / DRAIN ≤ -0.6 → 11% / 24% de las semanas de la era · regla: p90/p20 of the floor-under-QT era; DRAIN ≤ −0.6 survives the funding test · propuesta automática p80/p20: 0.12 / -0.64 (p80 alcanzable más próximo 0.12, p20 -0.64)
- fiscal — corte de mesa (fuente única para el config): INJ ≥ 0.7 / DRAIN ≤ -0.04 → 21% / 21% de las semanas de la era · regla: p80/p20 of the era; DRAIN impossible until the structural deficit weighs 0.25 (v0.3) · propuesta automática p80/p20: 0.7 / -0.04 (p80 alcanzable más próximo 0.7, p20 -0.04)

Estabilidad año a año — central_bank: 2023 p20 -0.47 / p50 -0.09 / p80 0.21 · 2024 p20 -0.62 / p50 -0.32 / p80 -0.01 · 2025 p20 -0.69 / p50 -0.33 / p80 -0.05 · 2026 p20 -0.66 / p50 -0.45 / p80 -0.01

Estabilidad año a año — fiscal: 2023 p20 0.26 / p50 0.48 / p80 0.87 · 2024 p20 0.06 / p50 0.29 / p80 0.57 · 2025 p20 -0.11 / p50 0.09 / p80 0.57 · 2026 p20 -0.09 / p50 0.3 / p80 0.64

## B. Verdad de funding — puntuación del bloque vs Δ spread de estrés (4 y 12 semanas; hipótesis: INJECTION comprime, DRAIN ensancha → ρ negativa)

- central_bank, 4 semanas: ρ=-0.306 p=0.0000 (p block-bootstrap 8 s: 0.0005; rejilla de 62 cortes) n=204 · umbral INJECTION que sobrevive: ≥ -0.5 (Δ train -0.49, t -3.61; Δ test -0.17) · DRAIN: ≤ -0.6 (Δ train 0.54, t 3.62; Δ test 0.08)
- central_bank, 12 semanas: ρ=-0.333 p=0.0000 (p block-bootstrap 8 s: 0.0005; rejilla de 62 cortes) n=196 · umbral INJECTION que sobrevive: ≥ -0.3 (Δ train -0.53, t -4.53; Δ test -0.07) · DRAIN: ≤ -0.3 (Δ train 0.53, t 4.62; Δ test 0.07)
- fiscal, 4 semanas: ρ=-0.077 p=0.2709 (p block-bootstrap 8 s: 0.3233; rejilla de 62 cortes) n=204 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 12 semanas: ρ=0.077 p=0.2810 (p block-bootstrap 8 s: 0.3683; rejilla de 62 cortes) n=196 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno

## 4. Subastas — anclas empíricas y validación

### bunds (n=1201, 1999-01-06 → 2026-09-08)

- bid-to-cover: p5 1.1 · p10 1.2 · p25 1.4 · mediana 1.7 · p75 2.1 · p90 2.7 · últimos 3 años (n=319): p10 1.4 mediana 2.1
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.022 t 0.20 · fuertes (≥ p90): Δ -0.215 t -1.98
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.342 t 1.85 · fuertes (≥ p90): Δ -0.343 t -1.78
- ρ bid-to-cover vs retorno forward 20: -0.107 (p 0.000, n 1191)
### bubills (n=776, 1999-01-13 → 2026-09-07)

- bid-to-cover: p5 1.2 · p10 1.3 · p25 1.5 · mediana 1.9 · p75 2.4 · p90 2.9 · últimos 3 años (n=198): p10 1.3 mediana 1.9
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ -0.035 t -0.31 · fuertes (≥ p90): Δ 0.204 t 1.53
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ -0.326 t -1.36 · fuertes (≥ p90): Δ 0.872 t 3.40
- ρ bid-to-cover vs retorno forward 20: 0.104 (p 0.004, n 770)
### ilb (n=166, 2007-04-25 → 2023-10-10)

- bid-to-cover: p5 1.2 · p10 1.3 · p25 1.5 · mediana 1.7 · p75 2.0 · p90 2.4 · últimos 3 años (n=4): p10 1.19 mediana 1.45
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.272 t 1.70 · fuertes (≥ p90): Δ — t —
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.518 t 1.31 · fuertes (≥ p90): Δ — t —
- ρ bid-to-cover vs retorno forward 20: -0.078 (p 0.315, n 166)
