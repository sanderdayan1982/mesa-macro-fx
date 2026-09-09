# EUR — engine v0.3 (era 2022-09-14, 208 semanas; ventanas ancladas a la era; persistencia 7/0 días; regla de acuerdo)


## central_bank — niveles: excess_liquidity_level, phase, tomo_level · flujos: excess_20s_vs_stock, excess_wow_vs_stock, mlf_used

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.52 / -0.29 / 0.02 (-0.64 / -0.25 / 0.12) | +0.02 (-0.14) / -0.53 (-0.42) | 24 / 50 / 25 % | 0.24 | 65 · 3.2 | -0.158 (0.061) · -0.40 · -2.70 |
| 0.5 | -0.52 / -0.27 / 0.04 (-0.61 / -0.24 / 0.15) | +0.04 (-0.12) / -0.52 (-0.40) | 24 / 49 / 27 % | 0.24 | 64 · 3.2 | -0.152 (0.070) · -0.11 · -2.29 |
| 0.25 | -0.51 / -0.27 / 0.06 (-0.62 / -0.22 / 0.13) | +0.06 (-0.10) / -0.51 (-0.40) | 26 / 48 / 26 % | 0.26 | 62 · 3.3 | -0.145 (0.085) · 0.07 · -2.18 |
| 0.0 | -0.49 / -0.25 / 0.05 (-0.61 / -0.20 / 0.15) | +0.06 (-0.09) / -0.49 (-0.39) | 24 / 49 / 27 % | 0.24 | 62 · 3.3 | -0.143 (0.087) · 0.24 · -2.16 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 22 % / DRAIN 24 % / cambios 100 · consecutive_7_0 → INJ 12 % / DRAIN 4 % / cambios 28 · mean_7_0 → INJ 24 % / DRAIN 25 % / cambios 65 · mean_7_7 → INJ 30 % / DRAIN 38 % / cambios 46

## fiscal — niveles: auction_health, structural_deficit · flujos: impulse_4w_percentile

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.02 / 0.30 / 0.59 (-0.11 / 0.27 / 0.65) | +0.59 (+0.46) / -0.02 (+0.10) | 24 / 50 / 26 % | 0.24 | 58 · 3.5 | 0.003 (0.970) · -1.38 · -0.90 |
| 0.5 | -0.20 / 0.12 / 0.42 (-0.31 / 0.08 / 0.46) | +0.42 (+0.27) / -0.20 (-0.09) | 24 / 50 / 26 % | 0.24 | 54 · 3.8 | 0.003 (0.967) · -1.56 · -1.09 |
| 0.25 | -0.30 / 0.03 / 0.34 (-0.40 / -0.01 / 0.37) | +0.34 (+0.17) / -0.30 (-0.18) | 24 / 50 / 26 % | 0.24 | 54 · 3.8 | -0.001 (0.992) · -1.56 · -1.09 |
| 0.0 | -0.40 / -0.07 / 0.25 (-0.50 / -0.10 / 0.27) | +0.26 (+0.08) / -0.40 (-0.28) | 24 / 50 / 26 % | 0.24 | 52 · 3.9 | 0.005 (0.958) · -1.52 · -0.98 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 22 % / DRAIN 29 % / cambios 91 · consecutive_7_0 → INJ 10 % / DRAIN 15 % / cambios 32 · mean_7_0 → INJ 24 % / DRAIN 26 % / cambios 58 · mean_7_7 → INJ 33 % / DRAIN 34 % / cambios 49

## Régimen general (regla de acuerdo, pesos {'central_bank': 1.0, 'fiscal': 1.0})

INYECCIÓN 11 % · NEUTRAL parcial 74 % · NEUTRAL conflicto 5 % · DRENAJE 10 % · cambios 52 · racha media 3.9 semanas

## Parche de config (regime.dual)

```json
{
 "version": "0.3",
 "status": "calibrated by replay 2026-09-09 (engine v0.3, era 2022-09-14, 208 weeks)",
 "era_start": "2022-09-14",
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
   "injection_enter": 0.02,
   "injection_exit": -0.14,
   "drain_enter": -0.525,
   "drain_exit": -0.42,
   "level_weight": 1.0,
   "evidence": {
    "injection": "frecuencia_de_era",
    "drain": "frecuencia_de_era"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  },
  "fiscal": {
   "injection_enter": 0.59,
   "injection_exit": 0.46,
   "drain_enter": -0.02,
   "drain_exit": 0.1,
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
