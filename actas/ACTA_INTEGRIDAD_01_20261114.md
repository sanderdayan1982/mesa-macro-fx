# ACTA — ORDEN INTEGRIDAD-01 (bloque A), 14-nov-2026

Orden firmada por Sander el 14-nov-2026 19:38 WAT. Un dato ausente, viejo o de otra fecha no se rellena (0, último valor, `or 0`, ffill): se publica ausente o STALE y no entra en el derivado ni en el voto de ese dato.

No hay hash de fichero congelado en `tests/`. Nada que actualizar por SALUD-1.

## A2 — `fresh` encima de un dato viejo

`entry()` hacía `st = status or q["freshness"]`. Cualquier `status="fresh" if ser` (y las asignaciones posteriores del mismo tipo en `blocks_*`) pintaba de fresco una serie cuya frescura calculada era `stale`.

Cambio: `clamp_status`. Un estado explícito puede repetir o empeorar la frescura; no puede mejorarla si lo calculado es `stale` o peor. Cubre `blocks.py` y el mismo patrón en todos los `blocks_*`, incluido `blocks_gbp_v04.py` (líneas de `apf_sales_daily`, `apf_sales_5d`, `ctrf_net_daily` y el cubo APF). El componente sombra `apf_sales_5d_pct` no entra si la serie no está `fresh` o `proxy`.

No se toca el convenio «celda vacía = 0 de no uso» (AUD/JPY `zero_if_empty`): no es el patrón de esta orden y reescribe fecha y valor, no solo el estado.

## A3 — liquidez neta con fechas mezcladas

`net_liquidity` de USD restaba el ON RRP más reciente ≤ la fecha H.4.1. El 11-nov-2026 (WALCL y TGA) no tiene ON RRP; el código usaba el del 10-nov (152).

Cambio: solo fechas presentes en las tres patas. Si falta una pata, ese día no existe. `component_dates` publica la fecha de cada pata que entró en el punto impreso. La fórmula de `config/usd.json` deja de decir «RRP = último diario ≤ H.4.1».

## A6 — boletín que fabrica «0,0» y «NEUTRAL»

`_es_num(x or 0.0)` y la dirección `(x or 0)` convertían ausencia en cero. `_dt` heredaba el `as_of` del bloque. `notify.py` comparaba dirección o fecha con `None` y podía avisar de un giro.

Cambio: sin `or 0`; `_es_num(None)` sigue siendo «—»; dirección `None` si falta el insumo; un cero real sigue siendo NEUTRAL; no hay alerta si un lado es `None`; `_dt` solo usa la fecha de la serie.

## Comprobación

`bash tools/smoke.sh` el 14-nov-2026: 18/18 `CHECK` con rc 0 (compilación, `validate` de las 8 divisas, los ocho `ingest/tests_*.py` incluida `tests_integridad_01`, JSON de config, `tools.test_agent_gate`). Los tests viejos no se han modificado. Ninguno fijaba el relleno; no hubo caso que parar.

Los JSON de `data/` no se regeneran en este PR.
