# Motor v0.3 — calibración por replay de las ocho divisas (2026-09-09)

Cierra lo acordado en la ronda 2 de la triangulación de umbrales: los niveles no pueden fijar un bloque en un estado durante toda una era, la persistencia y la regla de acuerdo entran en el motor como parámetros, los cortes se prerregistran (sin búsqueda en rejilla), NZD y JPY reciben una verdad de funding nueva, y cada corte lleva su etiqueta de evidencia. Todo sale del mismo replay as-of semanal de la v2 (`ingest/calibrate.py --v03`), con las ventanas de percentiles ancladas a la era desde su primer día. Detalle por divisa en `calibration/<ccy>_v03/report.md`; corrección conjunta en `calibration/B_fdr_v03.md`.

## Mapa ejecutivo

| divisa | era (semanas) | BC INJ ≥ (salida) / DRAIN ≤ (salida) | Tesoro INJ ≥ / DRAIN ≤ | BC INJ / N / DRAIN (% era) | Tesoro | general INJ / parcial / conflicto / DRAIN | estado |
|---|---|---|---|---|---|---|---|
| CAD | 2020-03-23 (337) | +0,38 (+0,05) / −0,55 (−0,33) | +0,55 (+0,28) / −0,67 (−0,27) | 25 / 52 / 22 | 25 / 51 / 23 | 8 / 80 / 5 / 5 | **firme** (frecuencia de era) |
| GBP | 2022-11-01 (201) | +0,67 (+0,50) / −0,17 (+0,17) | +0,50 / −0,50 | 33 / 34 / 32 | 9 / 69 / 21 | 3 / 75 / 12 / 9 | **firme** (frecuencia); Tesoro banda por diseño |
| AUD | 2025-04-09 (74) | +1,00 / +0,09 (+0,34) | +0,53 (+0,34) / −0,56 (−0,37) | 28 / 48 / 23 | 21 / 54 / 24 | 12 / 71 / 4 / 12 | **provisional** (era corta: sólo acuerdo hasta 150 s) |
| JPY | 2024-07-31 (102) | +0,75 / +0,25 | +0,24 (+0,13) / −0,32 (−0,14) | 13 / 67 / 18 | 23 / 52 / 24 | 2 / 84 / 8 / 3 | **provisional** (era corta); repo GC como verdad, 58 semanas |
| CHF | 2022-09-22 (207) | +1,00 (+0,50) / −0,50 | +0,25 / −0,25 | 33 / 42 / 24 | 21 / 58 / 19 | 2 / 80 / 15 / 1 | **firme** (frecuencia); Tesoro banda por diseño |
| NZD | 2022-07-01 (210) | +0,38 (+0,25) / −0,38 (−0,25) | +0,25 / −0,50 | 27 / 43 / 28 | 23 / 51 / 24 | 7 / 73 / 14 / 5 | **firme** (frecuencia); Tesoro banda por diseño; verdad nueva no separa |
| USD | 2022-06-01 (223) | +0,11 (0,00) / −0,50 (−0,30) | +1,22 (+1,11) / +0,61 (+0,81) | 24 / 49 / 26 | 25 / 50 / 24 | 7 / 71 / 11 / 9 | **firme** (frecuencia); Tesoro = ritmo del impulso (INJECTION permanente) |
| EUR | 2022-09-14 (208) | +0,02 (−0,14) / −0,53 (−0,42) | +0,59 (+0,46) / −0,02 (+0,10) | 24 / 50 / 25 | 23 / 50 / 26 | 10 / 74 / 4 / 10 | **BC validado por funding** (única de las ocho); Tesoro frecuencia; DRAIN fiscal ahora posible |

Rediseño pendiente (no lo resuelve un umbral): la verdad de funding del NZD (ni bank bill 30 d − OCR ni interbancario overnight − OCR separan: ρ +0,07 / +0,04); el peso del Tesoro en las divisas donde es una banda de dos o tres valores (GBP, CHF, NZD) — la banda vale, pero no admite calibración fina hasta que el flujo se mida en continuo; y la ausencia de verdad de funding en JPY con tipos positivos más allá de las 58 semanas de repo GC de la JSDA (Japan Securities Dealers Association) — el histórico completo del Tokyo Repo Rate es la siguiente captura.

## Qué cambia en el motor (y qué no)

1. **Cortes por bloque con histéresis y persistencia.** El régimen de cada bloque (BC, Tesoro) sale de la **media de 7 días** de su puntuación (dos prints semanales en el replay; una semana de prints diarios en vivo) contra cortes de entrada p80 / p20 de la era y de salida p67 / p33, siempre el valor alcanzable más próximo y siempre estrictamente más allá de la mediana (en escalas discretas, el siguiente valor tras la masa de la mediana; un corte nunca captura más del 35 % de la era). Persistencia "dos prints consecutivos fuera del corte" — la lectura literal de la ronda 2 — se probó y se descartó con datos: deja los regímenes del BC en el 2–13 % de las semanas (CAD 4 / 5 %, JPY 2 / 7 %, EUR 12 / 4 %), porque los flujos semanales no repiten dos veces seguidas. La media de dos semanas conserva las frecuencias de la era (≈ 25 / 50 / 25) y reduce los cambios entre un 25 % y un 60 % respecto a sin persistencia. Las tres variantes están en cada informe.
2. **Régimen general sólo por acuerdo.** Ambos inyectan → LIQUIDITY_INJECTION; ambos drenan → LIQUIDITY_DRAIN; parcial o conflicto → NEUTRAL etiquetado (parcial / conflicto), sin pesos duales; el score dual se publica como contexto. Consecuencia medida: el general está en INJECTION o DRAIN entre el 3 % (CHF) y el 24 % (AUD) de las semanas de la era; el conflicto abierto (BC y Tesoro en sentidos opuestos) ocupa del 4 % (EUR) al 15 % (CHF). Es lo que la mesa pidió: el general sólo habla cuando los dos hablan.
3. **Ventanas ancladas a la era.** Todo percentil (umbrales WATCH/STRESS/CRISIS, bandas RISK_ON/OFF) se calcula sólo con prints desde `era_start`; si la era tiene menos de `min_n` prints se vuelve a la ventana móvil y el metric queda marcado `era_thin`. En vivo sólo cambia lecturas cuando la ventana del metric es más larga que la era (AUD, JPY, y las ventanas de 260 semanas del CHF); en las eras de 4 años con ventanas de 156 semanas no toca nada.
4. **Peso de los niveles: calibrado, y la respuesta es que no cambia las frecuencias.** Cada bloque publica ahora sus componentes de flujo y de nivel (`signals.components`), y la calibración vuelve a puntuar el replay con pesos 1,0 / 0,5 / 0,25 / 0 sin repetirlo. Con cortes relativos a la era las cuotas INJ / DRAIN son las mismas con cualquier peso (un desplazamiento constante no mueve un percentil); sólo cambia el orden de las semanas, y eso sólo lo puede juzgar la verdad de funding. Regla prerregistrada: se conserva 1,0 (aritmética v0.2) salvo que otro peso tenga una B que sobreviva al bootstrap a 12 semanas con signo MMT (Modern Monetary Theory). Ningún peso lo consigue en ninguna divisa: el 0,25 de la ronda 2 no tiene evidencia que lo respalde y no se aplica. El parámetro queda en el config (`level_weight`) para cuando la tenga.
5. **Verdades de funding nuevas.** NZD: interbancario overnight − OCR (Official Cash Rate) (RBNZ B2 INM.DN.NZK − INM.DP1.N, diario desde 2018): no separa (BC ρ +0,07 a 4 s, +0,04 a 12; medias condicionales no monótonas). JPY: repo GC O/N T+0 de la JSDA − IOER (interest on excess reserves), 58 semanas: **BC ρ −0,33 a 4 semanas (p bootstrap 0,03; DRENAJE → +0,54 pb, t 2,7)**; no sobrevive el FDR conjunto (q 0,61) por el tamaño de la muestra, pero es la primera verdad de funding del JPY con el signo correcto y se mantiene como prueba prerregistrada para cuando haya historia.
6. **Pruebas B prerregistradas y corrección conjunta.** 38 pruebas (2 bloques × 2 horizontes × 8 divisas + las dos verdades alternativas), una por celda, sin rejilla; Benjamini–Hochberg sobre el p del bootstrap por bloques. Sobrevive **sólo EUR BC a 4 semanas (ρ −0,31, p 0,0005, q 0,02)**, como en la v2. La v2 lo daba a 4 y 12; con la puntuación suavizada y los cortes prerregistrados el de 12 semanas cae a q 0,61 (ρ −0,16). La etiqueta `funding_validado` del EUR se apoya en el de 4 semanas.
7. **Etiquetas de evidencia en el config.** `funding_validado` (EUR BC), `frecuencia_de_era` (CAD, GBP, CHF, NZD, USD, EUR Tesoro), `provisional_era_corta` (AUD, JPY: sólo acuerdo hasta 150 semanas, 76 y 48 semanas por delante), `banda_por_diseño` (Tesoro GBP / CHF / NZD). Se ven en la tarjeta de los tres regímenes de cada dashboard, junto a los cortes y al estado de persistencia (lectura bruta, candidato pendiente, media efectiva).

## Lo que cambia hoy en vivo (regresión offline con los configs v0.3)

El compuesto de 4 bloques no cambia (CAD −0,137 · GBP 0,4 · AUD 0,391 · JPY 0,485 · CHF 0,425 · NZD 0,3 · USD 0,545 · EUR 0,397) porque los fixtures offline son cortos y el anclaje no llega a morder. Los regímenes de bloque sí, porque los cortes ya no son ±0,5:

| divisa | BC (score → régimen v0.3) | Tesoro | general |
|---|---|---|---|
| CAD | −1,00 → DRAIN | +2,00 → INJECTION | FLOOR_FRICTION (puerta de precio, como antes); sin puerta sería NEUTRAL por conflicto |
| GBP | +0,50 → INJECTION | 0,00 → NEUTRAL | NEUTRAL (parcial) |
| AUD | +0,67 → NEUTRAL | −0,26 → NEUTRAL | NEUTRAL |
| JPY | +0,50 → NEUTRAL | +0,24 → INJECTION | NEUTRAL (parcial) |
| CHF | 0,00 → NEUTRAL | +0,50 → INJECTION | NEUTRAL (parcial) |
| NZD | 0,00 → NEUTRAL | +0,50 → INJECTION | NEUTRAL (parcial) |
| USD | −0,70 → DRAIN | +1,00 → NEUTRAL (ritmo dentro de banda) | NEUTRAL (parcial) |
| EUR | +0,40 → INJECTION (p80 de la era es +0,02: el BC del EUR vive en negativo bajo QT) | +0,18 → NEUTRAL | NEUTRAL (parcial) |

Nota de lectura: un BC del EUR en +0,40 es INJECTION *relativo a su era* (percentil > 80), no una inyección en términos absolutos; la tarjeta muestra los cortes para que nadie lo lea como lo segundo. Al primer run en vivo el estado de persistencia parte de cero (una semana de prints diarios hasta que la media efectiva sea de 7 días).

## Ficheros

`ingest/engine.py` (máquina de estados `block_regime_step`, regla de acuerdo, etiquetas) · `ingest/thresholds.py` (anclaje a la era) · `ingest/scoring.py` (nuevo: componentes de flujo/nivel) · `ingest/blocks*.py` (los 16 bloques BC/Tesoro publican componentes; aritmética idéntica con peso 1,0) · `ingest/run.py` (lee `regime.dual.era_start` / `level_weight`) · `ingest/calibrate.py` (`--v03`, `--fdr-v03`, `--cache`, verdades alternativas) · `ingest/apply_v03.py` (escribe el parche en `config/<ccy>.json` y guarda el bloque v0.2 en `regime.dual_v02`) · `config/*.json` (regime.dual v0.3) · `*/index.html` (tarjeta de los tres regímenes) · `calibration/<ccy>_v03/` (scores, informe, calibration.json con `v03`, `v03_regimes.csv`) · `calibration/B_fdr_v03.{md,json}`.
