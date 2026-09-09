# EUR — subida a GitHub (web UI) y primer run (Fase 2)

Archivos del zip (mismas rutas que en `mesa-macro-fx`; "Add file → Upload files", commit a `main`):

| Ruta | Estado | Qué hace |
|---|---|---|
| `ingest/providers_eur.py` | NUEVO | ECB Data Portal (SDMX csvdata sin clave, FLOW/KEY separados en el primer punto, ≥ 1,5 s entre peticiones; semanas → viernes, meses → día 1, trimestres → inicio con 90 días de margen) + CSV APP/PEPP de ecb.europa.eu (tenencias a coste amortizado y amortizaciones programadas) + XLSX de la Finanzagentur (líneas por ISIN agregadas por fecha de subasta) |
| `ingest/blocks_eur.py` | NUEVO | las cuatro capas EUR del config v0.2 (E1–E15): anclas dead-man 1,5/1,0/0,75 bn sin disparo, TOMO 30/100/250 bn con puerta de precio, fase QT ±20 bn, reconciliación APP+PEPP, impulso fiscal 4w/13w, GFS estructural, subastas DE, TARGET Δ3m, impulso de crédito en €, MIR, BLS, €STR − DFR con anclas por régimen de liquidez (0/5/10 → 5/10/15 bajo 1,5 bn), dispersión R75−R25, prima periférica, spreads país |
| `ingest/run.py` | REEMPLAZA | `fetch_eur` (lanes daily / daily_retry / weekly_tue / weekly / monthly); 404 del portal sin observaciones nuevas = no es error |
| `ingest/engine.py` | REEMPLAZA | `_calendar_eur` (Consejo de Gobierno 2026–27, WFS martes, APP viernes, MRO, períodos de mantenimiento 2026, festivos TARGET, TGB/BSI mensuales); flag PHASE_ sólo con fase conocida |
| `config/eur.json` | REEMPLAZA (v0.2.1) | ids de los parsers que ya están vivos (APP:holdings, PEPP:holdings, DE:bid_to_cover / avg_yield / retention / volume), L050000 como contexto, reglas de puntuación documentadas |
| `eur/index.html` | NUEVO | dashboard `/eur/` (misma carcasa que USD; tarjeta de los tres regímenes en la pestaña REGIME) |
| `.github/workflows/refresh-eur.yml` | NUEVO | lanes con doble cron CEST/CET + paso de diagnóstico a los tres hosts |
| `fixtures/eur/` (58 archivos) | NUEVO | test offline: 52 claves del portal con historia (ILM diario desde 2024-09 / 2022, WFS desde 2019, €STR desde 2019-10, BSI/MIR/IRS/TGB desde 2015), 5 CSV APP/PEPP, XLSX Finanzagentur — capturados el 2026-09-09 desde los orígenes primarios |
| `requirements.txt` | REEMPLAZA | añade `openpyxl` (XLSX de la Finanzagentur) |
| `README.md`, `index.html` | REEMPLAZA | sección EUR, enlace en la landing (ocho divisas vivas) |
| `PASOS_GITHUB_EUR.md` | NUEVO | estos pasos |

No subir `data/`, `history/` ni `logs/`: los genera el workflow. No hace falta ningún secreto: el ECB Data Portal, los CSV del BCE y la Finanzagentur no piden clave.

Después de subir:
1. Actions → `refresh-eur` → Run workflow → lane `all`, backfill `true` (~3–4 min: 49 claves a 1,5 s cada una + 4 CSV + 1 XLSX, con 8–12 años de historia).
2. Abrir `https://mesa-macro-fx-g8-commands-centers.netlify.app/eur/`. Banner verde = sin errores de fuente.
3. Comprobar (valores del 2026-09-07/08, verificados a mano en el portal): exceso de liquidez ≈ €2,160 bn (SAFE, banda 1,5–4,0), €STR − DFR −6,2 pb (NORMAL), TOMO €28,2 bn (ROUTINE), depósitos de gobiernos €89,3 bn, APP ago-2026 €2.077,9 bn y PEPP €1.284,8 bn (reconciliación RECONCILED), Bund/g 09-08 b/c ponderado 1,94, prima periférica 42 pb, OAT − Bund 78 pb (WATCH por el ancla 70 de tu v5), M3 3,38 %, BSI GREEN.
4. Régimen esperado el primer día: **banco central NEUTRAL (+0,40) · Tesoro equivalente NEUTRAL (+0,18) · general NEUTRAL (dual +0,33)**, flags PHASE_QT, STRUCTURAL_DEFICIT_INJECTION (déficit −3,06 % PIB), COUNTRY_SPREAD_WATCH (OAT). Coincide con la lectura consensuada de la triangulación.
5. El paso "Diagnose source reachability" muestra el código HTTP de `data-api.ecb.europa.eu`, `ecb.europa.eu` y `deutsche-finanzagentur.de` desde el runner. Si alguno da 403/timeout, pégamelo y abrimos el plan B (los tres fueron verificados hoy desde tu navegador, no desde GitHub).
6. Al día siguiente (lane daily 10:45 CET) el log de operador mostrará `NO_NEW_OBSERVATIONS` para las tres claves de tipos oficiales (FM.B…): es normal, son series escalonadas que sólo publican en los cambios.

Regresión offline: CAD −0.137, GBP 0.4, AUD 0.358, JPY 0.485, CHF 0.425, NZD 0.3, USD 0.545 sin cambio; EUR NEUTRAL 0.397 (BC +0.40 · fiscal +0.18 · bancos +1.00 · tipos +0.20). Camino "en vivo" probado contra un stub local de las tres fuentes en las cinco lanes (histórico, incremental, 404 sin observaciones).

Pendiente para la Fase 3 del EUR: parsers AFT / MEF / Tesoro ES / Comisión UE, Bundesbank BBSSY (Bund 10Y diario), estadísticas diarias del mercado monetario del BCE, calendario de períodos de mantenimiento 2027 y el texto literal del informe mensual del Bundesbank (1,5 bn fin-2027).
