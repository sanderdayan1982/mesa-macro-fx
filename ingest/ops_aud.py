"""AUD v0.4 — RBA OMO by operation (A3 transaction details + unwinds schedule), AOFM issuance by settlement (bonds, notes, indexed bonds,
buybacks), Treasury Bond redemption / coupon calendar from the AOFM portfolio file.

Sources (VERIFICACIONES_V04.md, ADJUDICACION_METRICAS_AUD.md, A1–A6):
  RBA a3-omo-repo-transaction-details.csv — per operation: date, term (days), value dealt ($m), average / cut-off rate or spread; additional rounds
      in the AAROMO* columns (live 2026-09-10, 5 301 rows since 2013-11-11). OMO repos settle the same day (verified: dealt + term = the unwinds schedule).
  RBA a3-omo-repo-unwinds.csv — ARRRUNW: maturing repo agreements by date, FORWARD schedule (~2 years; includes accrued interest → ~0.3 % above principal).
  AOFM Data Hub XLSX (link discovery by file name on /data-hub; upload-dated URLs, contents updated in place):
      'treasury bonds - issuance.xlsx', 'Treasury Notes - Issuance.xlsx', 'Treasury Indexed Bonds - Issuance*.xlsx' — sheet 'Transactions', header row 2:
      Date Held | Tender Number | Maturity | (Coupon) | ISIN | Amount Offered | Amount Allotted | Amount of Bids | Coverage Ratio | Weighted Average Issue Yield |
      Lowest / Highest Accepted Yield | Highest Bid Yield | ... | Settlement Proceeds | Date Settled   (AUD, not millions)
      'treasury bonds - buybacks.xlsx', 'treasury indexed bonds - buybacks.xlsx' — Date Held | Method | Maturity | Coupon | ISIN | Amount Repurchased | ... |
      Settlement Proceeds | Date Settled; method 'RBA' = transfer to the RBA (no market cash) → excluded.
      'portfolio_aggregate_-_treasury_bonds_-_settlement.xlsx' sheet 'FaceValue' — face value by line at month-end (all CGS on issue, RBA holdings included).

Reserve mechanics (+ = ES balances created):
  OMO repo dealt → + value on the deal date; maturity (deal + term) → −.  AOFM tender → − settlement proceeds on Date Settled (nominal if proceeds missing);
  Treasury Note / TIB maturity → + nominal (market-held by construction); buyback → + proceeds on Date Settled.
  Treasury Bond redemptions and semi-annual coupons: face value by line INCLUDES the RBA's holdings (A3.1 gives the RBA share only in aggregate),
  so they are published as a gross calendar / context and NOT added to the private net-issuance series (A5: the RBA-held part is an OPA→RBA transfer).
Cuts: OMO flows stop at the last dealt date in the file when within 21 days (weekly operations); AOFM flows are current (T+2/T+3 settlement) → cut at today.
Nothing here decides a regime: shadow components only (signals.components_v04)."""
from __future__ import annotations
import csv
import io
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from .series import Series, clean

DATA_HUB = "https://www.aofm.gov.au/data-hub"
AOFM_FILES = {  # name pattern on the Data Hub → fallback URL (verified 2026-09-10)
    "tb_issuance": (r"treasury%20bonds%20-%20issuance", "https://www.aofm.gov.au/sites/default/files/2025-06-20/treasury%20bonds%20-%20issuance.xlsx"),
    "tn_issuance": (r"treasury%20notes%20-%20issuance", "https://www.aofm.gov.au/sites/default/files/2025-06-05/Treasury%20Notes%20-%20Issuance.xlsx"),
    "tib_issuance": (r"treasury%20indexed%20bonds%20-%20issuance", "https://www.aofm.gov.au/sites/default/files/2025-07-10/Treasury%20Indexed%20Bonds%20-%20Issuance_0.xlsx"),
    "tb_buybacks": (r"treasury%20bonds%20-%20buybacks", "https://www.aofm.gov.au/sites/default/files/2025-06-06/treasury%20bonds%20-%20buybacks.xlsx"),
    "tib_buybacks": (r"treasury%20indexed%20bonds%20-%20buybacks", "https://www.aofm.gov.au/sites/default/files/2025-06-06/treasury%20indexed%20bonds%20-%20buybacks.xlsx"),
    "tb_portfolio": (r"portfolio_aggregate_-_treasury_bonds_-_settlement", "https://www.aofm.gov.au/sites/default/files/2025-05-02/portfolio_aggregate_-_treasury_bonds_-_settlement.xlsx"),
}
RBA_OMO_DETAILS = "a3-omo-repo-transaction-details"
RBA_OMO_UNWINDS = "a3-omo-repo-unwinds"
_MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _num(v) -> Optional[float]:
    try:
        if v in (None, "", "-"):
            return None
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _serial(x) -> Optional[str]:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if 20000 < f < 80000:
        return (date(1899, 12, 30) + timedelta(days=int(f))).isoformat()
    return None


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$", s)
    if m:
        return "%s-%02d-%02d" % (m.group(3), _MON[m.group(2).title()], int(m.group(1)))
    return _serial(s)


def business_days(start: str, end: str) -> List[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    out, d = [], d0
    while d <= d1:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bucket(m: Dict[str, float]) -> Series:
    return clean(sorted((d, round(v, 3)) for d, v in m.items() if d))


def _dense(flows: Series, days: List[str]) -> Series:
    fm: Dict[str, float] = defaultdict(float)
    for d, v in flows:
        fm[d] += v
    return [(d, round(fm.get(d, 0.0), 3)) for d in days]


def _stock(events: Dict[str, float], days: List[str]) -> Series:
    lvl = sum(v for d, v in events.items() if d < days[0])
    out = []
    for d in days:
        lvl += events.get(d, 0.0)
        out.append((d, round(lvl, 3)))
    return out


# ───────────────────────── RBA OMO per operation ─────────────────────────
def parse_omo_details(text: str) -> List[dict]:
    """rows: date, term (days), value ($m), wa_rate, cutoff_rate, wa_spread, cutoff_spread, round ('main' | 'additional')"""
    out = []
    hdr: List[str] = []
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if row[0] == "Series ID":
            hdr = [h.strip() for h in row]
            continue
        d = _iso(row[0])
        if not hdr or not d:
            continue
        rec = dict(zip(hdr, row))
        for tag, pre in (("main", "AFROMO"), ("additional", "AAROMO")):
            term, val = _num(rec.get(pre + "TD")), _num(rec.get(pre + "VD"))
            if term is None or val is None:
                continue
            out.append({"date": d, "term": int(term), "value": val, "wa_rate": _num(rec.get(pre + "WAR")), "cutoff_rate": _num(rec.get(pre + "COR")),
                        "wa_spread": _num(rec.get(pre + "WAS")), "cutoff_spread": _num(rec.get(pre + "COS")), "round": tag})
    return out


def parse_omo_unwinds(text: str) -> Series:
    out = []
    hdr = False
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if row[0] == "Series ID":
            hdr = True
            continue
        d = _iso(row[0])
        v = _num(row[1]) if len(row) > 1 else None
        if hdr and d and v is not None:
            out.append((d, v))
    return clean(out)


def omo_flows(ops: List[dict], unwinds: Series, days: List[str], max_lag: int = 21) -> Dict[str, Series]:
    dealt: Dict[str, float] = defaultdict(float)
    mat: Dict[str, float] = defaultdict(float)
    by_term: Dict[str, Dict[str, float]] = {"7": defaultdict(float), "28": defaultdict(float), "other": defaultdict(float)}
    spread: Dict[str, List[float]] = defaultdict(list)
    for o in ops:
        d, t, v = o["date"], o["term"], o["value"]
        dealt[d] += v
        m = (date.fromisoformat(d) + timedelta(days=t)).isoformat()
        mat[m] -= v
        key = "7" if 5 <= t <= 9 else "28" if 25 <= t <= 31 else "other"
        by_term[key][d] += v
        if o.get("wa_spread") is not None:
            spread[d].append(o["wa_spread"])
    today = date.today().isoformat()
    last = max(dealt) if dealt else ""
    cut = min(today, last) if last and (date.today() - date.fromisoformat(last)).days <= max_lag else today
    net: Dict[str, float] = defaultdict(float)
    for d, v in dealt.items():
        if d <= cut:
            net[d] += v
    for d, v in mat.items():
        if d <= cut:
            net[d] += v
    events: Dict[str, float] = defaultdict(float)
    for d, v in dealt.items():
        events[d] += v
    for d, v in mat.items():
        events[d] += v
    stock_full = _stock(events, days)
    # unwinds schedule (published) vs maturities implied by dealt + term: error as % (interest included in the schedule)
    um = dict(unwinds)
    recon = []
    for d in sorted(mat):
        if d > cut and d in um and um[d]:
            recon.append((d, round((um[d] + mat[d]) / um[d] * 100, 3)))  # +mat because mat is negative
    return {"omo_dealt_daily": _bucket({d: v for d, v in dealt.items() if d <= cut}), "omo_matured_daily": _bucket({d: v for d, v in mat.items() if d <= cut}),
            "omo_net_daily": _dense(_bucket(net), [d for d in days if d <= cut]), "omo_stock_daily": [(d, v) for d, v in stock_full if d <= cut], "omo_stock_full": stock_full,
            "omo_unwinds_ahead": clean([(d, v) for d, v in unwinds if d > cut]), "omo_maturities_implied_ahead": _bucket({d: -v for d, v in mat.items() if d > cut}),
            "omo_takeup_7d": _bucket(by_term["7"]), "omo_takeup_28d": _bucket(by_term["28"]), "omo_takeup_other": _bucket(by_term["other"]),
            "omo_wa_spread_bp": clean(sorted((d, round(sum(v) / len(v), 3)) for d, v in spread.items())), "unwinds_vs_implied_pct": clean(recon), "omo_cut": [(cut, 1.0)]}


def reconcile_stock(stock_full: Series, ref: Series) -> Series:
    """stock from operations − A3 outstanding OMO reverse repos (AORROMO, which carries accrued interest) on common dates"""
    s = dict(stock_full)
    return clean([(d, round(s[d] - v, 3)) for d, v in ref if d in s])


# ───────────────────────── AOFM XLSX (Transactions sheet) ─────────────────────────
def parse_transactions(cells: Dict[str, object]) -> List[dict]:
    """generic reader for the issuance / buyback XLSX: header row = the row whose column A is 'Date Held'; keys lowercased"""
    from .providers_chf import _rows_of
    rows = _rows_of(cells)
    hdr_row = next((r for r in sorted(rows) if str(rows[r].get("A", "")).strip().lower() == "date held"), None)
    if hdr_row is None:
        return []
    hdr = {c: re.sub(r"\s+", " ", str(v)).strip().lower() for c, v in rows[hdr_row].items()}
    out = []
    for r in sorted(rows):
        if r <= hdr_row:
            continue
        row = rows[r]
        held = _serial(row.get("A"))
        if not held:
            continue
        rec = {h: row.get(c) for c, h in hdr.items()}
        rec["held"] = held
        rec["settled"] = _serial(rec.get("date settled")) or held
        rec["maturity"] = _serial(rec.get("maturity"))
        out.append(rec)
    return out


def records_from_csv(path: str, kind: str) -> List[dict]:
    """fixture readers: aud_hist/aofm_*_tenders.csv (date, maturity, coupon, allotted, coverage, wa_yield, tail_bp) and aofm_*_buybacks.csv"""
    out = []
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if kind == "buyback":
            out.append({"held": r["held"], "settled": r.get("settled") or r["held"], "maturity": r.get("maturity"), "method": r.get("method", ""),
                        "amount repurchased": _num(r.get("repurchased")), "settlement proceeds": _num(r.get("proceeds"))})
        else:
            out.append({"held": r["date"], "settled": None, "maturity": r.get("maturity"), "coupon": _num(r.get("coupon")), "amount allotted": _num(r.get("allotted")),
                        "coverage ratio": _num(r.get("coverage")), "weighted average issue yield": _num(r.get("wa_yield")), "tail_bp": _num(r.get("tail_bp")),
                        "settlement proceeds": None})
    return out


SETTLE_BD = {"tb": 2, "tn": 1, "tib": 2}  # fallback when Date Settled is missing (fixture CSVs): verified 2026-09 (TB held 09-09 → 09-11; TN 09-03 → 09-04; TIB 09-03 → 09-07 spans a weekend)


def _bd_add(d: str, n: int) -> str:
    x = date.fromisoformat(d)
    k = 0
    while k < n:
        x += timedelta(days=1)
        if x.weekday() < 5:
            k += 1
    return x.isoformat()


def issuance_flows(recs: Dict[str, List[dict]], buybacks: Dict[str, List[dict]], days: List[str]) -> Dict[str, Series]:
    """recs: {'tb': [...], 'tn': [...], 'tib': [...]} from parse_transactions / records_from_csv; AUD → millions"""
    settled: Dict[str, float] = defaultdict(float)
    by_kind: Dict[str, Dict[str, float]] = {k: defaultdict(float) for k in ("tb", "tn", "tib")}
    tn_mat: Dict[str, float] = defaultdict(float)
    tib_mat: Dict[str, float] = defaultdict(float)
    cov: Dict[str, List[float]] = defaultdict(list)
    tail: Dict[str, List[float]] = defaultdict(list)
    tn_yield: Dict[str, List[float]] = defaultdict(list)
    tb_yield: Dict[str, List[float]] = defaultdict(list)
    today = min(date.today().isoformat(), days[-1]) if days else date.today().isoformat()  # the flow cut never runs past the grid
    for kind, rs in recs.items():
        for r in rs:
            allot = _num(r.get("amount allotted"))
            if allot is None or allot <= 0:
                continue
            s = r.get("settled") or _bd_add(r["held"], SETTLE_BD.get(kind, 2))
            proceeds = _num(r.get("settlement proceeds"))
            cash = (proceeds if proceeds else allot) / 1e6
            settled[s] += cash
            by_kind[kind][s] += cash
            m = r.get("maturity")
            if kind == "tn" and m:
                tn_mat[m] += allot / 1e6
            if kind == "tib" and m:
                tib_mat[m] += allot / 1e6
            c = _num(r.get("coverage ratio"))
            if c is not None:
                cov[r["held"]].append(c)
            hi, wa = _num(r.get("highest accepted yield")), _num(r.get("weighted average issue yield"))
            t = _num(r.get("tail_bp"))
            if t is None and hi is not None and wa is not None:
                t = (hi - wa) * 100
            if t is not None and kind == "tb":
                tail[r["held"]].append(t)
            if wa is not None:
                (tn_yield if kind == "tn" else tb_yield)[r["held"]].append(wa)
    bb: Dict[str, float] = defaultdict(float)
    for kind, rs in buybacks.items():
        for r in rs:
            if str(r.get("method", "")).strip().upper() == "RBA":
                continue  # transfer to the RBA: no market cash
            p = _num(r.get("settlement proceeds")) or _num(r.get("amount repurchased"))
            if p:
                bb[r.get("settled") or r["held"]] += p / 1e6
    net: Dict[str, float] = defaultdict(float)
    for d, v in settled.items():
        if d <= today:
            net[d] -= v
    for src in (tn_mat, tib_mat, bb):
        for d, v in src.items():
            if d <= today:
                net[d] += v
    mean = lambda m: clean(sorted((d, round(sum(v) / len(v), 4)) for d, v in m.items()))
    return {"aofm_settled": _bucket({d: -v for d, v in settled.items() if d <= today}), "tb_settled": _bucket({d: -v for d, v in by_kind["tb"].items() if d <= today}),
            "tn_settled": _bucket({d: -v for d, v in by_kind["tn"].items() if d <= today}), "tib_settled": _bucket({d: -v for d, v in by_kind["tib"].items() if d <= today}),
            "aofm_settlements_ahead": _bucket({d: v for d, v in settled.items() if d > today}),
            "tn_matured": _bucket({d: v for d, v in tn_mat.items() if d <= today}), "tn_maturities_ahead": _bucket({d: v for d, v in tn_mat.items() if d > today}),
            "tib_matured": _bucket({d: v for d, v in tib_mat.items() if d <= today}), "tib_maturities_ahead": _bucket({d: v for d, v in tib_mat.items() if d > today}),
            "buybacks_settled": _bucket({d: v for d, v in bb.items() if d <= today}),
            "net_issuance_private_daily": _dense(_bucket(net), days), "tender_coverage": mean(cov), "tb_tail_bp": mean(tail), "tn_wa_yield": mean(tn_yield), "tb_wa_yield": mean(tb_yield),
            "tn_stock_daily": _stock(_events(by_kind["tn"], tn_mat), days)}


def _events(plus: Dict[str, float], minus: Dict[str, float]) -> Dict[str, float]:
    ev: Dict[str, float] = defaultdict(float)
    for d, v in plus.items():
        ev[d] += v
    for d, v in minus.items():
        ev[d] -= v
    return ev


# ───────────────────────── Treasury Bond lines: redemptions and coupons (gross, RBA holdings included) ─────────────────────────
def parse_face_value_sheet(cells: Dict[str, object]) -> List[dict]:
    """'FaceValue' sheet: row with A='Maturity' holds the line maturities, row 'Coupon (%)' the coupons, then one row per month-end (serial in A, negative face in AUD)"""
    from .providers_chf import _rows_of
    rows = _rows_of(cells)
    mrow = next((r for r in sorted(rows) if str(rows[r].get("A", "")).strip() == "Maturity"), None)
    crow = next((r for r in sorted(rows) if str(rows[r].get("A", "")).strip().lower().startswith("coupon")), None)
    if mrow is None or crow is None:
        return []
    mats = {c: _serial(v) for c, v in rows[mrow].items() if c != "A" and _serial(v)}
    cps = {c: _num(v) for c, v in rows[crow].items() if c != "A"}
    out = []
    for r in sorted(rows):
        d = _serial(rows[r].get("A"))
        if not d:
            continue
        for c, m in mats.items():
            v = _num(rows[r].get(c))
            if v:
                out.append({"date": d, "maturity": m, "coupon": cps.get(c), "face": round(-v / 1e6, 3)})
    return out


def face_value_from_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    return [{"date": r["date"], "maturity": r["maturity"], "coupon": _num(r["coupon"]), "face": _num(r["face"])} for r in csv.DictReader(open(path, encoding="utf-8"))]


def tb_calendar(lines: List[dict], horizon_days: int = 365, back_days: int = 90) -> Dict[str, Series]:
    """latest month-end snapshot: redemptions by maturity (face, RBA holdings included) and semi-annual coupons on the maturity day-of-month
    (Treasury Bonds pay on the maturity day and six months earlier; verified on the lines' 15/21-day conventions)"""
    if not lines:
        return {"tb_redemptions_gross_ahead": [], "tb_coupons_gross_paid": [], "tb_coupons_gross_ahead": [], "tb_face_total": []}
    latest = max(l["date"] for l in lines)
    snap = [l for l in lines if l["date"] == latest]
    today = date.today()
    end = (today + timedelta(days=horizon_days)).isoformat()
    start = (today - timedelta(days=back_days)).isoformat()
    red: Dict[str, float] = defaultdict(float)
    cpn: Dict[str, float] = defaultdict(float)
    for l in snap:
        m, f, c = l["maturity"], l["face"] or 0.0, l["coupon"] or 0.0
        if today.isoformat() < m <= end:
            red[m] += f
        mo, dd = int(m[5:7]), int(m[8:10])
        for yy in range(int(start[:4]), int(end[:4]) + 1):
            for mm in (mo, (mo + 5) % 12 + 1):
                try:
                    d = date(yy, mm, dd).isoformat()
                except ValueError:
                    continue
                if start <= d <= end and d <= m:
                    cpn[d] += f * c / 200.0
    tday = today.isoformat()
    return {"tb_redemptions_gross_ahead": _bucket(red), "tb_coupons_gross_paid": _bucket({d: v for d, v in cpn.items() if d <= tday}),
            "tb_coupons_gross_ahead": _bucket({d: v for d, v in cpn.items() if d > tday}), "tb_face_total": [(latest, round(sum(l["face"] or 0.0 for l in snap), 3))]}


# ───────────────────────── Data Hub link discovery ─────────────────────────
def discover_links(html: str) -> Dict[str, str]:
    out = {}
    hrefs = re.findall(r'href="([^"]+\.xlsx)"', html, flags=re.I)
    for key, (pat, fallback) in AOFM_FILES.items():
        hit = next((h for h in hrefs if re.search(pat, h, flags=re.I)), None)
        out[key] = ("https://www.aofm.gov.au" + hit if hit and hit.startswith("/") else hit) if hit else fallback
    return out
