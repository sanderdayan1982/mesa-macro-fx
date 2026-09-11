# Replay v0.4 · EUR · era desde 2022-09-14 · 208 semanas (2022-09-16 → 2026-09-04)

## central_bank
_Δ cartera WFS semanal sin histórico archivado (monpol_wow) → empate 3-3 sin resolver aquí_

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (exceso de liquidez diario) | 1.00 | 208 | 0.02 / -0.14 | -0.525 / -0.42 | 0.24 / 0.51 / 0.25 | estable | -0.311 (0.0005) | -0.158 (0.061) | -0.158 (0.061) | — |


**Selección (escalera de la ronda 1): A** — sólo una variante evaluable · Δ cartera WFS semanal sin histórico archivado (monpol_wow) → empate 3-3 sin resolver aquí

## fiscal

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (déficit estructural GFS.Q + −ΔL050100) | 1.00 | 208 | 0.59 / 0.46 | -0.02 / 0.1 | 0.24 / 0.51 / 0.26 | estable | -0.048 (0.5492) | 0.003 (0.9695) | 0.003 (0.9695) | — |
| B — v0.4 base | 1.00 | 208 | 0.1427 / -0.0359 | -0.5159 / -0.3496 | 0.26 / 0.51 / 0.23 | estable | -0.01 (0.8926) | -0.071 (0.3428) | -0.071 (0.3428) | 0.375 |

- B · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 1 d · cobertura 1.0 · conciliación: DE+FR+ES+IT+UE(+ESM) por liquidación + reembolsos y cupones BRUTOS: DE 1999→, EU 2020→, FR 2019→ (recompras por mes), IT 2020→, ES 2025→ (sólo reembolsos, sin cupones); IT aplicado desde el primer registro de emisión del archivo MEF (2022 en el runner) para que el flujo sea de dos lados desde la misma fecha; ESM sólo un lado; ES/IT emisión sólo desde 2022

**Selección (escalera de la ronda 1): B** — sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 1.00, corte estable)

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).