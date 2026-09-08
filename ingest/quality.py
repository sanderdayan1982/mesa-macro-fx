"""Data quality pipeline — port of Canada Command Center v2.0 quality.mjs + holidays.mjs.
Dedup, MAD modified z-score outliers (rolling 20), holiday-aware null streaks, confidence 0-100.
Desk Standard correction: a null is never 'amber' — a series without data is `unavailable`."""
from __future__ import annotations
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from .series import Series

STATUS_ORDER = ["fresh", "stale", "proxy", "degraded", "unavailable"]


def _is_weekend(d: str) -> bool:
    return datetime.strptime(d, "%Y-%m-%d").weekday() >= 5


def expected_missing(d: str, holidays: List[str]) -> bool:
    return _is_weekend(d) or d in holidays


def modified_z(series: Series, z_thresh: float = 3.5, window: int = 20, min_points: int = 5) -> List[dict]:
    vals = [v for _, v in series]
    out = []
    for i, (d, v) in enumerate(series):
        if v is None:
            out.append({"date": d, "value": None, "outlier": False, "mz": 0.0})
            continue
        win = [x for x in vals[max(0, i - window):i + 1] if x is not None]
        if len(win) < min_points:
            out.append({"date": d, "value": v, "outlier": False, "mz": 0.0})
            continue
        s = sorted(win)
        med = s[len(s) // 2]
        mads = sorted(abs(x - med) for x in s)
        mad = mads[len(mads) // 2]
        mz = 0.0 if mad == 0 else 0.6745 * (v - med) / mad
        out.append({"date": d, "value": v, "outlier": abs(mz) > z_thresh, "mz": round(mz, 2)})
    return out


def freshness(last_date: Optional[str], frequency: str, cfg: dict, now: Optional[datetime] = None, lag_days: int = 0) -> Dict[str, object]:
    """fresh: age <= 1.5 x nominal period; stale: <= 3 x; else unavailable-by-age (reported as 'stale' with age flag).
    Monthly series get the configured publication-lag allowance."""
    now = now or datetime.now(timezone.utc)
    if not last_date:
        return {"status": "unavailable", "age_days": None}
    age = (now.date() - datetime.strptime(last_date, "%Y-%m-%d").date()).days
    rules = cfg.get("status_rules", {})
    period = rules.get("nominal_period_days", {}).get(frequency, 7)
    if frequency == "monthly":
        period = period + rules.get("monthly_lag_allowance_days", 75)
    period = period + lag_days
    fresh_mult = rules.get("fresh_multiplier", 1.5)
    stale_mult = rules.get("stale_multiplier", 3.0)
    if age <= period * fresh_mult:
        st = "fresh"
    elif age <= period * stale_mult:
        st = "stale"
    else:
        st = "stale"  # very old but present: still shown, flagged by age
    return {"status": st, "age_days": age}


def evaluate_series(name: str, series: Series, frequency: str, cfg: dict, z_thresh: float = 3.5,
                    holidays: Optional[List[str]] = None, now: Optional[datetime] = None, lag_days: int = 0) -> dict:
    holidays = holidays or []
    if not series:
        return {"name": name, "total_points": 0, "valid_points": 0, "outliers": 0, "last_valid_date": None,
                "freshness": "unavailable", "age_days": None,
                "confidence": {"score": 0, "tier": "CRITICAL", "penalties": [{"type": "empty", "penalty": 100}]}}
    checked = modified_z(series, z_thresh)
    valid = [p for p in checked if p["value"] is not None]
    last_valid = valid[-1]["date"] if valid else None
    fr = freshness(last_valid, frequency, cfg, now, lag_days)
    score, pen = 100, []
    if fr["status"] == "stale":
        p = 30 if fr["age_days"] and fr["age_days"] > 3 * cfg.get("status_rules", {}).get("nominal_period_days", {}).get(frequency, 7) else 15
        score -= p
        pen.append({"type": "stale", "penalty": p})
    # unexpected nulls in last 30 (only meaningful for daily series with explicit nulls)
    recent = checked[-30:]
    unexp = sum(1 for p in recent if p["value"] is None and not expected_missing(p["date"], holidays))
    if unexp:
        p = round(40 * unexp / len(recent))
        score -= p
        pen.append({"type": "nulls", "penalty": p})
    if valid and valid[-1]["outlier"]:
        p = 15 if abs(valid[-1]["mz"]) > 5 else 8
        score -= p
        pen.append({"type": "outlier", "penalty": p})
    score = max(0, min(100, score))
    tier = "HIGH" if score >= 90 else "MEDIUM" if score >= 70 else "LOW" if score >= 50 else "CRITICAL"
    return {"name": name, "total_points": len(checked), "valid_points": len(valid),
            "outliers": sum(1 for p in checked if p["outlier"]), "last_valid_date": last_valid,
            "latest_outlier": bool(valid and valid[-1]["outlier"]), "latest_mz": valid[-1]["mz"] if valid else None,
            "freshness": fr["status"], "age_days": fr["age_days"],
            "confidence": {"score": score, "tier": tier, "penalties": pen}}


def system_summary(per_series: Dict[str, dict]) -> dict:
    scores = [v["confidence"]["score"] for v in per_series.values()]
    if not scores:
        return {"average": 0, "abv90": 0, "blw70": 0, "lowest": None}
    lowest = min(per_series.items(), key=lambda kv: kv[1]["confidence"]["score"])
    return {"average": round(sum(scores) / len(scores)), "abv90": sum(1 for s in scores if s >= 90),
            "blw70": sum(1 for s in scores if s < 70), "lowest": {"series": lowest[0], "score": lowest[1]["confidence"]["score"]}}
