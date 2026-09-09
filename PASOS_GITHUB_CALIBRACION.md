# Calibración v2 — subida a GitHub (web UI) de las correcciones y del paquete de umbrales

Todo va a `main` con "Add file → Upload files" (arrastrar las carpetas del zip conserva las rutas). GitHub admite como máximo 100 archivos por commit desde el navegador, así que el zip viene en **tres lotes** con las mismas rutas que en `mesa-macro-fx`; se suben en orden, un commit por lote. Nada de esto necesita secretos ni cambia `requirements.txt`: `calibrate.py` sólo corre en local (numpy + scipy) y ningún workflow lo importa.

## Lote 1 — código y documentación (40 archivos)

| Ruta | Estado | Qué hace |
|---|---|---|
| `ingest/blocks_chf.py` | REEMPLAZA | **corrección de la histéresis de dos lados** (`_two_sided`): `exit_on: "pA/pB"` ahora es salida del lado alto en pA y del lado bajo en pB; antes un STRESS por el lado alto no salía nunca. Afecta en vivo al CHF (`sight_deposits_wow`, `other_sight_deposits_wow`) y al NZD (`settlement_cash_wow`, `csa_mom`, `govt_cash_influence`, `tbill_yield_minus_ocr_bps`, `bank_bill_90d_minus_ocr_bps`, `hike_pricing_bps`, `curve_10y_2y_bps`) |
| `ingest/blocks.py` | REEMPLAZA | corrección CAD: celdas vacías de los depósitos a plazo del Receptor General = 0 (antes el bloque fiscal se quedaba sin dato) |
| `ingest/calibrate.py` | NUEVO | replay as-of semanal de las ocho divisas con retardos de publicación, control FX, método A (percentiles de era) + B (verdad de funding), subastas, bootstrap por bloques, FDR conjunto (`--fdr`), `FINAL_CUTS` = fuente única de los cortes de mesa |
| `calibration/<ccy>/scores.csv` · `report.md` · `calibration.json` (8 divisas, 24 archivos) | NUEVO | puntuaciones semanales del replay, informe de detalle y JSON con `ab.final_cuts`, `proposal_auto` y `p_block_bootstrap` |
| `calibration/B_fdr.md` · `B_fdr.json` | NUEVO | corrección conjunta Benjamini–Hochberg + bootstrap de las 32 pruebas B: sólo el BC del EUR sobrevive |
| `CALIBRACION_{CAD,GBP,AUD,JPY,CHF,NZD,USD,EUR}.md` | NUEVO | informe por divisa con la sección "Corrección conjunta (v2)" y la etiqueta de evidencia |
| `PROMPT_TRIANGULACION_UMBRALES.md` · `MATRIZ_RESPUESTA_UMBRALES.md` | NUEVO | prompt y matriz v2 de la triangulación de umbrales (las dos rondas ya cerradas) |
| `PASOS_GITHUB_CALIBRACION.md` | NUEVO | estos pasos |

## Lote 2 — fixtures históricos AUD · CHF · GBP · JPY · NZD (65 archivos, 10,6 MB)

| Ruta | Estado | Contenido |
|---|---|---|
| `fixtures/aud_hist/` (18) | NUEVO | tablas RBA A1/A2/A3/D1/D3/F1/F2/F11.1, tenders AOFM (bonos, notas, TIB), AUD/USD |
| `fixtures/chf_hist/` (12) | NUEVO | cubos del SNB (snbgwdchfsgw, snbgwdmigirow, snbgwdzid, snbbipo, bamire, snbfxtr, snbmoba, zirepo), gmges.xlsx, celdas AFF/EFV (MMDRC, bonos), USD/CHF del IADB del BoE (XUDLSFD) |
| `fixtures/gbp_hist/` (9) | NUEVO | IADB diario/semanal/mensual/eventos, PSF de la ONS, D21A gilts y D22D T-bills de la DMO |
| `fixtures/jpy_hist/` (24) | NUEVO | cuentas del BoJ, series API md/fm, TONA, JSDA, subastas MOF (JGB, T-bills), USD/JPY |
| `fixtures/nzd_hist/` (2) | NUEVO | `rbnz_cells.json` (2,1 MB: hd12/hd3/hd10/hr1/hr3/hb2/hb1) y `nzdm_cells.json` (1,2 MB: tenders de letras y bonos) — celdas ya parseadas de los XLSX del RBNZ y del NZDM |

## Lote 3 — fixtures históricos EUR · USD (86 archivos, 5,0 MB)

| Ruta | Estado | Contenido |
|---|---|---|
| `fixtures/eur_hist/` (59) | NUEVO | los 58 de `fixtures/eur` más la historia completa del ECB Data Portal (ILM diario/semanal desde 2005, EXR desde 1999, FM, €STR) y `emissionshistorie_en.xlsx` de la Finanzagentur |
| `fixtures/usd_hist/` (27) | NUEVO | 21 series FRED, 5 extractos del DTS de Fiscal Data (caja, totales pre/post-2022, deuda), `treasurydirect_auctions.csv` (1,1 MB) |

El CAD no tiene carpeta `_hist`: su replay usa `fixtures/cad`, que ya está en el repo. No subir `data/`, `history/` ni `logs/`.

## Después de subir

1. Actions → `refresh-chf` → Run workflow → lane `all` (sin backfill). Luego `refresh-nzd` → lane `all`. Es lo único que cambia en vivo: los dos runners recogen la corrección de la histéresis de dos lados. Los otros seis workflows no hace falta lanzarlos (el arreglo del CAD ya estaba en el runner desde la Fase 3 y la calibración no toca configs).
2. Abrir `/chf/` y `/nzd/`: banner verde. En el NZD, `settlement_cash_wow` debería salir SAFE o WATCH según el print de la semana, no STRESS fijo; en el CHF, `sight_deposits_wow` igual. Si alguno sigue en STRESS con un print dentro de banda, pégame el JSON del bloque.
3. Comprobar que `calibration/B_fdr.md` se lee bien en GitHub (tabla de 32 filas, sólo EUR BC con q < 0,05).
4. Ningún `config/<ccy>.json` cambia en esta subida: los cortes de `FINAL_CUTS` se llevan al config **después** de la v0.3 (flujos dicen la inyección, persistencia 2/1, regla de acuerdo, etiquetas de evidencia), como quedó en la ronda 2.

Regresión offline con los `blocks.py` / `blocks_chf.py` corregidos: CAD −0.137, GBP 0.4, AUD 0.391, JPY 0.485, CHF 0.425, NZD 0.3, USD 0.545, EUR 0.397 — sin cambio en ningún régimen general (el error `zimoma: no series returned` del CHF es el hueco conocido del fixture, no del código).

Para repetir la calibración en local (macOS): `pip install numpy scipy` y, desde la raíz del repo, `python -m ingest.calibrate --ccy eur --fixtures fixtures/eur_hist --era 2022-09-14` (una divisa) o `python -m ingest.calibrate --fdr` (corrección conjunta). Los comandos exactos de cada divisa están en la primera línea de cada `CALIBRACION_<CCY>.md`.

Siguiente paso acordado: v0.3 del motor (normalización por era de los componentes, peso de nivel calibrado por replay, persistencia 2/1 y "sólo acuerdo bajo 150 semanas" como parámetros, verdades de funding nuevas para NZD y JPY, cortes prerregistrados) y recalibración de las ocho; después los parches de config.
