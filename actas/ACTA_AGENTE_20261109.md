# ACTA — CAD indicadores de operaciones del BdC: tabla de saldos de liquidación (2026-11-09)

**Síntoma.** `logs/cad/oplog.json` y `source_health.errors`: `market ops indicators: settlement balances table not found (STRUCTURE CHANGE?)`. El archivo `history/cad/market_ops_indicators.csv` se queda en 2026-11-03.

**Qué no es la causa.** `government_deposits_banks` (Valet V36811) y `bank_assets` (Valet V36852) siguen en 2026-08-01 porque esa es la última observación publicada, no porque falle el parser. Comprobado el 2026-11-09:

- Valet `observations/V36811,V36852/json`: 2026-08-01 = 2 965 y 5 293 478 (millones CAD). Etiquetas sin cambio.
- Statistics Canada WDS, tabla 10-10-0109-01, vectores 36811 y 36852: mismos valores, `cubeEndDate` 2026-08-01, `releaseTime` 2026-10-21.
- Página C1 del BdC: última columna `2026-08`. No hay impresión de septiembre.

**Causa (fuente primaria, 2026-11-09).** La página https://www.bankofcanada.ca/rates/indicators/market-operations-indicators/ cambió de formato:

- Las fechas del encabezado usan el guion de no separación `&#8209;` (U+2011), así que el regex `^\d{4}-\d{2}-\d{2}$` no veía la tabla.
- La fila `Actual` pasó a ser `Amount in Lynx`; el resto se publicó en minúsculas (`Term repos`, `Securities lending`, `Overnight repos (OR)`).
- Las mismas cantidades, en millones de CAD, están en Valet: `ACTUAL`, `SPRA_OUT`, `SRA_OUT`, `TERMREPOS`, `SEC_LEND`. `ACTUAL` coincide con los 41 puntos archivados de `settlement_actual` (0 diferencias). `TOTAL_SETTLEMENT_BALANCES` = Lynx + Real-Time Rail y desde 2026-11-04 queda 2 millones por encima; no se usa, para no saltar el nivel. Sin conversión de unidades.

**Cambio.** Solo el fetch/parse CAD del BdC: `ingest/providers.py` (`MarketOpsIndicatorsProvider` lee Valet, `recent=16`, y si falla parsea el HTML) y `ingest/ops_cad.py` (`parse_indicators_html` acepta el HTML viejo y el de 2026-11). Sin cambios de metodología.

**Corrida local** `python -m ingest.run --ccy cad --lane all --no-rss` (2026-11-09): `errors=[]`. `settlement_actual` 2026-11-09 = 69 413 (antes 2026-11-03 = 72 333). `government_deposits_banks` y `bank_assets` siguen en 2026-08-01, igual que la fuente.

**Siguiente.** El workflow `refresh-cad` (`.github/workflows/refresh.yml`) regenera `data/cad/*.json` tras el merge. Los JSON de esta corrida local no se commitean.
