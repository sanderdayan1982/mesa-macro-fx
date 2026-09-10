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
| B — v0.4 base | 0.0 | 0 | insuficiente (0 semanas con dato) | | | | | | | |
| C — candidato ronda 1 | 0.0 | 0 | insuficiente (0 semanas con dato) | | | | | | | |

- B · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 1 d · cobertura 0.0 · conciliación: gilts + letras − APF − vencimientos − cupones, por liquidación (D2.1A/D2.2D/D1A)
- C · `exchequer_residual_w` ← hist:exchequer_residual_weekly · weekly · retraso de publicación 7 d · cobertura 0.0 · conciliación: residual del Exchequer semanal (canal de renta)

**Selección (escalera de la ronda 1): A** — sólo una variante evaluable

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).