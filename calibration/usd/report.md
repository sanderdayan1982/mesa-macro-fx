# USD — calibración empírica del régimen dual (BC / Tesoro / general)

Generado 2026-09-09T09:12:12Z · 870 semanas (2010-01-06 → 2026-09-02) · corte entrenamiento/prueba 2025-01-01 · verdad: 1 / broad dollar index (FRED DTWEXBGS) — + = USD weaker

Hipótesis de la mesa (MMT/Mosler): INYECCIÓN → la divisa se debilita después (retorno forward positivo del cruce divisa-por-USD); DRENAJE → se fortalece. Un umbral sólo se propone si separa los retornos forward con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba y cubre ≥ 10 % de las semanas.

Ruptura estructural: 2020-03-15 — COVID: emergency cuts, unlimited QE, reserves 1.7 → 4 tn; ON RRP era 2021–2023

Ruptura estructural: 2022-06-01 — QT starts (caps 47.5 → 95 bn/month); TGA rebuilds; RRP drains from 2.3 tn to ~0 by 2025 — ample-reserves-under-QT era (calibration era)

Ruptura estructural: 2022-06-01 — era start set on the command line


## 1. ¿Explican los bloques el tipo de cambio? (Spearman, muestra completa)

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 sesiones | -0.020 | 0.558 | 869 | 0.010 | 0.776 | 869 |
| 10 sesiones | 0.005 | 0.880 | 868 | 0.013 | 0.706 | 868 |
| 20 sesiones | 0.009 | 0.781 | 866 | 0.030 | 0.378 | 866 |

Submuestra desde la ruptura (2022-06-01, 223 semanas):

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 | 0.008 | 0.903 | 222 | -0.033 | 0.624 | 222 |
| 10 | 0.021 | 0.754 | 221 | 0.026 | 0.700 | 221 |
| 20 | 0.118 | 0.080 | 219 | 0.027 | 0.691 | 219 |

## 2. Bloque central_bank — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2010–2011 ρ=-0.12 (n=104) · 2012–2013 ρ=-0.04 (n=104) · 2014–2015 ρ=0.07 (n=105) · 2016–2017 ρ=0.02 (n=104) · 2018–2019 ρ=0.06 (n=104) · 2020–2021 ρ=-0.08 (n=105) · 2022–2023 ρ=0.12 (n=104) · 2024–2025 ρ=0.00 (n=105) · 2026–2026 ρ=-0.25 (n=34)
- 10 sesiones: 2010–2011 ρ=-0.10 (n=104) · 2012–2013 ρ=0.05 (n=104) · 2014–2015 ρ=-0.01 (n=105) · 2016–2017 ρ=0.08 (n=104) · 2018–2019 ρ=0.15 (n=104) · 2020–2021 ρ=-0.07 (n=105) · 2022–2023 ρ=0.18 (n=104) · 2024–2025 ρ=0.07 (n=105) · 2026–2026 ρ=-0.47 (n=33)
- 20 sesiones: 2010–2011 ρ=-0.13 (n=104) · 2012–2013 ρ=-0.04 (n=104) · 2014–2015 ρ=-0.00 (n=105) · 2016–2017 ρ=0.09 (n=104) · 2018–2019 ρ=0.13 (n=104) · 2020–2021 ρ=-0.07 (n=105) · 2022–2023 ρ=0.10 (n=104) · 2024–2025 ρ=0.18 (n=105) · 2026–2026 ρ=-0.11 (n=31)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=0.226 p=0.000 n=849

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 2. Bloque fiscal — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2010–2011 ρ=0.00 (n=104) · 2012–2013 ρ=-0.03 (n=104) · 2014–2015 ρ=-0.07 (n=105) · 2016–2017 ρ=0.03 (n=104) · 2018–2019 ρ=0.01 (n=104) · 2020–2021 ρ=0.03 (n=105) · 2022–2023 ρ=0.02 (n=104) · 2024–2025 ρ=-0.10 (n=105) · 2026–2026 ρ=0.09 (n=34)
- 10 sesiones: 2010–2011 ρ=0.03 (n=104) · 2012–2013 ρ=-0.08 (n=104) · 2014–2015 ρ=-0.11 (n=105) · 2016–2017 ρ=0.04 (n=104) · 2018–2019 ρ=-0.05 (n=104) · 2020–2021 ρ=0.01 (n=105) · 2022–2023 ρ=0.09 (n=104) · 2024–2025 ρ=-0.02 (n=105) · 2026–2026 ρ=0.12 (n=33)
- 20 sesiones: 2010–2011 ρ=-0.06 (n=104) · 2012–2013 ρ=0.03 (n=104) · 2014–2015 ρ=-0.06 (n=105) · 2016–2017 ρ=0.02 (n=104) · 2018–2019 ρ=-0.03 (n=104) · 2020–2021 ρ=-0.01 (n=105) · 2022–2023 ρ=0.14 (n=104) · 2024–2025 ρ=-0.08 (n=105) · 2026–2026 ρ=0.16 (n=31)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=0.123 p=0.000 n=849

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 3. Pesos duales (OLS del retorno forward sobre los dos bloques estandarizados; walk-forward)

- 5 sesiones: {"beta_cb": -0.0186, "beta_fi": 0.0184, "t_cb": -0.68, "t_fi": 0.67, "n_train": 782, "n_test": 87, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 10 sesiones: {"beta_cb": -0.0071, "beta_fi": 0.0083, "t_cb": -0.19, "t_fi": 0.22, "n_train": 782, "n_test": 86, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 20 sesiones: {"beta_cb": -0.0445, "beta_fi": 0.0192, "t_cb": -0.82, "t_fi": 0.35, "n_train": 782, "n_test": 84, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}

## A. Umbrales por frecuencia de la era operativa (desde 2022-06-01, 223 semanas)

| bloque | n | p10 | p20 | p33 | p50 | p67 | p80 | p90 | %% DRAIN a −0,5 | %% INJ a +0,5 | propuesta enter/exit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| central_bank | 223 | -0.7 | -0.6 | -0.3 | 0.0 | 0.0 | 0.1 | 0.3 | 0.25 | 0.04 | INJ ≥ 0.3 (salida 0.0) · DRAIN ≤ -0.6 (salida -0.3) |
| fiscal | 223 | 0.27 | 0.54 | 0.78 | 0.97 | 1.15 | 1.28 | 1.42 | 0.04 | 0.83 | INJ ≥ 1.28 (salida 1.15) · DRAIN ≤ -0.5 (salida -0.5) |

Convención de percentil: numpy.percentile default = linear interpolation between order statistics (on a discrete score the p80 can fall between two attainable values; the nearest attainable value is reported alongside).
- central_bank — corte de mesa (fuente única para el config): INJ ≥ 0.3 / DRAIN ≤ -0.6 → 18% / 21% de las semanas de la era · regla: p90/p20 of the QT era (INJ 10 %, DRAIN 20 %); level anchors kept · propuesta automática p80/p20: 0.1 / -0.6 (p80 alcanzable más próximo 0.1, p20 -0.6)
- fiscal — corte de mesa (fuente única para el config): INJ ≥ 1.28 / DRAIN ≤ -0.5 → 20% / 4% de las semanas de la era · regla: label INJECTION by construction; pace band p80 (strong) / p20 +0.54 (weak); absolute DRAIN ≤ −0.5 · propuesta automática p80/p20: 1.28 / 0.54 (p80 alcanzable más próximo 1.28, p20 0.54)

Estabilidad año a año — central_bank: 2022 p20 -0.6 / p50 -0.2 / p80 0.0 · 2023 p20 -0.3 / p50 0.0 / p80 0.0 · 2024 p20 -0.38 / p50 -0.3 / p80 0.0 · 2025 p20 -0.67 / p50 0.0 / p80 0.3 · 2026 p20 -0.7 / p50 -0.3 / p80 0.3

Estabilidad año a año — fiscal: 2022 p20 0.0 / p50 0.79 / p80 1.12 · 2023 p20 0.72 / p50 1.12 / p80 1.42 · 2024 p20 0.57 / p50 0.94 / p80 1.21 · 2025 p20 0.55 / p50 1.0 / p80 1.32 · 2026 p20 0.47 / p50 0.91 / p80 1.26

## B. Verdad de funding — puntuación del bloque vs Δ spread de estrés (4 y 12 semanas; hipótesis: INJECTION comprime, DRAIN ensancha → ρ negativa)

- central_bank, 4 semanas: ρ=0.109 p=0.1075 (p block-bootstrap 8 s: 0.1289; rejilla de 62 cortes) n=219 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- central_bank, 12 semanas: ρ=0.101 p=0.1451 (p block-bootstrap 8 s: 0.2299; rejilla de 62 cortes) n=211 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 4 semanas: ρ=-0.121 p=0.0741 (p block-bootstrap 8 s: 0.0975; rejilla de 62 cortes) n=219 · umbral INJECTION que sobrevive: ≥ 0.9 (Δ train -1.36, t -2.27; Δ test -0.86) · DRAIN: ≤ 0.7 (Δ train 1.57, t 2.55; Δ test 0.03)
- fiscal, 12 semanas: ρ=-0.052 p=0.4546 (p block-bootstrap 8 s: 0.5352; rejilla de 62 cortes) n=211 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno

## 4. Subastas — anclas empíricas y validación

### notes_bonds (n=1502, 2005-01-12 → 2026-09-08)

- bid-to-cover: p5 2.2 · p10 2.28 · p25 2.39 · mediana 2.54 · p75 2.74 · p90 3.13 · últimos 3 años (n=253): p10 2.35 mediana 2.52
- tail (pb): p50 4.5 · p75 6.0 · p90 7.3 · p95 8.1
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ -0.057 t -0.64 · fuertes (≥ p90): Δ 0.167 t 2.67
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.022 t 0.13 · fuertes (≥ p90): Δ 0.004 t 0.03
- ρ bid-to-cover vs retorno forward 20: -0.016 (p 0.553, n 1458)
### bills (n=4333, 2005-01-03 → 2026-09-08)

- bid-to-cover: p5 2.35 · p10 2.54 · p25 2.8 · mediana 3.09 · p75 3.73 · p90 4.56 · últimos 3 años (n=909): p10 2.67 mediana 2.91
- tail (pb): p50 2.0 · p75 3.0 · p90 5.0 · p95 7.0
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.013 t 0.28 · fuertes (≥ p90): Δ -0.080 t -2.15
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.133 t 1.48 · fuertes (≥ p90): Δ -0.200 t -2.74
- ρ bid-to-cover vs retorno forward 20: -0.047 (p 0.003, n 4149)
### tips (n=238, 2005-01-13 → 2026-08-20)

- bid-to-cover: p5 1.847 · p10 2.078 · p25 2.31 · mediana 2.445 · p75 2.62 · p90 2.8 · últimos 3 años (n=36): p10 2.31 mediana 2.44
- tail (pb): p50 6.2 · p75 8.0 · p90 10.2 · p95 12.235
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ — t — · fuertes (≥ p90): Δ 0.307 t 1.90
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ — t — · fuertes (≥ p90): Δ 0.575 t 1.55
- ρ bid-to-cover vs retorno forward 20: 0.031 (p 0.641, n 229)
### frn (n=154, 2014-01-29 → 2026-08-26)

- bid-to-cover: p5 2.606 · p10 2.713 · p25 2.88 · mediana 3.155 · p75 3.49 · p90 4.007 · últimos 3 años (n=36): p10 2.785 mediana 3.01
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ — t — · fuertes (≥ p90): Δ — t —
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ — t — · fuertes (≥ p90): Δ — t —
- ρ bid-to-cover vs retorno forward 20: -0.078 (p 0.335, n 153)
