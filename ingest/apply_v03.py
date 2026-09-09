"""Write the engine v0.3 calibration into config/<ccy>.json (regime.dual) from calibration/<ccy>_v03/calibration.json.

    python -m ingest.apply_v03 --ccy eur            # one currency
    python -m ingest.apply_v03 --all                # the eight
    python -m ingest.apply_v03 --all --revert       # back to the v0.2 dual block kept in regime.dual_v02

Keeps the previous block under regime.dual_v02 (first run only), keeps the per-currency weights note, and writes the evidence
labels stamped by `calibrate --fdr-v03`. Never invents a number: every cut comes from the replay file."""
from __future__ import annotations
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CCYS = ["cad", "gbp", "aud", "jpy", "chf", "nzd", "usd", "eur"]


def apply(ccy: str, revert: bool = False) -> str:
    cp = os.path.join(ROOT, "config", "%s.json" % ccy)
    raw = open(cp, encoding="utf-8").read()
    ind = 2 if raw.startswith('{\n  "') else 1
    cfg = json.loads(raw)
    rc = cfg["regime"]
    if revert:
        if "dual_v02" in rc:
            rc["dual"] = rc.pop("dual_v02")
            json.dump(cfg, open(cp, "w", encoding="utf-8"), indent=ind, ensure_ascii=False)
            return "%s: reverted to v0.2" % ccy
        return "%s: nothing to revert" % ccy
    cal = json.load(open(os.path.join(ROOT, "calibration", "%s_v03" % ccy, "calibration.json")))
    patch = (cal.get("v03") or {}).get("config_patch")
    if not patch or not patch.get("block_thresholds"):
        return "%s: no v0.3 patch in the calibration file" % ccy
    old = rc.get("dual") or {}
    if "dual_v02" not in rc and not str(old.get("version", "")).startswith("0.3"):
        rc["dual_v02"] = old
    new = dict(patch)
    # per-currency dual weights stay as the desk set them (context only under the agreement rule)
    if old.get("weights"):
        new["weights"] = old["weights"]
    if old.get("note"):
        new["note"] = old["note"]
    new["rule"] = ("three regimes per currency (engine v0.3): central_bank and fiscal from their block score with era-calibrated entry/exit cuts on the "
                   "%d-day mean score; general = agreement only (both inject → LIQUIDITY_INJECTION, both drain → LIQUIDITY_DRAIN, partial or conflict → NEUTRAL labelled); "
                   "percentile windows anchored to era_start; price gates (LIQUIDITY_SCARCITY, FLOOR_FRICTION) override the general regime" % new.get("persistence", {}).get("entry_days", 7))
    rc["dual"] = new
    json.dump(cfg, open(cp, "w", encoding="utf-8"), indent=ind, ensure_ascii=False)
    bt = new["block_thresholds"]
    return "%s: v0.3 applied — level_weight %s · CB %s / %s · fiscal %s / %s · evidence %s" % (
        ccy, new.get("level_weight"), bt.get("central_bank", {}).get("injection_enter"), bt.get("central_bank", {}).get("drain_enter"),
        bt.get("fiscal", {}).get("injection_enter"), bt.get("fiscal", {}).get("drain_enter"), {k: v.get("evidence") for k, v in bt.items()})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccy")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args(argv)
    for c in (CCYS if a.all else [a.ccy.lower()]):
        print(apply(c, a.revert))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
