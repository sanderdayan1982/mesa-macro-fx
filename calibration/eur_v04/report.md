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
| B — v0.4 base | 0.74 | 155 | -0.3904 / -0.5084 | -0.9574 / -0.8086 | 0.17 / 0.41 / 0.17 | provisional | -0.095 (0.2679) | -0.149 (0.1344) | -0.149 (0.1344) | 0.432 |

- B · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 1 d · cobertura 0.745 · conciliación: DE+FR+ES+IT+UE(+ESM) por liquidación; ES/IT sólo desde 2022 (cobertura parcial antes)
- **comprobaciones**: ONE_SIDED: el corte de inyección no cruza el cero (la serie no cambia de signo en la era; el 'régimen' opuesto sería sólo menos drenaje/inyección)

**Selección (escalera de la ronda 1): A** — sin evidencia B y la variante v0.4 no cubre la era (cobertura 0.745) → se mantiene v0.3

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).