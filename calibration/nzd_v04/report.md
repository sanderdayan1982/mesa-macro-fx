# Replay v0.4 · NZD · era desde 2022-07-01 · 210 semanas (2022-07-01 → 2026-09-03)

## central_bank

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (settlement cash Δ) | 1.00 | 210 | 0.375 / 0.25 | -0.375 / -0.25 | 0.27 / 0.44 / 0.29 | estable | 0.017 (0.8486) | -0.06 (0.4803) | -0.034 (0.6932) | — |
| B — v0.4 base | 0.1 | 21 | insuficiente (21 semanas con dato) | | | | | | | |

- B · `omo_net_5d` ← hist:omo_net_daily · daily5 · retraso de publicación 1 d · cobertura 0.1 · conciliación: OMO por operación (D3); settlement cash = conciliación

**Selección (escalera de la ronda 1): A** — sólo una variante evaluable

## fiscal

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (R3 mensual + proxy) | 1.00 | 210 | 0.25 / 0.25 | -0.5 / -0.5 | 0.24 / 0.52 / 0.24 | estable | 0.073 (0.3878) | -0.069 (0.5102) | -0.044 (0.6662) | — |
| B — v0.4 base | 0.071 | 15 | insuficiente (15 semanas con dato) | | | | | | | |
| C — candidato ronda 1 | 0.63 | 133 | 4.2415 / 1.5534 | -5.672 / -4.0648 | 0.14 / 0.36 / 0.13 | estable | 0.075 (0.3963) | -0.056 (0.4983) | -0.043 (0.6597) | 0.406 |

- B · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 1 d · cobertura 0.071 · conciliación: tenders por liquidación − letras vencidas − cupones al mercado (NZDM, D3 LSAP)
- C · `residual_5d` ← hist:residual_flow_daily · daily5 · retraso de publicación 1 d · cobertura 0.633 · conciliación: proxy residual diario (conciliado D10 −7 mm)

**Selección (escalera de la ronda 1): A** — sin evidencia B y la variante v0.4 no cubre la era (cobertura None) → se mantiene v0.3

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).