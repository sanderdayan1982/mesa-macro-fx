"""Regime changelog reconstructed from the calibration replay (adjudication 2026-09-11, institutionality round, idea G).

The live changelog in regime_history.json only records changes since the record began. The replay that calibrated the v0.3
cuts (calibration/<ccy>_v03/v03_regimes.csv: weekly grid inside the era, per-block regime with the live hysteresis and the
general agreement rule) is the honest history of what the engine would have said, week by week. Declared deviation: the
live engine reads the 7-day mean on a daily clock, so the exact day of a change can differ from the replay Friday; blocks
now on v0.4 are reconstructed with their v0.3 shadow (the v0.4 replay does not store weekly states). Nothing new is measured.
Output: data/<ccy>/regime_changelog.json."""
from __future__ import annotations

import csv
import json
import os
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCKS = {"central_bank": ("cb_score_lw", "cb_regime"), "fiscal": ("fi_score_lw", "fi_regime")}


def _rows(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("date")]


def _spells(states: List[tuple]) -> dict:
    """transitions, current spell, spell stats from [(date, state)] on the weekly grid."""
    trans, spells = [], []
    cur, since, n = None, None, 0
    for d, s in states:
        if s != cur:
            if cur is not None:
                trans.append({"date": d, "old": cur, "new": s})
                spells.append(n)
            cur, since, n = s, d, 0
        n += 1
    return {"current": cur, "since": since, "weeks_in_current": n, "switches": len(trans),
            "mean_spell_weeks": round(sum(spells) / len(spells), 1) if spells else None, "transitions": trans}


def _band_weeks(rows: List[dict], score_col: str, reg_col: str, cuts: Optional[dict]) -> Optional[int]:
    """weeks the block stayed in INJECTION/DRAIN while its score sat inside the hysteresis band (past the exit cut but not
    beyond the enter cut): the flips a memoryless engine would have made and the hysteresis did not."""
    if not cuts:
        return None
    k = 0
    for r in rows:
        try:
            s = float(r[score_col])
        except Exception:
            continue
        st = r.get(reg_col)
        if st == "INJECTION" and cuts["injection_exit"] <= s < cuts["injection_enter"]:
            k += 1
        elif st == "DRAIN" and cuts["drain_enter"] < s <= cuts["drain_exit"]:
            k += 1
    return k


def build(ccy: str, root: str = ROOT) -> dict:
    rows = _rows(os.path.join(root, "calibration", "%s_v03" % ccy, "v03_regimes.csv"))
    cfg = {}
    try:
        cfg = json.load(open(os.path.join(root, "config", "%s.json" % ccy), encoding="utf-8"))
    except Exception:
        pass
    dual = ((cfg.get("regime") or {}).get("dual")) or {}
    th = dual.get("block_thresholds") or {}
    v04 = dual.get("v04") or {}
    out = {"currency": ccy.upper(), "source": "replay v0.3 (calibration/%s_v03/v03_regimes.csv): rejilla semanal dentro de la era, cortes e histéresis vivos, regla de acuerdo para el general" % ccy,
           "deviation": "el motor vivo lee la media de 7 días con reloj diario: el día exacto de un cambio puede diferir del viernes del replay; los bloques en v0.4 se reconstruyen con su sombra v0.3 (el replay v0.4 no guarda estados semanales)",
           "weeks": len(rows), "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None, "blocks": {}}
    if not rows:
        out["status"] = "unavailable"
        return out
    for b, (sc, rc) in BLOCKS.items():
        sp = _spells([(r["date"], r[rc]) for r in rows if r.get(rc)])
        sp["engine_today"] = "v0.4" if (v04.get(b) or {}).get("active") else "v0.3"
        sp["hysteresis_band_weeks"] = _band_weeks(rows, sc, rc, th.get(b))
        sp["cuts_v03"] = {k: th[b][k] for k in ("injection_enter", "injection_exit", "drain_enter", "drain_exit")} if th.get(b) else None
        sp["transitions"] = sp["transitions"][-12:]
        out["blocks"][b] = sp
    g = _spells([(r["date"], r["general"]) for r in rows if r.get("general")])
    g["transitions"] = g["transitions"][-12:]
    out["blocks"]["general"] = g
    out["status"] = "ok"
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccy", default="usd")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    o = build(a.ccy.lower())
    if a.write:
        p = os.path.join(ROOT, "data", a.ccy.lower(), "regime_changelog.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(o, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in o.items() if k != "blocks"}, ensure_ascii=False))
    for b, s in o.get("blocks", {}).items():
        print(b, {k: v for k, v in s.items() if k != "transitions"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
