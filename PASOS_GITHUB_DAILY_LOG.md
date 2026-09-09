# daily_log 1.0 — subida a GitHub (web UI) y primer run

Un solo lote, mismas rutas que en `mesa-macro-fx`, "Add file → Upload files" desde la raíz del repo, un commit a `main`. Sin secretos nuevos; `requirements.txt` no cambia (numpy ya está).

## Lote único — motor, panel, salidas, dashboards, workflows, documentación (32 archivos)

| Ruta | Estado | Qué hace |
|---|---|---|
| `ingest/narrative.py` | NUEVO | las siete frases (cabecera, F1–F7) con el vocabulario de cada divisa, mapa de frecuencia, variantes degradadas, glosario, ledger de rachas → `data/<ccy>/agent.json` |
| `ingest/jefe.py` | NUEVO | jefe de mesa: ranking de las ocho por Δ13 semanas de reservas (Z transversal, σ agrupada de era, as-of) → `data/mesa/jefe.json` |
| `ingest/gate.py` | NUEVO | puerta anti-invención (A1–A5 + lista negra del cierre + fuzzing); si falla, el texto queda retenido |
| `ingest/run.py` | REEMPLAZA | llama a `narrative.run(ccy)` al final de cada refresco (nunca bloquea la ingesta) |
| `calibration/conviction/reserves_panel.json` | NUEVO | panel semanal congelado de reservas (de los replays de la calibración v0.3, hasta 2026-09-04); el motor lo extiende con `history/<ccy>/` |
| `data/{usd,eur,gbp,jpy,chf,cad,aud,nzd}/agent.json` | NUEVO | primera publicación (2026-09-09), las ocho pasan la puerta |
| `data/mesa/jefe.json` | NUEVO | ranking al viernes 2026-09-04 |
| `{usd,eur,gbp,jpy,chf,cad,aud,nzd}/index.html` | REEMPLAZA | pestaña AGENT: siete frases, ranking del jefe de mesa, puerta, hueco del cierre del modelo |
| `.github/workflows/refresh.yml`, `refresh-{usd,eur,gbp,jpy,chf,nzd,aud}.yml` | REEMPLAZA | paso "Anti-invention gate" después de validar; `data/mesa` en el commit |
| `DAILY_LOG_V1.md`, `PASOS_GITHUB_DAILY_LOG.md` | NUEVO | documentación y estos pasos |

Cómo arrastrar: desde la raíz del repo, "Upload files", arrastra las carpetas `ingest`, `calibration`, `data`, `.github` y las ocho carpetas de divisa tal como vienen en el zip (se fusionan con las existentes; sólo se reemplazan los archivos con el mismo nombre), y los dos `.md` sueltos. Si el navegador no deja arrastrar la carpeta `.github` (empieza por punto), entra en `.github/workflows/` en GitHub y sube ahí los ocho `.yml`.

## Después de subir

1. Actions → cualquier `refresh-<ccy>` → Run workflow → lane `all`, backfill `false`. En el log del paso "Run ingestion" debe aparecer `daily_log gate=PASS hash=… degraded=N` y el paso "Anti-invention gate" en verde.
2. Dashboard → pestaña AGENT: cabecera «Datos hasta …», F1–F7, tarjeta del jefe de mesa con las ocho filas (AUD 1.º … NZD 8.º al viernes 2026-09-04), badge «PUERTA: PASA». La racha empieza en 1.ª y sube una lectura por cada as-of nuevo del bloque.
3. Con el primer run de cada divisa, `data/mesa/jefe.json` se reescribe con la misma lectura (el panel es el mismo para las ocho); a partir del viernes 2026-09-11 el ranking avanza solo con los CSV de `history/`.
4. Si la puerta retiene un texto (badge rojo), `agent.json.gate.failures` dice qué aserción falló; el resto del refresco no se ve afectado.

Comprobación en local: `python -m ingest.narrative --all` (imprime las ocho narrativas y el estado de la puerta) y `python -m ingest.gate --all --fuzz`.
