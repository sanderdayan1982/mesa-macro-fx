# NZD — calibración empírica del régimen dual (BC / Tesoro / general)

Generado 2026-09-09T09:05:59Z · 385 semanas (2019-01-03 → 2026-09-03) · corte entrenamiento/prueba 2025-01-01 · verdad: NZD per USD (1 / RBNZ B1 NZD/USD daily) — + = NZD weaker

Hipótesis de la mesa (MMT/Mosler): INYECCIÓN → la divisa se debilita después (retorno forward positivo del cruce divisa-por-USD); DRENAJE → se fortalece. Un umbral sólo se propone si separa los retornos forward con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba y cubre ≥ 10 % de las semanas.

Ruptura estructural: 2020-03-23 — LSAP starts: settlement cash from ~7 bn to > 40 bn; floor system (ODR = OCR)

Ruptura estructural: 2022-07-01 — LSAP unwind: bond sales to NZDM begin (NZ$5 bn/yr), settlement cash declines toward the new steady state — calibration era

Ruptura estructural: 2022-07-01 — era start set on the command line


## 1. ¿Explican los bloques el tipo de cambio? (Spearman, muestra completa)

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 sesiones | 0.058 | 0.256 | 384 | -0.019 | 0.710 | 384 |
| 10 sesiones | 0.018 | 0.723 | 383 | -0.025 | 0.631 | 383 |
| 20 sesiones | -0.059 | 0.254 | 381 | -0.041 | 0.428 | 381 |

Submuestra desde la ruptura (2022-07-01, 210 semanas):

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 | 0.029 | 0.680 | 209 | 0.030 | 0.663 | 209 |
| 10 | -0.013 | 0.851 | 208 | 0.040 | 0.565 | 208 |
| 20 | -0.082 | 0.244 | 206 | 0.047 | 0.504 | 206 |

## 2. Bloque central_bank — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2019–2020 ρ=-0.03 (n=101) · 2021–2022 ρ=0.12 (n=100) · 2023–2024 ρ=0.01 (n=100) · 2025–2026 ρ=0.14 (n=83)
- 10 sesiones: 2019–2020 ρ=-0.14 (n=101) · 2021–2022 ρ=0.05 (n=100) · 2023–2024 ρ=0.02 (n=100) · 2025–2026 ρ=0.10 (n=82)
- 20 sesiones: 2019–2020 ρ=-0.28 (n=101) · 2021–2022 ρ=-0.09 (n=100) · 2023–2024 ρ=0.03 (n=100) · 2025–2026 ρ=-0.04 (n=80)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=0.057 p=0.275 n=364

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 2. Bloque fiscal — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2019–2020 ρ=-0.11 (n=101) · 2021–2022 ρ=0.01 (n=100) · 2023–2024 ρ=0.10 (n=100) · 2025–2026 ρ=-0.07 (n=83)
- 10 sesiones: 2019–2020 ρ=-0.17 (n=101) · 2021–2022 ρ=0.05 (n=100) · 2023–2024 ρ=0.04 (n=100) · 2025–2026 ρ=-0.02 (n=82)
- 20 sesiones: 2019–2020 ρ=-0.28 (n=101) · 2021–2022 ρ=0.02 (n=100) · 2023–2024 ρ=0.05 (n=100) · 2025–2026 ρ=0.08 (n=80)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=0.051 p=0.333 n=364

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 3. Pesos duales (OLS del retorno forward sobre los dos bloques estandarizados; walk-forward)

- 5 sesiones: {"beta_cb": 0.0352, "beta_fi": -0.0398, "t_cb": 0.39, "t_fi": -0.44, "n_train": 301, "n_test": 83, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 10 sesiones: {"beta_cb": 0.0033, "beta_fi": -0.1084, "t_cb": 0.03, "t_fi": -0.89, "n_train": 301, "n_test": 82, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 20 sesiones: {"beta_cb": -0.192, "beta_fi": -0.1709, "t_cb": -1.11, "t_fi": -0.99, "n_train": 301, "n_test": 80, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}

## A. Umbrales por frecuencia de la era operativa (desde 2022-07-01, 210 semanas)

| bloque | n | p10 | p20 | p33 | p50 | p67 | p80 | p90 | %% DRAIN a −0,5 | %% INJ a +0,5 | propuesta enter/exit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| central_bank | 210 | -1.0 | -0.5 | -0.5 | 0.0 | 0.25 | 0.35 | 0.75 | 0.35 | 0.2 | INJ ≥ 0.75 (salida 0.25) · DRAIN ≤ -0.5 (salida -0.25) |
| fiscal | 210 | -0.5 | -0.5 | 0.0 | 0.0 | 0.0 | 0.5 | 0.5 | 0.32 | 0.23 | INJ ≥ 0.5 (salida 0.5) · DRAIN ≤ -0.5 (salida -0.5) |

Convención de percentil: numpy.percentile default = linear interpolation between order statistics (on a discrete score the p80 can fall between two attainable values; the nearest attainable value is reported alongside).
- central_bank — corte de mesa (fuente única para el config): INJ ≥ 0.75 / DRAIN ≤ -0.5 → 20% / 35% de las semanas de la era · regla: natural gaps of the discrete score (INJ 20 %, DRAIN 35 % of the LSAP-unwind era) · propuesta automática p80/p20: 0.35 / -0.5 (p80 alcanzable más próximo 0.25, p20 -0.5)
- fiscal — corte de mesa (fuente única para el config): INJ ≥ 0.5 / DRAIN ≤ -0.5 → 23% / 32% de las semanas de la era · regla: ternary band by design (±0.5) · propuesta automática p80/p20: 0.5 / -0.5 (p80 alcanzable más próximo 0.5, p20 -0.5)

Estabilidad año a año — central_bank: 2022 p20 -0.5 / p50 0.0 / p80 0.25 · 2023 p20 -0.5 / p50 0.0 / p80 0.35 · 2024 p20 -0.5 / p50 0.0 / p80 0.35 · 2025 p20 -0.5 / p50 0.0 / p80 0.75 · 2026 p20 -0.5 / p50 0.0 / p80 0.45

Estabilidad año a año — fiscal: 2022 p20 -0.5 / p50 0.0 / p80 0.5 · 2023 p20 -0.5 / p50 0.0 / p80 0.5 · 2024 p20 -0.5 / p50 0.0 / p80 0.1 · 2025 p20 -0.5 / p50 0.0 / p80 0.0 · 2026 p20 -0.5 / p50 0.0 / p80 0.2

## B. Verdad de funding — puntuación del bloque vs Δ spread de estrés (4 y 12 semanas; hipótesis: INJECTION comprime, DRAIN ensancha → ρ negativa)

- central_bank, 4 semanas: ρ=0.070 p=0.3176 (p block-bootstrap 8 s: 0.3668; rejilla de 62 cortes) n=206 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- central_bank, 12 semanas: ρ=0.058 p=0.4134 (p block-bootstrap 8 s: 0.4443; rejilla de 62 cortes) n=198 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 4 semanas: ρ=0.098 p=0.1625 (p block-bootstrap 8 s: 0.2454; rejilla de 62 cortes) n=206 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 12 semanas: ρ=-0.024 p=0.7359 (p block-bootstrap 8 s: 0.8041; rejilla de 62 cortes) n=198 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno

## 4. Subastas — anclas empíricas y validación

### tbills (n=4138, 1993-03-09 → 2026-09-08)

- bid-to-cover: p5 1.25 · p10 1.6 · p25 2.267 · mediana 3.2 · p75 4.2 · p90 5.026 · últimos 3 años (n=438): p10 1.3 mediana 2.75
- tail (pb): p50 0.8 · p75 1.5 · p90 2.75 · p95 3.988
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.253 t 2.24 · fuertes (≥ p90): Δ -0.481 t -2.57
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.492 t 2.15 · fuertes (≥ p90): Δ -0.381 t -1.15
- ρ bid-to-cover vs retorno forward 20: -0.029 (p 0.369, n 989)
### nzgb_nominal (n=2035, 1983-09-08 → 2026-09-03)

- bid-to-cover: p5 1.299 · p10 1.589 · p25 2.16 · mediana 2.916 · p75 3.804 · p90 4.84 · últimos 3 años (n=364): p10 1.857 mediana 3.33
- tail (pb): p50 0.85 · p75 1.54 · p90 2.976 · p95 5.124
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ -0.026 t -0.12 · fuertes (≥ p90): Δ -0.011 t -0.06
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.481 t 1.09 · fuertes (≥ p90): Δ -0.455 t -1.24
- ρ bid-to-cover vs retorno forward 20: -0.079 (p 0.021, n 866)
