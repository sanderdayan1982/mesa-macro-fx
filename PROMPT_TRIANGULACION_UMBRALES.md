# PROMPT DE TRIANGULACIÓN — FASE 3, UMBRALES CALIBRADOS DEL RÉGIMEN DUAL (ocho divisas) — v2 (segunda ronda, 2026-09-09)

> Instrucciones para Sander: pega este prompt completo **en el cuerpo del mensaje** de cada AI (CodeWord, Kimi, Perplexity, DeepSeek, Gemini, Qwen, Claude). Adjunta el zip `triangulacion_umbrales_v0.1.zip` (ocho `CALIBRACION_<CCY>.md`, ocho `report_<ccy>_detalle.md`, ocho `calibration.json`, el `calibrate.py` y la `MATRIZ_RESPUESTA_UMBRALES.md`). Pide que rellenen la matriz al final. Recoge las respuestas literales y pégamelas; yo verifico en fuente primaria cada afirmación y no toco ningún config sin esa verificación.

---

Actúa como un jefe de mesa macro institucional de FX (Foreign Exchange) con experiencia real en implementación de la política monetaria (sistemas de suelo y corredor, reservas, facilidades permanentes, QT — Quantitative Tightening), en mercados monetarios (SOFR, €STR, SONIA, SARON, TONA, AONIA, CORRA, tipos overnight de Nueva Zelanda), en gestión de la caja de los tesoros (DTS — Daily Treasury Statement —, Receiver General, cuentas del Gobierno en el banco central) y en subastas de deuda soberana; y con formación estadística suficiente para juzgar una calibración empírica (correlación de rangos, walk-forward, pruebas condicionales, percentiles por era).

## Contexto

Soy un operador macro FX individual. Opero las ocho monedas del G8 (USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF) leyendo la liquidez de cada moneda bajo el marco MMT/Mosler: el gasto del gobierno crea activos financieros netos y reservas; la emisión de deuda y los impuestos los drenan; el banco central fija el precio de las reservas, no su cantidad. Tengo en producción ocho dashboards sobre un Desk Standard triangulado (cuatro capas con título: 1 banco central · 2 Tesoro o equivalente · 3 transmisión bancaria · 4 tipos y mercado monetario). Cada dashboard produce una **puntuación de bloque** para el banco central y otra para el Tesoro (o equivalente), y de ellas salen **tres regímenes**: banco central, Tesoro y general (INYECCIÓN / DRENAJE / NEUTRAL). Los umbrales de bloque provisionales eran ±0,5, y los pesos del régimen general 0,6 / 0,4 — números de la mesa, no de la historia.

Mi regla es que **no quiero umbrales inventados**: sólo umbrales que la historia haya demostrado reales. Por eso he calibrado las ocho divisas con datos primarios y un método común, y lo que te adjunto son los resultados. Tu trabajo no es proponer umbrales de cabeza — eso está prohibido en esta mesa —: es revisar el **método**, las **eras**, las **verdades** y las **fuentes**, y señalar lo que falta o está mal cortado.

## El método que has de revisar (`ingest/calibrate.py`, adjunto)

1. **Replay as-of**: cada bloque del dashboard se vuelve a calcular semana a semana **con los datos que existían ese día** (mismos parsers y mismo código que en producción; retardos de publicación aplicados; histéresis arrastrada como en vivo). Nada se elige con datos futuros.
2. **Control FX**: retorno logarítmico forward del cruce divisa-por-USD a 5 / 10 / 20 sesiones (hipótesis MMT: inyección → divisa más débil). Spearman, walk-forward por bloques de dos años, y una rejilla de cortes −1,5…+1,5 que sólo se acepta si separa los retornos con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba (corte 2025-01-01) y cubre ≥ 10 % de las semanas. Pesos duales por OLS walk-forward.
3. **A — frecuencia de la era operativa**: percentiles p10…p90 de la puntuación de cada bloque dentro de la era operativa vigente de cada banco central (suelo, corredor, QT, marco nuevo…), con estabilidad año a año; propuesta INJECTION ≥ p80 (salida p67) / DRAIN ≤ p20 (salida p33), o los huecos naturales cuando la puntuación es discreta.
4. **B — verdad de funding**: cambio forward del spread de estrés de cada divisa (SOFR − IORB, €STR − DFR, SONIA − Bank Rate, SARON − ancla, TONA − IOER, AONIA − target, CORRA − depósito, bank bill 30 d − OCR) a 4 y 12 semanas: correlación de rangos, medias condicionales por régimen y la misma rejilla de cortes.
5. **Subastas**: percentiles históricos y de la era (p5 / p10 / mediana / p90) del bid-to-cover, del tail y de la retención por instrumento, y prueba de si una subasta débil (≤ p10) o fuerte (≥ p90) precede un movimiento distinto del cruce, por eras.

## Lo que la historia dijo (resumen; el detalle está en cada `CALIBRACION_<CCY>.md`)

- **Ningún bloque predice el cruce a 1–4 semanas en ninguna de las ocho** (|ρ| < 0,12, ningún corte sobrevive, ningún peso dual significativo). Conclusión de la mesa: el régimen de liquidez es una descripción del estado, no una señal de tipo de cambio; el régimen general se queda en la regla de acuerdo (los dos inyectan / los dos drenan) y el conflicto abierto es NEUTRAL etiquetado.
- **Las subastas describen la demanda del papel, no el cruce**: los efectos FX cambian de signo por eras en las ocho. Las anclas propuestas son percentiles de la era reciente.
- **Defecto de diseño común**: los bloques del banco central mezclan **niveles** (reservas sobre un rango, cuota de absorción, recurso al OMO, fase QT, badge del TGA/RRP, déficit estructural) con **flujos**; los niveles dejan al bloque en un estado permanente (GBP INYECCIÓN 49 % de la QT; AUD 74 %; JPY +0,5 el 81 %; USD y EUR INYECCIÓN 4 %; NZD DRENAJE 35 %, CHF 51 %). Propuesta v0.3: niveles a 0,25 y que la inyección la digan los flujos.
- **Verdad de funding**: existe y con el signo MMT en GBP (Tesoro, 12 s, ρ −0,24), CHF (Tesoro, 12 s, ρ −0,19), USD (sorpresa fiscal, 4 s, p 0,07 sin corregir) y EUR (banco central, ρ −0,31 / −0,33 a 4 / 12 s, negativa dentro de cada año). Sólo dos cortes de la rejilla sobreviven la prueba fuera de muestra en las ocho divisas: el INJECTION ≥ 0,9 del Tesoro USD y el DRAIN ≤ −0,6 del BC del EUR, ambos con efecto pequeño en prueba (−0,86 pb y +0,08 pb). Tras la primera ronda de triangulación se añadió la corrección de Benjamini–Hochberg conjunta sobre las 32 pruebas B y un block-bootstrap de 8 semanas por autocorrelación (`calibration/B_fdr.md`): los resultados van en el dossier. No existe en AUD (era nueva), JPY (TONA − IOER vive en 0,2 pb) ni NZD (el bill − OCR lo mueve la expectativa de tipos).
- **Dos defectos reales del código de producción** aparecieron en el replay y están corregidos: el flujo fiscal del CAD congelado 3,5 años (celdas vacías del Receiver General) y la histéresis de dos lados de CHF/NZD que nunca salía de STRESS.

## Cambios respecto a la primera ronda (v1 → v2)

Se corrigieron los hallazgos verificados de la ronda 1: (1) el `proposal` automático p80/p20 de los `calibration.json` divergía de los cortes argumentados en los informes — ahora los cortes de mesa viven en `FINAL_CUTS` dentro de `calibrate.py`, se escriben en `ab.final_cuts` y son la única fuente para los parches de config; (2) el CAD se re-ejecutó con el bloque A + B y el mismo corte de prueba 2025-01-01 que las otras siete; (3) el reparto del JPY decía 85/15/4 (suma 104) — los valores son 81,4 / 14,7 / 3,9; (4) se declara la convención de percentil (interpolación lineal; en escalas discretas se reporta también el valor alcanzable más próximo); (5) corrección por comparaciones múltiples (FDR) y por autocorrelación (block-bootstrap) en B; (6) la matriz admite el veredicto SD (sin datos) y cada VO/R debe traer la comprobación concreta (serie, rango de fechas, signo esperado).

## Regla obligatoria

No propongas cifras de umbral. Si crees que un umbral está mal, di **por qué** (era mal cortada, retardo mal aplicado, verdad inadecuada, fuente mejor) y **con qué fuente primaria pública** se comprobaría. Si no lo sabes, dilo. Cada respuesta: VALIDADO, VALIDADO CON OBSERVACIONES o RECHAZADO, y la razón.

## Lo que te pido revisar

**1. Método (común a las ocho).**
- ¿Es correcto calibrar por frecuencia de la era operativa cuando el cruce no responde? ¿Qué verdad alternativa usarías para validar un régimen de liquidez (p. ej. basis cross-currency, primas a plazo, flujos de balanza de pagos, volatilidad implícita) que sea pública y diaria/semanal?
- ¿El spread de estrés elegido por divisa es el precio de funding correcto? En particular: NZD (bank bill 30 d − OCR está contaminado por la expectativa de tipos; ¿interbancario overnight − OCR, aunque sea disperso?), JPY (TONA − IOER no tiene varianza; ¿repo GC de la JSDA o uso del CLF?), AUD (AONIA − target cambió de régimen con el marco de abril-2025).
- ¿Los retardos de publicación aplicados en el replay son realistas? (SNB balance +10 d, reservas mínimas +45 d, gmges +31 d; RBNZ D10 +31 d, R1/R3 +14 d; ECB WFS +4 d, TARGET/BSI/MIR +60 d, APP/PEPP +32 d; USD H.4.1 miércoles/jueves, DTS T-1; BoJ archivo www3; MoF; RBA/AOFM; DMO/ONS.)
- Percentiles de entrada p80/p20 con salida p67/p33: ¿es la histéresis correcta para un régimen que un operador lee a diario? ¿Qué persistencia mínima pediría un jefe de mesa antes de cambiar el régimen?
- El cambio v0.3 (niveles a 0,25, flujos dicen la inyección): ¿lo validas? ¿Qué flujos concretos por divisa deberían componer la "inyección" del banco central (p. ej. Δ reservas neto de factores autónomos, compras − vencimientos, operaciones de fondos, Δ TGA con signo cambiado)?
- **Persistencia**: el método no fija cuántas semanas fuera de banda hacen falta para cambiar la etiqueta de régimen. ¿Qué regla pediría un jefe de mesa (2 semanas consecutivas de entrada, 1 de salida; 3 de 4; otra) y con qué fundamento?
- **Multiplicidad y autocorrelación**: con la corrección FDR conjunta y el block-bootstrap (tabla B_fdr en el dossier), ¿qué validaciones de funding aceptarías como reales y cuáles como sugerencias? ¿Es correcto el bloque de 8 semanas?
- **Transición de era**: cuando un banco central cambia de marco (NZD 2026-04-02, AUD 2025-04-09), ¿qué umbrales deben operar en vivo hasta que la era nueva tenga 150 semanas: los de la era anterior, los provisionales de la nueva, o sólo la regla de acuerdo?
- **Etiquetado de evidencia**: cada umbral del config llevará una etiqueta (`funding_validado`, `frecuencia_de_era`, `provisional_era_corta`, `banda_por_diseño`). ¿Qué haría el operador de forma distinta con cada etiqueta?

**2. Eras (una por divisa; di si el corte es el correcto y qué fuente primaria lo fija).**
- CAD: suelo desde 2020-03-23 (337 semanas). GBP: QT con ventas del APF desde 2022-11 (201). AUD: reservas amplias desde 2025-04-09 (74; ¿es calibrable con 74 semanas o hay que esperar?). JPY: suelo de tipos positivos desde 2024-07-31 (102). CHF: absorción con remuneración escalonada desde 2022-09-22 (207; sub-era 0 % desde 2025-06-20). NZD: desenvolvimiento del LSAP desde 2022-07-01 (210; marco nuevo desde 2026-04-02, 22 semanas). USD: QT desde 2022-06-01 (223; sub-era desde 2025-04). EUR: suelo bajo QT desde el DFR positivo, 2022-09-14 (208).
- ¿Hay alguna era que deba subdividirse o unirse? ¿Algún cambio de marco operativo que yo no haya cortado (p. ej. cambios de factor umbral del SNB, fin de TLTRO, cambio de remuneración de reservas)?

**3. Anclas de subasta (por instrumento; el detalle numérico está en cada informe).**
- ¿Los percentiles de la era reciente son la referencia correcta, o hay anclas institucionales publicadas (informes anuales de los DMO, Treasury Borrowing Advisory Committee, AOFM, NZDM, Finanzagentur, MoF) que deban prevalecer?
- Tails: definiciones distintas por fuente (USD alto − mediana de la subasta; NZ alto aceptado − medio; UK del PDF del DMO; DE sin marginal). ¿Alguna fuente pública con el tail vs WI (when-issued) o vs mercado secundario al cierre?
- Retención (Finanzagentur), infra-adjudicación (NZDM 1 año), tramos propios (EFV): ¿cómo los leería un operador de la deuda de cada país?

**4. Casos especiales.**
- USD: el Tesoro está en INYECCIÓN el 83 % de las semanas por el déficit permanente; propongo mantener la etiqueta y leer el **ritmo** (banda p20/p80 de la puntuación). ¿Cómo lo leería una mesa de dólar? ¿Prefieres el ritmo por FYTD (Fiscal Year To Date) vs año anterior, por NTF (Net Treasury Flow) de 60 sesiones o por la sorpresa diaria?
- EUR: el déficit estructural del área (−3 % PIB) impide que el bloque del Tesoro drene; los depósitos de los gobiernos en el Eurosistema son sólo una parte de la caja de los tesoros. ¿Qué medida semanal pública de la caja fiscal del área usarías?
- JPY: el bloque del banco central no discrimina (exceso/requerido 35×). ¿Qué flujos del "Sources of Changes in Current Account Balances" del BoJ definirían la inyección?
- CHF: la ventana de percentiles del Δ13 semanas de depósitos a la vista mezcla la caída de 2022–24 con la fase plana de 2025–26. ¿Anclar la ventana a la era o usar una ventana más corta?

**5. Fuentes.** Para cada divisa, indica si conoces una serie primaria pública, diaria o semanal, que yo no haya usado y que mejore (a) la verdad de funding, (b) el flujo fiscal o (c) las subastas. Sólo fuentes que puedas señalar con URL.

## Formato de respuesta

Rellena la `MATRIZ_RESPUESTA_UMBRALES.md` adjunta (una fila por pregunta y divisa: VALIDADO / CON OBSERVACIONES / RECHAZADO · razón · fuente primaria). Después, un párrafo final: qué tres cosas cambiarías del método antes de aplicar cualquier umbral a producción. No repitas los números de los informes; no propongas cifras.
