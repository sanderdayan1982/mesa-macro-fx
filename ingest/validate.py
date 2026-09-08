"""Validate data/<ccy>/*.json block files against schema/block.schema.json (CI gate)."""
import json, os, sys, argparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--ccy", default="cad"); a = ap.parse_args(argv)
    schema = json.load(open(os.path.join(ROOT, "schema", "block.schema.json")))
    try:
        import jsonschema
    except ImportError:
        print("jsonschema not installed; skipping"); return 0
    bad = 0
    for b in ("central_bank", "fiscal", "banking", "rates"):
        p = os.path.join(ROOT, "data", a.ccy, "%s.json" % b)
        if not os.path.exists(p):
            print("MISSING", p); bad += 1; continue
        doc = json.load(open(p))
        errs = sorted(jsonschema.Draft202012Validator(schema).iter_errors(doc), key=lambda e: e.path)
        for e in errs[:10]:
            print("SCHEMA", b, "/".join(str(x) for x in e.path), "->", e.message[:120])
        bad += len(errs)
        # heartbeat: generated_at present and as_of not null
        if not doc.get("generated_at") or not doc.get("as_of"):
            print("HEARTBEAT", b, "missing generated_at/as_of"); bad += 1
        print("%-13s %s as_of=%s health=%s signal=%s" % (b, "OK" if not errs else "ERR", doc.get("as_of"), doc["source_health"]["status"], doc["signals"]["label"]))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
