# Prerregistro — T1'/T2' sobre el componente v0.4 y test fuera de muestra del jefe de mesa · 2026-09-11

Origen: adjudicación de la segunda ronda de institucionalidad (CURSOR F-SPLIT; KIMI H3; CODEWORD 6). Una mirada por familia, BH (Benjamini–Hochberg) dentro de la familia, bootstrap por bloques con longitud de la ACF del IC, mitades del mismo signo como condición de robustez. Nada de lo que sigue cambia el ranking publicado hasta que el test correspondiente se corra y pase.

## Familia A — T1'/T2': la columna Tesoro sobre el objeto v0.4

Hoy la columna Tesoro del jefe lee la media de 13 semanas del score de flujos v0.3 (el objeto que pasó T1/T2). El régimen fiscal vivo de EUR, CAD, AUD, JPY y CHF corre v0.4 (componente en % del stock de reservas en cinco sesiones). Son dos relojes; se declaran como tales en `jefe.json.treasury.clock_note`, F7 y ESTADO.

- **Hipótesis T1'**: Φ⁻¹ del percentil de era as-of de la media de 13 viernes del componente v0.4 activo (`net_issuance_5d` / `govt_delta` / `treasury_5d` según divisa, tal cual lo publica el motor), demeaned entre las divisas disponibles y escalado por la σ agrupada de la era, predice el retorno residual a 13 semanas con signo MMT (más inyección relativa → divisa relativamente más débil), IC > 0.
- **Hipótesis T2'**: misma medida a 26 semanas.
- **Universo**: divisas con componente v0.4 activo y ≥ 26 viernes de era en `history/<ccy>/` (GBP, NZD y CHF-BC quedan fuera mientras sigan en v0.3 o proxy; USD fuera por diseño).
- **Condición de arranque**: se corre UNA vez, cuando las cinco divisas activas tengan ≥ 26 viernes de componente v0.4 archivado tras su fecha de activación (estimado: marzo de 2027). Hasta entonces no se mira.
- **Método**: idéntico a T1/T2 (`ingest/conviction_t123.py`): residual contra betas as-of de tipos y cesta, Spearman transversal por viernes, bootstrap por bloques, BH sobre {T1', T2'}, mitades.
- **Decisión prerregistrada**: si T1' o T2' pasan (q < 0,05, mitades del mismo signo), la columna Tesoro migra al objeto v0.4 en las divisas activas y v0.3 queda en sombra; si no pasan, la columna sigue en v0.3 y se publica el resultado igual.

## Familia B — test fuera de muestra del ranking vivo

Desde el 11-sep-2026 cada viernes se congela el ranking publicado en `history/mesa/jefe_weekly.csv` (última escritura del día: fecha, divisa, rango y Z de BC, rango y Z de Tesoro, etiqueta, etiqueta por terciles, flag de compresión, sello). `jefe.json.live_tracking` cuenta los viernes archivados.

- **Hipótesis OOS-BC**: la Z de BC archivada (no recalculada) predice el retorno residual a 13 semanas, IC > 0.
- **Hipótesis OOS-TES**: la Z de Tesoro archivada predice el retorno residual a 13 y 26 semanas, IC > 0.
- **Condición de arranque**: se corre UNA vez a los 26 viernes archivados con retorno forward disponible (≈ 39 semanas desde el arranque para el horizonte de 13 s). No se mira antes.
- **Método**: el de ICL 1.0 / T1–T2, sobre las filas archivadas tal cual (sin recomputar Z, sin cambiar eras); BH sobre {OOS-BC, OOS-TES-13, OOS-TES-26}.
- **Lectura prerregistrada**: el IC vivo se compara con el IC histórico y su IC95; fuera del intervalo por debajo = decaimiento declarado en EVIDENCIA; no se recalibra nada por eso sin una nueva ronda.

## Pendiente de research (no prerregistrado aquí)

- Bootstrap por posición (banda del rango 1 y 8) y bootstrap por conglomerados de divisa (n = 8 correlacionadas): objeción estadística válida (KIMI H1), requiere diseño propio.
- Universo homogéneo del ranking BC («sólo saldos de liquidación»): cambiar el objeto validado exige su propio prerregistro; hoy no hay evidencia de que mejore.
