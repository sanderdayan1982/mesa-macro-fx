# Replay v0.4 · CHF · era desde 2022-09-22 · 207 semanas (2022-09-23 → 2026-09-04)

## central_bank

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (Δ GI semanal, cuota de absorción mensual) | 1.00 | 207 | 1.0 / 0.5 | -0.5 / -0.5 | 0.33 / 0.42 / 0.25 | estable | 0.018 (0.8351) | 0.093 (0.4393) | None (None) | — |
| B — v0.4 base | 0.99 | 204 | 0.5948 / 0.2622 | -0.7792 / -0.4869 | 0.22 / 0.55 / 0.21 | estable | -0.014 (0.8551) | -0.005 (0.9525) | None (None) | 0.392 |
| C — candidato ronda 1 | 1.00 | 207 | 0.7997 / 0.4293 | -0.9262 / -0.4763 | 0.24 / 0.53 / 0.23 | estable | -0.004 (0.9465) | -0.042 (0.6002) | None (None) | 0.396 |

- B · `fx_proxy_w` ← hist:fx_intervention_proxy_v04 · weekly · retraso de publicación 7 d · cobertura 0.986 · conciliación: ΔGI − operaciones − Confederación, semanas completas
- C · `ops_net_5d` ← hist:ops_net_daily · daily5 · retraso de publicación 35 d · cobertura 1.0 · conciliación: Bills + repos por fecha; importes publicados ~35 días tras fin de mes (reloj de publicación)

**Selección (escalera de la ronda 1): B** — sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 0.99, corte estable)

## fiscal

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (saldos de la Confederación mensuales) | 1.00 | 207 | 0.25 / 0.25 | -0.25 / -0.25 | 0.21 / 0.59 / 0.20 | estable | -0.045 (0.6092) | -0.164 (0.1359) | None (None) | — |
| B — v0.4 base | 1.00 | 207 | 0.034 / 0.0092 | -0.0701 / -0.0392 | 0.25 / 0.54 / 0.22 | estable | 0.077 (0.3308) | 0.182 (0.1079) | None (None) | 0.329 |

- B · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 2 d · cobertura 1.0 · conciliación: MMDRC + bonos por liquidación T+2 (EFV)

**Selección (escalera de la ronda 1): B** — sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 1.00, corte estable) · aviso: ρ a 12 s con signo no MMT (0.182, no significativo)

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).