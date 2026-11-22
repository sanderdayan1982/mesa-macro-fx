"""t331u A3 follow-up: block.schema.json accepts status source_current.

New tests only. Does not edit older tests, thresholds, or formulas.
  python -m ingest.tests_cad_source_current_schema
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "block.schema.json"
FISCAL_PATH = ROOT / "data" / "cad" / "fiscal.json"
ALLOWED = ("fresh", "source_current", "stale", "proxy", "degraded", "unavailable")


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def test_schema_enum_includes_source_current(fails):
    schema = json.loads(SCHEMA_PATH.read_text())
    enum = schema["$defs"]["status"]["enum"]
    check(enum == list(ALLOWED),
          "status enum is fresh, source_current, stale, proxy, degraded, unavailable", fails)
    check(schema["$defs"]["series"]["properties"]["status"]["$ref"] == "#/$defs/status",
          "series.status $ref points at $defs.status", fails)


def test_source_current_series_validates(fails):
    try:
        import jsonschema
    except ImportError:
        print("skip jsonschema not installed; enum test already ran")
        return
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = json.loads(FISCAL_PATH.read_text())
    ser = doc["series"]["government_deposits_banks"]
    ser["status"] = "source_current"
    ser["next_publication"] = "2026-12-26"
    errs = list(jsonschema.Draft202012Validator(schema).iter_errors(doc))
    check(errs == [], "fiscal.json with government_deposits_banks status source_current validates", fails)
    ser["status"] = "invented"
    bad = list(jsonschema.Draft202012Validator(schema).iter_errors(doc))
    check(any("invented" in e.message or "not one of" in e.message for e in bad),
          "unknown status is still rejected", fails)


def main():
    fails = []
    test_schema_enum_includes_source_current(fails)
    test_source_current_series_validates(fails)
    print("fails=%d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
