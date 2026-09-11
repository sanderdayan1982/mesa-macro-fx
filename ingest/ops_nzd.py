"""NZD v0.4 — Treasury flows by settlement, OMO calendar, proxy reconciliation and the OIA daily Crown Settlement Account.

Sources (VERIFICACIONES_V04.md, ADJUDICACION_METRICAS_NZD.md):
  NZDM XLSX (already wired: tender histories, bonds on issue by line with market holdings) + new: ECP-onissue-<date>.xlsx (monthly)
  RBNZ D3 per operation (date held, maturity, allocated) — already in the side file; D12 daily settlement cash; D10 monthly cash influence
  NZ Treasury OIA-20250819: oia-20250819-overdraft-facility-csa.xlsx — Crown Settlement Account balance, DAILY, 1997-11-10 → 2025-10-31

Reserve mechanics (+ = settlement cash created):
  Tender settled (bills T+1, bonds T+3 business days unless the tender listing gives the settlement date) → −
  Bill maturity → +; bond maturity: market-held part (bonds on issue: total − RBNZ − EQC − SRESL, month-end before maturity) → +;
  coupons × market nominal (latest month-end ≤ coupon date) → + — both from EVERY month-end of the register (bond_flows_history)
  LSAP sales RBNZ → NZDM (NZ$415m/month): Crown pays the RBNZ from the CSA → NO settlement-cash effect (corrects N2 of the adjudication);
  they matter as the Crown's refinancing need, published as context.
  OMO reverse repo allocated → +; maturity (7/28 d) → − ; full allotment at OCR + 10 bp → allocated = demand.
Reconciliation (N3): Σ monthly residual_flow_daily vs D10 government cash influence; Σ over the OIA overlap (2024-01 → 2025-10) vs −ΔCSA.
Nothing here decides a regime: every series is published; candidate components go to signals.components_v04 (shadow)."""
from __future__ import annotations
import csv
import io
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional
from .series import Series, clean

Row = Dict[str, object]
OIA_CSA_URL = "https://www.treasury.govt.nz/sites/default/files/2026-02/oia-20250819-overdraft-facility-csa.xlsx"


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
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else _serial(s)


def bd_add(d: str, n: int) -> str:
    x = date.fromisoformat(d)
    k = 0
    while k < n:
        x += timedelta(days=1)
        if x.weekday() < 5:
            k += 1
    return x.isoformat()


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
    fm = defaultdict(float)
    for d, v in flows:
        fm[d] += v
    return [(d, round(fm.get(d, 0.0), 3)) for d in days]


# ───────────────────────── NZDM tenders → issuance and bill maturities by settlement ─────────────────────────
SETTLE_BD = {"tbill": 1, "bond": 3}  # verified on the listing: bill tender 2026-09-08 → 09-09; bond tender 2026-09-03 → 09-08


def tender_flows(tender_rows: List[dict], upcoming: Optional[List[dict]] = None) -> Dict[str, Series]:
    iss: Dict[str, float] = defaultdict(float)
    for u in upcoming or []:  # announced tenders: offered volume at the announced settlement date (calendar only)
        v, sd = _num(u.get("volume")), _iso(u.get("settlement"))
        if v and sd and sd > date.today().isoformat():
            iss[sd] += v
    bill_mat: Dict[str, float] = defaultdict(float)
    cov: Dict[str, List[float]] = defaultdict(list)
    for r in tender_rows:
        a = _num(r.get("accepted"))
        td = _iso(r.get("tender_date"))
        if a is None or not td or a <= 0:
            continue
        kind = r.get("kind", "bond")
        s = _iso(r.get("settlement_date")) or bd_add(td, SETTLE_BD.get(kind, 3))
        iss[s] += a
        if kind == "tbill":
            m = _iso(r.get("maturity"))
            if m:
                bill_mat[m] += a
        c = _num(r.get("coverage"))
        if c is not None:
            cov[td].append(c)
    today = date.today().isoformat()
    return {"tender_settled": _bucket({d: v for d, v in iss.items() if d <= today}),
            "tender_settlements_ahead": _bucket({d: v for d, v in iss.items() if d > today}),
            "bill_matured": _bucket({d: v for d, v in bill_mat.items() if d <= today}),
            "bill_maturities_ahead": _bucket({d: v for d, v in bill_mat.items() if d > today}),
            "tender_coverage": clean(sorted((d, round(sum(v) / len(v), 3)) for d, v in cov.items()))}


# ───────────────────────── bonds on issue → market-held redemptions and coupons ─────────────────────────
def bond_calendar(bonds_on_issue: List[dict], horizon_days: int = 365, back_days: int = 60) -> Dict[str, Series]:
    """market-held redemptions and coupons by date (NZ$m). Coupons: semi-annual on the maturity day-of-month,
    in the maturity month and six months earlier (NZGB convention, verified against the D3 coupon-day tags)."""
    today = date.today()
    end = (today + timedelta(days=horizon_days)).isoformat()
    start = (today - timedelta(days=back_days)).isoformat()
    red: Dict[str, float] = defaultdict(float)
    cpn: Dict[str, float] = defaultdict(float)
    lines: Dict[str, dict] = {}
    for b in bonds_on_issue:  # keep the latest month-end per line
        m = b.get("maturity")
        if not m:
            continue
        if m not in lines or str(b.get("month_end", "")) > str(lines[m].get("month_end", "")):
            lines[m] = b
    for m, b in lines.items():
        mk = _num(b.get("market")) or 0.0
        c = _num(b.get("coupon")) or 0.0
        if today.isoformat() < m <= end:
            red[m] += mk
        y, mo, dd = int(m[:4]), int(m[5:7]), int(m[8:10])
        for yy in range(int(start[:4]), int(end[:4]) + 1):
            for mm in (mo, (mo + 5) % 12 + 1):
                try:
                    d = date(yy, mm, dd).isoformat()
                except ValueError:
                    continue
                if start <= d <= end and d <= m:
                    cpn[d] += mk * c / 2.0
    tday = today.isoformat()
    return {"bond_redemptions_market_ahead": _bucket(red),
            "coupons_market_paid": _bucket({d: v for d, v in cpn.items() if d <= tday}),
            "coupons_market_ahead": _bucket({d: v for d, v in cpn.items() if d > tday})}


def _roll_bd(d: str) -> str:
    x = date.fromisoformat(d)
    while x.weekday() >= 5:
        x += timedelta(days=1)
    return x.isoformat()


def bond_flows_history(snapshots: List[dict], days: List[str]) -> dict:
    """market-held bond redemptions and coupons over the window from EVERY month-end snapshot of the NZDM register (NZ$m).
    House convention (as GBP/EUR): both GROSS to the market holder; the NZDM 'market' column (total − RBNZ − EQC − SRESL) is the holder.
      bond_redeemed_market: market holding of the LAST month-end snapshot BEFORE the maturity, on the maturity rolled to the next business day
      coupons_market_paid:  every semi-annual coupon date (maturity day-of-month, maturity month and six months earlier, ≤ maturity),
                            rolled to the next business day, × market nominal of the latest month-end snapshot ≤ the coupon date ÷ 2
    Coverage is honest, not filled: a date with no snapshot at or before it gets nothing (two-sided from the first month-end on file).
    Inflation-indexed lines: nominal without indexation (understates the indexed principal/coupon; low confidence)."""
    if not snapshots or not days:
        return {"bond_redeemed_market": [], "coupons_market_paid": [], "two_sided_from": None}
    by_me: Dict[str, Dict[str, dict]] = defaultdict(dict)
    for b in snapshots:
        me, m = str(b.get("month_end", "")), b.get("maturity")
        if me and m:
            by_me[me][m] = b
    mes = sorted(by_me)
    today = date.today().isoformat()
    start, end = days[0], min(days[-1], today)

    def snap_at(d: str, strict: bool) -> Optional[str]:  # latest month-end < d (strict) or ≤ d
        prev = [me for me in mes if (me < d if strict else me <= d)]
        return prev[-1] if prev else None

    red: Dict[str, float] = defaultdict(float)
    cpn: Dict[str, float] = defaultdict(float)
    lines: Dict[str, dict] = {}
    for me in mes:
        for m, b in by_me[me].items():
            lines[m] = b  # coupon of the line (constant across snapshots)
    for m, b in lines.items():
        pay = _roll_bd(m)
        if start <= pay <= end:
            s = snap_at(m, strict=True)
            if s and m in by_me[s]:
                red[pay] += _num(by_me[s][m].get("market")) or 0.0
        c = _num(b.get("coupon")) or 0.0
        y, mo, dd = int(m[:4]), int(m[5:7]), int(m[8:10])
        for yy in range(int(start[:4]), int(end[:4]) + 1):
            for mm in (mo, (mo + 5) % 12 + 1):
                try:
                    d = date(yy, mm, dd).isoformat()
                except ValueError:
                    continue
                pay = _roll_bd(d)
                if not (start <= pay <= end and d <= m):
                    continue
                s = snap_at(d, strict=False)
                if s and m in by_me[s]:
                    cpn[pay] += (_num(by_me[s][m].get("market")) or 0.0) * c / 2.0
    return {"bond_redeemed_market": _bucket(red), "coupons_market_paid": _bucket(cpn), "two_sided_from": mes[0]}


def net_issuance_private(tender_settled: Series, bill_matured: Series, coupons_paid: Series, days: List[str], bond_redeemed: Optional[Series] = None) -> Series:
    """− tenders settled + bill maturities + market bond redemptions + market coupons (both from bond_flows_history)"""
    m: Dict[str, float] = defaultdict(float)
    for d, v in tender_settled:
        m[d] -= v
    for d, v in bill_matured:
        m[d] += v
    for d, v in bond_redeemed or []:
        m[d] += v
    for d, v in coupons_paid:
        m[d] += v
    return _dense(_bucket(m), days)


# ───────────────────────── RBNZ D3 OMO per operation → settled / matured / calendar ─────────────────────────
def omo_flows(rr_rows: List[dict], days: List[str]) -> Dict[str, Series]:
    inj: Dict[str, float] = defaultdict(float)
    dr: Dict[str, float] = defaultdict(float)
    for r in rr_rows or []:
        a = _num(r.get("allocated"))
        s, m = _iso(r.get("date_held")), _iso(r.get("maturity"))
        if a is None or not s:
            continue
        inj[s] += a
        if m:
            dr[m] += -a
    today = date.today().isoformat()
    last_op = max(inj) if inj else ""
    if last_op and (date.today() - date.fromisoformat(last_op)).days <= 45:
        today = min(today, last_op)  # a maturity after the last published operation belongs to a day D3 does not cover yet
    net: Dict[str, float] = defaultdict(float)
    for d, v in inj.items():
        if d <= today:
            net[d] += v
    for d, v in dr.items():
        if d <= today:
            net[d] += v
    return {"omo_settled_daily": _bucket({d: v for d, v in inj.items() if d <= today}), "omo_matured_daily": _bucket({d: v for d, v in dr.items() if d <= today}),
            "omo_net_daily": _dense(_bucket(net), days), "omo_maturities_ahead": _bucket({d: v for d, v in dr.items() if d > today})}


# ───────────────────────── reconciliations ─────────────────────────
def monthly_sum(daily: Series) -> Series:
    m: Dict[str, float] = defaultdict(float)
    last: Dict[str, str] = {}
    for d, v in daily:
        k = d[:7]
        m[k] += v
        last[k] = max(last.get(k, ""), d)
    return clean(sorted((last[k], round(v, 3)) for k, v in m.items()))


def reconcile_monthly(proxy_daily: Series, monthly_ref: Series, min_days: int = 15) -> Dict[str, Series]:
    """monthly Σ proxy vs a monthly reference (D10 cash influence, or −ΔCSA from the OIA file): error and error as % of |reference|"""
    cnt: Dict[str, int] = defaultdict(int)
    for d, _ in proxy_daily:
        cnt[d[:7]] += 1
    ps = {d[:7]: v for d, v in monthly_sum(proxy_daily) if cnt[d[:7]] >= min_days}
    err, pct = [], []
    for d, v in monthly_ref:
        k = d[:7]
        if k in ps:
            err.append((d, round(ps[k] - v, 3)))
            if abs(v) > 1e-9:
                pct.append((d, round((ps[k] - v) / abs(v) * 100, 2)))
    return {"error": clean(err), "error_pct": clean(pct)}


# ───────────────────────── OIA daily CSA (xlsx → series, NZ$m) ─────────────────────────
def parse_oia_csa_xlsx(blob: bytes) -> Series:
    from .providers_chf import xlsx_sheets, _rows_of
    sheets = xlsx_sheets(blob)
    cells = next(iter(sheets.values()))
    rows = _rows_of(cells)
    out = []
    for r in sorted(rows):
        d = _serial(rows[r].get("A"))
        v = _num(rows[r].get("B"))
        if d and v is not None:
            out.append((d, round(v / 1e6, 3)))
    return clean(out)


def read_csv_series(path: str) -> Series:
    if not os.path.exists(path):
        return []
    return clean([(r[0], float(r[1])) for r in csv.reader(open(path, encoding="utf-8")) if r and r[0] != "date"])


def csa_flow_from_balance(csa: Series) -> Series:
    """−Δ CSA balance = Crown net flow into settlement cash (spending − taxes − net issuance settled that day)"""
    csa = clean(csa)
    return [(csa[i][0], round(-(csa[i][1] - csa[i - 1][1]), 3)) for i in range(1, len(csa))]


# ───────────────────────── ECP on issue (monthly xlsx) ─────────────────────────
def parse_ecp_xlsx(blob: bytes) -> Series:
    from .providers_chf import xlsx_sheets, _rows_of
    sheets = xlsx_sheets(blob)
    cells = next(iter(sheets.values()))
    rows = _rows_of(cells)
    out = []
    for r in sorted(rows):
        d = _serial(rows[r].get("A"))
        v = _num(rows[r].get("B"))
        if d and v is not None:
            out.append((d, round(v, 3)))
    return clean(out)
