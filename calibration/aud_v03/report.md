# AUD — engine v0.3 (era 2025-04-09, 74 semanas; ventanas ancladas a la era; persistencia 7/0 días; regla de acuerdo)


## central_bank — niveles: es_vs_range · flujos: balance_sheet_band, es_dod_level, standing_facility

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | 0.34 / 0.67 / 1.00 (0.00 / 0.67 / 0.67) | +1.00 (+1.00) / +0.09 (+0.34) | 28 / 49 / 23 % | 0.23 | 33 · 2.2 | 0.129 (0.331) · -0.51 · 1.01 |
| 0.5 | 0.09 / 0.42 / 0.75 (-0.25 / 0.42 / 0.42) | +0.75 (+0.75) / -0.14 (+0.09) | 28 / 49 / 23 % | 0.23 | 33 · 2.2 | 0.129 (0.331) · -0.51 · 1.01 |
| 0.25 | -0.04 / 0.29 / 0.62 (-0.38 / 0.29 / 0.29) | +0.62 (+0.62) / -0.24 (-0.04) | 28 / 49 / 23 % | 0.23 | 33 · 2.2 | 0.123 (0.350) · -0.51 · 1.01 |
| 0.0 | -0.17 / 0.17 / 0.50 (-0.50 / 0.17 / 0.17) | +0.50 (+0.50) / -0.35 (-0.17) | 28 / 49 / 23 % | 0.23 | 33 · 2.2 | 0.129 (0.331) · -0.51 · 1.01 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 19 % / DRAIN 26 % / cambios 46 · consecutive_7_0 → INJ 3 % / DRAIN 7 % / cambios 14 · mean_7_0 → INJ 28 % / DRAIN 23 % / cambios 33 · mean_7_7 → INJ 42 % / DRAIN 30 % / cambios 24

## fiscal — niveles: ninguno · flujos: fiscal_flow_z

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.58 / 0.07 / 0.53 (-1.02 / 0.12 / 0.57) | +0.53 (+0.34) / -0.56 (-0.37) | 22 / 54 / 24 % | 0.22 | 34 · 2.1 | -0.075 (0.573) · 0.77 · 0.58 |
| 0.5 | -0.58 / 0.07 / 0.53 (-1.02 / 0.12 / 0.57) | +0.53 (+0.34) / -0.56 (-0.37) | 22 / 54 / 24 % | 0.22 | 34 · 2.1 | -0.075 (0.573) · 0.77 · 0.58 |
| 0.25 | -0.58 / 0.07 / 0.53 (-1.02 / 0.12 / 0.57) | +0.53 (+0.34) / -0.56 (-0.37) | 22 / 54 / 24 % | 0.22 | 34 · 2.1 | -0.075 (0.573) · 0.77 · 0.58 |
| 0.0 | -0.58 / 0.07 / 0.53 (-1.02 / 0.12 / 0.57) | +0.53 (+0.34) / -0.56 (-0.37) | 22 / 54 / 24 % | 0.22 | 34 · 2.1 | -0.075 (0.573) · 0.77 · 0.58 |

Peso seleccionado: **1.0** — no level components in this block — weight irrelevant
Persistencia (peso seleccionado): none → INJ 23 % / DRAIN 22 % / cambios 43 · consecutive_7_0 → INJ 8 % / DRAIN 5 % / cambios 12 · mean_7_0 → INJ 22 % / DRAIN 24 % / cambios 34 · mean_7_7 → INJ 35 % / DRAIN 35 % / cambios 27

## Régimen general (regla de acuerdo, pesos {'central_bank': 1.0, 'fiscal': 1.0})

INYECCIÓN 12 % · NEUTRAL parcial 72 % · NEUTRAL conflicto 4 % · DRENAJE 12 % · cambios 25 · racha media 2.8 semanas

## Parche de config (regime.dual)

```json
{
 "version": "0.3",
 "status": "calibrated by replay 2026-09-09 (engine v0.3, era 2025-04-09, 74 weeks)",
 "era_start": "2025-04-09",
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
   "injection_enter": 1.0,
   "injection_exit": 1.0,
   "drain_enter": 0.085,
   "drain_exit": 0.335,
   "level_weight": 1.0,
   "evidence": {
    "injection": "provisional_era_corta",
    "drain": "provisional_era_corta"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  },
  "fiscal": {
   "injection_enter": 0.53,
   "injection_exit": 0.34,
   "drain_enter": -0.555,
   "drain_exit": -0.37,
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
