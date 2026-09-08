# FASE 1 — JPY COMMAND CENTER · Mapa de fuentes y auditoría (v0.1, borrador para triangulación)

Fecha: 2026-09-08. Hereda el Desk Standard v0.3 (CAD), las mecánicas repo-led de GBP v0.2 y el bloque diario de reservas de AUD v0.2.2. Todas las fuentes, códigos, precios y fechas de este documento se verificaron HOY en vivo con el navegador integrado (el sandbox no alcanza boj.or.jp, stat-search.boj.or.jp ni mof.go.jp). Lo que no pude verificar está marcado como **pendiente**; nada pendiente entra en `config/jpy.json` como hecho.

Glosario: BoJ (Bank of Japan), MoF (Ministry of Finance, Japón), MPM (Monetary Policy Meeting, reunión de política monetaria del BoJ), CAB (Current Account Balances, saldos en cuenta corriente en el BoJ = reservas), IOER (Interest On Excess Reserves, aquí el tipo de la Complementary Deposit Facility), CLF (Complementary Lending Facility, ventanilla de préstamo del BoJ al basic loan rate), TONA (Tokyo OverNight Average, tipo medio del call no colateralizado a un día), JGB (Japanese Government Bond), T-Bill/TDB (Treasury Discount Bill), SLF (Securities Lending Facility, préstamo de JGB por el BoJ como fuente secundaria), QT (Quantitative Tightening, reducción del balance), DTS (Daily Treasury Statement, el estado diario del Tesoro de EE. UU. que usamos como analogía), TGA (Treasury General Account), XLSX (hoja de cálculo Excel), API (Application Programming Interface), CSV (Comma-Separated Values), JST (Japan Standard Time, UTC+9), UTC (Coordinated Universal Time).

## 1. Auditoría del JPY Liquidity Command Center v5 (Netlify Function + FRED + seeds)

**Lo que había**
- Backend `fetch-data.mjs`: FRED mensual (base monetaria BOGMBASEJPM163N, call rate IRSTCB01JPM156N, JGB 10Y IRLTLT01JPM156N, USD/JPY DEXJPUS, CPI, exportaciones/importaciones, M2, tipo de descuento, reservas de divisas), frankfurter para EUR/JPY, Yahoo para el Nikkei.
- Todo lo que de verdad importa para una mesa de liquidez era **SEED (aleatorio determinista)**: balance del BoJ, CAB, depósitos del Gobierno, TONAR, TIBOR, toda la curva JGB salvo el 10Y, series fiscales y de flujos. El README lo decía honestamente ("pendiente BOJ API / MOF API").
- Frontend: 7 pestañas (incluidas FX, renta variable y flujos), composite "Net Liquidity = Assets − GovDep − ReqRes" calculado sobre seeds, auto-refresh cada 300 s de datos mensuales.

**Diagnóstico**
- Un dashboard con el 80 % de las métricas simuladas no es un dashboard: era una maqueta de interfaz. No hay nada que migrar en datos; la arquitectura (función Netlify con llamadas en paralelo y sin histórico en git) es la que ya abandonamos en CAD/GBP/AUD.
- Las series FRED reales eran mensuales y con 1–2 meses de retraso, así que ni siquiera la parte viva servía para operar.

**Se rescata (ideas, no código)**
- La intuición del composite "activos del BoJ − depósitos del Gobierno": ahora se calcula con datos reales del BoJ cada 10 días.
- La lista de métricas deseadas (CAB, exceso de reservas, TONA, tipos a plazo, curva JGB por tramos, factores fiscales): todas existen en fuentes primarias y **diarias**, ver abajo.
- Badge de procedencia por métrica (LIVE/SEED) → en el Desk Standard es el estado fresh/stale/proxy/degraded/unavailable.

**Se descarta**: FRED como fuente JPY (no hace falta), Yahoo/frankfurter, pestañas de equity/flujos (fuera del alcance de liquidez), seeds, auto-refresh de 5 minutos.

## 2. Lo que hace especial al JPY: reservas Y fiscal DIARIOS, con calendario de publicación fijo

El BoJ publica cada día hábil "Sources of Changes in Current Account Balances at the Bank of Japan and Market Operations": un DTS + H.4.1 diario en un solo fichero. Contiene el factor billetes, el factor **fondos del Tesoro** (= flujo fiscal neto del día, la analogía más limpia del DTS fuera de EE. UU.), las operaciones del BoJ por tipo, la variación de CAB, el CAB total, las reservas, el **exceso de reservas**, la base monetaria y las reservas requeridas del periodo. Tres versiones por día: proyección (día siguiente, ~18:00 JST), provisional (mismo día, ~18:00 JST) y **final (día anterior, ~10:00 JST)**.

Aviso importante descubierto hoy: la página antigua `www3.boj.or.jp/market/en/menu.htm` (la que citan todas las IAs y todos los scripts viejos) está **suspendida desde el 6 de octubre de 2025**. Los datos viven ahora en `https://www.boj.or.jp/en/statistics/boj/fm/juq/index.htm` como XLSX con URL determinista. Cualquier revisor que proponga la URL antigua está desactualizado.

Segundo descubrimiento: el BoJ tiene una **API oficial** en el Time-Series Data Search (`https://www.stat-search.boj.or.jp/api/v1/getDataCode?db=<DB>&code=<códigos>&format=json&lang=EN&startDate=YYYYMM&endDate=YYYYMM`, más `getMetadata?db=<DB>` y `getDataLayer`). Probada hoy con FM01 (TONA) y metadatos de MD06/MD01/MD02/MD08/MD13/FM02: JSON limpio con `SURVEY_DATES` y `VALUES`. Hasta 250 códigos por petición. Cubre lo mensual (money stock, préstamos, base monetaria, CAB por sector) y TONA diario; NO cubre el diario de CAB (MD06 en la API es solo mensual), para eso están los XLSX diarios.

## 3. Capa A — Banco central (BoJ)

### 3.1 Diario: XLSX "Sources of Changes in CAB and Market Operations" (verificado 2026-09-07 final)
URL final: `https://www.boj.or.jp/en/statistics/boj/fm/juq/d_release/jd/YYYY/jdYYYYMMDD.xlsx` · provisional: `.../d_release/jx/jxYYYYMMDD.xlsx` · proyección: `.../d_release/jp/jpYYYYMMDD.xlsx`. Índice anual para backfill: `.../d_release/jd/2026/index.htm` (2025 desde octubre en `jd/2025/`; anteriores en HTML en www3). Unidad: 100 millones de yenes, redondeado a 10 000 millones. Una sola hoja, etiquetas en B/C/D/E, valores en F (proyección) / G (provisional) / H (final). Se parsea por texto de etiqueta, no por número de fila (el BoJ cambia ítems: avisos 2025-10-31, 2026-01-27, 2026-06-30).

| Ítem (etiqueta inglesa en la hoja) | Valor 2026-09-07 final (100 m ¥) | Uso |
|---|---|---|
| Banknotes (Minus: net issuance) | +600 | factor billetes |
| Treasury funds and others (Minus: net receipt) | +3 300 | **flujo fiscal diario** (Capa B) |
| Surplus/Shortage of funds | +3 900 | autónomo neto |
| BOJ Loans and Market Operations (excl. Loan Support Program) subtotal | −1 000 | operaciones del día |
| · Outright purchases of JGBs | (vacío = 0 ese día) | compras QE/QT |
| · Outright purchases of Corporate Bonds | −100 | |
| · Loans (= Complementary Lending Facility) | (vacío = 0) | **uso de ventanilla = flag** |
| · Securities lending as a secondary source of JGSs | +300 / −1 200 | tensión de colateral JGB |
| Net change in current account balances | +2 900 | ΔCAB |
| Current account balances (amount outstanding) | 4 161 200 (= ¥416,1 bn) | **reservas** |
| Reserve balances held by institutions subject to reserve requirements | 3 844 200 | |
| Excess reserves | 3 844 200 | **exceso de reservas** (nota: iguala reserve balances porque el requerido ya está cubierto en el periodo) |
| CAB held by institutions NOT subject to reserve requirements | 317 000 | tanshi, securities cos., etc. — no cobran IOER: explica TONA < IOER |
| Monetary base | 5 353 400 | solo en el fichero final |
| Required reserves, current maintenance period (Aug.16–Sep.15), daily average | 134 800 (= ¥13,48 bn) | denominador de ampleness |
| Remaining required reserves on and after Sep.8 (daily average) | 0 | |

Periodo de mantenimiento de reservas: del 16 al 15 del mes siguiente; el requerido se revisa el día 7.

### 3.2 Cada 10 días: BoJ Accounts (HTML, verificado 2026-08-31, publicado 2026-09-02)
URL: `https://www.boj.or.jp/en/statistics/boj/other/acmai/release/YYYY/acYYMMDD.htm` (índice en `.../acmai/index.htm`, fechas 10/20/fin de mes, publicación 2–3 días hábiles después). Unidad: miles de yenes.

| Partida | 2026-08-31 (bn ¥) | Analogía USD |
|---|---|---|
| Japanese government securities (JGBs; T-Bills = 0) | 519,93 | SOMA |
| Loans (excl. DIC) | 71,86 | — (de los cuales Loan Support Program 39,11; pooled-collateral + disaster + climate 32,75) |
| Foreign currency assets | 11,97 | |
| Total assets | 644,66 | WALCL |
| Banknotes | 114,87 | currency in circulation |
| Current deposits | 424,32 | WRESBAL (media/fin de periodo; el diario es la fuente primaria) |
| Deposits of the government | 9,26 | TGA (pequeño: el Tesoro japonés opera con saldo bajo y se financia con T-Bills) |
| Payables under repurchase agreements | 37,43 | |

Además: "Japanese Government Bonds Held by the Bank of Japan" (XLSX cada 10 días, emisión por emisión) para Fase 3.

### 3.3 Corredor y anclas de política (verificado en primarias)
- MPM 2026-06-16 (efectivo 2026-06-17): tipo objetivo del call no colateralizado O/N **"around 1.0 %"**; Complementary Deposit Facility (IOER) **1.0 %**; basic loan rate (CLF, techo) **1.25 %**. Votación 7–1. Reafirmado en la MPM 2026-07-31 (8–1, el disidente pedía 1.25 %).
- Serie histórica del basic loan rate en CSV: `https://www.boj.or.jp/en/statistics/boj/other/discount/cdab0101.csv` (2024-08-01 0.5 · 2025-01-27 0.75 · 2025-12-22 1.0 · 2026-06-17 1.25). Regla verificada en los 4 últimos movimientos: **policy rate = basic loan rate − 0.25**; sirve para que el pipeline detecte subidas sin leer PDF.
- Plan de compras de JGB (MPM 2026-06-16): compras mensuales ~¥2,7 bn (abr–jun 2026), **~¥2,5 bn (jul–sep 2026)**, ~¥2,3 bn (oct–dic 2026), ~¥2,1 bn (ene–mar 2027), ~¥2,0 bn desde abril 2027; sin revisiones intermedias. Tenencias esperadas: ~¥480 bn a fin de marzo 2027 (−17 % vs junio 2024), ¥430–440 bn en marzo 2028, ¥390–400 bn en marzo 2029, ¥350–370 bn en marzo 2030. Ancla del ritmo de QT: tenencia real 519,93 bn (31-ago-2026) → 480 bn en 7 meses ≈ −¥5,7 bn/mes.
- Calendario MPM restante 2026: 17–18 sep, 29–30 oct (Outlook), 17–18 dic. 2027: 21–22 ene, 17–18 mar, 27–28 abr, 10–11 jun, 21–22 jul, 21–22 sep, 28–29 oct, 16–17 dic. Comunicado ~12:00 JST del segundo día.

### 3.4 Mensual por API (Time-Series Data Search)
- MD06 (desglose mensual de los factores): `MASDM@01` net fiscal payments, `MASDM253/254/255` JGB >1 año neto/emitidos/amortizados, `MASDM273/274/275` T-Bills, **`MASDM26` Foreign Exchange (aquí aparece la intervención cambiaria del MoF)**, `MASDM58` compras de JGB, `MASDM5F` pooled-collateral ops, `MASDM51` loans, `MASDM@03` ΔCAB, `MASDM@07` CAB outstanding, `MABCLE16` CLF outstanding.
- MD01 base monetaria (`MABS1AN11`, `MABS1AN113` CAB media, `MABS1AN114` reservas). MD08 CAB por sector (exceso de reservas de city banks `MACAB1013`, regionales `MACAB1023`, extranjeros `MACAB1043`, trust `MACAB1053`, total `MACAB1201`) — distribución de reservas = transmisión.

## 4. Capa B — Tesoro (MoF): fiscal DIARIO desde el BoJ + calendario de subastas del MoF

- **Serie primaria**: "Treasury funds and others" del XLSX diario (§3.1). Signo BoJ: menos = recepción neta (impuestos, emisión) = drenaje; más = pago neto (gasto, amortizaciones, cupones) = inyección. Se guarda con el signo del BoJ y `fiscal_flow_daily = valor` (positivo = inyección), como −ΔTGA en USD. Cobertura: 100 % de los días hábiles, T+1 a las 10:00 JST, con provisional el mismo día a las 18:00 JST y proyección del día siguiente. Es mejor que CAD (Receiver General semanal) y que GBP.
- Depósitos del Gobierno en el BoJ cada 10 días (§3.2): nivel pequeño (~¥9 bn) porque el MoF gestiona caja con T-Bills; se muestra, no manda.
- Desglose mensual MD06 (§3.4) para atribuir: pagos fiscales netos, JGB emitidos/amortizados, T-Bills, y **FX** (intervención).
- **Calendario de subastas del MoF** (HTML mensual, verificado sep-2026): `https://www.mof.go.jp/english/policy/jgbs/auction/calendar/YYMMe.htm` (p. ej. `2609e.htm`): 10Y 1-sep, 30Y 3-sep, TDB 3m 4-sep, 5Y 8-sep, TDB 6m 9-sep, liquidity enhancement 10-sep, 20Y 15-sep, TDB 1y 16-sep, 40Y 29-sep, 2Y 30-sep, más préstamos de cuentas especiales. Los resultados (bid-to-cover, tail) están en páginas "Detail" — parser Fase 3.
- Estacionalidad fiscal japonesa (impuestos de sociedades, pensiones el 15 de meses pares, amortizaciones/cupones JGB los días 20 de mar/jun/sep/dic, cierre fiscal 31-mar): **pendiente de verificar** contra el histórico diario de "Treasury funds"; no entra en el config como hecho, se aprende del propio dato.
- Estado mensual del MoF "Receipts and Payments of Treasury Funds": URL no localizada hoy en la web inglesa → **pendiente** (Fase 3, no bloquea).

## 5. Capa C-1 — Transmisión bancaria (mensual, API)

- MD13 "Principal Figures of Financial Institutions" (préstamos y depósitos, sale ~día 8): `FAAP@01` préstamos total major+regional+shinkin, `FAAPOBAL1` major+regional, `FAAPOBAL1@` variación interanual %, `FAAPOBAL11` major, `FAAPOBAL12` regionales, `FAAPOBRDCD5` depósitos+CDs total; último dato 2026-08.
- MD02 Money Stock (sale ~2.ª semana): `MAM1NAM2M2MO` M2, `MAM1NAM3M3MO` M3, `MAM1NAM3M1MO` M1, `MAM1NAM3DMMO` deposit money (media mensual), último 2026-07.
- Loan Support Program (Fund-Provisioning Measure to Stimulate Bank Lending, ¥39,11 bn) y pooled-collateral loans desde BoJ Accounts cada 10 días: dependencia del crédito BoJ (analogía de repo dependence).
- MD08 CAB por sector: qué sector acumula el exceso de reservas (bancos extranjeros vs city banks) — distribución, no nivel.

## 6. Capa C-2 — Tipos y mercado monetario (diario)

- **TONA** por API FM01: `STRDCLUCON` media, `STRDCLUCONH` máximo, `STRDCLUCONL` mínimo, `STRDCLUCV` volumen (100 m ¥). Verificado 2026-09-07: media 0.977 %, máx 0.978, mín 0.95; el 2026-08-24 el máximo tocó 1.10 %. Final a las 10:00 JST del día siguiente (XLSX `md/YYYY/mdYYYYMMDD.xlsx`), provisional 17:15 JST (`mp/mpYYYYMMDD.xlsx`).
- Call Money Market Data (XLSX `others/fcall.xlsx`, fichero fijo que se sobreescribe cada día, final + volumen): call **colateralizado** O/N (0.93 % el 2026-09-07 — analogía GC), no colateralizado a plazo 1w 1.005 %, 2w 1.117 %, 3w 1.167 %, 1m 1.30 %, 3m 1.39 %; saldo del mercado call ¥12,9 bn (colateralizado 2,4 / no colateralizado 10,5).
- **Curva JGB** del MoF: `https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv` (mes en curso, 1Y–40Y, diario) e histórico `historical/jgbcme_all.csv` (desde 1974). Verificado 2026-09-07: 1Y 1.564 · 2Y 1.852 · 5Y 2.272 · 10Y 2.935 · 20Y 3.751 · 30Y 4.009 · 40Y 4.013.
- Corredor: IOER 1.0 % (suelo efectivo para bancos con reservas), basic loan rate 1.25 % (techo), objetivo 1.0 %. TONA opera normalmente **2–3 pb por debajo** del IOER porque las instituciones sin acceso al IOER prestan por debajo; eso es normal, no fricción. La señal de tensión es TONA ≥ objetivo de forma persistente, o el máximo diario ≥ +5 pb sobre el IOER varios días, o el colateralizado por encima del no colateralizado (escasez de colateral).
- FX: USD/JPY diario por API FM08 (código a fijar en Fase 2) solo como desk export.

## 7. Diferencias estructurales JPY vs CAD/GBP/AUD

1. Reservas gigantescas (CAB ¥416 bn vs requerido ¥13,5 bn/día: 28×): la escasez cuantitativa no es un escenario a 12 meses; el régimen relevante es **QT + normalización de tipos** y la señal viene por precio (TONA, colateral, curva) y por el ritmo de reducción del balance.
2. Fiscal diario real (como el DTS): permite `fiscal_big_day` diario, no semanal.
3. Balance cada 10 días (no semanal): las métricas de balance usan `freq: "ten_day"` con nominal_period 12 días.
4. La intervención cambiaria del MoF aparece en el factor fiscal diario (día de liquidación) y en `MASDM26` mensual: flag `FX_INTERVENTION_SUSPECT` cuando el flujo fiscal diario sea un outlier sin subasta/impuesto que lo explique.
5. SLF y Loans del BoJ son los indicadores de emergencia (equivalentes a Primary credit / Advances), pero el SLF se usa también de forma operativa: umbrales por percentil, no > 0.
6. Sin ancla publicada de demanda de reservas (a diferencia del RBA): el ancla absoluta propuesta es exceso/requerido, marcada como propuesta del desk, no del BoJ.

## 8. Pendientes antes de Fase 2

- Parsers: XLSX diario por etiqueta (jd/jx/jp), BoJ Accounts HTML, API JSON (getDataCode), MoF CSV (encabezado de 1 línea + fila final de aviso), fcall.xlsx, calendario de subastas HTML.
- Código FM08 de USD/JPY; código MD07 reservas requeridas mensual; confirmar `NEXTPOSITION` de la API para tramos largos.
- Festivos japoneses 2026–2027 (verificar contra la lista de días hábiles del BoJ; hoy no verificado → fuera del config).
- Backfill: jd 2026 + jd 2025 (desde octubre) por XLSX; anteriores por HTML www3 (`stat/jdYYMMDD.htm`) solo si hace falta para percentiles 750d.
- Estacionalidad fiscal: aprenderla del dato (medias por día del mes) antes de fijar fechas.
- OK de Sander a v0.2 tras la triangulación → Fase 2 JPY.
