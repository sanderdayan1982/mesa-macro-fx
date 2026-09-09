"""EUR providers — ECB Data Portal (SDMX csvdata, no key), ECB APP/PEPP history CSVs, Deutsche Finanzagentur issuance XLSX.
Verified 2026-09-09 from the data.ecb.europa.eu / ecb.europa.eu / deutsche-finanzagentur.de origins (config/eur.json v0.2 source map):
  • ECB Data Portal: https://data-api.ecb.europa.eu/service/data/<FLOW>/<KEY>?format=csvdata&startPeriod=YYYY-MM-DD
    FLOW = text before the first dot of the desk key (ILM, EST, FM, YC, IRS, TGB, BSI, MIR, BLS, GFS, EXR, ICP) — E14.
    CSV columns used: KEY, TIME_PERIOD, OBS_VALUE, UNIT, UNIT_MULT. TIME_PERIOD formats: YYYY-MM-DD (daily), YYYY-Wnn (weekly →
    Friday of the ISO week = WFS 'position as at' date), YYYY-MM (monthly → 1st of month), YYYY-Qn (quarterly → quarter end).
    UNIT_MULT 6 = EUR millions (desk unit; no rescale); rates in percent. ≥ 1.5 s between requests (E14).
  • APP/PEPP: /mopo/pdf/APP_breakdown_history.csv, PEPP_breakdown_history.csv (end-of-month holdings at amortised cost, EUR millions;
    the last four (APP) / six (PEPP) columns are the holdings), APP_redemptions_history.csv, PEPP_redemptions_history.csv
    (realised or estimated redemptions per month, EUR millions).
  • Finanzagentur: emissionsergebnisse_aktuell_en.xlsx (current year; columns No., Date, ISIN, Bond, Coupon, Maturity, segment, volume,
    Type, process, Bids, competitive, non-competitive, allotted, lowest price, avg price, avg yield, retention, bid-to-cover).
Fixtures: fixtures/eur/ecb_<KEY>.csv ('# meta' line + TIME_PERIOD,OBS_VALUE), fixtures/eur/<APP|PEPP file>.csv, fixtures/eur/finanzagentur_*.xlsx."""
from __future__ import annotations
import csv
import io
import os
import re
import time
import urllib.request
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from .series import Series, clean
from .providers import ProviderError, UA

ECB_API = os.environ.get("ECB_API_BASE", "https://data-api.ecb.europa.eu/service/data")
ECB_MOPO = os.environ.get("ECB_MOPO_BASE", "https://www.ecb.europa.eu/mopo/pdf")
FINANZAGENTUR_XLSX = os.environ.get("FINANZAGENTUR_XLSX_URL", "https://www.deutsche-finanzagentur.de/fileadmin/user_upload/Institutionelle-investoren/auktionen/emissionsergebnisse_aktuell_en.xlsx")
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _get(url: str, timeout: int = 60, retries: int = 3, binary: bool = False, accept: str = "text/csv,*/*;q=0.8"):
    last = None
    for i in range(retries):
        try:
            ua = UA["User-Agent"] if isinstance(UA, dict) else str(UA)
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": accept})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return raw if binary else raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise ProviderError("%s: %s" % (url.split("?")[0], last))


def period_to_date(tp: str) -> Optional[str]:
    """ECB TIME_PERIOD → ISO date (weekly = Friday of the ISO week; monthly = 1st; quarterly = quarter end)."""
    tp = tp.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", tp):
        return tp
    m = re.fullmatch(r"(\d{4})-W(\d{1,2})", tp)
    if m:
        try:
            return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 5).isoformat()
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})-Q([1-4])", tp)
    if m:
        q = int(m.group(2))
        mo = q * 3
        d = date(int(m.group(1)), mo, 1) + timedelta(days=32)
        return (d.replace(day=1) - timedelta(days=1)).isoformat()
    m = re.fullmatch(r"(\d{4})-(\d{2})", tp)
    if m:
        return "%s-%s-01" % (m.group(1), m.group(2))
    return None


def _split_key(key: str) -> Tuple[str, str]:
    i = key.index(".")
    return key[:i], key[i + 1:]


class EcbProvider:
    """One SDMX key per request; csvdata parsed by header names (column order is not guaranteed)."""

    def __init__(self, base: str = ECB_API, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None, pause: float = 1.5):
        self.base, self.fixtures_dir, self.raw_dir, self.pause = base, fixtures_dir, raw_dir, pause
        self.meta: Dict[str, dict] = {}
        self.no_new: List[str] = []

    @staticmethod
    def parse_csvdata(text: str, key: str) -> Tuple[Series, dict]:
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            return [], {}
        hdr = rows[0]
        if "TIME_PERIOD" not in hdr or "OBS_VALUE" not in hdr:
            raise ProviderError("ECB csvdata %s: unexpected header %r" % (key, hdr[:6]))
        iT, iV = hdr.index("TIME_PERIOD"), hdr.index("OBS_VALUE")
        iU = hdr.index("UNIT") if "UNIT" in hdr else None
        iM = hdr.index("UNIT_MULT") if "UNIT_MULT" in hdr else None
        out: Series = []
        meta: dict = {}
        for r in rows[1:]:
            if len(r) <= max(iT, iV):
                continue
            d = period_to_date(r[iT])
            if not d:
                continue
            v = r[iV].strip()
            try:
                out.append((d, float(v) if v not in ("", "NaN", "-") else None))
            except ValueError:
                out.append((d, None))
            if not meta:
                meta = {"unit": r[iU] if iU is not None else None, "unit_mult": r[iM] if iM is not None else None}
        return clean(out), meta

    @staticmethod
    def parse_fixture(text: str, key: str) -> Tuple[Series, dict]:
        lines = text.strip().splitlines()
        meta: dict = {}
        if lines and lines[0].startswith("#"):
            m = re.search(r"UNIT=(\S+)\s+UNIT_MULT=(\S+)", lines[0])
            if m:
                meta = {"unit": m.group(1), "unit_mult": m.group(2)}
            lines = lines[1:]
        out: Series = []
        for r in csv.reader(io.StringIO("\n".join(lines))):
            if len(r) < 2 or r[0] == "TIME_PERIOD":
                continue
            d = period_to_date(r[0])
            if d:
                v = r[1].strip()
                out.append((d, float(v) if v not in ("", "NaN", "-") else None))
        return clean(out), meta

    def fetch_one(self, key: str, since: str) -> Series:
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, "ecb_%s.csv" % key)
            if not os.path.exists(p):
                raise ProviderError("fixture missing: %s" % p)
            ser, meta = self.parse_fixture(open(p, encoding="utf-8").read(), key)
        else:
            flow, rest = _split_key(key)
            url = "%s/%s/%s?format=csvdata&startPeriod=%s" % (self.base, flow, rest, since)
            try:
                text = _get(url, retries=2)
            except ProviderError as e:
                # the portal answers 404 when a valid key has no observation after startPeriod (step series such as the key rates,
                # quarterly flows on a short incremental window): not an error — the runner keeps the history CSV
                if "404" in str(e) and since > "2000":
                    self.meta[key] = {"no_new_observations": True}
                    self.no_new.append(key)
                    return []
                raise
            if self.raw_dir:
                os.makedirs(self.raw_dir, exist_ok=True)
                open(os.path.join(self.raw_dir, "ecb_%s.csv" % key), "w", encoding="utf-8").write(text)
            ser, meta = self.parse_csvdata(text, key)
            time.sleep(self.pause)
        self.meta[key] = meta
        return ser

    def fetch(self, keys: List[str], since: str, errors: Optional[List[str]] = None) -> Dict[str, Series]:
        out: Dict[str, Series] = {}
        for k in keys:
            try:
                out[k] = self.fetch_one(k, since)
            except ProviderError as e:
                if errors is None:
                    raise
                errors.append("%s: %s" % (k, e))
        return out


# ─────────────────────────── APP / PEPP history CSVs ───────────────────────────
def _num(s: str) -> Optional[float]:
    s = (s or "").strip().replace(",", "").replace("−", "-")
    if s in ("", "-", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _month_rows(text: str) -> List[Tuple[str, List[str]]]:
    """Rows of the ECB purchase-programme CSVs: (YYYY-MM-01, cells) — year carried down from the first column, month name in the second."""
    out = []
    year = None
    for r in csv.reader(io.StringIO(text.replace("\r", ""))):
        if len(r) < 3:
            continue
        y = r[0].strip()
        if re.fullmatch(r"\d{4}", y):
            year = int(y)
        mtxt = r[1].strip().lower()
        m = MONTHS.get(mtxt[:3]) if mtxt[:3] in MONTHS else None
        mm = re.fullmatch(r"([a-z]{3})-(\d{2})", mtxt)
        if mm:
            m, year = MONTHS.get(mm.group(1)), 2000 + int(mm.group(2))
        if year and m:
            out.append(("%04d-%02d-01" % (year, m), r))
    return out


def parse_holdings(text: str, n_holdings_cols: int) -> Dict[str, Series]:
    """APP: last 4 columns = ABSPP, CBPP3, CSPP, PSPP holdings; PEPP: last 6 = ABS, covered, corporate, CP, public, total.
    Returns 'total' (sum for APP; the file's Total for PEPP) and 'public' (PSPP / PEPP public sector)."""
    total: Series = []
    public: Series = []
    for d, r in _month_rows(text):
        cells = [_num(x) for x in r[-n_holdings_cols:]]
        if n_holdings_cols == 4:
            if all(c is not None for c in cells):
                total.append((d, round(sum(cells), 1)))
                public.append((d, cells[3]))
        else:
            if cells[-1] is not None:
                total.append((d, cells[-1]))
                public.append((d, cells[-2]))
    return {"total": clean(total), "public": clean(public)}


def parse_redemptions(text: str, n_programmes: int) -> Series:
    """Per month: sum over programmes of realised redemptions (or the estimate when the realised cell is empty), EUR millions."""
    out: Series = []
    for d, r in _month_rows(text):
        cells = r[2:2 + 2 * n_programmes]
        tot, any_ = 0.0, False
        for i in range(n_programmes):
            real, est = _num(cells[2 * i]) if 2 * i < len(cells) else None, _num(cells[2 * i + 1]) if 2 * i + 1 < len(cells) else None
            v = real if real is not None else est
            if v is not None:
                tot += v
                any_ = True
        if any_:
            out.append((d, round(tot, 1)))
    return clean(out)


class AppPeppProvider:
    FILES = {"app": "APP_breakdown_history.csv", "pepp": "PEPP_breakdown_history.csv", "app_red": "APP_redemptions_history.csv", "pepp_red": "PEPP_redemptions_history.csv"}

    def __init__(self, base: str = ECB_MOPO, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None, pause: float = 1.5):
        self.base, self.fixtures_dir, self.raw_dir, self.pause = base, fixtures_dir, raw_dir, pause

    def _text(self, name: str) -> str:
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, name)
            if not os.path.exists(p):
                raise ProviderError("fixture missing: %s" % p)
            return open(p, encoding="utf-8").read()
        t = _get("%s/%s" % (self.base, name))
        if self.raw_dir:
            os.makedirs(self.raw_dir, exist_ok=True)
            open(os.path.join(self.raw_dir, name), "w", encoding="utf-8").write(t)
        time.sleep(self.pause)
        return t

    def fetch(self) -> Dict[str, Series]:
        """Keys: APP:holdings, APP:pspp, PEPP:holdings, PEPP:public, APP:redemptions, PEPP:redemptions (monthly, EUR millions)."""
        out: Dict[str, Series] = {}
        h = parse_holdings(self._text(self.FILES["app"]), 4)
        out["APP:holdings"], out["APP:pspp"] = h["total"], h["public"]
        h = parse_holdings(self._text(self.FILES["pepp"]), 6)
        out["PEPP:holdings"], out["PEPP:public"] = h["total"], h["public"]
        out["APP:redemptions"] = parse_redemptions(self._text(self.FILES["app_red"]), 4)
        out["PEPP:redemptions"] = parse_redemptions(self._text(self.FILES["pepp_red"]), 4)
        return out


# ─────────────────────────── Deutsche Finanzagentur issuance results ───────────────────────────
class FinanzagenturProvider:
    """Current-year XLSX (sheet 1). Row = one ISIN line of an auction (multi-ISIN auctions share the auction number).
    Series (event frequency, date = auction date; several lines per date are aggregated volume-weighted):
      DE:bid_to_cover (Bids / allotted, weighted by allotted), DE:avg_yield (weighted by allotted), DE:retention (sum), DE:volume (sum of issuance volume),
      DE:allotted (sum), DE:bills_bid_to_cover (Bubill only), DE:bonds_bid_to_cover (all except Bubill)."""

    def __init__(self, url: str = FINANZAGENTUR_XLSX, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.url, self.fixtures_dir, self.raw_dir = url, fixtures_dir, raw_dir
        self.rows: List[dict] = []

    def _bytes(self) -> bytes:
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, "finanzagentur_emissionsergebnisse_aktuell_en.xlsx")
            if not os.path.exists(p):
                raise ProviderError("fixture missing: %s" % p)
            return open(p, "rb").read()
        b = _get(self.url, binary=True, accept="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8")
        if self.raw_dir:
            os.makedirs(self.raw_dir, exist_ok=True)
            open(os.path.join(self.raw_dir, "finanzagentur_emissionsergebnisse_aktuell_en.xlsx"), "wb").write(b)
        return b

    @staticmethod
    def parse(b: bytes) -> List[dict]:
        try:
            import openpyxl  # noqa
        except ImportError as e:  # pragma: no cover
            raise ProviderError("openpyxl missing: %s" % e)
        wb = openpyxl.load_workbook(io.BytesIO(b), data_only=True, read_only=True)
        ws = wb.worksheets[0]
        out = []
        for r in ws.iter_rows(values_only=True):
            if len(r) < 19 or not isinstance(r[1], (datetime, date)):
                continue
            def f(x):
                try:
                    return float(x) if x not in (None, "", "-") else None
                except (TypeError, ValueError):
                    return None
            out.append({"no": str(r[0]).strip(), "date": r[1].date().isoformat() if isinstance(r[1], datetime) else r[1].isoformat(), "isin": r[2], "bond": (r[3] or "").strip(),
                        "coupon": f(r[4]), "maturity": r[5].date().isoformat() if isinstance(r[5], datetime) else (r[5].isoformat() if isinstance(r[5], date) else None),
                        "segment": (r[6] or "").strip(), "volume": f(r[7]), "type": r[8], "process": r[9], "bids": f(r[10]), "competitive": f(r[11]), "non_competitive": f(r[12]),
                        "allotted": f(r[13]), "lowest_price": f(r[14]), "avg_price": f(r[15]), "avg_yield": f(r[16]), "retention": f(r[17]), "bid_to_cover": f(r[18])})
        return out

    def fetch(self) -> Dict[str, Series]:
        self.rows = self.parse(self._bytes())
        by: Dict[str, List[dict]] = {}
        for r in self.rows:
            if r["process"] == "Syn":  # syndications have no bid-to-cover
                continue
            by.setdefault(r["date"], []).append(r)
        out: Dict[str, Series] = {k: [] for k in ("DE:bid_to_cover", "DE:avg_yield", "DE:retention", "DE:volume", "DE:allotted", "DE:bills_bid_to_cover", "DE:bonds_bid_to_cover")}
        for d in sorted(by):
            rows = by[d]
            def wavg(rs, field):
                num = sum((x[field] or 0) * (x["allotted"] or 0) for x in rs if x[field] is not None and x["allotted"])
                den = sum(x["allotted"] for x in rs if x[field] is not None and x["allotted"])
                return round(num / den, 3) if den else None
            bc = wavg(rows, "bid_to_cover")
            if bc is not None:
                out["DE:bid_to_cover"].append((d, bc))
            y = wavg(rows, "avg_yield")
            if y is not None:
                out["DE:avg_yield"].append((d, y))
            out["DE:retention"].append((d, round(sum(x["retention"] or 0 for x in rows), 1)))
            out["DE:volume"].append((d, round(sum(x["volume"] or 0 for x in rows), 1)))
            out["DE:allotted"].append((d, round(sum(x["allotted"] or 0 for x in rows), 1)))
            bills = [x for x in rows if x["bond"].lower().startswith("bubill")]
            bonds = [x for x in rows if not x["bond"].lower().startswith("bubill")]
            if bills and wavg(bills, "bid_to_cover") is not None:
                out["DE:bills_bid_to_cover"].append((d, wavg(bills, "bid_to_cover")))
            if bonds and wavg(bonds, "bid_to_cover") is not None:
                out["DE:bonds_bid_to_cover"].append((d, wavg(bonds, "bid_to_cover")))
        return {k: clean(v) for k, v in out.items()}
