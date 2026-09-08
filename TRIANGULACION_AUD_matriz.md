# TRIANGULACIÓN AUD COMMAND CENTER — Matriz de consenso (Fase 1 → config v0.2)

Fecha: 2026-09-08. Siete respuestas: Kimi, CodeWord, Perplexity, DeepSeek, Qwen, Claude, Gemini. Todas **VALIDADO CON CAMBIOS**. Nota: los textos de Claude y Gemini son idénticos palabra por palabra (mismo pegado o copia); cuentan como una sola voz.

Leyenda: ✅ validado · ⚠ con observaciones · ❌ rechazado · **[V]** afirmación verificada por mí en fuente primaria hoy · **[X]** afirmación verificada como falsa.

## 1. Hechos en disputa, resueltos contra fuente primaria

| Afirmación | Quién | Resultado |
|---|---|---|
| OMO de adjudicación plena a **target + 10 pb desde 9-abr-2025**, tenores 7d y 28d, miércoles | Kimi | **[V]** Kent, "Monetary Policy Implementation System — some important updates", 2-abr-2025 (RBA PDF): previo +5, nuevo +10, efectivo 9-abr-2025; reservas "~$240bn" tras el TFF |
| OMO "a tipo fijo igual al target" | DeepSeek | **[X]** |
| OMO "a target + 25" | CodeWord | **[X]** (+25 es la standing facility overnight) |
| "The Road to Ample" (Jacobs, 25-ago-2026): el open repo (standing facility a coste cero) **cesa a inicios de 2027**; el RBA no persigue un nivel de reservas | Kimi | **[V]** Además: ES ~$200bn (ago-2026), **demanda estimada de reservas $70–100bn** (2024: $100–200bn), OMO $20–30bn vivos, repo overnight privado ~+2 pb sobre target; señales de escasez que vigila el RBA: tipos cortos por encima del ES rate y aumento del take-up OMO |
| D1/D3 "muertas, sustituidas por F11/F12" | Qwen | **[X]** F11 son tipos de cambio; D1 (crecimientos), D2 (niveles), D3 (agregados monetarios) están vivas y verificadas hoy con 2 000 filas y cabeceras actuales. El mapeo correcto lo dio Kimi |
| F2 "es semanal, no diaria" | Kimi | **[V]** parcial: valores diarios, fichero actualizado semanalmente con ~2 días hábiles de retraso (último 02-sep visto el 08-sep) |
| "Los estados no bancan en el RBA" | CodeWord | **[X]** A1 tiene columna State Governments Deposits; pero es inmaterial (7–40 millones) → display only |
| "El RBA tiene API SDMX oficial" | Claude/Gemini | **no encontrada** — el RBA sirve CSV/XLS; se mantiene CSV con parser por nombre de columna |
| CLF viva | Kimi | **no adoptado**: APRA la eliminó (phase-out completado); se retira del config |
| Ancla "mínimo post-TFF 100–110 k" | Qwen | **[X]** inventado; sustituido por la estimación oficial $70–100bn |

## 2. Veredictos por punto

| Punto | Kimi | CodeWord | Perplexity | DeepSeek | Qwen | Claude=Gemini | Decisión v0.2 |
|---|---|---|---|---|---|---|---|
| 1 Equivalencias | ⚠ | ⚠ | ⚠ | ❌ | ⚠ | ⚠ | ES total vs rango RBA + precio como gauge primario; Net Liquidity = assets − gov deposits se conserva como análogo de balance (no como gauge) |
| 2 Fiscal | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | Semanal A1 = máximo; calendario fiscal completo; FISCAL_BIG_WEEK absoluto 15 bn + Z |
| 3 Banca | ⚠ | ⚠ | ❌ (códigos) | ❌ (códigos) | ❌ (D1 muerta: falso) | ⚠ | Códigos resueltos en ingesta desde la fila "Series ID"; D1/D2/D3 bien mapeadas; riesgo D2A → degraded-by-design |
| 4 Umbrales | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | Ancla $70–100bn (Jacobs 2026-08-25); percentiles sólo sobre Δ y en ventana post-feb-2025; BBSW−OIS 15/25/50 a validar empíricamente |
| 5 Régimen | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | Pesos 0,40/0,25/0,25/0,10 (mediana); flags OMO_TAKEUP_SURGE, STANDING_FACILITY_USED (+25 sólo), FX_OPERATION; commodities fuera |
| 6 Arquitectura | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | ❌ (SDMX) | CSV por nombre de columna, schema check, F2 semanal, open-repo tolerante |
| 8 Lectura hoy | INJECTION amplio | NEUTRAL | NEUTRAL | NEUTRAL | NEUTRAL sesgo drain | DRAIN sin escasez | **NEUTRAL** con FISCAL_BIG_WEEK (drenaje) y precio intacto |

## 3. Cambios adoptados

| # | Cambio | Origen |
|---|---|---|
| C1 | Precio OMO corregido a target + 10 (9-abr-2025), 7d/28d, miércoles 09:20 | Kimi [V] |
| C2 | **Ancla absoluta de reservas** = demanda estimada por el RBA $70–100bn (Jacobs 25-ago-2026): > 100bn ample, dentro = transición, < 70bn zona de escasez con confirmación de precio; regla de revisión en cada actualización del RBA | Kimi + verificación propia |
| C3 | Separar **open repo** (al ES rate, operativo, muere en 2027) de la **standing facility a +25** (estrés); parser tolerante a la desaparición de la columna | Kimi |
| C4 | **OMO take-up semanal** (a3-omo-repo-transaction-details) como métrica demand-driven; flag OMO_TAKEUP_SURGE ≥ p90 — es la señal temprana que el propio RBA declara vigilar | Kimi, Jacobs [V] |
| C5 | Umbral de holgura sobre **ES total** contra el rango RBA; percentiles sobre Δ diaria y Δ% semanal en la ventana del régimen (post-feb-2025), nunca sobre nivel | DeepSeek, CodeWord, Qwen, Claude (surplus) + CodeWord (ventana) |
| C6 | Spread primario AONIA − target (anclado en target desde +10); AONIA − ES rate secundario (banda); lado bajo −5 persistente = exceso, no escasez | Kimi, Claude; CodeWord/Qwen en secundario |
| C7 | F2 pasa a cadencia semanal; F1 diario; semis unavailable | Kimi |
| C8 | D1 = crecimientos, D2 = niveles, D3 = agregados; series ex-financial-businesses; códigos resueltos desde la cabecera "Series ID" en cada ingesta con fallo ruidoso | Kimi, CodeWord, Perplexity, Claude |
| C9 | Calendario fiscal: 21 mensual PAYG/GST, 28 tras trimestre BAS, sociedades trimestral, super guarantee 28 jul/oct/ene/abr, FBT 21-may, EOFY 30-jun con reconstrucción de caja jul–oct; salto de principios de septiembre ≠ BAS | CodeWord, Qwen, Kimi, DeepSeek |
| C10 | FISCAL_BIG_WEEK absoluto (≥ 15 bn) además del Z; T-notes on issue y calendario de redenciones AGS como series pendientes | Kimi |
| C11 | A3.1 holdings mensual (run-off), A3.2 securities lending, A4/A5 FX como flag binario raro; CLF retirada | Kimi, Perplexity, CodeWord |
| C12 | AOFM: descubrimiento de enlace en cada run + checksum (URLs con fecha) | CodeWord, DeepSeek, Perplexity |
| C13 | Pesos 0,40/0,25/0,25/0,10 mantenidos (mediana de 7) con calibración planificada | — |

## 4. Rechazado

SDMX del RBA (no existe verificable); commodities/términos de intercambio en el tab (7/7 de acuerdo: mesa macro); intervención FX como flag permanente (rara; A4/A5 como binario); ancla 100–110 k (inventada); D1/D3 "muertas"; "Total Reserves = ES + OMO + SF" de Kimi (los repos OMO ya crean ES: sumarlos es contar dos veces; se conserva la cuota OMO/ES en su lugar).

## 5. Ranking de los revisores (esta ronda)

1. **Kimi** — el único que aportó hechos nuevos y verificables (precio OMO +10 y fecha, "Road to Ample" con la estimación de demanda $70–100bn y el fin del open repo, F2 semanal, mapeo D1/D2/D3, OMO take-up como señal). Un error: "Total Reserves" sumando repos. Nivel de desk.
2. **CodeWord** — la mejor contabilidad MMT (identidad línea a línea, estados como no-gobierno, precio antes que cantidad, ventana post-régimen para percentiles, calendario fiscal). Dos errores de hecho (OMO +25, estados sin cuenta en el RBA) y uno de fecha (CLF).
3. **Perplexity** — honesto con los códigos, señaló tablas útiles (A3.1, A3.2, A4/A5, SOFIA) y el riesgo real del D2A de APRA; poco en mecánica.
4. **DeepSeek** — razonable en fiscal y umbrales; errores en OMO ("a target") y en tratar todo el SF como igual.
5. **Qwen** — buena definición de ES surplus y calendario, pero dos afirmaciones falsas graves (D1/D3 muertas → F11; ancla inventada) y BAS "trimestral" sin matiz.
6. **Claude = Gemini** — texto idéntico; lectura correcta del drenaje fiscal, pero recomendación central (API SDMX) no verificable y sin aportes de hecho.

Regla que sale de esta ronda: ninguna afirmación de precio, fecha o código entra en el config sin verificación propia en fuente primaria; los revisores sirven para encontrar lo que falta, no para fijar números.
