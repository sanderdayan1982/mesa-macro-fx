"""GBP v0.4 — Bank of England operations at operation level, DMO issuance by settlement, APF calendar, Exchequer residual.

Sources verified 2026-09-10 (VERIFICACIONES_V04.md, ADJUDICACION_METRICAS_GBP.md):
  BoE (XLSX, one row per operation)
    short-term-repo-omos-by-operation.xlsx        Operation date | Term (days) | Maturity date | Total allocated (£mn) | Clearing spread — 202 ops since 2022-10-06
    indexed-long-term-repo-omos-by-operation.xlsx Operation date | Term | Maturity date | Total allocated | bids A/B/C | alloc A/B/C | spreads | scaling — since 2014-02
    contingent-term-repo-operations-results.xlsx  Operation date | Term | Maturity date | Offered | Allocated | Spread
    gilt-sales-time-series.xlsx (APF)             Operation date | Settlement date | ISIN | Bond | offers | allocated proceeds (£mn) | nominal | yields — since 2022-11
    table-for-website.xlsx (APF maturity profile) Gilt | Maturity date | nominal £bn | proceeds £bn | remaining stock — 46 gilts, stock £489bn
  DMO (XML)
    XmlDataReport?reportCode=D1A   gilts in issue at close of business: REDEMPTION_DATE, DIVIDEND_DATES, TOTAL_AMOUNT_IN_ISSUE (£mn), coupon in the name
    XmlDataReport?reportCode=D2.2D T-bill tenders: di(MATURITY_DATE) > dd(TENDER_DATE) > sdd(ISSUE_DATE, SIZE_MILLIONS) > far(COVER, yields)
    XmlDataReport?reportCode=D2.1E gilt issuance history 2018→ (seed): INSTRUMENT_NAME, ISIN_CODE, ACTUAL_DATE (= settlement), ISSUANCE_TYPE,
                                   NOMINAL_ISSUED, ISSUE_CLEAN_PRICE ("N/A" = NLF→DMA collateral), ISSUE_YIELD — element name unverified from the sandbox
    GetDataExport?reportCode=D1C   redeemed gilts since 1981 (BIFF xls, seed): redemption date, gilt name, nominal outstanding at redemption (£mn)
  IADB weekly (already wired): reserves RPWB56A, STR RPWB67A, LTR RPWB69A, APF loan RPWZ4TM, notes RPWB55A, TFSME RPWZOQ4, W&M RPWB72A

Reserve mechanics (+ = reserves created):
  STR / ILTR / CTRF allocated at the operation date → +; maturity → −  (settlement convention: operation day; verify T+1 for ILTR)
  APF gilt sale settled → − (proceeds); APF-held gilt redeemed → 0 on reserves (HMT pays the BoE), private-held redemption → +
  Gilt issuance (Δ amount in issue from the daily D1A archive) → −; T-bill issue → −; T-bill maturity → +; coupons to private holders → +
  Exchequer residual (weekly identity): ΔReserves − ΔSTR − ΔLTR − ΔAPF loan − ΔTFSME − ΔW&M + ΔNotes = Exchequer + unobserved clients (foreign CBs, CCPs)
Nothing here decides a regime: every series is published; candidate components go to signals.components_v04 (shadow) until the replay."""
from __future__ import annotations
import csv
import io
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from .series import Series, clean

Row = Dict[str, str]

BOE_FILES = {
    "str": "https://www.bankofengland.co.uk/-/media/boe/files/markets/other-market-operations/short-term-repo-omos-by-operation.xlsx",
    "iltr": "https://www.bankofengland.co.uk/-/media/boe/files/markets/sterling-monetary-framework/indexed-long-term-repo-omos-by-operation.xlsx",
    "ctrf": "https://www.bankofengland.co.uk/-/media/boe/files/markets/sterling-monetary-framework/contingent-term-repo-operations-results.xlsx",
    "apf_sales": "https://www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/gilt-sales-time-series.xlsx",
    "apf_profile": "https://www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/table-for-website.xlsx",
}
DMO_D1A = "https://www.dmo.gov.uk/data/XmlDataReport?reportCode=D1A"
DMO_D22D = "https://www.dmo.gov.uk/data/XmlDataReport?reportCode=D2.2D"
DMO_D21E = "https://www.dmo.gov.uk/data/XmlDataReport?reportCode=D2.1E"  # gilt issuance history by ISIN and settlement (2018→)
DMO_D1C = "https://www.dmo.gov.uk/umbraco/surface/DataExport/GetDataExport?reportCode=D1C&exportFormatValue=xls"  # redeemed gilts (BIFF xls)
# the seed sources live in fixtures/gbp_hist (single copy); the GBP fixture dir is fixtures/gbp, hence the relative reference
FIXTURES = {"str": "boe_str_by_operation.csv", "iltr": "boe_iltr_by_operation.csv", "ctrf": "boe_ctrf_by_operation.csv",
            "apf_sales": "boe_apf_gilt_sales.csv", "apf_profile": "boe_apf_maturity_profile.csv",
            "d1a": "dmo_gilts_in_issue_D1A.csv", "d22d": "dmo_tbill_tenders_D22D.csv",
            "d21e": os.path.join("..", "gbp_hist", "dmo_gilt_issuance_history_D21E_2018.csv"),
            "d1c": os.path.join("..", "gbp_hist", "dmo_redeemed_gilts_D1C.xls")}
SEED_START = "2019-01-01"  # first date of the seed (ADJUDICACION_GBP_EMISION.md, "Diseño del seed GBP")


# ───────────────────────── helpers ─────────────────────────
def _num(v) -> Optional[float]:
    try:
        if v in (None, "", "-", "N/A", "Unlimited"):
            return None
        return float(str(v).replace(",", ""))
    except ValueError:
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
    fm = defaultdict(float)
    for d, v in flows:
        fm[d] += v
    return [(d, round(fm.get(d, 0.0), 3)) for d in days]


def _stock(flows: Series, days: List[str]) -> Series:
    fm = defaultdict(float)
    for d, v in flows:
        fm[d] += v
    acc = sum(v for d, v in fm.items() if days and d < days[0])
    out = []
    for d in days:
        acc += fm.get(d, 0.0)
        out.append((d, round(acc, 3)))
    return out


def rows_from_csv(text: str) -> List[Row]:
    return [dict(r) for r in csv.DictReader(io.StringIO(text))]


# ───────────────────────── BoE XLSX → rows ─────────────────────────
def _header_map(rows: Dict[int, Dict[str, object]], wanted: Dict[str, str]) -> Dict[str, str]:
    """{field: column letter} from the first row whose text cells contain the wanted header fragments (case-insensitive)."""
    if not wanted:
        return {}
    for r in sorted(rows)[:15]:
        found: Dict[str, str] = {}
        for col, val in rows[r].items():
            if isinstance(val, str):
                low = val.lower()
                for frag, field in wanted.items():
                    if frag in low and field not in found:
                        found[field] = col
        if len(found) >= max(2, len(wanted) // 2):
            return found
    return {}


def parse_boe_xlsx(blob: bytes, kind: str) -> List[Row]:
    """Normalises the five BoE workbooks to the fixture column names (dates ISO, £mn)."""
    from .providers_chf import xlsx_sheets, _rows_of
    sheets = xlsx_sheets(blob)
    # the APF maturity-profile workbook opens with a chartsheet (no cells): take the sheet that actually carries the table
    cells = max(sheets.values(), key=len) if sheets else {}
    rows = _rows_of(cells)
    out: List[Row] = []
    # the APF workbooks do not start in column A (gilt sales: B..N; a header row names the columns) → map by header text,
    # falling back to the fixed layout verified 2026-09-10 when no header is found
    hdr = _header_map(rows, {"apf_sales": {"operation date": "op", "settlement date": "settle", "isin": "isin", "bond": "bond", "offers received": "offers",
                                           "allocation (proceeds": "alloc_p", "allocation (nominal": "alloc_n", "accepted yield": "yld", "accepted price": "prc"},
                             "apf_profile": {"gilt": "gilt", "maturity date": "md", "nominal": "nom", "proceeds": "proc", "remaining stock": "rem"}}.get(kind, {}))
    for r in sorted(rows):
        c = rows[r]
        if kind == "apf_sales" and hdr:
            d = _serial(c.get(hdr.get("op", "A")))
            if not d:
                continue
            out.append({"operation_date": d, "settlement_date": _serial(c.get(hdr.get("settle", ""))) or "", "isin": str(c.get(hdr.get("isin", ""), "")), "bond": str(c.get(hdr.get("bond", ""), "")).strip(),
                        "offers_m": str(c.get(hdr.get("offers", ""), "")), "allocated_proceeds_m": str(c.get(hdr.get("alloc_p", ""), "")), "allocated_nominal_m": str(c.get(hdr.get("alloc_n", ""), "")),
                        "wa_yield": str(c.get(hdr.get("yld", ""), "")), "wa_price": str(c.get(hdr.get("prc", ""), ""))})
            continue
        if kind == "apf_profile" and hdr:
            a, md = c.get(hdr.get("gilt", "A")), _serial(c.get(hdr.get("md", "B")))
            if not md or not isinstance(a, str):
                continue
            out.append({"gilt": a.strip(), "maturity_date": md, "nominal_bn": str(c.get(hdr.get("nom", ""), "")), "proceeds_bn": str(c.get(hdr.get("proc", ""), "")), "remaining_stock_bn": str(c.get(hdr.get("rem", ""), ""))})
            continue
        a = c.get("A")
        d = _serial(a)
        if kind in ("str", "iltr", "ctrf"):
            if not d:
                continue
            base = {"operation_date": d, "term": str(c.get("B", "")), "maturity_date": _serial(c.get("C")) or ""}
            if kind == "str":
                base.update({"term_days": str(c.get("B", "")), "allocated_m": str(c.get("D", "")), "clearing_spread_bp": str(c.get("E", ""))})
            elif kind == "ctrf":
                base.update({"offered_m": str(c.get("D", "")), "allocated_m": str(c.get("E", "")), "clearing_spread_bp": str(c.get("F", ""))})
            else:
                base.update({"allocated_m": str(c.get("D", "")), "bids_a": str(c.get("E", "")), "bids_b": str(c.get("F", "")), "bids_c": str(c.get("G", "")),
                             "alloc_a": str(c.get("H", "")), "alloc_b": str(c.get("I", "")), "alloc_c": str(c.get("J", "")),
                             "spread_a": str(c.get("K", "")), "spread_b": str(c.get("L", "")), "spread_c": str(c.get("M", ""))})
            out.append(base)
        elif kind == "apf_sales":
            if not d:
                continue
            out.append({"operation_date": d, "settlement_date": _serial(c.get("B")) or "", "isin": str(c.get("C", "")), "bond": str(c.get("D", "")),
                        "offers_m": str(c.get("E", "")), "allocated_proceeds_m": str(c.get("F", "")), "allocated_nominal_m": str(c.get("G", "")),
                        "wa_yield": str(c.get("H", "")), "wa_price": str(c.get("I", ""))})
        elif kind == "apf_profile":
            md = _serial(c.get("B"))
            if not md or not isinstance(a, str):
                continue
            out.append({"gilt": a.strip(), "maturity_date": md, "nominal_bn": str(c.get("C", "")), "proceeds_bn": str(c.get("D", "")), "remaining_stock_bn": str(c.get("E", ""))})
    return out


# ───────────────────────── DMO XML → rows ─────────────────────────
def parse_d1a_xml(text: str) -> List[Row]:
    root = ET.fromstring(text.strip())
    out: List[Row] = []
    for e in root.iter():
        if e.tag != "View_GILTS_IN_ISSUE":
            continue
        g = e.attrib
        out.append({"date": (g.get("CLOSE_OF_BUSINESS_DATE") or "")[:10], "type": (g.get("INSTRUMENT_TYPE") or "").strip(),
                    "name": (g.get("INSTRUMENT_NAME") or "").strip(), "isin": g.get("ISIN_CODE", ""),
                    "redemption_date": (g.get("REDEMPTION_DATE") or "")[:10], "first_issue_date": (g.get("FIRST_ISSUE_DATE") or "")[:10],
                    "dividend_dates": g.get("DIVIDEND_DATES", ""), "ex_div_date": (g.get("CURRENT_EX_DIV_DATE") or "")[:10],
                    "amount_in_issue_m": g.get("TOTAL_AMOUNT_IN_ISSUE", ""), "amount_incl_uplift_m": g.get("TOTAL_AMOUNT_INCLUDING_IL_UPLIFT", "")})
    return out


def parse_d22d_xml(text: str) -> List[Row]:
    root = ET.fromstring(text.strip())
    out: List[Row] = []
    for di in root.iter("di"):
        mt, md = di.get("TBILL_MATURITY_TYPE", ""), (di.get("MATURITY_DATE") or "")[:10]
        for dd in di.iter("dd"):
            td = (dd.get("TENDER_DATE") or "")[:10]
            for sdd in dd.iter("sdd"):
                far = sdd.find("far")
                out.append({"tender_date": td, "maturity_type": mt, "maturity_date": md, "issue_date": (sdd.get("ISSUE_DATE") or "")[:10],
                            "size_m": sdd.get("SIZE_MILLIONS", ""), "cover": far.get("COVER", "") if far is not None else "",
                            "avg_yield": far.get("AVERAGE_YIELD_PERCENT", "") if far is not None else "", "tail_bp": far.get("YIELD_TAIL_BP", "") if far is not None else ""})
    return out


def parse_d21e_xml(text: str) -> List[Row]:
    """D2.1E gilt issuance history → the fixture columns (settlement, isin, type, nominal_m, clean_price, yield, name).
    Element name unverified from the sandbox (the DMO is unreachable here): any element carrying ISIN_CODE + ACTUAL_DATE is a row.
    ACTUAL_DATE is the settlement date for every ISSUANCE_TYPE, syndications included (pr080926: priced 8-Sep, settled 9-Sep)."""
    root = ET.fromstring(text.strip())
    out: List[Row] = []
    for e in root.iter():
        g = e.attrib
        if "ISIN_CODE" not in g or "ACTUAL_DATE" not in g:
            continue
        out.append({"settlement": (g.get("ACTUAL_DATE") or "")[:10], "isin": (g.get("ISIN_CODE") or "").strip(), "type": (g.get("ISSUANCE_TYPE") or "").strip(),
                    "nominal_m": g.get("NOMINAL_ISSUED", ""), "clean_price": g.get("ISSUE_CLEAN_PRICE", "N/A") or "N/A", "yield": g.get("ISSUE_YIELD", "N/A") or "N/A",
                    "name": (g.get("INSTRUMENT_NAME") or "").strip()})
    return out


def parse_d1c_xls(blob: bytes) -> List[Row]:
    """D1C redeemed gilts (BIFF xls via xlrd, already in requirements): rows after the 'Redemption Date' header →
    redemption_date (ISO), name, nominal_m (nominal outstanding at redemption, £mn; index-linked = nominal, NOT the uplifted value)."""
    import xlrd
    sh = xlrd.open_workbook(file_contents=blob).sheet_by_index(0)
    out: List[Row] = []
    started = False
    for i in range(sh.nrows):
        c = sh.row(i)
        if not started:
            started = isinstance(c[0].value, str) and c[0].value.strip().lower().startswith("redemption date")
            continue
        d, n = _serial(c[0].value), _num(c[2].value)
        if d and isinstance(c[1].value, str) and n is not None:
            out.append({"redemption_date": d, "name": c[1].value.strip(), "nominal_m": str(n)})
    return out


# ───────────────────────── BoE operations → flows ─────────────────────────
def op_flows(rows: List[Row], settle: str, mature: str, amount: str, sign: float = 1.0) -> Dict[str, Series]:
    """Flows are cut at min(today, last operation in the file): a maturity dated after the last published operation belongs to a
    day the file does not cover yet (the BoE posts the new operation the same afternoon), so it stays in the calendar."""
    inj: Dict[str, float] = defaultdict(float)
    dr: Dict[str, float] = defaultdict(float)
    last_op = ""
    for r in rows:
        a = _num(r.get(amount))
        s, m = _iso(r.get(settle)), _iso(r.get(mature))
        if a is None or not s:
            continue
        last_op = max(last_op, s)
        inj[s] += sign * a
        if m:
            dr[m] += -sign * a
    today = date.today().isoformat()
    if last_op and (date.today() - date.fromisoformat(last_op)).days <= 45:
        today = min(today, last_op)  # active facility: cut at the last published operation
    ahead = {d: v for d, v in dr.items() if d > today}
    inj = {d: v for d, v in inj.items() if d <= today}
    dr = {d: v for d, v in dr.items() if d <= today}
    net: Dict[str, float] = defaultdict(float)
    for d, v in inj.items():
        net[d] += v
    for d, v in dr.items():
        net[d] += v
    return {"settled": _bucket(inj), "matured": _bucket(dr), "net": _bucket(net), "ahead": _bucket(ahead)}


def repo_series(str_rows: List[Row], iltr_rows: List[Row], ctrf_rows: List[Row], days: List[str]) -> Dict[str, Series]:
    s = op_flows(str_rows, "operation_date", "maturity_date", "allocated_m")
    i = op_flows(iltr_rows, "operation_date", "maturity_date", "allocated_m")
    c = op_flows(ctrf_rows, "operation_date", "maturity_date", "allocated_m")
    net: Dict[str, float] = defaultdict(float)
    for f in (s, i, c):
        for d, v in f["net"]:
            net[d] += v
    ahead: Dict[str, float] = defaultdict(float)
    for f in (s, i, c):
        for d, v in f["ahead"]:
            ahead[d] += v
    out = {"str_settled": s["settled"], "str_matured": s["matured"], "str_net_daily": s["net"], "str_outstanding_ops": _stock(s["net"], days),
           "iltr_settled": i["settled"], "iltr_matured": i["matured"], "iltr_net_daily": i["net"], "iltr_outstanding_ops": _stock(i["net"], days),
           "ctrf_net_daily": c["net"], "repo_net_daily": _bucket(net), "repo_maturities_ahead": _bucket(ahead)}
    # ILTR demand: total bids vs allocated (cover) per operation
    cov = []
    for r in iltr_rows:
        d = _iso(r.get("operation_date"))
        a = _num(r.get("allocated_m"))
        b = sum(x for x in (_num(r.get("bids_a")), _num(r.get("bids_b")), _num(r.get("bids_c"))) if x is not None)
        if d and a and b:
            cov.append((d, round(b / a, 3)))
    out["iltr_cover"] = clean(cov)
    return out


def apf_series(sales_rows: List[Row], profile_rows: List[Row]) -> Dict[str, Series]:
    """APF sales (proceeds, − reserves at settlement) and the redemption calendar of the APF stock (nominal £mn, by gilt)."""
    sold: Dict[str, float] = defaultdict(float)
    for r in sales_rows:
        d, p = _iso(r.get("settlement_date")), _num(r.get("allocated_proceeds_m"))
        if d and p:
            sold[d] += -p
    red: Dict[str, float] = defaultdict(float)
    for r in profile_rows:
        d, n = _iso(r.get("maturity_date")), _num(r.get("nominal_bn"))
        if d and n:
            red[d] += n * 1000.0
    today = date.today().isoformat()
    return {"apf_sales_daily": _bucket({d: v for d, v in sold.items() if d <= today}),
            "apf_redemptions_ahead": _bucket({d: v for d, v in red.items() if d > today})}


def apf_holdings_by_name(profile_rows: List[Row]) -> Dict[str, float]:
    """{normalised gilt name: APF nominal £mn} for the private-share split of redemptions and coupons"""
    out: Dict[str, float] = {}
    for r in profile_rows:
        n = _num(r.get("nominal_bn"))
        if n is not None:
            out[_norm_name(r.get("gilt", ""))] = n * 1000.0
    return out


# ───────────────────────── DMO gilts in issue → issuance, redemptions, coupons ─────────────────────────
_FRAC = {"¼": 0.25, "½": 0.5, "¾": 0.75, "1/8": 0.125, "3/8": 0.375, "5/8": 0.625, "7/8": 0.875}


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip().lower().replace("¼ %", "¼%")


def coupon_from_name(name: str) -> Optional[float]:
    """'0 3/8% Treasury Gilt 2026' → 0.375; '4¼% Treasury Stock 2032' → 4.25; '1 5/8% …' → 1.625"""
    m = re.match(r"^\s*(\d+)?\s*(¼|½|¾|1/8|3/8|5/8|7/8)?\s*%", name.strip())
    if not m:
        return None
    whole = float(m.group(1)) if m.group(1) else 0.0
    frac = _FRAC.get(m.group(2) or "", 0.0)
    return whole + frac


_MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def dividend_dates(spec: str, start: str, end: str) -> List[str]:
    """'22 Apr/Oct' → every 22 Apr and 22 Oct in [start, end]"""
    m = re.match(r"^\s*(\d{1,2})\s+([A-Za-z]{3})/([A-Za-z]{3})", spec or "")
    if not m:
        return []
    day = int(m.group(1))
    months = [_MON.get(m.group(2).title()), _MON.get(m.group(3).title())]
    y0, y1 = int(start[:4]), int(end[:4])
    out = []
    for y in range(y0, y1 + 1):
        for mo in months:
            if not mo:
                continue
            try:
                d = date(y, mo, day).isoformat()
            except ValueError:
                continue
            if start <= d <= end:
                out.append(d)
    return sorted(out)


def read_d1a_archive(path: str) -> Dict[str, Dict[str, float]]:
    """{date: {isin: amount_in_issue_m}} from the append-only archive"""
    out: Dict[str, Dict[str, float]] = defaultdict(dict)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                v = _num(r.get("amount_in_issue_m"))
                if v is not None:
                    out[r["date"]][r["isin"]] = v
    return out


def append_d1a_archive(path: str, rows: List[Row]) -> Dict[str, Dict[str, float]]:
    arch = read_d1a_archive(path)
    for r in rows:
        v = _num(r.get("amount_in_issue_m"))
        if r.get("date") and r.get("isin") and v is not None:
            arch[r["date"]][r["isin"]] = v
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "isin", "amount_in_issue_m"])
        for d in sorted(arch):
            for isin in sorted(arch[d]):
                w.writerow([d, isin, arch[d][isin]])
    return arch


def issuance_from_archive(arch: Dict[str, Dict[str, float]], redemption_by_isin: Dict[str, str], apf_by_isin: Dict[str, float],
                          first_issue_by_isin: Optional[Dict[str, str]] = None) -> Dict[str, Series]:
    """Δ amount in issue between consecutive close-of-business snapshots = gross gilt issuance (auctions, syndications, tenders, PAOF)
    on the settlement day (the DMO updates the amount in issue on settlement). A gilt that disappears on its redemption date = redemption;
    private-held part = amount − APF nominal (APF-held redemptions are HMT ↔ BoE)."""
    dates = sorted(arch)
    iss: Dict[str, float] = defaultdict(float)
    red_private: Dict[str, float] = defaultdict(float)
    red_apf: Dict[str, float] = defaultdict(float)
    for prev, cur in zip(dates, dates[1:]):
        a, b = arch[prev], arch[cur]
        for isin, v in b.items():
            if isin not in a:
                # a gilt absent from the previous snapshot is issuance only if it was first issued after that snapshot;
                # otherwise the earlier snapshot was incomplete and counting it would fabricate a flow
                fi = (first_issue_by_isin or {}).get(isin, "")
                if fi and fi > prev:
                    iss[cur] += v
                continue
            dv = v - a[isin]
            if dv > 0.5:
                iss[cur] += dv
        for isin, v in a.items():
            if isin not in b:
                rd = redemption_by_isin.get(isin, cur)
                apf = min(v, apf_by_isin.get(isin, 0.0))
                red_private[rd] += v - apf
                red_apf[rd] += apf
    return {"gilt_issued_daily": _bucket(iss), "gilt_redeemed_private": _bucket(red_private), "gilt_redeemed_apf": _bucket(red_apf)}


def gilt_calendar(d1a_rows: List[Row], apf_by_name: Dict[str, float], horizon_days: int = 365) -> Dict[str, Series]:
    """Forward calendar from the current D1A snapshot: private-held redemptions and private coupons by date (£mn)."""
    today = date.today().isoformat()
    end = (date.today() + timedelta(days=horizon_days)).isoformat()
    red: Dict[str, float] = defaultdict(float)
    cpn: Dict[str, float] = defaultdict(float)
    cpn_apf: Dict[str, float] = defaultdict(float)
    for r in d1a_rows:
        amt = _num(r.get("amount_in_issue_m"))
        upl = _num(r.get("amount_incl_uplift_m")) or amt
        if amt is None:
            continue
        apf = min(amt, apf_by_name.get(_norm_name(r.get("name", "")), 0.0))
        share_priv = (amt - apf) / amt if amt else 1.0
        rd = r.get("redemption_date", "")
        if today < rd <= end:
            red[rd] += (upl if "index" in r.get("type", "").lower() else amt) * share_priv
        c = coupon_from_name(r.get("name", ""))
        if c is None:
            continue
        base = upl if "index" in r.get("type", "").lower() else amt
        for dd in dividend_dates(r.get("dividend_dates", ""), today, end):
            if dd > today:
                cpn[dd] += base * c / 100.0 / 2.0 * share_priv
                cpn_apf[dd] += base * c / 100.0 / 2.0 * (1 - share_priv)
    return {"gilt_redemptions_private_ahead": _bucket(red), "gilt_coupons_private_ahead": _bucket(cpn), "gilt_coupons_apf_ahead": _bucket(cpn_apf)}


def coupons_paid_recent(d1a_rows: List[Row], apf_by_name: Dict[str, float], days_back: int = 60) -> Series:
    """Coupons paid to private holders in the last `days_back` days, estimated from the current snapshot's amounts (the amount in
    issue of a gilt barely changes between a coupon date and today). Labelled as an estimate in the block."""
    today = date.today().isoformat()
    start = (date.today() - timedelta(days=days_back)).isoformat()
    cpn: Dict[str, float] = defaultdict(float)
    for r in d1a_rows:
        amt = _num(r.get("amount_in_issue_m"))
        upl = _num(r.get("amount_incl_uplift_m")) or amt
        c = coupon_from_name(r.get("name", ""))
        if amt is None or c is None:
            continue
        apf = min(amt, apf_by_name.get(_norm_name(r.get("name", "")), 0.0))
        share_priv = (amt - apf) / amt if amt else 1.0
        base = upl if "index" in r.get("type", "").lower() else amt
        for dd in dividend_dates(r.get("dividend_dates", ""), start, today):
            cpn[dd] += base * c / 100.0 / 2.0 * share_priv
    return _bucket(cpn)


def tbill_series(rows: List[Row]) -> Dict[str, Series]:
    iss: Dict[str, float] = defaultdict(float)
    mat: Dict[str, float] = defaultdict(float)
    cov: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        s = _num(r.get("size_m"))
        i, m, t = _iso(r.get("issue_date")), _iso(r.get("maturity_date")), _iso(r.get("tender_date"))
        if s is None or not i:
            continue
        iss[i] += s
        if m:
            mat[m] += s
        c = _num(r.get("cover"))
        if c is not None and t:
            cov[t].append(c)
    today = date.today().isoformat()
    return {"tbill_issued": _bucket({d: v for d, v in iss.items() if d <= today}), "tbill_matured": _bucket({d: v for d, v in mat.items() if d <= today}),
            "tbill_maturities_ahead": _bucket({d: v for d, v in mat.items() if d > today}),
            "tbill_cover": clean(sorted((d, round(sum(v) / len(v), 3)) for d, v in cov.items()))}


def net_issuance_private(gilt_iss: Series, gilt_red_priv: Series, tb_iss: Series, tb_mat: Series, coupons_paid: Series, days: List[str]) -> Series:
    """− gilt issuance − T-bill issuance + private redemptions + T-bill maturities + private coupons paid (daily, dense)"""
    m: Dict[str, float] = defaultdict(float)
    for d, v in gilt_iss:
        m[d] -= v
    for d, v in tb_iss:
        m[d] -= v
    for d, v in gilt_red_priv:
        m[d] += v
    for d, v in tb_mat:
        m[d] += v
    for d, v in coupons_paid:
        m[d] += v
    return _dense(_bucket(m), days)


# ───────────────────────── seed before the D1A archive: D2.1E issuance + D1C redemptions + rule coupons ─────────────────────────
# Design fixed in ADJUDICACION_GBP_EMISION.md ("Diseño del seed GBP"). Cash sign per D2.1E row (reserves, + = injection):
#   Outright / Syndication (any priced type not listed below) → −nominal (issuance drains); nominal, not cash: D2.1E prices are rounded
#   Reverse Auction → +nominal (the DMO buys back for cash)
#   price "N/A" (collateral created NLF→DMA under the cash-management remit: 2018-10-16, 2020-04-21, 2022-04/07/10, 2024-07-16, 2025-04-15 …),
#   Conversion, Switch Auction, Cancellation, Cancellation Adjustment → 0 cash (free of payment / book entries)
# Private outstanding base for coupons: cumulative D2.1E by line EXCLUDING the N/A-price rows (DMA-held, not private; assumed held to
# redemption) — they still count in the official amount in issue (D1C nominal, D1A amount), hence the back-solve below subtracts them.
_NO_CASH_TYPES = ("conversion", "switch", "cancellation")


def _d21e_kind(r: Row) -> str:
    """'issue' (priced sale), 'buyback' (reverse auction), 'collateral' (price N/A), 'cancel', 'exchange' (conversion/switch)"""
    t = (r.get("type") or "").lower()
    if "reverse" in t:
        return "buyback"
    if "cancel" in t:
        return "cancel"
    if any(k in t for k in _NO_CASH_TYPES):
        return "exchange"
    return "collateral" if _num(r.get("clean_price")) is None else "issue"


def next_business_day(d: str) -> str:
    """weekend → following Monday (same calendar as business_days: weekdays only, UK bank holidays not modelled)"""
    x = date.fromisoformat(d)
    while x.weekday() >= 5:
        x += timedelta(days=1)
    return x.isoformat()


def coupon_dates(maturity: str, start: str, end: str) -> List[str]:
    """Semi-annual rule ('About gilts'): the day/month of maturity and six months earlier, next business day if not one; ≤ maturity."""
    import calendar
    m = date.fromisoformat(maturity)
    months = sorted({m.month, (m.month + 6 - 1) % 12 + 1})
    out = []
    for y in range(int(start[:4]), int(end[:4]) + 1):
        for mo in months:
            nominal = date(y, mo, min(m.day, calendar.monthrange(y, mo)[1])).isoformat()
            d = next_business_day(nominal)
            if start <= d <= end and nominal <= maturity[:10]:
                out.append(d)
    return sorted(out)


def seed_flows(d21e_rows: List[Row], d1c_rows: List[Row], first_snapshot: Tuple[str, Dict[str, Tuple[float, str]]], days: List[str]) -> Tuple[Dict[str, Series], Dict[str, int]]:
    """Gilt flows (£mn) on `days` (business days strictly before the first D1A archive snapshot):
      gilt_issued_daily      +priced D2.1E nominal at settlement (a Reverse Auction enters as negative issuance = cash buyback)
      gilt_redeemed_private  D1C nominal outstanding at redemption, GROSS (no APF netting in this phase; index-linked at nominal, not uplift)
      coupons_private_paid   coupon-rule dates × private outstanding at that date × coupon/200; index-linked at real coupon × nominal
                             (the uplifted nominal is not available historically → understated; low confidence, stated)
      net                    −issued + redeemed + coupons, dense on `days` (T-bills are added by the caller from D2.2D)
    Every flow is dated on a business day (weekend dates roll forward) so the caller's dense grid keeps it.
    first_snapshot = (date, {gilt name: (amount in issue, redemption date)}) — the first D1A archive snapshot.
    Pre-2018 outstanding (D2.1E starts 2018-01): a line that redeemed is back-solved from D1C — base = D1C nominal − Σ official D2.1E
    rows of the line (all types, N/A included) up to redemption; a line alive at the snapshot the same way from the snapshot amount.
    Private outstanding(t) = base + Σ private rows settled ≤ t (priced issuance +, buyback/cancellation −, exchanges as given,
    N/A rows excluded). A line with no D1C row and no snapshot amount cannot be based: its coupons are skipped and counted."""
    from collections import Counter
    empty = {"gilt_issued_daily": [], "gilt_redeemed_private": [], "coupons_private_paid": [], "net": []}
    if not days:
        return empty, {}
    start, end = days[0], days[-1]
    snap_date, snap_by_name = first_snapshot
    stats: Dict[str, int] = Counter()
    by_line: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)  # name → [(settlement, nominal, kind)]
    iss: Dict[str, float] = defaultdict(float)
    for r in d21e_rows:
        d, n = _iso(r.get("settlement")), _num(r.get("nominal_m"))
        if not d or n is None:
            continue
        k = _d21e_kind(r)
        stats["d21e_%s" % k] += 1
        by_line[_norm_name(r.get("name", ""))].append((d, n, k))
        if start <= d <= end and k in ("issue", "buyback"):
            iss[next_business_day(d)] += n if k == "issue" else -n
    red: Dict[str, float] = defaultdict(float)
    lines: Dict[str, Tuple[str, float, str]] = {}  # name → (maturity, official nominal, as-of date of that nominal)
    for r in d1c_rows:
        d, n = _iso(r.get("redemption_date")), _num(r.get("nominal_m"))
        if not d or n is None:
            continue
        lines[_norm_name(r.get("name", ""))] = (d, n, d)
        if start <= d <= end:
            red[next_business_day(d)] += n  # a weekend redemption date pays on the next business day (7-Jun-2025 → 9-Jun)
    for name, (amt, rd) in snap_by_name.items():
        lines.setdefault(_norm_name(name), (rd, amt, snap_date))
    official_sign = {"issue": 1.0, "collateral": 1.0, "exchange": 1.0, "buyback": -1.0, "cancel": -1.0}
    private_sign = dict(official_sign, collateral=0.0)
    cpn: Dict[str, float] = defaultdict(float)
    for name, (mat, official, asof) in lines.items():
        c = coupon_from_name(name)
        if not mat or c is None or mat < start:
            continue
        rows = by_line.get(name, [])
        base = official - sum(official_sign[k] * n for d, n, k in rows if d <= asof)
        if base < -1.0:
            stats["negative_base"] += 1
        base = max(base, 0.0)
        for dd in coupon_dates(mat, start, end):
            out = base + sum(private_sign[k] * n for d, n, k in rows if d <= dd)
            if out > 0.5:
                cpn[dd] += out * c / 200.0
    stats["lines_unbased"] = sum(1 for n in by_line if n not in lines)
    stats["lines_based"] = len(lines)
    net: Dict[str, float] = defaultdict(float)
    for d, v in iss.items():
        net[d] -= v
    for d, v in red.items():
        net[d] += v
    for d, v in cpn.items():
        net[d] += v
    return ({"gilt_issued_daily": _bucket(iss), "gilt_redeemed_private": _bucket(red), "coupons_private_paid": _bucket(cpn), "net": _dense(_bucket(net), days)}, dict(stats))


def splice(before: Series, after: Series, cut: str) -> Series:
    """`before` strictly before `cut`, `after` from `cut` on (the seed never overrides the D1A-archive path)"""
    return clean([(d, v) for d, v in before if d < cut] + [(d, v) for d, v in after if d >= cut])


# ───────────────────────── Exchequer residual (weekly identity on the Weekly Report) ─────────────────────────
def exchequer_residual_weekly(h: Dict[str, Series]) -> Dict[str, Series]:
    """ΔR − ΔSTR − ΔLTR − ΔAPF − ΔTFSME − ΔW&M + ΔNotes on the Wednesday dates of the Weekly Report (£mn).
    h keys: reserves, str, ltr, apf, tfsme, wm, notes."""
    def diff(s: Series) -> Dict[str, float]:
        s = clean(s)
        return {s[i][0]: s[i][1] - s[i - 1][1] for i in range(1, len(s))}
    dR, dS, dL, dA, dT, dW, dN = (diff(h.get(k, [])) for k in ("reserves", "str", "ltr", "apf", "tfsme", "wm", "notes"))
    out = []
    for d in sorted(dR):
        if d in dS and d in dL and d in dA and d in dN:
            out.append((d, round(dR[d] - dS[d] - dL[d] - dA[d] - dT.get(d, 0.0) - dW.get(d, 0.0) + dN[d], 3)))
    res = clean(out)
    cum4 = []
    for i in range(len(res)):
        if i >= 3:
            cum4.append((res[i][0], round(sum(v for _, v in res[i - 3:i + 1]), 3)))
    return {"exchequer_residual_weekly": res, "exchequer_residual_4w": cum4}
