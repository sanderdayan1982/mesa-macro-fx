# TRIANGULACIÓN NZD — matriz de decisiones (2026-09-08) → config/nzd.json v0.2

Seis textos pegados; **cuatro revisiones reales** (Gemini, Qwen, DeepSeek, CodeWord) y dos que sólo resumieron el mapa sin revisar nada (Perplexity, Kimi K3). Regla de la casa: todo lo que un revisor afirma se verifica en primaria antes de tocar el config; lo no verificable queda marcado.

## Ranking de esta ronda

1. **CodeWord** — la única que encontró dos errores de diseño de fondo: la corrección del spread con el swap a 1 año sobre-corrige (12 meses de subidas contra un bill de 30 días) y `omo_reliance_share` sube mecánicamente al vaciarse el denominador. También el calendario fiscal (IRD) y el turnover del tramo largo como canario exterior. Fallo: los crons EventBridge de 6 campos son de otra plataforma (aquí es GitHub Actions).
2. **Qwen** — precisa y accionable: T+1 en T-bills (verificado), página HTML de resultados antes del Excel (verificado), flag de cupones, festivos con Matariki y aniversarios, lectura correcta del ORRF.
3. **DeepSeek** — la lista más completa de lo que falta (BKBM, OIS, D35 Kauri, ECP de NZDM, festivos, on-issue), y honestidad sobre lo que no pudo confirmar (T+1). Umbrales "RECHAZADO" es exagerado: eran ya DESK PROPOSAL.
4. **Gemini** — sólida, sin errores, pero sin aportar nada que no estuviera ya en el mapa salvo el OIS.
5. **Perplexity = Kimi** — cero revisión.

## Verificaciones hechas hoy a raíz de la ronda

| Afirmación del revisor | Fuente primaria | Resultado |
|---|---|---|
| T-bills liquidan T+1 (Qwen); "no lo asumas" (CodeWord, DeepSeek) | debtmanagement.treasury.govt.nz/tender/treasury-bill-tender-1887 | **T+1 confirmado**: tender martes 08-sep-2026, settlement miércoles 09-sep |
| NZDM publica el resultado en HTML antes del Excel (Qwen, DeepSeek, Gemini) | páginas `/tender/treasury-bill-tender-<n>` y `/tender/nominal-bond-tender-<n>` | **Confirmado**: cierre 14:30 NZT, resultados 14:35; el tender 1887 tiene **tres series** (18-nov-2026 100/100 2,55×; 10-mar-2027 100/100 3,65×; 25-ago-2027 **ofrecido 50, adjudicado 25** a 3,3675 %) → el 2,55× del mapa era sólo la primera serie; nueva métrica `tbill_allocation_ratio` |
| Bonos T+3 | tender 1007: jueves 03-sep → martes 08-sep | Confirmado; dos líneas (may-2030 4,05×, abr-2037 4,38×; tails 0,5 y 0,8 pb) |
| BKBM de la NZFMA como fuente mejor que B2 (DeepSeek, CodeWord, Qwen) | nzfbf.co.nz/benchmarks/bkbm | El fixing es a las **10:20 NZT** (1/3/6 m; 2/4/5 interpolados), administrado por NZFBF; los bank bills del B2 son cierres NZFMA/LSEG. **Feed público no verificado** → pendiente Fase 3 |
| NZ OIS a 1–3 m (todos) | — | **No existe feed público**; no se proxifica |
| Festivos NZ (Qwen, DeepSeek, CodeWord) | employment.govt.nz | Lista 2026–2027 verificada e incorporada (incl. aniversarios Wellington/Auckland, Matariki 10-jul-2026 / 25-jun-2027) |
| Fechas fiscales IRD (CodeWord) | ird.govt.nz payment dates for provisional tax | Provisional 28-ago / 15-ene / 7-may (ratio: +28-jun, 28-oct, 28-feb) verificado; GST 28 / PAYE 20 pendientes del calendario IR328 |
| Nivel "suficiente" de settlement cash (todos: no existe) | discurso 19-mar-2026 + marco RBNZ | Confirmado; pre-COVID 6–8 bn (DeepSeek) coincide con D12 (2019) |

## Cambios N1–N15 aplicados en v0.2

| # | Cambio | Origen | Estado |
|---|---|---|---|
| N1 | Anclas de settlement cash 20/15/10/7 bn se quedan como **dead-man switch**, `regime_trigger: false`, nunca disparan régimen; percentil-primario **rechazado** (la serie cae por diseño → WATCH permanente) | DeepSeek, CodeWord, Qwen | aplicado |
| N2 | `omo_reliance_share` se lee con `omo_outstanding` absoluto (umbrales propios) y `omo_outstanding_4w_change`; la fase de balance usa el stock absoluto | CodeWord | aplicado |
| N3 | **Se elimina la resta del swap 1 a** del spread de estrés; el bill 30 d − OCR se clasifica en crudo (ventana desde el inicio del ciclo 08-jul-2026 o 250 sesiones) + anclas; `hike_pricing_bps` y `bill_curve_slope_bps` (90 d − 30 d) son contexto y puerta de la escasez ("no explicado por expectativas") | CodeWord | aplicado |
| N4 | `autonomous_flow_daily` → `residual_flow_daily`: coincidente y ruidoso, con banda ± de reconciliación con D10, días de cupón / vencimiento / venta LSAP etiquetados y excluidos de FISCAL_BIG_DAY; el régimen fiscal sólo lo usa con banda estrecha | CodeWord, Qwen, DeepSeek, Gemini | aplicado |
| N5 | Parser primario = **HTML de resultados NZDM 14:35 NZT** (T-bills T+1, bonos T+3); Excel fechado = histórico; cobertura ponderada por volumen entre series; `tbill_allocation_ratio` y `tbill_1y_yield` nuevas | Qwen, DeepSeek | aplicado (verificado) |
| N6 | Cobertura y tail de tenders **topan en WATCH** salvo persistencia (2 de los últimos 3 tenders) — 450 M pueden quedar mal cubiertos por composición | CodeWord | aplicado |
| N7 | Canarios diarios/semanales de demanda exterior: bond-swap 10 a y `long_end_turnover_share` (D9 por línea ≥ 2034); D30 sigue mensual | CodeWord, Qwen, DeepSeek | aplicado |
| N8 | Core funding ratio: display + puerta RED, fuera del score; bloque 3 aceptado como el más lento (sin crédito semanal desde 2021) | CodeWord, DeepSeek, Qwen | aplicado |
| N9 | Flags nuevos: FX_SWAP_ACTIVE, TBILL_UNDERALLOCATED, COUPON_PAYMENT_DAY, BOND_MATURITY_DAY, LSAP_SALE_DAY, TAX_DAY; series D35 Kauri y ECP de NZDM (pendientes de pull) | DeepSeek, Qwen, CodeWord | aplicado |
| N10 | Overlay OMO_DEPENDENCE con persistencia (2 observaciones consecutivas) | CodeWord | aplicado |
| N11 | INJECTION/DRAIN **se mantienen**: enum estándar de la mesa (describen flujo de reservas, la escasez va por precio); aritmética del score comprobada (máx 1,275) | CodeWord (rechazado) | rechazado con nota |
| N12 | Crons EventBridge de 6 campos | CodeWord | rechazado (GitHub Actions, 5 campos) |
| N13 | Festivos 2026–2027 + regla de frescura consciente de festivos + DST | Qwen, DeepSeek, CodeWord | aplicado (verificado) |
| N14 | Calendario fiscal IRD → flag TAX_DAY para interpretar el residuo | CodeWord | aplicado (parcial: GST/PAYE pendientes) |
| N15 | BKBM/NZFBF y OIS: BKBM pendiente de feed público (Fase 3); OIS no disponible | DeepSeek, CodeWord, Gemini | documentado |

## Lectura consensuada de hoy

Los cuatro revisores reales coinciden: **NEUTRAL con overlay OMO_DEPENDENCE en ascenso, sin estrés** — ORRF en cero, overnight pegado al OCR, OMO ≈ 20 % del settlement cash como mecánica intencionada del nuevo marco, bill 30 d − OCR +20 pb explicado por el ciclo de subidas (2 a +86 pb sobre OCR), tenders bien cubiertos (4,05×/4,38× bonos; 2,55–3,65× T-bills con una sub-adjudicación en el año). Coincide con la lectura del config.

## Pendiente para Fase 2

On-issue NZGB → calendario de cupones/vencimientos; L1, S40, B20/B21, D35, ECP, D9 por línea, swaps 1/2/10 a; IR328 (GST/PAYE); BKBM feed (Fase 3); parser del Tesoro (Fase 3). Sitio: `mesa-macro-fx-g8-commands-centers.netlify.app/nzd/`.
