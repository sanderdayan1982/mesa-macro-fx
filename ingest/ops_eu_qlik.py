"""EU (European Commission) debt securities — the Qlik Sense 'EU debt securities data' dashboard (verified 2026-09-10).

Page: https://commission.europa.eu/strategy-and-policy/eu-budget/eu-borrower-investor-relations/eu-debt-securities-data_en
embeds a public Qlik mashup https://dashboard.tech.ec.europa.eu/qs_digit_dashboard_mt/public/extensions/BUDG_NGEUTransactions/BUDG_NGEUTransactions.html
(app 170eea17-0abf-4dc8-bb7b-300e7cb67ef7). The data is read with the Qlik Engine JSON-RPC API over a websocket
(OpenDoc → CreateSessionObject with a hypercube of plain dimensions → GetHyperCubeData), which needs the `websocket-client`
package (`pip install "websocket-client>=1.6"`; NOT added to requirements — the import lives inside fetch_qlik_table so the
module imports without it and the runner falls back to the fixtures fixtures/eur_hist/eu_*_qlik_<date>.csv).

Transactions fields: ISIN, Instrument (Bills | Bonds | NGEU green bonds | SURE social bonds), Type (NEW|TAP), Issue format (Auction|Syndication),
Transaction date, Date of settlement, Maturity, Volume issued (EUR m), Coupon ('0.13%'), Date of NCB, Settlement date NCB, Amount of NCB
(non-competitive bond-auction leg, T+3), New o/s amounts; other fields exist (Weighted average price, Yield, Cover ratio, Volume bids, Old o/s amounts,
Source, Green, Press release link). Outstanding fields: ISIN, Instrument, Maturity, Coupon, Outstanding amount, Date of data, To be quoted.
A hypercube of N dimensions returns the cross-product of the attribute values with '-' where the combination does not exist, so a real
transaction row is one with a Transaction date, a numeric Volume issued and Issue format in {Auction, Syndication}; the outstanding table lists the
same ISIN twice (coupon row with '-' amount, amount row with '-' coupon) → merged per ISIN.
Dates dd/mm/yyyy; amounts EUR millions. Calendars are GROSS (the Eurosystem does not publish holdings by ISIN)."""
from __future__ import annotations
import csv
import io
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from .series import Series
from .ops_eur import _num, _iso, _bucket, REC_COLS, merge_records

APP_ID = "170eea17-0abf-4dc8-bb7b-300e7cb67ef7"
HOST = "dashboard.tech.ec.europa.eu"
PREFIX = "/qs_digit_dashboard_mt/"
MASHUP_PATH = "public/extensions/BUDG_NGEUTransactions/BUDG_NGEUTransactions.html"
PAGE_URL = "https://commission.europa.eu/strategy-and-policy/eu-budget/eu-borrower-investor-relations/eu-debt-securities-data_en"
TX_FIELDS = ["ISIN", "Instrument", "Type", "Issue format", "Transaction date", "Date of settlement", "Maturity", "Volume issued", "Coupon",
             "Date of NCB", "Settlement date NCB", "Amount of NCB", "New o/s amounts"]
TX_FIELDS_EXTRA = TX_FIELDS + ["Weighted average price", "Yield", "Cover ratio"]
OUT_FIELDS = ["ISIN", "Instrument", "Maturity", "Coupon", "Outstanding amount", "Date of data", "To be quoted"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


class QlikError(RuntimeError):
    """provider-style failure: the caller falls back to the fixture CSV"""


# ═══════════════════════ Qlik Engine JSON-RPC over websocket ═══════════════════════
def _session(origin: str, vp_prefix: str, timeout: int, mashup_url: str = "") -> Tuple[str, str]:
    """Qlik Sense virtual proxy handshake as the mashup does it (observed 2026-09-10 in the browser): (1) GET the mashup page under the
    virtual proxy → the proxy sets the session cookie (X-Qlik-Session-*); (2) GET {vp_prefix}qps/csrftoken?xrfkey=<16 chars> with header
    X-Qlik-Xrfkey and the cookie → 204 with response header `qlik-csrf-token` (403 without the cookie). Returns (Cookie header, token)."""
    import urllib.request
    import http.cookiejar
    import random
    import string
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    base_hdr = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-GB,en;q=0.9", "Referer": mashup_url or origin + vp_prefix}
    if mashup_url:
        try:
            with opener.open(urllib.request.Request(mashup_url, headers=dict(base_hdr, Accept="text/html,*/*")), timeout=timeout) as resp:
                resp.read(65536)
        except Exception as e:  # noqa: BLE001
            raise QlikError("mashup GET failed: %s" % e)
    xrf = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
    req = urllib.request.Request(origin + vp_prefix + "qps/csrftoken?xrfkey=" + xrf, headers=dict(base_hdr, **{"X-Qlik-Xrfkey": xrf, "Origin": origin}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            token = resp.headers.get("qlik-csrf-token") or ""
    except Exception as e:  # noqa: BLE001
        raise QlikError("csrftoken GET failed: %s (cookies after mashup GET: %s)" % (e, ",".join(c.name for c in jar) or "none"))
    cookie = "; ".join("%s=%s" % (c.name, c.value) for c in jar)
    return cookie, token


class _Rpc:
    def __init__(self, ws, timeout: int):
        self.ws, self.timeout, self.id = ws, timeout, 0

    def call(self, handle: int, method: str, params) -> dict:
        self.id += 1
        rid = self.id
        try:
            self.ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "handle": handle, "method": method, "params": params}))
        except Exception as e:  # noqa: BLE001
            raise QlikError("send %s failed: %s" % (method, e))
        for _ in range(200):  # skip unsolicited messages (OnConnected, change notifications, ...)
            try:
                raw = self.ws.recv()
            except Exception as e:  # noqa: BLE001
                raise QlikError("recv after %s failed: %s" % (method, e))
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, dict) or msg.get("id") != rid:
                continue
            if "error" in msg:
                raise QlikError("%s → %s" % (method, msg["error"]))
            res = msg.get("result")
            if not isinstance(res, dict):
                raise QlikError("%s → no result" % method)
            return res
        raise QlikError("%s: no response after 200 messages" % method)


def fetch_qlik_table(fields: List[str], app_id: str = APP_ID, host: str = HOST, prefix: str = PREFIX, mashup_path: str = MASHUP_PATH,
                     timeout: int = 60, page: int = 500) -> List[List[str]]:
    """rows of qText cells (one per field), via OpenDoc → CreateSessionObject(hypercube) → GetLayout → GetHyperCubeData pages.
    Needs `websocket-client>=1.6` (import websocket). Raises QlikError on any failure."""
    try:
        import websocket  # websocket-client
    except ImportError:
        raise QlikError("websocket-client not installed (pip install 'websocket-client>=1.6')")
    if not fields:
        raise QlikError("no fields")
    n = len(fields)
    origin = "https://" + host
    vp = prefix + "public/"  # the mashup runs on the 'public' virtual proxy: wss://host/<prefix>public/app/<id>/identity/<x>?reloadUri=…&qlik-csrf-token=…
    cookies, token = _session(origin, vp, timeout, mashup_url=origin + prefix + mashup_path)
    headers = ["Origin: " + origin, "User-Agent: " + UA]
    if cookies:
        headers.append("Cookie: " + cookies)
    import time as _t
    import urllib.parse
    url = "wss://" + host + vp + "app/" + app_id + "/identity/mesa%d" % int(_t.time()) + "?reloadUri=" + urllib.parse.quote(origin + prefix + mashup_path, safe="") + \
          ("&qlik-csrf-token=" + token if token else "")
    try:
        ws = websocket.create_connection(url, header=headers, timeout=timeout, suppress_origin=True)
    except Exception as e:  # noqa: BLE001
        raise QlikError("websocket connect %s failed: %s" % (url, e))
    rows: List[List[str]] = []
    try:
        rpc = _Rpc(ws, timeout)
        doc = rpc.call(-1, "OpenDoc", [app_id])
        dh = (doc.get("qReturn") or {}).get("qHandle")
        if dh is None:
            raise QlikError("OpenDoc: no qHandle in %s" % doc)
        cube = {"qInfo": {"qType": "t"},
                "qHyperCubeDef": {"qDimensions": [{"qDef": {"qFieldDefs": ["[%s]" % f]}, "qNullSuppression": False} for f in fields], "qMeasures": [],
                                  "qInitialDataFetch": [{"qTop": 0, "qLeft": 0, "qHeight": 1, "qWidth": n}]}}
        obj = rpc.call(dh, "CreateSessionObject", [cube])
        oh = (obj.get("qReturn") or {}).get("qHandle")
        if oh is None:
            raise QlikError("CreateSessionObject: no qHandle in %s" % obj)
        lay = rpc.call(oh, "GetLayout", [])
        hc = ((lay.get("qLayout") or {}).get("qHyperCube") or {})
        total = int((hc.get("qSize") or {}).get("qcy") or 0)
        if hc.get("qError"):
            raise QlikError("hypercube error %s" % hc["qError"])
        top = 0
        while top < total:
            h = max(1, min(page, 10000 // n))  # Qlik caps a page at 10 000 cells
            res = rpc.call(oh, "GetHyperCubeData", ["/qHyperCubeDef", [{"qTop": top, "qLeft": 0, "qHeight": h, "qWidth": n}]])
            pages = res.get("qDataPages") or []
            mat = pages[0].get("qMatrix") if pages else None
            if not mat:
                break
            for r in mat:
                rows.append([str(c.get("qText", "")) if isinstance(c, dict) else "" for c in r])
            top += len(mat)
        if total and len(rows) != total:
            raise QlikError("expected %d rows, got %d" % (total, len(rows)))
    finally:
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass
    return rows


# ═══════════════════════ CSV (fixture format: header = field names, quoted values) ═══════════════════════
def rows_to_csv(fields: List[str], rows: List[List[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(fields)
    wq = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    for r in rows:
        wq.writerow(list(r) + [""] * (len(fields) - len(r)))
    return buf.getvalue()


def csv_to_rows(text: str) -> Tuple[List[str], List[List[str]]]:
    rd = csv.reader(io.StringIO(text))
    fields = next(rd, [])
    return fields, [r for r in rd if r]


def _dicts(fields: List[str], rows: List[List[str]]) -> List[Dict[str, str]]:
    return [{f: (r[i] if i < len(r) else "") for i, f in enumerate(fields)} for r in rows]


def _val(v) -> Optional[float]:
    return _num(v)  # '-' → None, '0.13%' → 0.13, '1,234' → 1234


# ═══════════════════════ transactions → REC_COLS ═══════════════════════
def transactions_from_rows(fields: List[str], rows: List[List[str]]) -> List[dict]:
    """real transaction rows only (transaction date + numeric volume + Issue format in {Auction, Syndication}); NCB leg as a '#noncomp' record"""
    out, seen = [], set()
    for d in _dicts(fields, rows):
        a, s = _iso(d.get("Transaction date")), _iso(d.get("Date of settlement"))
        nom = _val(d.get("Volume issued"))
        fmt = str(d.get("Issue format", "")).strip()
        if not a or not nom or fmt not in ("Auction", "Syndication"):
            continue
        isin = str(d.get("ISIN", "")).strip()
        kind = "bill" if str(d.get("Instrument", "")).strip() == "Bills" else "bond"
        price = _val(d.get("Weighted average price")) if "Weighted average price" in d else None
        src = "eu_qlik:%s:%s:%s" % (isin, a, fmt.lower())
        base = {"issuer": "EU", "kind": kind, "isin": isin, "auction": a, "settlement": s or "", "maturity": _iso(d.get("Maturity")) or "", "nominal": nom,
                "cash": round(nom * price / 100.0, 3) if price else nom, "cover": _val(d.get("Cover ratio")) if "Cover ratio" in d else None,
                "yield": _val(d.get("Yield")) if "Yield" in d else None, "source": src}
        recs = [base]
        ncb, s2 = _val(d.get("Amount of NCB")), _iso(d.get("Settlement date NCB"))
        if ncb and ncb > 0 and s2:
            recs.append(dict(base, settlement=s2, nominal=ncb, cash=round(ncb * price / 100.0, 3) if price else ncb, cover=None, source=src + "#noncomp"))
        for r in recs:
            k = tuple(str(r[c]) for c in REC_COLS)
            if k not in seen:
                seen.add(k)
                out.append(r)
    return out


# ═══════════════════════ outstanding → per ISIN ═══════════════════════
def outstanding_from_rows(fields: List[str], rows: List[List[str]]) -> List[dict]:
    """{isin, instrument, kind, maturity, coupon (% or None), outstanding (EUR m), asof} merging the coupon row and the amount row of each ISIN"""
    by: Dict[str, dict] = {}
    order: List[str] = []
    for d in _dicts(fields, rows):
        isin = str(d.get("ISIN", "")).strip()
        if not isin or isin == "-":
            continue
        if isin not in by:
            by[isin] = {"isin": isin, "instrument": str(d.get("Instrument", "")).strip(), "kind": "bill" if str(d.get("Instrument", "")).strip() == "Bills" else "bond",
                        "maturity": _iso(d.get("Maturity")) or "", "coupon": None, "outstanding": None, "asof": None}
            order.append(isin)
        o = by[isin]
        c, amt, asof = _val(d.get("Coupon")), _val(d.get("Outstanding amount")), _iso(d.get("Date of data"))
        if c is not None and o["coupon"] is None:
            o["coupon"] = c
        if amt is not None and asof and (o["asof"] is None or asof >= o["asof"]):
            o["outstanding"], o["asof"] = amt, asof
        if not o["maturity"] and _iso(d.get("Maturity")):
            o["maturity"] = _iso(d.get("Maturity"))
    return [by[i] for i in order]


# ═══════════════════════ calendar (GROSS) ═══════════════════════
def eu_calendar(outstanding: List[dict], horizon_days: int = 365, back_days: int = 60, today: Optional[date] = None) -> Dict[str, Series]:
    """eu_redemptions_gross_ahead (bills + bonds), eu_bill_maturities_ahead, eu_coupons_gross_paid / _ahead (annual on the maturity day-of-month,
    outstanding × coupon / 100, bonds only), eu_outstanding_total [(asof, Σ)] — GROSS (Eurosystem holdings by ISIN not published)"""
    today = today or date.today()
    tday = today.isoformat()
    end = (today + timedelta(days=horizon_days)).isoformat()
    start = (today - timedelta(days=back_days)).isoformat()
    red: Dict[str, float] = defaultdict(float)
    bill: Dict[str, float] = defaultdict(float)
    cpn: Dict[str, float] = defaultdict(float)
    tot, asof = 0.0, ""
    for l in outstanding:
        m, n, c = l.get("maturity"), l.get("outstanding") or 0.0, l.get("coupon")
        if not n:
            continue
        tot += n
        asof = max(asof, l.get("asof") or "")
        if not m:
            continue
        if tday < m <= end:
            red[m] += n
            if l.get("kind") == "bill":
                bill[m] += n
        if c and l.get("kind") != "bill":
            for yy in range(int(start[:4]), int(end[:4]) + 1):
                try:
                    d = date(yy, int(m[5:7]), int(m[8:10])).isoformat()
                except ValueError:
                    continue
                if start <= d <= end and d <= m:
                    cpn[d] += n * c / 100.0
    return {"eu_redemptions_gross_ahead": _bucket(red), "eu_bill_maturities_ahead": _bucket(bill),
            "eu_coupons_gross_paid": _bucket({d: v for d, v in cpn.items() if d <= tday}), "eu_coupons_gross_ahead": _bucket({d: v for d, v in cpn.items() if d > tday}),
            "eu_outstanding_total": [(asof or tday, round(tot, 3))] if outstanding else []}


# ═══════════════════════ convenience ═══════════════════════
def records_from_fixture_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    f, r = csv_to_rows(open(path, encoding="utf-8").read())
    return transactions_from_rows(f, r)


def outstanding_from_fixture_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    f, r = csv_to_rows(open(path, encoding="utf-8").read())
    return outstanding_from_rows(f, r)


def merge_eu_archive(path: str, records: List[dict]) -> List[dict]:
    return merge_records(path, records)


if __name__ == "__main__":  # network smoke: python3 -m ingest.ops_eu_qlik [--extra]
    fl = TX_FIELDS_EXTRA if "--extra" in sys.argv else TX_FIELDS
    try:
        tx = fetch_qlik_table(fl)
        print("transactions: %d raw rows → %d records" % (len(tx), len(transactions_from_rows(fl, tx))))
        ou = fetch_qlik_table(OUT_FIELDS)
        print("outstanding: %d raw rows → %d ISINs" % (len(ou), len(outstanding_from_rows(OUT_FIELDS, ou))))
        if "--save" in sys.argv:
            d = date.today().isoformat()
            open("fixtures/eur_hist/eu_transactions_qlik_%s.csv" % d, "w", encoding="utf-8").write(rows_to_csv(fl, tx))
            open("fixtures/eur_hist/eu_outstanding_qlik_%s.csv" % d, "w", encoding="utf-8").write(rows_to_csv(OUT_FIELDS, ou))
    except QlikError as e:
        print("QlikError:", e)
        sys.exit(1)
