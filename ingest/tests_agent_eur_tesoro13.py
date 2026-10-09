"""El enlace «Financiación neta del Estado» del Tesoro (13.xlsx) debe coincidir con el publicado en la página oficial.
Extracto real: fixtures/agent/eur/tesoro_estadisticas_mensuales_20261009.html. Con la URL vieja (/sites/default/files/estadisticas/13.xlsx,
404 desde ≤2026-10-07) este test falla."""
import os
import re
import sys

from . import ops_eur_lines as L

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "fixtures", "agent", "eur", "tesoro_estadisticas_mensuales_20261009.html")


def main() -> int:
    html = open(FX, encoding="utf-8").read()
    m = re.search(r"Financiación neta del Estado[^<]*<a[^>]*>PDF</a>\s*<a href=\"([^\"]+)\"[^>]*>XLSX</a>", html)
    fails = []
    if not m:
        fails.append("fixture: no XLSX link for 'Financiación neta del Estado'")
    elif L.TESORO_13_XLSX != "https://www.tesoro.es" + m.group(1):
        fails.append("TESORO_13_XLSX %s != published link %s" % (L.TESORO_13_XLSX, m.group(1)))
    for f in fails:
        print("FAIL", f)
    print("tests_agent_eur_tesoro13: %s" % ("OK" if not fails else "%d fallos" % len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
