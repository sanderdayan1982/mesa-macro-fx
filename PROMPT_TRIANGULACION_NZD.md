# PROMPT DE TRIANGULACIÓN — NZD COMMAND CENTER (Fase 1)

> Instrucciones para Sander: pega este prompt completo **en el cuerpo del mensaje** de cada AI (CodeWord, Kimi, Perplexity, DeepSeek, Gemini, Qwen, Claude). Adjunta `FASE1_NZD_Source_Map.md` y `config/nzd.json`. Pide la respuesta en el formato exacto del bloque final. Regla de la casa: los revisores señalan huecos; ningún precio, código, tabla o fecha que propongan entra en el config sin que yo lo verifique en la fuente primaria.

---

Actúa como un jefe de mesa macro institucional de FX (Foreign Exchange) con experiencia real en la implementación de la política monetaria del Reserve Bank of New Zealand (RBNZ), en el mercado monetario neozelandés (ESAS, Exchange Settlement Account System; bank bills BKBM; repo con NZGB), en New Zealand Debt Management (NZDM) y el Tesoro, y en el marco MMT (Modern Monetary Theory) / Mosler, con criterio de ingeniería de datos. No eres un asistente amable: eres un revisor que busca errores, huecos y supuestos no verificados. Si algo está bien, dilo en una línea y sigue. No inventes tablas del RBNZ, identificadores de series ni URL: si no estás seguro, dilo. Aviso: el "NZD Command Center V3.1" anterior era una maqueta con datos estáticos; no lo uses como referencia.

## Contexto

Soy un operador macro FX individual. Opero las ocho monedas del G8 (USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF) leyendo la liquidez de cada moneda bajo el marco MMT/Mosler: el gasto del gobierno crea activos financieros netos para el sector no gubernamental, los impuestos los destruyen, la emisión de bonos drena reservas pero no cambia ese stock, el banco central fija el precio de las reservas y no la cantidad.

Tengo en producción cinco dashboards sobre un Desk Standard triangulado: **CAD** (Bank of Canada Valet + Receiver General diario), **GBP** (BoE IADB + ONS), **AUD** (RBA CSV diario), **JPY** (BoJ XLSX diario + API + MoF) y **CHF** (portal SNB + AFF). El estándar: cuatro capas con título en orden fijo (banco central → tesoro o equivalente → transmisión bancaria → tipos), estados `fresh / stale / proxy / degraded / unavailable`, umbrales por percentiles rodantes con histéresis más anclas absolutas institucionales, regímenes LIQUIDITY_INJECTION / DRAIN / SCARCITY / FLOOR_FRICTION / NEUTRAL con la escasez confirmada por el precio y nunca sólo por la cantidad, flags ortogonales, ingesta Python en GitHub Actions, JSON estático en Netlify. Prioridad absoluta: datos diarios y semanales.

Ahora paso al **NZD**. He verificado hoy (8-sep-2026) en rbnz.govt.nz/statistics, en los ficheros Excel del RBNZ (`hd12.xlsx`, `hd3.xlsx`, `hb2-daily-close.xlsx`, `hr1/hr3/hd10/hd9/hd30/hc5/hc50/hl2.xlsx`), en debtmanagement.treasury.govt.nz y en treasury.govt.nz:

- **Sistema de suelo**: todo el settlement cash se remunera al OCR (Official Cash Rate). ODR (Overnight Deposit Rate) = OCR = **2,75 %** desde el 3-sep-2026 (subida de 25 pb en el MPS del 2-sep; antes 2,50 desde el 8-jul y 2,25 desde nov-2025; CPI 4,1 % a/a; "el OCR puede tener que subir más"). ORRF (Overnight Reverse Repurchase Facility) = OCR + 50 = 3,25 %. Bond Lending Facility a OCR − 50. Próximas decisiones: 28-oct-2026, 9-dic-2026 (MPS); ocho al año desde 2027.
- **Settlement cash** (tabla D12, diaria T-1, 15:00 NZT): **24 588 M** el 7-sep-2026; 26 785 → 24 175 → 24 507 → 24 588 en las últimas sesiones; uso del ORRF 0; FX swaps 0. Historial diario desde 1999 en un solo fichero.
- **Nuevo marco de gestión de liquidez desde el 2-abr-2026** (discurso 19-mar-2026, A. Richardson, Director Financial Markets; página "Key facilities" actualizada 2-abr-2026): OMO (open market operations) de **reverse repo semanales, jueves 11:30–11:45 NZT, a 7 y 28 días, full allotment, tipo flotante OCR + 10 pb**, colateral NZGB / RB Bills / Kauri / LGFA. Tabla D3: 3-sep-2026 **5 023 M a 7 d + 45 M a 28 d**; semanas anteriores 1 671 + 1 050 (2-abr), 3 590 + 400 (9-abr)… El RBNZ **no** publica un nivel objetivo de settlement cash: "ample" se juzga por tipos cortos cerca del OCR y liquidación fluida. El FLP (Funding for Lending Programme) está totalmente repagado (dic-2025); el Term Lending Facility, cerrado.
- **LSAP (Large Scale Asset Purchase) unwind**: tenencias LSAP 11 860 M (R1, jul-2026; 29 218 en jul-2024); ventas mensuales a NZDM de **415 M** (17-ago-2026; acumulado 20 830 M); recompras anticipadas de NZGB próximos a vencer (57 M en feb-2026). Balance total 73 237 M; reverse repos 15 926 M; depósitos 55 428 M; circulante 10 241 M.
- **Crown Settlement Account** (CSA): sólo mensual — R3 (día 14): **29 080 M** (jul-2026); saldos de instituciones de liquidación 25 819. D10 (último día del mes siguiente): "Government cash influence" **+6 846 M** en julio; bonos emitidos −7 840 (incluye la sindicación del 15-may-2038 por 7 000 M); T-bills −1 001 / +1 705; FX +266; net reverse repos +540; net FX swaps +1 154. No existe un estado diario de caja de la Corona; los estados financieros mensuales del Tesoro llegan con ~6 semanas (11 meses a mayo = último).
- **NZDM**: T-bills los martes 14:00–14:30 NZT — tender 1887 (8-sep-2026): 100 M ofrecidos, 255 M pujados (**2,55×**), wavg **2,8775 %**, vence 18-nov-2026. Bonos los jueves — tender 1007 (3-sep-2026): línea 15-may-2030 4,5 %, 275 M, pujado 1 115 M (**4,05×**), wavg 4,0227 %, highest accepted 4,0275 (tail 0,5 pb). Calendario de septiembre: cuatro tenders de 450 M (3/10/17/24-sep), 1 800 M; liquidación T+3 hábiles. Programa 2026/27 NZ$ 34 bn (BEFU 28-may-2026). Ficheros históricos con el nombre fechado (`Tbills-tender-history-2026-09-08.xlsx`).
- **Tenencias**: D30 (jul-2026) — NZGB nominales 206 463 M, de los que **118 400 M (57 %) en no residentes**; gobierno central (incl. RBNZ) 10 978.
- **Tipos** (B2 diario, 7-sep-2026): bank bills 30/60/90 d **2,95 / 3,00 / 3,06**; NZGB 1/2/5/10 a 3,10 / 3,61 / 4,21 / 4,78; swap 2-10 75 pb; overnight interbank **sólo se publica los días con cruces** (2,83 el 3-sep, 2,57 el 1-sep). Turnover semanal de NZGB (D9): 71 033 M la semana al 4-sep.
- **Bancos** (jul-2026): vivienda 401 944 M (+5,6 % a/a), empresas 142 861 (+4,4 %), agro 65 238 (+2,4 %); broad money 458 490; core funding ratio **89,2 %** (mínimo 75 %). Los flujos semanales de crédito (C65/C66) se discontinuaron en abril de 2021.

## Regla de diseño obligatoria

Capas con título visible, en este orden: 1 liquidez del banco central; 2 Tesoro / NZDM; 3 transmisión bancaria; 4 tipos y mercado monetario; 5 régimen, alertas, agente, calidad, histórico. Ninguna métrica se elimina porque la fuente sea difícil: se muestra con su estado. Prioridad a lo diario/semanal; mensual sólo cuando no haya más remedio.

## Lo que te pido revisar (adjunto `FASE1_NZD_Source_Map.md` y `config/nzd.json`)

Responde punto por punto: VALIDADO, VALIDADO CON OBSERVACIONES o RECHAZADO, y por qué.

**1. Equivalencias NZD ↔ USD ↔ resto de la mesa.**
- Reservas: uso el **settlement cash diario (D12)** como WRESBAL. Anclas de cantidad propuestas (dead-man switch, no del RBNZ): ample > 20 bn, WATCH < 15, STRESS < 10, CRISIS < 7 bn. ¿Conoces alguna estimación pública del RBNZ del nivel "suficiente" de settlement cash tras la Liquidity Management Review (Bulletin, discursos, consulta 2025, Financial Stability Report)? Cita título y fecha o di "no conozco ninguna".
- **Métrica estructural nueva: `omo_reliance_share` = stock vivo de OMO / settlement cash** (≈ 20 % ahora; anclas 30 % / 45 % propuestas). ¿Es la lectura correcta del tránsito de reservas creadas por el LSAP a reservas suministradas por el RBNZ? ¿Cómo distinguirías demanda precautoria de demanda estructural en una operación full allotment a precio fijo?
- **Spread de estrés = bank bill 30 d − OCR** (diario; anclas 25/40/60 pb propuestas; persistencia 3 sesiones; confirmación por overnight interbank ≥ OCR + 10 o uso del ORRF; corrección por `hike_pricing_bps` = swap 1 a − OCR). El overnight interbank del B2 es escaso. ¿Hay una fuente diaria mejor para el precio del efectivo overnight (NZFMA, BKBM fixings, NZ OIS)? ¿El bill a 30 días es demasiado contaminado por expectativas en un ciclo de subidas? ¿Qué nivel de bill − OCR es "normal" en el suelo neozelandés?
- Techo: ¿el uso del ORRF (D12) aparece de verdad en la tabla cuando ocurre, o hay contrapartes que lo usan sin que se publique el mismo día?
- **Huella fiscal diaria derivada**: `autonomous_flow_daily` = Δ settlement cash − Δ OMO vivo − Δ FX swaps − Δ ORRF ≈ Corona + circulante + flujos de bonos. ¿Es una derivación válida o hay flujos del RBNZ (compras de reservas exteriores, ventas LSAP, cupones de la cartera) que la contaminan a diario? ¿Cómo reconciliarías con D10 cada mes?

**2. Capa fiscal (Tesoro / NZDM).**
- No hay DTS neozelandés. Propongo CSA mensual (R3) + D10 mensual + tenders semanales + calendario de tenders + derivación diaria. Peso 0,15. ¿Conoces alguna publicación de mayor frecuencia de la caja de la Corona (Treasury, NZDM "cash management", Crown Settlement Account) o de la posición de caja de NZDM (Euro-Commercial Paper, depósitos)?
- ¿Cuál es la convención de liquidación de los T-bills (T+1?) y de los bonos (T+3 confirmado en el calendario)? ¿Publica NZDM el resultado del tender en una página HTML antes de actualizar el Excel?
- Umbrales de tenders propuestos: coverage < 2,0 WATCH, < 1,5 STRESS; tail (highest accepted − wavg) 2/4/8 pb; T-bill − OCR ±25/40 pb. ¿Razonables para tenders de 450 M semanales? ¿El tail se calcula así en la práctica neozelandesa?
- Con un 57 % de NZGB en no residentes, ¿qué serie mensual o semanal sirve de "canario" de demanda exterior además de D30 (D31 por bono, turnover D9, bond-swap spread)?

**3. Transmisión bancaria.** C5, C50, L2 mensuales. ¿Faltan series clave (L1 mismatch, S40 depósitos, B20/B21/B30 hipotecarios, B6/B7 yields y costes, Kauri D35)? ¿El core funding ratio a 89 % con mínimo 75 % dice algo sobre liquidez NZD o es sólo regulatorio?

**4. Umbrales.** Todas las anclas absolutas son DESK PROPOSAL (ver config). ¿Conoces documentos del RBNZ que cuantifiquen la demanda de settlement cash, el tamaño "normal" de las OMO semanales, el rango normal de bill − OCR, o el uso histórico del ORRF? Cita título y fecha; no inventes.

**5. Régimen.** Pesos propuestos banco central 0,40 / tipos 0,30 / fiscal 0,15 / bancos 0,15. Overlay `OMO_DEPENDENCE` (mínimo 2 de: omo_reliance_share ≥ WATCH, omo_takeup_wow ≥ WATCH, bill 30 d − OCR ≥ WATCH, coverage de bonos ≤ WATCH). Flags: STANDING_FACILITY_USED, OMO_TAKEUP_SURGE, OMO_RELIANCE_RISING, FLOOR_LEAK, FISCAL_BIG_DAY, SUPPLY_AHEAD, TENDER_WEAK, TENDER_TAIL, FOREIGN_DEMAND_FADE, LSAP_SALE_MONTH, BOND_MATURITY_MONTH, MPC_WEEK, TRANSMISSION_FAILURE, DATA_DEGRADED. ¿Sobra o falta alguno? ¿Cómo leerías un settlement cash que cae mientras el RBNZ sube tipos y las OMO semanales crecen?

**6. Arquitectura.** Lanes: diario 04:00 UTC (+ reintento 06:00) tras la publicación de las 15:00 NZT (B2 + D12 + D3); martes 03:00 UTC (T-bills); jueves 03:00 UTC (OMO + bonos); lunes (D9); mensual 3/15/19 + backfill día 1. Ficheros Excel del RBNZ con URL estable y todo el historial; ficheros NZDM con nombre fechado (el parser lee la página Data). ¿Conoces la hora real de publicación de D12/D3/B2 (¿siempre 15:00 NZT?), la de R1/R3 y D10, y los festivos neozelandeses que dejan huecos? ¿Existe una API del RBNZ (JSON/CSV) además de los Excel?

**7. Lo que falta.** Lista concreta de fuentes primarias neozelandesas que no estoy usando y deberían estar (NZFMA BKBM, NZ OIS, NZClear, RBNZ FX intervention data, NZDM cash management, Kauri issuance, calendario de vencimientos y cupones NZGB en formato máquina, festivos).

**8. Lectura de hoy.** Datos verificados (7/8-sep-2026): settlement cash 24 588 M (−2,2 bn en una semana), OMO 5 068 M (≈ 20 % del settlement cash), ORRF 0, OCR 2,75 recién subido, bill 30 d − OCR +20 pb, 2a NZGB 3,61 (+86 pb sobre OCR), 10a 4,78, T-bill 2,55× a 2,88 %, bono may-2030 4,05×, CSA 29 080 M (jul), gov cash influence +6 846 M (jul), 57 % de NZGB en manos extranjeras. ¿Qué régimen de liquidez NZD declararías y por qué? ¿Cómo lees un RBNZ que sube tipos mientras el settlement cash del LSAP se agota y lo repone con OMO semanales?

## Formato de respuesta obligatorio

```
VEREDICTO GLOBAL: [VALIDADO / VALIDADO CON CAMBIOS / RECHAZADO]
1. EQUIVALENCIAS: [estado] — [observaciones]
2. CAPA FISCAL: [estado] — [observaciones + fuentes Tesoro/NZDM]
3. TRANSMISIÓN BANCARIA: [estado] — [observaciones + tablas confirmadas o no]
4. UMBRALES: [estado] — [observaciones + ancla de reservas con fuente y fecha, o "no conozco ninguna"]
5. RÉGIMEN: [estado] — [observaciones]
6. ARQUITECTURA: [estado] — [observaciones]
7. LO QUE FALTA: [lista concreta]
8. LECTURA DE HOY: [régimen + justificación en 5 líneas]
TRES CAMBIOS PRIORITARIOS: [los tres que harías antes de escribir código]
```

No propongas ejecución automática de operaciones, ni análisis técnico, ni gestión de riesgo: eso está fuera del alcance.
