# USD — engine v0.3 (era 2022-06-01, 223 semanas; ventanas ancladas a la era; persistencia 7/0 días; regla de acuerdo)


## central_bank — niveles: phase, reserves_status, rrp_status · flujos: net_liquidity_band, primary_credit_panic, tga_status

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.50 / -0.14 / 0.11 (-0.60 / 0.00 / 0.30) | +0.11 (+0.00) / -0.50 (-0.30) | 24 / 50 / 26 % | 0.24 | 60 · 3.7 | 0.088 (0.344) · -0.74 · 2.53 |
| 0.5 | -0.40 / -0.10 / 0.05 (-0.45 / -0.10 / 0.10) | +0.05 (+0.05) / -0.40 (-0.25) | 34 / 41 / 25 % | 0.25 | 68 · 3.2 | 0.091 (0.305) · 0.34 · 2.21 |
| 0.25 | -0.40 / -0.08 / 0.07 (-0.42 / -0.12 / 0.11) | +0.07 (+0.00) / -0.41 (-0.23) | 32 / 45 / 23 % | 0.23 | 71 · 3.1 | 0.101 (0.252) · 0.53 · 2.41 |
| 0.0 | -0.40 / -0.10 / 0.10 (-0.40 / -0.20 / 0.10) | +0.10 (+0.00) / -0.40 (-0.20) | 30 / 40 / 29 % | 0.29 | 60 · 3.7 | 0.081 (0.354) · 0.40 · 2.35 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 21 % / DRAIN 28 % / cambios 74 · consecutive_7_0 → INJ 13 % / DRAIN 14 % / cambios 38 · mean_7_0 → INJ 24 % / DRAIN 26 % / cambios 60 · mean_7_7 → INJ 30 % / DRAIN 33 % / cambios 43

## fiscal — niveles: structural_ntf_60d · flujos: daily_surprise

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | 0.62 / 0.96 / 1.21 (0.54 / 0.97 / 1.28) | +1.22 (+1.11) / +0.61 (+0.81) | 25 / 51 / 24 % | 0.24 | 57 · 3.8 | -0.093 (0.287) · 0.51 · -0.21 |
| 0.5 | 0.40 / 0.68 / 0.88 (0.33 / 0.70 / 0.93) | +0.88 (+0.79) / +0.39 (+0.54) | 25 / 52 / 23 % | 0.23 | 72 · 3.1 | -0.106 (0.171) · 0.45 · 0.08 |
| 0.25 | 0.24 / 0.54 / 0.74 (0.19 / 0.59 / 0.76) | +0.74 (+0.64) / +0.24 (+0.42) | 25 / 51 / 25 % | 0.25 | 81 · 2.7 | -0.113 (0.119) · -0.37 · -1.13 |
| 0.0 | 0.14 / 0.39 / 0.58 (0.03 / 0.45 / 0.62) | +0.58 (+0.49) / +0.13 (+0.27) | 23 / 51 / 26 % | 0.23 | 84 · 2.6 | -0.107 (0.134) · -0.54 · -1.18 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 26 % / DRAIN 25 % / cambios 77 · consecutive_7_0 → INJ 12 % / DRAIN 15 % / cambios 44 · mean_7_0 → INJ 25 % / DRAIN 24 % / cambios 57 · mean_7_7 → INJ 33 % / DRAIN 31 % / cambios 46

## Régimen general (regla de acuerdo, pesos {'central_bank': 1.0, 'fiscal': 1.0})

INYECCIÓN 7 % · NEUTRAL parcial 72 % · NEUTRAL conflicto 11 % · DRENAJE 10 % · cambios 63 · racha media 3.5 semanas

## Parche de config (regime.dual)

```json
{
 "version": "0.3",
 "status": "calibrated by replay 2026-09-09 (engine v0.3, era 2022-06-01, 223 weeks)",
 "era_start": "2022-06-01",
 "anchor_percentiles": true,
 "level_weight": 1.0,
 "persistence": {
  "entry_days": 7,
  "exit_days": 0,
  "mode": "mean"
 },
 "agreement_only": true,
 "agreement_only_until_weeks": 150,
 "weights": {
  "central_bank": 0.6,
  "fiscal": 0.4
 },
 "general_thresholds": {
  "injection": 0.5,
  "drain": -0.5
 },
 "block_thresholds": {
  "central_bank": {
   "injection_enter": 0.11,
   "injection_exit": 0.0,
   "drain_enter": -0.5,
   "drain_exit": -0.3,
   "level_weight": 1.0,
   "evidence": {
    "injection": "frecuencia_de_era",
    "drain": "frecuencia_de_era"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  },
  "fiscal": {
   "injection_enter": 1.215,
   "injection_exit": 1.11,
   "drain_enter": 0.615,
   "drain_exit": 0.815,
   "level_weight": 1.0,
   "evidence": {
    "injection": "frecuencia_de_era",
    "drain": "frecuencia_de_era"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  }
 }
}
```
