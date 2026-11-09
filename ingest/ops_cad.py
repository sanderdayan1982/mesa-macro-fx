"""CAD v0.4 — Bank of Canada operations and Government of Canada issuance at operation level.

Sources verified 2026-09-10 (VERIFICACIONES_V04.md):
  * Valet group observations  /valet/observations/group/<GROUP>/json  (the /groups/<G>/json route returns metadata only)
      TERM_REPO_RESULTS   428 ops since 2015  TR_SETTLEMENT_DATE / TR_MATURITY_DATE / TR_ALLOCATED_AMOUNT ($M)
      OR_RESULTS          327 ops since 2020  OR_SETTLEMENT_DATE / OR_MATURITY_DATE / OR_ALLOCATED_AMOUNT
      ORR                 412 ops since 2022  ORR_SETTLEMENT_DATE / ORR_MATURITY_DATE / ORR_ALLOCATED_AMOUNT
      AUC_RGAM_RESULTS    2 164 auctions since 2024-02-21  AUC_RGAM_SETTLEMENT_DATE / _MATURITY_DATE / _AMOUNT / _COVERAGE
      AUC_TBILL_RESULTS / AUC_BOND_RESULTS  issue date, maturity date, amount, BoC purchase (already in fixtures)
      AUC_BOND_S_RESULTS_REPURCHASE  bond switch repurchases: settlement date, amount repurchased
  * Daily table "Indicators related to market operations" (HTML, 6-business-day rolling window).
      As of 2026-11-09 the same quantities are also Valet series in $M (ACTUAL, SPRA_OUT, SRA_OUT, TERMREPOS, SEC_LEND);
      the HTML dates use a non-breaking hyphen and the old "Actual" row is "Amount in Lynx". Archived daily by run.py.

Reserve mechanics (MMT / Mosler sign convention, + = settlement balances created):
  term repo / OR allocated at settlement → +; matures → −.  ORR allocated → −; matures → +.
  Receiver General morning auction placed → + (government cash BoC → banks); matures → −.
  Bills / bonds issued to the private sector (amount − BoC purchase) at issue date → −; matured (private-held part) → +;
  repurchased from the private sector → +.  BoC-held maturities are government ↔ BoC, no settlement-balance effect.
Nothing here decides a regime: every series is published, and the new flow components are exposed as a *shadow* score
(signals.components_v04) until the replay recalibrates the cuts (CAMBIOS_V04_PENDIENTES.md, step 5)."""
from __future__ import annotations
import csv
import html as html_lib
import io
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional
from .series import Series, clean

Row = Dict[str, str]

GROUPS = {
    "term_repo": "TERM_REPO_RESULTS",
    "or": "OR_RESULTS",
    "orr": "ORR",
    "rgam": "AUC_RGAM_RESULTS",
    "tbill": "AUC_TBILL_RESULTS",
    "bond": "AUC_BOND_RESULTS",
    "bond_repurchase": "AUC_BOND_S_RESULTS_REPURCHASE",
}


# ───────────────────────── helpers ─────────────────────────
def _num(v) -> Optional[float]:
    try:
        if v in (None, "", "-"):
            return None
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def _iso(v) -> Optional[str]:
    v = (v or "").strip()
    return v[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", v) else None


def business_days(start: str, end: str) -> List[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    out = []
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bucket(flows: Dict[str, float], start: Optional[str] = None) -> Series:
    return clean(sorted((d, round(v, 3)) for d, v in flows.items() if d and (start is None or d >= start)))


def _stock(flows: Series, days: List[str]) -> Series:
    """cumulative stock over business days (pre-history flows are summed into the first day)"""
    fm = defaultdict(float)
    for d, v in flows:
        fm[d] += v
    out, acc = [], 0.0
    if days:
        acc = sum(v for d, v in fm.items() if d < days[0])
    for d in days:
        acc += fm.get(d, 0.0)
        out.append((d, round(acc, 3)))
    return out


# ───────────────────────── Valet group rows ─────────────────────────
def parse_group_json(j: dict) -> List[Row]:
    rows: List[Row] = []
    for o in j.get("observations", []):
        r: Row = {}
        for k, v in o.items():
            r[k] = v.get("v", "") if isinstance(v, dict) else ("" if v is None else str(v))
        rows.append(r)
    return rows


def rows_from_csv(text: str) -> List[Row]:
    return [dict(r) for r in csv.DictReader(io.StringIO(text))]


# ───────────────────────── BoC operations → flows ─────────────────────────
def op_flows(rows: List[Row], settle: str, mature: str, amount: str, sign: float = 1.0) -> Dict[str, Series]:
    """+sign×amount at settlement, −sign×amount at maturity (per operation)."""
    inj: Dict[str, float] = defaultdict(float)
    dr: Dict[str, float] = defaultdict(float)
    for r in rows:
        a = _num(r.get(amount))
        s, m = _iso(r.get(settle)), _iso(r.get(mature))
        if a is None or not s:
            continue
        inj[s] += sign * a
        if m:
            dr[m] += -sign * a
    today = date.today().isoformat()
    ahead = {d: v for d, v in dr.items() if d > today}          # scheduled drains: a calendar, not a flow
    inj = {d: v for d, v in inj.items() if d <= today}
    dr = {d: v for d, v in dr.items() if d <= today}
    net: Dict[str, float] = defaultdict(float)
    for d, v in inj.items():
        net[d] += v
    for d, v in dr.items():
        net[d] += v
    return {"settled": _bucket(inj), "matured": _bucket(dr), "net": _bucket(net), "ahead": _bucket(ahead)}


def term_repo_series(rows: List[Row], days: List[str]) -> Dict[str, Series]:
    f = op_flows(rows, "TR_SETTLEMENT_DATE", "TR_MATURITY_DATE", "TR_ALLOCATED_AMOUNT")
    return {"term_repo_settled": f["settled"], "term_repo_matured": f["matured"], "term_repo_net_daily": f["net"],
            "term_repo_outstanding": _stock(f["net"], days), "term_repo_maturities_ahead": f["ahead"]}


def or_orr_series(or_rows: List[Row], orr_rows: List[Row]) -> Dict[str, Series]:
    a = op_flows(or_rows, "OR_SETTLEMENT_DATE", "OR_MATURITY_DATE", "OR_ALLOCATED_AMOUNT", +1.0)
    b = op_flows(orr_rows, "ORR_SETTLEMENT_DATE", "ORR_MATURITY_DATE", "ORR_ALLOCATED_AMOUNT", -1.0)
    net: Dict[str, float] = defaultdict(float)
    for d, v in a["net"]:
        net[d] += v
    for d, v in b["net"]:
        net[d] += v
    return {"or_settled": a["settled"], "orr_settled": [(d, -v) for d, v in b["settled"]], "overnight_ops_net_daily": _bucket(net)}


def rgam_series(rows: List[Row], days: List[str]) -> Dict[str, Series]:
    f = op_flows(rows, "AUC_RGAM_SETTLEMENT_DATE", "AUC_RGAM_MATURITY_DATE", "AUC_RGAM_AMOUNT")
    cov: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        c, d = _num(r.get("AUC_RGAM_COVERAGE")), _iso(r.get("AUC_RGAM_AUCTION_DATE"))
        if c is not None and d:
            cov[d].append(c)
    return {"rg_am_placed": f["settled"], "rg_am_matured": f["matured"], "rg_am_net_daily": f["net"],
            "rg_am_outstanding": _stock(f["net"], days), "rg_am_maturities_ahead": f["ahead"],
            "rg_am_coverage": clean(sorted((d, round(sum(v) / len(v), 3)) for d, v in cov.items()))}


# ───────────────────────── Government of Canada issuance → net issuance to the private sector ─────────────────────────
def _dense(flows: Series, days: List[str]) -> Series:
    """daily flow on every business day of the window (0 on days without operations) so 5-session sums are true sessions"""
    fm = defaultdict(float)
    for d, v in flows:
        fm[d] += v
    return [(d, round(fm.get(d, 0.0), 3)) for d in days]


def issuance_series(tbill_rows: List[Row], bond_rows: List[Row], repurchase_rows: Optional[List[Row]] = None,
                    start: Optional[str] = None, days: Optional[List[str]] = None) -> Dict[str, Series]:
    """Private-sector net issuance by settlement date (CAD millions):
       issued_private = amount − BoC purchase at issue date (drain, sign −)
       matured_private = the same private-held amount at maturity (injection, sign +)
       repurchased = bond switch repurchase amount at settlement (injection, +)
       Coupons are not yet included (v0.4 first pass; see CAMBIOS C3)."""
    iss: Dict[str, float] = defaultdict(float)
    mat: Dict[str, float] = defaultdict(float)
    boc: Dict[str, float] = defaultdict(float)
    for rows, p in ((tbill_rows, "AUC_TBILL"), (bond_rows, "AUC_BOND")):
        for r in rows:
            a = _num(r.get(p + "_AMOUNT"))
            b = _num(r.get(p + "_BOC_PURCHASE")) or 0.0
            i, m = _iso(r.get(p + "_ISSUE_DATE")), _iso(r.get(p + "_MATURITY_DATE"))
            if a is None or not i:
                continue
            priv = max(0.0, a - b)
            iss[i] += priv
            boc[i] += b
            if m:
                mat[m] += priv
    rep: Dict[str, float] = defaultdict(float)
    for r in repurchase_rows or []:
        a = _num(r.get("AUC_BOND_S_AMOUNT_REPURCHASED"))
        s = _iso(r.get("AUC_BOND_S_SETTLEMENT_DATE"))
        if a is not None and s:
            rep[s] += a
    net: Dict[str, float] = defaultdict(float)
    for d, v in iss.items():
        net[d] -= v
    for d, v in mat.items():
        net[d] += v
    for d, v in rep.items():
        net[d] += v
    today = date.today().isoformat()
    past = lambda m: {d: v for d, v in m.items() if d <= today}  # announced (future) auctions and maturities are a calendar, not a flow
    net = past(net)
    out_iss, out_mat, out_net = _bucket(past(iss), start), _bucket(past(mat), start), _bucket(net, start)
    if days:
        out_iss, out_mat, out_net = _dense(out_iss, days), _dense(out_mat, days), _dense(out_net, days)
    return {"issued_private": out_iss, "matured_private": out_mat,
            "boc_primary_purchase": _bucket(past(boc), start), "repurchased_private": _bucket(past(rep), start),
            "net_issuance_private_daily": out_net,
            "maturities_ahead": clean(sorted((d, round(v, 3)) for d, v in mat.items() if d > today))}


def weekly_sum(daily: Series, end_dates: List[str]) -> Series:
    """sum of daily flows in the 7 calendar days ending on each end date (Wednesday B2 dates → comparable to Δ reserves)"""
    fm = defaultdict(float)
    for d, v in daily:
        fm[d] += v
    out = []
    for e in end_dates:
        e0 = date.fromisoformat(e)
        s = sum(v for d, v in fm.items() if e0 - timedelta(days=6) <= date.fromisoformat(d) <= e0)
        out.append((e, round(s, 3)))
    return out


# ───────────────────────── Daily indicators table (HTML) ─────────────────────────
IND_KEYS = {"Actual": "settlement_actual", "Overnight Repos (OR)": "ind_or", "Overnight Reverse Repos (ORR)": "ind_orr",
            "Term Repos": "ind_term_repos", "Securities Lending": "ind_securities_lending", "Target (Available)": "settlement_target"}

# Same quantities, same unit ($M), published on Valet since the page was rebuilt (verified 2026-11-09 against the
# HTML table and against history/cad/market_ops_indicators.csv: ACTUAL equals every archived "Actual" point).
# TOTAL_SETTLEMENT_BALANCES is Lynx + Real-Time Rail and is $2M above ACTUAL from 2026-11-04; not used, so the
# Lynx series does not jump. TARGET ended 2020-03-20 and is not fetched.
INDICATOR_VALET = (("ACTUAL", "settlement_actual"), ("SPRA_OUT", "ind_or"), ("SRA_OUT", "ind_orr"),
                   ("TERMREPOS", "ind_term_repos"), ("SEC_LEND", "ind_securities_lending"))

_DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-"})


def _cell_text(fragment: str) -> str:
    t = html_lib.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("\xa0", " ").translate(_DASHES)
    return re.sub(r"\s+", " ", t).strip()


def _indicator_row_key(label: str) -> Optional[str]:
    """Row label → archive key. Accepts the pre-2026-11 table and the rebuilt one (case, footnote digit, Lynx rename)."""
    s = re.sub(r"\d+$", "", label).strip().casefold()
    if s.startswith("amount in lynx"):
        return "settlement_target" if "target" in s else "settlement_actual"
    if s.startswith("total settlement balances"):
        return "total_settlement_balances"  # Lynx + RTR; used only if the Lynx / Actual row is missing
    if s.startswith("overnight reverse repo"):
        return "ind_orr"
    if s.startswith("overnight repo"):
        return "ind_or"
    if s.startswith("term repo"):
        return "ind_term_repos"
    if s.startswith("securities lending"):
        return "ind_securities_lending"
    if s.startswith("target (available)"):
        return "settlement_target"
    if s == "actual" or s.startswith("actual "):
        return "settlement_actual"
    return None


def parse_indicators_html(html: str) -> Dict[str, Series]:
    """Second table of bankofcanada.ca/rates/indicators/market-operations-indicators/: header row of ISO dates
    (ASCII hyphen or &#8209;), rows labelled per IND_KEYS or the 2026-11 names. Returns {key: [(date, $M)]}."""
    tables = re.findall(r"<table.*?</table>", html, flags=re.S | re.I)
    out: Dict[str, List] = {k: [] for k in IND_KEYS.values()}
    total: List = []
    for t in tables:
        rows = re.findall(r"<tr.*?</tr>", t, flags=re.S | re.I)
        if not rows:
            continue
        cells0 = [_cell_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], flags=re.S | re.I)]
        dates = [c for c in cells0 if re.match(r"^\d{4}-\d{2}-\d{2}$", c)]
        if len(dates) < 3:
            continue
        for r in rows[1:]:
            cells = [_cell_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, flags=re.S | re.I)]
            if not cells:
                continue
            key = _indicator_row_key(cells[0])
            if not key:
                continue
            dest = total if key == "total_settlement_balances" else out[key]
            for d, v in zip(dates, cells[1:1 + len(dates)]):
                n = _num(v)
                if n is not None:
                    dest.append((d, n))
        if out["settlement_actual"] or out["ind_term_repos"]:
            break  # the first table on the page is the policy-rate table (also dated columns): keep scanning until the Lynx table
    if not out["settlement_actual"] and total:
        out["settlement_actual"] = total
    return {k: clean(v) for k, v in out.items()}


def merge_archive(path: str, fresh: Dict[str, Series]) -> Dict[str, Series]:
    """append-only archive of the rolling table (the BoC keeps 6 days; we keep everything)"""
    keys = list(IND_KEYS.values())
    old: Dict[str, Dict[str, float]] = {k: {} for k in keys}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                for k in keys:
                    v = _num(r.get(k))
                    if v is not None:
                        old[k][r["date"]] = v
    for k in keys:
        for d, v in fresh.get(k, []):
            old[k][d] = v
    dates = sorted(set(d for k in keys for d in old[k]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date"] + keys)
        for d in dates:
            w.writerow([d] + ["" if d not in old[k] else old[k][d] for k in keys])
    return {k: clean(sorted(old[k].items())) for k in keys}


def read_archive(path: str) -> Dict[str, Series]:
    keys = list(IND_KEYS.values())
    out: Dict[str, List] = {k: [] for k in keys}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                for k in keys:
                    v = _num(r.get(k))
                    if v is not None:
                        out[k].append((r["date"], v))
    return {k: clean(v) for k, v in out.items()}
