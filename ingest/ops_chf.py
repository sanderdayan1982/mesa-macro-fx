"""CHF v0.4 — SNB absorption by operation date, Confederation issuance by settlement, improved intervention proxy.

Sources (VERIFICACIONES_V04.md, ADJUDICACION_METRICAS_CHF.md, S1–S4):
  SNB gmges.xlsx (money-market operations, one row per operation: transaction date, CP/CT, term, from, to, type, allocation; CHF m;
                  published on the last working day of the month for the previous month → amounts lag up to ~5 weeks)
  SNB snbbillshreg (Issued SNB Bills register: ISIN, payment date, repayment date, outstanding; current, T+1)
  EFV resultate-gmbf.xlsx (MMDRC auctions: Auction | Settlement | Maturity | Days | ISIN | bids | amount | price | yield; sheet per year)
  EFV resultate-anleihen.xlsx (bond auctions: Auction | Settlement | Maturity | prov. ISIN | fungible ISIN | Bond | coupon | bids | amount (market) | ... | own holdings not placed)
  EFV ausstehende-anleihen.xlsx (bonds outstanding: ISIN | Bond | Maturity | coupon | issued total | placed on the market | own placed | own available; captured 2026-09-10, as of 31.08.2026)

Reserve mechanics (+ = sight deposits created):
  SNB Bills: payment date −, repayment date +.  Repo CT (liquidity-absorbing): from −, to +.  Repo CP (liquidity-providing): from +, to −.
  Swaps (CHF leg) are listed but not dated in gmges beyond from/to: treated like CP/CT by side.
  MMDRC: settlement −, maturity +.  Bonds: settlement − (market amount; own tranches not placed excluded), maturity + (placed on the market),
  annual coupon on the maturity day-of-year × placed on the market +.  Own-holding sales in the secondary market are not dated (context only).
Cuts: SNB ops flows stop at min(today, last operation in gmges) when that operation is within 60 days (monthly file); the register and the
EFV files are current → cut at today. Announced auctions without amounts go to the calendar, never to the flows.
Weekly proxy (S3): ΔGI (domestic banks' sight deposits, Friday) − Σ SNB ops net − Σ Confederation net over the week; banknotes, swaps
volumes and third parties stay as recognised noise (monthly only). Nothing here decides a regime (shadow components only)."""
from __future__ import annotations
import csv
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from .series import Series, clean

Row = Dict[str, object]
OUTSTANDING_URL = "https://www.efv.admin.ch/dam/en/sd-web/K9gjjBZzAoPz/ausstehende-anleihen.xlsx"


def _num(v) -> Optional[float]:
    try:
        if v in (None, "", "-"):
            return None
        return float(str(v).replace(",", "").replace("'", ""))
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
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", s)
    if m:
        return "%s-%s-%s" % (m.group(3), m.group(2), m.group(1))
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
    """cumulative sum of dated events (events before days[0] included in the opening level)"""
    lvl = sum(v for d, v in events.items() if d < days[0])
    out = []
    for d in days:
        lvl += events.get(d, 0.0)
        out.append((d, round(lvl, 3)))
    return out


# ───────────────────────── archives (ops rows and the bills register roll off the live sources) ─────────────────────────
OPS_COLS = ["date", "side", "term", "from", "to", "type", "procedure", "yield", "premium_bp", "bids", "allocation"]


def _read_rows(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    return [dict(r) for r in csv.DictReader(open(path, encoding="utf-8"))]


def merge_ops_archive(path: str, ops: List[dict]) -> List[dict]:
    """union of the archived operations and the fresh gmges rows, keyed by (date, side, term, from, to, type, allocation)"""
    def key(o):
        return (o.get("date"), o.get("side"), o.get("term"), o.get("from"), o.get("to"), o.get("type"), str(_num(o.get("allocation")) or 0.0))
    seen: Dict[tuple, dict] = {}
    for o in _read_rows(path) + [{k: ("" if o.get(k) is None else o.get(k)) for k in OPS_COLS} for o in ops]:
        seen[key(o)] = o
    rows = sorted(seen.values(), key=lambda o: (str(o.get("date")), str(o.get("from")), str(o.get("type"))))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OPS_COLS)
        w.writeheader()
        for o in rows:
            w.writerow({k: o.get(k, "") for k in OPS_COLS})
    return rows


# ───────────────────────── SNB operations → dated flows ─────────────────────────
def _cut_ops(dates: List[str], max_lag: int = 60) -> str:
    """dates = the 'from' dates of every operation in the file: a repo transacted on T settles T+2 and a Bill auctioned on Thursday pays
    on Monday, so every settlement up to the last 'from' date is known; after it, new absorptions may be missing"""
    today = date.today().isoformat()
    last = max(dates) if dates else ""
    if last and (date.today() - date.fromisoformat(last)).days <= max_lag:
        return min(today, last)
    return today


def repo_flows(ops: List[dict], days: List[str]) -> Dict[str, Series]:
    """CT (SNB takes liquidity: repo / SNB Bills sold via gmges rows) and CP (SNB gives liquidity) by from/to dates.
    Bills rows in gmges are skipped here (the register is the dated source for Bills, see bills_flows)."""
    settle: Dict[str, float] = defaultdict(float)
    mature: Dict[str, float] = defaultdict(float)
    ct_settle: Dict[str, float] = defaultdict(float)
    ct_mature: Dict[str, float] = defaultdict(float)
    swaps: Dict[str, float] = defaultdict(float)
    tdates = [_iso(o.get("from")) for o in ops if _iso(o.get("from"))]  # every operation, Bills included: the file's coverage
    for o in ops:
        a = _num(o.get("allocation"))
        f, t, td = _iso(o.get("from")), _iso(o.get("to")), _iso(o.get("date"))
        typ = str(o.get("type", "")).lower()
        if a is None or not f or not td or typ.startswith("snb bills"):
            continue
        sign = -1.0 if str(o.get("side", "")).strip().upper() == "CT" else 1.0
        if typ.startswith("swap"):
            swaps[f] += sign * a
        settle[f] += sign * a
        if sign < 0:
            ct_settle[f] += a
        if t:
            mature[t] += -sign * a
            if sign < 0:
                ct_mature[t] += -a
    cut = _cut_ops(tdates)
    net: Dict[str, float] = defaultdict(float)
    for d, v in settle.items():
        if d <= cut:
            net[d] += v
    for d, v in mature.items():
        if d <= cut:
            net[d] += v
    events: Dict[str, float] = defaultdict(float)
    for d, v in ct_settle.items():
        events[d] += v
    for d, v in ct_mature.items():
        events[d] += v
    full = _stock(events, days)
    stock = [(d, v) for d, v in full if d <= cut]
    return {"repo_ct_stock_full": full, "repo_ct_settled": _bucket({d: -v for d, v in ct_settle.items() if d <= cut}), "repo_ct_matured": _bucket({d: -v for d, v in ct_mature.items() if d <= cut}),
            "repo_net_daily": _dense(_bucket(net), [d for d in days if d <= cut]), "repo_maturities_ahead": _bucket({d: v for d, v in mature.items() if d > cut}),
            "repo_ct_stock_daily": stock, "swaps_settled": _bucket({d: v for d, v in swaps.items() if d <= cut}), "ops_cut": [(cut, 1.0)]}


def bills_flows(ops: List[dict], days: List[str]) -> Dict[str, Series]:
    """SNB Bills PLACED, from the gmges rows (type 'SNB Bills'): from (payment) −, to (repayment) +; same monthly cut as the repos.
    The register (snbbillshreg) lists issued lines INCLUDING the SNB's own holdings (verified 2026-08-31: register 201 897 vs
    balance-sheet ES 81 901), so it is used only for the SHAPE of the calendar ahead (bills_calendar), never for amounts."""
    pay: Dict[str, float] = defaultdict(float)
    rep: Dict[str, float] = defaultdict(float)
    tdates = []
    for o in ops:
        a = _num(o.get("allocation"))
        f, t, td = _iso(o.get("from")), _iso(o.get("to")), _iso(o.get("date"))
        if a is None or not f or not td or not str(o.get("type", "")).lower().startswith("snb bills"):
            continue
        tdates.append(td)
        pay[f] += a
        if t:
            rep[t] += a
    cut = _cut_ops([_iso(o.get("from")) for o in ops if _iso(o.get("from"))])  # the file's cut, not the bills' (a month without bills is still covered)
    net: Dict[str, float] = defaultdict(float)
    for d, v in pay.items():
        if d <= cut:
            net[d] -= v
    for d, v in rep.items():
        if d <= cut:
            net[d] += v
    events: Dict[str, float] = defaultdict(float)
    for d, v in pay.items():
        events[d] += v
    for d, v in rep.items():
        events[d] -= v
    return {"bills_issued": _bucket({d: -v for d, v in pay.items() if d <= cut}), "bills_repaid": _bucket({d: v for d, v in rep.items() if d <= cut}),
            "bills_net_daily": _dense(_bucket(net), [d for d in days if d <= cut]), "bills_repayments_ahead_gmges": _bucket({d: v for d, v in rep.items() if d > cut}),
            "bills_stock_daily": [(d, v) for d, v in _stock(events, days) if d <= cut], "bills_stock_full": _stock(events, days), "bills_cut": [(cut, 1.0)]}


def bills_calendar(register: List[dict], es_level: Optional[float], horizon_days: int = 60) -> Dict[str, Series]:
    """repayments ahead from the register shape scaled to the balance-sheet stock ES (the register includes SNB own holdings)"""
    tot = sum(_num(r.get("outstanding_m", r.get("outstanding"))) or 0.0 for r in register)
    if not tot or es_level is None:
        return {"bills_repayments_ahead": [], "register_minus_es": []}
    today = date.today()
    lim = (today + timedelta(days=horizon_days)).isoformat()
    rep: Dict[str, float] = defaultdict(float)
    for r in register:
        a = _num(r.get("outstanding_m", r.get("outstanding")))
        q = _iso(r.get("repayment"))
        if a and q and today.isoformat() < q <= lim:
            rep[q] += a * es_level / tot
    return {"bills_repayments_ahead": _bucket(rep), "register_minus_es": [(today.isoformat(), round(tot - es_level, 1))]}


def absorption_stock(bills_stock: Series, repo_stock: Series) -> Series:
    rs = dict(repo_stock)
    return [(d, round(v + rs.get(d, 0.0), 3)) for d, v in bills_stock]


def reconcile_month_end(stock_daily: Series, month_end_ref: Series) -> Series:
    """daily stock on the reference's month-end date − reference (snbbipo ES / VRGSF): CHF m"""
    s = dict(stock_daily)
    out = []
    for d, v in month_end_ref:
        cand = [x for x in s if x <= d]
        if cand:
            out.append((d, round(s[max(cand)] - v, 3)))
    return clean(out)


# ───────────────────────── Confederation: MMDRC + bonds by settlement, redemptions and coupons from the outstanding list ─────────────────────────
def _field(rec: dict, prefix: str):
    return next((v for h, v in rec.items() if str(h).startswith(prefix)), None)


def mmdrc_flows(recs: List[dict], days: List[str]) -> Dict[str, Series]:
    iss: Dict[str, float] = defaultdict(float)
    mat: Dict[str, float] = defaultdict(float)
    ahead_dates = []
    for r in recs:
        s, m = _iso(r.get("settlement")), _iso(r.get("maturity"))
        a = _num(_field(r, "amount of issue"))
        if not s:
            continue
        if a is None:
            ahead_dates.append(s)  # announced auction: no amount yet
            continue
        iss[s] += a
        if m:
            mat[m] += a
    today = date.today().isoformat()
    net: Dict[str, float] = defaultdict(float)
    for d, v in iss.items():
        if d <= today:
            net[d] -= v
    for d, v in mat.items():
        if d <= today:
            net[d] += v
    return {"mmdrc_settled": _bucket({d: -v for d, v in iss.items() if d <= today}), "mmdrc_matured": _bucket({d: v for d, v in mat.items() if d <= today}),
            "mmdrc_net_daily": _dense(_bucket(net), days), "mmdrc_maturities_ahead": _bucket({d: v for d, v in mat.items() if d > today}),
            "mmdrc_settlements_announced": clean(sorted((d, 0.0) for d in set(ahead_dates) if d > today)),
            "mmdrc_stock_daily": _stock_from(iss, mat, days)}


def _stock_from(plus: Dict[str, float], minus: Dict[str, float], days: List[str]) -> Series:
    ev: Dict[str, float] = defaultdict(float)
    for d, v in plus.items():
        ev[d] += v
    for d, v in minus.items():
        ev[d] -= v
    return _stock(ev, days)


def bond_flows(recs: List[dict], days: List[str]) -> Dict[str, Series]:
    """market amount (excl. own tranches not placed) at settlement −"""
    iss: Dict[str, float] = defaultdict(float)
    own: Dict[str, float] = defaultdict(float)
    for r in recs:
        s = _iso(r.get("settlement"))
        a = _num(_field(r, "amount of issue"))
        if not s or a is None:
            continue
        iss[s] += a
        own[s] += _num(_field(r, "additional own holdings")) or 0.0
    today = date.today().isoformat()
    return {"bond_settled": _bucket({d: -v for d, v in iss.items() if d <= today}), "bond_settlements_ahead": _bucket({d: v for d, v in iss.items() if d > today}),
            "bond_own_retained": _bucket({d: v for d, v in own.items() if d <= today})}


def bond_calendar(outstanding: List[dict], horizon_days: int = 365, back_days: int = 400) -> Dict[str, Series]:
    """redemptions (placed on the market) and annual coupons on the maturity day-of-year × placed on the market × coupon"""
    today = date.today()
    end = (today + timedelta(days=horizon_days)).isoformat()
    start = (today - timedelta(days=back_days)).isoformat()
    red: Dict[str, float] = defaultdict(float)
    cpn: Dict[str, float] = defaultdict(float)
    for b in outstanding:
        m = _iso(b.get("maturity"))
        mk = _num(b.get("placed_market"))
        c = _num(b.get("coupon"))
        if not m or mk is None:
            continue
        if today.isoformat() < m <= end:
            red[m] += mk
        if c:
            for yy in range(int(start[:4]), int(end[:4]) + 1):
                try:
                    d = date(yy, int(m[5:7]), int(m[8:10])).isoformat()
                except ValueError:
                    continue
                if start <= d <= end and d <= m:
                    cpn[d] += mk * c
    tday = today.isoformat()
    return {"bond_redemptions_market_ahead": _bucket(red), "coupons_market_paid": _bucket({d: v for d, v in cpn.items() if d <= tday}),
            "coupons_market_ahead": _bucket({d: v for d, v in cpn.items() if d > tday})}


def net_issuance_private(mm: Dict[str, Series], bf: Dict[str, Series], cal: Dict[str, Series], days: List[str]) -> Series:
    """− MMDRC settled − bonds settled + MMDRC matured + market coupons (bond redemptions: calendar; they enter when the line leaves the list)"""
    m: Dict[str, float] = defaultdict(float)
    for ser in (mm["mmdrc_settled"], mm["mmdrc_matured"], bf["bond_settled"], cal["coupons_market_paid"]):
        for d, v in ser:
            m[d] += v
    return _dense(_bucket(m), days)


# ───────────────────────── weekly aggregation on the sight-deposit grid, intervention proxy ─────────────────────────
def weekly_on(daily: Series, grid: List[str]) -> Series:
    """Σ daily over (previous grid date, grid date]"""
    if not grid:
        return []
    out = []
    prev = None
    dd = clean(daily)
    for g in grid:
        if prev is None:
            prev = g
            continue
        out.append((g, round(sum(v for d, v in dd if prev < d <= g), 3)))
        prev = g
    return out


def intervention_proxy(gi_weekly: Series, ops_net_daily: Series, confed_net_daily: Series, ops_cut: str) -> Dict[str, Series]:
    """ΔGI − Σ SNB ops − Σ Confederation over the week; only weeks fully covered by the gmges file (≤ ops_cut) are 'complete'"""
    gi = clean(gi_weekly)
    grid = [d for d, _ in gi]
    dgi = [(gi[i][0], round(gi[i][1] - gi[i - 1][1], 3)) for i in range(1, len(gi))]
    ops_w = dict(weekly_on(ops_net_daily, grid))
    cf_w = dict(weekly_on(confed_net_daily, grid))
    out, partial = [], []
    for d, v in dgi:
        r = round(v - ops_w.get(d, 0.0) - cf_w.get(d, 0.0), 3)
        (out if d <= ops_cut else partial).append((d, r))
    return {"proxy_weekly": clean(out), "proxy_weekly_partial": clean(partial), "ops_weekly": clean(list(ops_w.items())), "confed_weekly": clean(list(cf_w.items()))}


# ───────────────────────── EFV bonds outstanding (xlsx) ─────────────────────────
def parse_outstanding_xlsx(blob: bytes) -> Tuple[List[dict], Optional[str]]:
    from .providers_chf import xlsx_sheets, _rows_of
    sheets = xlsx_sheets(blob)
    cells = next(iter(sheets.values()))
    rows = _rows_of(cells)
    hdr = next((r for r in sorted(rows) if str(rows[r].get("A", "")).strip() == "ISIN" and str(rows[r].get("B", "")).strip() == "Bond"), None)
    if hdr is None:
        raise ValueError("ausstehende-anleihen: English header row not found (STRUCTURE CHANGE)")
    out, asof = [], None
    for r in sorted(rows):
        row = rows[r]
        a = str(row.get("A", "")).strip()
        mm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", a)
        if a.lower().startswith("stand per") and mm:
            asof = "%s-%s-%s" % (mm.group(3), mm.group(2), mm.group(1))
        if r <= hdr or not re.match(r"^CH\d{10}$", a):
            continue
        out.append({"isin": a, "bond": str(row.get("B", "")).strip(), "maturity": _serial(row.get("C")), "coupon": _num(row.get("D")),
                    "issued_total": _num(row.get("E")), "placed_market": _num(row.get("F")), "own_placed": _num(row.get("G")), "own_available": _num(row.get("H"))})
    return out, asof


def read_outstanding_csv(path: str) -> Tuple[List[dict], Optional[str]]:
    rows = _read_rows(path)
    asof = rows[0].get("asof") if rows else None
    return rows, asof


def write_outstanding_csv(path: str, rows: List[dict], asof: Optional[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = ["isin", "bond", "maturity", "coupon", "issued_total", "placed_market", "own_placed", "own_available", "asof"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(dict({k: r.get(k, "") for k in cols}, asof=asof or ""))


def efv_records_from_cells(cells_by_sheet: Dict[str, dict], min_year: int = 2019) -> List[dict]:
    from .providers_chf import EfvAuctionsProvider
    recs: List[dict] = []
    for name, cells in cells_by_sheet.items():
        if re.match(r"^20\d\d$", name.strip()) and int(name) >= min_year:
            recs += EfvAuctionsProvider._table(cells)
    return recs
