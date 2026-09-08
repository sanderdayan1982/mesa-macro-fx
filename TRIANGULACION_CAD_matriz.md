# Triangulación CAD Command Center — Matriz de consenso y decisiones

2026-09-08 · 4 revisiones externas (R1–R4) + verificación propia contra fuentes primarias · Resultado: **Fase 1 pasa a v0.3**

Leyenda: ✔ acepta · ✘ rechaza · ~ acepta con matices · — no se pronuncia. La columna "Verificado" indica lo que comprobé yo contra la fuente oficial antes de decidir; lo no verificado queda como `pending` en el config.

## A. Matriz de discrepancias

| Punto | R1 | R2 | R3 | R4 | Verificado | Decisión v0.3 |
|---|---|---|---|---|---|---|
| Restar billetes (V36625) en Net Liquidity | ✔ restar | ✔ restar | ~ línea aparte | ✘ no restar | — (conceptual) | **No se resta.** Se mantiene Total assets − GoC deposits − SRA para comparabilidad con WALCL − TGA − RRP en las ocho monedas. Los billetes pasan a métrica propia `currency_drain` (drenaje autónomo) y a `reserves_ex_currency_effect`. Razón: WALCL − TGA − RRP tampoco resta el efectivo; restarlo en CAD rompería la mesa macro. |
| Spread de estrés: CORRA − target vs CORRA − deposit rate | target | deposit (= target − 25) | deposit (= target − 5) | banda ±25 | **Sí**: notice BoC 2025-01-29, deposit rate = target − 5 pb desde 2025-01-30; Bank Rate = target + 25 | **CORRA − deposit rate** es el análogo de SOFR − IORB (primario). CORRA − target queda como secundario (desviación del objetivo). Se añade `band_position` (0 = suelo, 1 = techo). R2 y R4 erraron el corredor. |
| Rango objetivo de saldos de liquidación | 20–60B (Mar 2024) | 50–70B | 50–70B (Gravelle) | — | **Sí**: Gravelle, 2025-01-16: 50–70B (20–30B pagos + precautorio) | **50–70B como umbral absoluto primario**; percentiles pasan a secundario. R1 citó el rango anterior. |
| Ventana de percentiles | 6 meses | 3 años ok | 3 años ok (o 2) | — | — | **Se mantienen 3 años para flujos** (WoW %, spreads). 6 meses (~26 obs semanales) hace inservible un p97. Para niveles con ancla institucional (reservas) el absoluto manda. |
| Peso capa fiscal (era 0.30) | 0.15–0.20 | 0.15–0.20 | 0.20–0.25 | 0.20 | — | **0.20**. Pesos finales: banco central 0.45 · tipos 0.25 · fiscal 0.20 · transmisión 0.10. |
| V36875 "Deposits of banks" como borrowings | ✘ | ~ pobre | ~ indirecto | ✘ | — | **Rechazado como proxy.** Queda `display_only`. El estrés interbancario se lee de la dispersión de CORRA (p95 − p5) y del volumen CORRA. |
| Separar term repo de overnight repo | ✔ | ✔ | ✔ | ✔ | **Sí**: BoC hace term repo 1M/3M quincenal desde 2025 | **Sí.** La línea B2 (V44201362) es agregada; el detalle sale de los grupos Valet OR_RESULTS / ORR en el carril de eventos. |
| Advances > 0 como alerta absoluta | ✔ | ✔ | ✔ | ✔ | — | **Sí**, binaria. |
| Régimen adicional | — | FISCAL_* | transición post-QT | FLOOR_FRICTION + flag transmisión | — | **Se añade FLOOR_FRICTION** (reservas en rango, CORRA por encima del target: fricción de distribución, no escasez). La transición post-QT es una **etiqueta de fase** informativa (`balance_sheet_phase`), no un régimen. **TRANSMISSION_FAILURE** es flag ortogonal, no régimen. FISCAL_* queda dentro del bloque fiscal. |
| Excluir precios del tab CAD | ✔ | ✔ | ✔ | ✔ | — | Confirmado 4/4. |
| Fuente fiscal diaria | ninguna | ninguna | ninguna | **Receiver General Daily Cash Balance** | **Sí**: open.canada.ca, CSV diario, saldo de cierre en BoC + term deposits + fondo prudencial; última fila 2026-09-01 vista el 2026-09-08 | **Hallazgo mayor.** La capa fiscal CAD pasa de semanal a **diaria**, con Z-score de 30 días como en el DTS. Calidad de equivalencia sube a medium-high. |
| JSON en git | — | metadatos versionados | crecimiento del repo | ✘ antipatrón, bucket | — | **Se mantiene git** (flujo GitHub-web-UI del operador, auditoría por commit) con mitigaciones: JSON "latest" compacto + histórico CSV append-only, un workflow con matriz y concurrency por moneda, heartbeat `generated_at`, keepalive mensual contra la desactivación de crons a 60 días, `Cache-Control: no-cache` en Netlify. Se revisa si el repo supera 500 MB. |
| Tablas StatCan de crédito | 10-10-0114-01, 33-10-0006-01 | "verificar" | 10-10-0109-01, 36-10-0640-01, V1231415582 | 36-10-0639-01, 36-10-0619-01 | **No** (cuatro respuestas, cuatro juegos de IDs) | Todas quedan como `statcan_candidates`; la ingesta las resuelve contra la API WDS antes de usarlas. Ningún ID de StatCan se da por bueno hoy. |
| Error MMT en el prompt ("la emisión destruye NFA") | — | — | — | ✔ señalado | — | **Corregido**: la emisión drena reservas, no cambia el stock de NFA. Reserve impact y creación de NFA son dos líneas separadas en el bloque fiscal. |

## B. Lectura de hoy (2 sept 2026) — dispersión de los revisores

| Revisor | Régimen | Argumento |
|---|---|---|
| R1 | LIQUIDITY_SCARCITY | reservas −10B en una semana + CORRA > target |
| R2 | LIQUIDITY_DRAIN | dentro del rango 50–70B, CORRA +10 pb sobre deposit rate sin pánico |
| R3 | LIQUIDITY_DRAIN moderado | idem, fase de transición post-QT |
| R4 | NEUTRAL + WATCH | dentro del rango, fricción menor |

Con las reglas v0.3 el motor daría: reservas 64.3B **dentro del rango** (no SCARCITY), CORRA − deposit = **+10 pb** (= STRESS absoluto secundario, `band_position` 0.33), caída semanal de reservas −13 % → **LIQUIDITY_DRAIN con flag FLOOR_FRICTION**. Es decir, la posición intermedia de R2/R3 con la fricción de R1 hecha explícita. Que un revisor declarara escasez y otro neutral con los mismos números es exactamente el hueco que FLOOR_FRICTION cierra.

## C. Sugerencias no adoptadas (y por qué)

- CORRA−OIS 1M/3M, cross-currency basis CAD/USD, LCR/NSFR de OSFI, Lynx throughput: útiles pero sin fuente pública gratuita o de frecuencia útil; van al backlog del Desk, no al tab CAD.
- Bankers' Acceptances y spread BA−OIS (R4): el mercado de BA desapareció con el cese de CDOR en junio de 2024; la sugerencia está desactualizada.
- Object storage (S3/R2/Supabase) en lugar de git: contradice el flujo de trabajo del operador y pierde la auditoría por commit; se difiere con mitigaciones.
- Ventana de percentiles de 6 meses: estadísticamente insuficiente para p97.

## D. Fuentes primarias verificadas en esta ronda

- Bank of Canada, "Bank of Canada announces an adjustment to the deposit rate and some changes to terms and conditions for Overnight Reverse Repo Operations", 2025-01-29 — deposit rate = target − 5 pb desde 2025-01-30.
- Bank of Canada, Toni Gravelle, "The end of quantitative tightening and what comes next", 2025-01-16 — rango 50–70B; term repo 1M/3M quincenal; letras desde Q4 2025; bonos hacia finales de 2026; "no será QE".
- Open Government Portal, Public Services and Procurement Canada, "Daily Cash Balance" (dataset 477bf61b-e764-4f24-8a8a-687a5755002e) — CSV diario, columnas: fecha, saldo de cierre en BoC, term deposits outstanding, fondo de liquidez prudencial; última fila 2026-09-01.
- Bank of Canada Valet API — series verificadas el 2026-09-08 (sección 2 de la Fase 1).
