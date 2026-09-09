"""Jefe de mesa — cross-sectional ranking of the eight G8 currencies by the validated conviction measure
(ICL 1.0, 2026-09-09): Δ13-week change of central-bank reserves as % of the stock 13 weeks earlier,
demeaned across the available currencies each Friday and scaled by the as-of pooled era σ (conviction.cross_section).

Inputs: calibration/conviction/reserves_panel.json (frozen weekly panel from the replays) extended with the live
history CSVs (history/<ccy>/<csv>) so the ranking keeps moving after the replay end. Deterministic, no HTTP.
Output: dict published as data/mesa/jefe.json and embedded in every data/<ccy>/agent.json (F7)."""
from __future__ import annotations

import csv
import json
import os
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import bisect
import math

CCYS = ["cad", "gbp", "aud", "jpy", "chf", "nzd", "usd", "eur"]
MIN_XS = 5


# pure-python copies of the conviction.py helpers (the GitHub runner has no numpy/scipy)
def _fridays(start: str, end: str) -> List[str]:
    d = date.fromisoformat(start)
    while d.weekday() != 4:
        d += timedelta(days=1)
    out = []
    while d.isoformat() <= end:
        out.append(d.isoformat())
        d += timedelta(days=7)
    return out


def _asof(series: List[Tuple[str, float]], d: str, max_gap: int = 10) -> Optional[float]:
    if not series:
        return None
    ds = [x for x, _ in series]
    i = bisect.bisect_right(ds, d) - 1
    if i < 0 or (date.fromisoformat(d) - date.fromisoformat(ds[i])).days > max_gap:
        return None
    return series[i][1]


def _sd(xs: List[float]) -> float:
    n = len(xs)
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _percentile(xs: List[float], q: float) -> float:
    """numpy default (linear interpolation) percentile."""
    s = sorted(xs)
    k = (len(s) - 1) * q / 100.0
    f, c = math.floor(k), math.ceil(k)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def cross_section(n_by_ccy: Dict[str, Dict[str, Optional[float]]], grid: List[str]) -> Tuple[Dict[str, Dict[str, float]], Dict[str, dict]]:
    """Identical to conviction.cross_section(scale='pooled', center='mean'): demean each week, scale by the as-of pooled σ."""
    Z: Dict[str, Dict[str, float]] = {c: {} for c in n_by_ccy}
    meta: Dict[str, dict] = {}
    pooled: List[float] = []
    for g in grid:
        vals = {c: n_by_ccy[c].get(g) for c in n_by_ccy}
        vals = {c: v for c, v in vals.items() if v is not None}
        if len(vals) < MIN_XS:
            meta[g] = {"n": len(vals)}
            continue
        ctr = sum(vals.values()) / len(vals)
        dem = {c: v - ctr for c, v in vals.items()}
        sd_week = _sd(list(dem.values()))
        pooled.extend(dem.values())
        sd_pool = _sd(pooled) if len(pooled) >= 30 else None
        if not sd_pool:
            meta[g] = {"n": len(vals), "sd_week": sd_week, "sd_pooled": sd_pool}
            continue
        for c, v in dem.items():
            Z[c][g] = v / sd_pool
        meta[g] = {"n": len(vals), "sd_week": sd_week, "sd_pooled": sd_pool}
    return Z, meta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "calibration", "conviction", "reserves_panel.json")
MIN_SIGMA_HIST = 26
LABEL = "basado sólo en reservas del banco central; Tesoro pendiente de prerregistro (T1–T3)"
SIGNATURE = "firma ICL 1.0 (2026-09-09): IC(8) > 0, IC(13) > 0, IC(26) ≤ 0; IC 13 s +0,124 (q BH 0,006), tercil que más inyecta pierde 0,46 % por trimestre frente al que más drena (divisa por USD)"
NAMES = {"usd": "USD", "eur": "EUR", "gbp": "GBP", "jpy": "JPY", "chf": "CHF", "cad": "CAD", "aud": "AUD", "nzd": "NZD"}


def _read_hist(path: str, col: str) -> List[Tuple[str, float]]:
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out.append((r["date"], float(r[col])))
            except Exception:
                continue
    out.sort()
    return out


def load_series(root: str = ROOT) -> Tuple[dict, Dict[str, List[Tuple[str, float]]]]:
    P = json.load(open(PANEL if root == ROOT else os.path.join(root, "calibration", "conviction", "reserves_panel.json"), encoding="utf-8"))
    S: Dict[str, List[Tuple[str, float]]] = {}
    for c in CCYS:
        wk = [(d, float(v)) for d, v in P["weekly"].get(c, [])]
        d = P["definition"][c]
        live = _read_hist(os.path.join(root, "history", c, d["history_csv"]), d["column"])
        last = wk[-1][0] if wk else "0000"
        ext = [(x, v) for x, v in live if x > last]
        S[c] = wk + ext
        P["definition"][c]["live_points_used"] = len(ext)
        P["definition"][c]["live_last"] = live[-1][0] if live else None
    return P, S


def compute(as_of: Optional[str] = None, root: str = ROOT) -> dict:
    P, S = load_series(root)
    today = date.fromisoformat(as_of) if as_of else date.today()
    grid = _fridays("2014-01-03", today.isoformat())
    era = {c: P["definition"][c]["era_start"] for c in CCYS}
    A: Dict[str, Dict[str, float]] = {c: {} for c in CCYS}
    VAL: Dict[str, Dict[str, Tuple[float, float, str]]] = {c: {} for c in CCYS}
    for c in CCYS:
        ser = S[c]
        vals = {g: _asof(ser, g, 10) for g in grid}
        for i, g in enumerate(grid):
            if i < 13 or g < era[c]:
                continue
            v, v0 = vals.get(g), vals.get(grid[i - 13])
            if v is None or v0 is None or not v0:
                continue
            A[c][g] = (v - v0) / abs(v0) * 100.0
            VAL[c][g] = (v, v0, grid[i - 13])
    Z, meta = cross_section(A, grid)
    # latest Friday with a full-enough cross-section
    use = None
    for g in reversed(grid):
        if meta.get(g, {}).get("n", 0) >= MIN_XS and any(Z[c].get(g) is not None for c in CCYS):
            use = g
            break
    if use is None:
        return {"status": "unavailable", "reason": "cross-section < %d currencies" % MIN_XS}
    gi = grid.index(use)

    def ranking_at(g: str) -> List[str]:
        zz = {c: Z[c][g] for c in CCYS if Z[c].get(g) is not None}
        return sorted(zz, key=lambda c: -zz[c])  # rank 1 = most reserve growth (relatively weaker currency under the MMT sign)

    rk = ranking_at(use)
    prev = ranking_at(grid[gi - 1]) if gi >= 1 else []
    ago4 = ranking_at(grid[gi - 4]) if gi >= 4 else []
    # dispersion label: this week's σ vs the as-of p20 of weekly σ over the era of the panel (weeks with a cross-section)
    sd_hist = [meta[g]["sd_week"] for g in grid[:gi] if meta.get(g, {}).get("sd_week") is not None and meta[g].get("n", 0) >= MIN_XS]
    sd_week = meta[use].get("sd_week")
    p20 = _percentile(sd_hist, 20) if len(sd_hist) >= MIN_SIGMA_HIST else None
    low = bool(p20 is not None and sd_week is not None and sd_week < p20)
    rows = []
    for i, c in enumerate(rk):
        v, v0, d0 = VAL[c][use]
        rows.append({"ccy": NAMES[c], "rank": i + 1, "d13_pct": round(A[c][use], 2), "z": round(Z[c][use], 2),
                     "rank_prev_week": (prev.index(c) + 1) if c in prev else None, "rank_4w_ago": (ago4.index(c) + 1) if c in ago4 else None,
                     "reserves_now": v, "reserves_13w_ago": v0, "date_13w_ago": d0, "field": P["definition"][c]["field"],
                     "source_column": P["definition"][c]["column"]})
    missing = [NAMES[c] for c in CCYS if c not in rk]
    return {"status": "ok", "as_of_friday": use, "measure": "Δ13 semanas de las reservas del banco central en % del stock de hace 13 semanas; demeaned entre las divisas disponibles; Z = valor / σ agrupada de la era (as-of)",
            "n": len(rk), "missing": missing, "ranking": rows, "sigma_week": round(sd_week, 3) if sd_week else None, "sigma_pooled": round(meta[use]["sd_pooled"], 3) if meta[use].get("sd_pooled") else None,
            "sigma_week_p20_era": round(p20, 3) if p20 else None, "low_dispersion": low, "sigma_history_weeks": len(sd_hist),
            "pair_max_conviction": {"reserves_growth": rows[0]["ccy"], "reserves_drain": rows[-1]["ccy"], "z_gap": round(rows[0]["z"] - rows[-1]["z"], 2)} if len(rows) >= 2 else None,
            "label": LABEL, "signature": SIGNATURE, "bootstrap_by_position": "no calculable con una sola sección transversal; pendiente (Kimi, ronda 3)",
            "panel": {"replay_end": max(P["weekly"][c][-1][0] for c in CCYS if P["weekly"].get(c)), "live_extension": {NAMES[c]: P["definition"][c]["live_points_used"] for c in CCYS}}}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--write", action="store_true", help="write data/mesa/jefe.json")
    a = ap.parse_args(argv)
    out = compute(a.as_of)
    if a.write:
        p = os.path.join(ROOT, "data", "mesa", "jefe.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(out, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
