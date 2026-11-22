"""Eurosystem weekly financial statement, asset item 7.1 by portfolio (t331u B5).

Source: weekly commentary HTML, Table 1 «Monetary policy securities portfolios»,
at amortised cost. Publication typically Tuesday; position date = «Reported value
as at <Friday>».

APP = CBPP3 + ABSPP + PSPP + CSPP (not SMP). PEPP is separate. SMP is recorded
but is not part of APP. Values in the table are EUR billions; we store millions
to reconcile with ILM.W.U2.C.A070100.U2.EUR and the monthly APP/PEPP files.

Does not replace the monthly APP_breakdown / PEPP_breakdown series.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from html import unescape
from typing import Dict, List, Optional, Tuple

WFS_HTML = "https://www.ecb.europa.eu/press/annual-reports-financial-statements/wfs/{year}/html/ecb.fs{yymmdd}.en.html"
PORTFOLIOS = {
    "Securities Markets Programme": "SMP",
    "Covered bond purchase programme 3": "CBPP3",
    "Asset-backed securities purchase programme": "ABSPP",
    "Public sector purchase programme": "PSPP",
    "Corporate sector purchase programme": "CSPP",
    "Pandemic emergency purchase programme": "PEPP",
}
APP_PARTS = ("CBPP3", "ABSPP", "PSPP", "CSPP")
MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}


def _strip(html: str) -> str:
    t = unescape(html.replace("\xa0", " ").replace("&nbsp;", " "))
    t = re.sub(r"<sup[^>]*>.*?</sup>", "", t, flags=re.I | re.S)
    t = re.sub(r"<br\s*/?>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_eur_billions(text: str) -> Optional[float]:
    t = _strip(text)
    if t in ("", "-", "–", "—"):
        return None
    m = re.search(r"(-?)\s*EUR\s+([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s+billion", t, re.I)
    if not m:
        return None
    sign = -1.0 if m.group(1) == "-" else 1.0
    return sign * float(m.group(2).replace(",", ""))


def parse_as_at(html: str) -> Optional[str]:
    t = _strip(html)
    m = re.search(r"Reported value as at\s+([0-9]{1,2})\s+([A-Za-z]+)\s+(20[0-9]{2})", t)
    if not m:
        return None
    day, mon, year = int(m.group(1)), MONTHS.get(m.group(2)), int(m.group(3))
    if not mon:
        return None
    return "%04d-%02d-%02d" % (year, mon, day)


def parse_table(html: str) -> Dict:
    """Return position_date, portfolios in EUR millions, app, pepp, smp, total."""
    pos = parse_as_at(html)
    # work on the Table 1 region if present
    start = html.find("Monetary policy securities portfolios")
    chunk = html[start:start + 12000] if start >= 0 else html
    rows = re.findall(r"<tr>(.*?)</tr>", chunk, flags=re.I | re.S)
    portfolios: Dict[str, float] = {}
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)
        if len(cells) < 2:
            continue
        name = _strip(cells[0])
        code = PORTFOLIOS.get(name)
        if not code:
            continue
        val = parse_eur_billions(cells[1])
        if val is None:
            continue
        portfolios[code] = round(val * 1000.0, 1)  # bn → millions
    missing = [c for c in list(APP_PARTS) + ["PEPP"] if c not in portfolios]
    app = round(sum(portfolios[c] for c in APP_PARTS if c in portfolios), 1) if not missing else None
    if any(c not in portfolios for c in APP_PARTS):
        app = None if missing else app
        # if any APP part missing, do not fill APP
        if any(c not in portfolios for c in APP_PARTS):
            app = None
    pepp = portfolios.get("PEPP")
    smp = portfolios.get("SMP")
    total = None
    if app is not None and pepp is not None:
        total = round(app + pepp + (smp or 0.0), 1)
    return {
        "position_date": pos,
        "portfolios_mn": portfolios,
        "app_mn": app,
        "pepp_mn": pepp,
        "smp_mn": smp,
        "app_pepp_smp_mn": total,
        "missing": missing,
    }


def commentary_url(pub_day: date) -> str:
    return WFS_HTML.format(year=pub_day.year, yymmdd=pub_day.strftime("%y%m%d"))


def recent_publication_tuesdays(today: date, weeks: int = 8) -> List[date]:
    # last Tuesday on or before today, then previous Tuesdays
    delta = (today.weekday() - 1) % 7
    tue = today - timedelta(days=delta)
    return [tue - timedelta(days=7 * i) for i in range(weeks)]


def reconcile_weekly_vs_ilm(app_pepp_smp_mn: Optional[float], ilm_mn: Optional[float], tol_mn: float = 200.0) -> Dict:
    """Compare 7.1 sum (table, 0.1 bn precision) with ILM A070100 (millions). Blank if a leg is missing."""
    if app_pepp_smp_mn is None or ilm_mn is None:
        return {"diff_mn": None, "status": "BLANK", "note": "falta una pata; no se rellena"}
    diff = round(app_pepp_smp_mn - ilm_mn, 1)
    # table is rounded to 0.1 bn = 100 mn
    ok = abs(diff) <= tol_mn
    return {"diff_mn": diff, "status": "OK" if ok else "CHECK", "note": "tolerancia 200 mn (redondeo a 0.1 bn de la tabla)"}


def reconcile_month_end(weekly: List[Tuple[str, float]], monthly: List[Tuple[str, float]]) -> List[Dict]:
    """Last weekly observation in each month vs monthly official file. No fill."""
    w_by = {}
    for d, v in weekly:
        w_by.setdefault(d[:7], []).append((d, v))
    m_by = {d[:7]: (d, v) for d, v in monthly}
    out = []
    for month, rows in sorted(w_by.items()):
        if month not in m_by:
            continue
        wd, wv = max(rows)
        md, mv = m_by[month]
        out.append({
            "month": month,
            "weekly_date": wd,
            "weekly_mn": wv,
            "monthly_date": md,
            "monthly_mn": mv,
            "diff_mn": round(wv - mv, 1),
        })
    return out


def load_html_fixture(fixtures_dir):
    from pathlib import Path
    if not fixtures_dir:
        return None
    p = Path(fixtures_dir)
    for cand in list(p.glob("ecb_fs*.html")) + list(p.glob("**/ecb_fs*.html")):
        return cand.read_text(encoding="utf-8", errors="replace")
    return None


def series_from_parsed(parsed):
    if not parsed.get("position_date") or parsed.get("app_mn") is None or parsed.get("pepp_mn") is None:
        return {}
    d = parsed["position_date"]
    out = {"WFS71:APP": [(d, parsed["app_mn"])], "WFS71:PEPP": [(d, parsed["pepp_mn"])]}
    if parsed.get("app_pepp_smp_mn") is not None:
        out["WFS71:TOTAL"] = [(d, parsed["app_pepp_smp_mn"])]
    return out


def fetch_wfs71(fixtures_dir=None, getter=None, today=None, weeks=12):
    """Return {id: [(date, value_mn), ...]}. With fixtures, no network."""
    html = load_html_fixture(fixtures_dir)
    if html:
        return series_from_parsed(parse_table(html))
    if getter is None:
        return {}  # production hook supplies getter; tests should use fixtures
    today = today or date.today()
    got = {}
    for tue in recent_publication_tuesdays(today, weeks=weeks):
        try:
            html = getter(commentary_url(tue))
        except Exception:
            continue
        parsed = parse_table(html)
        part = series_from_parsed(parsed)
        for k, rows in part.items():
            got.setdefault(k, []).extend(rows)
    for k in got:
        got[k] = sorted(set(got[k]))
    return got
