"""Source adapters (LiquidityProvider pattern). Each provider returns {key: Series} and can run from live HTTP
or from fixture CSVs (offline / test mode). Add a provider per central bank when scaling the desk."""
from __future__ import annotations
import csv
import io
import os
import time
from typing import Dict, List, Optional
from .series import Series, clean

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

UA = {"User-Agent": "MesaMacroFX/0.3 (+github.com/sanderdayan1982)"}


class ProviderError(Exception):
    pass


def _get(url: str, timeout: int = 30, retries: int = 3, as_json: bool = True):
    if requests is None:
        raise ProviderError("requests not installed")
    last_err: Optional[Exception] = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code != 200:
                raise ProviderError("HTTP %s for %s" % (r.status_code, url))
            return r.json() if as_json else r.text
        except Exception as e:  # noqa
            last_err = e
            time.sleep(2 + 2 * i)
    raise ProviderError("failed after %d tries: %s" % (retries, last_err))


# ───────────────────────── Bank of Canada Valet ─────────────────────────
class ValetProvider:
    name = "valet"

    def __init__(self, base_url: str = "https://www.bankofcanada.ca/valet", fixtures_dir: Optional[str] = None):
        self.base = base_url.rstrip("/")
        self.fixtures_dir = fixtures_dir

    def fetch(self, ids: List[str], start_date: Optional[str] = None, recent: Optional[int] = None) -> Dict[str, Series]:
        if self.fixtures_dir:
            return self._from_fixtures(ids)
        q = "?start_date=%s" % start_date if start_date else ("?recent=%d" % (recent or 60))
        url = "%s/observations/%s/json%s" % (self.base, ",".join(ids), q)
        j = _get(url)
        return self.parse(j, ids)

    def labels(self, ids: List[str]) -> Dict[str, str]:
        """Series labels for id-drift validation (label must match config label on every live run)."""
        if self.fixtures_dir:
            return {}
        out = {}
        for sid in ids:
            try:
                j = _get("%s/series/%s/json" % (self.base, sid))
                out[sid] = j.get("seriesDetails", {}).get("label", "")
            except Exception:
                out[sid] = ""
        return out

    @staticmethod
    def parse(j: dict, ids: List[str]) -> Dict[str, Series]:
        out: Dict[str, List] = {i: [] for i in ids}
        for o in j.get("observations", []):
            d = o.get("d")
            for sid in ids:
                cell = o.get(sid)
                if cell and cell.get("v") not in (None, ""):
                    try:
                        out[sid].append((d, float(cell["v"])))
                    except ValueError:
                        pass
        return {k: clean(v) for k, v in out.items()}

    def _from_fixtures(self, ids: List[str]) -> Dict[str, Series]:
        out: Dict[str, Series] = {i: [] for i in ids}
        for fn in os.listdir(self.fixtures_dir):
            if not fn.endswith(".csv") or fn.startswith("receiver_general"):
                continue
            with open(os.path.join(self.fixtures_dir, fn), encoding="utf-8") as f:
                rd = csv.DictReader(f)
                cols = [c for c in (rd.fieldnames or []) if c in ids]
                if not cols:
                    continue
                for row in rd:
                    for c in cols:
                        v = row.get(c, "")
                        if v not in ("", None):
                            out[c].append((row["date"], float(v)))
        return {k: clean(v) for k, v in out.items()}


class ValetGroupProvider:
    """Valet group observations (operation-level tables: term repos, OR/ORR, Receiver General auctions, T-bill / bond
    auctions, repurchases). Verified 2026-09-10: the data live at /observations/group/<G>/json; /groups/<G>/json is
    metadata only. Fixture mode reads fixtures/<ccy>/<GROUP>.csv (one row per operation, columns = series names)."""
    name = "valet_group"

    def __init__(self, base_url: str = "https://www.bankofcanada.ca/valet", fixtures_dir: Optional[str] = None):
        self.base = base_url.rstrip("/")
        self.fixtures_dir = fixtures_dir

    def fetch(self, group: str, start_date: Optional[str] = None) -> List[dict]:
        from .ops_cad import parse_group_json, rows_from_csv
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, "%s.csv" % group)
            if not os.path.exists(p):
                return []
            return rows_from_csv(open(p, encoding="utf-8").read())
        q = "?start_date=%s" % start_date if start_date else ""
        j = _get("%s/observations/group/%s/json%s" % (self.base, group, q), timeout=90)
        return parse_group_json(j)


class MarketOpsIndicatorsProvider:
    """Bank of Canada 'Indicators related to market operations' — daily Lynx settlement balances, OR/ORR, term repos and
    securities lending as an HTML table with a 6-business-day rolling window (no Valet series, no download; verified
    2026-09-10). run.py archives every fetch into history/cad/market_ops_indicators.csv so the daily history accumulates."""
    name = "boc_market_ops_indicators"

    def __init__(self, url: str = "https://www.bankofcanada.ca/rates/indicators/market-operations-indicators/", fixtures_dir: Optional[str] = None):
        self.url, self.fixtures_dir = url, fixtures_dir

    def fetch(self) -> Dict[str, Series]:
        from .ops_cad import parse_indicators_html, IND_KEYS
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, "market_ops_indicators.csv")
            out: Dict[str, List] = {k: [] for k in IND_KEYS.values()}
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        for k in out:
                            v = row.get(k, "")
                            if v not in ("", None):
                                out[k].append((row["date"], float(v)))
            return {k: clean(v) for k, v in out.items()}
        html = _get(self.url, as_json=False, timeout=60)
        got = parse_indicators_html(html)
        if not got.get("settlement_actual"):
            raise ProviderError("market ops indicators: settlement balances table not found (STRUCTURE CHANGE?)")
        return got


class BoeOpsProvider:
    """Bank of England operation-level XLSX (STR, ILTR, CTRF, APF gilt sales, APF maturity profile) — verified 2026-09-10.
    Fixture mode reads fixtures/gbp/boe_*.csv with the normalised column names."""
    name = "boe_ops"

    def __init__(self, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.fixtures_dir, self.raw_dir = fixtures_dir, raw_dir

    def fetch(self, kind: str) -> List[dict]:
        from .ops_gbp import BOE_FILES, FIXTURES, parse_boe_xlsx, rows_from_csv
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, FIXTURES[kind])
            return rows_from_csv(open(p, encoding="utf-8").read()) if os.path.exists(p) else []
        from .providers_chf import _http, _snapshot
        blob = _http(BOE_FILES[kind], binary=True, timeout=180)
        _snapshot(self.raw_dir, "boe_%s.xlsx" % kind, blob)
        rows = parse_boe_xlsx(blob, kind)
        if not rows:
            raise ProviderError("boe_ops %s: no rows parsed (STRUCTURE CHANGE?)" % kind)
        return rows


class DmoProvider:
    """DMO XML data reports (D1A gilts in issue, D2.2D T-bill tenders) — verified 2026-09-10: XML by direct link, no bot challenge.
    Fixture mode reads fixtures/gbp/dmo_*.csv."""
    name = "dmo_xml"

    def __init__(self, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.fixtures_dir, self.raw_dir = fixtures_dir, raw_dir

    def fetch(self, kind: str) -> List[dict]:
        from .ops_gbp import DMO_D1A, DMO_D22D, DMO_D21E, DMO_D1C, FIXTURES, parse_d1a_xml, parse_d22d_xml, parse_d21e_xml, parse_d1c_xls, rows_from_csv
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, FIXTURES[kind])
            if not os.path.exists(p):
                return []
            return parse_d1c_xls(open(p, "rb").read()) if kind == "d1c" else rows_from_csv(open(p, encoding="utf-8").read())
        from .providers_chf import _http, _snapshot
        if kind == "d1c":  # binary BIFF xls export (seed of redeemed gilts) — unverified from the sandbox (DMO unreachable there)
            blob = _http(DMO_D1C, binary=True, timeout=180)
            _snapshot(self.raw_dir, "dmo_d1c.xls", blob)
            rows = parse_d1c_xls(blob)
            if not rows:
                raise ProviderError("dmo d1c: no rows parsed (STRUCTURE CHANGE?)")
            return rows
        url = {"d1a": DMO_D1A, "d22d": DMO_D22D, "d21e": DMO_D21E}[kind]
        txt, reason = "", ""
        # two passes: plain requests, then the Chrome-impersonating ladder (curl_cffi → curl) — 2026-09-11 the runner got a non-XML
        # answer for D2.2D right after a good D1A (same host), which looks like a bot challenge on the second request. Whatever
        # comes back that is not the report is snapshotted (head) so the next diagnosis reads evidence, not a guess.
        for attempt in range(2):
            try:
                if attempt == 0:
                    txt = _http(url, timeout=180)
                else:
                    from .providers_nzd import _http as _ladder
                    txt = _ladder(url, timeout=120, retries=2)
            except Exception as e:  # noqa
                reason = str(e)
                txt = ""
            if txt and "<Data" in txt[:2000] and "ErrorDetails" not in txt[:500]:
                break
            if txt:
                reason = "non-XML answer: %r" % txt.strip()[:120]
                _snapshot(self.raw_dir, "dmo_%s_rejected_%d.txt" % (kind, attempt), txt[:20000].encode("utf-8", errors="replace"))
            time.sleep(5)
        else:
            raise ProviderError("dmo %s: not an XML data report (bot challenge or STRUCTURE CHANGE?) — %s" % (kind, reason))
        _snapshot(self.raw_dir, "dmo_%s.xml" % kind, txt.encode("utf-8"))
        rows = {"d1a": parse_d1a_xml, "d22d": parse_d22d_xml, "d21e": parse_d21e_xml}[kind](txt)
        if not rows:
            raise ProviderError("dmo %s: no rows parsed" % kind)
        return rows


# ───────────────────── Receiver General Daily Cash Balance ─────────────────────
class ReceiverGeneralProvider:
    """Public Services and Procurement Canada — Daily Cash Balance (open.canada.ca dataset 477bf61b…).
    Columns: date, closing cash balance at BoC (CAD), term deposits outstanding (CAD), prudential liquidity fund (CAD).
    Values converted to CAD millions to match Valet units."""
    name = "receiver_general"
    KEYS = ["rg_closing_balance", "rg_term_deposits", "rg_prudential_fund"]

    def __init__(self, csv_current: str, csv_archive: str, fixtures_dir: Optional[str] = None):
        self.csv_current, self.csv_archive, self.fixtures_dir = csv_current, csv_archive, fixtures_dir

    def fetch(self, include_archive: bool = True) -> Dict[str, Series]:
        texts: List[str] = []
        if self.fixtures_dir:
            for fn in ("receiver_general_archive.csv", "receiver_general_current.csv"):
                p = os.path.join(self.fixtures_dir, fn)
                if os.path.exists(p):
                    texts.append(open(p, encoding="utf-8").read())
        else:
            if include_archive:
                try:
                    texts.append(_get(self.csv_archive, as_json=False))
                except ProviderError:
                    pass  # archive optional; current file is mandatory
            texts.append(_get(self.csv_current, as_json=False))
        return self.parse("\n".join(texts))

    @classmethod
    def parse(cls, text: str) -> Dict[str, Series]:
        out: Dict[str, List] = {k: [] for k in cls.KEYS}
        for line in io.StringIO(text):
            line = line.strip()
            if not line or line.startswith("Cash-Business") or line.startswith("PLACEHOLDER"):
                continue
            parts = line.split(",")
            if len(parts) < 2 or len(parts[0]) != 10:
                continue
            d = parts[0]
            for k, idx in zip(cls.KEYS, (1, 2, 3)):
                if idx < len(parts) and parts[idx] not in ("", None):
                    try:
                        out[k].append((d, round(float(parts[idx]) / 1e6, 3)))
                    except ValueError:
                        pass
        return {k: clean(v) for k, v in out.items()}


# ───────────────────── Bank of Canada RSS wire (optional) ─────────────────────
def fetch_rss(feeds: List[dict], limit: int = 20) -> List[dict]:
    import re
    items: List[dict] = []
    for feed in feeds:
        try:
            xml = _get(feed["url"], as_json=False, retries=1, timeout=12)
        except Exception:
            continue
        for m in re.finditer(r"<item>([\s\S]*?)</item>", xml, re.I):
            block = m.group(1)
            t = re.search(r"<title><!\[CDATA\[(.*?)\]\]>|<title>(.*?)</title>", block)
            l = re.search(r"<link>(.*?)</link>", block)
            p = re.search(r"<pubDate>(.*?)</pubDate>", block)
            if t and l:
                items.append({"title": (t.group(1) or t.group(2) or "").strip(), "link": l.group(1).strip(),
                              "pubDate": p.group(1).strip() if p else "", "feed": feed["name"], "blocks": feed.get("blocks", [])})
    return items[:limit]


# ───────────────────────── Bank of England IADB (Interactive Database) ─────────────────────────
_MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def iadb_date(s: str) -> Optional[str]:
    """'03 Sep 2026' -> '2026-09-03' (locale-independent)."""
    try:
        d, m, y = s.strip().split()
        return "%s-%02d-%02d" % (y, _MONTHS[m[:3].title()], int(d))
    except Exception:
        return None


class IadbProvider:
    """BoE IADB CSV export (fromshowcolumns.asp). Rules (Desk Standard, GBP v0.2): ONE request per batch with all codes,
    identifiable User-Agent, >= 2 s between requests, never parallel. An invalid code makes the endpoint answer HTML for
    the whole batch -> ProviderError (caller marks the batch degraded and keeps the last good JSON)."""
    name = "boe_iadb"
    MIN_GAP_S = 2.5

    def __init__(self, base_url: str = "https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp", fixtures_dir: Optional[str] = None,
                 raw_dir: Optional[str] = None):
        self.base, self.fixtures_dir, self.raw_dir = base_url, fixtures_dir, raw_dir
        self._last = 0.0

    @staticmethod
    def _fmt(d: str) -> str:  # 2026-09-08 -> 08/Sep/2026
        y, m, dd = d.split("-")
        return "%s/%s/%s" % (dd, list(_MONTHS)[int(m) - 1], y)

    def fetch(self, codes: List[str], date_from: str, date_to: str, titles: bool = False) -> Dict[str, Series]:
        if self.fixtures_dir:
            return self._from_fixtures(codes)
        if requests is None:
            raise ProviderError("requests not installed")
        gap = time.time() - self._last
        if gap < self.MIN_GAP_S:
            time.sleep(self.MIN_GAP_S - gap)
        url = ("%s?csv.x=yes&Datefrom=%s&Dateto=%s&SeriesCodes=%s&CSVF=%s&UsingCodes=Y&VPD=Y&VFD=N"
               % (self.base, self._fmt(date_from), self._fmt(date_to), ",".join(codes), "TT" if titles else "TN"))
        last_err: Optional[Exception] = None
        for i in range(3):
            try:
                r = requests.get(url, headers=UA, timeout=60)
                self._last = time.time()
                ct = r.headers.get("content-type", "")
                if r.status_code != 200:
                    raise ProviderError("HTTP %s" % r.status_code)
                if "csv" not in ct.lower():
                    raise ProviderError("non-CSV answer (%s): invalid code or WAF block" % ct)
                if self.raw_dir:
                    os.makedirs(self.raw_dir, exist_ok=True)
                    with open(os.path.join(self.raw_dir, "iadb_%s_%s.csv" % (codes[0], date_to)), "w", encoding="utf-8") as f:
                        f.write(r.text)
                return self.parse(r.text, codes)
            except Exception as e:  # noqa
                last_err = e
                if "invalid code" in str(e):
                    break  # deterministic: do not hammer the WAF
                time.sleep(3 * (i + 1) + (0.5 * i))
        raise ProviderError("iadb %s: %s" % (codes[0], last_err))

    @staticmethod
    def parse(text: str, codes: List[str]) -> Dict[str, Series]:
        out: Dict[str, List] = {c: [] for c in codes}
        rd = csv.reader(io.StringIO(text))
        header: List[str] = []
        for row in rd:
            if not row:
                continue
            if row[0] == "DATE":
                header = row
                continue
            if not header or row[0] == "SERIES":
                continue
            d = iadb_date(row[0])
            if not d:
                continue
            for c, v in zip(header[1:], row[1:]):
                if c in out and v not in ("", None):
                    try:
                        out[c].append((d, float(v)))
                    except ValueError:
                        pass
        return {k: clean(v) for k, v in out.items()}

    def _from_fixtures(self, codes: List[str]) -> Dict[str, Series]:
        out: Dict[str, Series] = {c: [] for c in codes}
        for fn in sorted(os.listdir(self.fixtures_dir)):
            if fn.startswith("iadb_") and fn.endswith(".csv"):
                got = self.parse(open(os.path.join(self.fixtures_dir, fn), encoding="utf-8").read(), codes)
                for c in codes:
                    if got.get(c):
                        out[c] = clean(out[c] + got[c])
        return out


# ───────────────────────── ONS Public Sector Finances (JSON API) ─────────────────────────
class OnsProvider:
    """ONS time-series API: /economy/.../timeseries/<code>/pusf/data -> {months:[{date:'2026 JUL', value:'2723'}]}.
    Dates normalised to month-end ISO. One request per code (5 codes), 1.5 s apart."""
    name = "ons_api"

    def __init__(self, base_url: str, fixtures_dir: Optional[str] = None):
        self.base, self.fixtures_dir = base_url, fixtures_dir

    def fetch(self, codes: List[str]) -> Dict[str, Series]:
        if self.fixtures_dir:
            return self._from_fixtures(codes)
        out: Dict[str, Series] = {}
        for c in codes:
            try:
                j = _get(self.base.replace("{code}", c.lower()), timeout=40)
                out[c] = self.parse(j)
            except ProviderError as e:
                out[c] = []
                raise ProviderError("ons %s: %s" % (c, e))
            time.sleep(1.5)
        return out

    @staticmethod
    def parse(j: dict) -> Series:
        import calendar as _cal
        out = []
        for m in j.get("months", []):
            try:
                y, mon = m["date"].split()
                mi = _MONTHS[mon[:3].title()]
                d = "%s-%02d-%02d" % (y, mi, _cal.monthrange(int(y), mi)[1])
                out.append((d, float(m["value"])))
            except Exception:
                continue
        return clean(out)

    def _from_fixtures(self, codes: List[str]) -> Dict[str, Series]:
        out: Dict[str, Series] = {c: [] for c in codes}
        p = os.path.join(self.fixtures_dir, "ons_psf.csv")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    for c in codes:
                        v = row.get(c, "")
                        if v not in ("", None):
                            out[c].append((row["date"], float(v)))
        return {k: clean(v) for k, v in out.items()}


# ───────────────────────── Reserve Bank of Australia — statistical tables (CSV) ─────────────────────────
class RbaProvider:
    """RBA statistical tables: https://www.rba.gov.au/statistics/tables/csv/<table>.csv
    Layout: header block (Title / Description / Frequency / Type / Units / Source / Publication date / Series ID)
    then data rows dated 'DD-Mon-YYYY' (weekly/daily) or 'DD/MM/YYYY' (monthly). Values in $ million ($ billion in D3).
    Rule (AUD v0.2): parse by 'Series ID' header (never by position); one GET per table per lane, >= 2 s apart;
    an expected id missing from the header → ProviderError (fail loudly). Fixtures: fixtures/aud/rba_<table>.csv."""
    name = "rba_tables"
    MIN_GAP_S = 2.0
    _MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

    def __init__(self, base_url: str = "https://www.rba.gov.au/statistics/tables/csv/", fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.base, self.fixtures_dir, self.raw_dir = base_url.rstrip("/") + "/", fixtures_dir, raw_dir
        self._last = 0.0

    @classmethod
    def _date(cls, s: str) -> Optional[str]:
        s = s.strip()
        try:
            if "/" in s:  # DD/MM/YYYY
                d, m, y = s.split("/")
                return "%s-%02d-%02d" % (y, int(m), int(d))
            d, m, y = s.split("-")
            return "%s-%02d-%02d" % (y, cls._MON[m[:3].title()], int(d))
        except Exception:
            return None

    def fetch(self, table_file: str, ids: List[str], since: Optional[str] = None, fixture_name: Optional[str] = None) -> Dict[str, Series]:
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, fixture_name or ("rba_%s.csv" % table_file.split("-")[0]))
            text = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
            return self.parse(text, ids, since, strict=False)
        if requests is None:
            raise ProviderError("requests not installed")
        gap = time.time() - self._last
        if gap < self.MIN_GAP_S:
            time.sleep(self.MIN_GAP_S - gap)
        url = self.base + table_file + ".csv"
        last_err: Optional[Exception] = None
        for i in range(3):
            try:
                r = requests.get(url, headers=UA, timeout=90)
                self._last = time.time()
                if r.status_code != 200:
                    raise ProviderError("HTTP %s" % r.status_code)
                text = r.content.decode("utf-8-sig", errors="replace")
                if "Series ID" not in text[:20000] and not text.startswith("DATE"):
                    raise ProviderError("unexpected payload (no 'Series ID' header)")
                if self.raw_dir:
                    os.makedirs(self.raw_dir, exist_ok=True)
                    with open(os.path.join(self.raw_dir, "rba_%s.csv" % table_file), "w", encoding="utf-8") as f:
                        f.write(text[-400000:] if len(text) > 400000 else text)
                return self.parse(text, ids, since, strict=True)
            except ProviderError as e:
                last_err = e
                if "Series ID" in str(e) or "missing" in str(e):
                    break
                time.sleep(3 * (i + 1))
            except Exception as e:  # noqa
                last_err = e
                time.sleep(3 * (i + 1))
        raise ProviderError("rba %s: %s" % (table_file, last_err))

    @classmethod
    def parse(cls, text: str, ids: List[str], since: Optional[str] = None, strict: bool = True) -> Dict[str, Series]:
        out: Dict[str, List] = {i: [] for i in ids}
        rd = csv.reader(io.StringIO(text))
        header: List[str] = []
        for row in rd:
            if not row:
                continue
            if row[0] in ("Series ID", "DATE"):
                header = [h.strip() for h in row]
                missing = [i for i in ids if i not in header]
                if missing and strict:
                    raise ProviderError("missing series ids in header: %s" % ",".join(missing))
                continue
            if not header:
                continue
            d = cls._date(row[0])
            if not d or (since and d < since):
                continue
            for c, v in zip(header[1:], row[1:]):
                if c in out and v not in ("", None):
                    try:
                        out[c].append((d, float(v)))
                    except ValueError:
                        pass
        return {k: clean(v) for k, v in out.items()}
