"""Jefe de mesa — cross-sectional ranking of the eight G8 currencies by the validated conviction measure
(ICL 1.0, 2026-09-09): Δ13-week change of central-bank reserves as % of the stock 13 weeks earlier,
demeaned across the available currencies each Friday and scaled by the as-of pooled era σ (conviction.cross_section).

Inputs: calibration/conviction/reserves_panel.json (frozen weekly panel from the replays) extended with the live
history CSVs (history/<ccy>/<csv>) so the ranking keeps moving after the replay end. Deterministic, no HTTP.
Jefe de mesa v2 (adjudication 2026-09-11): a second, parallel Treasury column (13-week mean of the v0.3 fiscal flows-only score,
Φ⁻¹ of its as-of era percentile, same cross_section → Z; validated as T1/T2) from calibration/conviction/fiscal_panel.json extended
with history/<ccy>/fiscal_flows_score.csv, and one plumbing label per currency (abundante / escasa / vulnerable / sin señal) from the
terciles of both rankings and the price gate of regime.json. BC and Treasury are never combined into one number (no net pair).
Output: dict published as data/mesa/jefe.json and embedded in every data/<ccy>/agent.json (F7)."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
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

def norm_ppf(p: float) -> float:
    """Inverse normal CDF, pure Python: Acklam's rational approximation (|rel. err| < 1.15e-9) refined by one Halley step on
    math.erfc (machine precision; checked against scipy.stats.norm.ppf in tests_v04 --ccy activation)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p outside (0, 1)")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    plow = 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    elif p > 1 - plow:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    else:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    # Halley refinement on the nearer tail (Φ(x) − p in the upper tail would cancel; use (1 − p) − (1 − Φ(x)) instead)
    e = (0.5 * math.erfc(-x / math.sqrt(2)) - p) if x <= 0 else ((1 - p) - 0.5 * math.erfc(x / math.sqrt(2)))
    u = e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)
    return x - u / (1 + x * u / 2)


def asof_era_percentile(series: Dict[str, float], era: str, grid: List[str], min_n: int = 26, clip: float = 2.5, pct: Optional[Dict[str, float]] = None) -> Dict[str, Optional[float]]:
    """Φ⁻¹ of the as-of era percentile of a series already on the Friday grid — the conviction.asof_percentile convention
    (expanding window inside the era, min 26 weeks, (r − 0.5)/N with ties at mid-rank, clip ±2.5)."""
    out: Dict[str, Optional[float]] = {}
    sample: List[float] = []
    for g in grid:
        x = series.get(g)
        if x is None or g < era:
            out[g] = None
            continue
        sample.append(x)
        N = len(sample)
        if N < min_n:
            out[g] = None
            continue
        r_lt = sum(1 for v in sample if v < x)
        r_eq = sum(1 for v in sample if v == x)
        p = (r_lt + 0.5 * r_eq) / N
        p = min(max(p, 0.5 / N), 1 - 0.5 / N)
        if pct is not None:
            pct[g] = p
        out[g] = max(-clip, min(clip, norm_ppf(p)))
    return out


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "calibration", "conviction", "reserves_panel.json")
FISCAL_PANEL = os.path.join(ROOT, "calibration", "conviction", "fiscal_panel.json")
MIN_SIGMA_HIST = 26
WIN_T = 13                      # weeks of the Treasury flow mean (T1/T2)
PROXY = {"gbp", "nzd", "chf"}   # fiscal driver is a proxy/band (adjudication 2026-09-11)
LABEL = "momento de flujo de reservas a un trimestre, 8–13 s"
LABEL_T = "impulso fiscal a un trimestre, 13–26 s (más firme a 26)"
SIGNATURE_T = "T1/T2 2026-09-11: IC +0.125 (13 s, q 0.013) / +0.177 (26 s, q 0.0006); T3 y T4 no pasan"
LABELS = ("abundante", "escasa", "vulnerable", "sin señal", "sin señal (compresión)")
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


def load_series(root: str = ROOT, panel: str = "reserves_panel.json") -> Tuple[dict, Dict[str, List[Tuple[str, float]]]]:
    P = json.load(open(os.path.join(root, "calibration", "conviction", panel), encoding="utf-8"))
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


def _ranking_at(Z: Dict[str, Dict[str, float]], g: str) -> List[str]:
    zz = {c: Z[c][g] for c in CCYS if Z[c].get(g) is not None}
    return sorted(zz, key=lambda c: -zz[c])  # rank 1 = highest Z (most relative injection; relatively weaker currency under the MMT sign)


def compute_treasury(grid: List[str], root: str = ROOT) -> dict:
    """Treasury column (jefe de mesa v2): Friday as-of (≤ 10 d) of the fiscal flows-only score → 13-week mean (13 Fridays with a
    value) → Φ⁻¹(as-of era percentile) → clip ±2.5 → cross_section → Z. Validated as T1/T2 (T123.md); T4: the acceleration
    stays a descriptive zero-crossing flag (sign of the 13-week mean vs 13 weeks earlier)."""
    P, S = load_series(root, "fiscal_panel.json")
    V: Dict[str, Dict[str, float]] = {c: {} for c in CCYS}
    N: Dict[str, Dict[str, Optional[float]]] = {}
    PCT: Dict[str, Dict[str, float]] = {c: {} for c in CCYS}
    for c in CCYS:
        vals = {g: _asof(S[c], g, 10) for g in grid}
        for i in range(WIN_T - 1, len(grid)):
            w = [vals[g] for g in grid[i - WIN_T + 1: i + 1]]
            if all(x is not None for x in w):
                V[c][grid[i]] = sum(w) / WIN_T
        N[c] = asof_era_percentile(V[c], P["definition"][c]["era_start"], grid, pct=PCT[c])
    Z, meta = cross_section(N, grid)
    use = next((g for g in reversed(grid) if meta.get(g, {}).get("n", 0) >= MIN_XS and any(Z[c].get(g) is not None for c in CCYS)), None)
    if use is None:
        return {"status": "unavailable", "reason": "cross-section < %d currencies" % MIN_XS, "label": LABEL_T, "signature": SIGNATURE_T}
    gi = grid.index(use)
    rk = _ranking_at(Z, use)
    prev = _ranking_at(Z, grid[gi - 1]) if gi >= 1 else []
    ago4 = _ranking_at(Z, grid[gi - 4]) if gi >= 4 else []
    rows = []
    for i, c in enumerate(rk):
        v13, v13_prev = V[c][use], V[c].get(grid[gi - WIN_T]) if gi >= WIN_T else None
        rows.append({"ccy": NAMES[c], "rank": i + 1, "v13": round(v13, 2), "pct_era": round(PCT[c][use], 3), "z": round(Z[c][use], 2),
                     "rank_prev_week": (prev.index(c) + 1) if c in prev else None, "rank_4w_ago": (ago4.index(c) + 1) if c in ago4 else None,
                     "zero_cross": bool(v13_prev is not None and (v13 > 0) != (v13_prev > 0) and v13 != 0 and v13_prev != 0), "proxy": c in PROXY})
    return {"status": "ok", "as_of_friday": use, "measure": "media de 13 semanas del score de flujos del bloque fiscal (v0.3, sólo flujos) → Φ⁻¹ del percentil as-of de la era (mín. 26 s) → recorte ±2,5; demeaned entre las divisas disponibles; Z = valor / σ agrupada de la era (as-of)",
            "label": LABEL_T, "ranking": rows, "missing": [NAMES[c] for c in CCYS if c not in rk], "n": len(rk), "signature": SIGNATURE_T,
            "sigma_pooled": round(meta[use]["sd_pooled"], 3) if meta[use].get("sd_pooled") else None,
            "z_weekly": _z_weekly(Z, grid[:gi + 1]),
            "panel": {"replay_end": max(P["weekly"][c][-1][0] for c in CCYS if P["weekly"].get(c)), "live_extension": {NAMES[c]: P["definition"][c]["live_points_used"] for c in CCYS}}}


HIST_WEEKS = 52


def _z_weekly(Z: Dict[str, Dict[str, float]], grid: List[str]) -> Dict[str, List[list]]:
    """last HIST_WEEKS Fridays of the cross-sectional Z per currency (null where the currency has no value) — for the ESTADO
    chart (two bars per currency, BC and Tesoro, with their path backwards); presentation only, nothing new is measured."""
    g = grid[-HIST_WEEKS:]
    return {"fridays": g, **{NAMES[c]: [round(Z[c][d], 2) if Z[c].get(d) is not None else None for d in g] for c in CCYS}}


def _tercile(rank: Optional[int], n: int) -> Optional[str]:
    """top / mid / bottom for a rank in a ranking of n (top tercile size = ceil(n/3))."""
    if rank is None or n < 1:
        return None
    k = -(-n // 3)
    return "top" if rank <= k else "bottom" if rank > n - k else "mid"


def plumbing_label(bc_rank: Optional[int], bc_n: int, tr_rank: Optional[int], tr_n: int, price_gate: bool) -> str:
    """Etiqueta de fontanería (adjudicación 2026-09-11, pregunta 1): «abundante = tercil alto de la Z, escasa = tercil bajo,
    vulnerable = tercil bajo y puerta de precio del bloque de tipos ya calibrada por era (FLOOR_FRICTION / spread fuera de banda);
    sin señal = BC y Tesoro en terciles opuestos o bloque sin dato». Two rankings (BC, Tesoro), never combined into one number:
    abundant = at least one in the top tercile and none in the bottom; scarce = at least one in the bottom and none in the top;
    vulnerable = scarce and the price gate is active; no signal = one top and the other bottom, a missing ranking, or — assumption,
    the adjudication is silent — both in the middle tercile (no tercile speaks)."""
    a, b = _tercile(bc_rank, bc_n), _tercile(tr_rank, tr_n)
    if a is None or b is None:
        return "sin señal"
    if "top" in (a, b) and "bottom" not in (a, b):
        return "abundante"
    if "bottom" in (a, b) and "top" not in (a, b):
        return "vulnerable" if price_gate else "escasa"
    return "sin señal"


def _price_gate(root: str, c: str) -> Optional[bool]:
    """regimes.general.price_gate of data/<ccy>/regime.json (engine.classify_regime: non-null when LIQUIDITY_SCARCITY or
    FLOOR_FRICTION was set by the price gate). None when the file/field is absent."""
    p = os.path.join(root, "data", c, "regime.json")
    if not os.path.exists(p):
        return None
    g = (json.load(open(p, encoding="utf-8")).get("regimes") or {}).get("general") or {}
    return bool(g.get("price_gate")) if "price_gate" in g else None


def compute(as_of: Optional[str] = None, root: str = ROOT) -> dict:
    out = compute_bc(as_of, root)
    grid = _fridays("2014-01-03", (date.fromisoformat(as_of) if as_of else date.today()).isoformat())
    try:
        T = compute_treasury(grid, root)
    except Exception as e:  # the Treasury column never withholds the BC ranking
        T = {"status": "unavailable", "reason": "treasury error: %s" % e, "label": LABEL_T, "signature": SIGNATURE_T}
    out["treasury"] = T
    # chart feed (ESTADO): the two Z paths per currency, last HIST_WEEKS Fridays, one grid
    hb, ht = out.pop("z_weekly", None), T.pop("z_weekly", None) if isinstance(T, dict) else None
    if hb:
        out["history"] = {"weeks": HIST_WEEKS, "bc": hb, "treasury": ht}
    bc = {r["ccy"]: r["rank"] for r in out.get("ranking", [])}
    tr = {r["ccy"]: r["rank"] for r in T.get("ranking", [])}
    labels, no_gate = {}, []
    for c in CCYS:
        pg = _price_gate(root, c)
        if pg is None:
            no_gate.append(NAMES[c])
        labels[NAMES[c]] = plumbing_label(bc.get(NAMES[c]), out.get("n", 0), tr.get(NAMES[c]), T.get("n", 0), bool(pg))
    out["labels_tercile"] = labels  # the tercile reading, always published (no metric hidden)
    if out.get("low_dispersion"):
        # Adjudication 2026-09-11 (institutionality round, idea B): with the cross-section compressed (this week's σ below the
        # as-of p20 of the era, a cut that already existed as a flag) the terciles rank noise, so the plumbing label is withheld;
        # the tercile reading stays visible in labels_tercile. No new threshold.
        out["labels"] = {c: COMPRESSED for c in labels}
        out["labels_rule"] = ("sin señal (compresión): σ semanal %s < p20 de la era %s; la lectura por terciles queda en labels_tercile"
                              % (out.get("sigma_week"), out.get("sigma_week_p20_era")))
    else:
        out["labels"] = labels
        out["labels_rule"] = "terciles (techo de n/3) de las Z de BC y Tesoro + puerta de precio (regimes.general.price_gate); vulnerable sólo con puerta activa"
    if no_gate:
        out["labels_no_price_gate"] = no_gate  # label stays «escasa» for these: no price-gate field in regime.json
    # Single truth (idea A): the jefe is recomputed inside every lane, so each daily_log freezes the ranking it saw while
    # data/mesa/jefe.json holds the last one written. The stamp identifies the ranking content (rows and labels); a daily_log
    # whose stamp differs from the published one carries an earlier reading, and says so.
    out["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    out["stamp"] = stamp(out)
    return out


COMPRESSED = "sin señal (compresión)"


def stamp(j: dict) -> str:
    """12 hex of sha256 over the published rankings and labels (content, not time): same panel → same stamp in every lane."""
    core = {"bc": [(r["ccy"], r["d13_pct"], r["z"]) for r in j.get("ranking", [])],
            "as_of": j.get("as_of_friday"),
            "tr": [(r["ccy"], r["v13"], r["z"]) for r in (j.get("treasury") or {}).get("ranking", [])],
            "tr_as_of": (j.get("treasury") or {}).get("as_of_friday"),
            "labels": sorted((j.get("labels") or {}).items())}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def compute_bc(as_of: Optional[str] = None, root: str = ROOT) -> dict:
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

    rk = _ranking_at(Z, use)  # rank 1 = most reserve growth
    prev = _ranking_at(Z, grid[gi - 1]) if gi >= 1 else []
    ago4 = _ranking_at(Z, grid[gi - 4]) if gi >= 4 else []
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
            "z_weekly": _z_weekly(Z, grid[:gi + 1]),
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
