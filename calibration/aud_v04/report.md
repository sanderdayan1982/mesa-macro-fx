# Replay v0.4 · AUD · era desde 2025-04-09 · 74 semanas (2025-04-09 → 2026-09-02)

## central_bank

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (Δ ES diaria/20d) | 1.00 | 74 | 1.0 / 1.0 | 0.085 / 0.335 | 0.28 / 0.49 / 0.23 | estable | 0.047 (0.6122) | 0.129 (0.3308) | None (None) | — |
| B — v0.4 base | 1.00 | 74 | 0.466 / 0.2928 | -0.4831 / -0.2075 | 0.23 / 0.54 / 0.23 | estable | -0.055 (0.6042) | 0.021 (0.8876) | None (None) | 0.486 |

- **comprobaciones**: ONE_SIDED: el corte de drenaje no cruza el cero (la serie no cambia de signo en la era; el 'régimen' opuesto sería sólo menos drenaje/inyección)
- B · `omo_net_5d` ← hist:omo_net_daily · daily5 · retraso de publicación 1 d · cobertura 1.0 · conciliación: OMO por operación; stock = A3 AORROMO ±0,1 %

**Selección (escalera de la ronda 1): B** — sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 1.00, corte estable)

## fiscal

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (−Δ depósitos del gobierno semanal) | 1.00 | 74 | 0.53 / 0.34 | -0.555 / -0.37 | 0.22 / 0.54 / 0.24 | estable | -0.097 (0.4203) | -0.075 (0.5732) | None (None) | — |
| B — v0.4 base | 0.99 | 73 | 2.7248 / 1.6897 | -2.8347 / -1.8796 | 0.22 / 0.54 / 0.23 | estable | -0.1 (0.4178) | -0.077 (0.5842) | None (None) | 0.959 |
| C — candidato ronda 1 | 1.00 | 74 | 0.2743 / -0.0099 | -1.3565 / -0.9077 | 0.20 / 0.55 / 0.24 | estable | -0.219 (0.091) | -0.084 (0.5602) | None (None) | 0.486 |

- B · `govt_delta` ← scores:govt_account · dweekly · retraso de publicación 0 d · cobertura 0.986 · conciliación: depósitos del gobierno semanales (A1) — identidad
- C · `net_issuance_v2_5d` ← hist:net_issuance_private_v2_daily · daily5 · retraso de publicación 1 d · cobertura 1.0 · conciliación: v2: tenders AOFM por Date Settled (caja) − notas/indexados − recompras + reembolsos y cupones de TB NETOS de la cartera del RBA (A3.1)

**Selección (escalera de la ronda 1): B** — sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 0.99, corte estable)

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).