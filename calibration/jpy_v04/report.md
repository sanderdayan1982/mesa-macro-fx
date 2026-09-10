# Replay v0.4 · JPY · era desde 2024-07-31 · 102 semanas (2024-08-05 → 2026-09-01)

## central_bank
_operaciones por operación (ope) sólo desde el backfill del runner → replay pendiente de ese archivo_

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (CAB 20d, d/d, banda del balance) | 1.00 | 102 | 0.75 / 0.75 | 0.25 / 0.25 | 0.14 / 0.68 / 0.19 | estable | 0.012 (0.914) | 0.068 (0.5587) | None (None) | — |

- **comprobaciones**: ONE_SIDED: el corte de drenaje no cruza el cero (la serie no cambia de signo en la era; el 'régimen' opuesto sería sólo menos drenaje/inyección)

**Selección (escalera de la ronda 1): A** — sólo una variante evaluable · operaciones por operación (ope) sólo desde el backfill del runner → replay pendiente de ese archivo

## fiscal

| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |
|---|---|---|---|---|---|---|---|---|---|---|
| A — v0.3 (z del flujo del Tesoro) | 1.00 | 102 | 0.24 / 0.13 | -0.32 / -0.14 | 0.23 / 0.52 / 0.24 | estable | -0.04 (0.7136) | -0.009 (0.927) | None (None) | — |
| B — v0.4 base | 1.00 | 102 | 0.6459 / 0.1934 | -1.0505 / -0.7651 | 0.23 / 0.54 / 0.23 | estable | 0.018 (0.8431) | 0.098 (0.3953) | None (None) | 0.49 |
| C — candidato ronda 1 | 1.00 | 102 | 0.1916 / -0.0502 | -0.4879 / -0.3817 | 0.22 / 0.52 / 0.27 | estable | -0.029 (0.7471) | 0.063 (0.5797) | None (None) | 0.392 |

- B · `treasury_5d` ← hist:treasury_realized_daily · daily5 · retraso de publicación 0 d · cobertura 1.0 · conciliación: 財政等要因 realizado (速報/確報) = −Δ cuenta del gobierno
- C · `net_issuance_5d` ← hist:net_issuance_private_daily · daily5 · retraso de publicación 1 d · cobertura 1.0 · conciliación: emisión neta del MoF por fecha de emisión, neta de mei

**Selección (escalera de la ronda 1): B** — sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 1.00, corte estable)

Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).