"""EUR v0.4 — FR / IT / ES bond lines for ops_eur.bond_redemptions_coupons (GROSS redemptions + coupons), sources verified 2026-09-11.

Line structure (same as ops_eur.de_lines / ops_eu_qlik.eu_lines): {issuer, isin, coupon (% p.a.), maturity, tranches [(value_date, nominal €m)],
coupon_months (12 annual · 6 semi-annual · 3 quarterly)}; outstanding(d) = Σ tranches ≤ d, so a buyback is a negative tranche and a
snapshot-based line (IT) carries its first snapshot at the issue date and the later snapshots as deltas.

FR  AFT auction history XLSX (<yyyy-mm>_hist_mlt.xlsx, sheet MLT, 1999→: 'total amount issued' = served + NCTs per line and settlement date),
    AFT syndication history XLSX (1999-2026_historique_syndications.xlsx, sheet 'syndic': settlement, ISIN, volume issued (+) / bought back (−)),
    AFT Monthly Operations Review PDFs ('Over-the-counter buybacks' block: '<line> <volume>' in €m from 2026, '<line> <amount> €' in 2019) — the
    buyback has no settlement date in the review → dated on the LAST BUSINESS DAY of the review month; the line text is mapped to the ISIN by
    (family, coupon, maturity) from the auction / syndication names (BTAN lines are the same ISINs the 2013 assimilation renamed OAT).
    outstanding(d) = Σ auctions + Σ syndications − Σ buybacks; reconciled against the AFT 'OATs debt outstanding' list (fixture
    aft_encours_oat_<date>.csv, nominal OATs only — OATi/OAT€i are not on that list). Lines created before 1999 (first tranche before 2000)
    are snapped to the list (constant shortfall at the first tranche date, as ops_eur.de_lines does for pre-1999 Bunds); every other mismatch
    is reported, never patched. OATi/OAT€i: real coupon × nominal, no indexation (low confidence).
IT  MEF 'Scadenze suddivise per anno' CSVs (one snapshot per file: 'Aggiornato al …'; ISIN; Tipo titolo; Emissione; Scadenza; Cedola/Spread; Valuta;
    Circolante Euro [(rivalutato); (nominale) from 2024]). The market-held section only (the 'Titoli di Stato per portafoglio REPO' block that
    follows lists the Treasury's own repo tranches and is cut). Number formats: '7.700.000.000,00' (2020, 2022→) and '7,000,000,000.00' (2021);
    dates dd-mmm-yy (2020, Italian months) and dd/mm/yyyy (2021→, a few 2-digit years mis-expanded to 19xx in 2021 → +100 when the maturity
    precedes the snapshot year). Amount = nominale where the column exists, else 'Circolante Euro' (REVALUED for BTP€i / BTP Italia in the
    2020–2023 files, stated). Redemption = outstanding in the snapshot of the maturity year when that file exists (the amount actually
    redeemed), else the last snapshot before maturity. BOT excluded (bills: their maturities enter through the MEF auction records, kind='bill'),
    EMTN / GLOBAL / EUROBOND / Ispa / SURE-NGEU rows excluded (not domestic auction lines). Coupons: BTP / BTP Short / BTP Green / BTP€i / BTP
    Italia / BTP Futura semi-annual on the maturity day-month and six months earlier; BTP Valore / BTP Più quarterly (MEF prospectus: quarterly
    coupons; not re-verified today → low confidence); step-up lines on the FIRST step (understated later years); CCTeu coupons EXCLUDED (the
    field is the spread, no Euribor path invented); CTZ zero.
ES  Tesoro 'Deuda del Estado: financiación neta' 13.xlsx (sheets '<year> importes efectivos', monthly rows; the current months of the current
    year are broken down by day — row label = day number). Gross bond redemptions = AMORTIZACIONES Bonos + Oblig. + 'Bonos y Oblig. Index.'
    (empty in 2025–2026; 'Resto y asumidas' is NOT a bond line and is excluded). Daily rows are dated on the day; monthly rows on the maturity
    dates of the ES bond lines (kind='bond') in the auction records maturing that month, pro-rata to their auctioned nominal, else on the last
    business day of the month (stated in the line source). Coupons ES: NOT derived — the auction records carry no ISIN and miss the syndicated
    first tranches, so no line has a known nominal; the skipped maturities are counted in the notes.
Nothing here decides a regime (shadow components only)."""
from __future__ import annotations
import csv
import io
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from .ops_eur import _num, _iso, _serial, _MON_EN, _MON_FR, _fr_line_maturity

# ─── URLs (verified 2026-09-11 unless stated) ───
AFT_REVIEW_PAGE = "https://www.aft.gouv.fr/en/monthly-operations-review"  # 2024→; archives /en/monthly-operations-review-2019 … -2023
AFT_SYND_XLSX = "https://www.aft.gouv.fr/files/medias-aft/3_Dette/3.2_OATMLT/3.2.1_OAT/Principaux%20chiffres/1999-2026_historique_syndications.xlsx"
MEF_SCADENZE_INDEX = "https://www.dt.mef.gov.it/it/debito_pubblico/dati_statistici/scadenze_titoli_suddivise_anno/index.html?selezione-anno=%d"
MEF_BASE = "https://www.dt.mef.gov.it"
TESORO_13_XLSX = "https://www.tesoro.es/sites/default/files/estadisticas/13.xlsx"

_MON_IT = {m: i for i, m in enumerate(["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"], 1)}
_MON_ES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"], 1)}


def month_end_bd(y: int, m: int) -> str:
    """last business day of the month (weekends only, as ops_eur.roll_bd)"""
    d = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


# ═══════════════════════ FR — AFT ═══════════════════════
def fr_line_key(line: str) -> Optional[Tuple[str, Optional[float], str]]:
    """'OAT€i 3,15% 25 juillet 2032' → ('€i', 3.15, '2032-07-25'); BTAN lines map to the OAT family (same ISINs); TEC10 → coupon None"""
    s = str(line or "").strip()
    m = re.match(r"^(OAT|BTAN)\s*(€i|ei|€I|i|I)?\b", s)
    if not m:
        return None
    fam = {"ei": "€i", "€I": "€i", "I": "i"}.get(m.group(2) or "", m.group(2) or "")
    mat = _fr_line_maturity(s)
    if not mat:
        mm = re.search(r"(\d{2})/(\d{2})/(\d{4})", s)
        mat = "%s-%s-%s" % (mm.group(3), mm.group(2), mm.group(1)) if mm else None
    if not mat:
        mm = re.search(r"(\d{1,2})(?:er|st|nd|rd|th)? ([A-Za-z]+) (\d{4})", s)
        if mm and mm.group(2).lower() in _MON_EN:
            mat = "%s-%02d-%02d" % (mm.group(3), _MON_EN[mm.group(2).lower()], int(mm.group(1)))
    if not mat:
        return None
    c = re.search(r"(\d+(?:[.,]\d+)?)\s*%", s)
    return (fam, float(c.group(1).replace(",", ".")) if c else None, mat)


def fr_parse_syndications(blob: bytes) -> List[dict]:
    """sheet 'syndic': C settlement, F ISIN, G line, L volume issued (+) / bought back (−) €m"""
    from .providers_chf import xlsx_sheets, _rows_of
    rows = _rows_of(next(iter(xlsx_sheets(blob).values())))
    out = []
    for r in sorted(rows):
        row = rows[r]
        s, vol = _serial(row.get("C")) or _iso(row.get("C")), _num(row.get("L"))
        if not s or vol is None or not str(row.get("F", "")).startswith("FR"):
            continue
        out.append({"settlement": s, "isin": str(row["F"]).strip(), "line": str(row.get("G", "")).strip(), "volume": vol})
    return out


def fr_parse_buyback_pdf(text: str, filename: str = "") -> dict:
    """AFT Monthly Operations Review → {'month': 'yyyy-mm', 'date': last business day, 'total': €m or None, 'items': [{line, family, coupon,
    maturity, amount (€m)}], 'bills': €m of BTF buybacks (not lines)}. Both layouts: 2026 'OAT 2,50% 24/09/2027 5,665' (€m) and 2019
    'OAT 3.50% 25 April 2020 1,000,000,000 €' (euros). The month comes from the page-1 header ('July 2026'), else the file name MMYY."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    month = None
    for l in lines[:12]:
        m = re.match(r"^([A-Za-z]+) (\d{4})$", l)
        if m and m.group(1).lower() in _MON_EN:
            month = (int(m.group(2)), _MON_EN[m.group(1).lower()])
            break
    if month is None:
        m = re.match(r"^(\d{2})(\d{2})_", os.path.basename(filename))
        if m:
            month = (2000 + int(m.group(2)), int(m.group(1)))
    out = {"month": "%04d-%02d" % month if month else None, "date": month_end_bd(*month) if month else None, "total": None, "items": [], "bills": 0.0}
    k = next((i for i, l in enumerate(lines) if re.search(r"over-the-counter buybacks", l, flags=re.I)), None)
    if k is None:
        return out
    for l in lines[k:]:
        if re.match(r"^(Repos|Securities issued|Deposits|Swaps|Commercial paper|Average maturity)", l, flags=re.I):
            break
        m = re.match(r"^Amount(?: of)? OTC buybacks\s*:?\s*([\d\s,\.]+?)\s*(M€|€)?$", l, flags=re.I)
        if m:
            v = _num(m.group(1).replace(" ", ""))
            out["total"] = round(v / 1e6, 3) if v is not None and (m.group(2) == "€" or v > 1e6) else v
            continue
        m = re.match(r"^(BTF)\b.*\s([\d,\.]+)\s*(€)?$", l)
        if m:
            v = _num(m.group(2)) or 0.0
            out["bills"] += round(v / 1e6, 3) if (m.group(3) or v > 1e6) else v
            continue
        m = re.match(r"^((?:OAT|BTAN)\S*\s+\d+[.,]\d+\s*%\s+(?:\d{2}/\d{2}/\d{4}|\d{1,2}(?:er)? [A-Za-zéû]+ \d{4}))\s+([\d,\.]+)\s*(€)?$", l)
        if not m:
            continue
        key = fr_line_key(m.group(1))
        v = _num(m.group(2)) or 0.0
        amt = round(v / 1e6, 3) if (m.group(3) or v > 1e6) else v
        if key and amt:
            out["items"].append({"line": m.group(1), "family": key[0], "coupon": key[1], "maturity": key[2], "amount": amt})
    return out


def fr_review_links(html: str) -> List[str]:
    """PDF hrefs of the monthly operations review pages (names vary: 'opérations mensuelles', 'fusionné', spaces) — the English ('UK') version
    when both languages are listed; discovered, never hardcoded"""
    hrefs = [h.replace("&amp;", "&") for h in re.findall(r'href="([^"]+\.pdf)"', html, flags=re.I)]
    hrefs = [h for h in hrefs if "mensuel" in h.lower() or "monthly" in h.lower()]
    uk = [h for h in hrefs if "uk" in os.path.basename(h).lower()]
    return sorted(set(uk or hrefs))


def fr_buybacks_from_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    return [dict(r, amount=float(r["amount"])) for r in csv.DictReader(open(path, encoding="utf-8"))]


def fr_buybacks_to_csv(path: str, rows: List[dict]) -> List[dict]:
    """archive keyed by (month, line): re-parsing a review replaces its month; a review without buybacks is kept as a zero row so the month
    counts as read. Returns the merged archive (the ISIN is resolved from the line text in fr_lines)."""
    old = {(r["month"], r["line"]): r for r in fr_buybacks_from_csv(path)}
    months = {r["month"] for r in rows}
    old = {k: v for k, v in old.items() if k[0] not in months}
    for r in rows:
        old[(r["month"], r["line"])] = r
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month", "date", "line", "amount", "source"])
        w.writeheader()
        for k in sorted(old):
            w.writerow({c: old[k].get(c, "") for c in w.fieldnames})
    return fr_buybacks_from_csv(path)


def fr_encours_from_csv(path: str) -> Tuple[Optional[str], Dict[str, float]]:
    """'isin;line;outstanding_eur' → (asof from the file name, {isin: €m})"""
    if not os.path.exists(path):
        return None, {}
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
    out = {}
    for l in open(path, encoding="utf-8"):
        p = l.strip().split(";")
        if len(p) >= 3 and re.match(r"^FR[A-Z0-9]{10}$", p[0]):
            out[p[0]] = round((_num(p[2]) or 0.0) / 1e6, 3)
    return (m.group(1) if m else None), out


def fr_lines(records: List[dict], synd: List[dict], buybacks: List[dict], encours: Dict[str, float], encours_asof: Optional[str] = None) -> Tuple[List[dict], dict]:
    """records: FR bond records (ops_eur.fr_records_from_xlsx / _from_html, 1999→; duplicates on (isin, auction, settlement) collapsed);
    synd: fr_parse_syndications; buybacks: [{date, line, amount}] (fr_parse_buyback_pdf items with the review date, or the archive rows; the
    ISIN is resolved here from the line text by (family, coupon, maturity)); encours: {isin: €m} on encours_asof.
    Returns (lines, recon) — recon: {'asof', 'alive', 'matched' (|diff| ≤ 1 %), 'snapped' (pre-1999 shortfalls set to the list), 'rows':
    [(isin, encours, calc, diff, pct)] sorted by |diff|, 'unmapped_buybacks': [line…], 'buyback_months'}."""
    by: Dict[str, dict] = {}
    key_to_isin: Dict[tuple, str] = {}
    seen = set()
    for r in records:
        if r.get("issuer") != "FR" or r.get("kind") != "bond" or not r.get("isin") or not r.get("settlement"):
            continue
        k = (r["isin"], r.get("auction"), r["settlement"])
        if k in seen:
            continue
        seen.add(k)
        key = fr_line_key(r.get("line") or "") if r.get("line") else None
        l = by.setdefault(r["isin"], {"issuer": "FR", "isin": r["isin"], "coupon": None, "maturity": r.get("maturity") or (key[2] if key else ""), "tranches": [], "coupon_months": 12, "family": ""})
        l["tranches"].append((r["settlement"], float(_num(r["nominal"]) or 0.0)))
        if key:
            l["coupon"], l["family"] = key[1], key[0]
            key_to_isin[key] = r["isin"]
    for s in synd:
        key = fr_line_key(s["line"])
        l = by.setdefault(s["isin"], {"issuer": "FR", "isin": s["isin"], "coupon": key[1] if key else None, "maturity": key[2] if key else "", "tranches": [], "coupon_months": 12, "family": key[0] if key else ""})
        if key:
            key_to_isin[key] = s["isin"]
            if l["coupon"] is None:
                l["coupon"], l["family"], l["maturity"] = key[1], key[0], l["maturity"] or key[2]
        l["tranches"].append((s["settlement"], float(s["volume"])))
    unmapped, months = [], set()
    for b in buybacks:
        if not b.get("amount"):
            continue
        key = fr_line_key(b.get("line", ""))
        isin = key_to_isin.get(key) if key else None
        if not isin or not b.get("date"):
            unmapped.append(b.get("line", ""))
            continue
        by[isin]["tranches"].append((b["date"], -float(b["amount"])))
        months.add(b["date"][:7])
    rows, snapped = [], 0
    for isin, n in encours.items():
        l = by.get(isin)
        calc = sum(v for d, v in l["tranches"] if not encours_asof or d <= encours_asof) if l else 0.0
        diff = round(calc - n, 3)
        if l and diff < 0 and l["tranches"] and min(d for d, _ in l["tranches"]) < "2000-01-01":
            l["tranches"].append((min(d for d, _ in l["tranches"]), -diff))  # pre-1999 tranches are not in the 1999→ file: constant at the list
            snapped += 1
            diff, calc = 0.0, n
        rows.append((isin, n, round(calc, 3), diff, round(diff / n * 100.0, 2) if n else None))
    rows.sort(key=lambda r: -abs(r[3]))
    lines = []
    for l in by.values():
        if not l["maturity"]:
            continue
        l["tranches"].sort()
        l["coupon"] = l["coupon"] or 0.0  # OAT TEC10 (floating): redemption kept, no coupon
        l.pop("family", None)
        lines.append(l)
    recon = {"asof": encours_asof, "alive": len(encours), "matched": sum(1 for r in rows if r[4] is not None and abs(r[4]) <= 1.0), "snapped": snapped, "rows": rows,
             "unmapped_buybacks": unmapped, "buyback_months": sorted(months)}
    return lines, recon


# ═══════════════════════ IT — MEF scadenze ═══════════════════════
def _it_amount(v: str) -> Optional[float]:
    s = str(v or "").strip()
    if not s or s in ("-", "n/d"):
        return None
    if re.match(r"^[\d.]+,\d+$", s):
        return _num(s, dec=",")
    if re.match(r"^[\d,]+\.\d+$", s) or re.match(r"^[\d,]+$", s):
        return _num(s)
    return None


def _it_date(v: str, snapshot_year: Optional[int] = None) -> Optional[str]:
    s = str(v or "").strip()
    m = re.match(r"^(\d{1,2})-([a-z]{3})-(\d{2})$", s.lower())
    if m and m.group(2) in _MON_IT:
        return "%d-%02d-%02d" % (2000 + int(m.group(3)), _MON_IT[m.group(2)], int(m.group(1)))
    d = _iso(s)
    if d and snapshot_year and int(d[:4]) < snapshot_year - 1 and int(d[:4]) < 2000:
        d = "%d%s" % (int(d[:4]) + 100, d[4:])  # 2021 file: '01/03/1930' for 2030
    return d


def it_parse_scadenze(text: str) -> Tuple[Optional[str], List[dict]]:
    """→ (asof, rows {isin, type, issue, maturity, coupon_txt, currency, nominal (€m), revalued (€m)}) — market-held section only"""
    rd = csv.reader(io.StringIO(text), delimiter=";")
    asof, hdr, out = None, None, []
    for r in rd:
        cells = [c.strip() for c in r]
        if not any(cells):
            continue
        if asof is None:
            m = re.search(r"al (\d{1,2})[./ ](\d{1,2}|[a-z]+)[./ ](\d{4})", cells[0].lower())
            if m:
                mo = m.group(2)
                asof = "%s-%02d-%02d" % (m.group(3), int(mo) if mo.isdigit() else _MON_IT.get(mo[:3], 0), int(m.group(1)))
        if cells[0].lower().startswith("codice isin"):
            if hdr is not None:
                break  # second header = repo-portfolio section
            hdr = {c.lower(): i for i, c in enumerate(cells) if c}
            continue
        if hdr is None or cells[0].lower().startswith("titoli di stato per portafoglio"):
            if hdr is not None:
                break
            continue
        if not re.match(r"^[A-Z]{2}[A-Z0-9]{10}$", cells[0]):
            continue
        yr = int(asof[:4]) if asof else None
        g = lambda name: cells[hdr[name]] if name in hdr and hdr[name] < len(cells) else ""
        nom_col = next((k for k in hdr if k.startswith("circolante euro (nominale)")), None)
        rev_col = next((k for k in hdr if k.startswith("circolante euro (rivalutato)")), None)
        base_col = next((k for k in hdr if k.startswith("circolante euro") and k not in (nom_col, rev_col)), None)
        nom = _it_amount(g(nom_col)) if nom_col else _it_amount(g(base_col))
        rev = _it_amount(g(rev_col)) if rev_col else nom
        if nom is None:
            continue
        out.append({"isin": cells[0], "type": g("tipo titolo"), "issue": _it_date(g("emissione")), "maturity": _it_date(g("scadenza"), yr), "coupon_txt": g("cedola/spread"),
                    "currency": g("valuta") or "EUR", "nominal": round(nom / 1e6, 3), "revalued": round(rev / 1e6, 3) if rev is not None else None})
    return asof, out


def it_coupon(typ: str, txt: str) -> Tuple[Optional[float], int]:
    """(coupon % p.a. or None when excluded, coupon_months) by instrument family"""
    t = (typ or "").strip().lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(txt or ""))
    c = float(m.group(1).replace(",", ".")) if m else None
    if t.startswith("cct"):
        return None, 12  # floating: the field is the spread over Euribor 6m → excluded
    if t.startswith("ctz") or t.startswith("bot"):
        return 0.0, 12
    if t.startswith("btp valore") or t.startswith("btp più") or t.startswith("btp piu"):
        return c, 3
    if t.startswith("btp"):
        return c, 6
    return None, 12


def it_scadenze_links(html: str) -> List[str]:
    return sorted(set(MEF_BASE + h if h.startswith("/") else h for h in re.findall(r'href="([^"]*scadenze_titoli_suddivise_per_anno[^"]*\.csv)"', html, flags=re.I)))


def it_lines(snapshots: List[Tuple[str, List[dict]]]) -> Tuple[List[dict], dict]:
    """snapshots [(asof, rows)] (any order, deduped by asof). Domestic BTP-family / CCTeu / CTZ lines in EUR only; BOT excluded (bills, in the
    auction records). tranches: (issue date, first snapshot nominal) then each later snapshot as a delta on its asof; the snapshot of the
    maturity year (asof ≥ maturity) sets the redeemed amount as a delta ON the maturity date. Returns (lines, {'snapshots': [asof…],
    'lines', 'excluded': {type: n}, 'cct_no_coupon': n})."""
    snaps = sorted({a: r for a, r in snapshots if a}.items())
    per: Dict[str, List[Tuple[str, dict]]] = defaultdict(list)
    excluded: Dict[str, int] = defaultdict(int)
    for asof, rows in snaps:
        for r in rows:
            t = r["type"].strip().lower()
            if r.get("currency", "EUR") != "EUR" or not (t.startswith("btp") or t.startswith("cct") or t.startswith("ctz")):
                excluded[r["type"].split()[0] if r["type"] else "?"] += 1
                continue
            per[r["isin"]].append((asof, r))
    out, cct = [], 0
    for isin, lst in per.items():
        lst.sort(key=lambda x: x[0])
        m = lst[-1][1]["maturity"] or lst[0][1]["maturity"]
        if not m:
            continue
        c, months = it_coupon(lst[-1][1]["type"], lst[-1][1]["coupon_txt"])
        if c is None:
            cct += 1
        tr: List[Tuple[str, float]] = []
        prev = 0.0
        for asof, r in lst:
            if asof > m and tr and any(d == m for d, _ in tr):
                continue  # one post-maturity snapshot is enough
            d = (lst[0][1]["issue"] or asof) if not tr else (m if asof > m else asof)
            if not tr or round(r["nominal"] - prev, 3):
                tr.append((min(d, m), round(r["nominal"] - prev, 3)))
            prev = r["nominal"]
        out.append({"issuer": "IT", "isin": isin, "coupon": c or 0.0, "maturity": m, "tranches": sorted(tr), "coupon_months": months})
    return out, {"snapshots": [a for a, _ in snaps], "lines": len(out), "excluded": dict(excluded), "cct_no_coupon": cct}


# ═══════════════════════ ES — Tesoro 13.xlsx ═══════════════════════
def es_parse_financiacion(blob: bytes, upto: Optional[str] = None) -> List[dict]:
    """→ rows {year, month, day ('' for a monthly row), bonos, oblig, index} from every '(Importes efectivos)' sheet (the cumulative
    sheets are skipped). A month broken down by day keeps its daily rows only; months after `upto` ('yyyy-mm') are dropped (the sheet
    carries the scheduled amortizations of the months to come — projections, not flows)."""
    from .providers_chf import xlsx_sheets, _rows_of
    out = []
    for cells in xlsx_sheets(blob).values():
        rows = _rows_of(cells)
        title = " ".join(str(v) for r in sorted(rows)[:3] for v in rows[r].values() if v)
        m = re.search(r"FINANCIACI.N NETA EN (\d{4})", title)
        if not m or "acumulados" in title.lower():
            continue
        year = int(m.group(1))
        hdr = next((r for r in sorted(rows) if any(str(v).strip().upper() == "AMORTIZACIONES" for v in rows[r].values())), None)
        if hdr is None:
            continue
        a_col = next(c for c, v in rows[hdr].items() if str(v).strip().upper() == "AMORTIZACIONES")
        sub = rows.get(hdr + 1, {})
        cols = {}
        for c, v in sub.items():
            if c < a_col:
                continue
            lab = re.sub(r"\s+", " ", str(v)).strip().upper()
            if lab == "TOTAL":
                break
            cols[lab] = c
        bon = cols.get("BONOS")
        obl = next((c for l, c in cols.items() if l.startswith("OBLIG")), None)
        idx = next((c for l, c in cols.items() if "INDEX" in l), None)
        month = None
        for r in sorted(rows):
            if r <= hdr + 1:
                continue
            lab = rows[r].get("B")
            if isinstance(lab, str) and lab.strip().lower() in _MON_ES:
                month = _MON_ES[lab.strip().lower()]
                vals = [_num(rows[r].get(c)) for c in (bon, obl, idx) if c]
                if any(v is not None for v in vals):
                    out.append({"year": year, "month": month, "day": "", "bonos": vals[0] or 0.0, "oblig": (vals[1] if len(vals) > 1 else 0.0) or 0.0, "index": (vals[2] if len(vals) > 2 else 0.0) or 0.0})
            elif month and isinstance(lab, (int, float)) and 1 <= int(lab) <= 31:
                vals = [_num(rows[r].get(c)) for c in (bon, obl, idx) if c]
                if any(v is not None for v in vals):
                    out.append({"year": year, "month": month, "day": int(lab), "bonos": vals[0] or 0.0, "oblig": (vals[1] if len(vals) > 1 else 0.0) or 0.0, "index": (vals[2] if len(vals) > 2 else 0.0) or 0.0})
            elif isinstance(lab, str) and lab.strip().upper().startswith("TOTAL A"):
                break
    daily_months = {(r["year"], r["month"]) for r in out if r["day"] != ""}
    return [r for r in out if (r["day"] != "" or (r["year"], r["month"]) not in daily_months) and (not upto or "%04d-%02d" % (r["year"], r["month"]) <= upto)]


def es_amort_from_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        out.append({"year": int(r["year"]), "month": int(r["month"]), "day": int(r["day"]) if r["day"] else "", "bonos": float(r["bonos"]), "oblig": float(r["oblig"]), "index": float(r["index"])})
    return out


def es_amort_to_csv(path: str, rows: List[dict]) -> List[dict]:
    """archive keyed by month: a re-read month replaces the archived one (daily rows of a month in progress become one monthly row later)"""
    old = es_amort_from_csv(path)
    months = {(r["year"], r["month"]) for r in rows}
    merged = [r for r in old if (r["year"], r["month"]) not in months] + rows
    merged.sort(key=lambda r: (r["year"], r["month"], r["day"] or 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["year", "month", "day", "bonos", "oblig", "index"])
        w.writeheader()
        for r in merged:
            w.writerow(r)
    return merged


def es_lines(amort: List[dict], records: List[dict]) -> Tuple[List[dict], dict]:
    """one zero-coupon pseudo-line per redemption date (isin 'ES:<date>') so bond_redemptions_coupons needs no ES-specific path:
    daily rows on their day; monthly rows on the maturity dates of the ES bond records in that month (pro-rata to auctioned nominal),
    else the last business day of the month. Returns (lines, {'from', 'to', 'months', 'dated_by_records', 'dated_month_end', 'skipped_coupon_maturities'})."""
    mat: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in records:
        if r.get("issuer") == "ES" and r.get("kind") == "bond" and r.get("maturity"):
            mat[r["maturity"][:7]][r["maturity"]] += float(_num(r["nominal"]) or 0.0)
    red: Dict[str, float] = defaultdict(float)
    by_rec = by_me = 0
    for r in amort:
        amt = round((r["bonos"] or 0.0) + (r["oblig"] or 0.0) + (r["index"] or 0.0), 3)
        if not amt:
            continue
        ym = "%04d-%02d" % (r["year"], r["month"])
        if r["day"] != "":
            red["%s-%02d" % (ym, int(r["day"]))] += amt
        elif mat.get(ym):
            tot = sum(mat[ym].values())
            for d, n in mat[ym].items():
                red[d] += amt * n / tot
            by_rec += 1
        else:
            red[month_end_bd(r["year"], r["month"])] += amt
            by_me += 1
    lines = [{"issuer": "ES", "isin": "ES:" + d, "coupon": 0.0, "maturity": d, "tranches": [(d, round(v, 3))], "coupon_months": 12} for d, v in sorted(red.items())]
    months = sorted({"%04d-%02d" % (r["year"], r["month"]) for r in amort})
    skipped = len({r["maturity"] for r in records if r.get("issuer") == "ES" and r.get("kind") == "bond" and r.get("maturity")})
    return lines, {"from": months[0] if months else None, "to": months[-1] if months else None, "months": len(months), "dated_by_records": by_rec, "dated_month_end": by_me,
                   "skipped_coupon_maturities": skipped}
