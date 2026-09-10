# Replay v0.4 — resumen · 2026-09-10

| divisa | bloque | decisión | variante | corte inyección (entra/sale, % del stock en 5 sesiones) | corte drenaje | estabilidad | B 12 s ρ (p_boot) | motivo |
|---|---|---|---|---|---|---|---|---|
| CAD | central_bank | A | v0.3 (Δ reserves semanal, Δ13s, dependencia de repos) | 0.375 / 0.05 | -0.55 / -0.325 | estable | -0.019 (0.7836) | sólo una variante evaluable · saldos de liquidación diarios sin histórico en fixtures (tabla HTML de 6 días) → fuera del replay hasta que el archivo diario madure |
| CAD | fiscal | B | v0.4 base | 2.2412 / 0.9705 | -3.0433 / -1.5172 | estable | -0.103 (0.088) | sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 1.00, corte estable) |
| GBP | central_bank | A | v0.3 (Δ reservas semanal, Δ13s, dependencia de repos) | 0.665 / 0.5 | -0.165 / 0.165 | provisional | -0.028 (0.8386) | sólo una variante evaluable |
| GBP | fiscal | A | v0.3 (banda CGNCR mensual) | 0.5 / 0.5 | -0.5 / -0.5 | estable | -0.258 (0.0565) | sólo una variante evaluable |
| NZD | central_bank | A | v0.3 (settlement cash Δ) | 0.375 / 0.25 | -0.375 / -0.25 | estable | -0.06 (0.4803) | sólo una variante evaluable |
| NZD | fiscal | A | v0.3 (R3 mensual + proxy) | 0.25 / 0.25 | -0.5 / -0.5 | estable | -0.069 (0.5102) | sin evidencia B y la variante v0.4 no cubre la era (cobertura 0.705) → se mantiene v0.3 |
| CHF | central_bank | B | v0.4 base | 0.501 / 0.1373 | -0.8517 / -0.5859 | estable | -0.028 (0.7201) | sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 0.99, corte estable) |
| CHF | fiscal | A | v0.3 (saldos de la Confederación mensuales) | 0.25 / 0.25 | -0.25 / -0.25 | estable | -0.164 (0.1359) | sin evidencia B y la variante v0.4 no cubre la era (cobertura 0.749) → se mantiene v0.3 |
| AUD | central_bank | B | v0.4 base | 0.466 / 0.2928 | -0.4831 / -0.2075 | estable | 0.021 (0.8876) | sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 1.00, corte estable) |
| AUD | fiscal | B | v0.4 base | 2.7248 / 1.6897 | -2.8347 / -1.8796 | estable | -0.077 (0.5842) | sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura 0.99, corte estable) |
| EUR | central_bank | A | v0.3 (exceso de liquidez diario) | 0.02 / -0.14 | -0.525 / -0.42 | estable | -0.158 (0.061) | sólo una variante evaluable · Δ cartera WFS semanal sin histórico archivado (monpol_wow) → empate 3-3 sin resolver aquí |
| EUR | fiscal | A | v0.3 (déficit estructural GFS.Q + −ΔL050100) | 0.59 / 0.46 | -0.02 / 0.1 | estable | 0.003 (0.9695) | sin evidencia B y la variante v0.4 no cubre la era (cobertura 0.745) → se mantiene v0.3 |
| JPY | central_bank | A | v0.3 (CAB 20d, d/d, banda del balance) | 0.75 / 0.75 | 0.25 / 0.25 | estable | 0.068 (0.5587) | sólo una variante evaluable · operaciones por operación (ope) sólo desde el backfill del runner → replay pendiente de ese archivo |
| JPY | fiscal | A | v0.3 (z del flujo del Tesoro) | 0.24 / 0.13 | -0.32 / -0.14 | estable | -0.009 (0.927) | sin evidencia B y la variante v0.4 no cubre la era (cobertura 0.431) → se mantiene v0.3 |
