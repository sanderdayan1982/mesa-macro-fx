# CLAUDE.md — mesa-macro-fx

Mismas reglas de trabajo que g8-macro-pipeline (CLAUDE_G8). Se aplican a cualquier sesión de Claude Code en este repo,
incluido el agente de mantenimiento.

## Método
1. **Diagnóstico → propuesta → implementación.** Primero el problema con evidencia (fichero, fecha, valor), luego la
   propuesta, y solo después el cambio.
2. **Nada sin verificar en la fuente primaria** (banco central, tesoro, oficina estadística, bolsa). URL y fecha de la
   comprobación en el acta.
3. **Metodología intocable sin OK explícito del propietario**: umbrales, cortes, pesos, calibraciones, reglas de
   estado y de régimen, bloques, puntuaciones, «jefe», convicción, compuerta anti-invención. En `config/<ccy>.json`
   solo el bloque `sources` es mantenimiento; todo lo demás es metodología.
4. **Fuente más fresca disponible**, con la fecha real del dato siempre visible.
5. **Fallos ruidosos.** Nunca rellenar en silencio ni presentar como actual un dato viejo.

## Cada cambio
- Comprobaciones: `bash tools/smoke.sh` (compilación, `ingest.validate` de las 8 divisas, `ingest/tests_*.py`,
  JSON de config, tests de la compuerta). Ninguna puede empeorar respecto a `main`.
  Nota 1-oct-2026: `tests_v04` («no future-dated term repo flows») fallaba porque comparaba con una fecha fija;
  corregido con OK del propietario (ahora usa el mismo «hoy» que `ops_cad.op_flows`). Las 16 comprobaciones en verde.
- Acta en `actas/ACTA_<lote>.md` (el agente: `actas/ACTA_AGENTE_<AAAAMMDD>.md`).
- Python 3.11 con `requirements.txt` + `pyyaml`.

## Mapa rápido
- `config/<ccy>.json` — fuentes (`sources`) + metodología del resto de claves.
- `ingest/providers*.py`, `ingest/ops_*.py` — adaptadores de fuente; `ingest/run.py` — único sitio que descarga.
- `data/<ccy>/*.json`, `history/`, `logs/` — salidas que commitean los workflows `refresh-*` (no editar a mano).
- `.github/agent/mantenimiento.md` — agente de mantenimiento; `tools/agent_gate.py` — lo que puede integrar sin OK.
