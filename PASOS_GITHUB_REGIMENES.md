# Tres regímenes por divisa (banco central · tesoro · general) + USD v0.1.1 — subida a GitHub

Archivos del zip (mismas rutas; "Add file → Upload files", commit a `main`):

| Ruta | Estado | Qué hace |
|---|---|---|
| `ingest/engine.py` | REEMPLAZA | `classify_regime` calcula `regimes.central_bank`, `regimes.fiscal` y `regimes.general` (regla de acuerdo; conflicto → pesos/umbrales `regime.dual`; puertas de precio SCARCITY / FLOOR_FRICTION por encima). El `regime` reportado = general |
| `ingest/blocks_usd.py` | REEMPLAZA | v0.1.1: impulso fiscal estructural (`ntf_20d`, `ntf_60d`, `ntf_fytd_vs_prior_fy`, `fiscal_impulse`); score fiscal = 50 % estructural + 50 % sorpresa diaria; flag STRUCTURAL_DEFICIT_INJECTION |
| `config/{cad,gbp,aud,jpy,chf,nzd,usd}.json` | REEMPLAZA | bloque `regime.dual` (provisional: umbrales de bloque ±0,5, pesos BC 0,6 / tesoro 0,4, umbrales generales ±0,5) + reglas actualizadas; USD → v0.1.1 |
| `{cad,gbp,aud,jpy,chf,nzd,usd}/index.html` | REEMPLAZA | tarjeta "Three regimes reported to the desk" al inicio del tab REGIME; USD añade las tarjetas del impulso fiscal en la capa 2 |
| `PASOS_GITHUB_REGIMENES.md` | NUEVO | estos pasos |

No hace falta relanzar nada a mano: el siguiente lane programado de cada divisa regenera `regime.json` con los tres regímenes. Si quieres verlo ya, lanza `refresh-<ccy>` con lane `all` y backfill `false` (o `true` en USD para el FYTD del año anterior).

Lectura offline 2026-09-09 (fixtures): USD BC DRAIN −0,70 · tesoro INJECTION +1,00 · general NEUTRAL −0,02 (conflicto resuelto por umbrales) · CAD BC DRAIN −1,0 · tesoro INJECTION +2,0 · general FLOOR_FRICTION (puerta de precio) · GBP INJECTION/NEUTRAL → NEUTRAL · AUD INJECTION/NEUTRAL → NEUTRAL · JPY INJECTION/NEUTRAL → NEUTRAL · CHF NEUTRAL/INJECTION → NEUTRAL · NZD NEUTRAL/INJECTION → NEUTRAL.
