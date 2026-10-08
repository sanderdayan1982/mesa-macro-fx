"""CAD banking · StatCan credit aggregates self-checks (run: python3 -m ingest.tests_cad_statcan). No pytest; exits 1 on failure.
Acta NETLIFY_CREDITS/CAD_STATCAN (2026-10-08): household (36-10-0639) and business (36-10-0640) credit wired from StatCan
WDS; display_only series no longer mark the banking block stale. Offline: fixtures only."""
from __future__ import annotations
import csv
import json
import os
import sys
from .providers import StatCanProvider
from . import blocks as B
from .run import series_ids

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "fixtures", "cad")
HH, BUS = "v1231415582", "v1304432223"


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def main() -> int:
    fails = []
    cfg = json.load(open(os.path.join(ROOT, "config", "cad.json"), encoding="utf-8"))
    ser = cfg["blocks"]["banking"]["series"]

    # S1 config: both credit series wired to StatCan, no longer pending
    check(ser["household_credit"].get("id") == HH and ser["business_loans"].get("id") == BUS, "S1 vector ids wired", fails)
    check(all(ser[k].get("source") == "statcan" and ser[k].get("status") != "pending" for k in ("household_credit", "business_loans")),
          "S1 source statcan, not pending", fails)

    # S2 Valet never receives StatCan ids (a mixed request would fail the whole Valet call)
    valet_ids = series_ids(cfg, "banking", "valet")
    check(HH not in valet_ids and BUS not in valet_ids and "V36717" in valet_ids, "S2 Valet ids exclude StatCan vectors", fails)
    check(series_ids(cfg, "banking", "statcan") == [BUS, HH], "S2 StatCan ids = business, household", fails)

    # S3 WDS parser: SUCCESS items only, refPer as date, values float
    sample = [{"status": "SUCCESS", "object": {"vectorId": 1231415582, "vectorDataPoint": [
                  {"refPer": "2026-06-01", "value": 3280452}, {"refPer": "2026-07-01", "value": 3290492}]}},
              {"status": "FAILED", "object": {"vectorId": 1304432223, "vectorDataPoint": [{"refPer": "2026-07-01", "value": 1}]}}]
    got = StatCanProvider.parse(sample, [HH, BUS])
    check(got[HH] == [("2026-06-01", 3280452.0), ("2026-07-01", 3290492.0)], "S3 parse household points", fails)
    check(got[BUS] == [], "S3 failed item ignored", fails)

    # S4 fixture mode reads the CSV layout date,<vector>
    fx = StatCanProvider(fixtures_dir=FIX).fetch([HH, BUS])
    rows = list(csv.DictReader(open(os.path.join(FIX, "statcan_credit_monthly.csv"), encoding="utf-8")))
    check(len(fx[HH]) == sum(1 for r in rows if r[HH]) and fx[HH][-1][0] == rows[-1]["date"], "S4 fixture household series", fails)

    # S5 block: credit series loaded; health counts scored series only, display_only listed
    from .providers import ValetProvider
    data = ValetProvider(fixtures_dir=FIX).fetch(valet_ids)
    data.update(fx)
    blk = B.build_banking(cfg, data, None, None)
    disp = [k for k, sc in ser.items() if sc.get("status") == "display_only"]
    h = blk["source_health"]
    check(blk["series"]["household_credit"]["value"] == fx[HH][-1][1], "S5 household credit value in block", fails)
    check(blk["series"]["business_loans"]["status"] != "unavailable", "S5 business credit available", fails)
    check(h["display_only"] == disp and h["series_expected"] == len(ser) - len(disp), "S5 health excludes display_only", fails)
    check(blk["series"]["bank_assets"]["status"] == "degraded", "S5 bank_assets keeps its own degraded badge", fails)

    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
