#!/usr/bin/env python3
"""agent_gate.py — compuerta del agente de mantenimiento de mesa-macro-fx (la decide el workflow, no el agente).

    python tools/agent_gate.py --base <sha>                    → JSON; rc 0 = AUTO, 3 = OWNER, 4 = NADA
    python tools/agent_gate.py --compare base.txt head.txt     → rc 0 si ninguna comprobación empeora, 1 si alguna

AUTO  : solo adaptadores de fuente (ingest/providers*.py, ingest/ops_*.py), el bloque "sources" de config/<ccy>.json,
        actas y tests del agente. Se integra en main si además ninguna comprobación empeora respecto a la base.
OWNER : cualquier otro fichero, o un config/<ccy>.json con cambios FUERA de "sources" (bloques, régimen, reglas de
        estado, alertas, umbrales, calibración) → PR para el propietario.
NADA  : sin commits.
"""
import argparse
import fnmatch
import json
import subprocess
import sys

ALLOW = [
    "ingest/providers*.py",
    "ingest/ops_*.py",
    "actas/ACTA_AGENTE_*.md",
    "ingest/tests_agent_*.py",
    "fixtures/agent/*",
]
CONFIG = "config/*.json"
CONFIG_FREE_KEYS = ("sources",)          # lo único que el agente puede cambiar dentro de un config


def _git_show(ref, path):
    r = subprocess.run(["git", "show", "%s:%s" % (ref, path)], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def config_only_sources(old_text, new_text):
    """True si old y new solo difieren dentro de las claves permitidas (y ambos son JSON válidos)."""
    if old_text is None or new_text is None:
        return False
    try:
        old, new = json.loads(old_text), json.loads(new_text)
    except ValueError:
        return False
    if not isinstance(old, dict) or not isinstance(new, dict):
        return False
    strip = lambda d: {k: v for k, v in d.items() if k not in CONFIG_FREE_KEYS}
    return strip(old) == strip(new)


def allowed(path, base=None, head="HEAD", show=_git_show):
    if fnmatch.fnmatch(path, CONFIG) and path != "config/notify.json":
        return config_only_sources(show(base, path), show(head, path)) if base else False
    return any(fnmatch.fnmatch(path, p) for p in ALLOW)


def classify(paths, base=None, show=_git_show):
    paths = sorted(set(p for p in paths if p))
    if not paths:
        return {"decision": "NADA", "changed": [], "outside": []}
    outside = [p for p in paths if not allowed(p, base, show=show)]
    return {"decision": "OWNER" if outside else "AUTO", "changed": paths, "outside": outside}


def read_checks(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) == 3 and parts[0] == "CHECK":
                out[parts[1]] = int(parts[2])
    return out


def worse(base, head):
    """Comprobaciones que pasaban en la base y no pasan (o faltan) en la rama del agente."""
    return sorted(k for k, rc in base.items() if rc == 0 and head.get(k, 1) != 0)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--compare", nargs=2)
    a = ap.parse_args(argv)
    if a.compare:
        w = worse(read_checks(a.compare[0]), read_checks(a.compare[1]))
        print(json.dumps({"worse": w}))
        return 1 if w else 0
    out = subprocess.run(["git", "diff", "--name-only", a.base, "HEAD"], capture_output=True, text=True, check=True)
    res = classify(out.stdout.split("\n"), a.base)
    print(json.dumps(res, ensure_ascii=False))
    return {"AUTO": 0, "OWNER": 3, "NADA": 4}[res["decision"]]


if __name__ == "__main__":
    sys.exit(main())
