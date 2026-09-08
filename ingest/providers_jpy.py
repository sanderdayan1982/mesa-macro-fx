"""JPY source adapters — Bank of Japan (daily XLSX, Accounts HTML, Time-Series API, call-market XLSX), Ministry of Finance
(JGB yields CSV, auction results XLS, treasury receipts/payments XLS, ITS weekly CSV) and JSDA (Tokyo Repo Rate XLS).

Design rules (config/jpy.json v0.2, triangulated 2026-09-08):
  * daily XLSX parsed by ENGLISH LABEL (regex aliases), never by cell coordinates; expected-item assertion + structure hash →
    a changed layout degrades loudly (DATA_DEGRADED), it never remaps silently;
  * the BoJ writes the value on the Japanese row or on the English row (or both, e.g. SLF new lending vs returns) → the item
    value is the sum of both rows; an empty cell for a facility row is 'no usage' (0), handled by the block builder;
  * BoJ Accounts are in thousand yen → converted to 100 million yen with a magnitude guard (total assets 5e14–9e14 yen);
  * one request per source per lane, >= 1 s apart, raw snapshots under logs/jpy/raw; the sandbox cannot reach these hosts so
    every provider has an offline mode reading fixtures/jpy/<name>.csv in long format (date,key,value[,extra]).
Pure Python 3.9 (zipfile + xml for XLSX); legacy XLS (JSDA, MoF) needs xlrd (requirements.txt)."""
from __future__ import annotations
import csv
import hashlib
import io
import os
import re
import time
import zipfile
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET
from .series import Series, clean
from .providers import ProviderError, UA

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _sleep_gap(last: float, gap: float) -> float:
    d = time.time() - last
    if d < gap:
        time.sleep(gap - d)
    return time.time()


def _http(url: str, timeout: int = 60, retries: int = 3, binary: bool = False, encoding: Optional[str] = None):
    if requests is None:
        raise ProviderError("requests not installed")
    last_err: Optional[Exception] = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code == 404:
                raise FileNotFoundError(url)
            if r.status_code in (403, 429):
                raise ProviderError("HTTP %s (throttled) for %s" % (r.status_code, url))
            if r.status_code != 200:
                raise ProviderError("HTTP %s for %s" % (r.status_code, url))
            if binary:
                return r.content
            return r.content.decode(encoding or r.encoding or "utf-8", errors="replace")
        except FileNotFoundError:
            raise
        except Exception as e:  # noqa
            last_err = e
            time.sleep(3 * (i + 1))
    raise ProviderError("failed after %d tries: %s" % (retries, last_err))


def _snapshot(raw_dir: Optional[str], name: str, payload) -> None:
    if not raw_dir:
        return
    os.makedirs(raw_dir, exist_ok=True)
    mode = "wb" if isinstance(payload, (bytes, bytearray)) else "w"
    with open(os.path.join(raw_dir, name), mode) as f:
        f.write(payload if mode == "wb" else payload[-400000:])


def read_fixture(path: str) -> Dict[str, Series]:
    """fixtures/jpy/*.csv in either shape: long (date,key,value) or wide (date,<key1>,<key2>,...).
    'YYYY-MM' dates are normalised to month-end; empty cells are skipped (absent, never zero)."""
    import calendar as _c
    out: Dict[str, List] = {}
    if not os.path.exists(path):
        return {}

    def _d(x: str) -> str:
        x = x.strip()
        if re.match(r"^\d{4}-\d{2}$", x):
            y, m = int(x[:4]), int(x[5:7])
            return "%04d-%02d-%02d" % (y, m, _c.monthrange(y, m)[1])
        return x

    with open(path, encoding="utf-8") as f:
        rd = csv.reader(f)
        header = next(rd, None)
        if not header:
            return {}
        wide = not (len(header) == 3 and header[1].lower() == "key")
        for row in rd:
            if not row or not row[0] or row[0].startswith("#"):
                continue
            d = _d(row[0])
            if wide:
                for k, v in zip(header[1:], row[1:]):
                    if v.strip() != "":
                        try:
                            out.setdefault(k, []).append((d, float(v)))
                        except ValueError:
                            pass
            elif len(row) >= 3 and row[2].strip() != "":
                try:
                    out.setdefault(row[1], []).append((d, float(row[2])))
                except ValueError:
                    pass
    return {k: clean(v) for k, v in out.items()}


read_long_fixture = read_fixture  # backwards-compatible alias


# ───────────────────────── minimal XLSX reader (stdlib) ─────────────────────────
def xlsx_cells(blob: bytes, sheet: str = "xl/worksheets/sheet1.xml") -> Dict[str, object]:
    """{'B11': 'text' | number} for one sheet. Handles shared strings, inline strings, namespaced tags."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    ss: List[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.iter("{%s}si" % NS["m"]):
            # skip <rPh> phonetic (furigana) runs — BoJ files carry them and they would be glued onto the label text
            parts: List[str] = []
            for child in si:
                tag = child.tag.split("}")[-1]
                if tag == "t":
                    parts.append(child.text or "")
                elif tag == "r":
                    parts.extend(t.text or "" for t in child.iter("{%s}t" % NS["m"]))
            ss.append("".join(parts))
    cells: Dict[str, object] = {}
    root = ET.fromstring(z.read(sheet))
    for c in root.iter("{%s}c" % NS["m"]):
        ref = c.get("r")
        t = c.get("t")
        v = c.find("{%s}v" % NS["m"])
        if t == "s" and v is not None and v.text is not None:
            cells[ref] = ss[int(v.text)]
        elif t == "inlineStr":
            cells[ref] = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
        elif v is not None and v.text not in (None, ""):
            try:
                cells[ref] = float(v.text)
            except ValueError:
                cells[ref] = v.text
    return cells


def _collapse_errors(kind: str, errs: List[str], keep: int = 3) -> List[str]:
    """Same error text repeated for many dates → one line ('N dates, first…last'). Keeps the banner readable."""
    if len(errs) <= keep:
        return errs
    groups: Dict[str, List[str]] = {}
    for e in errs:
        m = re.match(r"^%s (\d{4}-\d{2}-\d{2}): (.*)$" % re.escape(kind), e)
        if m:
            groups.setdefault(m.group(2), []).append(m.group(1))
        else:
            groups.setdefault(e, []).append("")
    out: List[str] = []
    for msg, dates in groups.items():
        dates = [d for d in dates if d]
        if len(dates) <= keep:
            out.extend("%s %s: %s" % (kind, d, msg) for d in dates) if dates else out.append(msg)
        else:
            out.append("%s: %s (%d dates, %s … %s)" % (kind, msg, len(dates), min(dates), max(dates)))
    return out


def _rows(cells: Dict[str, object]) -> Dict[int, Dict[str, object]]:
    rows: Dict[int, Dict[str, object]] = {}
    for ref, val in cells.items():
        m = re.match(r"^([A-Z]+)(\d+)$", ref)
        if m:
            rows.setdefault(int(m.group(2)), {})[m.group(1)] = val
    return rows


# ───────────────────────── BoJ daily "Sources of Changes in CAB" (XLSX) ─────────────────────────
class BojDailyCabProvider:
    """jd (final, T-1), jx (provisional, T), jp (projection, T+1). Values: F = projection, G = provisional, H = final; 100 million yen."""
    name = "boj_daily_cab"
    MIN_GAP_S = 1.0
    # internal key -> (English label regex, is_facility_row)  — order irrelevant; aliases cover the 2025-10/2026-01/2026-06 item changes
    ITEMS: List[Tuple[str, str]] = [
        ("banknotes", r"^Banknotes"), ("treasury", r"^Treasury funds and others"), ("surplus", r"^Surplus\s*/\s*Shortage"),
        ("ops_ex_lsp", r"^BOJ Loans and Market Operations \(excluding"), ("jgb_purch", r"^Outright purchases of JGBs"),
        ("tbill_purch", r"^Outright purchases of T-Bills"), ("tbill_sales", r"^Outright sales of T-Bills"),
        ("jgs_repo_buy", r"^Purchases of JGSs under repurchase"), ("jgs_repo_sell", r"^Sales of JGSs under repurchase"),
        ("pooled_ho", r"pooled collateral \(at Head office\)"), ("pooled_all", r"pooled collateral \(at All offices\)"),
        ("cp_repo", r"^Purchases of CP under"), ("corp_bonds", r"^Outright purchases of Corporate Bonds"),
        ("disaster", r"^Funds-supplying operation to support financial institutions in disaster"), ("climate", r"^Climate response"),
        ("loans", r"^Loans$"), ("slf", r"^Securities lending as a secondary"), ("slf_usd", r"^Securities lending to provide JGSs"),
        ("lsp", r"^BOJ Loans and Market Operations \(Loan Support Program\)"), ("subtotal", r"^Subtotal"),
        ("net_change", r"^Net change in current account"), ("cab", r"^Current account balances \(amount outstanding\)"),
        ("reserve_bal", r"^Reserve balances held"), ("excess", r"^Excess reserves"),
        ("cab_nonres", r"^Current account balances held by institutions NOT"), ("mbase", r"^Monetary base"),
        ("req_cum", r"^Required reserves for the current maintenance period.*cumulative"),
        ("req_daily", r"^Required reserves for the current maintenance period.*daily average"),
        ("rem_daily", r"^Remaining required reserves.*daily average"),
    ]
    REQUIRED = ("banknotes", "treasury", "surplus", "ops_ex_lsp", "net_change", "cab", "reserve_bal", "excess", "req_daily")
    FACILITY = ("jgb_purch", "tbill_purch", "tbill_sales", "jgs_repo_buy", "jgs_repo_sell", "pooled_ho", "pooled_all", "cp_repo", "corp_bonds",
                "disaster", "climate", "loans", "slf", "slf_usd", "lsp")
    COL = {"jd": "H", "jx": "G", "jp": "F"}

    def __init__(self, base_url: str = "https://www.boj.or.jp/en/statistics/boj/fm/juq/d_release/", fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.base, self.fixtures_dir, self.raw_dir = base_url.rstrip("/") + "/", fixtures_dir, raw_dir
        self._last = 0.0

    def url(self, kind: str, date: str) -> str:
        ymd = date.replace("-", "")
        if kind == "jd":
            return "%sjd/%s/jd%s.xlsx" % (self.base, ymd[:4], ymd)
        return "%s%s/%s%s.xlsx" % (self.base, kind, kind, ymd)

    @classmethod
    def extract(cls, cells: Dict[str, object], col: str) -> Tuple[Dict[str, Optional[float]], List[str], str]:
        """Returns ({key: value|None}, missing_required, structure_hash). Value = JP-row + EN-row numbers (either may be empty)."""
        rows = _rows(cells)
        found: Dict[str, Optional[float]] = {}
        labels: List[str] = []
        for r in sorted(rows):
            row = rows[r]
            # Label = first NON-EMPTY string in B..E. Indented items carry empty-string cells in B (and C/D) before the
            # label — the 2026-09 live run failed on exactly that (ops_ex_lsp / reserve_bal / excess reported missing).
            txt = next((row[c].strip() for c in ("B", "C", "D", "E") if isinstance(row.get(c), str) and row[c].strip()), None)
            if not txt:
                continue
            txt = re.sub(r"\s+", " ", txt)
            for key, pat in cls.ITEMS:
                if key in found:
                    continue
                if re.search(pat, txt):
                    labels.append(txt)
                    jp = rows.get(r - 1, {})
                    a, b = jp.get(col), row.get(col)
                    na, nb = isinstance(a, float), isinstance(b, float)
                    found[key] = (a if na else 0.0) + (b if nb else 0.0) if (na or nb) else None
                    break
        missing = [k for k in cls.REQUIRED if k not in found]
        h = hashlib.sha256("|".join(labels).encode("utf-8")).hexdigest()[:16]
        return found, missing, h

    def fetch(self, dates: List[str], kind: str = "jd") -> Tuple[Dict[str, Series], List[str], Dict[str, str]]:
        """Returns ({key: Series}, errors, {date: structure_hash}). Missing file (holiday) is skipped silently."""
        if self.fixtures_dir:
            got = read_fixture(os.path.join(self.fixtures_dir, "boj_daily_%s_wide.csv" % kind))
            return got, [], {}
        out: Dict[str, List] = {}
        errs: List[str] = []
        hashes: Dict[str, str] = {}
        col = self.COL[kind]
        for d in dates:
            self._last = _sleep_gap(self._last, self.MIN_GAP_S)
            try:
                blob = _http(self.url(kind, d), binary=True)
            except FileNotFoundError:
                continue  # non-business day or not yet published
            except ProviderError as e:
                errs.append("%s %s: %s" % (kind, d, e))
                continue
            _snapshot(self.raw_dir, "%s%s.xlsx" % (kind, d.replace("-", "")), blob)
            try:
                vals, missing, h = self.extract(xlsx_cells(blob), col)
            except Exception as e:  # noqa
                errs.append("%s %s: unreadable xlsx (%s)" % (kind, d, e))
                continue
            if missing:
                errs.append("%s %s: STRUCTURE CHANGE — required items missing: %s" % (kind, d, ",".join(missing)))
                continue
            hashes[d] = h
            for k, v in vals.items():
                if v is not None:
                    out.setdefault(k, []).append((d, v))
        return {k: clean(v) for k, v in out.items()}, _collapse_errors(kind, errs), hashes


# ───────────────────────── BoJ Accounts (every ten days, HTML) ─────────────────────────
class BojAccountsProvider:
    name = "boj_accounts"
    MIN_GAP_S = 1.0
    ITEMS: List[Tuple[str, str]] = [
        ("total_assets", r"Total"), ("jgb_holdings", r"Japanese government securities"), ("boj_loans", r"Loans \(excluding those to the Deposit Insurance"),
        ("foreign_currency_assets", r"Foreign currency assets"), ("gold", r"^Gold"), ("banknotes", r"^Banknotes"), ("current_deposits", r"^Current deposits"),
        ("other_deposits", r"^Other deposits"), ("government_account", r"Deposits of the government"), ("repos_payable", r"Payables under repurchase"),
        ("loan_support_program", r"Fund-Provisioning Measure to Stimulate Bank Lending"), ("pooled_collateral_loans", r"Loans by Funds-Supplying Operations against Pooled Collateral"),
        ("etf", r"index-linked exchange-traded funds"), ("corporate_bonds", r"^Corporate bonds"),
    ]

    def __init__(self, base_url: str = "https://www.boj.or.jp/en/statistics/boj/other/acmai/release/", fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.base, self.fixtures_dir, self.raw_dir = base_url.rstrip("/") + "/", fixtures_dir, raw_dir
        self._last = 0.0

    def url(self, date: str) -> str:
        y, m, d = date.split("-")
        return "%s%s/ac%s%s%s.htm" % (self.base, y, y[2:], m, d)

    @classmethod
    def parse(cls, html: str) -> Dict[str, float]:
        """Labels and numbers live in separate <td>/<p> cells; walk the text tokens: a label is followed by its number.
        Thousand yen → 100 million yen (/100000). 'Total' appears twice (assets, liabilities): first wins."""
        txt = re.sub(r"<[^>]+>", "\n", html)
        txt = re.sub(r"&nbsp;|&#160;", " ", txt)
        toks = [t.strip() for t in txt.split("\n") if t.strip()]
        out: Dict[str, float] = {}
        for i, t in enumerate(toks):
            for key, pat in cls.ITEMS:
                if key in out or not re.search(pat, t):
                    continue
                for j in range(i + 1, min(i + 5, len(toks))):
                    n = toks[j].replace(",", "")
                    # footnote markers ('5') are short bare digits; real cells are comma-formatted or >= 4 digits
                    if re.match(r"^-?\d{4,}$", n) or re.match(r"^-?\d{1,3}(,\d{3})+$", toks[j]):
                        out[key] = round(int(n) / 100000.0, 1)
                        break
        ta = out.get("total_assets")
        if ta is not None and not (5e6 <= ta <= 9e6):  # 100m-yen units: 5e14–9e14 yen
            raise ProviderError("magnitude guard: total assets %s (100m yen) outside 5e6–9e6" % ta)
        return out

    def fetch(self, dates: List[str]) -> Tuple[Dict[str, Series], List[str]]:
        if self.fixtures_dir:
            return read_fixture(os.path.join(self.fixtures_dir, "boj_accounts_wide.csv")), []
        out: Dict[str, List] = {}
        errs: List[str] = []
        for d in dates:
            self._last = _sleep_gap(self._last, self.MIN_GAP_S)
            try:
                html = _http(self.url(d))
            except FileNotFoundError:
                continue
            except ProviderError as e:
                errs.append("accounts %s: %s" % (d, e))
                continue
            _snapshot(self.raw_dir, "ac%s.htm" % d.replace("-", ""), html)
            try:
                vals = self.parse(html)
            except ProviderError as e:
                errs.append("accounts %s: %s" % (d, e))
                continue
            for k, v in vals.items():
                out.setdefault(k, []).append((d, v))
        return {k: clean(v) for k, v in out.items()}, errs

    @staticmethod
    def candidate_dates(since: str, until: str) -> List[str]:
        """10th, 20th and month-end between two ISO dates."""
        from datetime import date, timedelta
        import calendar as _c
        y, m, _ = [int(x) for x in since.split("-")]
        end = date.fromisoformat(until)
        out: List[str] = []
        cur = date(y, m, 1)
        while cur <= end:
            for dd in (10, 20, _c.monthrange(cur.year, cur.month)[1]):
                x = date(cur.year, cur.month, dd)
                if since <= x.isoformat() <= until:
                    out.append(x.isoformat())
            cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        return out


# ───────────────────────── BoJ Time-Series Data Search API ─────────────────────────
class BojApiProvider:
    """https://www.stat-search.boj.or.jp/api/v1/getDataCode?db=FM01&code=A,B&format=json&lang=EN&startDate=YYYYMM&endDate=YYYYMM
    Daily series come as calendar days with null on non-business days (dropped). Max 250 codes; NEXTPOSITION paging."""
    name = "boj_api"
    MIN_GAP_S = 1.2

    def __init__(self, base_url: str = "https://www.stat-search.boj.or.jp/api/v1/", fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.base, self.fixtures_dir, self.raw_dir = base_url.rstrip("/") + "/", fixtures_dir, raw_dir
        self._last = 0.0

    @staticmethod
    def _date(freq: str, d) -> str:
        s = str(d)
        if len(s) == 8:
            return "%s-%s-%s" % (s[:4], s[4:6], s[6:])
        if len(s) == 6:  # monthly → month-end
            import calendar as _c
            y, m = int(s[:4]), int(s[4:])
            return "%04d-%02d-%02d" % (y, m, _c.monthrange(y, m)[1])
        return s

    @classmethod
    def parse(cls, j: dict) -> Dict[str, Series]:
        out: Dict[str, Series] = {}
        for rs in j.get("RESULTSET", []):
            code = rs.get("SERIES_CODE")
            vals = rs.get("VALUES") or {}
            dates, values = vals.get("SURVEY_DATES") or [], vals.get("VALUES") or []
            ser = []
            for d, v in zip(dates, values):
                if v is None:
                    continue
                try:
                    ser.append((cls._date(rs.get("FREQUENCY", ""), d), float(v)))
                except (TypeError, ValueError):
                    continue
            out[code] = clean(ser)
        return out

    def fetch(self, db: str, codes: List[str], start_yyyymm: str, end_yyyymm: str) -> Dict[str, Series]:
        if self.fixtures_dir:
            got = read_fixture(os.path.join(self.fixtures_dir, "boj_api_%s_wide.csv" % db.lower()))
            return {c: got.get(c, []) for c in codes}
        out: Dict[str, Series] = {c: [] for c in codes}
        pos: Optional[str] = None
        for _ in range(20):  # paging guard
            self._last = _sleep_gap(self._last, self.MIN_GAP_S)
            url = "%sgetDataCode?db=%s&code=%s&format=json&lang=EN&startDate=%s&endDate=%s%s" % (
                self.base, db, ",".join(codes), start_yyyymm, end_yyyymm, ("&startPosition=%s" % pos) if pos else "")
            txt = _http(url)
            _snapshot(self.raw_dir, "api_%s.json" % db.lower(), txt)
            import json as _j
            try:
                j = _j.loads(txt)
            except ValueError:
                raise ProviderError("api %s: non-JSON answer" % db)
            if j.get("STATUS") != 200:
                raise ProviderError("api %s: %s %s" % (db, j.get("STATUS"), j.get("MESSAGE")))
            for c, s in self.parse(j).items():
                if c in out:
                    out[c] = clean(out[c] + s)
            pos = j.get("NEXTPOSITION")
            if not pos:
                break
        return out


# ───────────────────────── BoJ call market (fcall.xlsx snapshot, TONA daily XLSX) ─────────────────────────
class BojCallMarketProvider:
    name = "boj_call_market"
    URL_FCALL = "https://www.boj.or.jp/en/statistics/market/short/mutan/d_release/others/fcall.xlsx"
    TENOR_ROWS = {"Overnight": "on", "Tomorrow next": "tn", "Spot next": "sn", "1  week": "1w", "2  weeks": "2w", "3  weeks": "3w", "1  month": "1m", "2  months": "2m", "3  months": "3m", "6  months": "6m"}

    def __init__(self, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.fixtures_dir, self.raw_dir = fixtures_dir, raw_dir

    @classmethod
    def parse(cls, cells: Dict[str, object]) -> Tuple[Optional[str], Dict[str, float]]:
        """fcall layout: A1 = Excel serial date; rows 11+ tenor label in A; columns B/C/D collateralized same-day min/max/avg,
        E/F/G collateralized forward, H/I/J uncollateralized same-day, K/L/M uncollateralized forward; S8–S13 outstanding + volume."""
        rows = _rows(cells)
        serial = rows.get(1, {}).get("A")
        date = None
        if isinstance(serial, float):
            from datetime import date as _d, timedelta
            date = (_d(1899, 12, 30) + timedelta(days=int(serial))).isoformat()
        out: Dict[str, float] = {}
        for r, row in rows.items():
            lab = row.get("A")
            if not isinstance(lab, str):
                continue
            key = None
            en = lab.replace("\r", "").split("\n")[-1].strip()
            for k, v in cls.TENOR_ROWS.items():
                if en.startswith(k) or k in lab:
                    key = v
                    break
            if not key:
                continue
            for col, tag in (("D", "col_same_avg"), ("G", "col_fwd_avg"), ("J", "unc_same_avg"), ("M", "unc_fwd_avg"), ("I", "unc_same_max"), ("H", "unc_same_min")):
                v = row.get(col)
                if isinstance(v, float):
                    out["%s_%s" % (key, tag)] = round(v, 4)
        for ref, key in (("S8", "call_outstanding_total"), ("S9", "call_outstanding_collateralized"), ("S10", "call_outstanding_uncollateralized"), ("S13", "tona_volume_fcall")):
            v = cells.get(ref)
            if isinstance(v, float):
                out[key] = v
        return date, out

    def fetch_fcall(self) -> Tuple[Dict[str, Series], List[str]]:
        if self.fixtures_dir:
            return read_fixture(os.path.join(self.fixtures_dir, "boj_fcall.csv")), []
        blob = _http(self.URL_FCALL, binary=True)
        _snapshot(self.raw_dir, "fcall.xlsx", blob)
        date, vals = self.parse(xlsx_cells(blob))
        if not date:
            return {}, ["fcall: date cell A1 missing"]
        return {k: [(date, v)] for k, v in vals.items()}, []


# ───────────────────────── MoF JGB yields (CSV) ─────────────────────────
class MofYieldsProvider:
    name = "mof_jgb_yields"
    TENORS = ["1Y", "2Y", "3Y", "4Y", "5Y", "6Y", "7Y", "8Y", "9Y", "10Y", "15Y", "20Y", "25Y", "30Y", "40Y"]

    def __init__(self, url_current: str, url_history: str, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.url_current, self.url_history, self.fixtures_dir, self.raw_dir = url_current, url_history, fixtures_dir, raw_dir

    @classmethod
    def parse(cls, text: str, since: Optional[str] = None) -> Dict[str, Series]:
        out: Dict[str, List] = {t: [] for t in cls.TENORS}
        header: List[str] = []
        for row in csv.reader(io.StringIO(text)):
            if not row:
                continue
            if row[0].strip() == "Date":
                header = [h.strip() for h in row]
                continue
            if not header or not re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", row[0].strip()):
                continue
            y, m, d = row[0].strip().split("/")
            iso = "%s-%02d-%02d" % (y, int(m), int(d))
            if since and iso < since:
                continue
            for h, v in zip(header[1:], row[1:]):
                if h in out and v.strip() not in ("", "-"):
                    try:
                        out[h].append((iso, float(v)))
                    except ValueError:
                        pass
        return {k: clean(v) for k, v in out.items()}

    def fetch(self, history: bool = False, since: Optional[str] = None) -> Dict[str, Series]:
        if self.fixtures_dir:
            return read_fixture(os.path.join(self.fixtures_dir, "mof_jgbcme_wide.csv"))
        text = _http(self.url_current, encoding="utf-8")
        _snapshot(self.raw_dir, "jgbcme.csv", text)
        out = self.parse(text)
        if history:
            th = _http(self.url_history, timeout=120, encoding="utf-8")
            hist = self.parse(th, since)
            for k in out:
                out[k] = clean(hist.get(k, []) + out[k])
        return out


# ───────────────────────── legacy XLS helpers (xlrd) ─────────────────────────
def _xls_rows(blob: bytes, sheet_index: int = 0) -> List[List[object]]:
    try:
        import xlrd  # type: ignore
    except Exception:
        raise ProviderError("xlrd not installed (needed for legacy .xls: JSDA, MoF)")
    wb = xlrd.open_workbook(file_contents=blob)
    sh = wb.sheet_by_index(sheet_index)
    return [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]


def _xls_sheets(blob: bytes) -> Dict[str, List[List[object]]]:
    try:
        import xlrd  # type: ignore
    except Exception:
        raise ProviderError("xlrd not installed (needed for legacy .xls: JSDA, MoF)")
    wb = xlrd.open_workbook(file_contents=blob)
    return {sh.name: [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)] for sh in wb.sheets()}


def _serial_to_iso(x) -> Optional[str]:
    from datetime import date, timedelta
    if isinstance(x, (int, float)) and 20000 < x < 80000:
        return (date(1899, 12, 30) + timedelta(days=int(x))).isoformat()
    return None


# ───────────────────────── JSDA Tokyo Repo Rate (XLS) ─────────────────────────
class JsdaRepoProvider:
    name = "jsda_tokyo_repo_rate"
    COLS = ["on_t0", "on", "1w", "2w", "3w", "1m", "3m", "6m", "1y"]  # column order after the date column

    def __init__(self, url_daily: str, url_history: str, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.url_daily, self.url_history, self.fixtures_dir, self.raw_dir = url_daily, url_history, fixtures_dir, raw_dir

    @classmethod
    def parse(cls, rows: List[List[object]], since: Optional[str] = None) -> Dict[str, Series]:
        out: Dict[str, List] = {c: [] for c in cls.COLS}
        for row in rows:
            iso = _serial_to_iso(row[0]) if row else None
            if not iso or (since and iso < since):
                continue
            for c, v in zip(cls.COLS, row[1:1 + len(cls.COLS)]):
                if isinstance(v, (int, float)) and v != "":
                    out[c].append((iso, float(v)))
        return {k: clean(v) for k, v in out.items()}

    def fetch(self, history: bool = False, since: Optional[str] = None) -> Dict[str, Series]:
        if self.fixtures_dir:
            return read_fixture(os.path.join(self.fixtures_dir, "jsda_trr_wide.csv"))
        blob = _http(self.url_daily, binary=True)
        _snapshot(self.raw_dir, "trr.xls", blob)
        out = self.parse(_xls_rows(blob))
        if history:
            hb = _http(self.url_history, binary=True, timeout=120)
            hist = self.parse(_xls_rows(hb), since)
            for k in out:
                out[k] = clean(hist.get(k, []) + out[k])
        return out


# ───────────────────────── MoF Receipts and Payments of Treasury Funds (monthly XLS) ─────────────────────────
class MofReceiptsProvider:
    name = "mof_treasury_receipts_payments"
    ITEMS: List[Tuple[str, str]] = [
        ("general_account", r"^General Account"), ("taxes", r"^Taxes"), ("social_security", r"^Social Security"), ("special_accounts", r"^Special Accounts"),
        ("filp", r"^Fiscal Investment and Loan"), ("fefsa", r"^Foreign Exchange\s*Equalization Fund"), ("pension", r"^Pension"), ("subtotal_1_2", r"^Subtotal（1＋2）|^Subtotal\(1\+2\)"),
        ("gov_bonds_etc", r"^Government Bonds etc"), ("gov_bonds_over_1y", r"^Government Bonds\(over one year\)"), ("tbills", r"^Treasury Discount Bills$"),
        ("tbills_etc", r"^Treasury Discount Bills etc"), ("subtotal_4_5", r"^Subtotal（4＋5）|^Subtotal\(4\+5\)"),
    ]

    def __init__(self, base_url: str, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.base, self.fixtures_dir, self.raw_dir = base_url.rstrip("/") + "/", fixtures_dir, raw_dir
        self._last = 0.0

    @classmethod
    def parse(cls, rows: List[List[object]]) -> Dict[str, float]:
        """Row label in one of the first 7 columns; numbers: receipts(prelim), receipts(prev yr), payments(prelim), payments(prev yr), balance(prelim), balance(prev yr), change."""
        out: Dict[str, float] = {}
        for row in rows:
            lab = next((c for c in row[:7] if isinstance(c, str) and c.strip()), None)
            if not lab:
                continue
            lab = re.sub(r"\s+", " ", lab.replace("\n", " ")).strip()
            nums = [c for c in row if isinstance(c, (int, float)) and c != ""]
            if len(nums) < 5:
                continue
            for key, pat in cls.ITEMS:
                if key in out or not re.search(pat, lab):
                    continue
                out[key + "_receipts"], out[key + "_receipts_py"], out[key + "_payments"], out[key + "_payments_py"], out[key + "_balance"] = [float(x) for x in nums[:5]]
                if len(nums) >= 6:
                    out[key + "_balance_py"] = float(nums[5])
                break
        return out

    def fetch(self, months: List[str]) -> Tuple[Dict[str, Series], List[str]]:
        """months: ['2026-08', ...] → series keyed '<item>_<field>' dated month-end."""
        if self.fixtures_dir:
            return read_fixture(os.path.join(self.fixtures_dir, "mof_receipts.csv")), []
        import calendar as _c
        out: Dict[str, List] = {}
        errs: List[str] = []
        for ym in months:
            y, m = ym.split("-")
            self._last = _sleep_gap(self._last, 1.0)
            try:
                blob = _http("%se%s%s.xls" % (self.base, y, m), binary=True)
            except FileNotFoundError:
                try:
                    blob = _http("%se%s%sa.xls" % (self.base, y, m), binary=True)  # preliminary 'a' file
                except FileNotFoundError:
                    continue
            except ProviderError as e:
                errs.append("mof receipts %s: %s" % (ym, e))
                continue
            _snapshot(self.raw_dir, "e%s%s.xls" % (y, m), blob)
            try:
                vals = self.parse(_xls_rows(blob))
            except ProviderError as e:
                errs.append(str(e))
                break
            d = "%s-%s-%02d" % (y, m, _c.monthrange(int(y), int(m))[1])
            for k, v in vals.items():
                out.setdefault(k, []).append((d, v))
        return {k: clean(v) for k, v in out.items()}, errs


# ───────────────────────── MoF auction results (XLS, one sheet per tenor) ─────────────────────────
class MofAuctionProvider:
    name = "mof_auction_results"
    SHEETS = {"40年債": "40y", "30年債": "30y", "20年債": "20y", "10年債": "10y", "5年債": "5y", "2年債": "2y"}

    def __init__(self, url_jgb: str, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.url_jgb, self.fixtures_dir, self.raw_dir = url_jgb, fixtures_dir, raw_dir

    @classmethod
    def parse(cls, sheets: Dict[str, List[List[object]]], since: Optional[str] = None) -> Dict[str, Series]:
        """columns: 0 issue, 1 auction date (serial), 2 issue date, 3 maturity, 4 coupon, 5 offering, 6 competitive bids, 7 accepted, 8 price, 9 highest accepted yield, 10 non-price II"""
        out: Dict[str, List] = {}
        for name, tag in cls.SHEETS.items():
            rows = sheets.get(name) or sheets.get(name.strip())
            if not rows:
                continue
            for row in rows:
                if len(row) < 10:
                    continue
                iso = _serial_to_iso(row[1])
                if not iso or (since and iso < since):
                    continue
                bids, acc, hy, off = row[6], row[7], row[9], row[5]
                if isinstance(bids, (int, float)) and isinstance(acc, (int, float)) and acc:
                    out.setdefault("btc_%s" % tag, []).append((iso, round(float(bids) / float(acc), 3)))
                if isinstance(hy, (int, float)):
                    out.setdefault("hy_%s" % tag, []).append((iso, float(hy)))
                if isinstance(off, (int, float)):
                    out.setdefault("offer_%s" % tag, []).append((iso, float(off)))
        return {k: clean(v) for k, v in out.items()}

    def fetch(self, since: Optional[str] = None) -> Dict[str, Series]:
        if self.fixtures_dir:
            return read_fixture(os.path.join(self.fixtures_dir, "mof_auctions.csv"))
        blob = _http(self.url_jgb, binary=True, timeout=120)
        _snapshot(self.raw_dir, "Auction_Results_for_JGBs.xls", blob)
        return self.parse(_xls_sheets(blob), since)


# ───────────────────────── MoF ITS weekly (Shift-JIS CSV) — parser Phase 3, snapshot only ─────────────────────────
class MofItsProvider:
    name = "mof_its_weekly"

    def __init__(self, url: str, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.url, self.fixtures_dir, self.raw_dir = url, fixtures_dir, raw_dir

    def snapshot(self) -> bool:
        if self.fixtures_dir:
            return True
        blob = _http(self.url, binary=True)
        _snapshot(self.raw_dir, "its_week.csv", blob)
        return True


# ───────────────────────── BoJ basic loan rate CSV (corridor) ─────────────────────────
class BojPolicyRateProvider:
    """cdab0101.csv: Shift-JIS header junk, then 'YYYY.MM.DD,rate' rows = basic loan rate (Complementary Lending Facility ceiling).
    Rule verified 2026-09-08 on the last four moves: policy_rate = basic_loan_rate − 0.25; IOER = policy_rate."""
    name = "boj_policy_rates_csv"

    def __init__(self, url: str, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None, spread: float = 0.25):
        self.url, self.fixtures_dir, self.raw_dir, self.spread = url, fixtures_dir, raw_dir, spread

    @staticmethod
    def parse(text: str) -> Series:
        out = []
        for line in text.splitlines():
            m = re.match(r"^(\d{4})\.(\d{2})\.(\d{2}),\s*([0-9.]+)\s*$", line.strip())
            if m:
                out.append(("%s-%s-%s" % (m.group(1), m.group(2), m.group(3)), float(m.group(4))))
        return clean(out)

    def fetch(self) -> Dict[str, Series]:
        if self.fixtures_dir:
            got = read_fixture(os.path.join(self.fixtures_dir, "boj_policy_rates.csv"))
            blr = got.get("basic_loan_rate", [])
        else:
            blob = _http(self.url, binary=True)
            _snapshot(self.raw_dir, "cdab0101.csv", blob)
            blr = self.parse(blob.decode("cp932", errors="replace"))
        if not blr:
            raise ProviderError("basic loan rate CSV: no rows parsed")
        pol = [(d, round(v - self.spread, 4)) for d, v in blr]
        return {"basic_loan_rate": blr, "policy_rate": pol, "ioer": list(pol)}
