"""CHF source adapters — SNB data portal (public JSON API: cubes, lists, warehouse cubes), SNB money-market operations XLSX,
Federal Finance Administration (AFF/EFV) auction XLSX files.

Design rules (config/chf.json v0.2, triangulated 2026-09-08):
  * portal series are addressed by cube id + dimension items exactly as the API returns them in metadata.key
    ('EPB@SNB.snbgwdzid{SARON}' -> data key 'snbgwdzid:SARON', 'EPB@SNB.bamire{TB,GA}' -> 'bamire:TB|GA';
     warehouse 'SNB1A@SNB.NSS.KZS.EID{J10M0,A1100,P1D_L,ZZ}' -> 'nss:J10M0');
  * monthly 'YYYY-MM' dates become month-end, quarterly 'YYYY-Qn' become quarter-end (portal delivers P1M / P3M);
  * one request per cube per lane, >= 1 s apart, no auth; raw snapshots under logs/chf/raw;
  * the sandbox cannot reach data.snb.ch / snb.ch / efv.admin.ch, so every provider has an offline mode reading
    fixtures/chf/<name>.csv (long format date,key,value) — captured live through the in-app browser on 2026-09-08.
Units: CHF millions everywhere (display bn = 10^9). Pure Python 3.9 (zipfile + xml for XLSX)."""
from __future__ import annotations
import calendar as _cal
import csv
import io
import os
import re
import time
import zipfile
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET
from .series import Series, clean
from .providers import ProviderError, UA
from .providers_jpy import read_fixture, _sleep_gap, _snapshot, _serial_to_iso, NS

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None


def _http(url: str, timeout: int = 60, retries: int = 3, binary: bool = False):
    if requests is None:
        raise ProviderError("requests not installed")
    last: Optional[Exception] = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=dict(UA, Accept="application/json, text/csv, */*"), timeout=timeout)
            if r.status_code == 404:
                raise FileNotFoundError(url)
            if r.status_code in (403, 429):
                raise ProviderError("HTTP %s (throttled) for %s" % (r.status_code, url))
            if r.status_code != 200:
                raise ProviderError("HTTP %s for %s" % (r.status_code, url))
            return r.content if binary else r.text
        except FileNotFoundError:
            raise
        except Exception as e:  # noqa
            last = e
            time.sleep(3 * (i + 1))
    raise ProviderError("failed after %d tries: %s" % (retries, last))


def _norm_date(d: str) -> Optional[str]:
    """'2026-09-04' | '2026-07' -> month-end | '2026-Q1' -> quarter-end | '2026' -> year-end."""
    d = d.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d
    m = re.match(r"^(\d{4})-(\d{2})$", d)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return "%04d-%02d-%02d" % (y, mo, _cal.monthrange(y, mo)[1])
    m = re.match(r"^(\d{4})-Q([1-4])$", d)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        mo = q * 3
        return "%04d-%02d-%02d" % (y, mo, _cal.monthrange(y, mo)[1])
    if re.match(r"^\d{4}$", d):
        return d + "-12-31"
    return None


# ───────────────────────── SNB data portal: cubes + warehouse ─────────────────────────
class SnbCubeProvider:
    """https://data.snb.ch/api/cube/{cube}/data/json/en?dimSel=...&fromDate=...&toDate=...
    Warehouse cubes: https://data.snb.ch/api/warehouse/cube/{prefix}.{path}/data/json/en (public id uses '.' where the portal shows '@')."""
    name = "snb_portal"
    MIN_GAP_S = 1.0

    def __init__(self, base_url: str = "https://data.snb.ch/api", fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.base, self.fixtures_dir, self.raw_dir = base_url.rstrip("/"), fixtures_dir, raw_dir
        self._last = 0.0

    @staticmethod
    def _key(meta_key: str, warehouse: bool) -> str:
        # 'EPB@SNB.snbgwdzid{SARON}' -> 'snbgwdzid:SARON' ; 'SNB1A@SNB.NSS.KZS.EID{J10M0,A1100,P1D_L,ZZ}' -> 'nss:J10M0'
        m = re.match(r"^[^.]+\.([^{]+)\{([^}]*)\}$", meta_key)
        if not m:
            return meta_key
        cube, dims = m.group(1), m.group(2)
        if warehouse:
            return "nss:" + dims.split(",")[0]
        return "%s:%s" % (cube, dims.replace(",", "|"))  # '|' between dimension items (keys must survive CSV headers)

    @classmethod
    def parse(cls, obj: dict, warehouse: bool = False) -> Dict[str, Series]:
        out: Dict[str, List] = {}
        for ts in obj.get("timeseries", []):
            k = cls._key(ts.get("metadata", {}).get("key", ""), warehouse)
            for v in ts.get("values", []):
                if v.get("value") is None:
                    continue
                d = _norm_date(str(v.get("date", "")))
                if d:
                    out.setdefault(k, []).append((d, float(v["value"])))
        return {k: clean(v) for k, v in out.items()}

    def fetch(self, cube: str, dim_sel: Optional[str], from_date: str, to_date: str, warehouse: bool = False, fixture: Optional[str] = None) -> Dict[str, Series]:
        if self.fixtures_dir:
            return read_fixture(os.path.join(self.fixtures_dir, "%s.csv" % (fixture or cube)))
        import json as _json
        self._last = _sleep_gap(self._last, self.MIN_GAP_S)
        path = "warehouse/cube" if warehouse else "cube"
        url = "%s/%s/%s/data/json/en?%sfromDate=%s&toDate=%s" % (self.base, path, cube, ("dimSel=%s&" % dim_sel) if dim_sel else "", from_date, to_date)
        txt = _http(url)
        _snapshot(self.raw_dir, "%s.json" % cube.replace("/", "_"), txt)
        try:
            obj = _json.loads(txt)
        except Exception as e:  # noqa
            raise ProviderError("portal %s: not JSON (%s)" % (cube, e))
        if isinstance(obj, dict) and obj.get("code"):
            raise ProviderError("portal %s: %s" % (cube, obj.get("message")))
        return self.parse(obj, warehouse)


# ───────────────────────── SNB Bills main register (list) ─────────────────────────
class SnbBillsRegisterProvider:
    """https://data.snb.ch/api/list/snbbillshreg/data/json/en — one row per ISIN: payment, repayment, outstanding volume (CHF).
    Level on the last bank working day of the previous month. Returns rows (CHF millions) + maturity ladder helpers."""
    name = "snb_bills_register"

    def __init__(self, url: str = "https://data.snb.ch/api/list/snbbillshreg/data/json/en", fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.url, self.fixtures_dir, self.raw_dir = url, fixtures_dir, raw_dir

    @staticmethod
    def parse(obj: dict) -> List[dict]:
        rows = []
        for r in obj.get("list", []):
            try:
                rows.append({"isin": r.get("HR_A"), "desc": r.get("HR_B"), "payment": r.get("HR_G"), "repayment": r.get("HR_H"), "outstanding": float(r.get("HR_K") or 0) / 1e6})
            except (TypeError, ValueError):
                continue
        return rows

    def fetch(self) -> Tuple[List[dict], Optional[str]]:
        """(rows, publishing_date). Fixture: fixtures/chf/snb_bills_register.csv with columns isin,desc,payment,repayment,outstanding_m."""
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, "snb_bills_register.csv")
            rows = []
            if os.path.exists(p):
                for r in csv.DictReader(open(p, encoding="utf-8")):
                    rows.append({"isin": r["isin"], "desc": r.get("desc", ""), "payment": r["payment"], "repayment": r["repayment"], "outstanding": float(r["outstanding_m"])})
            return rows, None
        import json as _json
        txt = _http(self.url)
        _snapshot(self.raw_dir, "snbbillshreg.json", txt)
        obj = _json.loads(txt)
        return self.parse(obj), None

    @staticmethod
    def ladder(rows: List[dict], asof: str, days: int) -> float:
        """Outstanding volume (CHF millions) repaying within `days` after `asof`."""
        from datetime import date, timedelta
        d0 = date.fromisoformat(asof)
        d1 = d0 + timedelta(days=days)
        tot = 0.0
        for r in rows:
            try:
                rp = date.fromisoformat(r["repayment"])
            except Exception:
                continue
            if d0 < rp <= d1:
                tot += r["outstanding"]
        return round(tot, 1)

    @staticmethod
    def total(rows: List[dict]) -> float:
        return round(sum(r["outstanding"] for r in rows), 1)


# ───────────────────────── XLSX (multi-sheet, stdlib) ─────────────────────────
def xlsx_sheets(blob: bytes) -> Dict[str, Dict[str, object]]:
    """{sheet name: {'A1': value}} for every sheet (workbook.xml + rels); shared strings without phonetic runs."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    m = NS["m"]
    ss: List[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.iter("{%s}si" % m):
            parts = []
            for child in si:
                tag = child.tag.split("}")[-1]
                if tag == "t":
                    parts.append(child.text or "")
                elif tag == "r":
                    parts.extend(t.text or "" for t in child.iter("{%s}t" % m))
            ss.append("".join(parts))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {r.get("Id"): r.get("Target") for r in rels}
    out: Dict[str, Dict[str, object]] = {}
    for sh in wb.iter("{%s}sheet" % m):
        rid = sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rid_to_target.get(rid, "")
        t = target.lstrip("/")
        path = t if t.startswith("xl/") else "xl/" + t
        if path not in z.namelist():
            continue
        cells: Dict[str, object] = {}
        root = ET.fromstring(z.read(path))
        for c in root.iter("{%s}c" % m):
            ref, t = c.get("r"), c.get("t")
            v = c.find("{%s}v" % m)
            if t == "s" and v is not None and v.text is not None:
                cells[ref] = ss[int(v.text)]
            elif t == "inlineStr":
                cells[ref] = "".join(x.text or "" for x in c.iter("{%s}t" % m))
            elif v is not None and v.text not in (None, ""):
                try:
                    cells[ref] = float(v.text)
                except ValueError:
                    cells[ref] = v.text
        out[sh.get("name")] = cells
    return out


def _rows_of(cells: Dict[str, object]) -> Dict[int, Dict[str, object]]:
    rows: Dict[int, Dict[str, object]] = {}
    for ref, val in cells.items():
        mm = re.match(r"^([A-Z]+)(\d+)$", ref)
        if mm:
            rows.setdefault(int(mm.group(2)), {})[mm.group(1)] = val
    return rows


# ───────────────────────── SNB money market operations (gmges.en.xlsx, monthly) ─────────────────────────
class SnbOpsProvider:
    """Single sheet; header row: Transaction date | SNB (CP/CT) | Contract/term | from | to | Type | Procedure | Yield % |
    Premium/discount to policy rate bp | Bids | Allocation. CHF millions. Update: last working day of the month for the previous month."""
    name = "snb_money_market_operations"

    def __init__(self, url: str, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.url, self.fixtures_dir, self.raw_dir = url, fixtures_dir, raw_dir

    @staticmethod
    def parse(cells: Dict[str, object]) -> List[dict]:
        rows = _rows_of(cells)
        hdr_row = next((r for r in sorted(rows) if str(rows[r].get("A", "")).startswith("Transaction date")), None)
        if hdr_row is None:
            raise ProviderError("gmges: header row not found (STRUCTURE CHANGE)")
        hdr = {col: str(v).lower() for col, v in rows[hdr_row].items()}
        def col(pat: str) -> Optional[str]:
            return next((c for c, h in hdr.items() if re.search(pat, h)), None)
        cd, cs, ct, cf, cto, cty, cp, cy, cpr, cb, ca = (col("transaction date"), col(r"^snb"), col("contract"), col("^from"), col("^to"), col("^type"),
                                                         col("procedure"), col("yield"), col("premium"), col("bids"), col("allocation"))
        out = []
        for r in sorted(rows):
            if r <= hdr_row:
                continue
            row = rows[r]
            d = row.get(cd)
            iso = _serial_to_iso(d) if isinstance(d, float) else (str(d)[:10] if d and re.match(r"^\d{4}-\d{2}-\d{2}", str(d)) else None)
            if not iso:
                continue
            def num(c):
                v = row.get(c)
                try:
                    return float(v) if v not in (None, "") else None
                except (TypeError, ValueError):
                    return None
            out.append({"date": iso, "side": str(row.get(cs, "")).strip(), "term": str(row.get(ct, "")).strip(), "from": _serial_to_iso(row.get(cf)) if isinstance(row.get(cf), float) else str(row.get(cf, ""))[:10],
                        "to": _serial_to_iso(row.get(cto)) if isinstance(row.get(cto), float) else str(row.get(cto, ""))[:10], "type": str(row.get(cty, "")).strip(),
                        "procedure": str(row.get(cp, "")).strip(), "yield": num(cy), "premium_bp": num(cpr), "bids": num(cb), "allocation": num(ca)})
        return out

    @staticmethod
    def series(ops: List[dict]) -> Dict[str, Series]:
        """absorbed_month (CT allocation), supplied_month (CP), swaps_month, bills_btc / bills_yield per auction date, repo_alloc_daily."""
        from collections import defaultdict
        absorbed, supplied, swaps = defaultdict(float), defaultdict(float), defaultdict(float)
        bills_btc, bills_yield, repo_daily = {}, {}, defaultdict(float)
        for o in ops:
            mo = o["date"][:7]
            me = _norm_date(mo)
            alloc = o["allocation"] or 0.0
            if o["type"].lower().startswith("swap"):
                swaps[me] += alloc
                continue
            if o["side"] == "CT":
                absorbed[me] += alloc
            elif o["side"] == "CP":
                supplied[me] += alloc
            tdays = int(re.sub(r"\D", "", o["term"]) or 0) if re.search(r"\d", o["term"]) else 0
            if o["type"].lower().startswith("snb bills") and 20 <= tdays <= 35:  # the weekly ~28-day bill (27T/28T/29T)
                if o["bids"] and alloc:
                    bills_btc[o["date"]] = round(o["bids"] / alloc, 3)
                if o["yield"] is not None:
                    bills_yield[o["date"]] = o["yield"]
            if o["type"].lower().startswith("repo") and o["side"] == "CT":
                repo_daily[o["date"]] += alloc
        # unreported months = 0 only inside the covered range
        mk = lambda d: clean([(k, round(v, 1)) for k, v in d.items()])
        return {"ops_absorbed_month": mk(absorbed), "ops_supplied_month": mk(supplied), "ops_swaps_month": mk(swaps),
                "bills_btc": clean(list(bills_btc.items())), "bills_yield_28d": clean(list(bills_yield.items())), "repo_absorb_daily": mk(repo_daily)}

    def fetch(self) -> Tuple[Dict[str, Series], List[dict]]:
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, "snb_ops_rows.csv")
            ops = []
            if os.path.exists(p):
                for r in csv.DictReader(open(p, encoding="utf-8")):
                    ops.append({"date": r["date"], "side": r["side"], "term": r["term"], "from": r.get("from", ""), "to": r.get("to", ""), "type": r["type"], "procedure": r.get("procedure", ""),
                                "yield": float(r["yield"]) if r.get("yield") else None, "premium_bp": float(r["premium_bp"]) if r.get("premium_bp") else None,
                                "bids": float(r["bids"]) if r.get("bids") else None, "allocation": float(r["allocation"]) if r.get("allocation") else None})
            return self.series(ops), ops
        blob = _http(self.url, binary=True, timeout=120)
        _snapshot(self.raw_dir, "gmges.en.xlsx", blob)
        sheets = xlsx_sheets(blob)
        cells = next(iter(sheets.values()))
        ops = self.parse(cells)
        return self.series(ops), ops


# ───────────────────────── AFF/EFV auctions (resultate-gmbf.xlsx, resultate-anleihen.xlsx, ausstehende-anleihen.xlsx) ─────────────────────────
class EfvAuctionsProvider:
    """Sheet per year; the English header row starts with 'Auction'. Excel serial dates. CHF millions.
    MMDRC columns: Auction | Settlement | Maturity | Days | ISIN | Total bids | Bids without price | Amount issued | Price | Yield
    Bond columns: Auction | Settlement | Maturity | prov. ISIN | Fungible ISIN | Bond | Coupon | Total bids | Bids w/o price | Amount issued | Price | Yield | Own holdings not placed"""
    name = "efv_auctions"

    def __init__(self, url_mmdrc: str, url_bonds: str, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None):
        self.url_mmdrc, self.url_bonds, self.fixtures_dir, self.raw_dir = url_mmdrc, url_bonds, fixtures_dir, raw_dir
        self.records: Dict[str, List[dict]] = {"mmdrc": [], "bonds": []}

    @staticmethod
    def _table(cells: Dict[str, object]) -> List[dict]:
        rows = _rows_of(cells)
        hdr_row = next((r for r in sorted(rows) if str(rows[r].get("A", "")).strip().lower() == "auction"), None)
        if hdr_row is None:
            return []
        hdr = {c: re.sub(r"\s+", " ", str(v)).strip().lower() for c, v in rows[hdr_row].items()}
        out = []
        for r in sorted(rows):
            if r <= hdr_row:
                continue
            rec = {}
            for c, h in hdr.items():
                rec[h] = rows[r].get(c)
            d = rec.get("auction")
            iso = _serial_to_iso(float(d)) if isinstance(d, (int, float)) and not isinstance(d, bool) else None
            if not iso:
                continue
            rec["_date"] = iso
            out.append(rec)
        return out

    @staticmethod
    def _num(v) -> Optional[float]:
        try:
            return float(v) if v not in (None, "", "-") else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def series_mmdrc(cls, recs: List[dict]) -> Dict[str, Series]:
        btc, yl, iss = [], [], []
        for r in recs:
            bids = cls._num(next((v for h, v in r.items() if h.startswith("total bids") and "without" not in h), None))
            amt = cls._num(next((v for h, v in r.items() if h.startswith("amount of issue")), None))
            y = cls._num(next((v for h, v in r.items() if h.startswith("yield")), None))
            if bids and amt:
                btc.append((r["_date"], round(bids / amt, 3)))
            if y is not None:
                yl.append((r["_date"], round(y * 100, 4)))  # file stores decimal (−0.00083) → percent
            if amt is not None:
                iss.append((r["_date"], amt))
        return {"mmdrc_btc": clean(btc), "mmdrc_yield": clean(yl), "mmdrc_issued": clean(iss)}

    @classmethod
    def series_bonds(cls, recs: List[dict]) -> Dict[str, Series]:
        from collections import defaultdict
        btc_d, y_d, iss_d, own_d = defaultdict(list), defaultdict(list), defaultdict(float), defaultdict(float)
        for r in recs:
            bids = cls._num(next((v for h, v in r.items() if h.startswith("total bids") and "without" not in h), None))
            amt = cls._num(next((v for h, v in r.items() if h.startswith("amount of issue")), None))
            y = cls._num(next((v for h, v in r.items() if h.startswith("yield")), None))
            own = cls._num(next((v for h, v in r.items() if h.startswith("additional own holdings")), None)) or 0.0
            d = r["_date"]
            if bids and amt:
                btc_d[d].append(bids / amt)
            if y is not None:
                y_d[d].append(y * 100)
            if amt is not None:
                iss_d[d] += amt
                own_d[d] += own
        btc = [(d, round(sum(v) / len(v), 3)) for d, v in btc_d.items()]
        yl = [(d, round(sum(v) / len(v), 4)) for d, v in y_d.items()]
        iss = [(d, round(v, 2)) for d, v in iss_d.items()]
        own = [(d, round(own_d[d] / (iss_d[d] + own_d[d]), 4) if (iss_d[d] + own_d[d]) else 0.0) for d in iss_d]
        return {"bond_btc": clean(btc), "bond_yield": clean(yl), "bond_issued": clean(iss), "bond_own_share": clean(own)}

    def fetch(self) -> Tuple[Dict[str, Series], List[str]]:
        if self.fixtures_dir:
            import json as _json
            for tag in ("mmdrc", "bonds"):
                pj = os.path.join(os.path.dirname(self.fixtures_dir.rstrip("/")), "chf_hist", "efv_%s_cells.json" % tag)
                if os.path.exists(pj):
                    cells_by_sheet = _json.load(open(pj, encoding="utf-8"))
                    self.records[tag] = [r for name, cells in cells_by_sheet.items() if re.match(r"^20\d\d$", name.strip()) and int(name) >= 2019 for r in self._table(cells)]
            return read_fixture(os.path.join(self.fixtures_dir, "efv_auctions.csv")), []
        out: Dict[str, Series] = {}
        errs: List[str] = []
        for url, fn, tag in ((self.url_mmdrc, self.series_mmdrc, "mmdrc"), (self.url_bonds, self.series_bonds, "bonds")):
            try:
                blob = _http(url, binary=True, timeout=180)
                _snapshot(self.raw_dir, "efv_%s.xlsx" % tag, blob)
                sheets = xlsx_sheets(blob)
                recs: List[dict] = []
                for name, cells in sheets.items():
                    if re.match(r"^20\d\d$", name.strip()) and int(name) >= 2019:
                        recs += self._table(cells)
                self.records[tag] = recs  # v0.4: per-auction records (settlement / maturity) for ops_chf
                got = fn(recs)
                if not any(got.values()):
                    errs.append("efv %s: no rows parsed (STRUCTURE CHANGE?)" % tag)
                out.update(got)
            except FileNotFoundError:
                errs.append("efv %s: 404 (file moved — check the SNB 'Services for the Confederation' page for the new DAM link)" % tag)
            except ProviderError as e:
                errs.append("efv %s: %s" % (tag, e))
        return out, errs
