# daily_log 1.0 — las siete frases en el motor · 2026-09-09

Plantilla adjudicada en la ronda 3 (Kimi > CodeWord > Qwen > DeepSeek > Perplexity > Gemini). Tres módulos nuevos en `ingest/`, sin HTTP, deterministas: el mismo JSON produce el mismo texto (hash).

| módulo | qué hace | salida |
|---|---|---|
| `ingest/narrative.py` | construye cabecera + F1–F7 desde los cuatro JSON de bloque + `regime.json`, con el vocabulario de cada divisa (`SPEC`), el mapa de frecuencia, las variantes degradadas, el glosario y el ledger de rachas | `data/<ccy>/agent.json` |
| `ingest/jefe.py` | ranking transversal de las ocho por Δ13 semanas de reservas del BC en % del stock (Z con σ agrupada de era, as-of), sobre el panel congelado de los replays (`calibration/conviction/reserves_panel.json`) extendido con `history/<ccy>/<csv>` | `data/mesa/jefe.json` y F7 |
| `ingest/gate.py` | puerta anti-invención (cinco aserciones + lista negra del cierre + fuzzing) | `agent.json.gate`; si falla, `published: false` y el texto queda retenido con los fallos visibles |

`ingest/run.py` llama a `narrative.run(ccy)` al final de cada refresco (nunca bloquea la ingesta; queda en `oplog` como `AGENT_DAILY_LOG`). Los ocho workflows corren `python -m ingest.gate --ccy X` después de validar y añaden `data/mesa` al commit. La pestaña AGENT de los ocho dashboards muestra las siete frases, el ranking, la puerta y el hueco del cierre del modelo.

## Las siete frases (qué lee cada hueco)

Cabecera: «Datos hasta <última fecha> (BC: as-of, fresco/stale/proxy; Tesoro: …; tipos: …; banca: …)».

| # | frase | origen | variante degradada |
|---|---|---|---|
| F1 | reservas: Δ en la ventana corta y larga del mapa de frecuencia (diario → 5/20 sesiones; semanal → 1/4 semanas; decena → 1/3 decenas), nivel, fecha, régimen del BC y racha | serie de reservas de la divisa (WRESBAL, exceso de liquidez, reservas BoE, CAB, depósitos a la vista SNB, saldos de liquidación BoC, ES, settlement cash); `regime.json` | «variación no calculable con la historia publicada» |
| F2 | cartera y operaciones: Δ de la cartera en su ventana, stocks mensuales con «atribución semanal no publicada», operaciones vivas o flujos del día | series de cartera/operaciones por divisa | stock mensual, nunca interpolación |
| F3 | Tesoro: Δ de la cuenta del gobierno en el BC + «este flujo alimenta/drena las reservas»; flujo fiscal semana / mes / trimestre móvil; régimen del Tesoro y racha | cuenta del gobierno + flujos fiscales del bloque | «no publicado por la fuente» por ventana; GBP/CHF sólo mensual |
| F4 | emisión y subastas: bruta, vencimientos, neta (o «neta no calculable»); cobertura, rendimiento, tail, retención con «sin señal/WATCH/STRESS» por anclas de era | series de emisión y subastas | «vencimientos no publicados por la fuente; emisión neta no calculable» |
| F5 | régimen general del motor (enum), racha, mecanismo con precedencia causal (9 combinaciones BC × Tesoro), puerta de precio, semanas de era | `regime.json` | «sin lectura de mecanismo» si falta un bloque |
| F6 | precio del dinero: spread overnight − tipo del BC, nivel, por encima/por debajo/al nivel, fricción confirmada o no; «confirma, no determina» | spread del bloque de tipos + `friction_confirmed` | «fricción: sin cálculo publicado» (CAD hoy) |
| F7 | jefe de mesa: ranking completo de ocho (Δ13 s %, Z), posición propia y semana anterior, par con más convicción relativa por la pata BC, etiqueta «sólo BC; Tesoro pendiente de prerregistro», dispersión baja cuando σ semanal < p20 de era, «sin par neto hasta T1–T3» | `jefe.json` | «ranking no calculable» si hay < 5 divisas |

Unidades de pantalla: mm (miles de millones) para USD, EUR, GBP, CHF, CAD, AUD, NZD; tn (10¹²) para JPY; importes por debajo de 0,05 mm se imprimen en la unidad de la fuente (mn) en lugar de añadir decimales. Formato español (coma decimal). El redondeo nunca cruza cero: si un valor no nulo redondearía a 0, se añaden decimales.

Rachas: `agent.json.ledger` guarda (as_of, régimen) por bloque y por régimen general; la racha es el número de lecturas consecutivas con el mismo régimen (unidad: «lecturas», no semanas — Kimi). Primera publicación = 1.ª.

## Puerta anti-invención (`python -m ingest.gate --ccy usd [--fuzz]`)

1. **A1 números**: cada token numérico del texto existe en `numbers` (token, campo, valor, precisión), o es una fecha presente en el JSON del día, o una etiqueta estructural declarada (`structural`: las ventanas del vocabulario, F1–F7, T1–T3, Δ13, p20).
2. **A2 verbos**: cada verbo direccional (subieron/cayeron, subió/bajó, creció/cayó, alimenta/drena, por encima/por debajo/al nivel) casa con el signo del campo, y se recomputa desde los sparklines del bloque.
3. **A3 enum y rachas**: la etiqueta de F5 pertenece al enum del motor y coincide con `regime.json`; los regímenes de bloque pertenecen a su enum; la racha coincide con el ledger y aparece en el texto.
4. **A4 glosario**: cada sigla del glosario de la divisa se expande en su primera aparición.
5. **A5 determinismo y degradación**: el hash coincide con el texto; un bloque stale/proxy/no disponible aparece en la cabecera.
6. **Cierre**: lista negra (busca, pretende, inflación, empleo, PIB, señal, recomendación, comprar, vender, objetivo, probabilidad, seguirá, masivo, fuerte…) y sin dígitos salvo fechas.
7. **Fuzzing** (`--fuzz`): mismo JSON → mismo hash; sparklines con signo invertido → todos los verbos de Δ cambian; bloque stale → aviso en cabecera.

Resultado hoy: las ocho divisas PASAN la puerta y el fuzzing.

## Lectura de hoy (2026-09-09; jefe de mesa al viernes 2026-09-04)

1 AUD +6,0 % (Z +1,35) · 2 GBP +0,6 (+0,56) · 3 CAD +0,1 (+0,49) · 4 CHF −1,9 (+0,20) · 5 EUR −2,6 (+0,10) · 6 USD −4,0 (−0,10) · 7 JPY −4,2 (−0,14) · 8 NZD −20,1 % (Z −2,45). Par con más convicción relativa por la pata BC: AUD frente a NZD (brecha Z 3,80). Dispersión normal (σ semanal 7,56 frente a p20 de era 4,44). El motor reproduce exactamente la lectura del ICL 1.0.

## Cómo lo usan las AI

Reciben `agent.json` (o las siete frases) y escriben sólo el cierre de 2–3 líneas: qué cambió respecto a ayer (ledger/rachas), qué vigilar mañana (`calendar_next`), aviso stale/proxy/degradado (`blocks_meta`, `degraded`). Sin cifras salvo fechas del calendario; el cierre pasa por la misma puerta antes de publicarse. Las siete frases no se reescriben.

## Pendiente

Intervalo bootstrap por posición del ranking (Kimi) — no calculable con una sola sección transversal; T1–T3 (una sola mirada); hipótesis del régimen a 4 semanas de Kimi para el replay del motor.
