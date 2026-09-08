# TRIANGULACIÓN GBP COMMAND CENTER — Matriz de consenso (Fase 1 → config v0.2)

Fecha: 2026-09-08. Revisores: DeepSeek, Gemini, CodeWord, Qwen (4 respuestas formales, las cuatro **VALIDADO CON CAMBIOS**). Perplexity devolvió un resumen del documento, no una revisión: hay que repetirla pegando el prompt en el cuerpo del mensaje, no sólo el fichero.

Leyenda: ✅ validado · ⚠ validado con observaciones · ❌ rechazado · — no se pronunció.

## 1. Veredicto por punto

| Punto | DeepSeek | Gemini | CodeWord | Qwen | Decisión v0.2 |
|---|---|---|---|---|---|
| 1 Equivalencias | ⚠ | ⚠ | ⚠ | ⚠ | Ver §2 |
| 2 Capa fiscal | ⚠ | ⚠ | ⚠ | ⚠ | Ver §2 |
| 3 Transmisión | ⚠ | ⚠ | ⚠ | ⚠ | Ver §2 |
| 4 Umbrales | ⚠ (PMRR 385–540) | ✅ (375–540) | ⚠ (verificar) | ⚠ (verificar) | **Los cuatro estaban desactualizados**: el BoE publicó el 27-mar-2026 un PMRR de **£365–515 bn** (ver §3) |
| 5 Régimen | ⚠ | ⚠ (añadir régimen) | ⚠ | ⚠ | Flags ortogonales, no regímenes nuevos |
| 6 Arquitectura | ⚠ | ⚠ | ⚠ | ⚠ | Lotes verified/probationary + endurecimiento |
| 8 Lectura de hoy | FLOOR_FRICTION (sesgo) | NEUTRAL | NEUTRAL (ample) | NEUTRAL + flags | **NEUTRAL** (3 de 4). DeepSeek confunde "QT activo" con fricción; con SONIA −2 pb no hay fricción |

## 2. Cambios adoptados (consenso ≥ 3/4 o error objetivo)

| # | Cambio | Quién lo pidió | Aplicado en v0.2 |
|---|---|---|---|
| C1 | **Renombrar `net_liquidity` → `policy_balance_sheet`** ("Policy Balance Sheet (assets)"). Sin línea de depósitos de HMG (His Majesty's Government) en el Weekly Report, el constructo WALCL − TGA − RRP no es construible semanalmente. Lectura primaria semanal = reservas RPWB56A + precio (SONIA − Bank Rate) | 4/4 | `blocks.central_bank.derived.policy_balance_sheet`; buscar en el árbol *Liabilities* de la IADB una línea de depósitos públicos (`government_account.search_terms`) |
| C2 | **RPWB59A (20 533) fuera de toda métrica**: `display_only`, excluido de `policy_assets`, régimen y alertas hasta etiqueta verificada. CodeWord propone CRD (Cash Ratio Deposits); no se adopta: el esquema CRD fue sustituido por el Bank of England Levy en 2024, así que 20,5 bn no puede ser CRD | 4/4 | `unidentified_rpwb59a` |
| C3 | **Eliminar el percentil rodante sobre el NIVEL de reservas** (serie no estacionaria bajo QT); percentiles sólo sobre transformadas estacionarias (Δ% semanal, spreads) | CodeWord, Qwen | `thresholds.reserves.secondary_percentile` eliminado |
| C4 | **Escasez y fricción exigen precio persistente**: SONIA − Bank Rate ≥ 0 durante 3 sesiones o media semanal; −1 pb = *early flag* informativo, nunca régimen. Excluir quarter-end, días de recaudación y liquidaciones grandes de gilts | Qwen, CodeWord | `rates.thresholds.overnight_minus_policy_bps.secondary_absolute.persistence`; reglas SCARCITY / FLOOR_FRICTION |
| C5 | **Capa "Repo & Funding Stress"** (pendiente de fuente): GC repo − Bank Rate (WATCH +10 / STRESS +20 / CRISIS +30 pb, calibrado al pico de nov-2025), uso de la OSF (Operational Standing Facility, Bank Rate ± 25 pb) como techo de referencia y ventanilla funcional, DWF (Discount Window Facility), resultados de STR/ILTR (cobertura, tail), volumen/dispersión SONIA | 4/4 | Series `pending` en `central_bank` y `rates`; umbral `gc_minus_policy_bps` |
| C6 | **Flags ortogonales GBP**: `QT_ACCELERATION`, `REPO_DEPENDENCE_HEALTHY` / `REPO_DEPENDENCE_STRESS` (ratio (STR+ILTR)/reservas, escala sólo con precio), `GILT_SUPPLY_STRESS` (DMO tail/cover), `FISCAL_BIG_MONTH` (z ≥ 2). Nuevos flags, no nuevos regímenes | 4/4 | `regime.orthogonal_flags`; derivado `repo_dependence_ratio` |
| C7 | **CGNCR ≠ gasto neto MMT**: CGNCR es necesidad de caja (proxy de drenaje por emisión); `net_spending = gastos − ingresos` sigue siendo el flujo de NFA (Net Financial Assets). Guardar vintages ONS. Añadir PSND (deuda) como serie pendiente: JW2P son intereses, no deuda | Qwen, CodeWord | `fiscal.derived.cgncr_role`, `fiscal.series.psnd` |
| C8 | **Capa fiscal no puede girar el régimen sola** (mensual, 3 semanas de retraso): contribución capada a ±0.5 | Qwen | `fiscal.influence_cap` |
| C9 | **Subastas DMO como capa de evento** (fecha, settlement, nominal, bid-to-cover, tail, yield medio) parseadas por evento; T-bill tenders semanales | 4/4 | Series `dmo_gilt_auction`, `dmo_tbill_tender` (pending) |
| C10 | **Banca = capa de confirmación**: flujos MoM/YoY en z-score, nunca niveles; mínimo 3 series válidas o NO SIGNAL; LPMB4VH es un stock, no un tipo efectivo (esos son familia IUM/CFM) | 4/4 | `banking.signal_rule`, serie `new_lending_effective_rate` pending |
| C11 | **Ingesta IADB endurecida**: lotes *verified* vs *probationary* (un código malo no tumba los buenos), snapshot CSV bruto por petición, comprobar Content-Type (HTML → degraded), backoff exponencial con jitter, fallback al último JSON bueno en `stale`, dead-man switch tras 2 fallos, 20–30 códigos por petición (el "300" de DeepSeek no está verificado), aviso de que las IP de GitHub Actions pueden ser bloqueadas más duro que una IP doméstica; FRED sólo como fallback degradado de tipos | 4/4 | `sources.boe_iadb.batches/hardening`, `sources.fred_fallback` |
| C12 | **Pesos** → banco central 0.45 / tipos 0.35 / fiscal 0.10 / banca 0.10. Argumento de fondo (CodeWord, Qwen): en el SMF (Sterling Monetary Framework) la cantidad de reservas es endógena; el precio es la prueba de escasez. DeepSeek y Gemini aceptaban 0.50/0.30 | 2/4 + coherencia con el marco | `regime.weights` — **pendiente de tu OK** |
| C13 | Códigos candidatos aportados por DeepSeek: **RPWZ4TM** (APF loan) y **RPWZOQ4** (TFSME). Se guardan como `id_candidate` **sin verificar** (DeepSeek los marca "✅" sin fuente) | DeepSeek | Verificación en la petición secuencial |

## 3. Corrección del ancla PMRR (hallazgo propio, no de los revisores)

Los cuatro revisores discutían entre £375–540 bn (Saporta, nov-2025) y £385–540 bn (encuesta Q1-2025). Verificado hoy en la fuente primaria: el Bank of England publicó el **27 de marzo de 2026** ("Resilience and readiness across the Sterling Monetary Framework", Bank Insights) que la última encuesta sitúa el PMRR en **£365–515 bn**, por debajo de reservas de ~£640 bn; STR normalizado en ~£100 bn con >30 firmas por subasta, ILTR ~£70 bn con ~80 participantes; los repos suministran ~¼ de las reservas. Adoptado en `thresholds.reserves.primary_absolute` con regla de revisión en cada encuesta. Nota: STR+ILTR probable a 2026-09-02 (124,8 + 83,9 = 208,7 bn) es bastante mayor que las cifras de marzo, coherente con absorción ordenada del QT mientras SONIA sigue bajo Bank Rate.

## 4. Errores en el prompt (detectados por CodeWord y Qwen)

El cuerpo de `PROMPT_TRIANGULACION_GBP.md` v1 etiquetaba mal los códigos: ONS ("PSNB (RUUW)… CGNCR (J5II)… deuda (JW2P)") y Bankstats (LPMBI2O/LPMBI2P intercambiados; LPMB4VH como tipo efectivo). **El config y el Source Map eran correctos**; el prompt está corregido en v2. La matriz usa sólo el config como referencia.

## 5. Rechazado o aplazado

- Régimen nuevo `STRESS_FACILITY_DRAW` / `REPO_DEPENDENCE` (Gemini): se implementa como **flag**, no como régimen, para mantener los cinco regímenes del Desk Standard comunes a todas las monedas.
- Parser PDF del DMO Daily Cash Flow (Gemini): el documento es del Consolidated Fund / NLF, no del Exchequer, y no está claro que sea público de forma estable. Aplazado a Fase 3; primero subastas DMO por evento.
- XCCY basis GBP/USD (CodeWord): sin fuente pública gratuita; entra en la mesa macro como input externo, no en el tab GBP.
- Curva OIS/swap forward (CodeWord): mesa macro / Fase 3.

## 6. Pendiente antes de Fase 2 (orden)

1. Petición IADB **secuencial y en dos lotes** cuando se levante el bloqueo Akamai: etiquetas RPWB59A/67A/69A, candidatos RPWZ4TM/RPWZOQ4, bonos en libras, línea de depósitos públicos en *Liabilities*, Money & Credit, 2Y/5Y/20Y/30Y, XUDLUSS/XUDLERS.
2. Fuente de OSF/DWF y resultados STR/ILTR; formato de subastas DMO.
3. Calendario: MPC (Monetary Policy Committee) 2026, bank holidays, estacionalidad fiscal.
4. OK de Sander a pesos 0.45/0.35 y a config v0.2 → Fase 2 (providers BoE/ONS, `gbp/index.html`, carril `gbp`, sitio `gbp-command-center`).
