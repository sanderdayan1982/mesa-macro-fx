# CAD — engine v0.3 (era 2020-03-23, 337 semanas; ventanas ancladas a la era; persistencia 7/0 días; regla de acuerdo)


## central_bank — niveles: reserves_vs_range · flujos: emergency_lending, net_liquidity_band, reserves_wow

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.55 / 0.00 / 0.37 (-1.00 / -0.03 / 0.90) | +0.38 (+0.05) / -0.55 (-0.33) | 25 / 52 / 23 % | 0.23 | 143 · 2.3 | -0.019 (0.784) · -0.67 · -1.80 |
| 0.5 | -0.56 / 0.00 / 0.38 (-1.03 / -0.04 / 0.90) | +0.38 (+0.05) / -0.56 (-0.33) | 25 / 52 / 23 % | 0.23 | 140 · 2.4 | -0.020 (0.769) · -0.41 · -1.78 |
| 0.25 | -0.57 / -0.01 / 0.40 (-1.03 / -0.05 / 0.92) | +0.40 (+0.04) / -0.57 (-0.33) | 25 / 52 / 23 % | 0.23 | 141 · 2.4 | -0.022 (0.746) · -0.49 · -1.81 |
| 0.0 | -0.57 / -0.01 / 0.40 (-1.03 / -0.05 / 0.90) | +0.40 (+0.03) / -0.57 (-0.33) | 24 / 53 / 23 % | 0.23 | 142 · 2.4 | -0.019 (0.788) · -0.47 · -1.74 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 23 % / DRAIN 24 % / cambios 183 · consecutive_7_0 → INJ 4 % / DRAIN 5 % / cambios 24 · mean_7_0 → INJ 25 % / DRAIN 23 % / cambios 143 · mean_7_7 → INJ 39 % / DRAIN 33 % / cambios 101

## fiscal — niveles: ninguno · flujos: fiscal_flow_z

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.66 / 0.01 / 0.55 (-0.59 / 0.03 / 0.62) | +0.55 (+0.28) / -0.67 (-0.27) | 25 / 51 / 24 % | 0.24 | 108 · 3.1 | 0.107 (0.165) · 0.46 · 3.44 |
| 0.5 | -0.66 / 0.01 / 0.55 (-0.59 / 0.03 / 0.62) | +0.55 (+0.28) / -0.67 (-0.27) | 25 / 51 / 24 % | 0.24 | 108 · 3.1 | 0.107 (0.165) · 0.46 · 3.44 |
| 0.25 | -0.66 / 0.01 / 0.55 (-0.59 / 0.03 / 0.62) | +0.55 (+0.28) / -0.67 (-0.27) | 25 / 51 / 24 % | 0.24 | 108 · 3.1 | 0.107 (0.165) · 0.46 · 3.44 |
| 0.0 | -0.66 / 0.01 / 0.55 (-0.59 / 0.03 / 0.62) | +0.55 (+0.28) / -0.67 (-0.27) | 25 / 51 / 24 % | 0.24 | 108 · 3.1 | 0.107 (0.165) · 0.46 · 3.44 |

Peso seleccionado: **1.0** — no level components in this block — weight irrelevant
Persistencia (peso seleccionado): none → INJ 23 % / DRAIN 23 % / cambios 175 · consecutive_7_0 → INJ 8 % / DRAIN 6 % / cambios 44 · mean_7_0 → INJ 25 % / DRAIN 24 % / cambios 108 · mean_7_7 → INJ 34 % / DRAIN 32 % / cambios 84

## Régimen general (regla de acuerdo, pesos {'central_bank': 1.0, 'fiscal': 1.0})

INYECCIÓN 8 % · NEUTRAL parcial 80 % · NEUTRAL conflicto 5 % · DRENAJE 6 % · cambios 90 · racha media 3.7 semanas

## Parche de config (regime.dual)

```json
{
 "version": "0.3",
 "status": "calibrated by replay 2026-09-09 (engine v0.3, era 2020-03-23, 337 weeks)",
 "era_start": "2020-03-23",
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
   "injection_enter": 0.375,
   "injection_exit": 0.05,
   "drain_enter": -0.55,
   "drain_exit": -0.325,
   "level_weight": 1.0,
   "evidence": {
    "injection": "frecuencia_de_era",
    "drain": "frecuencia_de_era"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  },
  "fiscal": {
   "injection_enter": 0.55,
   "injection_exit": 0.275,
   "drain_enter": -0.67,
   "drain_exit": -0.265,
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
