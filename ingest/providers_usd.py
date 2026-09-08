"""USD providers — exact replica of the three legacy USD dashboards' data paths (no triangulation, Sander's rule):
  • FRED (H.4.1 weekly + SOFR/IORB/ON RRP daily + H.8 weekly + H.15 daily). Primary path = the keyless CSV endpoint
    https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID>&cosd=<date> (verified 2026-09-08 for all 18 ids).
    Fallback = the FRED API (api.stlouisfed.org, needs FRED_API_KEY) with the same observation semantics.
    Units come from FRED itself and are normalised to USD MILLIONS in `UNITS_TO_M` (RRPONTTLD is the only $B series;
    WRESBAL/WTREGEN are already $M — the legacy H.4.1 v2.0 multiplied them by 1000, which inflated reserves/TGA 1000x).
  • Fiscal Data API (Daily Treasury Statement, Bureau of the Fiscal Service) — three endpoints exactly as the DTS Tracker v3.0:
    operating_cash_balance (TGA opening/closing, total deposits/withdrawals — closing balance lives in open_today_bal, documented quirk),
    deposits_withdrawals_operating_cash (line items: today / MTD / FYTD; total rows have transaction_catg = "null"),
    debt_subject_to_limit (Debt Held by the Public, Intragovernmental Holdings, close_today_bal). All $M. T-1 (published ~16:00 ET).
Fixtures: fixtures/usd/fred_<ID>.csv (observation_date,<ID>) and fixtures/usd/dts_{cash,tx,debt}.csv (API rows as CSV)."""
from __future__ import annotations
import csv
import io
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple
from .series import Series
from .providers import ProviderError, UA

# FRED units → USD millions (verified against the FRED series pages, 2026-09-08)
UNITS_TO_M: Dict[str, float] = {
    "WALCL": 1, "WTREGEN": 1, "WRESBAL": 1, "TREAST": 1, "WSHOMCB": 1, "WLCFLPCL": 1,   # $ millions
    "RRPONTTLD": 1000,                                                                  # $ billions
    "TOTBKCR": 1000, "TOTLL": 1000, "TOTCI": 1000, "BUSLOANS": 1000, "DPSACBW027SBOG": 1000,  # H.8 $ billions
    "H8B3094NCBA": 1,                                                                   # H.8 borrowings $ millions (SA)
}
RATE_IDS = ("SOFR", "IORB", "DFF", "DTB3", "DGS2", "DGS10")


def _get(url: str, timeout: int = 40, retries: int = 3, headers: Optional[dict] = None) -> str:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=dict({"User-Agent": UA, "Accept": "text/csv,application/json;q=0.9,*/*;q=0.8"}, **(headers or {})))
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise ProviderError("%s: %s" % (url.split("?")[0], last))


class FredProvider:
    """One series per request (fredgraph.csv accepts several ids but a single missing id fails the whole file)."""

    def __init__(self, csv_base: str = "https://fred.stlouisfed.org/graph/fredgraph.csv", api_base: str = "https://api.stlouisfed.org/fred/series/observations",
                 fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None, pause: float = 0.6):
        self.csv_base, self.api_base, self.fixtures_dir, self.raw_dir, self.pause = csv_base, api_base, fixtures_dir, raw_dir, pause
        self.key = os.environ.get("FRED_API_KEY", "")
        self.path_used: Dict[str, str] = {}

    @staticmethod
    def parse_csv(text: str, sid: str) -> Series:
        rows = list(csv.reader(io.StringIO(text)))
        if not rows or len(rows[0]) < 2:
            raise ProviderError("FRED csv %s: unexpected header %r" % (sid, rows[:1]))
        out: Series = []
        for r in rows[1:]:
            if len(r) < 2 or not r[0][:4].isdigit():
                continue
            v = r[1].strip()
            out.append((r[0], float(v) if v not in ("", ".") else None))
        return out

    @staticmethod
    def parse_api(text: str, sid: str) -> Series:
        j = json.loads(text)
        if "observations" not in j:
            raise ProviderError("FRED api %s: %s" % (sid, j.get("error_message", "no observations")))
        return [(o["date"], float(o["value"]) if o["value"] not in (".", "") else None) for o in j["observations"]]

    def fetch(self, ids: List[str], since: str) -> Dict[str, Series]:
        out: Dict[str, Series] = {}
        if self.fixtures_dir:
            for sid in ids:
                p = os.path.join(self.fixtures_dir, "fred_%s.csv" % sid)
                if not os.path.exists(p):
                    raise ProviderError("fixture missing: %s" % p)
                out[sid] = self._scale(sid, self.parse_csv(open(p, encoding="utf-8").read(), sid))
            return out
        for sid in ids:
            text, path = None, None
            try:
                text = _get(self.csv_base + "?" + urllib.parse.urlencode({"id": sid, "cosd": since}))
                ser = self.parse_csv(text, sid)
                path = "fredgraph.csv"
            except ProviderError as e:
                if not self.key:
                    raise ProviderError("%s (no FRED_API_KEY for the API fallback)" % e)
                text = _get(self.api_base + "?" + urllib.parse.urlencode({"series_id": sid, "api_key": self.key, "file_type": "json", "observation_start": since, "sort_order": "asc"}))
                ser = self.parse_api(text, sid)
                path = "api"
            self.path_used[sid] = path
            if self.raw_dir:
                os.makedirs(self.raw_dir, exist_ok=True)
                open(os.path.join(self.raw_dir, "fred_%s.csv" % sid), "w", encoding="utf-8").write(text)
            out[sid] = self._scale(sid, ser)
            time.sleep(self.pause)
        return out

    @staticmethod
    def _scale(sid: str, ser: Series) -> Series:
        f = UNITS_TO_M.get(sid, 1)
        return [(d, (v * f) if (v is not None and f != 1) else v) for d, v in ser]


class FiscalDataProvider:
    """Daily Treasury Statement via api.fiscaldata.treasury.gov (DTS Tracker v3.0 paths). Sort DESC so a page cut only loses the oldest days."""
    BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
    EP_CASH = "/v1/accounting/dts/operating_cash_balance"
    EP_TX = "/v1/accounting/dts/deposits_withdrawals_operating_cash"
    EP_DEBT = "/v1/accounting/dts/debt_subject_to_limit"

    def __init__(self, base: str = BASE, fixtures_dir: Optional[str] = None, raw_dir: Optional[str] = None, page_size: int = 10000):
        self.base, self.fixtures_dir, self.raw_dir, self.page_size = base, fixtures_dir, raw_dir, page_size
        self.truncated: List[str] = []

    def _rows(self, ep: str, params: dict, fixture: str) -> List[dict]:
        if self.fixtures_dir:
            p = os.path.join(self.fixtures_dir, fixture)
            if not os.path.exists(p):
                raise ProviderError("fixture missing: %s" % p)
            return list(csv.DictReader(open(p, encoding="utf-8")))
        rows: List[dict] = []
        page = 1
        while True:
            q = dict(params, **{"page[size]": str(self.page_size), "page[number]": str(page)})
            text = _get(self.base + ep + "?" + urllib.parse.urlencode(q, safe=":,"))
            j = json.loads(text)
            data = j.get("data") or []
            rows += data
            total = int((j.get("meta") or {}).get("total-count") or 0)
            if len(data) < self.page_size or len(rows) >= total or page >= 12:
                if len(rows) < total:
                    self.truncated.append("%s: %d of %d rows" % (ep.split("/")[-1], len(rows), total))
                break
            page += 1
            time.sleep(0.5)
        if self.raw_dir:
            os.makedirs(self.raw_dir, exist_ok=True)
            open(os.path.join(self.raw_dir, fixture.replace(".csv", ".json")), "w", encoding="utf-8").write(json.dumps(rows)[:5_000_000])
        return rows

    def cash(self, since: str) -> List[dict]:
        return self._rows(self.EP_CASH, {"filter": "record_date:gte:" + since, "fields": "record_date,account_type,open_today_bal", "sort": "-record_date"}, "dts_cash.csv")

    def tx(self, since: str) -> List[dict]:
        return self._rows(self.EP_TX, {"filter": "record_date:gte:" + since, "fields": "record_date,transaction_type,transaction_catg,transaction_catg_desc,transaction_today_amt,transaction_mtd_amt,transaction_fytd_amt", "sort": "-record_date"}, "dts_tx.csv")

    def debt(self, since: str) -> List[dict]:
        return self._rows(self.EP_DEBT, {"filter": "record_date:gte:" + since, "fields": "record_date,debt_catg,close_today_bal", "sort": "-record_date"}, "dts_debt.csv")

    # ── extraction (all $M) ──
    @staticmethod
    def _f(v) -> Optional[float]:
        try:
            return float(str(v).replace(",", "")) if v not in (None, "", "null") else None
        except ValueError:
            return None

    @classmethod
    def cash_series(cls, rows: List[dict]) -> Dict[str, Series]:
        """DTS:tga_close / DTS:tga_open / DTS:total_deposits / DTS:total_withdrawals (account_type substrings, post-Apr-2022 format)."""
        keys = {"DTS:tga_close": "Closing Balance", "DTS:tga_open": "Opening Balance", "DTS:total_deposits": "Total TGA Deposits", "DTS:total_withdrawals": "Total TGA Withdrawals"}
        m: Dict[str, Dict[str, float]] = {k: {} for k in keys}
        for r in rows:
            at = r.get("account_type") or ""
            v = cls._f(r.get("open_today_bal"))
            if v is None:
                continue
            for k, sub in keys.items():
                if sub in at:
                    m[k][r["record_date"]] = v
        return {k: sorted(d.items()) for k, d in m.items()}

    @classmethod
    def tx_series(cls, rows: List[dict], dep_keys: List[str], wd_keys: List[str]) -> Dict[str, Series]:
        """Line items by exact transaction_catg AND side (DTS Tracker keys; 'Dept of Defense (DoD) - misc' and 'HHS - misc' exist on both sides)
        → three series each: DTS:D|<key> / DTS:W|<key> (today), …|mtd, …|fytd.
        Plus DTS:debt_issues / DTS:debt_redemptions (Public Debt Cash Issues/Redemp.) and DTS:tot_dep_tx / DTS:tot_wd_tx (the catg='null' totals)."""
        want = {"D": set(dep_keys), "W": set(wd_keys)}
        m: Dict[str, Dict[str, float]] = {}

        def put(name: str, d: str, v: Optional[float]):
            if v is not None:
                m.setdefault(name, {})[d] = v

        for r in rows:
            d = r["record_date"]
            catg = (r.get("transaction_catg") or "").strip()
            desc = (r.get("transaction_catg_desc") or "").strip()
            typ = (r.get("transaction_type") or "").lower()
            today, mtd, fytd = cls._f(r.get("transaction_today_amt")), cls._f(r.get("transaction_mtd_amt")), cls._f(r.get("transaction_fytd_amt"))
            lc = catg.lower()
            side = "D" if typ.startswith("deposit") else "W" if typ.startswith("withdrawal") else None
            if side and (catg in want[side] or (desc in want[side] and desc != "null")):
                key = "DTS:%s|%s" % (side, catg if catg in want[side] else desc)
                put(key, d, today); put(key + "|mtd", d, mtd); put(key + "|fytd", d, fytd)
            if "public debt cash iss" in lc:
                for suf, v in (("", today), ("|mtd", mtd), ("|fytd", fytd)):
                    m.setdefault("DTS:debt_issues" + suf, {})[d] = (m.get("DTS:debt_issues" + suf, {}).get(d, 0.0) + (v or 0.0))
            elif "public debt cash redemp" in lc:
                for suf, v in (("", today), ("|mtd", mtd), ("|fytd", fytd)):
                    m.setdefault("DTS:debt_redemptions" + suf, {})[d] = (m.get("DTS:debt_redemptions" + suf, {}).get(d, 0.0) + (v or 0.0))
            elif catg in ("", "null") and desc in ("", "null"):
                # the DTS total rows carry no category label: one Deposits + one Withdrawals row per date
                nm = "DTS:tot_dep_tx" if typ.startswith("deposit") else "DTS:tot_wd_tx" if typ.startswith("withdrawal") else None
                if nm:
                    put(nm, d, today); put(nm + "|mtd", d, mtd); put(nm + "|fytd", d, fytd)
        return {k: sorted(v.items()) for k, v in m.items()}

    @classmethod
    def debt_series(cls, rows: List[dict]) -> Dict[str, Series]:
        pub: Dict[str, float] = {}
        intra: Dict[str, float] = {}
        limit: Dict[str, float] = {}
        for r in rows:
            v = cls._f(r.get("close_today_bal"))
            if v is None:
                continue
            c = r.get("debt_catg") or ""
            if c == "Debt Held by the Public":
                pub[r["record_date"]] = v
            elif c == "Intragovernmental Holdings":
                intra[r["record_date"]] = v
            elif c == "Statutory Debt Limit":
                limit[r["record_date"]] = v
        tot = {d: pub[d] + intra[d] for d in pub if d in intra}
        return {"DTS:debt_public": sorted(pub.items()), "DTS:debt_intragov": sorted(intra.items()), "DTS:debt_total": sorted(tot.items()), "DTS:debt_limit": sorted(limit.items())}
