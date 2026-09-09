# CHF — engine v0.3 (era 2022-09-22, 207 semanas; ventanas ancladas a la era; persistencia 7/0 días; regla de acuerdo)


## central_bank — niveles: absorption_share_level · flujos: fx_intervention_suspect, sight_deposits_13w_band, snb_supplying

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | -0.50 / 0.00 / 1.00 (-0.50 / 0.00 / 1.00) | +1.00 (+0.50) / -0.50 (-0.50) | 33 / 42 / 25 % | 0.25 | 33 · 6.1 | 0.093 (0.439) · -2.30 · -2.54 |
| 0.5 | -0.25 / 0.25 / 1.00 (-0.25 / 0.00 / 1.00) | +1.00 (+0.75) / -0.25 (+0.00) | 35 / 36 / 29 % | 0.29 | 33 · 6.1 | 0.105 (0.383) · -0.07 · 2.22 |
| 0.25 | -0.12 / 0.38 / 1.00 (-0.12 / 0.00 / 1.00) | +1.00 (+0.88) / -0.12 (+0.00) | 35 / 36 / 29 % | 0.29 | 33 · 6.1 | 0.109 (0.362) · -0.07 · 2.22 |
| 0.0 | 0.00 / 0.50 / 1.00 (0.00 / 0.00 / 1.00) | +1.25 (+1.00) / -0.50 (+0.00) | 6 / 72 / 22 % | 0.06 (un lado) | 7 · 25.9 | 0.144 (0.219) · 0.16 · 7.33 |

Peso seleccionado: **1.0** — no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight
Persistencia (peso seleccionado): none → INJ 35 % / DRAIN 25 % / cambios 39 · consecutive_7_0 → INJ 29 % / DRAIN 22 % / cambios 32 · mean_7_0 → INJ 33 % / DRAIN 25 % / cambios 33 · mean_7_7 → INJ 42 % / DRAIN 28 % / cambios 23

## fiscal — niveles: ninguno · flujos: confed_balances_mom_band

| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |
|---|---|---|---|---|---|---|
| 1.0 ★ | 0.00 / 0.00 / 0.25 (0.00 / 0.00 / 0.00) | +0.25 (+0.25) / -0.25 (-0.25) | 21 / 59 / 20 % | 0.20 | 27 · 7.4 | -0.164 (0.136) · 0.09 · -2.54 |
| 0.5 | 0.00 / 0.00 / 0.25 (0.00 / 0.00 / 0.00) | +0.25 (+0.25) / -0.25 (-0.25) | 21 / 59 / 20 % | 0.20 | 27 · 7.4 | -0.164 (0.136) · 0.09 · -2.54 |
| 0.25 | 0.00 / 0.00 / 0.25 (0.00 / 0.00 / 0.00) | +0.25 (+0.25) / -0.25 (-0.25) | 21 / 59 / 20 % | 0.20 | 27 · 7.4 | -0.164 (0.136) · 0.09 · -2.54 |
| 0.0 | 0.00 / 0.00 / 0.25 (0.00 / 0.00 / 0.00) | +0.25 (+0.25) / -0.25 (-0.25) | 21 / 59 / 20 % | 0.20 | 27 · 7.4 | -0.164 (0.136) · 0.09 · -2.54 |

Peso seleccionado: **1.0** — no level components in this block — weight irrelevant
Persistencia (peso seleccionado): none → INJ 19 % / DRAIN 18 % / cambios 25 · consecutive_7_0 → INJ 16 % / DRAIN 16 % / cambios 25 · mean_7_0 → INJ 21 % / DRAIN 20 % / cambios 27 · mean_7_7 → INJ 25 % / DRAIN 23 % / cambios 25

## Régimen general (regla de acuerdo, pesos {'central_bank': 1.0, 'fiscal': 1.0})

INYECCIÓN 2 % · NEUTRAL parcial 80 % · NEUTRAL conflicto 16 % · DRENAJE 1 % · cambios 24 · racha media 8.3 semanas

## Parche de config (regime.dual)

```json
{
 "version": "0.3",
 "status": "calibrated by replay 2026-09-09 (engine v0.3, era 2022-09-22, 207 weeks)",
 "era_start": "2022-09-22",
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
   "injection_exit": 0.5,
   "drain_enter": -0.5,
   "drain_exit": -0.5,
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
   "drain_enter": -0.25,
   "drain_exit": -0.25,
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
