"""Data quality pipeline — port of Canada Command Center v2.0 quality.mjs + holidays.mjs.
Dedup, MAD modified z-score outliers (rolling 20), holiday-aware null streaks, confidence 0-100.
Desk Standard correction: a null is never 'amber' — a series without data is `unavailable`."""
from __future__ import annotations
import math
from datetime import datetime, timedelta, timezone, date
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


def weekly_friday_freshness(last: date, today: date) -> str:
    """Presentation calendar for a Friday weekly print (t330u).

    Fresh during the ISO week of the last print and the following ISO week.
    Stale once that following week has ended without a new print.
    """
    week_start = last - timedelta(days=last.weekday())  # Monday
    following_week_end = week_start + timedelta(days=13)  # Sunday of the next week
    return "fresh" if today <= following_week_end else "stale"


# Official publication calendars (t331u). A print is "source_current"
# ("AL DÍA CON LA FUENTE") until the next expected official release is overdue.
OFFICIAL_CALENDARS = {
    "pspc_sqt_dcb": {
        "url": "https://donnees-data.tpsgc-pwgsc.gc.ca/ba1/sqt-dcb/sqt-dcb.csv",
        "portal": "https://open.canada.ca/data/en/dataset/477bf61b-e764-4f24-8a8a-687a5755002e",
        "kind": "monthly_day",
        "day": 4,
        "label": "PSPC Receiver General Daily Cash Balance (sqt-dcb), monthly ~day 4",
    },
    "statcan_10100116": {
        "url": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1010011601",
        "portal": "https://www150.statcan.gc.ca/n1/dai-quo/cal2-eng.htm",
        "kind": "weeks_after_month_end",
        "weeks": 8,
        "label": "StatCan 10-10-0116-01 / BoC C2, ~7–8 weeks after month-end",
    },
}


def _month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def _shift_month(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, _month_end(date(y, m, 1)).day)
    return date(y, m, day)


def next_official_publication(calendar: str, last: date) -> date:
    """Expected next official release after an observation dated `last`."""
    spec = OFFICIAL_CALENDARS[calendar]
    if spec["kind"] == "monthly_day":
        # Last obs in month M is typically posted on day 4 of month M;
        # the next batch is day 4 of M+1.
        nxt = _shift_month(date(last.year, last.month, 1), 1)
        return date(nxt.year, nxt.month, int(spec["day"]))
    if spec["kind"] == "weeks_after_month_end":
        # last is usually the 1st of the reference month (Valet/C2).
        # Next observation = following month; deadline = that month-end + N weeks.
        ref_end = _month_end(last) if last.day == 1 else last
        nxt_ref_end = _month_end(ref_end + timedelta(days=1))
        return nxt_ref_end + timedelta(weeks=int(spec["weeks"]))
    raise ValueError("unknown official calendar kind: %s" % spec.get("kind"))


def official_calendar_freshness(last: date, today: date, calendar: str) -> dict:
    spec = OFFICIAL_CALENDARS[calendar]
    nxt = next_official_publication(calendar, last)
    st = "source_current" if today <= nxt else "stale"
    return {
        "status": st,
        "next_publication": nxt.isoformat(),
        "calendar": calendar,
        "calendar_url": spec["url"],
        "calendar_label": spec["label"],
    }


def freshness(last_date: Optional[str], frequency: str, cfg: dict, now: Optional[datetime] = None, lag_days: int = 0,
              calendar: Optional[str] = None) -> Dict[str, object]:
    """fresh: age <= 1.5 x nominal period; stale: <= 3 x; else unavailable-by-age (reported as 'stale' with age flag).
    Monthly series get the configured publication-lag allowance.
    calendar='weekly_friday' uses the Friday weekly presentation rule instead of 1.5×/3×."""
    now = now or datetime.now(timezone.utc)
    if not last_date:
        return {"status": "unavailable", "age_days": None}
    last = datetime.strptime(last_date, "%Y-%m-%d").date()
    age = (now.date() - last).days
    if calendar == "weekly_friday":
        return {"status": weekly_friday_freshness(last, now.date()), "age_days": age}
    if calendar in OFFICIAL_CALENDARS:
        out = official_calendar_freshness(last, now.date(), calendar)
        out["age_days"] = age
        return out
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
                    holidays: Optional[List[str]] = None, now: Optional[datetime] = None, lag_days: int = 0,
                    calendar: Optional[str] = None) -> dict:
    holidays = holidays or []
    if not series:
        return {"name": name, "total_points": 0, "valid_points": 0, "outliers": 0, "last_valid_date": None,
                "freshness": "unavailable", "age_days": None,
                "confidence": {"score": 0, "tier": "CRITICAL", "penalties": [{"type": "empty", "penalty": 100}]}}
    checked = modified_z(series, z_thresh)
    valid = [p for p in checked if p["value"] is not None]
    last_valid = valid[-1]["date"] if valid else None
    fr = freshness(last_valid, frequency, cfg, now, lag_days, calendar=calendar)
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
    out = {"name": name, "total_points": len(checked), "valid_points": len(valid),
            "outliers": sum(1 for p in checked if p["outlier"]), "last_valid_date": last_valid,
            "latest_outlier": bool(valid and valid[-1]["outlier"]), "latest_mz": valid[-1]["mz"] if valid else None,
            "freshness": fr["status"], "age_days": fr["age_days"],
            "confidence": {"score": score, "tier": tier, "penalties": pen}}
    for k in ("next_publication", "calendar", "calendar_url", "calendar_label"):
        if fr.get(k):
            out[k] = fr[k]
    return out


def system_summary(per_series: Dict[str, dict]) -> dict:
    scores = [v["confidence"]["score"] for v in per_series.values()]
    if not scores:
        return {"average": 0, "abv90": 0, "blw70": 0, "lowest": None}
    lowest = min(per_series.items(), key=lambda kv: kv[1]["confidence"]["score"])
    return {"average": round(sum(scores) / len(scores)), "abv90": sum(1 for s in scores if s >= 90),
            "blw70": sum(1 for s in scores if s < 70), "lowest": {"series": lowest[0], "score": lowest[1]["confidence"]["score"]}}
