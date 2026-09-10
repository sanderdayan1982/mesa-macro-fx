"""ESM / EFSF issuance (verified 2026-09-10).

Sources:
  esm.europa.eu 'Transactions' table export (fixture fixtures/eur_hist/esm/esm_transactions_outstanding_2026-09-10.csv, OUTSTANDING issues only):
    Issuer, ISIN code, Instrument (Bill|Bond), Type (New|Tap), Pricing/Auction (dd/mm/yyyy), Amount bn, Currency, Tenor, Maturity, Coupon %,
    Weighted average yield %, Average Price %, Bid/Cover. Amounts in BILLIONS → converted to EUR millions here. USD bonds are excluded from the
    EUR calendar (listed in '_non_eur'). Rows with an empty Issuer are labelled 'ESM/EFSF'.
  Deutsche Bundesbank press releases for the ESM bill auctions (the Bundesbank runs the auctions through the ESM Bidding System):
    list https://www.bundesbank.de/en/press/press-releases/esm (10 items per page; paginated through
    https://www.bundesbank.de/action/en/756324/bbksearch?pageNumString=<n>, page 0 = first; 1 122 results on 2026-09-10), items
    <li class="resultlist__item"> with a teasable__downloadheadline title, a metadata__date (dd.mm.yyyy) and an
    <a href="/resource/blob/.../YYYY-MM-DD-(announcement|invitation|auction-result)-download.pdf">. The announcement PDF gives the value date and
    the ISIN, the result PDF the allotment / average price / cover. PDFs are text (pdfplumber in the runner).
Calendars are GROSS (holdings by ISIN not published). Bills settle T+2 (auction Tuesday → value date Thursday)."""
from __future__ import annotations
import csv
import io
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional
from .series import Series
from .ops_eur import _num, _iso, _bucket, _MON_EN, merge_records

BBK_LIST = "https://www.bundesbank.de/en/press/press-releases/esm"
BBK_SEARCH = "https://www.bundesbank.de/action/en/756324/bbksearch?pageNumString=%d"
BBK_BASE = "https://www.bundesbank.de"


# ═══════════════════════ ESM transactions CSV ═══════════════════════
def parse_esm_transactions_csv(text: str) -> List[dict]:
    """{issuer, isin, instrument ('Bill'|'Bond'), type, pricing (ISO), amount (m), currency, tenor, maturity (ISO), coupon, yield, price, cover}"""
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        isin = (r.get("ISIN code") or "").strip()
        if not isin:
            continue
        amt = _num(r.get("Amount bn"))
        inst = (r.get("Instrument") or "").strip().title()
        out.append({"issuer": (r.get("Issuer") or "").strip() or "ESM/EFSF", "isin": isin, "instrument": "Bill" if inst.startswith("Bill") else "Bond",
                    "type": (r.get("Type") or "").strip(), "pricing": _iso(r.get("Pricing/Auction")) or "", "amount": round(amt * 1000.0, 3) if amt is not None else None,
                    "currency": (r.get("Currency") or "").strip().upper() or "EUR", "tenor": (r.get("Tenor") or "").strip(), "maturity": _iso(r.get("Maturity")) or "",
                    "coupon": _num(r.get("Coupon %")), "yield": _num(r.get("Weighted average yield %")), "price": _num(r.get("Average Price %")), "cover": _num(r.get("Bid/Cover"))})
    return out


def esm_calendar(rows: List[dict], horizon_days: int = 365, back_days: int = 60, today: Optional[date] = None) -> Dict[str, Series]:
    """EUR only: esm_redemptions_ahead (bills + bonds), esm_coupons_paid / esm_coupons_ahead (annual on the maturity day-of-month, amount × coupon / 100,
    bonds only), esm_outstanding_total [(today, Σ EUR)]; '_non_eur' = ISINs excluded (USD)"""
    today = today or date.today()
    tday = today.isoformat()
    end = (today + timedelta(days=horizon_days)).isoformat()
    start = (today - timedelta(days=back_days)).isoformat()
    red: Dict[str, float] = defaultdict(float)
    cpn: Dict[str, float] = defaultdict(float)
    non_eur, tot = [], 0.0
    for l in rows:
        if l.get("currency", "EUR") != "EUR":
            non_eur.append(l.get("isin"))
            continue
        m, n, c = l.get("maturity"), l.get("amount") or 0.0, l.get("coupon")
        if not n:
            continue
        tot += n
        if not m:
            continue
        if tday < m <= end:
            red[m] += n
        if c and l.get("instrument") == "Bond":
            for yy in range(int(start[:4]), int(end[:4]) + 1):
                try:
                    d = date(yy, int(m[5:7]), int(m[8:10])).isoformat()
                except ValueError:
                    continue
                if start <= d <= end and d <= m:
                    cpn[d] += n * c / 100.0
    return {"esm_redemptions_ahead": _bucket(red), "esm_coupons_paid": _bucket({d: v for d, v in cpn.items() if d <= tday}),
            "esm_coupons_ahead": _bucket({d: v for d, v in cpn.items() if d > tday}), "esm_outstanding_total": [(tday, round(tot, 3))] if rows else [],
            "_non_eur": non_eur}


# ═══════════════════════ Bundesbank press list ═══════════════════════
def bundesbank_list_url(page: int) -> str:
    return BBK_SEARCH % page


def _kind(title: str, url: str) -> str:
    t, u = title.lower(), url.lower()
    if "auction-result" in u or "auction result" in t or "result" in t:
        return "result"
    if "invitation" in u or "invitation" in t:
        return "invitation"
    if "announcement" in u or "announcement" in t:
        return "announcement"
    return "other"


def bundesbank_list_links(html: str) -> List[dict]:
    """{date (ISO), title, url (absolute), kind ('announcement'|'invitation'|'result'|'other'), issuer ('ESM'|'EFSF')} per resultlist__item"""
    out = []
    for item in re.findall(r'<li class="resultlist__item[^"]*">(.*?)</li>', html, flags=re.S):
        mt = re.search(r'teasable__downloadheadline[^>]*>(.*?)</div>', item, flags=re.S)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", mt.group(1) if mt else "")).strip()
        md = re.search(r'metadata__date">\s*(\d{2}\.\d{2}\.\d{4})', item)
        mu = re.search(r'<a[^>]+href="([^"]+)"', item)
        if not mu:
            continue
        href = mu.group(1)
        url = href if href.startswith("http") else BBK_BASE + href
        d = _iso(md.group(1)) if md else None
        if not d:
            mm = re.search(r"/(\d{4}-\d{2}-\d{2})-", href)
            d = mm.group(1) if mm else ""
        out.append({"date": d, "title": title, "url": url, "kind": _kind(title, url), "issuer": "EFSF" if "efsf" in title.lower() else "ESM"})
    return out


# ═══════════════════════ PDFs ═══════════════════════
def _long_date(s: str) -> Optional[str]:
    """'Tuesday, 1 September 2026' / '3 December 2026' → ISO"""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s or "")
    if m and m.group(2).lower() in _MON_EN:
        return "%s-%02d-%02d" % (m.group(3), _MON_EN[m.group(2).lower()], int(m.group(1)))
    return None


def _issuer(text: str) -> str:
    head = text[:600].upper()
    return "EFSF" if "EFSF" in head or "FINANCIAL STABILITY FACILITY" in head else "ESM"


def _tenor(text: str) -> str:
    m = re.search(r"(\d+-months? Bills)", text)
    return m.group(1) if m else ""


def _maturity(text: str):
    m = re.search(r"Maturity:\s*(\d{1,2} [A-Za-z]+ \d{4})\s*(?:\((\d+) interest days\))?", text)
    return (_long_date(m.group(1)) if m else None), (int(m.group(2)) if m and m.group(2) else None)


def parse_esm_announcement(text: str) -> dict:
    """{issuer, tenor, auction_date, value_date, maturity, days, isin, envisaged (EUR m)}"""
    mat, days = _maturity(text)
    mb = re.search(r"Bidding period:\s*([A-Za-z]+,\s*\d{1,2} [A-Za-z]+ \d{4})", text)
    mv = re.search(r"Value date:\s*([A-Za-z]+,\s*\d{1,2} [A-Za-z]+ \d{4})", text)
    mi = re.search(r"ISIN:\s*([A-Z]{2}[A-Z0-9]{10})", text)
    me = re.search(r"[Uu]p to EUR\s*([\d.,]+)\s*(billion|million)", text)
    env = None
    if me:
        v = _num(me.group(1))
        env = round(v * (1000.0 if me.group(2) == "billion" else 1.0), 3) if v is not None else None
    return {"issuer": _issuer(text), "tenor": _tenor(text), "auction_date": _long_date(mb.group(1)) if mb else None, "value_date": _long_date(mv.group(1)) if mv else None,
            "maturity": mat, "days": days, "isin": mi.group(1) if mi else None, "envisaged": env}


def _amt(text: str, label: str) -> Optional[float]:
    m = re.search(re.escape(label) + r"\s*€\s*([\d,\.]+)\s*mn", text)
    return _num(m.group(1)) if m else None


def _pct(text: str, label: str) -> Optional[float]:
    m = re.search(re.escape(label) + r"\s*(-?[\d.]+)\s*%", text)
    return _num(m.group(1)) if m else None


def parse_esm_result(text: str) -> dict:
    """{issuer, tenor, auction_date, maturity, interest_days, isin, bids, competitive, noncompetitive, allotted, highest_yield, avg_yield, avg_price, cover}"""
    mat, days = _maturity(text)
    ma = re.search(r"result of the auction of\s*(\d{1,2} [A-Za-z]+ \d{4})", text)
    mi = re.search(r"ISIN:\s*([A-Z]{2}[A-Z0-9]{10})", text)
    mc = re.search(r"Cover ratio\s*([\d.,]+)", text)
    return {"issuer": _issuer(text), "tenor": _tenor(text), "auction_date": _long_date(ma.group(1)) if ma else None, "maturity": mat, "interest_days": days,
            "isin": mi.group(1) if mi else None, "bids": _amt(text, "Bids"), "competitive": _amt(text, "Competitive bids"), "noncompetitive": _amt(text, "Non-competitive bids"),
            "allotted": _amt(text, "Allotment / Issue volume"), "highest_yield": _pct(text, "Highest accepted yield"), "avg_yield": _pct(text, "Weighted average yield"),
            "avg_price": _pct(text, "Average price"), "cover": _num(mc.group(1)) if mc else None}


def esm_bill_records(announcements: List[dict], results: List[dict]) -> List[dict]:
    """REC_COLS records: settlement = value date of the announcement with the same ISIN (else maturity − interest days, source '#derived')"""
    ann = {a["isin"]: a for a in announcements if a.get("isin")}
    out = []
    for r in results:
        isin, nom = r.get("isin"), r.get("allotted")
        if not isin or not nom or not r.get("auction_date"):
            continue
        a = ann.get(isin)
        src = "esm_bbk:" + isin
        if a and a.get("value_date"):
            s = a["value_date"]
        elif r.get("maturity") and r.get("interest_days"):
            s = (date.fromisoformat(r["maturity"]) - timedelta(days=int(r["interest_days"]))).isoformat()
            src += "#derived"
        else:
            continue
        price = r.get("avg_price")
        out.append({"issuer": r.get("issuer") or (a or {}).get("issuer") or "ESM", "kind": "bill", "isin": isin, "auction": r["auction_date"], "settlement": s,
                    "maturity": r.get("maturity") or (a or {}).get("maturity") or "", "nominal": nom, "cash": round(nom * price / 100.0, 3) if price else nom,
                    "cover": r.get("cover"), "yield": r.get("avg_yield"), "source": src})
    return out


def merge_esm_archive(path: str, records: List[dict]) -> List[dict]:
    return merge_records(path, records)
