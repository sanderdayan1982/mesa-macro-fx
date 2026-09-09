# CHF — calibración empírica del régimen dual (BC / Tesoro / general)

Generado 2026-09-09T09:00:47Z · 766 semanas (2012-01-06 → 2026-09-04) · corte entrenamiento/prueba 2025-01-01 · verdad: USD/CHF (BoE IADB XUDLSFD, CHF per USD) — + = CHF weaker

Hipótesis de la mesa (MMT/Mosler): INYECCIÓN → la divisa se debilita después (retorno forward positivo del cruce divisa-por-USD); DRENAJE → se fortalece. Un umbral sólo se propone si separa los retornos forward con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba y cubre ≥ 10 % de las semanas.

Ruptura estructural: 2015-01-15 — EUR/CHF floor abandoned; policy −0.75 %, tiered exemption (20×) — negative-rate era, no absorption

Ruptura estructural: 2022-09-22 — exit from negative rates: policy 0.5 %, tiered remuneration (threshold factor 28 → 25 …), absorption via SNB Bills and repos begins — calibration era

Ruptura estructural: 2022-09-22 — era start set on the command line


## 1. ¿Explican los bloques el tipo de cambio? (Spearman, muestra completa)

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 sesiones | -0.015 | 0.679 | 764 | -0.012 | 0.738 | 764 |
| 10 sesiones | -0.007 | 0.849 | 763 | -0.016 | 0.655 | 763 |
| 20 sesiones | 0.014 | 0.691 | 761 | 0.001 | 0.985 | 761 |

Submuestra desde la ruptura (2022-09-22, 207 semanas):

| horizonte | BC ρ | p | n | Tesoro ρ | p | n |
|---|---|---|---|---|---|---|
| 5 | 0.001 | 0.993 | 205 | 0.000 | 0.997 | 205 |
| 10 | 0.056 | 0.424 | 204 | -0.001 | 0.987 | 204 |
| 20 | 0.170 | 0.016 | 202 | 0.021 | 0.768 | 202 |

## 2. Bloque central_bank — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2012–2013 ρ=-0.13 (n=104) · 2014–2015 ρ=0.14 (n=104) · 2016–2017 ρ=-0.13 (n=105) · 2018–2019 ρ=-0.05 (n=104) · 2020–2021 ρ=-0.02 (n=105) · 2022–2023 ρ=-0.15 (n=104) · 2024–2025 ρ=0.04 (n=104) · 2026–2026 ρ=-0.18 (n=34)
- 10 sesiones: 2012–2013 ρ=-0.18 (n=104) · 2014–2015 ρ=0.10 (n=104) · 2016–2017 ρ=-0.11 (n=105) · 2018–2019 ρ=-0.04 (n=104) · 2020–2021 ρ=-0.10 (n=105) · 2022–2023 ρ=-0.13 (n=104) · 2024–2025 ρ=0.07 (n=104) · 2026–2026 ρ=0.08 (n=33)
- 20 sesiones: 2012–2013 ρ=-0.28 (n=104) · 2014–2015 ρ=0.05 (n=104) · 2016–2017 ρ=-0.04 (n=105) · 2018–2019 ρ=-0.01 (n=104) · 2020–2021 ρ=-0.17 (n=105) · 2022–2023 ρ=-0.09 (n=104) · 2024–2025 ρ=0.21 (n=104) · 2026–2026 ρ=0.13 (n=31)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=0.242 p=0.000 n=745

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 2. Bloque fiscal — walk-forward (bloques de 2 años, fuera de muestra cada uno)

- 5 sesiones: 2012–2013 ρ=-0.30 (n=104) · 2014–2015 ρ=0.09 (n=104) · 2016–2017 ρ=0.00 (n=105) · 2018–2019 ρ=-0.04 (n=104) · 2020–2021 ρ=0.10 (n=105) · 2022–2023 ρ=0.10 (n=104) · 2024–2025 ρ=-0.02 (n=104) · 2026–2026 ρ=0.00 (n=34)
- 10 sesiones: 2012–2013 ρ=-0.41 (n=104) · 2014–2015 ρ=0.03 (n=104) · 2016–2017 ρ=0.11 (n=105) · 2018–2019 ρ=-0.01 (n=104) · 2020–2021 ρ=0.20 (n=105) · 2022–2023 ρ=0.10 (n=104) · 2024–2025 ρ=0.01 (n=104) · 2026–2026 ρ=-0.16 (n=33)
- 20 sesiones: 2012–2013 ρ=-0.51 (n=104) · 2014–2015 ρ=-0.10 (n=104) · 2016–2017 ρ=0.19 (n=105) · 2018–2019 ρ=0.06 (n=104) · 2020–2021 ρ=0.32 (n=105) · 2022–2023 ρ=0.15 (n=104) · 2024–2025 ρ=0.08 (n=104) · 2026–2026 ρ=-0.09 (n=31)
- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=-0.096 p=0.009 n=745

### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)

| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 10 | ninguno | — | — | — | — | ninguno | — | — | — | — |
| 20 | ninguno | — | — | — | — | ninguno | — | — | — | — |

## 3. Pesos duales (OLS del retorno forward sobre los dos bloques estandarizados; walk-forward)

- 5 sesiones: {"beta_cb": -0.0014, "beta_fi": -0.0233, "t_cb": -0.03, "t_fi": -0.47, "n_train": 678, "n_test": 86, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 10 sesiones: {"beta_cb": -0.01, "beta_fi": -0.0255, "t_cb": -0.15, "t_fi": -0.38, "n_train": 678, "n_test": 85, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}
- 20 sesiones: {"beta_cb": -0.0047, "beta_fi": 0.0194, "t_cb": -0.05, "t_fi": 0.23, "n_train": 678, "n_test": 83, "status": "neither block significant in the training window — keep the agreement rule, no dual weights"}

## A. Umbrales por frecuencia de la era operativa (desde 2022-09-22, 207 semanas)

| bloque | n | p10 | p20 | p33 | p50 | p67 | p80 | p90 | %% DRAIN a −0,5 | %% INJ a +0,5 | propuesta enter/exit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| central_bank | 207 | -1.5 | -1.5 | -1.0 | -0.5 | 0.0 | 0.5 | 1.0 | 0.51 | 0.22 | INJ ≥ 1.0 (salida 0.5) · DRAIN ≤ -1.0 (salida -0.5) |
| fiscal | 207 | -0.5 | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 | 0.5 | 0.18 | 0.23 | INJ ≥ 0.5 (salida 0.5) · DRAIN ≤ -0.5 (salida -0.5) |

Convención de percentil: numpy.percentile default = linear interpolation between order statistics (on a discrete score the p80 can fall between two attainable values; the nearest attainable value is reported alongside).
- central_bank — corte de mesa (fuente única para el config): INJ ≥ 1.0 / DRAIN ≤ -1.0 → 18% / 41% de las semanas de la era · regla: 13-week ternary must fire (±1); absorption-share penalty alone is not a regime · propuesta automática p80/p20: 0.5 / -1.5 (p80 alcanzable más próximo 0.5, p20 -1.5)
- fiscal — corte de mesa (fuente única para el config): INJ ≥ 0.5 / DRAIN ≤ -0.5 → 23% / 18% de las semanas de la era · regla: ternary band by design (±0.5); funding-validated at 12 weeks · propuesta automática p80/p20: 0.5 / 0.0 (p80 alcanzable más próximo 0.5, p20 0.0)

Estabilidad año a año — central_bank: 2023 p20 -1.5 / p50 -1.5 / p80 -0.5 · 2024 p20 -1.0 / p50 0.0 / p80 0.0 · 2025 p20 -1.0 / p50 0.0 / p80 1.0 · 2026 p20 0.0 / p50 0.0 / p80 1.0

Estabilidad año a año — fiscal: 2023 p20 0.0 / p50 0.0 / p80 0.0 · 2024 p20 0.0 / p50 0.0 / p80 0.5 · 2025 p20 0.0 / p50 0.0 / p80 0.5 · 2026 p20 -0.5 / p50 0.0 / p80 0.0

## B. Verdad de funding — puntuación del bloque vs Δ spread de estrés (4 y 12 semanas; hipótesis: INJECTION comprime, DRAIN ensancha → ρ negativa)

- central_bank, 4 semanas: ρ=-0.016 p=0.8242 (p block-bootstrap 8 s: 0.8571; rejilla de 62 cortes) n=203 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- central_bank, 12 semanas: ρ=0.041 p=0.5714 (p block-bootstrap 8 s: 0.7326; rejilla de 62 cortes) n=195 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 4 semanas: ρ=-0.020 p=0.7763 (p block-bootstrap 8 s: 0.8301; rejilla de 62 cortes) n=203 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno
- fiscal, 12 semanas: ρ=-0.186 p=0.0091 (p block-bootstrap 8 s: 0.0805; rejilla de 62 cortes) n=195 · umbral INJECTION que sobrevive: ninguno · DRAIN: ninguno

## 4. Subastas — anclas empíricas y validación

### mmdrc_3m (n=767, 2012-01-03 → 2026-09-08)

- bid-to-cover: p5 2.771 · p10 3.052 · p25 3.761 · mediana 4.681 · p75 5.676 · p90 7.012 · últimos 3 años (n=158): p10 2.979 mediana 4.252
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.091 t 0.56 · fuertes (≥ p90): Δ 0.219 t 1.32
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ -0.070 t -0.25 · fuertes (≥ p90): Δ 0.313 t 1.02
- ρ bid-to-cover vs retorno forward 20: 0.003 (p 0.926, n 762)
### confed_bonds (n=302, 2010-11-10 → 2026-07-08)

- bid-to-cover: p5 1.142 · p10 1.185 · p25 1.342 · mediana 1.62 · p75 2.098 · p90 2.514 · últimos 3 años (n=64): p10 1.188 mediana 1.532
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ -0.186 t -0.78 · fuertes (≥ p90): Δ -0.129 t -0.56
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ -0.296 t -0.85 · fuertes (≥ p90): Δ 0.430 t 1.06
- ρ bid-to-cover vs retorno forward 20: 0.058 (p 0.318, n 302)
### snb_bills_28d (n=201, 2022-09-22 → 2026-07-23)

- bid-to-cover: p5 1.012 · p10 1.016 · p25 1.063 · mediana 1.17 · p75 1.449 · p90 1.938 · últimos 3 años (n=151): p10 1.013 mediana 1.125
- subastas débiles (≤ p10) vs resto, retorno FX forward 5: Δ 0.290 t 1.95 · fuertes (≥ p90): Δ 0.055 t 0.28
- subastas débiles (≤ p10) vs resto, retorno FX forward 20: Δ 0.874 t 2.40 · fuertes (≥ p90): Δ 0.276 t 0.60
- ρ bid-to-cover vs retorno forward 20: -0.169 (p 0.017, n 201)
