"""Tests de la compuerta del agente de mantenimiento (python -m unittest tools.test_agent_gate)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_gate as G  # noqa: E402

try:
    import yaml
except ImportError:                                                     # pragma: no cover
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = {"currency": "CAD", "sources": {"valet": {"base_url": "https://www.bankofcanada.ca/valet"}},
        "status_rules": {"x": 1}, "blocks": {"rates": {"series": ["V39079"]}}}


def show_with(old, new):
    return lambda ref, path: json.dumps(old if ref == "B" else new)


class Gate(unittest.TestCase):
    def test_auto_adapters_actas_tests(self):
        r = G.classify(["ingest/providers_eur.py", "ingest/ops_cad.py", "actas/ACTA_AGENTE_20261005.md",
                        "ingest/tests_agent_rba.py", "fixtures/agent/boc/x.json"], "B")
        self.assertEqual((r["decision"], r["outside"]), ("AUTO", []))

    def test_owner_methodology_files(self):
        for p in ("ingest/engine.py", "ingest/blocks_cad_v04.py", "ingest/calibrate.py", "ingest/gate.py", "ingest/jefe.py",
                  "ingest/quality.py", "schema/block.schema.json", "calibration/x.json", ".github/workflows/refresh.yml",
                  "data/cad/rates.json", "config/notify.json", "tools/agent_gate.py"):
            self.assertEqual(G.classify([p], "B")["decision"], "OWNER", p)

    def test_config_sources_only_is_auto(self):
        new = json.loads(json.dumps(BASE))
        new["sources"]["valet"]["base_url"] = "https://www.bankofcanada.ca/valet/v2"
        r = G.classify(["config/cad.json"], "B", show=show_with(BASE, new))
        self.assertEqual(r["decision"], "AUTO")

    def test_config_outside_sources_is_owner(self):
        for key, val in (("status_rules", {"x": 2}), ("blocks", {"rates": {"series": ["V39080"]}})):
            new = json.loads(json.dumps(BASE))
            new[key] = val
            self.assertEqual(G.classify(["config/cad.json"], "B", show=show_with(BASE, new))["decision"], "OWNER", key)

    def test_config_new_or_invalid_is_owner(self):
        self.assertEqual(G.classify(["config/xxx.json"], "B", show=lambda ref, p: None if ref == "B" else "{}")["decision"], "OWNER")
        self.assertEqual(G.classify(["config/cad.json"], "B", show=lambda ref, p: "{" if ref == "B" else "{}")["decision"], "OWNER")

    def test_nothing(self):
        self.assertEqual(G.classify([""], "B")["decision"], "NADA")

    def test_worse(self):
        base = {"compile": 0, "tests_v04": 1, "validate_cad": 0}
        self.assertEqual(G.worse(base, {"compile": 0, "tests_v04": 1, "validate_cad": 0}), [])   # fallo previo: no cuenta
        self.assertEqual(G.worse(base, {"compile": 0, "tests_v04": 0, "validate_cad": 1}), ["validate_cad"])
        self.assertEqual(G.worse(base, {"tests_v04": 1}), ["compile", "validate_cad"])           # comprobación ausente

    @unittest.skipUnless(yaml, "sin pyyaml")
    def test_workflow_agent_job_read_only(self):
        with open(os.path.join(ROOT, ".github", "workflows", "maintenance-agent.yml"), encoding="utf-8") as fh:
            wf = yaml.safe_load(fh)
        on = wf.get("on", wf.get(True))
        self.assertEqual(on["schedule"], [{"cron": "0 19 * * 1,3,5"}])
        agent = wf["jobs"]["agent"]
        self.assertEqual(agent["permissions"], {"contents": "read", "actions": "read"})
        co = [s for s in agent["steps"] if str(s.get("uses", "")).startswith("actions/checkout")][0]
        self.assertIs(co["with"]["persist-credentials"], False)
        cl = [s for s in agent["steps"] if "claude-code-action" in str(s.get("uses", ""))][0]
        self.assertEqual(cl["with"]["claude_code_oauth_token"], "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}")
        self.assertIn("Bash(git push:*)", cl["with"]["claude_args"].split("--disallowedTools")[1])
        gate = wf["jobs"]["gate"]
        self.assertFalse([s for s in gate["steps"] if "claude-code-action" in str(s.get("uses", ""))])


if __name__ == "__main__":
    unittest.main()
