# Motor v0.3 — subida a GitHub (web UI) y primer run

Dos lotes, mismas rutas que en `mesa-macro-fx`, "Add file → Upload files" desde la raíz del repo, un commit por lote a `main`. Sin secretos nuevos; `requirements.txt` no cambia (numpy/scipy sólo en local para `calibrate.py`).

## Lote 1 — motor, configs, dashboards, documentación (32 archivos)

| Ruta | Estado | Qué hace |
|---|---|---|
| `ingest/engine.py` | REEMPLAZA | máquina de estados por bloque (`block_regime_step`: cortes de entrada/salida, media de 7 días, persistencia), régimen general sólo por acuerdo (parcial / conflicto = NEUTRAL etiquetado), etiquetas de evidencia, "sólo acuerdo hasta 150 semanas"; con un config v0.2 se comporta exactamente como antes |
| `ingest/thresholds.py` | REEMPLAZA | ventanas de percentiles ancladas a `regime.dual.era_start` (`era_thin` cuando la era no llega a `min_n`) |
| `ingest/scoring.py` | NUEVO | componentes de flujo / nivel de cada bloque (`signals.components`), peso de nivel parametrizado (1,0 = aritmética v0.2) |
| `ingest/blocks.py`, `blocks_gbp.py`, `blocks_aud.py`, `blocks_jpy.py`, `blocks_chf.py`, `blocks_nzd.py`, `blocks_usd.py`, `blocks_eur.py` | REEMPLAZA | los 16 bloques BC / Tesoro publican sus componentes; puntuaciones idénticas a la v0.2 |
| `ingest/run.py` | REEMPLAZA | aplica `era_start` y `level_weight` del config al arrancar |
| `ingest/calibrate.py` | REEMPLAZA | `--v03` (rejilla de pesos, cortes prerregistrados, persistencia, verdades alternativas NZD / JPY), `--fdr-v03`, `--cache` |
| `ingest/apply_v03.py` | NUEVO | escribe el parche v0.3 en `config/<ccy>.json` (guarda el bloque anterior en `regime.dual_v02`; `--revert` vuelve atrás) |
| `config/{cad,gbp,aud,jpy,chf,nzd,usd,eur}.json` | REEMPLAZA | `regime.dual` v0.3: `era_start`, `anchor_percentiles`, `level_weight`, `persistence`, `agreement_only`, `agreement_only_until_weeks`, cortes por bloque con etiqueta de evidencia; el bloque v0.2 queda en `regime.dual_v02` |
| `{cad,gbp,aud,jpy,chf,nzd,usd,eur}/index.html` | REEMPLAZA | tarjeta de los tres regímenes: cortes, lectura bruta / candidato pendiente, etiquetas de evidencia, regla v0.3 |
| `CALIBRACION_V03.md`, `PASOS_GITHUB_V03.md` | NUEVO | informe con el mapa ejecutivo y estos pasos |

## Lote 2 — calibración v0.3 (34 archivos)

| Ruta | Estado | Contenido |
|---|---|---|
| `calibration/<ccy>_v03/` (8 carpetas × 4: `scores.csv`, `report.md`, `calibration.json`, `v03_regimes.csv`) | NUEVO | replay con anclaje a la era, tabla por peso de nivel, variantes de persistencia, B prerregistradas, parche de config y serie semanal de regímenes |
| `calibration/B_fdr_v03.md` · `.json` | NUEVO | corrección conjunta de las 38 pruebas prerregistradas (sólo EUR BC a 4 semanas sobrevive) |

Arrastra la carpeta `calibration` del lote 2 desde la raíz del repo: se fusiona con la existente (las carpetas `_v03` se añaden al lado de las de la v2).

## Después de subir

1. Actions → los ocho workflows `refresh-<ccy>` → Run workflow → lane `all`, backfill `false` (uno detrás de otro; 2–4 minutos cada uno). Es el primer run con el motor v0.3, así que la persistencia arranca de cero: el estado se llena con los prints de la primera semana.
2. En cada dashboard, pestaña REGIME: la tarjeta de los tres regímenes debe mostrar "Rule (engine v0.3)", los cortes de cada bloque y la etiqueta de evidencia. Lecturas esperadas con los datos del 8/9-sep (regresión offline): CAD BC DRAIN · Tesoro INJECTION · general FLOOR_FRICTION (puerta de precio); GBP BC INJECTION · Tesoro NEUTRAL; AUD NEUTRAL / NEUTRAL; JPY NEUTRAL / INJECTION; CHF NEUTRAL / INJECTION; NZD NEUTRAL / INJECTION; USD BC DRAIN · Tesoro NEUTRAL; EUR BC INJECTION (relativo a su era) · Tesoro NEUTRAL. General NEUTRAL (parcial) en las siete sin puerta de precio.
3. Si algo se ve raro, `python -m ingest.apply_v03 --all --revert` en local y subir los ocho configs: el motor vuelve a la v0.2 sin tocar código.

Regresión offline con los configs v0.3: compuesto de 4 bloques sin cambio (CAD −0.137 · GBP 0.4 · AUD 0.391 · JPY 0.485 · CHF 0.425 · NZD 0.3 · USD 0.545 · EUR 0.397); `ingest.validate` limpio en las ocho.

Repetir la calibración en local: `python -m ingest.calibrate --ccy eur --fixtures fixtures/eur_hist --v03` (una divisa; `--era` opcional, por defecto la era de la v2) y `python -m ingest.calibrate --fdr-v03`; después `python -m ingest.apply_v03 --all`.
