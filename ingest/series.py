"""Series helpers — pure Python, 3.9-compatible. A series is a list of (date_str, float|None) sorted by date.
Ported from Canada Command Center v2.0 derive.mjs (pct_series, merge_series, change_series) + Desk Standard
additions (rolling z-score without lookahead, rolling percentile rank, rolling sums)."""
from __future__ import annotations
import math
from typing import List, Tuple, Optional, Callable, Dict

Point = Tuple[str, Optional[float]]
Series = List[Point]


def clean(s: Series) -> Series:
    """Drop None values, dedup by date (last wins), sort ascending."""
    m: Dict[str, float] = {}
    for d, v in s:
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(fv):
            m[d] = fv
    return sorted(m.items())


def last(s: Series, n: int = 0) -> Optional[Point]:
    return s[-1 - n] if len(s) > n else None


def values(s: Series) -> List[float]:
    return [v for _, v in s if v is not None]


def pct_change_series(s: Series, n: int = 1) -> Series:
    out: Series = []
    for i in range(n, len(s)):
        a, b = s[i][1], s[i - n][1]
        if a is None or b is None or b == 0:
            continue
        out.append((s[i][0], round((a - b) / abs(b) * 100.0, 4)))
    return out


def diff_series(s: Series, n: int = 1, mult: float = 1.0) -> Series:
    out: Series = []
    for i in range(n, len(s)):
        a, b = s[i][1], s[i - n][1]
        if a is None or b is None:
            continue
        out.append((s[i][0], round((a - b) * mult, 4)))
    return out


def merge_series(a: Series, b: Series, fn: Callable[[float, float], float]) -> Series:
    """Common-date rule (H.15 v2.1 / derive.mjs): only dates present in both series."""
    mb = {d: v for d, v in b if v is not None}
    out: Series = []
    for d, v in a:
        if v is None or d not in mb:
            continue
        r = fn(v, mb[d])
        if r is not None and math.isfinite(r):
            out.append((d, round(r, 4)))
    return out


def add_series(a: Series, b: Series) -> Series:
    return merge_series(a, b, lambda x, y: x + y)


def rolling_sum(s: Series, n: int) -> Series:
    out: Series = []
    vals = [v for _, v in s]
    for i in range(n - 1, len(s)):
        win = vals[i - n + 1:i + 1]
        if any(v is None for v in win):
            continue
        out.append((s[i][0], round(sum(win), 4)))
    return out


def rolling_zscore(s: Series, window: int, min_points: int = 10, lookahead: bool = False) -> Series:
    """Z of point i against the previous `window` points (excluding i unless lookahead=True).
    Inherited rule from H.8 v2.1: no lookahead."""
    out: Series = []
    vals = [v for _, v in s]
    for i in range(len(s)):
        hi = i + 1 if lookahead else i
        win = [v for v in vals[max(0, hi - window):hi] if v is not None]
        if len(win) < min_points or vals[i] is None:
            out.append((s[i][0], None))
            continue
        m = sum(win) / len(win)
        sd = math.sqrt(sum((x - m) ** 2 for x in win) / len(win))
        out.append((s[i][0], 0.0 if sd == 0 else round((vals[i] - m) / sd, 4)))
    return out


def percentile_rank(value: float, sample: List[float]) -> Optional[float]:
    """Rank of value within sample, 0-100 (share of sample <= value)."""
    if not sample:
        return None
    n = sum(1 for x in sample if x <= value)
    return round(100.0 * n / len(sample), 2)


def percentile_value(sample: List[float], p: float) -> Optional[float]:
    """Value at percentile p (0-100), linear interpolation."""
    if not sample:
        return None
    xs = sorted(sample)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p / 100.0
    f = math.floor(k)
    c = min(f + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 6)


def window_sample(s: Series, window: int) -> List[float]:
    """Last `window` non-null values, EXCLUDING the latest point (no lookahead for the current reading)."""
    v = [x for _, x in s if x is not None]
    return v[-window - 1:-1] if len(v) > 1 else []


def rolling_stats(s: Series, window: int) -> Dict[str, Optional[float]]:
    v = [x for _, x in s if x is not None][-window:]
    if len(v) < 2:
        return {"mean": None, "sd": None, "n": len(v)}
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / len(v))
    return {"mean": round(m, 4), "sd": round(sd, 4), "n": len(v)}


def high_low(s: Series, window: int) -> Dict[str, Optional[object]]:
    pts = [(d, v) for d, v in s if v is not None][-window:]
    if not pts:
        return {"high": None, "high_date": None, "low": None, "low_date": None}
    hi = max(pts, key=lambda p: p[1])
    lo = min(pts, key=lambda p: p[1])
    return {"high": hi[1], "high_date": hi[0], "low": lo[1], "low_date": lo[0]}


def tail(s: Series, n: int) -> Series:
    return s[-n:]


def parse_window(w: str, freq: str) -> int:
    """'156w' -> 156 obs for weekly; '750d' -> 750 obs for daily; '26m' -> 26; if unit mismatches freq, convert."""
    num = int("".join(ch for ch in w if ch.isdigit()))
    unit = w[-1]
    conv = {("w", "daily"): 5, ("d", "weekly"): 1 / 5, ("m", "weekly"): 4.33, ("w", "monthly"): 1 / 4.33, ("d", "monthly"): 1 / 21, ("m", "daily"): 21}
    return max(5, int(round(num * conv.get((unit, freq), 1))))
