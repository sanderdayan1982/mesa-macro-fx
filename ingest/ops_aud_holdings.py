"""AUD v0.4 — RBA holdings of Australian Government Securities by line (statistical table A3.1) and the private-held Treasury Bond calendar.

Source (fixtures/aud_hist/rba_a3.1_ags_bonds.csv, verified 2026-09-10):
  https://www.rba.gov.au/statistics/tables/csv/a3.1-ags---bonds.csv — "A3.1 Holdings of Australian Government Securities and Semis — AGS Bonds".
  Layout: title line; header rows Title / Description / Frequency / Type / Units / (blank) / Source / Publication date / Series ID; then one row per
  month-end ("31-Jan-2017,3301,…") and trailing blank lines.  Description = "Treasury Bond 164 0.50%  21-Sep-2026" → series number, coupon (%),
  maturity.  Values $m face; 0 or empty = no holding.  Columns whose Title is not "Australian Government Bonds" (semis) are parsed and tagged with
  the Title so the caller filters.

Units: AUD millions.  Sign convention as in ops_aud: + = ES balances created, so redemptions and coupons paid to the private sector are positive;
"ahead" series are calendars (positive), not flows.

Netting rule: private face = max(0, AOFM face by line − RBA holding by maturity) at the latest AOFM month-end snapshot, using the latest RBA
snapshot dated <= that AOFM date (else the latest RBA snapshot overall, which is then reported as `tb_holdings_asof`).  The RBA holding is
capped at face so that net + rba = gross line by line.  RBA-held redemptions/coupons are Treasury ↔ RBA (OPA → RBA), no ES-balance effect (A5).

Coupon convention (same as ops_aud.tb_calendar): semi-annual on the maturity day-of-month and six months earlier, amount = face × coupon / 200,
dates <= maturity, within [today − back_days, today + horizon_days].  net_daily_history books a flow dated on a day absent from the replay's day
list (weekend / holiday) on the next listed day, so the dense series lose nothing."""
from __future__ import annotations
import bisect
import csv
import io
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from .series import Series
from .ops_aud import _num, _iso, _bucket, business_days  # noqa: F401  (business_days re-exported for callers)

A31_URL = "https://www.rba.gov.au/statistics/tables/csv/a3.1-ags---bonds.csv"
AGS_TITLE = "Australian Government Bonds"
_DESC = re.compile(r"^\s*(?P<name>.*?)\s+(?P<no>\d+)\s+(?P<cpn>\d+(?:\.\d+)?)\s*%\s+(?P<mat>\d{1,2}-[A-Za-z]{3}-\d{4})\s*$")


# ───────────────────────── A3.1 CSV ─────────────────────────
def parse_description(desc: str) -> Tuple[Optional[int], Optional[float], Optional[str]]:
    """'Treasury Bond 164 0.50%  21-Sep-2026' → (164, 0.5, '2026-09-21'); anything unparseable → (None, None, None) with best-effort pieces"""
    m = _DESC.match(desc or "")
    if m:
        return int(m.group("no")), float(m.group("cpn")), _iso(m.group("mat"))
    no = re.search(r"\b(\d{2,4})\b", desc or "")
    cp = re.search(r"(\d+(?:\.\d+)?)\s*%", desc or "")
    mt = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{4})", desc or "")
    return (int(no.group(1)) if no else None), (float(cp.group(1)) if cp else None), (_iso(mt.group(1)) if mt else None)


def parse_a31_csv(text: str) -> List[dict]:
    """one record per (month-end, column) with holding > 0:
    {date, title, description, series_id, series_no, coupon, maturity, holding ($m), publication_date}"""
    hdr: Dict[str, List[str]] = {}
    out: List[dict] = []
    meta: Optional[List[dict]] = None
    for row in csv.reader(io.StringIO(text)):
        if not row or not str(row[0]).strip():
            continue
        key = str(row[0]).strip()
        d = _iso(key)
        if d is None:
            if key.lower() in ("title", "description", "frequency", "type", "units", "source", "publication date", "series id"):
                hdr[key.lower()] = [str(c).strip() for c in row[1:]]
            continue
        if meta is None:
            ncol = max((len(v) for v in hdr.values()), default=0)
            get = lambda k, i: (hdr.get(k) or [])[i] if i < len(hdr.get(k) or []) else ""
            meta = []
            for i in range(ncol):
                no, cp, mt = parse_description(get("description", i))
                meta.append({"title": get("title", i), "description": get("description", i), "series_id": get("series id", i), "series_no": no,
                             "coupon": cp, "maturity": mt, "publication_date": _iso(get("publication date", i))})
        for i, cell in enumerate(row[1:]):
            if i >= len(meta):
                break
            v = _num(cell)
            if v is None or v <= 0:
                continue
            rec = {"date": d, "holding": v}
            rec.update(meta[i])
            out.append(rec)
    out.sort(key=lambda r: (r["date"], r["maturity"] or "", r["series_id"]))
    return out


def rba_dates(rows: List[dict], title: Optional[str] = AGS_TITLE) -> List[str]:
    return sorted({r["date"] for r in rows if title is None or r.get("title") == title})


def _holdings_at(rows: List[dict], asof: str, title: Optional[str]) -> Dict[str, float]:
    m: Dict[str, float] = defaultdict(float)
    for r in rows:
        if r["date"] == asof and (title is None or r.get("title") == title) and r.get("maturity"):
            m[r["maturity"]] += r["holding"]
    return {k: round(v, 3) for k, v in m.items()}


def rba_by_maturity(rows: List[dict], asof: Optional[str] = None, title: Optional[str] = AGS_TITLE) -> Tuple[str, Dict[str, float]]:
    """(snapshot date used = latest <= asof, or latest overall, {maturity ISO: holding $m}); lines sharing a maturity are summed"""
    ds = rba_dates(rows, title)
    if not ds:
        return "", {}
    if asof:
        i = bisect.bisect_right(ds, asof)
        use = ds[i - 1] if i > 0 else ds[0]
    else:
        use = ds[-1]
    return use, _holdings_at(rows, use, title)


# ───────────────────────── netting ─────────────────────────
def _lines_at(lines: List[dict], asof: str) -> List[dict]:
    return [l for l in lines if l["date"] == asof and l.get("maturity")]


def _net_lines(snap: List[dict], rba: Dict[str, float]) -> Tuple[List[dict], List[str]]:
    """per line: face (gross), rba (capped at face, allocated across lines sharing a maturity in order), net; unmatched RBA maturities"""
    left = dict(rba)
    out = []
    for l in snap:
        f = l.get("face") or 0.0
        h = min(f, max(0.0, left.get(l["maturity"], 0.0)))
        left[l["maturity"]] = left.get(l["maturity"], 0.0) - h
        out.append({"maturity": l["maturity"], "coupon": l.get("coupon") or 0.0, "face": f, "rba": h, "net": max(0.0, f - h)})
    mats = {l["maturity"] for l in snap}
    return out, sorted(m for m in rba if m not in mats)


def _coupon_dates(m: str, start: str, end: str) -> List[str]:
    mo, dd = int(m[5:7]), int(m[8:10])
    out = []
    for yy in range(int(start[:4]), int(end[:4]) + 1):
        for mm in (mo, (mo + 5) % 12 + 1):
            try:
                d = date(yy, mm, dd).isoformat()
            except ValueError:
                continue
            if start <= d <= end and d <= m:
                out.append(d)
    return out


def net_tb_calendar(lines: List[dict], rba_rows: List[dict], horizon_days: int = 365, back_days: int = 90, today: Optional[str] = None,
                    title: Optional[str] = AGS_TITLE) -> Dict[str, Series]:
    """mirror of ops_aud.tb_calendar with the RBA's holdings netted out (private = face − RBA holding by maturity, RBA capped at face)"""
    empty_keys = ["tb_redemptions_net_ahead", "tb_redemptions_gross_ahead", "tb_redemptions_rba_ahead", "tb_coupons_net_paid", "tb_coupons_net_ahead",
                  "tb_coupons_gross_paid", "tb_coupons_gross_ahead", "tb_rba_share", "tb_rba_total", "tb_face_total", "tb_holdings_asof"]
    res: Dict[str, Series] = {k: [] for k in empty_keys}
    res["_unmatched"] = []  # type: ignore[assignment]
    if not lines:
        return res
    aofm_asof = max(l["date"] for l in lines)
    snap = _lines_at(lines, aofm_asof)
    rba_asof, rba = rba_by_maturity(rba_rows, aofm_asof, title)
    net, unmatched = _net_lines(snap, rba)
    tday = today or date.today().isoformat()
    t0 = date.fromisoformat(tday)
    end = (t0 + timedelta(days=horizon_days)).isoformat()
    start = (t0 - timedelta(days=back_days)).isoformat()
    red_n: Dict[str, float] = defaultdict(float)
    red_g: Dict[str, float] = defaultdict(float)
    red_r: Dict[str, float] = defaultdict(float)
    cp_n: Dict[str, float] = defaultdict(float)
    cp_g: Dict[str, float] = defaultdict(float)
    for l in net:
        m = l["maturity"]
        if tday < m <= end:
            red_n[m] += l["net"]
            red_g[m] += l["face"]
            red_r[m] += l["rba"]
        for d in _coupon_dates(m, start, end):
            cp_n[d] += l["net"] * l["coupon"] / 200.0
            cp_g[d] += l["face"] * l["coupon"] / 200.0
    face_tot = sum(l["face"] for l in net)
    rba_tot = sum(l["rba"] for l in net)
    res.update({"tb_redemptions_net_ahead": _bucket(red_n), "tb_redemptions_gross_ahead": _bucket(red_g), "tb_redemptions_rba_ahead": _bucket(red_r),
                "tb_coupons_net_paid": _bucket({d: v for d, v in cp_n.items() if d <= tday}), "tb_coupons_net_ahead": _bucket({d: v for d, v in cp_n.items() if d > tday}),
                "tb_coupons_gross_paid": _bucket({d: v for d, v in cp_g.items() if d <= tday}), "tb_coupons_gross_ahead": _bucket({d: v for d, v in cp_g.items() if d > tday}),
                "tb_rba_share": [(rba_asof, round(rba_tot / face_tot, 4))] if rba_asof and face_tot else [],
                "tb_rba_total": [(rba_asof, round(rba_tot, 3))] if rba_asof else [],
                "tb_face_total": [(aofm_asof, round(face_tot, 3))], "tb_holdings_asof": [(rba_asof, 1.0)] if rba_asof else [], "_unmatched": unmatched})
    return res


# ───────────────────────── dense daily history (replay) ─────────────────────────
def _prev(ds: List[str], d: str) -> Optional[str]:
    """latest element of sorted ds strictly before d"""
    i = bisect.bisect_left(ds, d)
    return ds[i - 1] if i > 0 else None


def net_daily_history(lines: List[dict], rba_rows: List[dict], days: List[str], title: Optional[str] = AGS_TITLE) -> Dict[str, Series]:
    """dense daily series over `days`: for each day d the latest AOFM snapshot dated < d and the latest RBA snapshot dated < d (strictly before, so a
    bond redeeming on d is still in the previous month-end); flows on a day absent from `days` book on the next listed day; None before the first AOFM snapshot"""
    keys = ["tb_redemptions_net_daily", "tb_coupons_net_daily", "tb_redemptions_gross_daily", "tb_coupons_gross_daily"]
    if not days:
        return {k: [] for k in keys}
    days = sorted(days)
    aofm_ds = sorted({l["date"] for l in lines})
    rba_ds = rba_dates(rba_rows, title)
    by_aofm: Dict[str, List[dict]] = defaultdict(list)
    for l in lines:
        if l.get("maturity"):
            by_aofm[l["date"]].append(l)
    by_rba: Dict[str, Dict[str, float]] = {}
    cache: Dict[Tuple[str, Optional[str]], Dict[str, Dict[str, float]]] = {}

    def expand(a: str, r: Optional[str]) -> Dict[str, Dict[str, float]]:
        key = (a, r)
        if key in cache:
            return cache[key]
        if r is not None and r not in by_rba:
            by_rba[r] = _holdings_at(rba_rows, r, title)
        net, _ = _net_lines(by_aofm[a], by_rba[r] if r is not None else {})
        # events dated from the snapshot date to the last day we may need (next snapshot at most, but a cheap bound: last replay day)
        lo, hi = a, days[-1]
        ev: Dict[str, Dict[str, float]] = {k: defaultdict(float) for k in keys}
        for l in net:
            m = l["maturity"]
            if lo < m <= hi:
                ev["tb_redemptions_net_daily"][m] += l["net"]
                ev["tb_redemptions_gross_daily"][m] += l["face"]
            for d in _coupon_dates(m, lo, hi):
                if d > lo:
                    ev["tb_coupons_net_daily"][d] += l["net"] * l["coupon"] / 200.0
                    ev["tb_coupons_gross_daily"][d] += l["face"] * l["coupon"] / 200.0
        cache[key] = ev
        return ev

    acc: Dict[str, Dict[str, float]] = {k: defaultdict(float) for k in keys}
    valid = set()
    # walk calendar days from the first replay day so that a non-business flow lands on the next listed day
    d0 = date.fromisoformat(days[0])
    d1 = date.fromisoformat(days[-1])
    di = 0
    pending: Dict[str, float] = defaultdict(float)  # key → carried amount for days not in `days`
    day_set = set(days)
    x = d0
    first_snap = aofm_ds[0] if aofm_ds else None
    while x <= d1:
        ds = x.isoformat()
        a = _prev(aofm_ds, ds)
        if a is not None:
            r = _prev(rba_ds, ds)
            ev = expand(a, r)
            for k in keys:
                v = ev[k].get(ds)
                if v:
                    pending[k] += v
        if ds in day_set:
            if a is not None:
                valid.add(ds)
            for k in keys:
                acc[k][ds] += pending[k]
                pending[k] = 0.0
        x += timedelta(days=1)
    out: Dict[str, Series] = {}
    for k in keys:
        out[k] = [(d, round(acc[k][d], 3) if d in valid else None) for d in days]
    return out
