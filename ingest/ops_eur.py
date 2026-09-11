"""EUR v0.4 — weekly net issuance to the private sector by SETTLEMENT date, built issuer by issuer (E2), plus the bills / bonds calendars.

Sources verified 2026-09-10 (VERIFICACIONES_V04.md, ADJUDICACION_METRICAS_EUR.md):
  DE  Finanzagentur 'Auction results' XLSX (already wired: date, ISIN, maturity, allotted = placed with the market, retention = kept by the Bund);
      value date = auction + 2 business days (verified on the issuance-outlook XLSX: 'Start of interest period' = auction + 2 for Bund 07-08 → 07-10,
      Schatz 07-14 → 07-16); Bubills use the same Monday → Wednesday convention.
      einzelaufstellung_en.xlsx 'security list' (monthly, nominal per ISIN at month-end: type, ISIN, coupon, issuance date, maturity) → redemptions + coupons.
      Issuance_outlook_<year>_Update_Q<n>_en.xlsx (Serial | Date | Security | Term | Type | Volume | Maturity | ISIN | Coupon | ...) → supply ahead.
  FR  AFT history XLSX: <yyyy-mm>_hist_mlt.xlsx sheet 'MLT' (type, auction date, SETTLEMENT date, ISIN, line, bid, served, cover, NCTs, TOTAL issued,
      wa rate/price) since 1999; <yyyy-mm>_hist_btf.xlsx sheet 'BTF' (auction, settlement, weeks, MATURITY, ISIN, ..., total issued). Updated monthly
      (end of July as of 10-Sep) → the current months come from /en/dernieres-adjudications (HTML tables; POST period_textfield[month]/[year] for a month).
      OAT settle T+2 business days (03-09 → 07-09), BTF T+2 (07-09 → 09-09).
  ES  tesoro.es per-auction pages (…/resultado-ultimas-subastas/<tipo>?nid=N): key-value table with Fecha subasta, Fecha vencimiento, Fecha de liquidación,
      Nominal adjudicado (+ 2ª vuelta), Efectivo adjudicado (+ 2ª vuelta), Ratio de cobertura, Tipo de interés medio; listing at
      /deuda-publica/subastas/resultados-subastas-anteriores?page=N (20 per page). Settlement T+3 (03-09 → 08-09; letras 08-09 → 11-09). No bulk file.
  IT  dt.mef.gov.it per-auction PDFs (text key-value: ISIN, Issue date, Maturity Date, Auction Date, Settlement Date, Amount Allotted, Allotment /
      Weighted Average Price, Bid To Cover Ratio, Gross Yield, Allotted to Specialists in supplementary placements); index per instrument with
      ?selezione-anno=YYYY. Parsed with pdfplumber in the runner (fixtures: two PDFs). BOT 6m: auction 08-27 → settlement 08-31; BTP 07-30 → 08-03.
  EU  commission.europa.eu news pages 'Results of dd-mm-yyyy auction (EU-Bills|EU-Bonds)' (HTML table: ISIN, auction / settlement dates, maturity,
      volume allotment, non-competitive allocation, prices, cover); yearly lists at /eu-bills-<year>_en and /eu-bonds-<year>_en (2025–2026 live,
      earlier years only on wayback). EU-Bills settle T+2 (02-09 → 04-09); bond auctions T+2, non-competitive leg T+3. SYNDICATIONS NOT WIRED
      (press-release format; the 'Transactions data' dashboard is a Qlik frame) → EU component = auctions only, labelled.
  ESM/EFSF  investor pages behind a login wall on 2026-09-10 → NOT WIRED (limitation written on the card).

Reserve mechanics (+ = excess liquidity created): settlement of an auction −cash (nominal × price where the price is published, else nominal);
bill maturities +nominal (market-held by construction); bond redemptions + coupons GROSS (Eurosystem APP/PEPP holdings are not published by
line) for the issuers whose outstanding per line is primary: DE (emissionshistorie_en.xlsx since 1999, de_lines), EU (Qlik operations since
2020, ops_eu_qlik.eu_lines), FR (auctions + syndications − monthly buybacks since 1999, reconciled to the AFT outstanding list), IT (MEF
year-end snapshots since 2020, applied from the first MEF auction record so both sides start together) and ES redemptions only (Tesoro
13.xlsx amortizations since 2025, no coupons) — ops_eur_lines. ESM stays ONE-SIDED (the export lists alive lines only). Flows cut at today;
the FR monthly file is bridged by the HTML months; IT/ES/EU archives grow with each run (history/eur/*.csv).
Nothing here decides a regime (shadow components only)."""
from __future__ import annotations
import csv
import io
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from .series import Series, clean

# ─── URLs (verified 2026-09-10) ───
AFT_LATEST = "https://www.aft.gouv.fr/en/dernieres-adjudications"
AFT_OAT_PAGE = "https://www.aft.gouv.fr/en/principaux-chiffres-oat"
AFT_BTF_PAGE = "https://www.aft.gouv.fr/en/btf-principaux-chiffres"
ES_LIST = "https://www.tesoro.es/deuda-publica/subastas/resultados-subastas-anteriores?page=%d"
ES_BASE = "https://www.tesoro.es"
IT_BASE = "https://www.dt.mef.gov.it"
IT_PAGES = {"bot_flex": "risultati_aste_bot_flessibili", "bot_3m": "risultati_aste_bot_3_mesi", "bot_6m": "risultati_aste_bot_6_mesi", "bot_12m": "risultati_aste_bot_12_mesi",
            "ccteu": "risultati_aste_cct_eu", "btp_st": "risultati_aste_btp_short_term", "btp_3y": "risultati_aste_btp_3_anni", "btp_5y": "risultati_aste_btp_5_anni",
            "btp_7y": "risultati_aste_btp_7_anni", "btp_10y": "risultati_aste_btp_10_anni", "btp_15y": "risultati_aste_btp_15_anni", "btp_20y": "risultati_aste_btp_20_anni",
            "btp_30y": "risultati_aste_btp_30_anni", "btp_50y": "risultati_aste_btp_50_anni", "btp_green": "risultati_aste_btp_green",
            "btpei_5y": "risultati_btpei_5_anni", "btpei_10y": "risultati_btpei_10_anni", "btpei_15y": "risultati_btpei_15_anni", "btpei_20y": "risultati_btpei_20_anni", "btpei_30y": "risultati_btpei_30_anni"}
IT_INDEX = IT_BASE + "/en/debito_pubblico/emissioni_titoli_di_stato_interni/risultati_aste/%s/index.html?selezione-anno=%d"
EU_BASE = "https://commission.europa.eu"
EU_YEAR = EU_BASE + "/eu-%s-%d_en"  # bills|bonds, year
DE_OUTSTANDING = "https://www.deutsche-finanzagentur.de/fileadmin/user_upload/Institutionelle-investoren/berichtswesen/einzelaufstellung_en.xlsx"
DE_HISTORY_XLSX = "https://www.deutsche-finanzagentur.de/fileadmin/user_upload/Institutionelle-investoren/auktionen/emissionshistorie_en.xlsx"  # config/eur.json finanzagentur.files.history_xlsx (verified 2026-09-09)
DE_CALENDAR_PAGE = "https://www.deutsche-finanzagentur.de/en/federal-securities/issuances/issuance-calendar"

_MON_EN = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
_MON_FR = {m: i for i, m in enumerate(["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"], 1)}


def _num(v, dec: str = ".") -> Optional[float]:
    """dec='.' → ',' and spaces are thousands separators (DE/FR/EU/IT pages); dec=',' → '.' is the thousands separator (ES pages)"""
    if v in (None, "", "-", "—"):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace("\u202f", "").replace(" ", "")
    if s.endswith("%"):
        s = s[:-1]
    if dec == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
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
    m = re.match(r"^(\d{1,2})[/.](\d{1,2})[/.](\d{4})$", s)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
    m = re.match(r"^([A-Za-z]+) (\d{1,2}), (\d{4})$", s)  # 'August 31, 2026' (MEF)
    if m and m.group(1).lower() in _MON_EN:
        return "%s-%02d-%02d" % (m.group(3), _MON_EN[m.group(1).lower()], int(m.group(2)))
    return _serial(s)


def bd_add(d: str, n: int) -> str:
    x = date.fromisoformat(d)
    k = 0
    while k < n:
        x += timedelta(days=1)
        if x.weekday() < 5:
            k += 1
    return x.isoformat()


def roll_bd(d: str) -> str:
    """payment date convention: Saturday / Sunday → next Monday (TARGET holidays not modelled, like business_days)"""
    x = date.fromisoformat(d)
    while x.weekday() >= 5:
        x += timedelta(days=1)
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
    fm: Dict[str, float] = defaultdict(float)
    for d, v in flows:
        fm[d] += v
    return [(d, round(fm.get(d, 0.0), 3)) for d in days]


# ═══════════════════════ unified record: issuer, kind ('bill'|'bond'), isin, auction, settlement, maturity, nominal, cash, cover, yield, source ═══════════════════════
REC_COLS = ["issuer", "kind", "isin", "auction", "settlement", "maturity", "nominal", "cash", "cover", "yield", "source"]


def read_records(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    return [dict(r) for r in csv.DictReader(open(path, encoding="utf-8"))]


def merge_records(path: str, recs: List[dict]) -> List[dict]:
    """union keyed by (issuer, isin, auction, settlement, nominal)"""
    seen: Dict[tuple, dict] = {}
    for r in read_records(path) + recs:
        k = (r.get("issuer"), r.get("isin"), r.get("auction"), r.get("settlement"), str(_num(r.get("nominal")) or 0.0))
        seen[k] = {c: ("" if r.get(c) is None else r.get(c)) for c in REC_COLS}
    rows = sorted(seen.values(), key=lambda r: (str(r["settlement"]), str(r["issuer"]), str(r["isin"])))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REC_COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return rows


# ═══════════════════════ DE — Finanzagentur ═══════════════════════
def de_records(rows: List[dict]) -> List[dict]:
    """rows from FinanzagenturProvider.parse (allotted = placed with the market; retention excluded); value date T+2"""
    out = []
    for r in rows:
        a = r.get("allotted")
        if not a or not r.get("date"):
            continue
        s = bd_add(r["date"], 2)
        kind = "bill" if str(r.get("bond", "")).lower().startswith("bubill") else "bond"
        price = r.get("avg_price")
        cash = round(a * price / 100.0, 3) if price else a
        out.append({"issuer": "DE", "kind": kind, "isin": r.get("isin", ""), "auction": r["date"], "settlement": s, "maturity": r.get("maturity") or "", "nominal": a,
                    "cash": cash, "cover": r.get("bid_to_cover"), "yield": r.get("avg_yield"), "source": "finanzagentur"})
    return out


def parse_de_outstanding(cells: Dict[str, object]) -> List[dict]:
    """einzelaufstellung_en.xlsx: header row 'TYPE OF SECURITY | ISIN | COUPON | ISSUANCE DATE | MATURITY | <dates…>' → nominal (EUR m) at the last date column"""
    from .providers_chf import _rows_of
    rows = _rows_of(cells)
    hdr = next((r for r in sorted(rows) if str(rows[r].get("A", "")).strip().upper() == "TYPE OF SECURITY"), None)
    if hdr is None:
        return []
    date_cols = [(c, _iso(v)) for c, v in rows[hdr].items() if c not in ("A", "B", "C", "D", "E") and _iso(v)]
    if not date_cols:
        return []
    last_col, asof = max(date_cols, key=lambda x: x[1])
    out, typ = [], ""
    for r in sorted(rows):
        if r <= hdr:
            continue
        row = rows[r]
        a = str(row.get("A", "")).strip()
        if a and a.upper() != "TOTAL":
            typ = a
        isin = str(row.get("B", "")).strip()
        if re.match(r"^[A-Z]{2}[A-Z0-9]{10}$", isin):
            out.append({"type": typ, "isin": isin, "coupon": _num(row.get("C")), "issue_date": _iso(row.get("D")), "maturity": _iso(row.get("E")),
                        "nominal": round((_num(row.get(last_col)) or 0.0) / 1e6, 3), "asof": asof})
    return out


def de_outstanding_from_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        ncol = next((k for k in r if k.startswith("nominal")), "nominal")
        out.append({"type": r["type"], "isin": r["isin"], "coupon": _num(r.get("coupon")), "issue_date": r.get("issue_date"), "maturity": r.get("maturity"),
                    "nominal": _num(r.get(ncol)) or 0.0, "asof": ncol.split("_")[-1] if "_" in ncol else r.get("asof", "")})
    return out


def parse_de_calendar(cells: Dict[str, object]) -> List[dict]:
    """Issuance outlook XLSX: 'Serial number | Date | Security | Term | Type | Volume in € mn | Maturity | ISIN | Coupon | ...'"""
    from .providers_chf import _rows_of
    rows = _rows_of(cells)
    hdr = next((r for r in sorted(rows) if str(rows[r].get("A", "")).strip().lower().startswith("serial")), None)
    if hdr is None:
        return []
    out = []
    for r in sorted(rows):
        if r <= hdr:
            continue
        row = rows[r]
        d = _serial(row.get("B"))
        if not d:
            continue
        out.append({"date": d, "security": str(row.get("C", "")).strip(), "term": str(row.get("D", "")).strip(), "type": str(row.get("E", "")).strip(),
                    "volume": _num(row.get("F")), "maturity": _serial(row.get("G")), "isin": str(row.get("H", "")).strip()})
    return out


def de_lines(hist_rows: List[dict], outstanding: List[dict]) -> List[dict]:
    """Bond lines for bond_redemptions_coupons from the Finanzagentur issuance history (emissionshistorie_en.xlsx parsed by
    FinanzagenturProvider.parse: every auction, syndication and tap into own holdings since 1999 with ISIN, coupon, maturity, issuance volume).
    Outstanding of a line by date = Σ issuance volume (allotted + retention; the retention is sold later in the secondary market without
    changing the nominal) by value date (auction + 2 bd). Verified 2026-09-11 against einzelaufstellung 2026-08-31: 84/84 lines whose
    creation ('N' row) is in the file match to the euro. Lines created before 1999 (only 'R' rows): alive → constant nominal from the
    outstanding list (3 × 30Y Bunds of 1997-98); matured → dropped, not fabricated (DE0001134922 6.25 % Bund 2024-01-04: only 2.5 bn of
    2005/2020 taps in the file). Bubills excluded (their maturities come from the records), USD bonds excluded, ILB on the real coupon and
    the nominal (indexation ignored, as in de_calendar). Coupon: annual (Bund/Bobl/Schatz/Green/ILB)."""
    by: Dict[str, dict] = {}
    for r in hist_rows:
        isin, vol = str(r.get("isin") or "").strip(), r.get("volume")
        if not isin or not vol or not r.get("date") or not r.get("maturity") or r.get("bond") in ("Bubill", "USD-Bond"):
            continue
        l = by.setdefault(isin, {"issuer": "DE", "isin": isin, "coupon": round((r.get("coupon") or 0.0) * 100.0, 4), "maturity": r["maturity"], "tranches": [], "created": False})
        l["tranches"].append((bd_add(r["date"], 2), float(vol)))
        if r.get("type") == "N":
            l["created"] = True
    alive = {o["isin"]: o for o in outstanding if o.get("nominal")}
    out = []
    for isin, l in by.items():
        if not l.pop("created"):
            if isin not in alive:
                continue
            l["tranches"] = [(min(d for d, _ in l["tranches"]), alive[isin]["nominal"])]
        l["tranches"].sort()
        out.append(l)
    return out


# ═══════════════════════ FR — AFT ═══════════════════════
def _fr_line_maturity(line: str) -> Optional[str]:
    m = re.search(r"(\d{1,2})(?:er)? ([a-zéû]+) (\d{4})", str(line).lower())
    if m and m.group(2) in _MON_FR:
        return "%s-%02d-%02d" % (m.group(3), _MON_FR[m.group(2)], int(m.group(1)))
    return None


def fr_records_from_csv(oat_path: str, btf_path: str) -> List[dict]:
    out = []
    for r in csv.DictReader(open(oat_path, encoding="utf-8")) if os.path.exists(oat_path) else []:
        tot = _num(r.get("total"))
        if not tot:
            continue
        price = _num(r.get("wa_price"))
        out.append({"issuer": "FR", "kind": "bond", "isin": r.get("isin", ""), "auction": r["auction"], "settlement": r["settlement"], "maturity": _fr_line_maturity(r.get("line", "")) or "",
                    "nominal": tot, "cash": round(tot * price, 3) if price else tot, "cover": _num(r.get("btc")), "yield": round((_num(r.get("wa_rate")) or 0.0) * 100, 4), "source": "aft_hist_mlt",
                    "line": r.get("line", "")})  # line name (not a REC_COL: dropped by merge_records) → ops_eur_lines.fr_lines maps buybacks by coupon + maturity
    for r in csv.DictReader(open(btf_path, encoding="utf-8")) if os.path.exists(btf_path) else []:
        tot = _num(r.get("total"))
        if not tot:
            continue
        out.append({"issuer": "FR", "kind": "bill", "isin": r.get("isin", ""), "auction": r["auction"], "settlement": r["settlement"], "maturity": r.get("maturity", ""),
                    "nominal": tot, "cash": tot, "cover": _num(r.get("btc")), "yield": round((_num(r.get("wa_rate")) or 0.0) * 100, 4), "source": "aft_hist_btf"})
    return out


def fr_records_from_xlsx(oat_blob: Optional[bytes], btf_blob: Optional[bytes]) -> List[dict]:
    from .providers_chf import xlsx_sheets, _rows_of
    out = []
    if oat_blob:
        rows = _rows_of(next(iter(xlsx_sheets(oat_blob).values())))
        for r in sorted(rows):
            row = rows[r]
            a, s, tot = _serial(row.get("B")), _serial(row.get("C")), _num(row.get("L"))
            if not a or not s or not tot:
                continue
            price = _num(row.get("N"))
            out.append({"issuer": "FR", "kind": "bond", "isin": str(row.get("F", "")).strip(), "auction": a, "settlement": s, "maturity": _fr_line_maturity(row.get("G", "")) or "",
                        "nominal": tot, "cash": round(tot * price, 3) if price else tot, "cover": _num(row.get("J")), "yield": round((_num(row.get("M")) or 0.0) * 100, 4), "source": "aft_hist_mlt",
                        "line": str(row.get("G", "")).strip()})
    if btf_blob:
        rows = _rows_of(next(iter(xlsx_sheets(btf_blob).values())))
        for r in sorted(rows):
            row = rows[r]
            a, s, tot = _serial(row.get("A")), _serial(row.get("B")), _num(row.get("L"))
            if not a or not s or not tot:
                continue
            out.append({"issuer": "FR", "kind": "bill", "isin": str(row.get("G", "")).strip(), "auction": a, "settlement": s, "maturity": _serial(row.get("D")) or "",
                        "nominal": tot, "cash": tot, "cover": _num(row.get("J")), "yield": round((_num(row.get("M")) or 0.0) * 100, 4), "source": "aft_hist_btf"})
    return out


def _html_tables(html: str) -> List[List[List[str]]]:
    tabs = []
    for t in re.findall(r"<table[^>]*>(.*?)</table>", html, flags=re.S | re.I):
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S | re.I):
            cells = [re.sub(r"<[^>]+>", " ", c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, flags=re.S | re.I)]
            rows.append([re.sub(r"\s+", " ", c).replace("&nbsp;", " ").strip() for c in cells])
        tabs.append(rows)
    return tabs


def fr_records_from_html(html: str) -> List[dict]:
    """AFT latest-auctions page: one table per auction group; row labels in column 0, one column per line/ISIN"""
    out = []
    for rows in _html_tables(html):
        kv = {r[0].lower(): r[1:] for r in rows if r}
        head = rows[0][1:] if rows else []
        isins = kv.get("isin code", [])
        n = max(len(isins), len(kv.get("auction date", [])))
        for i in range(n):
            g = lambda k: (kv.get(k, []) + [""] * n)[i]
            a, s = _iso(g("auction date")), _iso(g("settlement date"))
            tot = _num(g("total amount issued*")) or _num(g("total amount issued"))
            if not a or not s or not tot:
                continue
            is_btf = "btf" in " ".join(head).lower() or "maturity" in kv
            mat = _iso(g("maturity")) if is_btf else None
            if not is_btf and i < len(head):
                mm = re.search(r"(\d{2}/\d{2}/\d{4})", head[i])
                mat = _iso(mm.group(1)) if mm else None
            price = _num(g("weighted average price"))
            out.append({"issuer": "FR", "kind": "bill" if is_btf else "bond", "isin": (isins + [""] * n)[i], "auction": a, "settlement": s, "maturity": mat or "",
                        "nominal": tot, "cash": round(tot * price / 100.0, 3) if price else tot, "cover": _num(g("bid to cover ratio**")) or _num(g("bid to cover ratio")),
                        "yield": _num(g("weighted average rate")), "source": "aft_html", "line": "" if is_btf or i >= len(head) else head[i]})
    return out


# ═══════════════════════ ES — Tesoro Público ═══════════════════════
def es_records_from_csv(path: str) -> List[dict]:
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")) if os.path.exists(path) else []:
        nom = (_num(r.get("nominal_alloc")) or 0.0) + (_num(r.get("nominal_2nd")) or 0.0)  # the fixture/archive CSV is already normalised ('.' decimal)
        cash = (_num(r.get("cash_alloc")) or 0.0) + (_num(r.get("cash_2nd")) or 0.0)
        if not nom or not r.get("settlement"):
            continue
        out.append({"issuer": "ES", "kind": "bill" if "letras" in r.get("title", "").lower() else "bond", "isin": "", "auction": r["auction"], "settlement": r["settlement"],
                    "maturity": r.get("maturity", ""), "nominal": round(nom, 3), "cash": round(cash or nom, 3), "cover": _num(r.get("btc")), "yield": _num(r.get("avg_yield")), "source": "tesoro_nid_%s" % r.get("nid", "")})
    return out


def es_parse_auction_page(html: str, title: str, nid: str) -> List[dict]:
    out = []
    for rows in _html_tables(html):
        kv = {r[0]: r[1:] for r in rows if len(r) >= 2}
        if "Fecha subasta" not in kv:
            continue
        n = len(kv["Fecha subasta"])
        for i in range(n):
            g = lambda k: (kv.get(k, []) + [""] * n)[i]
            E = lambda k: _num(g(k), dec=",") if re.match(r"^\d{1,3}(\.\d{3})*(,\d+)?$", g(k).strip()) else _num(g(k))  # tesoro.es mixes '2.916,08' and '415.35'
            nom = (E("Nominal adjudicado") or 0.0) + (E("Nominal adjudicado (2ª vuelta)") or 0.0)
            cash = (E("Efectivo adjudicado") or 0.0) + (E("Efectivo adjudicado (2ª vuelta)") or 0.0)
            a, s = _iso(g("Fecha subasta")), _iso(g("Fecha de liquidación"))
            if not a or not s or not nom:
                continue
            out.append({"issuer": "ES", "kind": "bill" if "letras" in title.lower() else "bond", "isin": "", "auction": a, "settlement": s, "maturity": _iso(g("Fecha vencimiento")) or "",
                        "nominal": round(nom, 3), "cash": round(cash or nom, 3), "cover": _num(g("Ratio de cobertura"), dec=","), "yield": _num(g("Tipo de interés medio"), dec=","), "source": "tesoro_nid_%s" % nid})
    return out


def es_parse_listing(html: str) -> List[dict]:
    """(date, title, href, nid) from the paginated listing"""
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"]*resultado-ultimas-subastas/[^"]*\?nid=(\d+))"[^>]*>(.*?)</a>(.{0,400}?)(\d{2}/\d{2}/\d{4})', html, flags=re.S):
        out.append({"href": m.group(1), "nid": m.group(2), "title": re.sub(r"<[^>]+>|\s+", " ", m.group(3)).strip(), "date": _iso(m.group(5))})
    return out


# ═══════════════════════ IT — MEF PDFs ═══════════════════════
def it_parse_pdf_text(text: str, url: str = "") -> List[dict]:
    kv = {}
    for line in text.splitlines():
        m = re.match(r"^(ISIN Code|Coupon|Issue date|Maturity Date|Auction Date|Settlement Date|Amount Allotted|Allotment Price|Weighted Average Price|Bid To Cover Ratio|Gross Yield|Weighted Average Yield|Days to Maturity|Accrued Coupon Days|Amount Bid|Amount Offered)\s+(.+)$", line.strip())
        if m and m.group(1) not in kv and not m.group(2).strip().lower().startswith("to specialists"):  # first occurrence; skip the specialists block
            kv[m.group(1)] = m.group(2).strip()
    a, s = _iso(kv.get("Auction Date")), _iso(kv.get("Settlement Date"))
    nom = _num(kv.get("Amount Allotted"))
    if not a or not s or not nom:
        return []
    supp = None
    m = re.search(r"Amount Allotted to Specialists\s+([\d,\.]+)", text)  # this auction's supplementary placement (the 'Issue Volume' block is cumulative)
    if m:
        supp = _num(m.group(1))
    price = _num(kv.get("Allotment Price")) or _num(kv.get("Weighted Average Price"))
    kind = "bill" if "BOT" in text[:300].upper() else "bond"
    cash = round(nom * price / 100.0, 3) if price else nom
    cpn, days = _num(kv.get("Coupon")), _num(kv.get("Accrued Coupon Days"))
    if kind == "bond" and cpn and days:
        cash = round(cash + nom * cpn / 100.0 * days / 365.0, 3)
    recs = [{"issuer": "IT", "kind": kind, "isin": kv.get("ISIN Code", ""), "auction": a, "settlement": s, "maturity": _iso(kv.get("Maturity Date")) or "", "nominal": nom, "cash": cash,
             "cover": _num(kv.get("Bid To Cover Ratio")), "yield": _num(kv.get("Gross Yield")) or _num(kv.get("Weighted Average Yield")), "source": "mef_pdf:" + url.rsplit("/", 1)[-1]}]
    if supp:  # supplementary placement to specialists settles with the main leg
        recs.append(dict(recs[0], nominal=supp, cash=round(supp * price / 100.0, 3) if price else supp, cover=None, source=recs[0]["source"] + "#supplementary"))
    return recs


def it_pdf_links(html: str) -> List[str]:
    return [h if h.startswith("http") else IT_BASE + h for h in re.findall(r'href="([^"]+\.pdf)"', html) if "Auction-Results" in h or "Syndicate" in h or "Placement-results" in h]


# ═══════════════════════ EU — Commission auction result pages ═══════════════════════
def eu_records_from_tables(tables: Dict[str, List[List[List[str]]]]) -> List[dict]:
    out = []
    for url, tabs in tables.items():
        for rows in tabs:
            kv = {r[0].lower(): r[1:] for r in rows if r}
            head = rows[0][1:] if rows else []
            isins = kv.get("isin", [])
            n = len(isins)
            for i in range(n):
                g = lambda k: (kv.get(k, []) + [""] * n)[i]
                is_bill = "bills" in " ".join(head).lower()
                if is_bill:
                    a, s = _iso(g("date of auction")), _iso(g("settlement date"))
                    nom = _num(g("volume allotment *"))
                    if not a or not s or not nom:
                        continue
                    out.append({"issuer": "EU", "kind": "bill", "isin": isins[i], "auction": a, "settlement": s, "maturity": _iso(g("maturity")) or "", "nominal": nom, "cash": nom,
                                "cover": _num(g("cover ratio")), "yield": _num(g("weighted average yield")), "source": "eu_news:" + url.rsplit("/", 1)[-1]})
                else:
                    a, s = _iso(g("competitive auction")), _iso(g("settlement competitive auction"))
                    nom = _num(g("volume allotment *"))
                    price = _num(g("weighted average price"))
                    if not a or not s or not nom:
                        continue
                    base = {"issuer": "EU", "kind": "bond", "isin": isins[i], "auction": a, "settlement": s, "maturity": _iso(g("maturity")) or "", "nominal": nom,
                            "cash": round(nom * price / 100.0, 3) if price else nom, "cover": _num(g("cover ratio")), "yield": _num(g("weighted average yield")), "source": "eu_news:" + url.rsplit("/", 1)[-1]}
                    out.append(base)
                    nc, s2 = _num(g("non-competitive allocation *")), _iso(g("settlement non-competitive auction"))
                    if nc and s2:
                        out.append(dict(base, settlement=s2, nominal=nc, cash=round(nc * price / 100.0, 3) if price else nc, cover=None, source=base["source"] + "#noncomp"))
    return out


def eu_result_links(html: str) -> List[str]:
    return sorted(set(re.findall(r'href="(/news-and-media/news/results-[^"]+_en)"', html)))


# ═══════════════════════ flows ═══════════════════════
def bond_redemptions_coupons(lines: List[dict], days: List[str], today: Optional[str] = None) -> Dict[str, Series]:
    """GROSS bond redemptions and coupons paid inside the grid (≤ today), from lines {issuer, isin, coupon (% p.a.), maturity,
    tranches [(value_date, nominal)], coupon_months (optional: 12 annual — DE, EU, FR, ES —, 6 semi-annual — IT BTP —, 3 quarterly),
    from (optional: payments before this date are left out — an issuer whose issuance records start later than its lines, so the flow
    stays two-sided from the same date on both sides)}:
    outstanding(d) = Σ tranches settled ≤ d; redemption = outstanding at maturity; coupons on the maturity day/month and every coupon_months
    before it within the year, each = outstanding × coupon × coupon_months/12, the first one pro-rata ACT/365 from the first value date
    (short first coupon; a long-first-coupon line shifts that fraction of a coupon by one period); payment on the next weekday when the
    date is a weekend (roll_bd). Zero-coupon lines pay no coupon. Nothing is netted of Eurosystem holdings (GBP desk decision: gross in this
    phase). Returns bond_redeemed_all, coupons_paid_all and the per-issuer bond_redeemed_<iss> / coupons_paid_<iss>."""
    if not days:
        return {"bond_redeemed_all": [], "coupons_paid_all": []}
    today = min(today or date.today().isoformat(), days[-1])
    red: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    cpn: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for l in lines:
        tr = sorted(l.get("tranches") or [])
        m, c, iss = l.get("maturity"), l.get("coupon") or 0.0, l["issuer"]
        if not tr or not m:
            continue
        start = max(days[0], l.get("from") or "")
        outstanding = lambda d: sum(n for vd, n in tr if vd <= d)
        pay = roll_bd(m)
        if start <= pay <= today and outstanding(m):
            red[iss][pay] += outstanding(m)
        if not c:
            continue
        months = int(l.get("coupon_months") or 12)
        first, frac = tr[0][0], None
        dates = set()
        for yy in range(int(first[:4]), int(m[:4]) + 1):
            for k in range(12 // months):
                mo = int(m[5:7]) - k * months
                try:
                    dates.add(date(yy - (mo <= 0), mo + 12 * (mo <= 0), int(m[8:10])).isoformat())
                except ValueError:
                    continue
        for cd in sorted(dates):
            if not (first < cd <= m):
                continue
            frac = min(1.0, (date.fromisoformat(cd) - date.fromisoformat(first)).days / (365.0 * months / 12.0)) if frac is None else 1.0  # first coupon pro-rata, then full
            pay = roll_bd(cd)
            if start <= pay <= today:
                cpn[iss][pay] += outstanding(cd) * c / 100.0 * months / 12.0 * frac
    out: Dict[str, Series] = {}
    all_red: Dict[str, float] = defaultdict(float)
    all_cpn: Dict[str, float] = defaultdict(float)
    for iss, m_ in red.items():
        out["bond_redeemed_%s" % iss] = _bucket(m_)
        for d, v in m_.items():
            all_red[d] += v
    for iss, m_ in cpn.items():
        out["coupons_paid_%s" % iss] = _bucket(m_)
        for d, v in m_.items():
            all_cpn[d] += v
    out["bond_redeemed_all"], out["coupons_paid_all"] = _bucket(all_red), _bucket(all_cpn)
    return out


def issuance_flows(recs: List[dict], days: List[str], lines: Optional[List[dict]] = None) -> Dict[str, Series]:
    """net_issuance_private_daily = − settled + bill maturities + bond redemptions + coupons (the last two from `lines`, GROSS, see bond_redemptions_coupons)"""
    today = min(date.today().isoformat(), days[-1]) if days else date.today().isoformat()  # the flow cut never runs past the grid
    settled: Dict[str, float] = defaultdict(float)
    by_iss: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    bill_mat: Dict[str, float] = defaultdict(float)
    bill_by_iss: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    cov: Dict[str, List[float]] = defaultdict(list)
    for r in recs:
        s, cash, nom = r.get("settlement"), _num(r.get("cash")), _num(r.get("nominal"))
        if not s or not nom:
            continue
        cash = cash or nom
        settled[s] += cash
        by_iss[r["issuer"]][s] += cash
        if r.get("kind") == "bill" and r.get("maturity"):
            bill_mat[r["maturity"]] += nom
            bill_by_iss[r["issuer"]][r["maturity"]] += nom
        c = _num(r.get("cover"))
        if c is not None and r.get("auction"):
            cov[r["auction"]].append(c)
    net: Dict[str, float] = defaultdict(float)
    for d, v in settled.items():
        if d <= today:
            net[d] -= v
    for d, v in bill_mat.items():
        if d <= today:
            net[d] += v
    bonds = bond_redemptions_coupons(lines or [], days, today)
    for k in ("bond_redeemed_all", "coupons_paid_all"):
        for d, v in bonds[k]:
            net[d] += v
    out = {"settled_all": _bucket({d: -v for d, v in settled.items() if d <= today}), "bills_matured_all": _bucket({d: v for d, v in bill_mat.items() if d <= today}),
           "net_issuance_private_daily": _dense(_bucket(net), days), "settlements_ahead": _bucket({d: v for d, v in settled.items() if d > today}),
           "bill_maturities_ahead": _bucket({d: v for d, v in bill_mat.items() if d > today}),
           "tender_coverage": clean(sorted((d, round(sum(v) / len(v), 3)) for d, v in cov.items()))}
    out.update(bonds)
    for iss, m in by_iss.items():
        out["settled_%s" % iss] = _bucket({d: -v for d, v in m.items() if d <= today})
    for iss, m in bill_by_iss.items():
        out["bills_matured_%s" % iss] = _bucket({d: v for d, v in m.items() if d <= today})
    return out


def weekly_on(daily: Series, grid: List[str]) -> Series:
    if not grid:
        return []
    out, prev = [], None
    dd = clean(daily)
    for g in grid:
        if prev is None:
            prev = g
            continue
        out.append((g, round(sum(v for d, v in dd if prev < d <= g), 3)))
        prev = g
    return out


def de_calendar(outstanding: List[dict], horizon_days: int = 365, back_days: int = 60) -> Dict[str, Series]:
    """gross redemptions and annual coupons by line (Eurosystem holdings not deducted); ILB coupons on the real coupon (indexation ignored)"""
    today = date.today()
    end = (today + timedelta(days=horizon_days)).isoformat()
    start = (today - timedelta(days=back_days)).isoformat()
    red: Dict[str, float] = defaultdict(float)
    cpn: Dict[str, float] = defaultdict(float)
    for l in outstanding:
        m, n, c = l.get("maturity"), l.get("nominal") or 0.0, l.get("coupon")
        if not m or not n or "strip" in str(l.get("type", "")).lower():
            continue
        if today.isoformat() < m <= end:
            red[m] += n
        if c:
            for yy in range(int(start[:4]), int(end[:4]) + 1):
                try:
                    d = date(yy, int(m[5:7]), int(m[8:10])).isoformat()
                except ValueError:
                    continue
                if start <= d <= end and d <= m:
                    cpn[d] += n * c / 100.0
    tday = today.isoformat()
    return {"de_redemptions_gross_ahead": _bucket(red), "de_coupons_gross_paid": _bucket({d: v for d, v in cpn.items() if d <= tday}), "de_coupons_gross_ahead": _bucket({d: v for d, v in cpn.items() if d > tday}),
            "de_outstanding_total": [(outstanding[0]["asof"], round(sum(l.get("nominal") or 0.0 for l in outstanding if "strip" not in str(l.get("type", "")).lower()), 3))] if outstanding else []}


def de_supply_ahead(cal: List[dict]) -> Series:
    today = date.today().isoformat()
    m: Dict[str, float] = defaultdict(float)
    for c in cal:
        if c.get("date") and c["date"] > today and c.get("volume"):
            m[bd_add(c["date"], 2)] += c["volume"]
    return _bucket(m)
