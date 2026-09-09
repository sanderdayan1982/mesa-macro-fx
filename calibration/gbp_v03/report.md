# GBP — engine v0.3 (era 2022-11-01, 201 semanas; ventanas ancladas a la era; persistencia 7/0 días; regla de acuerdo)


## central_bank — niveles: qt_pace_level, reserves_vs_pmrr · flujos: balance_sheet_band

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.17 / 0.34 / 0.67 (-0.17 / 0.50 / 0.83) | +0.67 (+0.50) / -0.17 (+0.17) | 33 / 34 / 32 % | 0.32 | 48 · 4.1 | -0.028 (0.839) · -1.30 · -2.59 |
| 0.5 | -0.09 / 0.25 / 0.58 (-0.42 / 0.25 / 0.75) | +0.58 (+0.58) / -0.09 (-0.08) | 21 / 51 / 28 % | 0.21 | 74 · 2.7 | 0.048 (0.650) · -1.82 · -1.11 |
| 0.25 | -0.21 / 0.12 / 0.46 (-0.54 / 0.12 / 0.71) | +0.46 (+0.29) / -0.21 (-0.04) | 25 / 50 / 25 % | 0.25 | 72 · 2.8 | 0.075 (0.500) · -2.90 · -2.29 |
| 0.0 | -0.34 / 0.00 / 0.34 (-0.67 / 0.00 / 0.67) | +0.67 (+0.34) / -0.34 (-0.34) | 18 / 58 / 24 % | 0.18 | 60 · 3.3 | 0.122 (0.270) · -2.57 · -2.12 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 22 % / DRAIN 35 % / cambios 119 · consecutive_7_0 → INJ 11 % / DRAIN 18 % / cambios 44 · mean_7_0 → INJ 33 % / DRAIN 32 % / cambios 48 · mean_7_7 → INJ 39 % / DRAIN 39 % / cambios 29

## fiscal — niveles: ninguno · flujos: net_spending_band_x_z

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.50 / 0.00 / 0.00 (0.00 / 0.00 / 0.00) | +0.50 (+0.50) / -0.50 (-0.50) | 10 / 69 / 21 % | 0.10 (un lado) | 20 · 9.6 | -0.258 (0.057) · 4.35 · -0.38 |
| 0.5 | -0.50 / 0.00 / 0.00 (0.00 / 0.00 / 0.00) | +0.50 (+0.50) / -0.50 (-0.50) | 10 / 69 / 21 % | 0.10 (un lado) | 20 · 9.6 | -0.258 (0.057) · 4.35 · -0.38 |
| 0.25 | -0.50 / 0.00 / 0.00 (0.00 / 0.00 / 0.00) | +0.50 (+0.50) / -0.50 (-0.50) | 10 / 69 / 21 % | 0.10 (un lado) | 20 · 9.6 | -0.258 (0.057) · 4.35 · -0.38 |
| 0.0 | -0.50 / 0.00 / 0.00 (0.00 / 0.00 / 0.00) | +0.50 (+0.50) / -0.50 (-0.50) | 10 / 69 / 21 % | 0.10 (un lado) | 20 · 9.6 | -0.258 (0.057) · 4.35 · -0.38 |

Peso seleccionado: **1.0** — no level components in this block — weight irrelevant
Persistencia (peso seleccionado): none → INJ 8 % / DRAIN 19 % / cambios 18 · consecutive_7_0 → INJ 8 % / DRAIN 16 % / cambios 18 · mean_7_0 → INJ 10 % / DRAIN 21 % / cambios 20 · mean_7_7 → INJ 11 % / DRAIN 24 % / cambios 18

## Régimen general (regla de acuerdo, pesos {'central_bank': 1.0, 'fiscal': 1.0})

INYECCIÓN 4 % · NEUTRAL parcial 75 % · NEUTRAL conflicto 12 % · DRENAJE 9 % · cambios 32 · racha media 6.1 semanas

## Parche de config (regime.dual)

```json
{
 "version": "0.3",
 "status": "calibrated by replay 2026-09-09 (engine v0.3, era 2022-11-01, 201 weeks)",
 "era_start": "2022-11-01",
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
   "injection_enter": 0.665,
   "injection_exit": 0.5,
   "drain_enter": -0.165,
   "drain_exit": 0.165,
   "level_weight": 1.0,
   "evidence": {
    "injection": "frecuencia_de_era",
    "drain": "frecuencia_de_era"
   },
   "rule": "era p80/p20 (exit p67/p33) of the 7-day mean score, nearest attainable, exit after 0 days inside"
  },
  "fiscal": {
   "injection_enter": 0.5,
   "injection_exit": 0.5,
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
