# NZD — engine v0.3 (era 2022-07-01, 210 semanas; ventanas ancladas a la era; persistencia 7/0 días; regla de acuerdo)


## central_bank — niveles: omo_reliance_level, settlement_cash_level · flujos: orrf_used, settlement_cash_20d, settlement_cash_wow

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.38 / 0.00 / 0.38 (-0.50 / 0.00 / 0.75) | +0.38 (+0.25) / -0.38 (-0.25) | 27 / 44 / 29 % | 0.27 | 93 · 2.2 | -0.060 (0.480) · -1.73 · -1.77 |
| 0.5 | -0.25 / 0.12 / 0.50 (-0.38 / 0.12 / 0.88) | +0.50 (+0.38) / -0.25 (-0.13) | 27 / 44 / 29 % | 0.27 | 93 · 2.2 | -0.061 (0.475) · -1.73 · -1.77 |
| 0.25 | -0.18 / 0.19 / 0.56 (-0.31 / 0.19 / 0.94) | +0.56 (+0.44) / -0.18 (-0.06) | 27 / 44 / 29 % | 0.27 | 93 · 2.2 | -0.060 (0.480) · -1.73 · -1.77 |
| 0.0 | -0.12 / 0.25 / 0.62 (-0.25 / 0.25 / 1.00) | +0.62 (+0.50) / -0.12 (+0.00) | 27 / 44 / 29 % | 0.27 | 93 · 2.2 | -0.060 (0.480) · -1.73 · -1.77 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 32 % / DRAIN 35 % / cambios 116 · consecutive_7_0 → INJ 12 % / DRAIN 15 % / cambios 38 · mean_7_0 → INJ 27 % / DRAIN 29 % / cambios 93 · mean_7_7 → INJ 38 % / DRAIN 40 % / cambios 64
- B stress 4s: ρ 0.017 (p 0.813, boot 0.849, n 206) · Δ medio DRAIN -3.35 / NEUTRAL 2.98 / INJ -1.00 · t DRAIN−N -2.32 · t INJ−N -1.20
- B stress 12s: ρ -0.060 (p 0.401, boot 0.480, n 198) · Δ medio DRAIN -1.76 / NEUTRAL 2.69 / INJ -1.49 · t DRAIN−N -1.73 · t INJ−N -1.77
- B stress_alt 4s: ρ 0.073 (p 0.300, boot 0.390, n 206) · Δ medio DRAIN -0.08 / NEUTRAL 1.09 / INJ -0.58 · t DRAIN−N -0.66 · t INJ−N -0.92
- B stress_alt 12s: ρ 0.040 (p 0.579, boot 0.634, n 198) · Δ medio DRAIN 0.51 / NEUTRAL 1.62 / INJ 0.67 · t DRAIN−N -0.59 · t INJ−N -0.46

## fiscal — niveles: ninguno · flujos: govt_cash_influence_band

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.50 / 0.00 / 0.25 (-0.50 / 0.00 / 0.50) | +0.25 (+0.25) / -0.50 (-0.50) | 24 / 52 / 24 % | 0.24 | 52 · 4.0 | -0.069 (0.510) · -2.04 · -1.42 |
| 0.5 | -0.50 / 0.00 / 0.25 (-0.50 / 0.00 / 0.50) | +0.25 (+0.25) / -0.50 (-0.50) | 24 / 52 / 24 % | 0.24 | 52 · 4.0 | -0.069 (0.510) · -2.04 · -1.42 |
| 0.25 | -0.50 / 0.00 / 0.25 (-0.50 / 0.00 / 0.50) | +0.25 (+0.25) / -0.50 (-0.50) | 24 / 52 / 24 % | 0.24 | 52 · 4.0 | -0.069 (0.510) · -2.04 · -1.42 |
| 0.0 | -0.50 / 0.00 / 0.25 (-0.50 / 0.00 / 0.50) | +0.25 (+0.25) / -0.50 (-0.50) | 24 / 52 / 24 % | 0.24 | 52 · 4.0 | -0.069 (0.510) · -2.04 · -1.42 |

Peso seleccionado: **1.0** — no level components in this block — weight irrelevant
Persistencia (peso seleccionado): none → INJ 23 % / DRAIN 31 % / cambios 51 · consecutive_7_0 → INJ 19 % / DRAIN 24 % / cambios 38 · mean_7_0 → INJ 24 % / DRAIN 24 % / cambios 52 · mean_7_7 → INJ 30 % / DRAIN 30 % / cambios 41
- B stress 4s: ρ 0.073 (p 0.297, boot 0.388, n 206) · Δ medio DRAIN -2.41 / NEUTRAL 1.02 / INJ 0.45 · t DRAIN−N -1.29 · t INJ−N -0.17
- B stress 12s: ρ -0.069 (p 0.333, boot 0.510, n 198) · Δ medio DRAIN -3.06 / NEUTRAL 2.35 / INJ -1.21 · t DRAIN−N -2.04 · t INJ−N -1.42
- B stress_alt 4s: ρ 0.021 (p 0.766, boot 0.820, n 206) · Δ medio DRAIN 0.96 / NEUTRAL -0.44 / INJ 1.16 · t DRAIN−N 0.79 · t INJ−N 0.85
- B stress_alt 12s: ρ 0.011 (p 0.879, boot 0.912, n 198) · Δ medio DRAIN 1.92 / NEUTRAL 0.36 / INJ 1.58 · t DRAIN−N 0.82 · t INJ−N 0.56

## Régimen general (regla de acuerdo, pesos {'central_bank': 1.0, 'fiscal': 1.0})

INYECCIÓN 7 % · NEUTRAL parcial 73 % · NEUTRAL conflicto 14 % · DRENAJE 5 % · cambios 61 · racha media 3.4 semanas

## Parche de config (regime.dual)

```json
{
 "version": "0.3",
 "status": "calibrated by replay 2026-09-09 (engine v0.3, era 2022-07-01, 210 weeks)",
 "era_start": "2022-07-01",
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
   "injection_exit": 0.25,
   "drain_enter": -0.375,
   "drain_exit": -0.25,
   "level_weight": 1.0,
   "evidence": {
    "injection": "frecuencia_de_era",
    "drain": "frecuencia_de_era"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  },
  "fiscal": {
   "injection_enter": 0.25,
   "injection_exit": 0.25,
   "drain_enter": -0.5,
   "drain_exit": -0.5,
   "level_weight": 1.0,
   "evidence": {
    "injection": "banda_por_diseño",
    "drain": "banda_por_diseño"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  }
 }
}
```
