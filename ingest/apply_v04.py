"""Activate engine v0.4 on the APPROVED blocks (calibration/REPLAY_V04.md, runner, 8-year archives, 2026-09-11) in config/<ccy>.json.

    python -m ingest.apply_v04 --ccy cad            # one currency
    python -m ingest.apply_v04 --all                # cad chf aud jpy
    python -m ingest.apply_v04 --all --revert       # back to the v0.3 dual block kept in regime.dual_v03

Writes regime.dual.v04 = {<block>: {active, component, cuts, evidence, selected}} for the approved blocks only, keeps the untouched
v0.3 block under regime.dual_v03 (first run only), sets dual.version "0.4" and bumps the config_version patch. Every cut is read
from calibration/<ccy>_v04/replay_v04.json (variant B of the approved block) and cross-checked against the approved table below;
a mismatch aborts — nothing is typed by hand into the config."""
from __future__ import annotations
import argparse
import json
import os

from .replay_v04 import SPEC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELECTED = "replay-v04 2026-09-11 (runner, 8-year archives)"
# approved (currency, block) → cuts as adjudicated (enter/exit, % of the reserves stock over 5 sessions); the replay file must agree
APPROVED = {
    "cad": {"fiscal": {"injection_enter": 2.2412, "injection_exit": 0.9705, "drain_enter": -3.0433, "drain_exit": -1.5172}},
    # chf central_bank (fx_proxy_w) NOT activated (desk decision 2026-09-11): the proxy is complete only when the monthly gmges amounts
    # arrive (~35 d after month-end), so it is never known as of today under the replay's 7-day lag and would blind the block
    "chf": {"fiscal": {"injection_enter": 0.034, "injection_exit": 0.0092, "drain_enter": -0.0701, "drain_exit": -0.0392}},
    "aud": {"central_bank": {"injection_enter": 0.466, "injection_exit": 0.2928, "drain_enter": -0.4831, "drain_exit": -0.2075},
            "fiscal": {"injection_enter": 2.7248, "injection_exit": 1.6897, "drain_enter": -2.8347, "drain_exit": -1.8796}},
    "jpy": {"fiscal": {"injection_enter": 0.6459, "injection_exit": 0.1934, "drain_enter": -1.0505, "drain_exit": -0.7651}},
    # eur fiscal approved 2026-09-11 (second batch): two-signed since the FR/IT/ES redemptions+coupons lot — replay-v04 on the runner
    # 14:18Z: B, stable, coverage 1.00, no ONE_SIDED, injection cut above zero (0.1427). NZD fiscal stays v0.3: still ONE_SIDED on the
    # runner (injection cut −0.0439) after the LSAP/repurchase netting — net issuance without the spending leg is one-sided by economics
    "eur": {"fiscal": {"injection_enter": 0.1427, "injection_exit": -0.0359, "drain_enter": -0.5159, "drain_exit": -0.3496}},
}
# denominator = the 'reserves' column calibrate.py writes to scores.csv (the replay divides by it)
DENOMINATOR = {"cad": "central_bank.reserves", "aud": "central_bank.reserves", "jpy": "central_bank.cab_daily", "chf": "central_bank.sight_deposits_domestic_weekly", "eur": "central_bank.excess_liquidity"}
CCYS = list(APPROVED)


def _bump_patch(v: str) -> str:
    p = str(v).split(".")
    while len(p) < 3:
        p.append("0")
    p[2] = str(int(p[2]) + 1)
    return ".".join(p[:3])


def _component(ccy: str, block: str) -> dict:
    """the single component of variant B for the block, from replay_v04.SPEC: {name, source, kind, lag, sign, denominator}"""
    b = SPEC[ccy][block]["B"]
    if len(b) != 1:
        raise SystemExit("%s %s: variant B must carry exactly one component (found %s)" % (ccy, block, list(b)))
    name, (src, key, kind, lag, sign, recon) = next(iter(b.items()))
    source = "central_bank.government_account" if src == "scores" else key
    return {"name": name, "source": source, "kind": kind, "lag": lag, "sign": sign, "denominator": DENOMINATOR[ccy], "reconciliation": recon}


def apply(ccy: str, revert: bool = False) -> str:
    cp = os.path.join(ROOT, "config", "%s.json" % ccy)
    raw = open(cp, encoding="utf-8").read()
    ind = 2 if raw.startswith('{\n  "') else 1
    cfg = json.loads(raw)
    rc = cfg["regime"]
    if revert:
        if "dual_v03" in rc:
            rc["dual"] = rc.pop("dual_v03")
            cfg["config_version"] = _bump_patch(cfg["config_version"])
            cfg["note"] = "v0.4 activation reverted to v0.3 (regime.dual restored from dual_v03)"
            json.dump(cfg, open(cp, "w", encoding="utf-8"), indent=ind, ensure_ascii=False)
            return "%s: reverted to v0.3" % ccy
        return "%s: nothing to revert" % ccy
    if ccy not in APPROVED:
        return "%s: no approved v0.4 block" % ccy
    rep = json.load(open(os.path.join(ROOT, "calibration", "%s_v04" % ccy, "replay_v04.json"), encoding="utf-8"))
    old = rc.get("dual") or {}
    if "dual_v03" not in rc and not str(old.get("version", "")).startswith("0.4"):
        rc["dual_v03"] = json.loads(json.dumps(old))
    new = dict(old)
    new.pop("v04", None)
    v04 = {}
    for block, cuts in APPROVED[ccy].items():
        rb = rep["blocks"][block]
        var = rb["variants"].get("B") or {}
        if rb["selection"].get("decision") != "B" or not var.get("cuts"):
            raise SystemExit("%s %s: the replay file does not select variant B" % (ccy, block))
        if any(abs(float(var["cuts"][k]) - cuts[k]) > 1e-9 for k in cuts):
            raise SystemExit("%s %s: replay cuts %s differ from the approved table %s" % (ccy, block, var["cuts"], cuts))
        b12 = (var.get("B") or {}).get("12") or {}
        v04[block] = {"active": True, "component": _component(ccy, block), "cuts": {k: var["cuts"][k] for k in ("injection_enter", "injection_exit", "drain_enter", "drain_exit")},
                      "evidence": {"injection": "frecuencia_de_era", "drain": "frecuencia_de_era", "stability": (var.get("stability") or {}).get("status"),
                                   "B12_rho": b12.get("rho"), "B12_p_bootstrap": b12.get("p_block_bootstrap"), "coverage_era": var.get("coverage_era"),
                                   "sign_warning": bool((b12.get("rho") or 0) > 0.1), "reason": rb["selection"].get("reason")},
                      "selected": SELECTED, "unit": "% of the reserves stock, 5-session sum (weekly components enter as a step)",
                      "rule": "engine v0.4: %s → cuts = era p80/p20 (exit p67/p33) of the 2-print mean, hysteresis + persistence as v0.3; first v0.4 run starts from confirmed NEUTRAL" % _component(ccy, block)["name"]}
    new["v04"] = v04
    new["version"] = "0.4"
    new["status"] = "%s · v0.4 active on %s (%s); other blocks v0.3" % (old.get("status", ""), ", ".join(v04), SELECTED)
    rc["dual"] = new
    cfg["config_version"] = _bump_patch(cfg["config_version"])
    cfg["note"] = "v0.4 activation (%s): %s" % (SELECTED, ", ".join("%s=%s" % (b, v["component"]["name"]) for b, v in v04.items()))
    json.dump(cfg, open(cp, "w", encoding="utf-8"), indent=ind, ensure_ascii=False)
    return "%s: v0.4 applied — %s · config_version %s" % (ccy, " · ".join("%s %s %s/%s %s/%s" % (b, v["component"]["name"], v["cuts"]["injection_enter"], v["cuts"]["injection_exit"], v["cuts"]["drain_enter"], v["cuts"]["drain_exit"]) for b, v in v04.items()), cfg["config_version"])


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
