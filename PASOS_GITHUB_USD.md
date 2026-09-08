# USD — subida a GitHub (web UI) y primer run

Archivos del zip (mismas rutas que en `mesa-macro-fx`; "Add file → Upload files", commit a `main`):

| Ruta | Estado | Qué hace |
|---|---|---|
| `ingest/providers_usd.py` | NUEVO | FRED por CSV sin clave (`fredgraph.csv`, con fallback API si existe `FRED_API_KEY`) + Fiscal Data API (DTS: cash, transacciones, deuda) |
| `ingest/blocks_usd.py` | NUEVO | las cuatro capas USD con las métricas exactas de H.4.1 / DTS / H.8-H.15 |
| `ingest/run.py` | REEMPLAZA | `fetch_usd` (lanes daily / daily_retry / weekly_thu / weekly / monthly) |
| `ingest/engine.py` | REEMPLAZA | `_calendar_usd` (FOMC 2026–27, H.4.1, H.8, DTS, ventanas estacionales, festivos NYSE) |
| `ingest/providers_nzd.py` | REEMPLAZA | fix3 NZD (celdas multilínea del listado NZDM) — si ya lo subiste, idéntico |
| `config/usd.json` | NUEVO (v0.1.0) | 47 series, umbrales tuyos como anclas absolutas, régimen, alertas, escenarios, calendario |
| `usd/index.html` | NUEVO | dashboard `/usd/` |
| `.github/workflows/refresh-usd.yml` | NUEVO | lanes con doble cron EDT/EST |
| `fixtures/usd/*.csv` (23) | NUEVO | test offline (capturados de FRED y Fiscal Data el 2026-09-08) |
| `README.md`, `index.html` | REEMPLAZA | sección USD, enlace en la landing |
| `USD_MIGRACION_mapa.md`, `PASOS_GITHUB_USD.md` | NUEVO | mapa 1:1 y estos pasos |

No subir `data/`, `history/` ni `logs/`: los genera el workflow. No hace falta ningún secreto: FRED por CSV y Fiscal Data no piden clave (el secreto `FRED_API_KEY` es opcional, sólo como respaldo).

Después de subir:
1. Actions → `refresh-usd` → Run workflow → lane `all`, backfill `true` (~1–2 min: 20 CSV de FRED + 3 endpoints DTS, con 4 años de historia).
2. Abrir `https://mesa-macro-fx-g8-commands-centers.netlify.app/usd/`. Banner verde = sin errores de fuente.
3. Comprobar: WRESBAL ≈ 2,89 T (NERVOUS), TGA 968 B (HEAVY DRAIN), SOFR − IORB 0 pb, H.8 GREEN, tablas DTS con fecha 09-04 (o 09-08 si corres después de las 22:00 WAT).
4. El paso "Diagnose source reachability" del workflow muestra el código HTTP de FRED y Fiscal Data desde el runner (por si algún día bloquean como el RBNZ).

Regresión offline: CAD −0.137, GBP 0.4, AUD 0.358, JPY 0.485, CHF 0.425, NZD 0.3 sin cambio; USD NEUTRAL 0.343.
