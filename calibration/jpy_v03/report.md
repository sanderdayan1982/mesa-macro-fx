# JPY — engine v0.3 (era 2024-07-31, 102 semanas; ventanas ancladas a la era; persistencia 7/0 días; regla de acuerdo)


## central_bank — niveles: excess_to_required · flujos: balance_sheet_band, cab_20d_level, cab_dod_level

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | 0.50 / 0.50 / 0.50 (0.50 / 0.50 / 0.50) | +0.75 (+0.75) / +0.25 (+0.25) | 14 / 68 / 19 % | 0.14 | 30 · 3.3 | 0.068 (0.559) · -1.49 · -0.36 |
| 0.5 | 0.31 / 0.31 / 0.31 (0.31 / 0.31 / 0.31) | +0.56 (+0.56) / +0.06 (+0.06) | 14 / 68 / 19 % | 0.14 | 30 · 3.3 | 0.068 (0.559) · -1.49 · -0.36 |
| 0.25 | 0.22 / 0.22 / 0.22 (0.22 / 0.22 / 0.22) | +0.47 (+0.47) / -0.03 (-0.03) | 14 / 68 / 19 % | 0.14 | 30 · 3.3 | 0.068 (0.559) · -1.49 · -0.36 |
| 0.0 | 0.12 / 0.12 / 0.12 (0.12 / 0.12 / 0.12) | +0.37 (+0.37) / -0.13 (-0.13) | 14 / 68 / 19 % | 0.14 | 30 · 3.3 | 0.068 (0.559) · -1.49 · -0.36 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 10 % / DRAIN 16 % / cambios 33 · consecutive_7_0 → INJ 2 % / DRAIN 7 % / cambios 14 · mean_7_0 → INJ 14 % / DRAIN 19 % / cambios 30 · mean_7_7 → INJ 18 % / DRAIN 28 % / cambios 29
- B stress 4s: ρ 0.012 (p 0.905, boot 0.914, n 98) · Δ medio DRAIN -0.01 / NEUTRAL 0.00 / INJ -0.01 · t DRAIN−N -0.25 · t INJ−N -0.23
- B stress 12s: ρ 0.068 (p 0.525, boot 0.559, n 90) · Δ medio DRAIN -0.03 / NEUTRAL 0.01 / INJ -0.01 · t DRAIN−N -1.49 · t INJ−N -0.36
- B stress_alt 4s: ρ -0.332 (p 0.011, boot 0.032, n 58) · Δ medio DRAIN 0.54 / NEUTRAL -0.01 / INJ -0.04 · t DRAIN−N 2.66 · t INJ−N -0.22
- B stress_alt 12s: ρ -0.097 (p 0.504, boot 0.579, n 50) · Δ medio DRAIN 0.56 / NEUTRAL 0.20 / INJ 0.28 · t DRAIN−N 1.11 · t INJ−N 0.49

## fiscal — niveles: ninguno · flujos: fiscal_flow_z

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.31 / 0.01 / 0.24 (-0.33 / 0.08 / 0.30) | +0.24 (+0.13) / -0.32 (-0.14) | 24 / 52 / 24 % | 0.23 | 36 · 2.8 | -0.009 (0.927) · 2.44 · 2.28 |
| 0.5 | -0.31 / 0.01 / 0.24 (-0.33 / 0.08 / 0.30) | +0.24 (+0.13) / -0.32 (-0.14) | 24 / 52 / 24 % | 0.23 | 36 · 2.8 | -0.009 (0.927) · 2.44 · 2.28 |
| 0.25 | -0.31 / 0.01 / 0.24 (-0.33 / 0.08 / 0.30) | +0.24 (+0.13) / -0.32 (-0.14) | 24 / 52 / 24 % | 0.23 | 36 · 2.8 | -0.009 (0.927) · 2.44 · 2.28 |
| 0.0 | -0.31 / 0.01 / 0.24 (-0.33 / 0.08 / 0.30) | +0.24 (+0.13) / -0.32 (-0.14) | 24 / 52 / 24 % | 0.23 | 36 · 2.8 | -0.009 (0.927) · 2.44 · 2.28 |

Peso seleccionado: **1.0** — no level components in this block — weight irrelevant
Persistencia (peso seleccionado): none → INJ 24 % / DRAIN 22 % / cambios 53 · consecutive_7_0 → INJ 7 % / DRAIN 5 % / cambios 13 · mean_7_0 → INJ 24 % / DRAIN 24 % / cambios 36 · mean_7_7 → INJ 28 % / DRAIN 34 % / cambios 30
- B stress 4s: ρ -0.040 (p 0.698, boot 0.714, n 98) · Δ medio DRAIN 0.04 / NEUTRAL -0.02 / INJ 0.01 · t DRAIN−N 2.11 · t INJ−N 1.39
- B stress 12s: ρ -0.009 (p 0.931, boot 0.927, n 90) · Δ medio DRAIN 0.06 / NEUTRAL -0.03 / INJ 0.02 · t DRAIN−N 2.44 · t INJ−N 2.28
- B stress_alt 4s: ρ 0.073 (p 0.584, boot 0.650, n 58) · Δ medio DRAIN -0.14 / NEUTRAL 0.20 / INJ 0.11 · t DRAIN−N -2.06 · t INJ−N -0.53
- B stress_alt 12s: ρ 0.115 (p 0.426, boot 0.486, n 50) · Δ medio DRAIN 0.06 / NEUTRAL 0.37 / INJ 0.29 · t DRAIN−N -1.44 · t INJ−N -0.37

## Régimen general (regla de acuerdo, pesos {'central_bank': 1.0, 'fiscal': 1.0})

INYECCIÓN 3 % · NEUTRAL parcial 84 % · NEUTRAL conflicto 9 % · DRENAJE 4 % · cambios 22 · racha media 4.4 semanas

## Parche de config (regime.dual)

```json
{
 "version": "0.3",
 "status": "calibrated by replay 2026-09-09 (engine v0.3, era 2024-07-31, 102 weeks)",
 "era_start": "2024-07-31",
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
   "injection_enter": 0.75,
   "injection_exit": 0.75,
   "drain_enter": 0.25,
   "drain_exit": 0.25,
   "level_weight": 1.0,
   "evidence": {
    "injection": "provisional_era_corta",
    "drain": "provisional_era_corta"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  },
  "fiscal": {
   "injection_enter": 0.24,
   "injection_exit": 0.13,
   "drain_enter": -0.32,
   "drain_exit": -0.14,
   "level_weight": 1.0,
   "evidence": {
    "injection": "provisional_era_corta",
    "drain": "provisional_era_corta"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  }
 }
}
```
