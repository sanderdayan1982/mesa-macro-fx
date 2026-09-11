# Replay v0.4 · GBP · era desde 2022-11-01 · 201 semanas (2022-11-02 → 2026-09-02)

## central_bank

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (Δ reservas semanal, Δ13s, dependencia de repos) | 1.00 | 201 | 0.665 / 0.5 | -0.165 / 0.165 | 0.33 / 0.34 / 0.32 | provisional | 0.127 (0.2029) | -0.028 (0.8386) | 0.269 (0.1544) | — |
| B — v0.4 base | 0.0 | 0 | insuficiente (0 semanas con dato) | | | | | | | |

- B · `repo_net_5d` ← hist:repo_net_daily · daily5 · retraso de publicación 1 d · cobertura 0.0 · conciliación: STR/ILTR/CTRF por operación; stock STR = IADB exacto
- B · `apf_sales_5d` ← hist:apf_sales_daily · daily5 · retraso de publicación 1 d · cobertura 0.0 · conciliación: ventas APF por fecha (drenan)

**Selección (escalera de la ronda 1): A** — sólo una variante evaluable

## fiscal

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (banda CGNCR mensual) | 1.00 | 201 | 0.5 / 0.5 | -0.5 / -0.5 | 0.10 / 0.69 / 0.21 | estable | -0.166 (0.1374) | -0.258 (0.0565) | -0.333 (0.076) | — |
| B — v0.4 base | 0.77 | 154 | 0.1552 / 0.0694 | -0.1525 / -0.0749 | 0.19 / 0.38 / 0.19 | estable | -0.228 (0.091) | -0.034 (0.8466) | -0.155 (0.6517) | 0.383 |
| C — candidato ronda 1 | 1.00 | 201 | 0.3659 / 0.1821 | -0.3895 / -0.1815 | 0.24 / 0.54 / 0.22 | estable | 0.069 (0.3988) | 0.047 (0.5377) | 0.068 (0.5792) | 0.388 |

- B · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 1 d · cobertura 0.766 · conciliación: gilts + letras − APF − vencimientos − cupones, por liquidación (D2.1A/D2.2D/D1A)
- C · `exchequer_residual_w` ← hist:exchequer_residual_weekly · weekly · retraso de publicación 7 d · cobertura 1.0 · conciliación: residual del Exchequer semanal (canal de renta)

**Selección (escalera de la ronda 1): A** — sin evidencia B y la variante v0.4 no cubre la era (cobertura 0.766) → se mantiene v0.3

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).