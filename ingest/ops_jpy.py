"""JPY v0.4 — BoJ daily "Sources of Changes in Current Account Balances" (all three columns), BoJ operations by offer (ope*.xlsx),
BoJ monthly projections (juqp*.xlsx), BoJ JGB holdings by issue (mei*.xlsx), MoF auction results (JGB / T-Bill XLS) → net issuance,
redemption and coupon calendars netted for the BoJ's holdings.

Units: everything is JPY 100 million (億円, "100m"). BoJ files are already 100m. MoF T-Bill XLS is in BILLIONS of yen → ×10 here.
MoF JGB XLS is in 100m. US-dollar funds-supplying operations are in USD million in the ope file → kind 'usd_funds', excluded from JPY flows.

Signs: + = current account balances (reserves) CREATED, − = destroyed.
  Daily file lines carry the BoJ's own sign (財政等要因 受超 = minus, 国債買入 = plus, SLF JP row = supply (+), EN row = the previous
  day's repurchase (−); JP + EN rows are summed, as the existing BojDailyCabProvider does).
  Operations (ope file, FACE amounts):
    jgb_purch / tbill_purch / corp_bonds : + allotted at the start (settlement) date.
    tbill_sales / bills_sold             : − allotted at start (bills_sold: + at end when the BoJ bill matures).
    slf / slf_usd (sales of JGSs under repurchase agreements): − allotted at start (the BoJ SELLS JGSs, takes cash), + at end
                                           (the BoJ repurchases → reserves created).
    jgs_repo_buy / pooled / loans / cp_repo: + at start (funds supplied), − at end (repaid → reserves destroyed).
    jgs_repo_sell                         : − at start, + at end.
    usd_funds                             : USD million, ignored in JPY flows (listed in the records only).
  Net issuance (MoF): − issued_total on the issue date; + redemption on maturity (T-Bills gross — the BoJ's T-Bill holdings are not in
  mei —; JGBs net of the BoJ's holdings by maturity from mei); coupons = principal × coupon / 200 on the maturity day-of-month and six
  months earlier (principal net of the BoJ's holding of that issue when netting). Weekend dates roll to the next Monday.
Caveats (documented, not corrected): the outstanding per JGB issue is Σ issued_total over the auctions in the MoF XLS (reopenings
  included) — MoF buybacks, BoJ→government sales and the CPI indexation of 物価連動債 are ignored; T-Bill maturities are gross of
  the BoJ's holdings; the daily file's 国債買入 line is CASH while the ope file is FACE (reconcile_ops measures the gap).
Nothing here decides a regime: shadow components only."""
from __future__ import annotations
import csv
import io
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from .series import Series, clean

# ───────────────────────── generic helpers ─────────────────────────
_MON = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}


def _num(v) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("△", "-").replace("▲", "-")
    if s in ("", "-", "―", "－", "—", "…"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _iso(v) -> Optional[str]:
    """datetime / date / 'YYYY-MM-DD…' / Excel serial → ISO date"""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    f = _num(s)
    if f is not None and 20000 < f < 80000:
        return (date(1899, 12, 30) + timedelta(days=int(f))).isoformat()
    return None


def _norm(s) -> str:
    return re.sub(r"[\s　]+", "", str(s)) if isinstance(s, str) else ""


def _is_jp(s) -> bool:
    return isinstance(s, str) and re.search(r"[぀-ヿ一-鿿！-～]", s) is not None


def business_days(start: str, end: str) -> List[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    out, d = [], d0
    while d <= d1:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _roll(d: str) -> str:
    """weekend → next Monday (payment / settlement convention for calendar dates)"""
    x = date.fromisoformat(d)
    while x.weekday() >= 5:
        x += timedelta(days=1)
    return x.isoformat()


def _bucket(m: Dict[str, float]) -> Series:
    return clean(sorted((d, round(v, 3)) for d, v in m.items() if d))


def _dense(flows: Series, days: List[str]) -> Series:
    fm: Dict[str, float] = defaultdict(float)
    for d, v in flows:
        fm[d] += v
    return [(d, round(fm.get(d, 0.0), 3)) for d in days]


def read_xlsx_cells(blob: bytes, sheet: Optional[str] = None) -> List[List]:
    """openpyxl, values only: rows as lists (row 0 = Excel row 1); `sheet` by name, else the first sheet"""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)  # not read_only: BoJ files declare a short <dimension>, read_only truncates
    ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb[wb.sheetnames[0]]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return rows


def _cells(blob_or_cells, sheet: Optional[str] = None) -> List[List]:
    if isinstance(blob_or_cells, (bytes, bytearray)):
        return read_xlsx_cells(bytes(blob_or_cells), sheet)
    return [list(r) for r in blob_or_cells]


def _col_index(row: List, pred) -> Optional[int]:
    for i, v in enumerate(row):
        if isinstance(v, str) and pred(_norm(v)):
            return i
    return None


# ───────────────────────── 1. BoJ daily file (jd / jx / jp) ─────────────────────────
DAILY_ITEMS: List[Tuple[str, str]] = [  # (key, JP label regex, applied to the whitespace-stripped label)
    ("banknotes", r"^銀行券要因"), ("treasury", r"^財政等要因"), ("surplus", r"^資金過不足"),
    ("ops_ex_lsp", r"^金融調節（除く貸出支援基金）"), ("jgb_purch", r"^国債買入"), ("tbill_purch", r"^国庫短期証券買入"),
    ("tbill_sales", r"^国庫短期証券売却"), ("jgs_repo_buy", r"^国債買現先"), ("jgs_repo_sell", r"^国債売現先"),
    ("pooled_ho", r"^共通担保オペ（本店）"), ("pooled_all", r"^共通担保オペ（全店）"), ("cp_repo", r"^(ＣＰ|CP)買現先"),
    ("bills_sold", r"^手形売出"), ("corp_bonds", r"^社債等買入"), ("disaster", r"^被災地金融機関支援オペ"), ("climate", r"^気候変動対応オペ"),
    ("loans", r"^貸出$"), ("slf", r"^国債補完供給"), ("slf_usd", r"^米ドルオペ用担保国債供給"), ("lsp", r"^金融調節（貸出支援基金）"),
    ("lsp_lending", r"^貸出増加支援資金供給"), ("subtotal", r"^小計"), ("net_change", r"^当座預金増減"), ("cab", r"^当座預金残高"),
    ("reserve_bal", r"^準備預金残高"), ("reserve_done", r"^積み終了先"), ("excess", r"^超過準備"), ("cab_nonres", r"^非準預先残高"),
    ("mbase", r"^マネタリーベース"), ("req_cum", r"所要準備額（積数）"), ("req_daily", r"所要準備額（１日平均）"),
    ("rem_cum", r"残り要積立額（積数）"), ("rem_daily", r"残り要積立額（１日平均）"),
]
DAILY_KEYS = [k for k, _ in DAILY_ITEMS]
VERSIONS = ("proj", "prov", "final")
_VER_HDR = {"proj": "予想", "prov": "速報", "final": "確報"}
_JP_MD = re.compile(r"（\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_EN_MD = re.compile(r"for\s+([A-Z][a-z]+)\s+(\d{1,2})")


def _daily_label(row: List) -> Optional[str]:
    for c in range(1, 5):
        if c < len(row) and isinstance(row[c], str) and row[c].strip():
            return _norm(row[c])
    return None


def parse_daily_file(blob, filename: str) -> dict:
    """{date (business day covered, ISO), kind ('jd'|'jx'|'jp'), proj: {key: value|None}, prov: {...}, final: {...}, notes: [str]}
    blob: xlsx bytes or a List[List] of cell values (sheet 当預). Values = JP-row + EN-row numbers per column (either may be empty)."""
    rows = _cells(blob, "当預")
    base = os.path.basename(filename or "")
    m = re.match(r"^(jd|jx|jp)(\d{4})(\d{2})(\d{2})", base)
    kind = m.group(1) if m else "jd"
    fyear = int(m.group(2)) if m else None
    fdate = "%s-%s-%s" % (m.group(2), m.group(3), m.group(4)) if m else None
    # title → month/day (JP first, EN as fallback), year from the file name (EN title has no year) else current year
    md: Optional[Tuple[int, int]] = None
    for row in rows[:12]:
        for v in row:
            if not isinstance(v, str):
                continue
            mj = _JP_MD.search(v)
            if mj:
                md = (int(mj.group(1)), int(mj.group(2)))
                break
            me = _EN_MD.search(v)
            if me and me.group(1) in _MON:
                md = (_MON[me.group(1)], int(me.group(2)))
                break
        if md:
            break
    year = fyear or date.today().year
    try:
        d = date(year, md[0], md[1]).isoformat() if md else fdate
    except ValueError:
        d = fdate
    # header row with 予想 / 速報 / 確報 → column indices
    cols: Dict[str, int] = {}
    for row in rows[:20]:
        for ver, hdr in _VER_HDR.items():
            i = _col_index(row, lambda s, h=hdr: s.startswith(h))
            if i is not None:
                cols[ver] = i
        if len(cols) == 3:
            break
    if len(cols) < 3:
        cols = {"proj": 5, "prov": 6, "final": 7}
    out = {ver: {k: None for k in DAILY_KEYS} for ver in VERSIONS}
    found = set()
    notes: List[str] = []
    in_notes = False
    for r, row in enumerate(rows):
        lab = _daily_label(row)
        if not lab:
            continue
        if lab.startswith("備考") or lab.startswith("Notes"):
            in_notes = True
        if in_notes:
            txt = next((str(v).strip() for v in row[2:] if isinstance(v, str) and v.strip()), None)
            if txt and re.match(r"^\d+\.$", str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""):
                notes.append(txt)
            continue
        if not _is_jp(lab):
            continue
        nxt = rows[r + 1] if r + 1 < len(rows) else []
        for key, pat in DAILY_ITEMS:
            if key in found or not re.search(pat, lab):
                continue
            found.add(key)
            for ver, ci in cols.items():
                a = _num(row[ci]) if ci < len(row) else None
                b = _num(nxt[ci]) if ci < len(nxt) else None
                out[ver][key] = None if a is None and b is None else (a or 0.0) + (b or 0.0)
            break
    return {"date": d, "kind": kind, "proj": out["proj"], "prov": out["prov"], "final": out["final"], "notes": notes}


# ───────────────────────── 2. wide series / 3. archive ─────────────────────────
def daily_records_to_wide(recs: List[dict]) -> Dict[str, Dict[str, Series]]:
    out: Dict[str, Dict[str, List]] = {v: {} for v in VERSIONS}
    for rec in recs:
        for ver in VERSIONS:
            for k, v in (rec.get(ver) or {}).items():
                if v is not None:
                    out[ver].setdefault(k, []).append((rec["date"], v))
    return {ver: {k: clean(s) for k, s in m.items()} for ver, m in out.items()}


ARCHIVE_COLS = ["date", "version"] + DAILY_KEYS


def read_daily_archive(path: str) -> List[dict]:
    """CSV rows → records {date, version, <keys>} (values float|None)"""
    if not os.path.exists(path):
        return []
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        out.append({"date": r["date"], "version": r["version"], **{k: _num(r.get(k)) for k in DAILY_KEYS}})
    return out


def merge_daily_archive(path: str, recs: List[dict]) -> List[dict]:
    """recs from parse_daily_file (one record → up to three CSV rows: proj/prov/final where any value is present) or archive rows;
    replaces the same (date, version); rewrites the CSV sorted by date, version"""
    seen: Dict[Tuple[str, str], dict] = {}
    for r in read_daily_archive(path):
        seen[(r["date"], r["version"])] = r
    for rec in recs:
        if "version" in rec:
            seen[(rec["date"], rec["version"])] = {"date": rec["date"], "version": rec["version"], **{k: rec.get(k) for k in DAILY_KEYS}}
            continue
        for ver in VERSIONS:
            vals = rec.get(ver) or {}
            if any(v is not None for v in vals.values()):
                seen[(rec["date"], ver)] = {"date": rec["date"], "version": ver, **{k: vals.get(k) for k in DAILY_KEYS}}
    order = {v: i for i, v in enumerate(VERSIONS)}
    rows = sorted(seen.values(), key=lambda r: (r["date"], order.get(r["version"], 9)))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ARCHIVE_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in ARCHIVE_COLS})
    return rows


# ───────────────────────── 4. surprise / best realized ─────────────────────────
def surprise(final_or_prov: Series, proj: Series) -> Series:
    """realized − projected on common dates"""
    p = {d: v for d, v in proj if v is not None}
    return clean([(d, v - p[d]) for d, v in final_or_prov if v is not None and d in p])


def best_realized(final: Series, prov: Series) -> Series:
    """final where available, else provisional"""
    m = {d: v for d, v in prov if v is not None}
    m.update({d: v for d, v in final if v is not None})
    return clean(list(m.items()))


# ───────────────────────── 5. BoJ operations by offer (ope*.xlsx) ─────────────────────────
OPE_COLS = [("offered", "オファー額"), ("start", "スタート日"), ("end", "エンド日"), ("rate", "貸付利率"), ("yield", "利回り"), ("bids", "応札総額"),
            ("allotted", "落札総額"), ("prorata_rate", "按分レート"), ("nonprorata_rate", "全取レート"), ("avg_rate", "平均落札レート"), ("prorata_pct", "按分比率")]


def classify_op(name_jp: str, name_en: str = "") -> str:
    n = _norm(name_jp)
    e = (name_en or "").lower()
    if "米ドル" in n and ("担保国債供給" in n or "国債供給" in n):
        return "slf_usd"
    if "米ドル" in n or "u.s. dollar" in e or "us dollar" in e:
        return "usd_funds"
    if "国債補完供給" in n:
        return "slf"
    if n.startswith("国債買入") or "国債買入" in n:
        return "jgb_purch"
    if "国庫短期証券買入" in n:
        return "tbill_purch"
    if "国庫短期証券売却" in n:
        return "tbill_sales"
    if "国債買現先" in n:
        return "jgs_repo_buy"
    if "国債売現先" in n:
        return "jgs_repo_sell"
    if "共通担保" in n:
        return "pooled"
    if "ＣＰ" in n or n.startswith("CP"):
        return "cp_repo"
    if "手形売出" in n:
        return "bills_sold"
    if "社債" in n:
        return "corp_bonds"
    if "貸出" in n or "資金供給" in n or "支援オペ" in n or "気候変動" in n or "被災地" in n:
        return "loans"
    return "other"


def parse_ope_file(blob, filename: str) -> List[dict]:
    """[{date (file date), instrument_jp, instrument_en, offered, start, end, rate, yield, bids, allotted, kind, prorata_rate,
    nonprorata_rate, avg_rate, prorata_pct}] — 100m (USD million for kind 'usd_funds'); columns located by the 種類 header row"""
    rows = _cells(blob, "オペ")
    base = os.path.basename(filename or "")
    m = re.search(r"(\d{4})(\d{2})(\d{2})", base)
    fdate = "%s-%s-%s" % m.groups() if m else None
    hdr_i = next((i for i, row in enumerate(rows) if any(isinstance(v, str) and _norm(v) == "種類" for v in row)), None)
    if hdr_i is None:
        return []
    hdr = rows[hdr_i]
    lab_c = next(i for i, v in enumerate(hdr) if isinstance(v, str) and _norm(v) == "種類")
    ci: Dict[str, int] = {}
    for key, jp in OPE_COLS:
        i = _col_index(hdr, lambda s, j=jp: s.startswith(j))
        if i is not None:
            ci[key] = i
    # month/day from the title, year from the file name
    title_d = None
    for row in rows[:hdr_i]:
        for v in row:
            if isinstance(v, str):
                mj = _JP_MD.search(v)
                if mj and fdate:
                    title_d = "%s-%02d-%02d" % (fdate[:4], int(mj.group(1)), int(mj.group(2)))
                    break
        if title_d:
            break
    fdate = title_d or fdate
    out: List[dict] = []
    i = hdr_i + 1
    while i < len(rows):
        row = rows[i]
        lab = row[lab_c] if lab_c < len(row) else None
        if isinstance(lab, str) and (lab.strip().startswith("(注") or lab.strip().startswith("（注") or lab.strip().lower().startswith("notes")):
            break
        if not (_is_jp(lab) and lab.strip() != "種類"):
            i += 1
            continue
        get = lambda k: row[ci[k]] if k in ci and ci[k] < len(row) else None
        start, end = _iso(get("start")), _iso(get("end"))
        if start is None and _num(get("offered")) is None and _num(get("allotted")) is None:
            i += 1
            continue
        en = ""
        nxt = rows[i + 1] if i + 1 < len(rows) else []
        nl = nxt[lab_c] if lab_c < len(nxt) else None
        if isinstance(nl, str) and nl.strip() and not _is_jp(nl):
            en = re.sub(r"\s+", " ", nl).strip()
            i += 1
        rec = {"date": fdate, "instrument_jp": re.sub(r"\s+", " ", lab).strip(), "instrument_en": en, "offered": _num(get("offered")), "start": start, "end": end,
               "rate": _num(get("rate")), "yield": _num(get("yield")), "bids": _num(get("bids")), "allotted": _num(get("allotted")),
               "prorata_rate": _num(get("prorata_rate")), "nonprorata_rate": _num(get("nonprorata_rate")), "avg_rate": _num(get("avg_rate")), "prorata_pct": _num(get("prorata_pct"))}
        rec["kind"] = classify_op(rec["instrument_jp"], en)
        out.append(rec)
        i += 1
    return out


# sign at START and at END per kind (× allotted); usd_funds excluded (USD)
OP_SIGNS: Dict[str, Tuple[float, float]] = {
    "jgb_purch": (1, 0), "tbill_purch": (1, 0), "corp_bonds": (1, 0), "tbill_sales": (-1, 0),
    "slf": (-1, 1), "slf_usd": (-1, 1), "jgs_repo_sell": (-1, 1), "bills_sold": (-1, 1),
    "jgs_repo_buy": (1, -1), "pooled": (1, -1), "loans": (1, -1), "cp_repo": (1, -1), "other": (0, 0), "usd_funds": (0, 0),
}


def ops_flows(ops: List[dict], daily_flow_line: Optional[Dict[str, Series]], days: List[str], today: Optional[str] = None) -> Dict[str, Series]:
    """By settlement (start) date, 100m, FACE amounts (see the module docstring for the sign per kind):
      jgb_purch_settled (+), tbill_purch_settled (+), tbill_sales_settled (−), slf_out (− at start), slf_back (+ at end),
      pooled_supplied (+ at start), pooled_repaid (− at end), ops_net_daily (dense over `days`, all kinds, events <= today),
      ops_calendar_ahead (end-of-operation events > today: − repayments of funds-supplying ops, + SLF/repo-sell repurchases),
      jgb_purch_face_minus_cash (reconcile vs daily_flow_line['jgb_purch'] when given), ops_by_kind_* (start-date buckets per kind)."""
    today = today or date.today().isoformat()
    ev_start: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    ev_end: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for o in ops:
        k, a = o.get("kind", "other"), o.get("allotted")
        s0, s1 = OP_SIGNS.get(k, (0, 0))
        if a is None or k == "usd_funds":
            continue
        st = o.get("start") or o.get("date")
        if st and s0:
            ev_start[k][st] += s0 * a
        if o.get("end") and s1:
            ev_end[k][o["end"]] += s1 * a
    net: Dict[str, float] = defaultdict(float)
    ahead: Dict[str, float] = defaultdict(float)
    for src in (ev_start, ev_end):
        for k, m in src.items():
            for d, v in m.items():
                if d <= today:
                    net[d] += v
    for k, m in ev_end.items():
        for d, v in m.items():
            if d > today:
                ahead[d] += v
    out: Dict[str, Series] = {
        "jgb_purch_settled": _bucket(ev_start["jgb_purch"]), "tbill_purch_settled": _bucket(ev_start["tbill_purch"]), "tbill_sales_settled": _bucket(ev_start["tbill_sales"]),
        "slf_out": _bucket(ev_start["slf"]), "slf_back": _bucket(ev_end["slf"]), "pooled_supplied": _bucket(ev_start["pooled"]), "pooled_repaid": _bucket(ev_end["pooled"]),
        "ops_net_daily": _dense(_bucket(net), [d for d in days if d <= today]), "ops_calendar_ahead": _bucket(ahead)}
    for k in ("jgs_repo_buy", "jgs_repo_sell", "loans", "cp_repo", "corp_bonds", "bills_sold", "slf_usd"):
        if ev_start.get(k):
            out["ops_by_kind_" + k] = _bucket(ev_start[k])
    if daily_flow_line and daily_flow_line.get("jgb_purch"):
        out["jgb_purch_face_minus_cash"] = reconcile_ops(out["jgb_purch_settled"], daily_flow_line["jgb_purch"])
    return out


def reconcile_ops(ops_net_by_kind_nominal: Series, daily_line_cash: Series) -> Series:
    """nominal (ope file, face) − cash (daily file line) on common dates; e.g. 国債買入 2026-09-10: 7 659 face vs 7 200 cash → 459"""
    c = {d: v for d, v in daily_line_cash if v is not None}
    return clean([(d, v - c[d]) for d, v in ops_net_by_kind_nominal if v is not None and d in c])


# ───────────────────────── 6. BoJ monthly projections (juqp*.xlsx) ─────────────────────────
JUQP_ITEMS = [("banknotes", r"^銀行券要因"), ("treasury", r"^財政等要因"), ("jgb_net", r"^国債等"), ("tbill_net", r"^国庫短期証券等"), ("other", r"^その他"), ("surplus", r"^資金過不足")]


def parse_juqp(blob) -> dict:
    """{month 'YYYY-MM', published (ISO), banknotes, treasury, jgb_net, tbill_net, other, surplus, prev_year {...}, yoy {...},
    shortage_days [ISO], surplus_days [ISO]} — 100m. Label cells carry 'JP\\nEN'; the first line is matched."""
    rows = _cells(blob)
    month = published = None
    for row in rows[:12]:
        for v in row:
            if isinstance(v, str):
                mm = re.search(r"(\d{4})年(\d{1,2})月", v)
                if mm and not month:
                    month = "%s-%02d" % (mm.group(1), int(mm.group(2)))
                mp = re.match(r"^\s*([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})\s*$", v)
                if mp and mp.group(1) in _MON and not published:
                    published = "%s-%02d-%02d" % (mp.group(3), _MON[mp.group(1)], int(mp.group(2)))
            elif isinstance(v, datetime) and not published:
                published = v.date().isoformat()
    cols: Dict[str, Optional[int]] = {"proj": None, "prev": None, "yoy": None}
    for row in rows:
        p = _col_index(row, lambda s: s.startswith("見込み"))
        if p is not None:
            cols = {"proj": p, "prev": _col_index(row, lambda s: s.startswith("前年実績")), "yoy": _col_index(row, lambda s: s.startswith("前年比"))}
            break
    out: dict = {"month": month, "published": published, "prev_year": {}, "yoy": {}, "shortage_days": [], "surplus_days": []}
    for k, _ in JUQP_ITEMS:
        out[k] = None
    found = set()
    for row in rows:
        lab_i = next((i for i, v in enumerate(row) if _is_jp(v)), None)
        if lab_i is None:
            continue
        lab = _norm(str(row[lab_i]).split("\n")[0])
        for k, pat in JUQP_ITEMS:
            if k in found or not re.search(pat, lab):
                continue
            found.add(k)
            get = lambda c: _num(row[c]) if c is not None and c < len(row) else None
            out[k] = get(cols["proj"]) if cols["proj"] is not None else next((_num(v) for v in row[lab_i + 1:] if _num(v) is not None), None)
            out["prev_year"][k] = get(cols["prev"])
            out["yoy"][k] = get(cols["yoy"])
            break
        if lab.startswith("主な不足日") or lab.startswith("主な余剰日"):
            raw = next((v for v in row[lab_i + 1:] if v not in (None, "") and not _is_jp(v)), None)
            days = _days_in_month(raw, month)
            out["shortage_days" if lab.startswith("主な不足日") else "surplus_days"] = days
    return out


def _days_in_month(raw, month: Optional[str]) -> List[str]:
    if raw is None or not month:
        return []
    s = str(raw) if not isinstance(raw, float) else str(int(raw))
    out = []
    for tok in re.findall(r"\d{1,2}", s):
        try:
            out.append("%s-%02d" % (month, int(tok)))
            date.fromisoformat(out[-1])
        except ValueError:
            out.pop()
    return out


# ───────────────────────── 7. BoJ JGB holdings by issue (mei*.xlsx) ─────────────────────────
def _tenor_from_type(t: str) -> Optional[int]:
    n = _norm(t)
    m = re.search(r"(\d+)年", n.translate(str.maketrans("０１２３４５６７８９", "0123456789")))
    if m:
        return int(m.group(1))
    if "物価連動" in n:
        return 10
    if "変動" in n:
        return 15
    return None


def parse_mei(blob, filename: str = "") -> dict:
    """{asof, published, rows: [{type_jp, type_en, tenor_years, issue_no, amount}]} — face, 100m. Column C = type label on the JP row
    (EN label on the row below); D = issue number; E = amount. Rows without a label inherit the previous type."""
    rows = _cells(blob, "mei")
    dts: List[str] = []
    for row in rows[:12]:
        for v in row:
            d = _iso(v) if isinstance(v, (datetime, date)) else None
            if d and d not in dts:
                dts.append(d)
    asof = dts[0] if dts else None
    published = dts[1] if len(dts) > 1 else None
    if not asof:
        m = re.search(r"mei(\d{2})(\d{2})(\d{2})", os.path.basename(filename or ""))
        if m:
            asof = "20%s-%s-%s" % m.groups()
    out: List[dict] = []
    cur_jp, cur_en = "", ""
    pending_en = False
    for row in rows:
        lab = row[2] if len(row) > 2 else None
        if isinstance(lab, str) and lab.strip() and "\n" not in lab:
            if _is_jp(lab):
                cur_jp, cur_en, pending_en = lab.strip(), "", True
            elif pending_en:
                cur_en, pending_en = lab.strip(), False
                for r in reversed(out):
                    if r["type_jp"] == cur_jp and not r["type_en"]:
                        r["type_en"] = cur_en
                    else:
                        break
        no, amt = (_num(row[3]) if len(row) > 3 else None), (_num(row[4]) if len(row) > 4 else None)
        if no is None or amt is None or not cur_jp:
            continue
        out.append({"type_jp": cur_jp, "type_en": cur_en, "tenor_years": _tenor_from_type(cur_jp), "issue_no": int(no), "amount": amt})
    return {"asof": asof, "published": published, "rows": out}


def mei_holdings_by_issue(mei: dict) -> Dict[Tuple[str, int], float]:
    out: Dict[Tuple[str, int], float] = defaultdict(float)
    for r in mei.get("rows", []):
        out[(r["type_jp"], r["issue_no"])] += r["amount"]
    return dict(out)


# ───────────────────────── 8. MoF auction results (XLS, xlrd) ─────────────────────────
SHEET_TENOR = {"40年債": 40, "30年債": 30, "20年債": 20, "15変動": 15, "10年債": 10, "GX10年債": 10, "10年物価連動": 10, "5年債": 5, "GX5年債": 5, "2年債": 2,
               "6年債": 6, "4年債": 4, "割3年": 3, "TB": None}


def _xlrd_book(path_or_bytes):
    import xlrd
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return xlrd.open_workbook(file_contents=bytes(path_or_bytes))
    return xlrd.open_workbook(path_or_bytes)


def _xl_date(v, book) -> Optional[str]:
    import xlrd
    f = _num(v)
    if f is None or not (20000 < f < 80000):
        return _iso(v)
    try:
        return xlrd.xldate.xldate_as_datetime(f, book.datemode).date().isoformat()
    except Exception:  # noqa
        return None


def _mof_header(sheet) -> Tuple[Optional[int], Dict[str, int]]:
    """header row = the row whose column 0 is 'Issue Number'; columns by header substring"""
    hi = next((i for i in range(min(sheet.nrows, 12)) if str(sheet.cell_value(i, 0)).strip().lower().startswith("issue number")), None)
    if hi is None:
        return None, {}
    hdr = [re.sub(r"\s+", " ", str(sheet.cell_value(hi, c))).strip() for c in range(sheet.ncols)]
    ci: Dict[str, int] = {}
    for c, h in enumerate(hdr):
        hl = h.lower()
        if not h:
            continue
        if hl.startswith("issue number"):
            ci.setdefault("issue_no", c)
        elif hl.startswith("auction date"):
            ci.setdefault("auction", c)
        elif hl.startswith("issue date"):
            ci.setdefault("issue", c)
        elif hl.startswith("maturity date"):
            ci.setdefault("maturity", c)
        elif hl == "maturity" or hl.startswith("maturity ("):
            ci.setdefault("tenor_label", c)
        elif "nominal coupon" in hl:
            ci.setdefault("coupon", c)
        elif hl.startswith("offering") or "[a+b]" in hl:
            ci.setdefault("offering", c)
        elif "competitive bids" in hl and "non" not in hl:
            ci.setdefault("bids", c)
        elif "non-price" in hl or "non price" in hl:
            two = ("Ⅱ" in h) or re.search(r"\bII\b", h) is not None
            ci.setdefault("npc2" if two else "npc1", c)
        elif "bids accepted" in hl and "non-competitive" not in hl and "accepted at" not in hl:
            ci.setdefault("accepted", c)
        elif "non-competitive" in hl:
            ci.setdefault("noncomp", c)
        elif "average price" in hl:
            ci.setdefault("avg_price", c)
        elif "yield at the average" in hl:
            ci.setdefault("avg_yield", c)
        elif "highest accepted yield" in hl and "price" not in hl:
            ci.setdefault("high_yield", c)
        elif "lowest accepted price" in hl:
            ci.setdefault("low_price", c)
        elif "yield at the lowest" in hl:
            ci.setdefault("low_yield", c)
    return hi, ci


def _mof_rows(book, sheet, type_jp: str, scale: float) -> List[dict]:
    hi, ci = _mof_header(sheet)
    if hi is None or "issue_no" not in ci or "auction" not in ci:
        return []
    out = []
    for r in range(hi + 1, sheet.nrows):
        row = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
        no = _num(row[ci["issue_no"]])
        auc = _xl_date(row[ci["auction"]], book)
        if no is None or auc is None:
            continue
        g = lambda k: (_num(row[ci[k]]) if k in ci and ci[k] < len(row) else None)
        accepted, npc1, npc2 = g("accepted") or 0.0, g("npc1") or 0.0, g("npc2") or 0.0
        rec = {"type_jp": type_jp, "tenor_years": SHEET_TENOR.get(type_jp, _tenor_from_type(type_jp)), "issue_no": int(no), "auction": auc,
               "issue": _xl_date(row[ci["issue"]], book) if "issue" in ci else None, "maturity": _xl_date(row[ci["maturity"]], book) if "maturity" in ci else None,
               "coupon": g("coupon"), "offering": _scale(g("offering"), scale), "bids": _scale(g("bids"), scale), "accepted": accepted * scale,
               "npc1": npc1 * scale, "npc2": npc2 * scale, "noncomp": _scale(g("noncomp"), scale), "issued_total": round((accepted + npc1 + npc2) * scale, 3),
               "avg_price": g("avg_price"), "avg_yield": g("avg_yield"), "high_yield": g("high_yield"), "low_price": g("low_price"), "low_yield": g("low_yield"),
               "tenor_label": (str(row[ci["tenor_label"]]).strip() if "tenor_label" in ci else None)}
        out.append(rec)
    return out


def _scale(v: Optional[float], k: float) -> Optional[float]:
    return None if v is None else round(v * k, 3)


def parse_mof_jgb_xls(path_or_bytes) -> List[dict]:
    """one sheet per type (40年債 … 割3年, TB); 100m. issued_total = accepted + NPC I + NPC II (non-competitive small-lot bids kept in
    'noncomp', not added — MoF's own 落札・割当額 definition). Footnote rows (strings in column 0) are skipped."""
    book = _xlrd_book(path_or_bytes)
    out: List[dict] = []
    for sh in book.sheets():
        out.extend(_mof_rows(book, sh, sh.name.strip(), 1.0))
    return out


def parse_mof_tbill_xls(path_or_bytes) -> List[dict]:
    """sheets FY2026 … FY2008, BILLIONS of yen → ×10 to 100m; type_jp 'TB'; tenor_label '3-month' etc."""
    book = _xlrd_book(path_or_bytes)
    out: List[dict] = []
    for sh in book.sheets():
        recs = _mof_rows(book, sh, "TB", 10.0)
        for r in recs:
            r["fy"] = sh.name.strip()
        out.extend(recs)
    return out


# ───────────────────────── 9. issue map / holdings by maturity ─────────────────────────
def issue_map(jgb_recs: List[dict]) -> Dict[Tuple[str, int], dict]:
    """(type_jp, issue_no) → {maturity, coupon, tenor_years, issued_total (Σ over auctions incl. reopenings), first_issue, auctions}"""
    out: Dict[Tuple[str, int], dict] = {}
    for r in jgb_recs:
        k = (r["type_jp"], r["issue_no"])
        e = out.get(k)
        if e is None:
            out[k] = {"maturity": r.get("maturity"), "coupon": r.get("coupon"), "tenor_years": r.get("tenor_years"), "issued_total": 0.0,
                      "first_issue": r.get("issue"), "auctions": 0}
            e = out[k]
        e["issued_total"] = round(e["issued_total"] + (r.get("issued_total") or 0.0), 3)
        e["auctions"] += 1
        if r.get("issue") and (e["first_issue"] is None or r["issue"] < e["first_issue"]):
            e["first_issue"] = r["issue"]
        if e["maturity"] is None:
            e["maturity"] = r.get("maturity")
        if e["coupon"] is None:
            e["coupon"] = r.get("coupon")
    return out


def mei_type_to_sheet(type_jp: str) -> Optional[str]:
    """mei type label → MoF XLS sheet name"""
    n = _norm(type_jp).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    tenor = _tenor_from_type(n)
    if "物価連動" in n:
        return "10年物価連動"
    if "変動" in n:
        return "15変動"
    if "GX" in n.upper() or "ＧＸ" in n or "クライメート" in n or "トランジション" in n:
        return "GX%d年債" % tenor if tenor else None
    m = re.match(r"^(\d+)年債$", n)
    if m:
        return "%s年債" % m.group(1)
    return ("%d年債" % tenor) if tenor else None


def mei_to_maturity(mei: dict, imap: Dict[Tuple[str, int], dict]) -> Dict[str, object]:
    """BoJ holdings summed by maturity date (ISO → 100m); key '_unmapped' = [(type_jp, issue_no, amount)] not found in the MoF map"""
    out: Dict[str, float] = defaultdict(float)
    unmapped: List[Tuple[str, int, float]] = []
    for r in mei.get("rows", []):
        sheet = mei_type_to_sheet(r["type_jp"])
        e = imap.get((sheet, r["issue_no"])) if sheet else None
        if e and e.get("maturity"):
            out[e["maturity"]] += r["amount"]
        else:
            unmapped.append((r["type_jp"], r["issue_no"], r["amount"]))
    res: Dict[str, object] = {d: round(v, 3) for d, v in sorted(out.items())}
    res["_unmapped"] = unmapped
    return res


def coupon_lines(imap: Dict[Tuple[str, int], dict], mei: Optional[dict]) -> List[dict]:
    """per (type, issue): principal (Σ issued_total), boj_holding (mei, via mei_type_to_sheet), coupon, maturity, first_issue —
    input for net_issuance(coupon_lines=…)"""
    hold: Dict[Tuple[str, int], float] = defaultdict(float)
    for r in (mei or {}).get("rows", []):
        sheet = mei_type_to_sheet(r["type_jp"])
        if sheet:
            hold[(sheet, r["issue_no"])] += r["amount"]
    out = []
    for (t, no), e in imap.items():
        if not e.get("maturity") or e.get("coupon") is None or t == "TB":
            continue
        out.append({"type_jp": t, "issue_no": no, "maturity": e["maturity"], "coupon": e["coupon"], "principal": e["issued_total"],
                    "boj_holding": round(hold.get((t, no), 0.0), 3), "first_issue": e.get("first_issue")})
    return out


# ───────────────────────── 10. net issuance ─────────────────────────
def net_issuance(jgb_recs: List[dict], tbill_recs: List[dict], mei_by_maturity: Dict[str, float], coupon_lines_: Optional[List[dict]], days: List[str],
                 today: Optional[str] = None, horizon_days: int = 365) -> Dict[str, Series]:
    """100m, + = reserves created. Flows (<= today): issued_jgb (−), issued_tbill (−), matured_tbill (+ gross), matured_jgb_gross (+),
    matured_jgb_net (+ gross − BoJ holding at that maturity, floored at 0), coupons_jgb_gross / coupons_jgb_net,
    net_issuance_private_daily (dense: −issued_jgb − issued_tbill + matured_tbill + matured_jgb_net; coupons kept OUT).
    Calendars (> today, horizon): jgb_redemptions_net_ahead, jgb_redemptions_gross_ahead, tbill_maturities_ahead, jgb_coupons_net_ahead,
    jgb_coupons_gross_ahead, boj_share_by_maturity [(maturity, share)].
    Weekend dates roll to Monday. JGB issues = MoF auction records only (Σ issued_total per issue; buybacks ignored); the 'TB' sheet of the
    JGB XLS is treated as bills."""
    today = today or date.today().isoformat()
    end = (date.fromisoformat(today) + timedelta(days=horizon_days)).isoformat()
    start = days[0] if days else today
    iss_j: Dict[str, float] = defaultdict(float)
    iss_t: Dict[str, float] = defaultdict(float)
    mat_t: Dict[str, float] = defaultdict(float)
    mat_j: Dict[str, float] = defaultdict(float)  # keyed by the ORIGINAL maturity date (for netting with mei), rolled later
    for r in jgb_recs:
        v = r.get("issued_total") or 0.0
        if r.get("type_jp") == "TB":
            if r.get("issue"):
                iss_t[_roll(r["issue"])] += v
            if r.get("maturity"):
                mat_t[_roll(r["maturity"])] += v
            continue
        if r.get("issue"):
            iss_j[_roll(r["issue"])] += v
        if r.get("maturity"):
            mat_j[r["maturity"]] += v
    for r in tbill_recs:
        v = r.get("issued_total") or 0.0
        if r.get("issue"):
            iss_t[_roll(r["issue"])] += v
        if r.get("maturity"):
            mat_t[_roll(r["maturity"])] += v
    mbm = {d: v for d, v in (mei_by_maturity or {}).items() if not str(d).startswith("_")}
    gross: Dict[str, float] = defaultdict(float)
    net_j: Dict[str, float] = defaultdict(float)
    share: List[Tuple[str, float]] = []
    for m, v in sorted(mat_j.items()):
        h = mbm.get(m, 0.0)
        rm = _roll(m)
        gross[rm] += v
        net_j[rm] += max(v - h, 0.0)
        if today < m <= end and v > 0:
            share.append((m, round(min(h / v, 1.0), 4)))
    cg: Dict[str, float] = defaultdict(float)
    cn: Dict[str, float] = defaultdict(float)
    for ln in coupon_lines_ or []:
        m, c = ln.get("maturity"), ln.get("coupon")
        if not m or not c or m < start:
            continue
        p, h = ln.get("principal") or 0.0, ln.get("boj_holding") or 0.0
        fi = ln.get("first_issue") or ""
        mo, dd = int(m[5:7]), int(m[8:10])
        for yy in range(int(start[:4]), int(end[:4]) + 1):
            for mm in (mo, (mo + 5) % 12 + 1):
                try:
                    d = date(yy, mm, dd).isoformat()
                except ValueError:
                    continue
                if not (start <= d <= end and d <= m and d > fi):
                    continue
                rd = _roll(d)
                cg[rd] += p * c / 200.0
                cn[rd] += max(p - h, 0.0) * c / 200.0
    net: Dict[str, float] = defaultdict(float)
    for src, sg in ((iss_j, -1), (iss_t, -1), (mat_t, 1), (net_j, 1)):
        for d, v in src.items():
            if d <= today:
                net[d] += sg * v
    past = lambda m, sg=1.0: _bucket({d: sg * v for d, v in m.items() if start <= d <= today})
    ahead = lambda m: _bucket({d: v for d, v in m.items() if today < d <= end})
    return {"issued_jgb": past(iss_j, -1.0), "issued_tbill": past(iss_t, -1.0), "matured_tbill": past(mat_t), "matured_jgb_gross": past(gross), "matured_jgb_net": past(net_j),
            "coupons_jgb_gross": past(cg), "coupons_jgb_net": past(cn), "net_issuance_private_daily": _dense(_bucket(net), [d for d in days if d <= today]),
            "jgb_redemptions_net_ahead": ahead(net_j), "jgb_redemptions_gross_ahead": ahead(gross), "tbill_maturities_ahead": ahead(mat_t),
            "jgb_coupons_net_ahead": ahead(cn), "jgb_coupons_gross_ahead": ahead(cg), "boj_share_by_maturity": share}
