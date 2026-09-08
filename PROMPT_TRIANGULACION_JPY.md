# PROMPT DE TRIANGULACIÓN — JPY COMMAND CENTER (Fase 1)

> Instrucciones para Sander: pega este prompt completo **en el cuerpo del mensaje** de cada AI (DeepSeek, Gemini, CodeWord, Qwen, Kimi, Claude; Perplexity sólo si le pegas el prompt, no el fichero suelto). Adjunta `FASE1_JPY_Source_Map.md` y `config/jpy.json`. Pide la respuesta en el formato exacto del bloque final. Regla de la casa desde el AUD: los revisores señalan huecos; ningún precio, código o fecha que propongan entra en el config sin que yo lo verifique en la fuente primaria.

---

Actúa como un jefe de mesa macro institucional de FX (Foreign Exchange) con experiencia real en las operaciones de mercado del Bank of Japan (BoJ), en el mercado call de Tokio y en la emisión de JGB (Japanese Government Bond) del Ministry of Finance (MoF), en el marco MMT (Modern Monetary Theory) / Mosler, y con criterio de ingeniería de datos. No eres un asistente amable: eres un revisor que busca errores, huecos y supuestos no verificados. Si algo está bien, dilo en una línea y sigue; el valor de tu respuesta está en lo que falta o está mal. No inventes identificadores de series ni URL: si no estás seguro, dilo. Aviso: la página antigua `www3.boj.or.jp/market/en/menu.htm` está suspendida desde el 6 de octubre de 2025; si tu memoria apunta ahí, está desactualizada.

## Contexto

Soy un operador macro FX individual. Opero las ocho monedas del G8 (USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF) leyendo la liquidez de cada moneda bajo el marco MMT/Mosler: el gasto del gobierno crea activos financieros netos para el sector no gubernamental, los impuestos los destruyen, la emisión de bonos drena reservas pero no cambia ese stock, el banco central fija el precio de las reservas y no la cantidad, y las reservas no son lo mismo que los activos financieros netos.

Tengo en producción tres dashboards USD y tres dashboards no-USD construidos sobre un Desk Standard triangulado y validado: **CAD** (Bank of Canada Valet + Receiver General diario), **GBP** (BoE IADB + ONS) y **AUD** (RBA CSV: ES balances diarias, A1 semanal, F1/F2 diarias). El estándar: 12 bloques por moneda, cuatro capas con título en orden fijo (banco central → tesoro o equivalente → transmisión bancaria → tipos), estados `fresh / stale / proxy / degraded / unavailable`, umbrales por percentiles rodantes con histéresis sobre transformadas estacionarias más anclas absolutas institucionales, regímenes LIQUIDITY_INJECTION / DRAIN / SCARCITY / FLOOR_FRICTION / NEUTRAL con la escasez confirmada por el precio y nunca sólo por la cantidad, flags ortogonales, ingesta Python en GitHub Actions, JSON estático en Netlify.

Ahora paso al **JPY**. Tuve un dashboard JPY v5 (Netlify Function + FRED mensual) en el que todo lo importante —balance del BoJ, CAB (Current Account Balances), depósitos del Gobierno, TONA, TIBOR, la curva JGB, lo fiscal— era dato simulado. Lo he descartado. He verificado hoy, leyendo los ficheros celda a celda en el navegador:

- BoJ diario "Sources of Changes in Current Account Balances and Market Operations": XLSX con URL determinista (final `jd/YYYY/jdYYYYMMDD.xlsx` ~10:00 JST del día siguiente, provisional `jx/` ~18:00 JST, proyección del día siguiente `jp/`). Contiene el factor billetes, el factor **fondos del Tesoro** (flujo fiscal neto diario, con signo: menos = recepción neta), operaciones por tipo (compras de JGB, pooled collateral, Loans = Complementary Lending Facility, Securities Lending Facility), ΔCAB, CAB total (¥416,1 bn el 7-sep-2026), reservas, **exceso de reservas** (¥384,4 bn), CAB de instituciones sin requisito (¥31,7 bn), base monetaria (¥535,3 bn) y reservas requeridas del periodo (¥13,48 bn/día, periodo 16-ago/15-sep).
- BoJ Accounts cada 10 días (HTML): JGB ¥519,93 bn, préstamos ¥71,86 bn (Loan Support Program 39,11; pooled collateral + disaster + climate 32,75), activos ¥644,66 bn, billetes ¥114,87 bn, depósitos corrientes ¥424,32 bn, **depósitos del Gobierno ¥9,26 bn**, repos ¥37,43 bn (31-ago-2026).
- **API oficial** del Time-Series Data Search: `https://www.stat-search.boj.or.jp/api/v1/getDataCode?db=FM01&code=STRDCLUCON&format=json&lang=EN&startDate=202608&endDate=202609` (probada, JSON limpio); metadatos MD06 (mensual), MD01, MD02, MD08, MD13, FM02.
- Corredor (MPM 16-jun-2026, efectivo 17-jun): objetivo del call no colateralizado O/N **"around 1.0 %"**, IOER (Complementary Deposit Facility) **1.0 %**, basic loan rate **1.25 %**. Reafirmado el 31-jul-2026 (8–1). Serie CSV del basic loan rate `cdab0101.csv`; regla verificada policy = basic loan rate − 0.25 en los cuatro últimos movimientos.
- Plan de compras de JGB (MPM 16-jun-2026): ~¥2,5 bn/mes jul–sep 2026, 2,3 oct–dic, 2,1 ene–mar 2027, 2,0 desde abril 2027; tenencias esperadas ~¥480 bn a fin de marzo 2027, 430–440 en 2028, 390–400 en 2029, 350–370 en 2030. Sin revisión intermedia.
- TONA (API FM01, media/máximo/mínimo/volumen): 0.977 % el 7-sep-2026 (máx 0.978, mín 0.95); el máximo tocó 1.10 % el 24-ago. Call colateralizado O/N 0.93 %; call no colateralizado 1w 1.005 %, 1m 1.30 %, 3m 1.39 % (fcall.xlsx).
- Curva JGB del MoF (`jgbcme.csv`, diario 1Y–40Y): 1Y 1.564, 2Y 1.852, 5Y 2.272, 10Y 2.935, 20Y 3.751, 30Y 4.009, 40Y 4.013 (7-sep-2026).
- Calendario de subastas del MoF (HTML mensual): 10Y 1-sep, 30Y 3-sep, 5Y 8-sep, 20Y 15-sep, 40Y 29-sep, 2Y 30-sep, T-Bills semanales.
- Calendario MPM: 17–18 sep, 29–30 oct, 17–18 dic 2026.

## Regla de diseño obligatoria

Capas con título visible, en este orden: 1 liquidez del banco central; 2 Tesoro (MoF) / fiscal; 3 transmisión bancaria; 4 tipos y mercado monetario; 5 régimen, alertas, agente, calidad, histórico. Ninguna métrica se elimina porque la fuente sea difícil: se muestra con su estado. Prioridad a métricas diarias; cada 10 días y mensuales sólo cuando no haya más remedio.

## Lo que te pido revisar (adjunto `FASE1_JPY_Source_Map.md` y `config/jpy.json`)

Responde punto por punto: VALIDADO, VALIDADO CON OBSERVACIONES o RECHAZADO, y por qué.

**1. Equivalencias JPY ↔ USD ↔ CAD/GBP/AUD.**
- Reservas: uso el CAB total diario como WRESBAL y el **exceso de reservas / reservas requeridas (media diaria del periodo)** como medida de holgura (28,5× hoy). ¿Es el denominador correcto? ¿Debo usar el exceso "macro-add-on/benchmark" de la Complementary Deposit Facility (tramos) en vez del requerido legal? ¿Sigue existiendo el sistema de tres tramos tras la salida de tipos negativos (marzo 2024) o el IOER se aplica a todo el exceso?
- Spread de estrés primario = TONA − objetivo (= IOER). En un sistema de suelo TONA cotiza 2–3 pb **por debajo** del IOER por las instituciones sin acceso (tanshi, securities). Propongo: normal −5…0; WATCH ≥ 0 tres sesiones; STRESS ≥ +5; CRISIS ≥ +15 (techo +25); lado bajo ≤ −8 = fuga del suelo. ¿Signos y niveles correctos? ¿Qué explica los máximos diarios de 1.03 % con media 0.977 %: fin de día, contrapartes concretas, fin de periodo de mantenimiento?
- Ventanilla de emergencia: la fila "Loans" (Complementary Lending Facility al basic loan rate). ¿Es el análogo correcto de Primary credit? ¿Algún uso > 0 es flag o hay uso rutinario (fin de mes, fin de año fiscal)?
- Securities Lending Facility: propongo percentil p90 como WATCH sólo con el colateralizado por encima del no colateralizado. ¿La SLF es un indicador de escasez de colateral JGB o es ruido operativo por los cheapest-to-deliver (relajación de condiciones 27-feb-2026)?
- Net Liquidity = activos totales − depósitos del Gobierno (cada 10 días). Con depósitos del Gobierno en ¥9 bn frente a activos de ¥645 bn, ¿tiene sentido conservarlo como analogía cross-currency o es cosmético en Japón?

**2. Capa fiscal.**
Propongo el factor "Treasury funds and others" diario del BoJ como flujo fiscal (positivo = inyección), acumulados de 5 y 20 días, Z de 250 días, `fiscal_big_day` ≥ ¥3 bn o |Z| ≥ 2, y la **proyección del BoJ para el día siguiente** como impulso fiscal de mañana (único en el G8). Desglose mensual por MD06 (pagos fiscales netos MASDM@01, JGB emitidos/amortizados, T-Bills, **FX MASDM26**).
- ¿Es correcto leer "Treasury funds and others" como el neto fiscal (impuestos + emisión de JGB/T-Bills − gasto − amortizaciones − cupones)? ¿Qué más entra en "and others" (FEFSA, pensiones públicas, Japan Post)?
- Intervención cambiaria del MoF: ¿se liquida a través de este factor el día de liquidación y aparece en MASDM26 mensual? ¿Cómo la distinguirías de un día de impuestos?
- Estacionalidad japonesa que debo verificar en el dato antes de fijar fechas: impuesto de sociedades (fin de mayo para cierre marzo, interino en noviembre), IRPF marzo, consumo, pensiones el 15 de meses pares, amortizaciones y cupones JGB los 20 de mar/jun/sep/dic, cierre fiscal 31-mar y "fin de año fiscal" en el call. Corrige o completa; cita fuente si la conoces.
- ¿Existe una fuente diaria o semanal del MoF de caja del Tesoro (Receipts and Payments of Treasury Funds) con URL estable en inglés o japonés? No la localicé hoy.
- ¿Peso 0,25 para la capa fiscal (diaria) es defendible? En CAD (diario) 0,20, GBP 0,10, AUD 0,25.

**3. Transmisión bancaria.**
MD13 (préstamos y depósitos: FAAP@01, FAAPOBAL1, FAAPOBAL1@, FAAPOBRDCD5) y MD02 (M2 MAM1NAM2M2MO, M3, M1, deposit money), más Loan Support Program y pooled-collateral loans cada 10 días como dependencia del crédito BoJ.
- ¿Son ésas las series de cabecera correctas para "préstamos crean depósitos"? ¿Falta la serie ajustada por partidas especiales (FAAPOBAL4) o el desglose por sector LA01?
- ¿Hay alguna fuente semanal o quincenal (BoJ, JBA, FSA) que acerque la frecuencia al H.8?
- ¿La distribución del exceso de reservas por sector (MD08: city vs regional vs extranjeros vs trust) es un indicador de transmisión útil o sólo display?

**4. Umbrales.**
El BoJ no publica una estimación de la demanda de reservas.
- ¿Conoces alguna publicación del BoJ (Review of Monetary Policy 2024, Outlook, discursos de Ueda/Uchida/Himino, papers del Financial Markets Department) que cuantifique el nivel de reservas "amplio" o el punto donde el suelo dejaría de funcionar bajo el QT? Cita título y fecha; si no la conoces, dilo.
- Mi ancla absoluta propuesta (exceso/requerido: ample > 10×, WATCH < 5×, STRESS < 2×, CRISIS < 1,2×) está marcada como propuesta del desk, no del BoJ. ¿Es razonable como orden de magnitud? ¿Qué usarías tú?
- Percentiles anclados en 2024-08-01 (primera subida tras el fin de YCC) y nunca sobre el nivel de CAB (no estacionario bajo QT). ¿De acuerdo? ¿Ventana mejor?
- Call 1m − objetivo: propongo la regla AUD (absoluto 30/45/70 vinculante; el percentil solo llega a WATCH porque el plazo descuenta subidas). ¿Correcto para Tokio? ¿Sería mejor OIS/TONA swap 1m o 3m, y de qué fuente pública diaria?
- Curva 30y−10y: WATCH p90 / STRESS p97 como estrés del super-largo (aseguradoras, QT). ¿Añadirías el 40y−30y o el 20y?

**5. Régimen.**
Pesos propuestos: banco central 0,35 / tipos 0,30 / fiscal 0,25 / banca 0,10 (más peso a tipos que en AUD/GBP porque con 28× de exceso la historia JPY está en el precio y en el ritmo del QT). Flags: CLF_USED, JGB_COLLATERAL_SQUEEZE, QT_ACCELERATION, QT_PAUSE_NIMBLE, FX_INTERVENTION_SUSPECT, BOJ_CREDIT_DEPENDENCE_ELEVATED, SUPER_LONG_STRESS, TRANSMISSION_FAILURE, DATA_DEGRADED. USD/JPY, Nikkei y carry quedan fuera del tab JPY (van a la mesa).
- ¿Pesos defensibles? ¿Falta algún flag propio del JPY (operaciones en dólares del BoJ, compras a tipo fijo, ETF/J-REIT en venta, Japan Post, GPIF)?
- Con reservas 28× el requerido, ¿LIQUIDITY_SCARCITY debe existir siquiera como régimen en JPY o debe sustituirse por un régimen "QT_STRESS" leído en el super-largo y en la SLF?

**6. Arquitectura y fuentes.**
Ingesta Python en GitHub Actions: carril diario 02:30 UTC (11:30 JST: jd final + TONA final + fcall + MoF yields), carril provisional opcional 09:30 UTC (jx + jp), carril de 10 días (3/13/23) para BoJ Accounts, mensual día 15 para MD13/MD02/MD06/MD08; parseo del XLSX por texto de etiqueta; snapshot de fcall.xlsx (nombre fijo, se sobreescribe); una petición por fuente, ≥ 1 s; JSON en git; Netlify estático.
- ¿Ves un fallo estructural? ¿Qué se rompe primero: cambios de ítems en el XLSX diario (avisos 2025-10-31, 2026-01-27, 2026-06-30), límites de la API, bloqueo de runners de GitHub por el BoJ o el MoF?
- ¿La API tiene cuota o clave? ¿`NEXTPOSITION` obliga a paginar series diarias largas?
- ¿Prefieres reconstruir el histórico diario desde los XLSX (2025-10 en adelante) o desde el HTML antiguo de www3 para tener 750 días de percentiles?

**7. Lo que falta.**
Lista métricas, fuentes o reglas que un desk institucional tendría en un monitor de liquidez JPY y que no aparecen. Sé concreto: serie (si la conoces con certeza), fuente, frecuencia. Ejemplos de lo que sospecho: TONA swap / OIS público, T-Bill 3m de mercado (no subasta), resultados de subasta (bid-to-cover, tail), GC repo (Tokyo Repo Rate de JSDA), TIBOR (JBA), operaciones en dólares del BoJ, fails en JGB (PS02), CP/corporate bond spreads, saldos de Japan Post en el BoJ.

**8. Lectura de hoy.**
Datos verificados (7-sep-2026 salvo indicación): CAB ¥416,1 bn, exceso ¥384,4 bn, requerido ¥13,48 bn/día, ΔCAB +¥0,29 bn, fondos del Tesoro +¥0,33 bn (proyección para el 8-sep +¥0,32 bn), CLF 0, SLF +300/−1 200; BoJ JGB ¥519,9 bn (31-ago), plan ~¥480 bn a marzo 2027; objetivo 1.0 %, IOER 1.0 %, techo 1.25 %; TONA 0.977 (máx 0.978, mín 0.95; máx 1.10 el 24-ago), colateralizado O/N 0.93, call 1m 1.30, 3m 1.39; JGB 2Y 1.852, 10Y 2.935, 30Y 4.009. ¿Qué régimen de liquidez JPY declararías y por qué? ¿Cómo lees un 2Y 85 pb por encima del objetivo y un 30Y en 4 % con el BoJ recortando compras?

## Formato de respuesta obligatorio

```
VEREDICTO GLOBAL: [VALIDADO / VALIDADO CON CAMBIOS / RECHAZADO]
1. EQUIVALENCIAS: [estado] — [observaciones]
2. CAPA FISCAL: [estado] — [observaciones + fuentes MoF]
3. TRANSMISIÓN BANCARIA: [estado] — [observaciones + códigos confirmados o no]
4. UMBRALES: [estado] — [observaciones + ancla de reservas con fuente y fecha, o "no conozco ninguna"]
5. RÉGIMEN: [estado] — [observaciones]
6. ARQUITECTURA: [estado] — [observaciones]
7. LO QUE FALTA: [lista concreta]
8. LECTURA DE HOY: [régimen + justificación en 5 líneas]
TRES CAMBIOS PRIORITARIOS: [los tres que harías antes de escribir código]
```

No propongas ejecución automática de operaciones, ni análisis técnico, ni gestión de riesgo: eso está fuera del alcance.
