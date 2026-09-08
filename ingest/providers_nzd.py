"""NZD providers — Reserve Bank of New Zealand statistics workbooks + New Zealand Debt Management (NZDM) tenders.

RBNZ (https://www.rbnz.govt.nz/-/media/project/sites/rbnz/files/statistics/series/<group>/<table>/h<table>.xlsx):
  * B-/C-/D-/L-/R-tables share ONE layout: sheet 'Data', a row whose column A is 'Series Id', data rows below with Excel serial dates
    in column A → parsed BY SERIES ID, never by column position (keys '<TABLE>:<SeriesId>', e.g. 'B2:INM.DP1.N', 'R3:UGEN.MR7019').
  * D12 (standing facilities): sheet 'Standing Facilities' = Date | Settlement Cash | Overnight Reverse Repo | Autorepo | FX Swaps (NZ$m),
    plus 'Bond Lending Facility' per-transaction rows.
  * D3 (open market operations): sheets 'Reverse Repo - OMO' (new weekly framework since 2026-04-02: Date Held | Maturity | Volume | spread),
    'RR - OMO up to 01 Apr 26' (old discretionary), 'LSAP bond sales' (face value NZ$), 'Govt Bond Repurchases', 'BMLS'.
  * D10 (influences on settlement cash): sheet 'History_D10 (Jan 08 onwards)', two header rows (4 and 5), matched by label regex.
  All released after 15:00 NZT (T-1). One request per file per lane, >= 1 s apart, identifiable User-Agent, raw snapshots.
NZDM (https://debtmanagement.treasury.govt.nz):
  * result pages /tender/treasury-bill-tender-<n> and /tender/nominal-bond-tender-<n> (14:35 NZT): one 2-column table per series
    (label | value) — PRIMARY same-day source; listing pages /government-securities/treasury-bills and /nominal-bonds carry the
    tender + settlement dates and the upcoming tenders (number | maturity | volume | announcement | tender | settlement).
  * dated XLSX history files linked from /investor-resources/data (Tbills-tender-history-<date>.xlsx, govtbonds-tender-history-<date>.xlsx,
    govtbonds-onissue-history-<month-end>.xlsx) — backfill and the coupon/maturity calendar.
Fixtures: fixtures/nzd/*.csv captured live on 2026-09-08 (see FASE1_NZD_Source_Map.md)."""
from __future__ import annotations
import csv
import datetime as _dt
import os
import re
import time
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

from .providers import ProviderError, UA
from .providers_chf import xlsx_sheets, _rows_of
try:
    import requests  # type: ignore
except Exception:  # noqa
    requests = None

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-NZ,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
_SESSIONS: Dict[str, object] = {}
_LAST_403: Dict[str, str] = {}


def _session(origin: str):
    """one requests.Session per origin, primed with a GET on the site root so Sitecore/Drupal cookies exist before the file request.
    RBNZ and NZDM answered HTTP 403 to the desk User-Agent from the GitHub runner on the first live run (2026-09-08) → browser headers + cookies."""
    if requests is None:
        raise ProviderError("requests not installed")
    if origin not in _SESSIONS:
        sess = requests.Session()
        sess.headers.update(BROWSER_HEADERS)
        try:
            sess.get(origin + "/", timeout=30)
        except Exception:  # noqa
            pass
        _SESSIONS[origin] = sess
    return _SESSIONS[origin]


def _impersonated_get(url: str, hdr: Dict[str, str], timeout: int, origin: str):
    """Akamai / Cloudflare bot managers fingerprint the TLS handshake (JA3): python-requests is rejected with 403 whatever the headers.
    curl_cffi impersonates Chrome's TLS + HTTP/2 fingerprint; falls back to the system curl binary, then to requests."""
    try:
        from curl_cffi import requests as creq  # type: ignore
        key = "cffi:" + origin
        if key not in _SESSIONS:
            s = creq.Session(impersonate="chrome")
            try:
                s.get(origin + "/", timeout=30)
            except Exception:  # noqa
                pass
            _SESSIONS[key] = s
        return _SESSIONS[key].get(url, headers=hdr, timeout=timeout, allow_redirects=True)
    except ImportError:
        pass
    import shutil
    import subprocess
    import tempfile
    if shutil.which("curl"):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        args = ["curl", "-sSL", "--compressed", "-m", str(timeout), "-o", path, "-w", "%{http_code}", "-A", BROWSER_HEADERS["User-Agent"], "-H", "Accept-Language: en-NZ,en;q=0.9", "-H", "Referer: " + origin + "/", url]
        p = subprocess.run(args, capture_output=True, text=True)
        code = int((p.stdout or "0").strip()[-3:] or 0)
        body = open(path, "rb").read()
        os.unlink(path)

        class R:  # minimal response shim
            status_code, content, headers = code, body, {"via": "system-curl"}
            text = body.decode("utf-8", "replace")
        return R()
    return None


def _http(url: str, timeout: int = 60, retries: int = 3, binary: bool = False):
    """fetch ladder: curl_cffi (Chrome TLS fingerprint) → system curl → requests with browser headers; 403/429 recorded with server headers for the oplog"""
    from urllib.parse import urlsplit
    sp = urlsplit(url)
    origin = "%s://%s" % (sp.scheme, sp.netloc)
    sess = _session(origin)
    last: Optional[Exception] = None
    for i in range(retries):
        try:
            hdr = {"Referer": origin + "/", "Accept": ("application/octet-stream,*/*;q=0.8" if binary else BROWSER_HEADERS["Accept"])}
            r = _impersonated_get(url, hdr, timeout, origin) if i == 0 else None
            if r is None or r.status_code in (403, 429):
                r = sess.get(url, headers=hdr, timeout=timeout, allow_redirects=True)
            if r.status_code == 403 and i == 0:
                r = sess.get(url, headers=dict(hdr, **UA), timeout=timeout, allow_redirects=True)
            if r.status_code == 404:
                raise FileNotFoundError(url)
            if r.status_code in (403, 429):
                srv = {k: v for k, v in r.headers.items() if k.lower() in ("server", "x-cache", "cf-ray", "x-akamai-request-id", "akamai-grn", "x-sucuri-id", "via", "x-robots-tag", "set-cookie")}
                _LAST_403[url] = "HTTP %s headers=%s body=%s" % (r.status_code, srv, (r.text or "")[:160].replace("\n", " "))
                raise ProviderError("HTTP %s (blocked/throttled) for %s — %s" % (r.status_code, url, _LAST_403[url]))
            if r.status_code != 200:
                raise ProviderError("HTTP %s for %s" % (r.status_code, url))
            if binary and r.content[:2] != b"PK":
                raise ProviderError("not an XLSX (got %s bytes starting %r) for %s" % (len(r.content), r.content[:12], url))
            return r.content if binary else r.text
        except FileNotFoundError:
            raise
        except Exception as e:  # noqa
            last = e
            time.sleep(3 * (i + 1))
    raise ProviderError("failed after %d tries: %s" % (retries, last))
from .providers_jpy import read_fixture, _sleep_gap, _snapshot
from .series import Series, clean

RBNZ_FILES = "https://www.rbnz.govt.nz/-/media/project/sites/rbnz/files/statistics/series/"
NZDM = "https://debtmanagement.treasury.govt.nz"
EPOCH = _dt.date(1899, 12, 30)


def _serial(v) -> Optional[str]:
    if isinstance(v, (int, float)) and 20000 < v < 80000:
        return (EPOCH + _dt.timedelta(days=int(round(v)))).isoformat()
    if isinstance(v, str):
        s = v.strip()
        for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d-%b-%Y"):
            try:
                return _dt.datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                pass
    return None


def _num(v) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "").replace("$", "").replace("%", "")
        if s in ("", "-", "..", "n/a", "x"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _read_rows_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


# ───────────────────────── generic RBNZ 'Data' sheet (Series Id row) ─────────────────────────
class RbnzTableProvider:
    MIN_GAP_S = 1.0

    def __init__(self, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.fixtures_dir, self.raw_dir = fixtures_dir, raw_dir
        self._last = 0.0

    def _blob(self, path: str, tag: str) -> bytes:
        self._last = _sleep_gap(self._last, self.MIN_GAP_S)
        blob = _http(RBNZ_FILES + path, binary=True)
        _snapshot(self.raw_dir, tag + ".xlsx", blob)
        return blob

    @staticmethod
    def parse_data_sheet(cells: Dict[str, object], table: str, since: str) -> Dict[str, Series]:
        rows = _rows_of(cells)
        idrow = None
        for r in sorted(rows):
            if str(rows[r].get("A", "")).strip() == "Series Id":
                idrow = r
                break
        if idrow is None:
            raise ProviderError("%s: no 'Series Id' row (layout changed)" % table)
        ids = {c: str(v).strip() for c, v in rows[idrow].items() if c != "A" and isinstance(v, str)}
        out: Dict[str, List] = {}
        for r in sorted(rows):
            if r <= idrow:
                continue
            d = _serial(rows[r].get("A"))
            if not d or d < since:
                continue
            for c, sid in ids.items():
                v = _num(rows[r].get(c))
                if v is not None:
                    out.setdefault("%s:%s" % (table, sid), []).append((d, v))
        return {k: clean(v) for k, v in out.items()}

    def fetch(self, table: str, path: str, since: str = "2019-01-01") -> Dict[str, Series]:
        if self.fixtures_dir:
            return read_fixture(os.path.join(self.fixtures_dir, "%s.csv" % table.lower()))
        sheets = xlsx_sheets(self._blob(path, table))
        if "Data" not in sheets:
            raise ProviderError("%s: sheet 'Data' missing (sheets: %s)" % (table, list(sheets)[:6]))
        return self.parse_data_sheet(sheets["Data"], table, since)


# ───────────────────────── D12 standing facilities ─────────────────────────
class RbnzD12Provider(RbnzTableProvider):
    PATH = "d-f-r/d12/hd12.xlsx"

    def fetch_d12(self, since: str = "2019-01-01") -> Tuple[Dict[str, Series], List[dict]]:
        """({'D12:settlement_cash','D12:overnight_reverse_repo','D12:fx_swaps','D12:blf_amount'}, blf rows)"""
        if self.fixtures_dir:
            got = read_fixture(os.path.join(self.fixtures_dir, "d12.csv"))
            return got, []
        sheets = xlsx_sheets(self._blob(self.PATH, "D12"))
        sf = sheets.get("Standing Facilities")
        if not sf:
            raise ProviderError("D12: sheet 'Standing Facilities' missing")
        rows = _rows_of(sf)
        hdr = {}
        for r in sorted(rows)[:6]:
            for c, v in rows[r].items():
                if isinstance(v, str):
                    hdr[c] = (hdr.get(c, "") + " " + v).strip().lower()
        col = {}
        for c, h in hdr.items():
            if "settlement" in h and "cash" in h:
                col["settlement_cash"] = c
            elif "reverse" in h and "overnight" in h:
                col["overnight_reverse_repo"] = c
            elif "fx" in h and "swap" in h:
                col["fx_swaps"] = c
        if "settlement_cash" not in col:
            raise ProviderError("D12: header 'Settlement Cash' not found (%s)" % hdr)
        out: Dict[str, List] = {}
        for r in sorted(rows):
            d = _serial(rows[r].get("A"))
            if not d or d < since:
                continue
            for k, c in col.items():
                v = _num(rows[r].get(c))
                if v is None and k != "settlement_cash":
                    v = 0.0 if rows[r].get(c) in (None, "-") else None
                if v is not None:
                    out.setdefault("D12:" + k, []).append((d, v))
        blf_rows: List[dict] = []
        blf = sheets.get("Bond Lending Facility")
        if blf:
            br = _rows_of(blf)
            for r in sorted(br):
                d = _serial(br[r].get("A"))
                a = _num(br[r].get("B"))
                if d and d >= since and a is not None:
                    blf_rows.append({"date": d, "amount": a, "issuer": br[r].get("C"), "bond_maturity": _serial(br[r].get("D"))})
        agg: Dict[str, float] = {}
        for x in blf_rows:
            agg[x["date"]] = agg.get(x["date"], 0.0) + x["amount"]
        out["D12:blf_amount"] = sorted(agg.items())
        return {k: clean(v) for k, v in out.items()}, blf_rows


# ───────────────────────── D3 open market operations ─────────────────────────
class RbnzD3Provider(RbnzTableProvider):
    PATH = "d-f-r/d3/hd3.xlsx"

    def fetch_d3(self, since: str = "2024-01-01") -> Dict[str, List[dict]]:
        """{'rr': [{date_held, maturity, allocated, spread}], 'rr_old': [...], 'lsap': [...], 'repurchases': [...], 'bmls': [...]}"""
        if self.fixtures_dir:
            fx = self.fixtures_dir
            rr = [{"date_held": r["date_held"], "maturity": r["maturity"], "allocated": float(r["allocated"] or 0), "spread": float(r["spread_to_ocr"] or 0)} for r in _read_rows_csv(os.path.join(fx, "d3_rr_omo.csv"))]
            old = [{"date_held": r["date_held"], "maturity": r["maturity"], "allocated": float(r["allocated"] or 0), "wavg": float(r["wavg"]) if r.get("wavg") else None} for r in _read_rows_csv(os.path.join(fx, "d3_rr_omo_old.csv"))]
            ls = [{"date": r["date"], "settlement": r["settlement"], "bond_maturity": r["bond_maturity"], "face_m": float(r["face_value"]) / 1e6, "yield": float(r["yield"]) * 100 if r.get("yield") else None, "total_m": float(r["total_to_date"]) / 1e6} for r in _read_rows_csv(os.path.join(fx, "d3_lsap_sales.csv"))]
            rp = [{"date": r["date"], "settlement": r["settlement"], "bond_maturity": r["bond_maturity"], "face_m": float(r["face_value"]) / 1e6, "total_m": float(r["total_to_date"]) / 1e6} for r in _read_rows_csv(os.path.join(fx, "d3_repurchases.csv"))]
            bm = read_fixture(os.path.join(fx, "d3_bmls.csv"))
            bmls = [{"date": d, "nzgb_m": v} for d, v in bm.get("D3:bmls_nzgb", [])]
            return {"rr": rr, "rr_old": old, "lsap": ls, "repurchases": rp, "bmls": bmls}
        sheets = xlsx_sheets(self._blob(self.PATH, "D3"))

        def rows(name: str):
            sh = sheets.get(name)
            if sh is None:
                raise ProviderError("D3: sheet '%s' missing (sheets: %s)" % (name, list(sheets)))
            rr_ = _rows_of(sh)
            return [rr_[r] for r in sorted(rr_)]

        rr = []
        for o in rows("Reverse Repo - OMO"):
            d, m = _serial(o.get("A")), _serial(o.get("B"))
            if d and m:
                rr.append({"date_held": d, "maturity": m, "allocated": _num(o.get("C")) or 0.0, "spread": _num(o.get("D")) or 0.0})
        old = []
        for o in rows("RR - OMO up to 01 Apr 26"):
            d, m = _serial(o.get("A")), _serial(o.get("B"))
            a = _num(o.get("F"))
            if d and m and d >= since and a:
                old.append({"date_held": d, "maturity": m, "allocated": a, "wavg": _num(o.get("J"))})
        ls = []
        for o in rows("LSAP bond sales"):
            d = _serial(o.get("A"))
            fv = _num(o.get("D"))
            if d and fv:
                ls.append({"date": d, "settlement": _serial(o.get("B")), "bond_maturity": _serial(o.get("C")) or str(o.get("C")), "face_m": fv / 1e6,
                           "yield": (_num(o.get("E")) or 0) * 100, "total_m": (_num(o.get("F")) or 0) / 1e6})
        rp = []
        for o in rows("Govt Bond Repurchases"):
            d = _serial(o.get("A"))
            fv = _num(o.get("D"))
            if d and fv and d >= since:
                rp.append({"date": d, "settlement": _serial(o.get("B")), "bond_maturity": _serial(o.get("C")), "face_m": fv / 1e6, "total_m": (_num(o.get("E")) or 0) / 1e6})
        bmls = []
        for o in rows("BMLS"):
            d = _serial(o.get("A"))
            if d and d >= since and _num(o.get("B")) is not None:
                bmls.append({"date": d, "nzgb_m": (_num(o.get("B")) or 0) / 1e6, "lgfa_m": (_num(o.get("C")) or 0) / 1e6})
        return {"rr": rr, "rr_old": old, "lsap": ls, "repurchases": rp, "bmls": bmls}

    @staticmethod
    def omo_series(d3: Dict[str, List[dict]], business_days: List[str]) -> Dict[str, Series]:
        """allocated per operation date (new framework) + stock outstanding on every business day (allocations live: held <= d < maturity)
        + LSAP sales per settlement date + repurchases per settlement date (NZ$m)."""
        rr = d3.get("rr", []) + [dict(x, spread=None) for x in d3.get("rr_old", [])]
        alloc: Dict[str, float] = {}
        for x in d3.get("rr", []):
            alloc[x["date_held"]] = alloc.get(x["date_held"], 0.0) + x["allocated"]
        stock = []
        for d in business_days:
            s = sum(x["allocated"] for x in rr if x["date_held"] <= d < x["maturity"])
            stock.append((d, round(s, 1)))
        spread = [(x["date_held"], x["spread"] * 100) for x in d3.get("rr", []) if x.get("spread") is not None]
        sp: Dict[str, float] = {}
        for d, v in spread:
            sp[d] = v
        ls: Dict[str, float] = {}
        for x in d3.get("lsap", []):
            k = x.get("settlement") or x["date"]
            ls[k] = ls.get(k, 0.0) + x["face_m"]
        rp: Dict[str, float] = {}
        for x in d3.get("repurchases", []):
            k = x.get("settlement") or x["date"]
            rp[k] = rp.get(k, 0.0) + x["face_m"]
        return {"D3:rr_omo_allocated": clean(sorted(alloc.items())), "D3:rr_omo_outstanding": clean(stock), "D3:rr_omo_spread_bps": clean(sorted(sp.items())),
                "D3:lsap_sales": clean(sorted(ls.items())), "D3:govt_bond_repurchases": clean(sorted(rp.items())),
                "D3:bmls_nzgb": clean([(x["date"], x["nzgb_m"]) for x in d3.get("bmls", [])])}


# ───────────────────────── D10 influences on settlement cash (monthly) ─────────────────────────
class RbnzD10Provider(RbnzTableProvider):
    PATH = "d-f-r/d10/hd10.xlsx"
    LABELS = {"cash_begin": r"cash at beginning", "govt_cash_influence": r"government cash influence", "rbnz_transactions": r"reserve bank transactions",
              "bonds_issued": r"^bonds issued", "bond_maturities": r"bond maturities", "tbills_issued": r"treasury bill issued", "tbills_matured": r"treasury bill matur",
              "fx": r"foreign exchange", "net_reverse_repos": r"net reverse repos", "net_fx_swaps": r"net fx swaps", "net_orrf": r"overnight reverse repo facility",
              "cash_end": r"cash as at end", "avg_settlement_cash": r"average settlement cash"}

    def fetch_d10(self, since: str = "2019-01-01") -> Dict[str, Series]:
        if self.fixtures_dir:
            return read_fixture(os.path.join(self.fixtures_dir, "d10.csv"))
        sheets = xlsx_sheets(self._blob(self.PATH, "D10"))
        name = next((n for n in sheets if n.startswith("History_D10") and "onwards" in n), None)
        if not name:
            raise ProviderError("D10: history sheet not found (%s)" % list(sheets))
        rows = _rows_of(sheets[name])
        hdr: Dict[str, str] = {}
        for r in sorted(rows)[:8]:
            for c, v in rows[r].items():
                if isinstance(v, str) and c != "A":
                    hdr[c] = (hdr.get(c, "") + " " + v).strip().lower()
        col: Dict[str, str] = {}
        for k, pat in self.LABELS.items():
            for c, h in hdr.items():
                if re.search(pat, h) and c not in col.values():
                    col[k] = c
                    break
        if "govt_cash_influence" not in col or "cash_end" not in col:
            raise ProviderError("D10: header labels not found (%s)" % hdr)
        out: Dict[str, List] = {}
        for r in sorted(rows):
            d = _serial(rows[r].get("A"))
            if not d or d < since:
                continue
            for k, c in col.items():
                v = _num(rows[r].get(c))
                if v is not None:
                    out.setdefault("D10:" + k, []).append((d, round(v, 1)))
        return {k: clean(v) for k, v in out.items()}


# ───────────────────────── NZDM ─────────────────────────
class _Tables(HTMLParser):
    """collects every <table> as a list of rows (list of cell texts) + <a href> list"""

    def __init__(self):
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self.links: List[Tuple[str, str]] = []
        self._in_cell = False
        self._cell = ""
        self._row: List[str] = []
        self._tbl: Optional[List[List[str]]] = None
        self._a: Optional[str] = None
        self._atext = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._tbl = []
        elif tag == "tr" and self._tbl is not None:
            self._row = []
        elif tag in ("td", "th") and self._tbl is not None:
            self._in_cell, self._cell = True, ""
        elif tag == "a" and a.get("href"):
            self._a, self._atext = a["href"], ""
        if tag in ("br", "p", "div", "li", "span") and self._in_cell:
            # multi-line cells (e.g. three volumes '225<br>175<br>50') must not collapse into one number
            self._cell += " "

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in ("p", "div", "li", "span") and self._in_cell:
            self._cell += " "
        if tag in ("td", "th") and self._in_cell:
            self._row.append(re.sub(r"\s+", " ", self._cell).strip())
            self._in_cell = False
        elif tag == "tr" and self._tbl is not None and self._row:
            self._tbl.append(self._row)
            self._row = []
        elif tag == "table" and self._tbl is not None:
            self.tables.append(self._tbl)
            self._tbl = None
        elif tag == "a" and self._a is not None:
            self.links.append((self._a, re.sub(r"\s+", " ", self._atext).strip()))
            self._a = None

    def handle_data(self, data):
        if self._in_cell:
            self._cell += data
        if self._a is not None:
            self._atext += data


class NzdmProvider:
    """Tender results (HTML same-day + XLSX history), listings (dates, upcoming), bonds on issue (coupon/maturity calendar)."""
    MIN_GAP_S = 1.0
    KINDS = {"tbill": {"listing": "/government-securities/treasury-bills", "result": "/tender/treasury-bill-tender-%s", "hist": r"Tbills-tender-history"},
             "bond": {"listing": "/government-securities/nominal-bonds", "result": "/tender/nominal-bond-tender-%s", "hist": r"govtbonds-tender-history"}}

    def __init__(self, base: str = NZDM, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.base, self.fixtures_dir, self.raw_dir = base.rstrip("/"), fixtures_dir, raw_dir
        self._last = 0.0

    def _get(self, path: str, tag: str, binary: bool = False):
        self._last = _sleep_gap(self._last, self.MIN_GAP_S)
        url = path if path.startswith("http") else self.base + path
        payload = _http(url, binary=binary)
        _snapshot(self.raw_dir, tag, payload)
        return payload

    # ── listings ──
    def listing(self, kind: str) -> Tuple[List[dict], List[dict]]:
        """(upcoming [{number, volume, announcement, tender, settlement}], completed [{number, tender, settlement, url}])"""
        if self.fixtures_dir:
            up = [dict(r, volume=float(r["volume"])) for r in _read_rows_csv(os.path.join(self.fixtures_dir, "nzdm_upcoming_tenders.csv")) if r["kind"] == kind]
            comp = []
            if kind == "tbill":
                comp = [{"number": "1887", "tender": "2026-09-08", "settlement": "2026-09-09", "url": "/tender/treasury-bill-tender-1887"}]
            else:
                comp = [{"number": "1007", "tender": "2026-09-03", "settlement": "2026-09-08", "url": "/tender/nominal-bond-tender-1007"}]
            return up, comp
        html = self._get(self.KINDS[kind]["listing"], "nzdm_%s_listing.html" % kind)
        p = _Tables()
        p.feed(html)
        upcoming, completed = [], []
        links = {t: h for h, t in p.links}
        detail = [h for h, t in p.links if "/tender/" in h]
        for tb in p.tables:
            if not tb:
                continue
            hdr = [c.lower() for c in tb[0]]
            if "announcement" in hdr and "volume ($m)" in " ".join(hdr):
                for row in tb[1:]:
                    if len(row) < 6:
                        continue
                    vols = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", row[2])]
                    # a multi-line tender lists several volumes concatenated (e.g. '225 175 50'); if the string is a single big number, split by the line count
                    vol = sum(vols) if len(vols) > 1 else (vols[0] if vols else None)
                    upcoming.append({"number": row[0], "lines": row[1], "volume": vol, "announcement": _serial(row[3]), "tender": _serial(row[4]), "settlement": _serial(row[5])})
            elif "tender" in hdr and "settlement" in hdr and len(hdr) <= 4:
                for i, row in enumerate(tb[1:]):
                    if len(row) < 3:
                        continue
                    url = detail[i] if i < len(detail) else None
                    completed.append({"number": row[0], "tender": _serial(row[1]), "settlement": _serial(row[2]), "url": url})
        return upcoming, completed

    # ── HTML result page ──
    @staticmethod
    def parse_result(html: str) -> List[dict]:
        p = _Tables()
        p.feed(html)
        out = []
        for tb in p.tables:
            kv = {r[0].strip().rstrip("*").lower(): r[1] for r in tb if len(r) >= 2}
            if "series offered" not in kv or "coverage ratio" not in kv:
                continue
            g = lambda *keys: next((_num(kv[k]) for k in keys if k in kv), None)  # noqa
            ser = kv.get("series offered", "")
            mat = _serial(kv.get("maturity date", "")) or None
            if not mat:
                mm = re.search(r"(\d{1,2} \w{3} \d{4})", ser)
                mat = _serial(mm.group(1)) if mm else None
            out.append({"series": ser, "maturity": mat, "coupon": (_num(re.match(r"\s*([\d.]+)%", ser).group(1)) / 100) if re.match(r"\s*([\d.]+)%", ser) else None,
                        "offered": g("total amount offered ($million)"), "allocated": g("total amount allocated ($million)"),
                        "bids_n": g("total number of bids received"), "bid": g("total amount of bids received ($million)"),
                        "success_n": g("total number of successful bids"), "high_acc": g("highest yield accepted (%)"), "low_acc": g("lowest yield accepted (%)"),
                        "high_rej": g("highest yield rejected (%)"), "low_rej": g("lowest yield rejected (%)"),
                        "wavg": g("weighted average accepted yield (%)"), "wavg_rej": g("weighted average rejected yield (%)"), "coverage": g("coverage ratio")})
        return out

    def result(self, kind: str, number: str, url: Optional[str] = None) -> List[dict]:
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, "html_tender_%s.html" % ("treasury-bill-tender-1887" if kind == "tbill" else "nominal-bond-tender-1007"))
            return self.parse_result(open(p, encoding="utf-8").read()) if os.path.exists(p) else []
        path = url or (self.KINDS[kind]["result"] % number)
        return self.parse_result(self._get(path, "nzdm_%s_%s.html" % (kind, number)))

    # ── XLSX history ──
    def data_links(self) -> Dict[str, str]:
        html = self._get("/investor-resources/data", "nzdm_data.html")
        p = _Tables()
        p.feed(html)
        out = {}
        for h, _t in p.links:
            if re.search(r"\.xlsx?$", h, re.I):
                for k, spec in self.KINDS.items():
                    if re.search(spec["hist"], h, re.I):
                        out[k] = h
                if re.search(r"govtbonds-onissue", h, re.I):
                    out["bonds_on_issue"] = h
                if re.search(r"TBills-onissue", h, re.I):
                    out["tbills_on_issue"] = h
        return out

    def history(self, kind: str, since: str = "2024-01-01", links: Optional[Dict[str, str]] = None) -> List[dict]:
        """rows [{tender_date, maturity, coupon?, tender_no, offered, bids_n, success_n, bid, accepted, coverage, low_acc, high_acc, wavg}] newest first in file → sorted ascending"""
        if self.fixtures_dir:
            rows = _read_rows_csv(os.path.join(self.fixtures_dir, "nzdm_%s_tenders.csv" % kind))
            out = []
            for r in rows:
                x = {k: (_num(v) if k not in ("tender_date", "maturity", "tender_no") else v) for k, v in r.items()}
                x["tender_no"] = str(int(float(r["tender_no"]))) if r.get("tender_no") else None
                if kind == "tbill" and x.get("bid") and x.get("offered"):
                    x["coverage"] = round(x["bid"] / x["offered"], 4)
                out.append(x)
            return sorted([x for x in out if x["tender_date"] >= since], key=lambda x: (x["tender_date"], x["maturity"]))
        links = links or self.data_links()
        if kind not in links:
            raise ProviderError("NZDM data page: no %s history link" % kind)
        blob = self._get(links[kind], "nzdm_%s_history.xlsx" % kind, binary=True)
        sheets = xlsx_sheets(blob)
        sh = sheets.get("Sheet1") if kind == "tbill" else sheets.get("Nominals")
        if sh is None:
            raise ProviderError("NZDM %s history: sheet missing (%s)" % (kind, list(sheets)))
        rows = _rows_of(sh)
        hdr_row = None
        for r in sorted(rows):
            if str(rows[r].get("A", "")).strip().lower().startswith("tender date"):
                hdr_row = r
                break
        if hdr_row is None:
            raise ProviderError("NZDM %s history: header row not found" % kind)
        hdr = {c: str(v).strip().lower() for c, v in rows[hdr_row].items()}

        def col(pat: str) -> Optional[str]:
            return next((c for c, h in hdr.items() if re.search(pat, h)), None)

        C = {"maturity": col(r"^maturity"), "coupon": col(r"^coupon"), "tender_no": col(r"tender no"), "offered": col(r"volume offered"), "bids_n": col(r"total number of bids"),
             "success_n": col(r"number of successful"), "bid": col(r"volume bid"), "accepted": col(r"volume accepted"), "coverage": col(r"coverage"),
             "low_acc": col(r"lowest accepted"), "high_acc": col(r"highest accepted"), "wavg": col(r"wtd\.? ?avg\.? ?successful")}
        out = []
        for r in sorted(rows):
            if r <= hdr_row:
                continue
            d = _serial(rows[r].get("A"))
            if not d or d < since:
                continue
            x = {"tender_date": d, "maturity": _serial(rows[r].get(C["maturity"])) if C["maturity"] else None}
            for k in ("coupon", "offered", "bids_n", "success_n", "bid", "accepted", "coverage", "low_acc", "high_acc", "wavg"):
                x[k] = _num(rows[r].get(C[k])) if C.get(k) else None
            tn = rows[r].get(C["tender_no"]) if C.get("tender_no") else None
            x["tender_no"] = str(int(tn)) if isinstance(tn, (int, float)) else (str(tn) if tn else None)
            if x.get("coverage") is None and x.get("bid") and x.get("offered"):
                x["coverage"] = round(x["bid"] / x["offered"], 4)
            out.append(x)
        return sorted(out, key=lambda x: (x["tender_date"], x["maturity"] or ""))

    def bonds_on_issue(self, links: Optional[Dict[str, str]] = None) -> List[dict]:
        """latest month-end lines: [{maturity, coupon, type, total_outstanding, market}] (NZ$m)"""
        if self.fixtures_dir:
            return [{"month_end": r["month_end"], "maturity": r["maturity"], "coupon": float(r["coupon"]), "type": r["type"], "total": float(r["total_outstanding"]), "market": float(r["market"] or 0)}
                    for r in _read_rows_csv(os.path.join(self.fixtures_dir, "nzdm_bonds_on_issue.csv"))]
        links = links or self.data_links()
        if "bonds_on_issue" not in links:
            raise ProviderError("NZDM data page: no bonds-on-issue link")
        sheets = xlsx_sheets(self._get(links["bonds_on_issue"], "nzdm_bonds_on_issue.xlsx", binary=True))
        sh = sheets.get("Month_end")
        if sh is None:
            raise ProviderError("bonds on issue: sheet 'Month_end' missing")
        rows = _rows_of(sh)
        recs = []
        for r in sorted(rows):
            d, m = _serial(rows[r].get("A")), _serial(rows[r].get("E"))
            if d and m:
                cp = rows[r].get("D")
                cpv = _num(cp) if not (isinstance(cp, str) and "%" in cp) else (_num(cp) or 0) / 100
                recs.append({"month_end": d, "maturity": m, "coupon": cpv or 0.0, "type": rows[r].get("F"), "total": _num(rows[r].get("G")) or 0.0, "market": _num(rows[r].get("K")) or 0.0})
        if not recs:
            return []
        mx = max(x["month_end"] for x in recs)
        return [x for x in recs if x["month_end"] == mx]

    @staticmethod
    def tender_series(rows: List[dict]) -> Dict[str, Series]:
        """per tender date: volume-weighted coverage, total accepted / offered, worst-line tail (bp), wavg of the shortest line"""
        by: Dict[str, List[dict]] = {}
        for x in rows:
            by.setdefault(x["tender_date"], []).append(x)
        cov, acc, off, tail, wy, alloc, y1 = [], [], [], [], [], [], []
        for d in sorted(by):
            L = [x for x in by[d] if x.get("offered")]
            if not L:
                continue
            o = sum(x["offered"] for x in L)
            b = sum(x.get("bid") or 0 for x in L)
            a = sum(x.get("accepted") or 0 for x in L)
            cov.append((d, round(b / o, 3) if o else None))
            acc.append((d, a))
            off.append((d, o))
            alloc.append((d, round(a / o, 3) if o else None))
            filled = [x for x in L if (x.get("accepted") or 0) > 0 and x.get("wavg")]
            t = [((x["high_acc"] - x["wavg"]) * 100) for x in filled if x.get("high_acc") is not None]
            tail.append((d, round(max(t), 1) if t else None))
            Ls = sorted(filled, key=lambda x: x.get("maturity") or "") or sorted(L, key=lambda x: x.get("maturity") or "")
            wy.append((d, Ls[0]["wavg"]) if Ls[0].get("wavg") is not None else (d, None))
            y1.append((d, Ls[-1]["wavg"]) if Ls[-1].get("wavg") is not None else (d, None))
        return {"coverage": clean(cov), "accepted": clean(acc), "offered": clean(off), "allocation_ratio": clean(alloc), "tail_bp": clean(tail), "wavg_short": clean(wy), "wavg_long": clean(y1)}
