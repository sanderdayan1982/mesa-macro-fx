# Mesa Macro FX — Fase 1: Desk Standard + CAD Source Map

Versión 0.3 · 2026-09-08 · Estado: POST-TRIANGULACIÓN, PENDIENTE DE APROBACIÓN FINAL (no hay código todavía) · incorpora la auditoría del v2.0 y el consenso de 4 revisores externos (ver `TRIANGULACION_CAD_matriz.md`)

Este documento fija (1) el molde común de cada dashboard de moneda extraído de los tres paneles USD en producción, (2) el mapa de fuentes verificado para CAD (dólar canadiense) contra el Valet API del Bank of Canada, y (3) las decisiones de arquitectura que quedan congeladas antes de escribir la ingesta. Está pensado para pegarse tal cual en otra AI si se quiere triangular.

Siglas usadas: MMT (Modern Monetary Theory), FX (Foreign Exchange), BoC (Bank of Canada), GoC (Government of Canada), CORRA (Canadian Overnight Repo Rate Average), SOFR (Secured Overnight Financing Rate), IORB (Interest on Reserve Balances), TGA (Treasury General Account), RRP (Reverse Repo Facility), WALCL (Fed total assets, FRED ID), FRED (Federal Reserve Economic Data), DTS (Daily Treasury Statement), QT/QE (Quantitative Tightening / Easing), SPRA (Securities Purchased under Resale Agreements), SRA (Securities sold under Repurchase Agreements), SLF (Standing Liquidity Facility), NFA (Net Financial Assets), WAT (West Africa Time, UTC+1), ET (Eastern Time), API (Application Programming Interface), JSON (JavaScript Object Notation), CSV (Comma-Separated Values), pb (puntos básicos).

---

## 1. Desk Standard — el molde común (extraído de USD)

### 1.1 Las tres capas y su origen en los paneles USD

| Capa | Panel USD de origen | Pregunta que responde |
|---|---|---|
| A · Central Bank | H.4.1 Command Center | ¿El banco central inyecta o drena? ¿Hay escasez de reservas? |
| B · Treasury / Fiscal | DTS Tracker | ¿El gobierno crea o destruye NFA? ¿Cuál es el impacto en reservas de la cuenta del Tesoro? |
| C · Banking Transmission + Rates | H.8 / H.15 Monitor | ¿La liquidez llega a la economía real (crédito, depósitos) o se queda en el interbancario? ¿Qué dice la curva? |

### 1.2 Geometría fija de cada tab de moneda (12 bloques, brief sin Technical)

1. Executive Header — semáforo maestro de la moneda, régimen de liquidez, fecha del último dato, próximas publicaciones.
2. Release Calendar — banco central, tesoro/equivalente, series bancarias; hora oficial y hora WAT.
3. Central Bank Block (Capa A).
4. Treasury / Fiscal Equivalent Block (Capa B).
5. Banking Transmission Block (Capa C-1).
6. Rates / Money Market Block (Capa C-2).
7. Regime / Confluence Block — combina A+B+C en un régimen único y un score de confluencia.
8. Alerts Panel — tabla de umbrales con estado actual.
9. Agent Narrative — texto generado por el Currency Agent (JSON de narrativa).
10. Operator Takeaway — tres líneas máximo, en vocabulario MMT/Mosler.
11. Data Quality / Source Health — estado por serie: fresh / stale / proxy / degraded / unavailable.
12. Historical Record — tabla semanal + log de señales.

### 1.3 Métricas canónicas por bloque (fórmulas heredadas de USD)

**Central Bank Block**
- Net Liquidity = Total assets − Government deposits at central bank − Reverse-repo-type liabilities. (USD: WALCL − WTREGEN − RRPONTTLD.) El efectivo en circulación NO se resta (outside money; tampoco lo resta la fórmula USD): se muestra como línea propia "Currency drain" (drenaje autónomo) para mantener comparabilidad entre monedas.
- Reserves = saldos de liquidación de los bancos en el banco central. (USD: WRESBAL.)
- Weekly Net Liquidity Δ% — con umbrales Risk-On / Risk-Off. (USD: ≥ +2 % / ≤ −2 %.)
- QT/QE tracker por componente de activo: bonos soberanos, letras, hipotecarios/otros, repos de liquidez.
- Stress monitor: préstamos de emergencia del banco central. (USD: Primary Credit, +20 % semanal = crisis.)
- Drains tracker: cuenta del gobierno + reverse repo apilados.
- Overnight − deposit-rate spread (USD: SOFR − IORB; el análogo es el tipo pagado por las reservas, el suelo del corredor, no el objetivo de política) con velocímetro, posición en la banda operativa (0 = suelo, 1 = techo) y tabla de historial. Overnight − target queda como métrica secundaria.
- Alerts & Limits table, Forex Signal Matrix, Publication Schedule, Legend.

**Treasury / Fiscal Block** (campos obligatorios del brief)
- Net spending / Fiscal flow: Net Treasury Flow = (Withdrawals − Debt redemptions) − (Deposits − Debt issues), Mosler-style; positivo = inyección neta de NFA. Donde no exista un DTS, el proxy es −Δ(Government account at central bank), con estado `proxy`.
- Reserve impact = −ΔGovernment account.
- Z-score (30 días hábiles o 26 semanas según frecuencia), media y desviación rodantes, acumulado 7 días.
- Fiscal stress, Fiscal regime (injection / drain / neutral), Fiscal regime score, Fiscal confluence score frente al resto del tab.
- Next fiscal release, equivalence quality, historical record con sparkline, high/low y percentil.

**Banking Transmission Block**
- Bank credit, loans, business loans, deposits, borrowings (wholesale/central bank).
- Semáforo: verde = crédito ↑, depósitos ↑, borrowings estables; rojo = préstamos ↓, depósitos ↓, borrowings ↑.
- Heatmap de cambios con Z-score rodante de 26 periodos, sin lookahead (regla heredada de H.8 v2.1).
- Índice base 100 combinado (loans / deposits / borrowings).
- Regla de cobertura: con menos de 3 series válidas la señal se suprime (NO SIGNAL), nunca se computa con ceros fantasma.

**Rates / Money Market Block**
- Policy rate, overnight market rate, 3M bill, 2Y, 10Y.
- Spreads: 10Y − 2Y (inversión), Policy − 3M (mercado descuenta recortes si > 0), Overnight − Deposit rate (estrés de reservas, primario), Overnight − Policy (secundario), dispersión intradía del overnight (p95 − p5) como estrés interbancario.
- Regla heredada de H.15 v2.1: los spreads se calculan sobre la última fecha común de ambas series, nunca last(A) − last(B).

### 1.4 Framework de umbrales

Los umbrales USD son absolutos y calibrados a mano (3.0T / 2.5T, 15 / 30 pb, 200B). No son trasladables. Regla del Desk Standard:

- Umbral primario: **percentil rodante distribution-free** sobre el histórico propio de cada serie. Ventana: 3 años (≈156 semanas o ≈750 días hábiles). Niveles: WATCH ≥ p80, STRESS ≥ p90, CRISIS ≥ p97 (y simétricos a la baja para series donde "bajo" es el riesgo, como reservas).
- Histéresis Schmitt: se entra en un nivel al cruzar su percentil y se sale sólo al cruzar el percentil del nivel inferior (p80 → sale en p70; p90 → sale en p80; p97 → sale en p90). Evita parpadeo semanal.
- Umbral absoluto **primario** cuando exista doctrina pública del banco central para una serie de nivel (ejemplo CAD: rango objetivo de saldos de liquidación 50–70B, Gravelle 2025-01-16); en esos casos el percentil pasa a secundario, porque los niveles de balance cruzan regímenes de política (QE → QT → normalización) y un percentil rodante los lee mal. Los percentiles mandan en flujos (Δ %, spreads).
- Umbrales binarios absolutos siempre: préstamos de emergencia > 0; overnight por encima del techo del corredor.
- Todo umbral vive en `config/{ccy}.json`, nunca en el HTML. Cambiarlo exige commit, y el commit es la traza metodológica.

### 1.5 Taxonomía de estados (aplica a cada serie y a cada bloque)

| Estado | Definición |
|---|---|
| fresh | Última observación dentro de 1.5 × su frecuencia nominal |
| stale | Entre 1.5 × y 3 × su frecuencia nominal |
| proxy | La métrica no es nativa; se calcula con un equivalente documentado (`equivalence_note`) |
| degraded | La fuente respondió pero con huecos, valores vacíos o cobertura < 3 series en un bloque |
| unavailable | Sin fuente o fuente caída en el último refresco; se muestra la tarjeta con "—", nunca se oculta |

### 1.6 Régimen y confluencia

Cada bloque emite un score en [−2, +2]: −2 drenaje/estrés extremo, 0 neutral, +2 inyección amplia. El Regime Block combina con pesos definidos en config y produce: `LIQUIDITY_INJECTION`, `LIQUIDITY_DRAIN`, `LIQUIDITY_SCARCITY` (reservas por debajo del rango + spread overnight−deposit en estrés), `FLOOR_FRICTION` (reservas dentro del rango pero overnight por encima del objetivo: fricción de distribución, no escasez agregada), `NEUTRAL`. Flags ortogonales, no regímenes: `TRANSMISSION_FAILURE` (crédito contrayéndose con reservas amplias) y `BALANCE_SHEET_PHASE` (QE / QT / NORMALIZATION / STEADY). Pesos v0.3: banco central 0.45, tipos 0.25, fiscal 0.20, transmisión 0.10. La lectura FX de "se fortalece / se debilita" no sale de un tab: sale del Desk, cruzando dos monedas.

---

## 2. CAD Source Map — verificado contra el Valet API (2026-09-08)

Fuente única para las tres capas: `https://www.bankofcanada.ca/valet` · JSON/CSV · sin clave · sin coste.
Endpoints: `/observations/{series}/json?recent=N` · `?start_date=YYYY-MM-DD` · `/groups/{group}/json` · `/observations/group/{group}/json`.

### 2.1 Capa A — Central Bank (grupo `B2_WEEKLY`, miércoles, millones de CAD)

| Métrica canónica | Serie Valet | Etiqueta oficial | Último dato verificado |
|---|---|---|---|
| Total assets (≈ WALCL) | V36610 | Total assets | 2026-09-02 · 223 219 |
| Reserves (≈ WRESBAL) | V36636 | Members of Payments Canada (settlement balances) | 2026-09-02 · 64 324 |
| Government account (≈ TGA) | V36628 | Government of Canada deposits | 2026-09-02 · 24 810 |
| Reverse-repo-type liability (≈ RRP) | V1203435186 | Securities sold under repurchase agreements | — (habitualmente 0) |
| Sovereign bonds (≈ TREAST) | V36613 | Government of Canada Bonds | 2026-09-02 · 136 660 |
| Bills | V36612 | Treasury Bills | 2026-09-02 · 3 538 |
| Mortgage-type (≈ MBST) | V1038114416 | Canada Mortgage Bonds | — |
| Liquidity repos (term repo / SPRA) | V44201362 | Securities purchased under resale agreements | 2026-09-02 · 46 530 |
| Emergency lending (≈ Primary Credit) | V36634 | Advances (SLF) | 2026-09-02 · 0 |
| Notes in circulation | V36625 | Notes in circulation | — |

Fórmula CAD: **Net Liquidity = V36610 − V36628 − V1203435186**. Reserves = V36636 directamente.
Histórico disponible desde 2000-01-05 (V36636, V36628) y 2007-10-03 (V44201362): suficiente para percentiles de 3 años y para backfill completo.
Nota doctrinal (verificada): el BoC opera un sistema de suelo y declaró el 2025-01-16 (Gravelle) un rango objetivo de saldos de liquidación de **50 000–70 000 millones** (20–30B por necesidades de pagos + demanda precautoria). Ese rango es el **umbral absoluto primario** de reservas. Post-QT el BoC compensa el crecimiento del efectivo con term repo 1M/3M quincenal, letras desde Q4 2025 y bonos hacia finales de 2026 ("no será QE"): por eso la línea V44201362 es hoy mayoritariamente term repo estructural, y el detalle overnight/term sale de los grupos Valet OR_RESULTS / ORR en el carril de eventos.

### 2.2 Capa B — Treasury / Fiscal Equivalent (revisada tras triangulación)

Hallazgo de la ronda de triangulación, verificado el 2026-09-08: el **Receiver General (Public Services and Procurement Canada) publica un "Daily Cash Balance"** en el Open Government Portal — CSV diario con el saldo de cierre de la cuenta del gobierno en el BoC, los term deposits colocados en instituciones financieras y el fondo de liquidez prudencial. Última fila disponible 2026-09-01 (≈ una semana de retraso). No es un DTS con ingresos y pagos desglosados, pero sí es el análogo diario del saldo de cierre del TGA, y cambia la capa fiscal CAD de semanal a diaria.

| Campo | Fuente | Serie / columna | Frecuencia | Estado esperado |
|---|---|---|---|---|
| Government account at central bank (diario) | Receiver General Daily Cash Balance (CSV) | Closing-Cash-Balance-Amount | diaria, lote ~semanal | fresh / stale |
| RG term deposits en bancos | idem | Term-Deposit-Outstanding-Amount | diaria | fresh / stale |
| Government account (semanal, contraste) | Valet B2 | V36628 | semanal | fresh |
| Reserve impact = −Δ saldo de cierre | derivada | — | diaria | proxy |
| Fiscal flow proxy = −Δ(saldo BoC + term deposits) | derivada | — | diaria | proxy |
| Z-score 30 días hábiles, acumulado 7 días | derivadas | — | diaria | proxy |
| Issuance & redemptions | Valet auctions (`AUC_TBILL_RESULTS`, subastas de bonos) | por subasta | evento | pending |
| Net spending / déficit | Fiscal Monitor (Department of Finance) | sin API, mensual | mensual | pending |

Lectura MMT del bloque (consenso de la triangulación): el gasto crea NFA; los impuestos los destruyen; **la emisión de deuda drena reservas pero no cambia el stock de NFA** (swap de composición). Por eso el bloque lleva dos líneas separadas: impacto en reservas (−Δ saldo en BoC) y flujo fiscal neto (−Δ caja total del gobierno, que excluye los traspasos BoC ↔ bancos vía term deposits). `equivalence_quality` del bloque = **medium-high**. Datasets relacionados a verificar: "Deposits at Financial Institutions", "Consolidated Revenue Fund Term Deposits", "Government of Canada — Domestic Payments" (mismo portal).

### 2.3 Capa C-1 — Banking Transmission

Hallazgo importante: las series de crédito agregado (`E2_MONTHLY`, Total business credit V105926371, Total household & business credit V122644) **terminan en 2020-09 en Valet**; el BoC trasladó esas medidas a Statistics Canada. Por tanto:

| Métrica canónica | Serie Valet | Etiqueta | Último dato | Estado |
|---|---|---|---|---|
| Bank assets (≈ Bank Credit) | V36852 | Total Canadian dollar assets (C1) | 2026-06-01 | stale por diseño (mensual, ~3 meses) |
| Deposits | V41552773 | Total deposits held by general public (C2) | 2026-06-01 | idem |
| Government deposits at banks | V36811 | Government of Canada deposits (C2) | 2026-06-01 | idem |
| Borrowings (interbancario) | V36875 | Deposits of banks (C2) | 2026-06-01 | idem |
| Banks' reserves on their own books | V36691 | Bank of Canada deposits (C1) | — | idem |
| Business loans / consumer credit | Statistics Canada (tabla de crédito de la Banking and Financial Statistics) | a verificar en ingesta | mensual | pending |

Decisión: el bloque C-1 de CAD nace con `equivalence_quality = medium-low` y frecuencia mensual. Se mantiene visible con estado `stale`/`proxy`, nunca se elimina (regla del brief). Las series de Statistics Canada se verifican en la Fase 3 de ingesta; el config las declara como `pending` con el campo de fuente vacío.

### 2.4 Capa C-2 — Rates / Money Market (diarios)

| Métrica canónica | Serie Valet | Etiqueta | Último dato verificado |
|---|---|---|---|
| Policy rate (≈ IORB / FF target) | V39079 | Target for the overnight rate | 2026-09-04 · 2.25 % |
| Overnight market rate (≈ SOFR) | AVG.INTWO | CORRA | 2026-09-03 · 2.30 % |
| 3M bill | TB.CDN.90D.MID | Treasury bills: 3 month | 2026-09-04 · 2.28 % |
| 2Y | BD.CDN.2YR.DQ.YLD | Benchmark bond yield: 2 year | 2026-09-03 · 3.10 % |
| 10Y | BD.CDN.10YR.DQ.YLD | Benchmark bond yield: 10 year | 2026-09-03 · 3.79 % |
| CORRA volumen / percentiles | CORRA_TRIMMED_VOLUME, CORRA_RATE_AT_PERCENTILE_95 | métricas de transparencia CORRA | diario |

Spreads CAD: **CORRA − Deposit rate** (deposit rate = target − 5 pb desde 2025-01-30, notice BoC 2025-01-29; hoy +10 pb, posición en banda 0.33), **CORRA − Target** secundario (+5 pb), **Target − 3M bill** (−3 pb), **10Y − 2Y** (+69 pb, curva positiva), dispersión CORRA p95 − p5. Banda operativa vigente: [target − 5, target + 25]. CORRA histórico desde 1997-08-12.

### 2.5 Calendario de publicación CAD (a confirmar hora exacta en ingesta)

| Serie | Publicación oficial | Hora ET | Hora WAT (verano / invierno) |
|---|---|---|---|
| B2 balance semanal | viernes, datos del miércoles | 14:30 | 19:30 / 20:30 |
| CORRA | siguiente día hábil | ~09:00 | 14:00 / 15:00 |
| Bond yields, T-bills | diario, cierre | ~16:00 | 21:00 / 22:00 |
| Target rate (decisiones) | 8 fechas/año | 09:45 | 14:45 / 15:45 |
| C1/C2 mensual | ~6-8 semanas tras fin de mes | — | — |
| Fiscal Monitor | mensual, ~2 meses de retraso | — | — |

---

## 3. Decisiones de arquitectura congeladas

1. **Ingesta en GitHub Actions** (Python 3, `requests` + `pandas`), un workflow por carril: `weekly-cad.yml` (viernes 20:00 WAT), `daily-cad.yml` (lunes-viernes 22:30 WAT), `event-cad.yml` (fechas de decisión del BoC). Cada run escribe `data/cad/*.json` y hace commit; Netlify despliega solo.
2. **El frontend no hace fetch a fuentes**: sólo lee `data/cad/*.json` y `agents/cad.json`. El proxy FRED actual deja de ser necesario para las monedas nuevas.
3. **Un HTML motor** (`desk-engine.html` + `engine.js`) y un config por moneda. El tab CAD se sirve en su propia URL (`/cad/`), como pediste: dashboards separados por fuera, motor común por dentro.
4. **Backfill inicial** de 3 años mínimo por serie en el primer run, para que los percentiles existan desde el día uno.
5. **Agentes** (Fase 4): Currency Agent CAD lee `data/cad/*.json` y escribe `agents/cad.json`; se ejecuta al final del workflow semanal y del diario, no cada 30 minutos.
6. **Manual**: aprobación de fases, cambios de umbrales o fórmulas (commit explícito al config), decisión de trade.

## 4. Riesgos específicos CAD

- Crédito bancario mensual y con retraso: el bloque de transmisión será el más lento de los tres. Aceptado y visible como `stale`.
- Series E2 discontinuadas en Valet: hay que localizar las tablas de Statistics Canada. Riesgo bajo de existencia, medio de formato.
- Fiscal Monitor sin API: se pospone; el bloque fiscal arranca con −ΔV36628 + subastas.
- Etiquetas anidadas en C1 ("Total" aparece varias veces): la ingesta debe validar cada ID contra su valor esperado la primera vez y dejarlo fijado en el config.
- Horario de publicación del B2: verificar en el primer run que el dato del miércoles está disponible el viernes por la tarde ET antes de fijar el cron.

## 4b. Herencia del Canada Command Center v2.0 (auditoría de `lib/`)

Revisados los once módulos de `netlify/functions/lib/` más el frontend y los cuatro refresh. Veredicto módulo a módulo:

| Módulo v2.0 | Destino en el nuevo motor | Motivo |
|---|---|---|
| `sources.mjs` | **Portar** a `ingest/sources_cad.py` | Mapa Valet correcto y ya probado; aporta V39078 (Bank Rate), 5Y, CORRA volumen, FXUSDCAD (USD/CAD oficial del BoC, sustituye a Yahoo para el Desk) y los tres RSS oficiales del BoC. Se elimina Yahoo. `recent=104` pasa a backfill completo. |
| `quality.mjs` + `holidays.mjs` | **Portar** íntegro a `ingest/quality.py` | Dedup, outliers por Z modificado con MAD y ventana 20, rachas de nulos excluyendo fines de semana y festivos, confianza 0–100 con penalizaciones explícitas. Es mejor que lo que tienen los paneles USD y pasa al Desk Standard para las ocho monedas. Única corrección: un nulo nunca es "amber"; es `unavailable` y suprime la señal del bloque. |
| `revisions.mjs` | **Portar** a `ingest/revisions.py` | Detecta revisiones retroactivas del BoC. En git el "previo" es el último JSON commiteado, sin blob. |
| `alerts.mjs` | **Portar** el mecanismo (activa → resuelta, histórico 100) | Las reglas se reescriben sobre niveles de percentil y viven en `config/cad.json → alerts`. |
| `regime.mjs` | **Portar** changelog y heatmap semanal de 52 semanas; **sustituir** la clasificación | Contar verdes entre siete semáforos que mezclan liquidez con precios (USD/CAD, WTI, DXY) contamina la lectura MMT. El régimen nuevo pondera bloques (A 0.4 / B 0.3 / C 0.3) y añade `LIQUIDITY_SCARCITY`. |
| `scenarios.mjs` | **Portar** el motor (condiciones, mínimo N cumplidas); **reescribir** la lista | Se conservan como escenarios de liquidez L1–L6 (tightening, silent fiscal easing, QT drag, funding stress, curve normalization, transmission break). External Pressure, Risk-On Reflation y Stagflation pasan al Desk Cross-Market porque son de precio. |
| `derive.mjs` | **Portar** helpers (`pct_series`, `merge_series` en fecha común, `change_series`) | Misma regla de fecha común que el H.15 v2.1. |
| `thresholds.mjs` | **Sustituir** por `config/cad.json` | Umbrales absolutos duplicados en backend y frontend; pasan a percentiles con los absolutos del v2.0 conservados como `secondary_absolute` (50B/40B reservas, 0/+5 pb CORRA, ±2 % activos, −1 % bonos, ±5 % repos, +1 % billetes). |
| `oplog.mjs` | **Portar** a `logs/cad/oplog.json` commiteado | Log de operador con versión de metodología por entrada. |
| `store.mjs` (Netlify Blobs) | **Eliminar** | Sustituido por git: cada refresco es un commit y el historial es la auditoría. |
| `refresh-fast/daily/weekly/monthly.mjs` | **Sustituir** por tres workflows de GitHub Actions | El fast lane de 4 h descargaba todo cada vez; ahora cada carril baja sólo sus bloques. |
| Frontend `index.html` | **Base del motor HTML** | Se conserva el esqueleto (header con pill de régimen y confianza, tabs, cards, badges, heatmap, calendario, SYSTEM con alerts/oplog/quality/methodology/revisions, export JSON, gráficos SVG sin dependencias) y se reorganiza a los 12 bloques. MARKET y CROSS-MKT salen del tab CAD. La carga pasa de `/.netlify/functions/api-data` a `data/cad/*.json`. |

Fechas 2026 del BoC (decisiones, MPR, festivos CA/US) rescatadas de `holidays.mjs` al config; pendiente añadir 2027 cuando el BoC publique su calendario.

## 5. Ficheros adjuntos a este documento

- `config/cad.json` — configuración completa de la moneda (series, equivalencias, umbrales, calendario, pesos de régimen).
- `schema/block.schema.json` — esquema de cada fichero `data/{ccy}/{block}.json` que produce la ingesta y consume el motor y los agentes.

## 6. Qué se aprueba con este documento

Al aprobar la Fase 1 quedan congelados: la geometría de 12 bloques, las fórmulas canónicas, el framework de percentiles con histéresis, la taxonomía de estados, el esquema JSON y el mapa de fuentes CAD. La Fase 2 (ingesta CAD en GitHub Actions + motor HTML) sólo arranca tras tu OK, y cualquier cambio posterior a estos puntos se hace por commit al config, no por edición del HTML.
