# JPY — calibración empírica del régimen dual (BC / Tesoro / general)

Generado 2026-09-09T08:58:45Z · 168 semanas (2023-04-03 → 2026-09-01) · corte entrenamiento/prueba 2025-06-01 · verdad: USD/JPY 9:00 Tokyo (BoJ FM08 FXERD01) — + = JPY weaker

Hipótesis de la mesa (MMT/Mosler): INYECCIÓN → la divisa se debilita después (retorno forward positivo del cruce divisa-por-USD); DRENAJE → se fortalece. Un umbral sólo se propone si separa los retornos forward con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba y cubre ≥ 10 % de las semanas.

Ruptura estructural: 2024-03-19 — end of NIRP / YCC: policy rate 0–0.1 %, IOER floor; JGB purchase taper from 2024-07

Ruptura estructural: 2024-07-31 — first hike to 0.25 % (basic loan rate 0.50) — positive-rate floor era (calibration era)

Ruptura estructural: 2024-07-31 — era start set on the command line


## 1. ¿Explican los bloques el tipo de cambio? (Spearman, muestra completa)

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 sesiones | -0.063 | 0.421 | 167 | 0.030 | 0.705 | 167 |
| 10 sesiones | -0.056 | 0.473 | 166 | 0.032 | 0.686 | 166 |
| 20 sesiones | 0.078 | 0.320 | 164 | 0.033 | 0.677 | 164 |

Submuestra desde la ruptura (2024-07-31, 102 semanas):

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 | -0.029 | 0.770 | 101 | 0.001 | 0.991 | 101 |
| 10 | -0.079 | 0.433 | 100 | 0.011 | 0.912 | 100 |
| 20 | 0.104 | 0.306 | 98 | 0.015 | 0.886 | 98 |

## 2. Bloque central_bank — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2023–2024 ρ=-0.08 (n=87) · 2025–2026 ρ=-0.04 (n=80)
- 10 sesiones: 2023–2024 ρ=-0.01 (n=87) · 2025–2026 ρ=-0.12 (n=79)
- 20 sesiones: 2023–2024 ρ=0.05 (n=87) · 2025–2026 ρ=0.12 (n=77)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=-0.042 p=0.616 n=147

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 2. Bloque fiscal — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2023–2024 ρ=0.04 (n=87) · 2025–2026 ρ=0.03 (n=80)
- 10 sesiones: 2023–2024 ρ=0.04 (n=87) · 2025–2026 ρ=0.02 (n=79)
- 20 sesiones: 2023–2024 ρ=0.07 (n=87) · 2025–2026 ρ=-0.01 (n=77)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=0.060 p=0.467 n=147

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 3. Pesos duales (OLS del retorno forward sobre los dos bloques estandarizados; walk-forward)

- 5 sesiones: {"beta_cb": -0.119, "beta_fi": 0.0343, "t_cb": -0.83, "t_fi": 0.24, "n_train": 106, "n_test": 61, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 10 sesiones: {"beta_cb": -0.0325, "beta_fi": 0.0851, "t_cb": -0.16, "t_fi": 0.41, "n_train": 106, "n_test": 60, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 20 sesiones: {"beta_cb": 0.1426, "beta_fi": 0.0571, "t_cb": 0.47, "t_fi": 0.19, "n_train": 106, "n_test": 58, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}

## A. Umbrales por frecuencia de la era operativa (desde 2024-07-31, 102 semanas)

| bloque | n | p10 | p20 | p33 | p50 | p67 | p80 | p90 | %% DRAIN a −0,5 | %% INJ a +0,5 | propuesta enter/exit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| central_bank | 102 | 0.0 | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 0.0 | 0.85 | INJ ≥ 1.0 (salida 0.5) · DRAIN ≤ 0.0 (salida 0.5) |
| fiscal | 102 | -0.67 | -0.33 | -0.12 | 0.08 | 0.17 | 0.3 | 0.49 | 0.17 | 0.1 | INJ ≥ 0.3 (salida 0.17) · DRAIN ≤ -0.33 (salida -0.12) |

Convención de percentil: numpy.percentile default = linear interpolation between order statistics (on a discrete score the p80 can fall between two attainable values; the nearest attainable value is reported alongside).
- central_bank — corte de mesa (fuente única para el config): INJ ≥ 1.0 / DRAIN ≤ 0.0 → 4% / 15% de las semanas de la era · regla: only two values leave the modal +0.5 (INJ 4 %, DRAIN 15 %); block to be redesigned in v0.3 · propuesta automática p80/p20: 0.5 / 0.5 (p80 alcanzable más próximo 0.5, p20 0.5)
- fiscal — corte de mesa (fuente única para el config): INJ ≥ 0.3 / DRAIN ≤ -0.33 → 21% / 21% de las semanas de la era · regla: p80/p20 of the positive-rate era, exit p67/p33 · propuesta automática p80/p20: 0.3 / -0.33 (p80 alcanzable más próximo 0.3, p20 -0.33)

Estabilidad año a año — central_bank: 2024 p20 0.5 / p50 0.5 / p80 0.5 · 2025 p20 0.5 / p50 0.5 / p80 0.5 · 2026 p20 0.0 / p50 0.5 / p80 0.5

Estabilidad año a año — fiscal: 2024 p20 -0.29 / p50 0.12 / p80 0.23 · 2025 p20 -0.21 / p50 0.08 / p80 0.32 · 2026 p20 -0.44 / p50 0.05 / p80 0.29

## B. Verdad de funding — puntuación del bloque vs Δ spread de estrés (4 y 12 semanas; hipótesis: INJECTION comprime, DRAIN ensancha → ρ negativa)

- central_bank, 4 semanas: ρ=0.146 p=0.1517 (p block-bootstrap 8 s: 0.1739; rejilla de 62 cortes) n=98 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- central_bank, 12 semanas: ρ=0.219 p=0.0382 (p block-bootstrap 8 s: 0.0490; rejilla de 62 cortes) n=90 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 4 semanas: ρ=0.013 p=0.8967 (p block-bootstrap 8 s: 0.9050; rejilla de 62 cortes) n=98 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 12 semanas: ρ=0.044 p=0.6836 (p block-bootstrap 8 s: 0.6817; rejilla de 62 cortes) n=90 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno

## 4. Subastas — anclas empíricas y validación

### jgb_2y (n=482, 1979-08-27 → 2026-07-30)

- bid-to-cover: p5 1.499 · p10 1.79 · p25 2.492 · mediana 3.709 · p75 4.856 · p90 6.421 · últimos 3 años (n=35): p10 3.093 mediana 3.696
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ — t — · fuertes (≥ p90): Δ — t —
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ — t — · fuertes (≥ p90): Δ — t —
- ρ bid-to-cover vs retorno forward 20: -0.136 (p 0.110, n 139)
### jgb_5y (n=318, 2000-02-01 → 2026-07-09)

- bid-to-cover: p5 2.04 · p10 2.468 · p25 2.961 · mediana 3.513 · p75 4.038 · p90 4.577 · últimos 3 años (n=35): p10 3.134 mediana 3.696
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ — t — · fuertes (≥ p90): Δ — t —
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ — t — · fuertes (≥ p90): Δ — t —
- ρ bid-to-cover vs retorno forward 20: -0.145 (p 0.088, n 139)
### jgb_10y (n=448, 1989-04-05 → 2026-07-02)

- bid-to-cover: p5 1.978 · p10 2.264 · p25 2.656 · mediana 3.266 · p75 3.934 · p90 4.987 · últimos 3 años (n=35): p10 2.855 mediana 3.239
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ — t — · fuertes (≥ p90): Δ — t —
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ — t — · fuertes (≥ p90): Δ — t —
- ρ bid-to-cover vs retorno forward 20: -0.009 (p 0.919, n 139)
### jgb_20y (n=343, 1987-09-01 → 2026-07-14)

- bid-to-cover: p5 1.877 · p10 2.17 · p25 2.718 · mediana 3.283 · p75 3.782 · p90 4.23 · últimos 3 años (n=35): p10 2.969 mediana 3.283
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ — t — · fuertes (≥ p90): Δ — t —
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ — t — · fuertes (≥ p90): Δ — t —
- ρ bid-to-cover vs retorno forward 20: -0.110 (p 0.199, n 139)
### jgb_30y (n=200, 2007-04-17 → 2026-07-07)

- bid-to-cover: p5 2.852 · p10 2.957 · p25 3.119 · mediana 3.47 · p75 3.825 · p90 4.231 · últimos 3 años (n=35): p10 2.945 mediana 3.411
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ — t — · fuertes (≥ p90): Δ — t —
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ — t — · fuertes (≥ p90): Δ — t —
- ρ bid-to-cover vs retorno forward 20: -0.133 (p 0.118, n 139)
### jgb_40y (n=95, 2007-11-06 → 2026-07-22)

- bid-to-cover: p5 2.198 · p10 2.26 · p25 2.577 · mediana 2.865 · p75 3.422 · p90 3.851 · últimos 3 años (n=18): p10 2.184 mediana 2.561
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ — t — · fuertes (≥ p90): Δ — t —
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ — t — · fuertes (≥ p90): Δ — t —
- ρ bid-to-cover vs retorno forward 20: -0.261 (p 0.032, n 68)
### tbills (n=1397, 2009-02-04 → 2026-07-30)

- bid-to-cover: p5 2.736 · p10 2.954 · p25 3.397 · mediana 4.098 · p75 5.314 · p90 8.618 · últimos 3 años (n=219): p10 2.718 mediana 3.243
- tail (pb): p50 0.44 · p75 1.0 · p90 1.656 · p95 2.17
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.241 t 1.72 · fuertes (≥ p90): Δ — t —
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.741 t 2.93 · fuertes (≥ p90): Δ — t —
- ρ bid-to-cover vs retorno forward 20: -0.076 (p 0.022, n 895)
