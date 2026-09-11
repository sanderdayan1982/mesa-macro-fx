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
| B — v0.4 base | 1.00 | 210 | -0.1595 / -0.501 | -1.519 / -1.0957 | 0.23 / 0.53 / 0.23 | estable | 0.089 (0.2424) | -0.022 (0.7716) | -0.026 (0.7556) | 0.31 |
| C — candidato ronda 1 | 0.64 | 135 | 4.2415 / 1.5731 | -5.672 / -4.0675 | 0.15 / 0.36 / 0.14 | estable | 0.069 (0.4368) | -0.054 (0.5082) | -0.047 (0.6167) | 0.415 |

- B · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 1 d · cobertura 1.0 · conciliación: tenders por liquidación − letras vencidas − reembolsos y cupones BRUTOS al tenedor de mercado (NZDM bonds on issue, todos los cierres de mes; dos lados sólo desde el primer cierre de mes archivado)
- **comprobaciones**: ONE_SIDED: el corte de inyección no cruza el cero (la serie no cambia de signo en la era; el 'régimen' opuesto sería sólo menos drenaje/inyección)
- C · `residual_5d` ← hist:residual_flow_daily · daily5 · retraso de publicación 1 d · cobertura 0.643 · conciliación: proxy residual diario (conciliado D10 −7 mm)

**Selección (escalera de la ronda 1): A** — sin evidencia B y la variante v0.4 es de un solo signo (ONE_SIDED: el corte de inyección no cruza el cero (la serie no cambia de signo e) → se mantiene v0.3

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).