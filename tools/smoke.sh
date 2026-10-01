#!/usr/bin/env bash
# smoke.sh — comprobaciones de mesa-macro-fx para la compuerta del agente de mantenimiento.
# Escribe una línea «CHECK <nombre> <rc>» por comprobación (no se detiene en el primer fallo): la compuerta compara
# la rama del agente con la base y bloquea si alguna comprobación que pasaba deja de pasar.
#   bash tools/smoke.sh > checks.txt
set -u
cd "$(dirname "$0")/.."
run() { local name=$1; shift; "$@" > /dev/null 2>&1; echo "CHECK $name $?"; }
run compile python -m compileall -q ingest tools
for c in usd eur jpy gbp cad aud nzd chf; do
  run "validate_$c" python -m ingest.validate --ccy "$c"
done
for t in ingest/tests_*.py; do
  m=$(basename "$t" .py)
  run "$m" python -m "ingest.$m"
done
run "config_json" python -c 'import glob, json; [json.load(open(f)) for f in glob.glob("config/*.json")]'
run "agent_gate_tests" python -m unittest -q tools.test_agent_gate
