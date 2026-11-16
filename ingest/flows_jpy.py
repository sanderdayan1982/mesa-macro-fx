"""FAMILIAS-01 Fase 2 module M2 — D3 FLOWS, weekly Japan (shadow).

Signed rule, applied once: flow_jpy = col14 + col17 − col3 − col6 on the MoF
International Transactions in Securities week.csv (Shift-JIS, 100 million yen,
Sun–Sat). States are computed only for flow_jpy, from the percentile of the
4-week sum inside a 52-publication window, with 2-publication hysteresis.
They read the first vintage value, so a later MoF revision does not repaint.

VOTE is 0 and this module is not a blocked_entry. It does not write fiscal.json
and it does not change MofItsProvider.parse (that path still feeds
foreign_jgb_flow_weekly).

CHF sight deposits are read only when history/chf already holds the weekly SNB
series. USD custody is FRED WMTSECL1, the seventh H.4.1 series on the same
fredgraph.csv download as WALCL and the other five: value, sum4, z52 only.
EUR, GBP, AUD, NZD and CAD are always NA.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

# Signed table. These are the thresholds; they are not searched.
ENTRADA_ENTRY = 80
ENTRADA_EXIT = 70
SALIDA_ENTRY = 20
SALIDA_EXIT = 30
WINDOW = 52
HYSTERESIS_PUBS = 2
PROV_MIN = 26
VOTE = 0
BLOCKED_ENTRY = False

STATE_ENTRADA = "ENTRADA"
STATE_SALIDA = "SALIDA"
STATE_NEUTRO = "NEUTRO"
STATE_UNAVAILABLE = "UNAVAILABLE"
STATE_STALE = "STALE"
STATE_DEGRADED = "DATA_DEGRADED"

# (name, column index, R11 sign). The sign is applied once, here.
SERIES_SPEC: Tuple[Tuple[str, int, int], ...] = (
    ("its_resident_foreign_equity_weekly", 3, -1),
    ("its_resident_foreign_bonds_weekly", 6, -1),
    ("its_nonres_jp_equity_weekly", 14, 1),
    ("its_foreign_jgb_weekly", 17, 1),
)
SERIES_NAMES: Tuple[str, ...] = tuple(n for n, _, _ in SERIES_SPEC)
FLOW_NAME = "flow_jpy"
VINTAGE_SERIES: Tuple[str, ...] = SERIES_NAMES + (FLOW_NAME,)

# Already captured weekly SNB sight deposits (history/chf). Informative only.
CHF_WEEKLY_FILES = {
    "sight_deposits_total_weekly": "snbgwdchfsgw:TG.csv",
    "sight_deposits_domestic_weekly": "snbgwdchfsgw:GI.csv",
    "other_sight_deposits_weekly": "snbgwdchfsgw:UEB.csv",
}
# Read only if one of these files is already on disk from the H.4.1 download.
# Mesa stores six FRED series (WALCL, TREAST, WSHOMCB, WLCFLPCL, WTREGEN, WRESBAL),
# not the full H.4.1 release, so WMTSECL1 is not among them and is not fetched.
USD_CUSTODY_FILES = ("WMTSECL1.csv", "WSHOICL.csv", "WSEFINTL.csv", "WSEFDIN.csv")
USD_ABSENT_REASON = (
    "Securities held in custody for foreign official and international accounts "
    "(H.4.1 line, FRED WMTSECL1) is not in the H.4.1 download Mesa already stores "
    "(WALCL, TREAST, WSHOMCB, WLCFLPCL, WTREGEN, WRESBAL). "
    "That download is one FRED csv per series, not the full H.4.1 release. No new source added."
)
# Signed release, then this many Mon–Fri days that are not Japanese national holidays.
STALE_TOLERANCE_BUSINESS_DAYS = 2

NA_CURRENCIES = ("EUR", "GBP", "AUD", "NZD", "CAD")

METHOD_FLOWS = (
    "Fable [PROV] uncalibrated (R12), kept until the GATE act. "
    "States on flow_jpy only, from pct52 of sum4 over 52 publications, "
    "2 consecutive publications to enter and to exit, first vintage value (no repaint). "
    "VOTE=0 shadow; not in blocked_entry."
)
METHOD_RELEASE = (
    "Signed rule: Thursday after the Saturday week-end, or Friday when that Thursday is a "
    "Japanese national holiday. No release-date table. The week that is due is the latest "
    "one whose signed release is on or before today. STALE on the next calendar day if "
    "that row is missing, unless a national holiday falls on Mon–Wed before that Thursday: "
    "then the tolerance is 2 business days (Mon–Fri, national holidays excluded) and the "
    "state is not classified until that tolerance has passed."
)
SOURCE_LINE = "Source: Ministry of Finance Japan, International Transactions in Securities"
SOURCE_URL = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv"

_WAVE = re.compile(r"[\u301c\uff5e~]")
_PERIOD = re.compile(
    r"^(\d{4})\.(\d{1,2})\.(\d{1,2})[\u301c\uff5e~](?:(\d{4})\.)?(\d{1,2})\.(\d{1,2})$"
)
_HOLIDAY_CACHE: Dict[int, set] = {}


class FlowsDataDegraded(Exception):
    """The week.csv does not parse or its column layout moved. Never remap."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _nth_monday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(0 - d.weekday()) % 7)
    return d + timedelta(days=7 * (n - 1))


def _equinox_day(year: int, month: int) -> int:
    """NAOJ-equivalent day-of-month for 1980–2099 (verified against the Cabinet
    Office syukujitsu list for 2025, 2026 and 2027 on 2026-11-16)."""
    y = year - 1980
    leap = y // 4
    if month == 3:
        return int(math.floor(20.8431 + 0.242194 * y - leap))
    return int(math.floor(23.2488 + 0.242194 * y - leap))


def holidays_in_year(year: int) -> set:
    """Japanese national holidays for `year` (祝日, 振替休日, 国民の休日)."""
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]
    h = set()

    def add(month: int, day: int) -> None:
        h.add(date(year, month, day))

    add(1, 1)
    add(2, 11)
    add(4, 29)
    add(5, 3)
    add(5, 4)
    add(5, 5)
    add(11, 3)
    add(11, 23)
    if year <= 2018:
        add(12, 23)  # Emperor's Birthday (Akihito)
    if year >= 2020:
        add(2, 23)  # Emperor's Birthday (Naruhito)
    if year >= 2016:
        if year == 2020:
            add(8, 10)
        elif year == 2021:
            add(8, 8)
        else:
            add(8, 11)
    h.add(_nth_monday(year, 1, 2))
    if year == 2020:
        add(7, 23)
    elif year == 2021:
        add(7, 22)
    else:
        h.add(_nth_monday(year, 7, 3))
    h.add(_nth_monday(year, 9, 3))
    if year == 2019:
        add(10, 22)
        add(4, 30)
        add(5, 1)
        add(5, 2)
    elif year == 2020:
        add(7, 24)
    elif year == 2021:
        add(7, 23)
    else:
        h.add(_nth_monday(year, 10, 2))
    h.add(date(year, 3, _equinox_day(year, 3)))
    h.add(date(year, 9, _equinox_day(year, 9)))
    extra = set()
    for d in list(h):
        if d.weekday() != 6:
            continue
        nxt = d + timedelta(days=1)
        while nxt in h or nxt in extra:
            nxt += timedelta(days=1)
        extra.add(nxt)
    h |= extra
    changed = True
    while changed:
        changed = False
        for d in list(h):
            mid = d + timedelta(days=1)
            nxt = mid + timedelta(days=1)
            if mid.year == year and mid not in h and nxt in h:
                h.add(mid)
                changed = True
    _HOLIDAY_CACHE[year] = h
    return h


def is_jp_holiday(d: date) -> bool:
    return d in holidays_in_year(d.year)


def release_date(week_end: date) -> date:
    """Thursday after the Saturday week-end, or Friday if that Thursday is a holiday."""
    if week_end.weekday() != 5:
        raise FlowsDataDegraded("week_end %s is not a Saturday (Sun–Sat week)" % week_end.isoformat())
    thu = week_end + timedelta(days=5)
    if is_jp_holiday(thu):
        return thu + timedelta(days=1)
    return thu


def _is_business_day(d: date) -> bool:
    return d.weekday() < 5 and not is_jp_holiday(d)


def add_business_days(start: date, n: int) -> date:
    """The date `n` Japanese business days after `start` (start itself is not counted)."""
    d = start
    left = n
    while left > 0:
        d += timedelta(days=1)
        if _is_business_day(d):
            left -= 1
    return d


def latest_due_week_end(today: date) -> date:
    """Last Sun–Sat week whose signed release date is on or before `today`.

    A combined MoF release (two weeks on one day) is not stale on that day: the
    latest completed week's signed date is today, so the 2-business-day tolerance
    has not started. No per-date table.
    """
    sat = today - timedelta(days=(today.weekday() - 5) % 7)
    if sat == today:
        sat -= timedelta(days=7)
    while release_date(sat) > today:
        sat -= timedelta(days=7)
    return sat


def _holiday_before_thursday(week_end: date, rel: date) -> bool:
    """National holiday on Mon–Wed after week_end and before the signed release.

    A holiday Thursday is already moved to Friday by release_date and is not counted again.
    """
    d = week_end + timedelta(days=1)
    while d < rel:
        if d.weekday() <= 2 and is_jp_holiday(d):
            return True
        d += timedelta(days=1)
    return False


def stale_since(latest_week_end: date, today: date) -> Optional[date]:
    """Signed release once it is overdue, with a 2-business-day tolerance after an earlier holiday.

    The due week is the latest one whose signed Thursday/Friday is on or before today, so a
    combined release is not stale on the later week's signed date. No per-date table.
    Without an earlier Mon–Wed holiday, STALE is the next calendar day (the signed +1 day rule).
    """
    due = latest_due_week_end(today)
    if latest_week_end >= due:
        return None
    rel = release_date(due)
    if _holiday_before_thursday(due, rel):
        overdue = today > add_business_days(rel, STALE_TOLERANCE_BUSINESS_DAYS)
    else:
        overdue = today >= rel + timedelta(days=1)
    if overdue:
        return rel
    return None


def _cell(row: Sequence[str], idx: int) -> str:
    if idx >= len(row):
        return ""
    return row[idx].replace(",", "").replace("\u3000", "").strip()


def _number(cell: str, where: str) -> Optional[float]:
    if cell == "" or cell in ("-", "\u2212", "\uff0d"):
        return None
    try:
        v = float(cell)
    except ValueError:
        raise FlowsDataDegraded("DATA_DEGRADED: %s is not a number or a blank (%r)" % (where, cell))
    if not math.isfinite(v):
        raise FlowsDataDegraded("DATA_DEGRADED: %s is not finite" % where)
    return v


def _period_end(cell: str) -> Optional[date]:
    s = cell.strip().replace("\uff0e", ".").replace(" ", "").replace("\u3000", "")
    if not s:
        return None
    looks = bool(re.search(r"\d", s) and _WAVE.search(s))
    m = _PERIOD.match(s)
    if looks and not m:
        raise FlowsDataDegraded("DATA_DEGRADED: period %r does not match the week format" % cell.strip())
    if not m:
        return None
    y1, m1, _d1, y2, m2, d2 = m.groups()
    year = int(y2) if y2 else (int(y1) + 1 if int(m2) < int(m1) else int(y1))
    try:
        return date(year, int(m2), int(d2))
    except ValueError:
        raise FlowsDataDegraded("DATA_DEGRADED: period %r is not a date" % cell.strip())


def _header_ok(rows: List[List[str]]) -> bool:
    for row in rows:
        if len(row) < 18:
            continue
        cells = [c.strip() for c in row]
        if (cells[1] == "Acquisition" and cells[3] == "Net" and cells[6] == "Net"
                and cells[14] == "Net" and cells[17] == "Net"):
            return True
    return False


def _decode_its(blob: bytes) -> str:
    """UTF-8 fixtures decode as UTF-8. The MoF snapshot is Shift-JIS (cp932).

    A strict UTF-8 decode that still shows the English Net header is a fixture.
    Anything else is the Shift-JIS file. A failure of both is DATA_DEGRADED.
    """
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and "Acquisition" in text and "Net" in text:
        return text
    try:
        return blob.decode("cp932")
    except UnicodeDecodeError:
        raise FlowsDataDegraded("DATA_DEGRADED: week.csv is neither UTF-8 nor Shift-JIS")


def parse_its_week(text: str) -> List[dict]:
    """Parse week.csv text into signed weekly rows.

    Raises FlowsDataDegraded when the Net columns are not at 3, 6, 14 and 17,
    a period cannot be read, or a Net cell is neither a number nor blank. An
    empty cell or '-' is None and is not filled.
    """
    rows = list(csv.reader(text.splitlines()))
    if not rows or not _header_ok(rows):
        raise FlowsDataDegraded(
            "DATA_DEGRADED: Net columns are not at 3, 6, 14, 17 under Acquisition — file not remapped")
    out: List[dict] = []
    seen = set()
    for row in rows:
        if not row:
            continue
        week_end = _period_end(row[0] if row else "")
        if week_end is None:
            continue
        if len(row) < 18:
            raise FlowsDataDegraded(
                "DATA_DEGRADED: week %s has %d columns, expected at least 18 — not remapped"
                % (week_end.isoformat(), len(row)))
        if week_end.weekday() != 5:
            raise FlowsDataDegraded(
                "DATA_DEGRADED: week ending %s is not a Saturday" % week_end.isoformat())
        if week_end in seen:
            raise FlowsDataDegraded("DATA_DEGRADED: duplicate week %s" % week_end.isoformat())
        seen.add(week_end)
        raw: Dict[int, Optional[float]] = {}
        signed: Dict[str, Optional[float]] = {}
        for name, col, sign in SERIES_SPEC:
            num = _number(_cell(row, col), "%s col %d" % (week_end.isoformat(), col))
            raw[col] = num
            signed[name] = None if num is None else num * sign
        out.append({"week_end": week_end, "raw": raw, "signed": signed})
    out.sort(key=lambda r: r["week_end"])
    if not out:
        raise FlowsDataDegraded("DATA_DEGRADED: week.csv has a header and no week rows")
    return out


def flow_from_signed(signed: Dict[str, Optional[float]]) -> Optional[float]:
    """col14 + col17 − col3 − col6, with the R11 sign applied once.

    None when any of the four series is missing. A missing leg is not treated as zero.
    """
    parts = []
    for name, _col, _sign in SERIES_SPEC:
        v = signed.get(name)
        if v is None:
            return None
        parts.append(v)
    # parts are already signed: (−col3) + (−col6) + col14 + col17
    return parts[0] + parts[1] + parts[2] + parts[3]


def missing_names(signed: Dict[str, Optional[float]]) -> List[str]:
    return [name for name, _c, _s in SERIES_SPEC if signed.get(name) is None]


def _window(values: Sequence[Optional[float]], i: int) -> List[Optional[float]]:
    lo = max(0, i - WINDOW + 1)
    return list(values[lo:i + 1])


def n_valid(values: Sequence[Optional[float]], i: int) -> int:
    return sum(1 for v in _window(values, i) if v is not None)


def sum4_at(values: Sequence[Optional[float]], dates: Sequence[date], i: int) -> Optional[float]:
    """Sum of four present weeks. A hole in the four, or a break in the Saturday grid, is null."""
    if i < 3:
        return None
    for k in range(i - 3, i):
        if (dates[k + 1] - dates[k]).days != 7 or values[k] is None:
            return None
    if values[i] is None:
        return None
    return values[i - 3] + values[i - 2] + values[i - 1] + values[i]


def z52_at(values: Sequence[Optional[float]], i: int) -> Optional[float]:
    """Z of the current point against the other valid points in the 52-row window.

    The current point is excluded (no lookahead). Fewer than two prior points → null.
    """
    cur = values[i]
    if cur is None:
        return None
    prior = [v for v in _window(values, i)[:-1] if v is not None]
    if len(prior) < 2:
        return None
    mean = sum(prior) / len(prior)
    var = sum((x - mean) ** 2 for x in prior) / len(prior)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return round((cur - mean) / sd, 4)


def pct52_at(values: Sequence[Optional[float]], i: int) -> Optional[float]:
    """Percentile rank of values[i] inside the 52-row window, current included.

    Null weeks are excluded from the sample and are not filled. 100 * (count <= current) / n.
    """
    cur = values[i]
    if cur is None:
        return None
    sample = [v for v in _window(values, i) if v is not None]
    if not sample:
        return None
    n = sum(1 for x in sample if x <= cur)
    return round(100.0 * n / len(sample), 2)


def _fresh_memory() -> dict:
    return {"confirmed": STATE_NEUTRO, "pending": None, "pending_n": 0}


def step_state(memory: dict, pct: Optional[float], unavailable: bool) -> Tuple[dict, str]:
    """One publication. Two consecutive prints to enter and to exit. UNAVAILABLE resets."""
    if unavailable or pct is None:
        return _fresh_memory(), STATE_UNAVAILABLE
    confirmed = memory["confirmed"]
    pending = memory["pending"]
    pending_n = memory["pending_n"]
    if confirmed == STATE_NEUTRO:
        if pct >= ENTRADA_ENTRY:
            want = STATE_ENTRADA
        elif pct <= SALIDA_ENTRY:
            want = STATE_SALIDA
        else:
            want = None
        if want is None:
            return _fresh_memory(), STATE_NEUTRO
        n = pending_n + 1 if pending == want else 1
        if n >= HYSTERESIS_PUBS:
            return {"confirmed": want, "pending": None, "pending_n": 0}, want
        return {"confirmed": STATE_NEUTRO, "pending": want, "pending_n": n}, STATE_NEUTRO
    if confirmed == STATE_ENTRADA:
        if pct < ENTRADA_EXIT:
            n = pending_n + 1 if pending == "EXIT" else 1
            if n >= HYSTERESIS_PUBS:
                return _fresh_memory(), STATE_NEUTRO
            return {"confirmed": STATE_ENTRADA, "pending": "EXIT", "pending_n": n}, STATE_ENTRADA
        return {"confirmed": STATE_ENTRADA, "pending": None, "pending_n": 0}, STATE_ENTRADA
    if pct > SALIDA_EXIT:
        n = pending_n + 1 if pending == "EXIT" else 1
        if n >= HYSTERESIS_PUBS:
            return _fresh_memory(), STATE_NEUTRO
        return {"confirmed": STATE_SALIDA, "pending": "EXIT", "pending_n": n}, STATE_SALIDA
    return {"confirmed": STATE_SALIDA, "pending": None, "pending_n": 0}, STATE_SALIDA


def fold_states(pcts: Sequence[Optional[float]], n: int = WINDOW) -> List[str]:
    """Hysteresis over an explicit percentile path. None, or n < 26, is UNAVAILABLE and resets."""
    memory = _fresh_memory()
    out: List[str] = []
    for pct in pcts:
        unavailable = pct is None or n < PROV_MIN
        memory, state = step_state(memory, pct, unavailable)
        out.append(state)
    return out


def _series_paths(values: Sequence[Optional[float]], dates: Sequence[date]) -> dict:
    sums: List[Optional[float]] = []
    zs: List[Optional[float]] = []
    pcts: List[Optional[float]] = []
    for i in range(len(values)):
        sums.append(sum4_at(values, dates, i))
        zs.append(z52_at(values, i))
    for i in range(len(values)):
        pcts.append(pct52_at(sums, i))
    return {"sum4": sums, "z52": zs, "pct52_sum4": pcts}


def replay(weeks: Sequence[dict]) -> List[dict]:
    """Replay states from signed component values (already the first-vintage values).

    `weeks` is a list of {"week_end": date, "signed": {name: float|None}} sorted by week_end.
    """
    dates = [w["week_end"] for w in weeks]
    signed_cols = {name: [w["signed"].get(name) for w in weeks] for name in SERIES_NAMES}
    flows: List[Optional[float]] = [flow_from_signed(w["signed"]) for w in weeks]
    flow_stats = _series_paths(flows, dates)
    comp_stats = {name: _series_paths(signed_cols[name], dates) for name in SERIES_NAMES}
    memory = _fresh_memory()
    out: List[dict] = []
    for i, w in enumerate(weeks):
        value = flows[i]
        n = n_valid(flows, i)
        sum4 = flow_stats["sum4"][i]
        pct = flow_stats["pct52_sum4"][i]
        z = flow_stats["z52"][i]
        missed = missing_names(w["signed"])
        if value is None:
            reason = "missing series: %s" % ", ".join(missed)
            unavailable = True
        elif sum4 is None or pct is None:
            reason = "sum4 null (gap)"
            unavailable = True
        elif n < PROV_MIN:
            reason = "n=%d<%d" % (n, PROV_MIN)
            unavailable = True
        else:
            reason = None
            unavailable = False
        memory, state = step_state(memory, pct, unavailable)
        prov = (not unavailable) and PROV_MIN <= n < WINDOW
        if prov:
            reason = "[PROV] n=%d" % n
        rel = release_date(w["week_end"]).isoformat()
        series = {}
        for name in SERIES_NAMES:
            sv = signed_cols[name][i]
            series[name] = {
                "value": sv,
                "sum4": comp_stats[name]["sum4"][i],
                "z52": comp_stats[name]["z52"][i],
                "pct52_sum4": comp_stats[name]["pct52_sum4"][i],
                "week_end": w["week_end"].isoformat(),
                "release_date": rel,
                "state": None,
                "flows_prov": False,
                "flows_reason": None if sv is not None else "missing",
            }
        out.append({
            "week_end": w["week_end"].isoformat(),
            "release_date": rel,
            "series": series,
            "flow_jpy": {
                "value": value,
                "sum4": sum4,
                "z52": z,
                "pct52_sum4": pct,
                "week_end": w["week_end"].isoformat(),
                "release_date": rel,
                "state": state,
                "flows_prov": prov,
                "flows_reason": reason,
                "n": n,
            },
        })
    return out


def _fmt_value(v: Optional[float]) -> str:
    if v is None:
        return ""
    fv = float(v)
    if fv.is_integer():
        return str(int(fv))
    return repr(fv)


def _read_vintage(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if not row or not row.get("week"):
                continue
            raw = (row.get("value") or "").strip()
            out.append({
                "week": row["week"],
                "series": row["series"],
                "value": None if raw == "" else float(raw),
                "first_seen": row.get("first_seen") or "",
                "rev": int(row["rev"]) if row.get("rev") not in (None, "") else 0,
            })
    return out


def _first_map(rows: Sequence[dict]) -> Dict[Tuple[str, str], Optional[float]]:
    best: Dict[Tuple[str, str], Tuple[Tuple[str, int], Optional[float]]] = {}
    for row in rows:
        key = (row["week"], row["series"])
        rank = (row["first_seen"], row["rev"])
        if key not in best or rank < best[key][0]:
            best[key] = (rank, row["value"])
    return {k: v for k, (_rank, v) in best.items()}


def _latest_map(rows: Sequence[dict]) -> Dict[Tuple[str, str], dict]:
    latest: Dict[Tuple[str, str], dict] = {}
    for row in rows:
        latest[(row["week"], row["series"])] = row
    return latest


def update_vintage(path: str, weeks: Sequence[dict], first_seen: str) -> List[dict]:
    """Append-only. A changed past week adds a row with rev incremented (first change is rev=1).

    Returns the rows appended on this call. Existing rows are not rewritten.
    """
    existing = _read_vintage(path)
    latest = _latest_map(existing)
    new_rows: List[dict] = []
    for w in weeks:
        week = w["week_end"].isoformat()
        signed = w["signed"]
        flow = flow_from_signed(signed)
        values = {name: signed.get(name) for name in SERIES_NAMES}
        values[FLOW_NAME] = flow
        for series in VINTAGE_SERIES:
            value = values[series]
            prev = latest.get((week, series))
            if prev is None:
                if value is None:
                    continue
                rev = 0
            else:
                if prev["value"] == value or (prev["value"] is not None and value is not None and float(prev["value"]) == float(value)):
                    continue
                rev = prev["rev"] + 1
            row = {"week": week, "series": series, "value": value, "first_seen": first_seen, "rev": rev}
            new_rows.append(row)
            latest[(week, series)] = row
    if not new_rows:
        return []
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new_file = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["week", "series", "value", "first_seen", "rev"])
        for row in new_rows:
            writer.writerow([row["week"], row["series"], _fmt_value(row["value"]), row["first_seen"], row["rev"]])
    return new_rows


def _weeks_from_first(parsed: Sequence[dict], first: Dict[Tuple[str, str], Optional[float]]) -> List[dict]:
    """Spine is the union of the file and the vintage, so a dropped week does not shift the window."""
    by_end = {w["week_end"].isoformat(): w for w in parsed}
    ends = set(by_end) | {week for (week, _series) in first}
    out = []
    for end in sorted(ends):
        signed = {}
        current = (by_end.get(end) or {}).get("signed") or {}
        for name in SERIES_NAMES:
            key = (end, name)
            if key in first:
                signed[name] = first[key]
            else:
                signed[name] = current.get(name)
        out.append({"week_end": date.fromisoformat(end), "signed": signed})
    return out


def _read_weekly_csv(path: str) -> List[Tuple[date, float]]:
    pts = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 2 or row[0] == "date" or row[1] in ("", "None"):
                continue
            try:
                pts.append((date.fromisoformat(row[0]), float(row[1])))
            except ValueError:
                continue
    pts.sort(key=lambda p: p[0])
    return pts


def _informative(pts: List[Tuple[date, float]]) -> dict:
    """value, sum4, z52. No state. sum4 is null when the last four dates are not 7 days apart."""
    if not pts:
        return {"value": None, "sum4": None, "z52": None}
    values = [v for _d, v in pts]
    dates = [d for d, _v in pts]
    i = len(values) - 1
    return {"value": values[i], "sum4": sum4_at(values, dates, i), "z52": z52_at(values, i)}


def _chf_block(chf_dir: str) -> Optional[dict]:
    if not chf_dir or not os.path.isdir(chf_dir):
        return None
    block = {}
    for name, fn in CHF_WEEKLY_FILES.items():
        path = os.path.join(chf_dir, fn)
        if not os.path.exists(path):
            continue
        pts = _read_weekly_csv(path)
        if not pts:
            continue
        block[name] = _informative(pts)
    return block or None


def _usd_block(usd_dir: str) -> Optional[dict]:
    """Custody only when the series is already in the H.4.1 download. Never fetches."""
    if not usd_dir or not os.path.isdir(usd_dir):
        return None
    for fn in USD_CUSTODY_FILES:
        path = os.path.join(usd_dir, fn)
        if os.path.exists(path):
            pts = _read_weekly_csv(path)
            if pts:
                return {os.path.splitext(fn)[0]: _informative(pts)}
    return None


def _blank_flow(state: str, reason: str) -> dict:
    return {
        "value": None, "sum4": None, "z52": None, "pct52_sum4": None,
        "week_end": None, "release_date": None, "state": state,
        "flows_prov": False, "flows_reason": reason, "n": 0,
    }


def _degraded_document(reason: str, today: date, generated_at: str, chf, usd) -> dict:
    currencies = {ccy: None for ccy in NA_CURRENCIES}
    currencies["CHF"] = chf
    currencies["USD"] = usd
    currencies["JPY"] = {"flow_jpy": _blank_flow(STATE_DEGRADED, reason)}
    for name in SERIES_NAMES:
        currencies["JPY"][name] = {
            "value": None, "sum4": None, "z52": None, "pct52_sum4": None,
            "week_end": None, "release_date": None, "state": None,
            "flows_prov": False, "flows_reason": reason,
        }
    return _document(currencies, today, generated_at, status=STATE_DEGRADED)


def _document(currencies: dict, today: date, generated_at: str, status: str = "ok") -> dict:
    return {
        "schema": "mesa.flows_weekly.m2",
        "shadow": True,
        "vote": VOTE,
        "blocked_entry": BLOCKED_ENTRY,
        "status": status,
        "as_of": today.isoformat(),
        "generated_at": generated_at,
        "unit": "JPY 100 million (MoF ITS week.csv); CHF in the source unit already stored",
        "source": SOURCE_LINE,
        "licence": "PDL 1.0",
        "source_url": SOURCE_URL,
        "method": {"flows": METHOD_FLOWS, "release": METHOD_RELEASE},
        "thresholds": {
            "entrada_entry": ENTRADA_ENTRY,
            "entrada_exit": ENTRADA_EXIT,
            "salida_entry": SALIDA_ENTRY,
            "salida_exit": SALIDA_EXIT,
            "window": WINDOW,
            "hysteresis_publications": HYSTERESIS_PUBS,
            "prov_min": PROV_MIN,
        },
        "coverage": {
            "JPY": "MoF ITS week.csv (logs/jpy/raw/its_week.csv)",
            "CHF": "SNB sight deposits already in history/chf (snbgwdchfsgw TG, GI, UEB); value, sum4, z52 only",
            "USD": (
                {"value": None, "reason": USD_ABSENT_REASON}
                if currencies.get("USD") is None
                else "H.4.1 custody already in the download; value, sum4, z52 only, no state"
            ),
            "EUR": "NA", "GBP": "NA", "AUD": "NA", "NZD": "NA", "CAD": "NA",
        },
        "reason": None if currencies.get("USD") is not None else {"USD": USD_ABSENT_REASON},
        "currencies": currencies,
    }


def _apply_stale(flow: dict, today: date) -> dict:
    if not flow.get("week_end"):
        return flow
    rel = stale_since(date.fromisoformat(flow["week_end"]), today)
    if rel is None:
        return flow
    out = dict(flow)
    # Do not classify. The last print's value, sum4, z and pct stay; the state does not.
    out["state"] = STATE_STALE
    out["flows_prov"] = False
    out["flows_reason"] = "STALE signed release %s without a new row" % rel.isoformat()
    return out


def build_document(parsed: Sequence[dict], vintage_rows: Sequence[dict], today: date, generated_at: str,
                   chf: Optional[dict], usd: Optional[dict]) -> Tuple[dict, List[dict]]:
    first = _first_map(vintage_rows)
    spine = _weeks_from_first(parsed, first)
    history = replay(spine)
    if not history:
        raise FlowsDataDegraded("DATA_DEGRADED: no weeks to classify")
    last = history[-1]
    flow = _apply_stale(last["flow_jpy"], today)
    jpy = {"flow_jpy": flow}
    jpy.update(last["series"])
    currencies = {ccy: None for ccy in NA_CURRENCIES}
    currencies["CHF"] = chf
    currencies["USD"] = usd
    currencies["JPY"] = jpy
    return _document(currencies, today, generated_at), history


def publish(root: str, today: Optional[date] = None, now: Optional[str] = None,
            csv_path: Optional[str] = None, vintage_path: Optional[str] = None,
            out_path: Optional[str] = None, chf_dir: Optional[str] = None,
            usd_dir: Optional[str] = None) -> dict:
    """Write data/mesa/FLOWS_weekly.json and append history/mesa/its_vintage.csv.

    Does not open, write or delete fiscal.json. `today` drives STALE; `now` is the
    vintage first_seen stamp (so a test can replay a revision on a later stamp).
    """
    today = today or date.today()
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    csv_path = csv_path or os.path.join(root, "logs", "jpy", "raw", "its_week.csv")
    vintage_path = vintage_path or os.path.join(root, "history", "mesa", "its_vintage.csv")
    out_path = out_path or os.path.join(root, "data", "mesa", "FLOWS_weekly.json")
    chf_dir = chf_dir if chf_dir is not None else os.path.join(root, "history", "chf")
    usd_dir = usd_dir if usd_dir is not None else os.path.join(root, "history", "usd")
    chf = _chf_block(chf_dir)
    usd = _usd_block(usd_dir)
    try:
        if not os.path.exists(csv_path):
            raise FlowsDataDegraded("DATA_DEGRADED: its_week.csv is not in the repo (%s)" % csv_path)
        text = _decode_its(open(csv_path, "rb").read())
        parsed = parse_its_week(text)
        update_vintage(vintage_path, parsed, now)
        vintage_rows = _read_vintage(vintage_path)
        doc, _history = build_document(parsed, vintage_rows, today, now, chf, usd)
    except FlowsDataDegraded as e:
        doc = _degraded_document(str(e.reason), today, now, chf, usd)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    return doc


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    doc = publish(root)
    flow = ((doc.get("currencies") or {}).get("JPY") or {}).get("flow_jpy") or {}
    print("FLOWS_weekly status=%s state=%s week_end=%s vote=%s" % (
        doc.get("status"), flow.get("state"), flow.get("week_end"), doc.get("vote")))
    return 0 if doc.get("status") != STATE_DEGRADED else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
