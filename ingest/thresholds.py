"""Threshold engine — Desk Standard 1.4.
Primary: rolling distribution-free percentiles (WATCH/STRESS/CRISIS) with Schmitt hysteresis (exit at the lower
level's percentile). Absolute institutional anchors (BoC settlement-balance range, Advances > 0, corridor) when the
config declares them. Rule 'worst_of': the reported level is the more severe of primary and secondary so that an
institutional breach is never hidden by a benign percentile (and vice versa). All numbers come from config, never code."""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from .series import Series, window_sample, percentile_rank, percentile_value, parse_window

LEVELS = ["SAFE", "WATCH", "STRESS", "CRISIS"]

# ── era anchoring (engine v0.3): percentile windows never reach back before the operating era ──
# run.py / calibrate.py set it from config regime.dual.era_start (None = v0.2 rolling windows). A spec can opt out with
# "era_anchor": false. When the era holds fewer than min_n points the rolling window is used and the result is flagged era_thin.
_ERA: Dict[str, Optional[str]] = {"start": None}


def set_era_anchor(start: Optional[str]) -> None:
    _ERA["start"] = start


def era_anchor() -> Optional[str]:
    return _ERA["start"]


def _sample(series: Series, window: int, spec: dict, min_n: int):
    """(sample, era_thin) — values inside the window, excluding the latest print; truncated to the era when anchored."""
    start = _ERA["start"]
    if start and spec.get("era_anchor", True):
        v = [x for d, x in series if x is not None and d >= start]
        era = v[-window - 1:-1] if len(v) > 1 else []
        if len(era) >= min_n:
            return era, False
        return window_sample(series, window), True
    return window_sample(series, window), False


def _rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else 0


def _worse(a: str, b: str) -> str:
    return a if _rank(a) >= _rank(b) else b


def _pct_num(p) -> Optional[float]:
    if isinstance(p, str) and p.startswith("p"):
        return float(p[1:])
    return None


def _exit_map(spec: dict, entries: List[Tuple[str, float]]) -> Dict[str, float]:
    """exit_on 'p70/p80/p90' aligned with WATCH/STRESS/CRISIS entries; default = previous level's entry pct."""
    raw = (spec.get("hysteresis") or {}).get("exit_on", "")
    parts = [_pct_num(x.strip()) for x in raw.split("/") if x.strip()] if raw else []
    out = {}
    for i, (lvl, entry) in enumerate(entries):
        out[lvl] = parts[i] if i < len(parts) and parts[i] is not None else (entries[i - 1][1] if i > 0 else entry)
    return out


def percentile_level(value: float, series: Series, spec: dict, freq: str, prev_level: Optional[str]) -> dict:
    window = parse_window(spec.get("window", "156w"), freq)
    min_n = spec.get("min_n", {"daily": 120, "weekly": 26, "monthly": 12}.get(freq, 20))
    sample, era_thin = _sample(series, window, spec, min_n)
    if len(sample) < min_n:
        # thin history: never escalate on percentiles (a 70-day window makes any max a 'CRISIS'); absolute anchors still apply
        return {"level": "SAFE", "percentile": percentile_rank(value, sample) if len(sample) >= 5 else None, "resolved": {}, "insufficient_history": True, "n": len(sample)}
    r = percentile_rank(value, sample)
    low_is_risk = spec.get("direction") in ("low_is_risk", "low_is_qt")
    # entries: level -> percentile threshold (for low_is_risk we mirror: below pX)
    entries: List[Tuple[str, float]] = []
    for lvl, key in (("WATCH", "watch"), ("STRESS", "stress"), ("CRISIS", "crisis")):
        k = key + ("_below" if low_is_risk else "_above")
        p = _pct_num(spec.get(k))
        if p is not None:
            entries.append((lvl, p))
    resolved = {lvl: percentile_value(sample, p) for lvl, p in entries}
    level = "SAFE"
    for lvl, p in entries:
        hit = (r <= p) if low_is_risk else (r >= p)
        if hit:
            level = lvl
    # hysteresis: stay in prev level while still beyond its exit percentile
    if prev_level and _rank(prev_level) > _rank(level):
        ex = _exit_map(spec, entries)
        thr = ex.get(prev_level)
        if thr is not None:
            still = (r <= thr) if low_is_risk else (r >= thr)
            if still:
                level = prev_level
    return {"level": level, "percentile": r, "resolved": resolved, "insufficient_history": False, "n": len(sample),
            "window": spec.get("window"), "era_anchor": (_ERA["start"] if (_ERA["start"] and spec.get("era_anchor", True) and not era_thin) else None), "era_thin": era_thin}


def absolute_level(value: float, spec: dict) -> dict:
    """Generic absolute thresholds. Keys understood: watch_above/stress_above/crisis_above, watch_below/stress_below/
    crisis_below, and the BoC-range form primary_absolute{boc_target_range, below_range_watch, stress_below, crisis_below}."""
    level, resolved = "SAFE", {}
    s = spec.get("primary_absolute") or spec.get("secondary_absolute") or spec
    rng = s.get("boc_target_range")
    if rng:
        lo, hi = rng
        resolved = {"range_low": lo, "range_high": hi, "STRESS": s.get("stress_below"), "CRISIS": s.get("crisis_below")}
        if value < lo:
            level = "WATCH"
        if s.get("stress_below") is not None and value < s["stress_below"]:
            level = "STRESS"
        if s.get("crisis_below") is not None and value < s["crisis_below"]:
            level = "CRISIS"
        return {"level": level, "resolved": resolved, "in_range": lo <= value <= hi, "above_range": value > hi}
    for lvl, key in (("WATCH", "watch"), ("STRESS", "stress"), ("CRISIS", "crisis")):
        a, b = s.get(key + "_above", s.get(key)), s.get(key + "_below")
        if a is not None:
            resolved[lvl] = a
            if value > a if key == "watch" and s.get(key + "_above") == 0 else value >= a:
                level = lvl
        if b is not None:
            resolved[lvl] = b
            if value < b:
                level = lvl
    return {"level": level, "resolved": resolved}


def classify(value: Optional[float], series: Series, spec: dict, freq: str, prev_level: Optional[str] = None) -> dict:
    """Returns {level, method, primary, secondary, percentile, thresholds}. None value -> NO DATA (never SAFE)."""
    if value is None:
        return {"level": "NO DATA", "method": spec.get("method"), "percentile": None, "thresholds": {}}
    method = spec.get("method", "percentile")
    out = {"method": method, "percentile": None, "thresholds": {}, "rule": "worst_of"}
    if method == "percentile":
        pr = percentile_level(value, series, spec, freq, prev_level)
        out["primary"] = pr
        out["percentile"] = pr["percentile"]
        out["thresholds"] = {"method": "percentile", "levels": pr["resolved"], "window": spec.get("window"), "n": pr["n"], "era_anchor": pr.get("era_anchor"), "era_thin": pr.get("era_thin", False)}
        level = pr["level"]
        if spec.get("secondary_absolute"):
            sec = absolute_level(value, {"secondary_absolute": spec["secondary_absolute"]})
            out["secondary"] = sec
            level = _worse(level, sec["level"])
        out["level"] = level
    elif method == "absolute_primary":
        pa = absolute_level(value, spec)
        out["primary"] = pa
        out["thresholds"] = {"method": "absolute", "levels": pa["resolved"]}
        level = pa["level"]
        if spec.get("secondary_percentile"):
            sp = percentile_level(value, series, dict(spec["secondary_percentile"], direction=spec.get("direction", "low_is_risk")), freq, None)
            out["secondary"] = sp
            out["percentile"] = sp["percentile"]
            # informational only: institutional anchor is the level (triangulation: level percentiles cross policy regimes)
            out["secondary_percentile_level"] = sp["level"]
        out["level"] = level
        out["in_range"] = pa.get("in_range")
        if "above_range" in pa:
            out["above_range"] = pa["above_range"]
    elif method == "absolute":
        pa = absolute_level(value, spec)
        out["primary"] = pa
        out["thresholds"] = {"method": "absolute", "levels": pa["resolved"]}
        out["level"] = pa["level"]
    elif method == "zscore":
        z = value
        lvl = "SAFE"
        if abs(z) >= spec.get("extraordinary_above", 2.0):
            lvl = "STRESS"
        elif abs(z) >= spec.get("notable_above", 1.0):
            lvl = "WATCH"
        out["level"] = lvl
        out["thresholds"] = {"method": "zscore", "levels": {"WATCH": spec.get("notable_above", 1.0), "STRESS": spec.get("extraordinary_above", 2.0)}}
    else:
        out["level"] = "SAFE"
    return out


def signal_band(value: Optional[float], series: Series, spec: dict, freq: str) -> dict:
    """Risk-on / risk-off style two-sided signal (net liquidity Δ%). Percentile primary + absolute secondary."""
    if value is None:
        return {"signal": "NO DATA", "percentile": None}
    window = parse_window(spec.get("window", "156w"), freq)
    sample, era_thin = _sample(series, window, spec, spec.get("min_n", 20))
    r = percentile_rank(value, sample) if len(sample) >= 20 else None
    sig = "NEUTRAL"
    on, off = _pct_num(spec.get("risk_on_above")), _pct_num(spec.get("risk_off_below"))
    if r is not None:
        if on is not None and r >= on:
            sig = "RISK_ON"
        elif off is not None and r <= off:
            sig = "RISK_OFF"
    sec = spec.get("secondary_absolute") or {}
    if sec.get("risk_on") is not None and value >= sec["risk_on"]:
        sig = "RISK_ON"
    if sec.get("risk_off") is not None and value <= sec["risk_off"]:
        sig = "RISK_OFF"
    return {"signal": sig, "percentile": r, "n": len(sample), "era_anchor": (_ERA["start"] if (_ERA["start"] and spec.get("era_anchor", True) and not era_thin) else None), "era_thin": era_thin,
            "thresholds": {"risk_on_pct": on, "risk_off_pct": off, "abs": sec,
            "resolved": {"risk_on": percentile_value(sample, on) if (r is not None and on) else None,
                         "risk_off": percentile_value(sample, off) if (r is not None and off) else None}}}
