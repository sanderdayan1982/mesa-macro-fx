# ACTA AGENTE 2026-10-09

## Diagnóstico
- `logs/eur/oplog.json`: desde 2026-10-07 todas las ejecuciones EUR registran `tesoro_13: HTTP 404 for https://www.tesoro.es/sites/default/files/estadisticas/13.xlsx (archive/fixture)`; la amortización española cae al archivo/fixture.
- Comprobación en la fuente primaria (2026-10-09, cliente `ingest.tls` con completado de cadena AIA): la URL vieja devuelve 404. La página oficial https://www.tesoro.es/deuda-publica/estad%C3%ADsticas-mensuales publica «Financiación neta del Estado en 2026 y 2025» en `/documents/d/tesoro/13-xlsx` (200, xlsx, 46 122 bytes).
- `es_parse_financiacion` lee el fichero nuevo igual que el fixture (mismas filas 2026-01/04/05/07/10; solo cambia que julio llega como fila mensual, `day=''`).

## Cambio
- `ingest/ops_eur_lines.py`: `TESORO_13_XLSX` → `https://www.tesoro.es/documents/d/tesoro/13-xlsx`.
- Test `ingest/tests_agent_eur_tesoro13.py` con extracto real `fixtures/agent/eur/tesoro_estadisticas_mensuales_20261009.html` (falla con la URL vieja).

## No tocado
- WFS EUR (MRO/LTRO…) en 2026-09-25 mientras el BCE ya publica 2026-W40: ver informe (enrutado de carriles, fuera de mi alcance).
