# Replay v0.4 · CHF · era desde 2022-09-22 · 207 semanas (2022-09-23 → 2026-09-04)

## central_bank

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (Δ GI semanal, cuota de absorción mensual) | 1.00 | 207 | 1.0 / 0.5 | -0.5 / -0.5 | 0.33 / 0.42 / 0.25 | estable | 0.018 (0.8351) | 0.093 (0.4393) | None (None) | — |
| B — v0.4 base | 0.99 | 204 | 0.501 / 0.1373 | -0.8517 / -0.5859 | 0.23 / 0.53 / 0.23 | estable | -0.064 (0.3643) | -0.028 (0.7201) | None (None) | 0.466 |
| C — candidato ronda 1 | 0.73 | 151 | 0.8125 / 0.4554 | -0.6933 / -0.3828 | 0.17 / 0.39 / 0.17 | estable | 0.025 (0.7891) | -0.05 (0.5737) | None (None) | 0.377 |

- B · `fx_proxy_w` ← hist:fx_intervention_proxy_v04 · weekly · retraso de publicación 7 d · cobertura 0.986 · conciliación: ΔGI − operaciones − Confederación, semanas completas
- C · `ops_net_5d` ← hist:ops_net_daily · daily5 · retraso de publicación 35 d · cobertura 0.729 · conciliación: Bills + repos por fecha; importes publicados ~35 días tras fin de mes (reloj de publicación)

**Selección (escalera de la ronda 1): B** — sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 0.99, corte estable)

## fiscal

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (saldos de la Confederación mensuales) | 1.00 | 207 | 0.25 / 0.25 | -0.25 / -0.25 | 0.21 / 0.59 / 0.20 | estable | -0.045 (0.6092) | -0.164 (0.1359) | None (None) | — |
| B — v0.4 base | 0.75 | 155 | 0.0375 / 0.0105 | -0.0495 / -0.0282 | 0.18 / 0.40 / 0.17 | estable | -0.009 (0.9045) | 0.07 (0.5427) | None (None) | 0.374 |

- B · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 2 d · cobertura 0.749 · conciliación: MMDRC + bonos por liquidación T+2 (EFV)

**Selección (escalera de la ronda 1): A** — sin evidencia B y la variante v0.4 no cubre la era (cobertura 0.749) → se mantiene v0.3

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).