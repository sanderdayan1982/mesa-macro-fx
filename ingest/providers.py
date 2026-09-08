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
