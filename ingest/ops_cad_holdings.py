"""CAD v0.4 — Bank of Canada holdings of Government of Canada securities and the private-held GoC calendar.

Sources (fixtures/cad, verified 2026-09-10):
  * bankofcanada.ca/markets/government-securities-auctions/bank-of-canada-holdings/  (HTML, three tables: GoC treasury bills,
    GoC bonds, Canada Mortgage Bonds; each preceded by "As of date: Month D, YYYY, HH:MM (ET)"; par values in CAD dollars).
    The BoC keeps only the latest snapshot on that page; month-end snapshots live under
    .../historical-bank-of-canada-holdings/?blob=boc_holdings_YYYY_MM.html (2018_12 → latest month) — see blob_names / blob_url.
  * Valet group GOC_OUTSTANDING (one row per ISIN, DOM_DBT_* columns, amounts in CAD dollars; total / subtotal rows have no ISIN).

Units: CAD millions (float, 3 decimals).  Sign convention as in ops_cad: + = settlement balances created, so redemptions and
coupons paid to the private sector are positive amounts; "ahead" series are calendars (positive), not flows.

Netting rule: private-held = outstanding − BoC par (full par; the "of which on repo/loan" column is informational — a bond
lent out still belongs economically to the BoC).  BoC-held maturities/coupons are government ↔ BoC, no settlement-balance effect.
Real Return Bonds (BD-REAL): the BoC table reports nominal par, so private nominal = outstanding nominal − BoC par and the
index ratio (inflation-adjusted ÷ nominal outstanding) is applied to that private nominal for both the redemption and the
semi-annual coupon (coupon on the indexed principal).  The gross series use the inflation-adjusted outstanding likewise.

Coupon convention (same as ops_aud.tb_calendar): semi-annual on the maturity day-of-month and six months earlier, amount =
principal × coupon / 200; dates must be <= maturity and, when an issue date is known, after it (no coupon before issuance;
the first short/long coupon is not modelled).  Calendars keep raw dates; net_daily_history books a flow dated on a day
absent from the replay's day list (weekend / holiday) on the next listed day, so the dense series lose nothing."""
from __future__ import annotations
import bisect
import csv
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from .series import Series
from .ops_cad import _num, _iso, _bucket, business_days  # noqa: F401  (business_days re-exported for callers)

HOLDINGS_URL = "https://www.bankofcanada.ca/markets/government-securities-auctions/bank-of-canada-holdings/"
HISTORICAL_URL = HOLDINGS_URL + "historical-bank-of-canada-holdings/"
ARCHIVE_COLS = ["asof", "kind", "maturity", "coupon", "isin", "par", "on_repo"]
_MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                           "september", "october", "november", "december"])}


# ───────────────────────── helpers ─────────────────────────
def _mn(v) -> Optional[float]:
    """CAD dollars (with thousands separators) → CAD millions, 3 decimals"""
    n = _num(v)
    return None if n is None else round(n / 1e6, 3)


def _asof_iso(text: str) -> Optional[str]:
    """'September 10, 2026, 06:00 (ET)' → '2026-09-10'"""
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", text or "")
    if not m or m.group(1).lower() not in _MONTHS:
        return None
    try:
        return date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
    except ValueError:
        return None


def _kind(heading: str) -> Optional[str]:
    h = (heading or "").lower()
    if "mortgage" in h:
        return "cmb"
    if "treasury bill" in h or "t-bill" in h:
        return "tbill"
    if "bond" in h:
        return "bond"
    return None


def blob_names(start: str = "2018-12", end: Optional[str] = None) -> List[str]:
    """['boc_holdings_2018_12.html', …, 'boc_holdings_YYYY_MM.html'] for every month in [start, end] (end defaults to the
    last complete month before today, i.e. the latest blob the historical index can list)."""
    if end is None:
        t = date.today().replace(day=1) - timedelta(days=1)
        end = t.strftime("%Y-%m")
    y0, m0 = int(start[:4]), int(start[5:7])
    y1, m1 = int(end[:4]), int(end[5:7])
    out = []
    while (y0, m0) <= (y1, m1):
        out.append("boc_holdings_%04d_%02d.html" % (y0, m0))
        m0 += 1
        if m0 > 12:
            y0, m0 = y0 + 1, 1
    return out


def blob_url(name: str) -> str:
    return HISTORICAL_URL + "?blob=" + name


# ───────────────────────── BoC holdings page (HTML) ─────────────────────────
class _HoldingsParser(HTMLParser):
    """Walks the page in document order: remembers the last <h2>/<h3> heading and the last 'As of date' text before each
    <table>, then collects <tbody> rows as lists of cell texts (<tfoot> totals are skipped)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: List[Tuple[str, str, List[List[str]]]] = []   # (heading, asof_text, rows)
        self._heading = ""
        self._asof = ""
        self._in_heading = False
        self._in_p = False
        self._text = ""
        self._table: Optional[List[List[str]]] = None
        self._in_foot = False
        self._row: Optional[List[str]] = None
        self._cell: Optional[str] = None

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4"):
            self._in_heading, self._text = True, ""
        elif tag == "p":
            self._in_p, self._text = True, ""
        elif tag == "table":
            self._table, self._in_foot = [], False
            self.tables.append((self._heading, self._asof, self._table))
        elif tag == "tfoot":
            self._in_foot = True
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = ""

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4") and self._in_heading:
            self._in_heading = False
            if _kind(self._text):
                self._heading, self._asof = self._text.strip(), ""
        elif tag == "p" and self._in_p:
            self._in_p = False
            if "as of" in self._text.lower():
                self._asof = self._text.strip()
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._table is not None and not self._in_foot and self._row and any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "tfoot":
            self._in_foot = False
        elif tag == "table":
            self._table = None

    def handle_data(self, data):
        if self._in_heading or self._in_p:
            self._text += data
        if self._cell is not None:
            self._cell += data


def parse_boc_holdings_html(html: str) -> List[dict]:
    """Rows {asof, kind ('tbill'|'bond'|'cmb'), maturity, coupon (% or None), isin, par ($M), on_repo ($M or None)} from the
    live page or a historical blob.  Table kind from the heading before each table, as-of date from the 'As of date' line;
    columns are located by the header row (Maturity / Coupon rate / ISIN / Par value / Of which on repo/loan)."""
    p = _HoldingsParser()
    p.feed(html)
    p.close()
    out: List[dict] = []
    for heading, asof_text, rows in p.tables:
        kind, asof = _kind(heading), _asof_iso(asof_text)
        if not kind or not asof or not rows:
            continue
        hdr = [c.lower() for c in rows[0]]
        if not any("isin" in c for c in hdr):
            continue
        col = {}
        for i, c in enumerate(hdr):
            if c.startswith("maturity"):
                col["maturity"] = i
            elif c.startswith("coupon"):
                col["coupon"] = i
            elif "isin" in c:
                col["isin"] = i
            elif c.startswith("par"):
                col["par"] = i
            elif "repo" in c or "loan" in c:
                col["on_repo"] = i
        for r in rows[1:]:
            g = lambda k: r[col[k]] if k in col and col[k] < len(r) else ""
            isin, mat = g("isin").strip().upper(), _iso(g("maturity"))
            if not re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", isin) or not mat:
                continue
            out.append({"asof": asof, "kind": kind, "maturity": mat, "coupon": _num(g("coupon")), "isin": isin,
                        "par": _mn(g("par")), "on_repo": _mn(g("on_repo"))})
    out.sort(key=lambda r: (r["asof"], r["kind"], r["maturity"], r["isin"]))
    return out


def holdings_latest(rows: List[dict], kinds=("tbill", "bond")) -> Dict[str, dict]:
    """{isin: row} for the latest as-of among the given kinds (each kind may carry its own as-of; the max across them is used
    and only rows of that as-of are returned)."""
    sel = [r for r in rows if r.get("kind") in kinds and r.get("asof")]
    if not sel:
        return {}
    latest = max(r["asof"] for r in sel)
    return {r["isin"]: r for r in sel if r["asof"] == latest}


# ───────────────────────── archive ─────────────────────────
def read_holdings_archive(path: str) -> List[dict]:
    out: List[dict] = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r.get("asof") or not r.get("isin"):
                continue
            out.append({"asof": r["asof"], "kind": r.get("kind", ""), "maturity": r.get("maturity", ""), "coupon": _num(r.get("coupon")),
                        "isin": r["isin"], "par": _num(r.get("par")), "on_repo": _num(r.get("on_repo"))})
    out.sort(key=lambda r: (r["asof"], r["kind"], r["maturity"], r["isin"]))
    return out


def merge_holdings_archive(path: str, rows: List[dict]) -> List[dict]:
    """append-only CSV keyed by (asof, isin) — a re-parse of the same snapshot replaces its rows, older snapshots are kept"""
    m: Dict[Tuple[str, str], dict] = {(r["asof"], r["isin"]): r for r in read_holdings_archive(path)}
    for r in rows:
        if r.get("asof") and r.get("isin"):
            m[(r["asof"], r["isin"])] = dict(r)
    merged = sorted(m.values(), key=lambda r: (r["asof"], r["kind"], r["maturity"], r["isin"]))
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(ARCHIVE_COLS)
        for r in merged:
            w.writerow(["" if r.get(k) is None else r.get(k) for k in ARCHIVE_COLS])
    return merged


# ───────────────────────── Valet GOC_OUTSTANDING ─────────────────────────
def parse_goc_outstanding(rows: List[dict]) -> List[dict]:
    """Rows with an ISIN for the latest DOM_DBT_AS_OF_DATE only (flattened Valet observations or the CSV of them):
    {asof, isin, security_type ('BOND'|'MM'), instrument_type, coupon, issue_date, maturity, outstanding ($M nominal),
    inflation_adjusted ($M or None)}.  Total / subtotal rows (no ISIN) are skipped."""
    sel = [r for r in rows if (r.get("DOM_DBT_ISIN") or "").strip() and _iso(r.get("DOM_DBT_AS_OF_DATE"))]
    if not sel:
        return []
    latest = max(_iso(r["DOM_DBT_AS_OF_DATE"]) for r in sel)
    out: List[dict] = []
    for r in sel:
        if _iso(r["DOM_DBT_AS_OF_DATE"]) != latest:
            continue
        nominal = _mn(r.get("DOM_DBT_OUTSTANDING_AMOUNT"))
        if nominal is None:
            continue
        adj = _mn(r.get("DOM_DBT_OUTSTANDING_AMOUNT_INF_ADJ"))
        out.append({"asof": latest, "isin": r["DOM_DBT_ISIN"].strip().upper(),
                    "security_type": (r.get("DOM_DBT_SECURITY_TYPE") or "").strip().upper(),
                    "instrument_type": (r.get("DOM_DBT_INSTRUMENT_TYPE") or "").strip().upper(),
                    "coupon": _num(r.get("DOM_DBT_COUPON_RATE")), "issue_date": _iso(r.get("DOM_DBT_ISSUE_DATE")),
                    "maturity": _iso(r.get("DOM_DBT_MATURITY_DATE")), "outstanding": nominal,
                    "inflation_adjusted": None if adj is None or adj == nominal else adj})
    out.sort(key=lambda r: (r["asof"], r["security_type"], r["maturity"] or "", r["isin"]))
    return out


def goc_outstanding_from_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return parse_goc_outstanding([dict(r) for r in csv.DictReader(f)])


# ───────────────────────── netting core ─────────────────────────
def _is_real(o: dict) -> bool:
    return "REAL" in (o.get("instrument_type") or "")


def _ratio(o: dict) -> float:
    """index ratio for Real Return Bonds (inflation-adjusted ÷ nominal outstanding); 1 otherwise"""
    if _is_real(o) and o.get("inflation_adjusted") and o.get("outstanding"):
        return o["inflation_adjusted"] / o["outstanding"]
    return 1.0


def _lines(outstanding: List[dict], held: Dict[str, dict]) -> Tuple[List[dict], List[str]]:
    """one line per outstanding ISIN: gross / boc / private principal (index ratio applied), maturity, coupon, kind"""
    lines: List[dict] = []
    seen = set()
    for o in outstanding:
        isin = o.get("isin")
        if not isin or not o.get("maturity") or o.get("outstanding") is None:
            continue
        seen.add(isin)
        h = held.get(isin)
        boc = (h.get("par") or 0.0) if h else 0.0
        k = _ratio(o)
        nominal_priv = max(0.0, o["outstanding"] - boc)
        lines.append({"isin": isin, "kind": "bond" if o.get("security_type") == "BOND" else "tbill", "maturity": o["maturity"],
                      "issue_date": o.get("issue_date"), "coupon": o.get("coupon") or 0.0,
                      "gross": o["outstanding"] * k, "boc": min(boc, o["outstanding"]) * k, "private": nominal_priv * k})
    unmatched = sorted(i for i in held if i not in seen)
    return lines, unmatched


def _coupon_dates(maturity: str, y0: int, y1: int) -> List[str]:
    mo, dd = int(maturity[5:7]), int(maturity[8:10])
    out = []
    for yy in range(y0, y1 + 1):
        for mm in (mo, (mo + 5) % 12 + 1):
            try:
                out.append(date(yy, mm, dd).isoformat())
            except ValueError:
                continue
    return out


def _is_coupon_date(line: dict, d: str) -> bool:
    m = line["maturity"]
    if d > m or (line.get("issue_date") and d <= line["issue_date"]):
        return False
    mo = int(m[5:7])
    return d[8:10] == m[8:10] and int(d[5:7]) in (mo, (mo + 5) % 12 + 1)


def net_calendar(outstanding: List[dict], holdings: List[dict], horizon_days: int = 365, back_days: int = 90,
                 today: Optional[str] = None) -> Dict[str, Series]:
    """Private-held GoC calendar from the latest outstanding snapshot netted with the latest BoC holdings snapshot.
    holdings: rows from parse_boc_holdings_html / the archive (any as-of; the latest tbill/bond snapshot is used).
    Returns calendars (ahead / paid), the gross and BoC variants, summary series and '_unmatched' (BoC-held ISINs absent
    from the outstanding list — a list, not a Series; the caller logs it)."""
    tday = today or date.today().isoformat()
    t0 = date.fromisoformat(tday)
    end = (t0 + timedelta(days=horizon_days)).isoformat()
    start = (t0 - timedelta(days=back_days)).isoformat()
    held = holdings_latest(holdings)
    lines, unmatched = _lines(outstanding, held)
    red_n: Dict[str, float] = defaultdict(float)
    red_g: Dict[str, float] = defaultdict(float)
    red_b: Dict[str, float] = defaultdict(float)
    cpn_n: Dict[str, float] = defaultdict(float)
    cpn_g: Dict[str, float] = defaultdict(float)
    tb_n: Dict[str, float] = defaultdict(float)
    tb_g: Dict[str, float] = defaultdict(float)
    for l in lines:
        m = l["maturity"]
        if l["kind"] == "tbill":
            if tday < m <= end:
                tb_n[m] += l["private"]
                tb_g[m] += l["gross"]
            continue
        if tday < m <= end:
            red_n[m] += l["private"]
            red_g[m] += l["gross"]
            red_b[m] += l["boc"]
        if l["coupon"]:
            for d in _coupon_dates(m, int(start[:4]), int(end[:4])):
                if start <= d <= end and _is_coupon_date(l, d):
                    cpn_n[d] += l["private"] * l["coupon"] / 200.0
                    cpn_g[d] += l["gross"] * l["coupon"] / 200.0
    # summary (nominal par, as the BoC table reports it)
    out_b = sum(o["outstanding"] for o in outstanding if o.get("security_type") == "BOND" and o.get("outstanding"))
    out_t = sum(o["outstanding"] for o in outstanding if o.get("security_type") == "MM" and o.get("outstanding"))
    boc_b = sum(h.get("par") or 0.0 for h in held.values() if h.get("kind") == "bond")
    boc_t = sum(h.get("par") or 0.0 for h in held.values() if h.get("kind") == "tbill")
    asof_h = max((h["asof"] for h in held.values()), default=None)
    asof_o = max((o["asof"] for o in outstanding if o.get("asof")), default=None)
    summary = lambda v: [(asof_h, round(v, 4))] if asof_h else []
    return {
        "bond_redemptions_net_ahead": _bucket(red_n), "bond_redemptions_gross_ahead": _bucket(red_g), "bond_redemptions_boc_ahead": _bucket(red_b),
        "bond_coupons_net_paid": _bucket({d: v for d, v in cpn_n.items() if d <= tday}),
        "bond_coupons_net_ahead": _bucket({d: v for d, v in cpn_n.items() if d > tday}),
        "bond_coupons_gross_paid": _bucket({d: v for d, v in cpn_g.items() if d <= tday}),
        "bond_coupons_gross_ahead": _bucket({d: v for d, v in cpn_g.items() if d > tday}),
        "tbill_maturities_net_ahead": _bucket(tb_n), "tbill_maturities_gross_ahead": _bucket(tb_g),
        "boc_share_bonds": summary(boc_b / out_b) if out_b else [], "boc_share_tbills": summary(boc_t / out_t) if out_t else [],
        "boc_holdings_bonds_total": summary(boc_b), "boc_holdings_tbills_total": summary(boc_t),
        "goc_outstanding_bonds_total": [(asof_o, round(out_b, 3))] if asof_o else [],
        "goc_outstanding_tbills_total": [(asof_o, round(out_t, 3))] if asof_o else [],
        "holdings_asof": [(asof_h, 1.0)] if asof_h else [],
        "_unmatched": unmatched,
    }


# ───────────────────────── replay: daily net flows from monthly snapshots ─────────────────────────
def net_daily_history(holdings_hist: List[dict], outstanding_hist: List[dict], days: List[str]) -> Dict[str, Series]:
    """Dense daily private-held flows for the replay: on each day d the latest holdings snapshot (asof <= d) and the latest
    outstanding snapshot (asof <= d) are used (both may be monthly).  Days with no prior snapshot of either input → None.
    A flow dated on a day absent from `days` (weekend / holiday) is booked on the next day in `days` (GoC pays on the
    following business day).  Snapshots are pre-sorted; each (holdings, outstanding) snapshot pair is expanded to a
    date → amount map once and cached, so the per-day work is a bisect plus a dict lookup."""
    days = sorted(days)
    h_by: Dict[str, List[dict]] = defaultdict(list)
    for r in holdings_hist:
        if r.get("kind") in ("tbill", "bond") and r.get("asof"):
            h_by[r["asof"]].append(r)
    o_by: Dict[str, List[dict]] = defaultdict(list)
    for r in outstanding_hist:
        if r.get("asof") and r.get("isin"):
            o_by[r["asof"]].append(r)
    h_keys, o_keys = sorted(h_by), sorted(o_by)
    cache: Dict[Tuple[str, str], Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]] = {}

    def snap(d: str) -> Optional[str]:
        """first day in `days` >= d (None when beyond the window)"""
        k = bisect.bisect_left(days, d)
        return days[k] if k < len(days) else None

    def expand(hk: str, ok: str):
        key = (hk, ok)
        if key in cache:
            return cache[key]
        held = {r["isin"]: r for r in h_by[hk]}
        lines, _ = _lines(o_by[ok], held)
        red: Dict[str, float] = defaultdict(float)
        cpn: Dict[str, float] = defaultdict(float)
        tb: Dict[str, float] = defaultdict(float)
        for l in lines:
            m = l["maturity"]
            sm = snap(m)
            if l["kind"] == "tbill":
                if sm and m >= days[0]:
                    tb[sm] += l["private"]
                continue
            if sm and m >= days[0]:
                red[sm] += l["private"]
            if l["coupon"]:
                for c in _coupon_dates(m, int(days[0][:4]), int(days[-1][:4])):
                    sc = snap(c)
                    if sc and c >= days[0] and _is_coupon_date(l, c):
                        cpn[sc] += l["private"] * l["coupon"] / 200.0
        cache[key] = (red, cpn, tb)
        return cache[key]

    out_r: Series = []
    out_c: Series = []
    out_t: Series = []
    for d in days:
        i, j = bisect.bisect_right(h_keys, d), bisect.bisect_right(o_keys, d)
        if i == 0 or j == 0:
            out_r.append((d, None))
            out_c.append((d, None))
            out_t.append((d, None))
            continue
        red, cpn, tb = expand(h_keys[i - 1], o_keys[j - 1])
        out_r.append((d, round(red.get(d, 0.0), 3)))
        out_c.append((d, round(cpn.get(d, 0.0), 3)))
        out_t.append((d, round(tb.get(d, 0.0), 3)))
    return {"bond_redemptions_net_daily": out_r, "bond_coupons_net_daily": out_c, "tbill_maturities_net_daily": out_t}
