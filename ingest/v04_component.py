"""Engine v0.4 component print — the live counterpart of replay_v04 (activation lot, 2026-09-11).

A v0.4 block reads ONE settlement/flow component instead of the v0.3 block score:
  daily5   = sum of the 5 sessions ending at the print (history/<ccy>/<file>.csv, publication-lag aware)
  weekly   = latest weekly value ≤ today − lag (step; stale after 10 days, as in the replay)
  dweekly  = −(value − prev_value) of the government-account entry of the central_bank block (identity: the account fills → drain)
The print is the component in % of the reserves stock (the same denominator calibrate.py writes to scores.csv), rounded to 4.
`read_hist` and `value_asof` are verbatim copies of replay_v04._load_hist / _value_asof so the live print and the replay stay
identical (tests_v04 --ccy activation checks the parity); this module imports no numpy/scipy so the engine stays light."""
from __future__ import annotations
import bisect
import csv
import os
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

Series = List[Tuple[str, float]]


def _f(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "None") else None
    except ValueError:
        return None


def read_hist(path: str) -> Series:
    """history CSV (date,value) → sorted series; a leading run of exact zeros is 'no data', not 'no flow' (= replay_v04._load_hist)"""
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for r in csv.reader(f):
            if r and r[0] != "date" and _f(r[1]) is not None:
                out.append((r[0], float(r[1])))
    out = sorted(out)
    k = 0
    while k < len(out) and out[k][1] == 0.0:
        k += 1
    return out[k:] if k < len(out) else out


def value_asof(ser: Series, d: str, kind: str, lag: int) -> Optional[float]:
    """as-of evaluation: only points whose date ≤ d − lag are known at d (= replay_v04._value_asof)"""
    if not ser:
        return None
    cutoff = (date.fromisoformat(d) - timedelta(days=lag)).isoformat()
    ds = [x for x, _ in ser]
    i = bisect.bisect_right(ds, cutoff)
    if i == 0:
        return None
    if kind == "daily5":
        pts = ser[max(0, i - 5):i]
        first = date.fromisoformat(pts[0][0])
        if len(pts) < 5 or (date.fromisoformat(cutoff) - first).days > 12:
            return None
        return float(sum(v for _, v in pts))
    if kind == "weekly":
        d0, v = ser[i - 1]
        return v if (date.fromisoformat(cutoff) - date.fromisoformat(d0)).days <= 10 else None
    return None


def _last_date_asof(ser: Series, d: str, lag: int) -> Optional[str]:
    """date of the last point known at d (the print's as-of date)"""
    cutoff = (date.fromisoformat(d) - timedelta(days=lag)).isoformat()
    i = bisect.bisect_right([x for x, _ in ser], cutoff)
    return ser[i - 1][0] if i else None


def _entry(blocks: Dict[str, dict], path: str) -> dict:
    blk, key = path.split(".", 1)
    b = blocks.get(blk) or {}
    return (b.get("series", {}).get(key) or b.get("derived", {}).get(key) or {})


def compute_print(comp: dict, blocks: Dict[str, dict], hist_dir: Optional[str], today: Optional[str] = None) -> dict:
    """One v0.4 print. comp = {"name", "source", "kind", "lag", "sign", "denominator"} as apply_v04 writes it into config regime.dual.v04.
    Returns {"score", "as_of", "raw", "denominator", "note"}; score None when the component is not known as of today (never estimated)."""
    kind, lag, sign = comp.get("kind"), int(comp.get("lag") or 0), float(comp.get("sign") or 1)
    today = today or datetime.now(timezone.utc).date().isoformat()
    den_e = _entry(blocks, comp.get("denominator") or "central_bank.reserves")
    den = den_e.get("value")
    out = {"score": None, "as_of": None, "raw": None, "denominator": den, "denominator_date": den_e.get("date"), "today": today, "note": None}
    if not den:
        out["note"] = "denominator %s not published in today's JSON" % comp.get("denominator")
        return out
    if kind == "dweekly":
        g = _entry(blocks, comp.get("source") or "central_bank.government_account")
        v, pv = g.get("value"), g.get("prev_value")
        if v is None or pv is None:
            out["note"] = "government account value/prev_value not published"
            return out
        raw, as_of = -(v - pv) * sign, g.get("date")
    elif kind in ("daily5", "weekly"):
        if not hist_dir:
            out["note"] = "no history dir passed to the engine — v0.4 print skipped"
            return out
        ser = read_hist(os.path.join(hist_dir, "%s.csv" % comp.get("source")))
        v = value_asof(ser, today, kind, lag)
        if v is None:
            last = ser[-1][0] if ser else None
            out["note"] = "%s not known as of %s (lag %d d; last archived point %s)" % (comp.get("source"), today, lag, last)
            return out
        raw, as_of = v * sign, _last_date_asof(ser, today, lag)
    else:
        out["note"] = "unknown component kind %r" % kind
        return out
    out.update({"score": round(raw / den * 100, 4), "as_of": as_of, "raw": round(raw, 4)})
    return out
