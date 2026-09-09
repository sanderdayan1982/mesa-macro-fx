# EUR — calibración empírica del régimen dual (A + B), 2026-09-09

Replay as-of semanal sobre los viernes del WFS (Weekly Financial Statement) 2016-01 → 2026-09 (557 semanas; `ingest/calibrate.py --ccy eur --fixtures fixtures/eur_hist --era 2022-09-14`). Datos primarios capturados hoy del ECB Data Portal (Banco Central Europeo): ILM diario — cuentas corrientes, facilidad de depósito y MLF (Marginal Lending Facility) desde 2005; exceso de liquidez, reservas mínimas, NLIQ y TOMO (Total Open Market Operations) existen en el portal sólo desde 2024-09-27, así que antes el replay usa exceso = CC + DF − reservas mínimas (primer requerimiento publicado, 162,9 bn, constante: ±40 bn sobre un stock de 1,5–4,7 tn) y TOMO = MRO + LTRO semanales llevados al día —; WFS semanal desde 2005/2009; depósitos del Gobierno: el desglose semanal L050100 sólo existe desde 2025-W45, el replay usa L050000 (pasivos frente a residentes del área en euros, ≈ 90 % Gobierno) en toda la muestra; EUR/USD de referencia desde 1999; tipos oficiales desde 1999; €STR (Euro Short-Term Rate) desde 2019-10; ficheros APP/PEPP (Asset Purchase Programme / Pandemic Emergency Purchase Programme); Emissionshistorie de la Finanzagentur 1999–2026 (2.319 líneas de subasta, mismo parser que en vivo). Retardos aplicados: WFS +4 d, TARGET/BSI/MIR +60 d, IRS +45 d, APP/PEPP +32 d, GFS regla de 90 d del bloque. Detalle en `calibration/eur/`.

## Eras y muestra válida

QE (Quantitative Easing) con tipos negativos 2015-03 → 2022-07 (exceso 0,1 → 4,7 tn; BC en INYECCIÓN el 65 % de 2020–22 con QE y TLTRO — Targeted Longer-Term Refinancing Operations); **suelo con QT (Quantitative Tightening) desde el DFR (Deposit Facility Rate) positivo, 14-sep-2022**: reembolsos TLTRO y vencimientos APP/PEPP, exceso 4,7 → 2,2 tn: **208 semanas**, la era comparable con el config (anclas E5/E8, TOMO 30/100/250 bn, €STR − DFR); sub-era desde el DFR 2,00 de junio-2025 (primera subida 2026-06-17): 65 semanas.

## Control FX: nada, como en las otras siete

BC ρ +0,04/+0,05/+0,03 (5/10/20 sesiones, p > 0,2, n 557); Tesoro 0,00/−0,03/−0,04; en la era −0,05/−0,01/−0,05 y +0,08/+0,08/−0,02, ninguna p < 0,25; walk-forward a 20 sesiones cambia de signo (2020–21 −0,31 · 2022–23 +0,23 · 2024–25 −0,02); ningún corte sobrevive; OLS sin bloque significativo; sin pesos duales.

## A. Frecuencia en la era QT (208 semanas)

**BC:** puntuación continua (media de nivel + Δ5s/exceso + Δ20s/exceso + fase + TOMO × 2): p10 −0,80 · p20 **−0,64** · p50 −0,25 · p80 +0,12 · p90 **+0,27**. Con ±0,5: INYECCIÓN **4 %** (0 % en 2024 y 2026), DRENAJE 30 % (19 % → 47 % por año). Es la era del drenaje (−2,5 tn de exceso) y el bloque lo dice; lo que no puede decir es la inyección, porque la fase QT (−0,5) y el TOMO en WATCH (130 de 208 semanas hasta que las TLTRO acabaron) son niveles que restan siempre. Cortes naturales: **INJECTION ≥ +0,25** (10 %), **DRAIN ≤ −0,6** (22 %; y es exactamente el corte que sobrevive la verdad de funding, abajo). Percentiles del Δ5s del exceso en la era: p10 −49 bn / p90 +26 bn (p3/p97 −178 / +103 bn: los reembolsos TLTRO); sub-era −34 / +14 bn.

**Tesoro (0,5 impulso + 0,35 estructural + 0,15 subastas):** p10 −0,11 · p20 **−0,04** · p50 +0,34 · p80 **+0,70** · p90 +0,89; INYECCIÓN 38 % (48 % en 2023, 25 % en 2025), DRENAJE **0 %**: el déficit estructural del área (−3,1 % PIB → componente +1,0 × 0,35) pone un suelo de +0,35 y el bloque no puede drenar por diseño. La regla semanal del impulso (p80/p20 a 156 s) reparte 12 % / 12 % por construcción. Propuesta: INJECTION ≥ +0,70 (salida +0,56), "ritmo débil" ≤ −0,04 (salida +0,17) y que el componente estructural pese como nivel (0,25) en v0.3 para que el drenaje fiscal pueda existir (13 s de acumulación de depósitos). Percentiles del impulso 4 s: p20 −9,3 bn / p80 +21,2 bn (sub-era −9,5 / +11,9).

## B. Verdad de funding (€STR − DFR, era: p10 −10,0 pb · mediana −8,7 · p90 −6,8): **la validación más fuerte de las ocho**

BC vs Δ spread: **ρ −0,31 a 4 semanas y −0,33 a 12 (p < 0,0001, n ≈ 200)**; por año −0,25 / −0,15 / −0,22 / −0,14 (4 s) y −0,21 / −0,31 / −0,28 (12 s): no es la tendencia de la era, se repite dentro de cada año. Medias condicionales a 12 semanas: DRENAJE **+0,48 pb** (n 58) · NEUTRAL +0,10 (130) · INYECCIÓN −0,41 (8). Umbrales que sobreviven: **DRAIN ≤ −0,6** (Δ +0,54 pb en entrenamiento, t 3,6; +0,08 en prueba, signo conservado) e INJECTION ≥ −0,5/−0,3 (Δ −0,49/−0,53, t −3,6/−4,5; −0,17/−0,07 en prueba). Lectura MMT: cuando el Eurosistema drena (QT + reembolsos), el €STR se despega del suelo (E5: menos exceso → menos compresión); es la dinámica que el config describe y aquí queda medida. Tesoro: ρ −0,08 / +0,08 (nada) — el bloque no puede drenar (arriba) y la regla del impulso tampoco separa (INYECCIÓN +0,06 · DRENAJE +0,16 pb a 4 s).

## Subastas Finanzagentur (1999–2026): anclas por era, efecto FX cambiante de signo

| instrumento | histórico p5 / p10 / mediana / p90 | era p5 / p10 / mediana / p90 | últimos 3 años p10 / mediana | retención p50 / p90 (era) | ancla propuesta |
|---|---|---|---|---|---|
| Bund / Bobl / Schatz / Green (n 1.201) | 1,1 / 1,2 / 1,7 / 2,7 | 1,2 / 1,3 / 2,0 / 3,2 (4 % bajo 1,2; 16 % bajo 1,5) | 1,4 / 2,1 | 19 % / 24 % | WATCH ≤ 1,3 · STRESS ≤ 1,2 (el < 1,2 / < 1,0 del config: 4 % / 0 %) · retención WATCH ≥ 25 % |
| Bubill (n 776) | 1,2 / 1,3 / 1,9 / 2,9 | 1,2 / 1,3 / 1,8 / 2,9 | 1,3 / 1,9 | 15 % / 39 % | WATCH ≤ 1,3 · STRESS ≤ 1,2 · retención WATCH ≥ 40 % |
| ILB — Bund€i (n 166, última 2023-10) | 1,2 / 1,3 / 1,7 / 2,4 | 1,26 / 1,3 / 1,5 | — | 21 % / 34 % | informativo (programa parado) |

La Finanzagentur no publica rendimiento marginal en el fichero: sin tail. Efecto FX: Bunds "débiles" dan +0,98 % (t 1,9) en 1999–2007, +1,38 (t 2,8) en 2008–14, +0,13 en 2015–22 y **−0,71 (t −2,1) en la era QT**; Bubills fuertes t +3,4 en la muestra completa con signo contrario a la hipótesis. Regularidades de época: la subasta describe la demanda del papel alemán, no el cruce. El bloque fiscal en vivo usa el b/c medio de las últimas 26 subastas y la última: con las anclas de arriba el flag WEAK_AUCTION saltaría en el 10 % de las subastas de la era en vez del 4 %.

## Propuesta para `config/eur.json` (a decidir)

`regime.dual.block_thresholds`: BC INJECTION ≥ +0,25 / DRAIN ≤ −0,6 (salida −0,08 / −0,43) — el −0,6 tiene validación de funding; Tesoro INJECTION ≥ +0,70 / ritmo débil ≤ −0,04, sin DRAIN posible hasta que el componente estructural sea nivel 0,25 (v0.3); régimen general por regla de acuerdo, conflicto (BC drena / Tesoro inyecta: 24 de 208 semanas, 10 de 65 en la sub-era) = NEUTRAL etiquetado; sin pesos duales. Anclas de subasta como en la tabla. Nota v0.3 común a las ocho: los componentes de nivel (fase QT, TOMO WATCH, déficit estructural) a 0,25 y los flujos (Δ exceso, −Δ depósitos del Gobierno, vencimientos APP/PEPP) dicen la inyección. Y una salvedad de datos: desde 2025-W45 el runner lee L050100 (Gobierno) y el replay leyó L050000 (Gobierno + otros); los percentiles del impulso en euros se recalibran cuando L050100 tenga 156 semanas.

## Corrección conjunta (v2, tras la triangulación)

FDR conjunto + block-bootstrap (`calibration/B_fdr.md`): el BC a 4 y 12 semanas es **la única validación de funding de las ocho divisas que sobrevive** (p bootstrap 0,0005, q FDR 0,000 / 0,008). Etiqueta del config: `funding_validado` para DRAIN ≤ −0,6; el INJECTION ≥ +0,25 queda como `frecuencia_de_era` (11 % de las semanas).
