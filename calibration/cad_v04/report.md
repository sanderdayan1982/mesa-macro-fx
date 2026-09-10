# Replay v0.4 · CAD · era desde 2020-03-23 · 337 semanas (2020-03-25 → 2026-09-02)

## central_bank
_saldos de liquidación diarios sin histórico en fixtures (tabla HTML de 6 días) → fuera del replay hasta que el archivo diario madure_

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (Δ reserves semanal, Δ13s, dependencia de repos) | 1.00 | 337 | 0.375 / 0.05 | -0.55 / -0.325 | 0.25 / 0.52 / 0.23 | estable | -0.095 (0.1) | -0.019 (0.7836) | -0.233 (0.028) | — |
| B — v0.4 base | 0.0 | 0 | insuficiente (0 semanas con dato) | | | | | | | |

- B · `term_repo_net_5d` ← hist:term_repo_net_daily · daily5 · retraso de publicación 1 d · cobertura 0.006 · conciliación: stock = B2 V44201362 ±1 %
- B · `overnight_ops_net_5d` ← hist:overnight_ops_net_daily · daily5 · retraso de publicación 1 d · cobertura 0.383 · conciliación: OR/ORR por operación

**Selección (escalera de la ronda 1): A** — sólo una variante evaluable · saldos de liquidación diarios sin histórico en fixtures (tabla HTML de 6 días) → fuera del replay hasta que el archivo diario madure

## fiscal

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (−Δ cuenta del gobierno semanal + banda) | 1.00 | 337 | 0.55 / 0.275 | -0.67 / -0.265 | 0.25 / 0.51 / 0.24 | estable | 0.092 (0.1369) | 0.107 (0.1649) | 0.175 (0.1219) | — |
| B — v0.4 base | 1.00 | 336 | 2.2412 / 0.9705 | -3.0433 / -1.5172 | 0.23 / 0.52 / 0.25 | estable | -0.052 (0.3618) | -0.103 (0.088) | -0.115 (0.2474) | 0.449 |
| C — candidato ronda 1 | 0.46 | 154 | -1.0299 / -2.8841 | -7.6744 / -5.8227 | 0.10 / 0.26 / 0.10 | estable | 0.098 (0.2844) | 0.084 (0.4018) | -0.072 (0.6392) | 0.377 |

- B · `govt_delta` ← scores:govt_account · dweekly · retraso de publicación 0 d · cobertura 0.997 · conciliación: cuenta del gobierno (Valet) — identidad
- C · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 1 d · cobertura 0.457 · conciliación: emisión neta por liquidación (AUC groups; sin cupones — la v2 neta de la cartera del BoC se archiva desde el lote 2)
- **comprobaciones**: ONE_SIDED: el corte de inyección no cruza el cero (la serie no cambia de signo en la era; el 'régimen' opuesto sería sólo menos drenaje/inyección)

**Selección (escalera de la ronda 1): B** — sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 1.00, corte estable)

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).