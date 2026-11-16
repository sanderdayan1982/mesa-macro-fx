# ACTA — FAMILIAS-01 Fase 2, módulo M2 (D3 FLOWS semanal), 16-nov-2026

Diseño firmado. Sombra: `vote = 0`, `blocked_entry = false`. No entra en el jefe ni en el bloque fiscal. `data/jpy/fiscal.json` no se reescribe.

## Diagnóstico

`logs/jpy/raw/its_week.csv` (descarga ya hecha por `refresh-jpy`, Shift-JIS, unidad 100 millones de yenes). Comprobado el 16-nov-2026 sobre el fichero del repo:

- 1.140 semanas, todas terminan en sábado, sin huecos de 14 días. Primera `2005-01-08`, última `2026-11-07` (`2026．11．1～11．7`).
- Cabecera inglesa: `Net` en las columnas 3, 6, 14 y 17. La 17 es la que ya publica `foreign_jgb_flow_weekly` (13.711 en la semana del 7-nov, el mismo número que `data/jpy/fiscal.json` → `series.foreign_jgb_flow_weekly.value`, fecha `2026-11-07`).
- El fichero declara `Final Update November 12, 2026`. El jueves 12-nov-2026 es `week_end + 5` de esa semana.
- `MofItsProvider.parse` sigue leyendo las columnas 6, 17 y 21 en crudo. Solo la 17 entra en el bloque fiscal (`display_only`). No se ha tocado.

Fuentes primarias de calendario, leídas el 16-nov-2026:

- FAQ MoF, pregunta 3: el semanal se publica «on the fourth day of the following week». <https://www.mof.go.jp/english/policy/international_policy/reference/itn_transactions_in_securities/faq_its_english.html>
- Calendario publicado MoF (nota: sujeto a cambio, 8:50 JST). <https://www.mof.go.jp/english/policy/international_policy/reference/itn_transactions_in_securities/schedule.htm>
- Festivos nacionales (内閣府 `syukujitsu.csv`), años 2025, 2026 y 2027. <https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv>

CHF: `history/chf/snbgwdchfsgw:TG.csv`, `:GI.csv` y `:UEB.csv` ya están en el repo (depósitos a la vista semanales del SNB). El total del 6-nov-2026 es 452.892, el mismo valor que `data/chf/central_bank.json` → `sight_deposits_total_weekly`. USD: la lista H.4.1 que ya captura el repo es WALCL, TREAST, WSHOMCB, WLCFLPCL, WTREGEN, WRESBAL (`ingest/run.py`). No hay custodia de la Fed (`WSHOICL`, `WSEFINTL`, `WSEFDIN`). No se añade fuente.

## Qué se publica

`data/mesa/FLOWS_weekly.json` y `history/mesa/its_vintage.csv`. Los escribe `ingest/flows_jpy.py` al final de `fetch_jpy` (cualquier carril, sin fixtures) y el carril semanal del jueves 04:00 UTC añadido en `refresh-jpy.yml`. El carril del viernes se queda.

`flow_jpy = col14 + col17 − col3 − col6`. El signo R11 (−1 en col 3 y col 6, +1 en col 14 y col 17) se aplica una vez. Celda vacía o `-` → null; no hay `or 0`. `sum4` exige cuatro semanas presentes y separadas 7 días; un hueco anula el `sum4` y no se rellena. Percentil y z usan la ventana de 52 publicaciones, sin rellenar huecos y sin lookahead en el z.

Estados solo en `flow_jpy`, sobre `pct52` de `sum4`: ENTRADA entra a ≥ 80 y sale a < 70; SALIDA entra a ≤ 20 y sale a > 30; si no, NEUTRO. Histéresis de 2 publicaciones semanales para entrar y para salir. `n` = publicaciones válidas en la ventana de 52. `n < 26` → UNAVAILABLE y la histéresis se pone a cero. `26 ≤ n < 52` → `flows_prov` y la etiqueta `[PROV]` de Fable (R12, sin calibrar) queda en `method.flows` hasta el acto de GATE. `n ≥ 52` → sin `[PROV]`. Las cuatro series sueltas no tienen estado.

STALE: jueves posterior al sábado, o viernes si ese jueves es festivo nacional japonés (sustituto y `国民の休日` incluidos). Si hoy es esa fecha del calendario + 1 día y no hay fila nueva, el estado no se clasifica (`STALE`). Entre medias no se interpola: el estado vigente es el de la última publicación, con su `week_end`.

Revisiones: `its_vintage.csv` es append-only (`week, series, value, first_seen, rev`). `_merge_hist` no se toca (sigue last-wins para lo ya publicado). Si el MoF cambia una semana pasada se añade una fila `rev=1`. El estado y el valor que lo alimenta usan la primera fila. Una segunda pasada con el mismo CSV no añade filas (5.700 datos = 1.140 × 5 series, más la cabecera).

Primera foto, `as_of` 2026-11-16, semana que termina el 2026-11-07, publicada el 2026-11-12: `flow_jpy` = 24.474, `sum4` = 51.023, `pct52_sum4` = 76,92, `n` = 52, estado ENTRADA sin `[PROV]`. El 76,92 no es una entrada nueva: la entrada pide ≥ 80 durante dos publicaciones y la salida pide < 70 durante dos. EUR, GBP, AUD, NZD, CAD y USD = null. CHF solo `value`, `sum4`, `z52`.

La serie firmada `its_resident_foreign_bonds_weekly` con signo −1 vive en este JSON y en el vintage. El CSV `history/jpy/its_resident_foreign_bonds_weekly.csv` sigue siendo la columna 6 en crudo. No se reescribe.

## Comprobación

`python3 -m ingest.tests_flows_jpy`: T-F1…T-F12, 0 fallos. Fixtures sintéticos. `tools/smoke.sh` ya lanza `ingest/tests_*.py`; no hizo falta editarlo.

`bash tools/smoke.sh` el 16-nov-2026, con `xlrd` y `pdfplumber` instalados (están en `requirements.txt`): 20/20 `CHECK` con rc 0, incluido `tests_flows_jpy`. Sin esos dos paquetes, `tests_eu_esm` y `tests_jpy_ops` salen por `ModuleNotFoundError` antes de ejecutar un assert; con los paquetes pasan. No importan el módulo nuevo. Los tests viejos no se han modificado.

SHA-256 de `data/jpy/fiscal.json` antes y después de generar la foto: `c859ff2020c7cd11aca56136ff75c65d428ef4eaf35a670bdb637db303fb049e`. Igual. `series.foreign_jgb_flow_weekly` igual.

## Lo que el diseño firmado no cubre y no se ha improvisado

El calendario publicado del MoF no es solo «jueves, o viernes si ese jueves es festivo». Comprobado el 16-nov-2026 en la página de schedule:

- 16-oct-2026 (viernes) para la semana del 4–10 oct: el lunes 12 es el día del deporte; el jueves 15 no es festivo.
- 6-nov-2026 (viernes) para la semana del 25–31 oct: el martes 3 es el día de la cultura; el jueves 5 no es festivo.
- 27-nov-2026 (viernes) para la semana del 15–21 nov: el lunes 23 es el día de acción de gracias del trabajo; el jueves 26 no es festivo.
- 1-oct-2026 junta las semanas del 13–19 y del 20–26 de septiembre.
- 7-ene-2027 junta las semanas del 20–26 dic y del 27 dic–2 ene.

La regla firmada solo admite jueves, o viernes cuando el jueves es festivo. Un «cuarto día hábil» sin tope también cae en otros días (la semana que termina el 19-sep-2026, con el 21, el 22 y el 23 festivos, daría el 29-sep). Eso no se ha codificado. STALE usa la regla firmada. Esas cinco fechas del schedule pueden marcar STALE un día antes de lo que el MoF publica, o no ver la semana combinada. Queda dicho en `method.release`.

USD queda NA. No hay custodia de la Fed ya capturada. No se añade fuente.
