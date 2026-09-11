"""One-off: freeze the weekly Friday panel of the v0.3 fiscal FLOWS-ONLY score used by T1/T2 (jefe de mesa v2, Treasury column).

Same code path as conviction_t123: conviction.load_panel reads the cached replays and rescores the fiscal components at
level weight 0 (D["ccy"][c]["fi"]); here that print series is sampled on the Friday grid (as-of ≤ 10 days) and written to
calibration/conviction/fiscal_panel.json with the same shape as reserves_panel.json. The live engine extends it from
history/<ccy>/fiscal_flows_score.csv (ingest/run.py). numpy is allowed here (calibration only), never in jefe.py.

    python -m ingest.build_fiscal_panel --cache-dir <dir with v03_<ccy>.pkl> [--fixtures-root fixtures] [--out calibration/conviction/fiscal_panel.json]
"""
from __future__ import annotations
import argparse
import json
import os
from datetime import date, timedelta

from .conviction import CCYS, ROOT, _asof, _fridays, load_panel

GRID_START = "2014-01-03"   # same first Friday as reserves_panel.json
COLUMN = "fiscal_flows_score"


def build(cache_dir: str, fx_root: str) -> dict:
    D = load_panel(cache_dir, fx_root)
    out = {"generated_at": date.today().isoformat(),
           "note": "Weekly (Friday, as-of ≤ 10 days) v0.3 fiscal flows-only block score (components rescored at level weight 0) from the v0.3 "
                   "calibration replays — the T1/T2 signal (T123.md, 2026-09-11). The live engine extends it from history/<ccy>/%s.csv." % COLUMN,
           "definition": {}, "weekly": {}}
    for c in CCYS:
        fi = D["ccy"][c]["fi"]
        grid = _fridays(GRID_START, (date.fromisoformat(fi[-1][0]) + timedelta(days=6)).isoformat())  # up to the Friday that sees the last print
        wk = [[g, v] for g in grid for v in [_asof(fi, g, 10)] if v is not None]
        out["weekly"][c] = wk
        out["definition"][c] = {"field": COLUMN, "history_csv": "%s.csv" % COLUMN, "column": COLUMN, "era_start": D["ccy"][c]["era"],
                                "replay_first": fi[0][0], "replay_last": fi[-1][0]}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--fixtures-root", default=os.path.join(ROOT, "fixtures"))
    ap.add_argument("--out", default=os.path.join(ROOT, "calibration", "conviction", "fiscal_panel.json"))
    a = ap.parse_args(argv)
    P = build(a.cache_dir, a.fixtures_root)
    json.dump(P, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for c in CCYS:
        w = P["weekly"][c]
        print("%s %d weeks %s → %s (era %s)" % (c, len(w), w[0][0], w[-1][0], P["definition"][c]["era_start"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
