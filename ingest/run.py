"""Mesa Macro FX — ingestion runner.
Usage:
  python -m ingest.run --ccy cad --lane weekly|daily|monthly|all [--backfill] [--fixtures fixtures/cad]
Writes data/<ccy>/*.json, history/<ccy>/*.csv, logs/<ccy>/*.json. Never fetches from the browser: this is the only
place that talks to sources. Frontend and agents read the JSON only."""
from __future__ import annotations
import argparse
import csv
import json
import os
import sys
from typing import Dict, List, Optional
from . import blocks as B
from . import engine as E
from .providers import ValetProvider, ReceiverGeneralProvider, IadbProvider, OnsProvider, RbaProvider, ProviderError, fetch_rss
from . import blocks_gbp as BG
from . import blocks_aud as BA
from . import blocks_jpy as BJ
from . import providers_jpy as PJ
from . import blocks_chf as BC
from . import providers_chf as PC
from . import blocks_nzd as BN
from . import providers_nzd as PN
from . import blocks_usd as BU
from . import providers_usd as PU
from . import blocks_eur as BE
from . import providers_eur as PE
from .quality import evaluate_series, system_summary
from .series import Series, clean

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_json(path: str) -> Optional[dict]:
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return None
    return None


def save_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def _v04_window_days(a) -> int:
    """v0.4 flow window: MESA_V04_YEARS (default 3 years) on incremental lanes; a --backfill run (manual or the monthly cron) opens it to
    8 years so the archives cover every currency's calibration era (earliest 2020-03, CAD) for the replay. The sources behind the
    window are full-history files already downloaded, so the wider window costs parsing, not requests."""
    years = int(os.environ.get("MESA_V04_YEARS", "3"))
    if getattr(a, "backfill", False):
        years = max(years, 8)
    return years * 365


def append_history_csv(path: str, name: str, series: Series) -> None:
    """Append-only CSV per series (full history; JSON keeps only the compact window)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing: Dict[str, float] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) == 2 and row[0] != "date":
                    try:
                        existing[row[0]] = float(row[1])
                    except ValueError:
                        pass
    merged = dict(existing)
    merged.update({d: v for d, v in series if v is not None})
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", name])
        for d in sorted(merged):
            w.writerow([d, merged[d]])


def series_ids(cfg: dict, block: str) -> List[str]:
    return [s["id"] for s in cfg["blocks"][block]["series"].values() if s.get("id")]


def _merge_hist(hist_dir: str, got: Dict[str, Series], ids: List[str]) -> Dict[str, Series]:
    """incremental runs: merge with history CSVs so rolling windows keep their length"""
    for i in ids:
        p = os.path.join(hist_dir, "%s.csv" % i)
        if os.path.exists(p):
            old = [(r[0], float(r[1])) for r in csv.reader(open(p)) if r and r[0] != "date"]
            got[i] = clean(old + got.get(i, []))
    return got


def fetch_cad(cfg: dict, a, prev: dict, hist_dir: str, oplog: str, errors: List[str]) -> Dict[str, dict]:
    blocks: Dict[str, dict] = {k: v for k, v in prev.items() if v}
    valet = ValetProvider(cfg["sources"]["valet"]["base_url"], fixtures_dir=a.fixtures)
    rg_cfg = cfg["sources"]["receiver_general"]
    rgp = ReceiverGeneralProvider(rg_cfg["csv_current"], rg_cfg["csv_archive"], fixtures_dir=a.fixtures)

    lanes = ["weekly", "daily", "monthly"] if a.lane == "all" else [a.lane]
    start = cfg["sources"]["valet"]["params"]["backfill"].split("=")[1] if a.backfill else None
    recent = None if a.backfill else int(cfg["sources"]["valet"]["params"]["incremental"].split("=")[1])

    def fetch_valet(ids: List[str]) -> Dict[str, Series]:
        try:
            got = valet.fetch(ids, start_date=start, recent=recent)
        except ProviderError as e:
            errors.append("valet: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "valet", "error": str(e)})
            return {i: [] for i in ids}
        # incremental: merge with history CSVs so percentiles keep their window
        if not a.backfill and not a.fixtures:
            for i in ids:
                p = os.path.join(hist_dir, "%s.csv" % i)
                if os.path.exists(p):
                    old = [(r[0], float(r[1])) for r in csv.reader(open(p)) if r and r[0] != "date"]
                    got[i] = clean(old + got[i])
        return got

    # ── 1 · central bank + 4 · rates (weekly lane also refreshes rates so spreads are current) ──
    if "weekly" in lanes or "daily" in lanes:
        ids = series_ids(cfg, "rates")
        rates_raw = fetch_valet(ids)
        blocks["rates"] = B.build_rates(cfg, rates_raw, prev.get("rates"))
        for i in ids:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, rates_raw.get(i, []))
    if "weekly" in lanes:
        ids = series_ids(cfg, "central_bank")
        cb_raw = fetch_valet(ids)
        blocks["central_bank"] = B.build_central_bank(cfg, cb_raw, prev.get("central_bank"))
        for i in ids:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, cb_raw.get(i, []))
    # ── 2 · fiscal (daily lane: Receiver General; weekly Valet cross-check) ──
    if "daily" in lanes or "weekly" in lanes:
        try:
            rg = rgp.fetch(include_archive=a.backfill)
        except ProviderError as e:
            errors.append("receiver_general: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "receiver_general", "error": str(e)})
            rg = {}
        if not a.backfill and not a.fixtures:
            for k in ReceiverGeneralProvider.KEYS:
                p = os.path.join(hist_dir, "%s.csv" % k)
                if os.path.exists(p):
                    old = [(r[0], float(r[1])) for r in csv.reader(open(p)) if r and r[0] != "date"]
                    rg[k] = clean(old + rg.get(k, []))
        fis_valet = fetch_valet(["V36628", "V36811"])
        blocks["fiscal"] = B.build_fiscal(cfg, fis_valet, rg, prev.get("fiscal"))
        for k in ReceiverGeneralProvider.KEYS:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, rg.get(k, []))
    # ── 3 · banking transmission (monthly) ──
    if "monthly" in lanes or (a.backfill and "weekly" in lanes):
        ids = series_ids(cfg, "banking")
        bk_raw = fetch_valet(ids)
        blocks["banking"] = B.build_banking(cfg, bk_raw, blocks.get("rates"), prev.get("banking"))
        for i in ids:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, bk_raw.get(i, []))

    # ── v0.4 · operation-level sources (daily + weekly lanes): Valet groups, daily indicators table ──
    if "daily" in lanes or "weekly" in lanes:
        _cad_v04(cfg, a, blocks, hist_dir, oplog, errors, rates_raw)
    return blocks


def _cad_v04(cfg: dict, a, blocks: Dict[str, dict], hist_dir: str, oplog: str, errors: List[str], rates_raw: Dict[str, Series]) -> None:
    """CAD v0.4 (CAMBIOS C1–C6): daily settlement balances archive, term repo / OR / ORR / RG AM auctions, net issuance to the
    private sector, CORRA IQR. Blocks are enriched in place; live scores untouched (shadow components_v04)."""
    from .providers import ValetGroupProvider, MarketOpsIndicatorsProvider
    from . import ops_cad as O
    from . import blocks_cad_v04 as V4
    v04 = cfg["sources"].get("valet_groups", {})
    gp = ValetGroupProvider(cfg["sources"]["valet"]["base_url"], fixtures_dir=a.fixtures)
    start = None if a.backfill else v04.get("incremental_start")
    rows: Dict[str, List[dict]] = {}
    for key, group in O.GROUPS.items():
        try:
            rows[key] = gp.fetch(group, start_date=start)
        except ProviderError as e:
            rows[key] = []
            errors.append("valet_group[%s]: %s" % (group, e))
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "valet_group", "group": group, "error": str(e)})
    # incremental runs merge with the archived rows so flows keep their history
    if not a.fixtures:
        for key, group in O.GROUPS.items():
            p = os.path.join(hist_dir, "groups", "%s.csv" % group)
            rows[key] = _merge_group_rows(p, rows[key])
    # daily indicators table → archive
    ind_path = os.path.join(hist_dir, "market_ops_indicators.csv")
    try:
        fresh = MarketOpsIndicatorsProvider(cfg["sources"].get("market_ops_indicators", {}).get("url", MarketOpsIndicatorsProvider().url), fixtures_dir=a.fixtures).fetch()
        ind = O.merge_archive(ind_path, fresh) if not a.fixtures else fresh
    except ProviderError as e:
        errors.append("market_ops_indicators: %s" % e)
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "market_ops_indicators", "error": str(e)})
        ind = O.read_archive(ind_path)
    from datetime import date, timedelta
    today = date.today().isoformat()
    days = O.business_days((date.today() - timedelta(days=_v04_window_days(a))).isoformat(), today)
    ops: Dict[str, Series] = {}
    ops.update(O.term_repo_series(rows.get("term_repo", []), days))
    ops.update(O.or_orr_series(rows.get("or", []), rows.get("orr", [])))
    rg = O.rgam_series(rows.get("rgam", []), days)
    iss = O.issuance_series(rows.get("tbill", []), rows.get("bond", []), rows.get("bond_repurchase", []), start=v04.get("issuance_start", "2005-01-01"), days=days)
    cb = blocks.get("central_bank")
    reserves_w: Series = []
    if cb:
        reserves_w = clean([(d, v) for d, v in zip(cb["history"]["dates"], cb["history"]["rows"].get("reserves", [])) if v is not None])
        V4.enrich_central_bank(cb, cfg, ind, ops)
    if blocks.get("fiscal"):
        V4.enrich_fiscal(blocks["fiscal"], cfg, iss, rg, reserves_w)
        # ── round 2: BoC holdings by ISIN → net redemptions / coupons ──
        try:
            netcal, nethist, hnote = _cad_holdings(cfg, a, gp, hist_dir, days, errors, oplog)
            V4.enrich_fiscal_net(blocks["fiscal"], cfg, iss, netcal, nethist, reserves_w)
            for k in ("net_issuance_private_v2_daily", "bond_redemptions_net_daily", "bond_coupons_net_daily"):
                if nethist.get(k):
                    append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, [(d, v) for d, v in nethist[k] if v is not None])
            E.log_event(oplog, "CAD_HOLDINGS", "system", hnote)
        except Exception as e:  # noqa
            errors.append("boc_holdings: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "boc_holdings", "error": str(e)})
    if blocks.get("rates"):
        V4.enrich_rates(blocks["rates"], cfg, rates_raw)
    for k in ("term_repo_net_daily", "term_repo_outstanding", "overnight_ops_net_daily"):
        append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, ops.get(k, []))
    for k in ("rg_am_net_daily", "rg_am_outstanding"):
        append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, rg.get(k, []))
    for k in ("net_issuance_private_daily", "issued_private", "matured_private"):
        append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, iss.get(k, []))
    E.log_event(oplog, "CAD_V04", "system", {"groups": {k: len(v) for k, v in rows.items()}, "indicator_days": len(ind.get("settlement_actual", [])),
                                             "net_issuance_last": iss.get("net_issuance_private_daily", [])[-1] if iss.get("net_issuance_private_daily") else None})


def _cad_holdings(cfg: dict, a, gp, hist_dir: str, days: List[str], errors: List[str], oplog: str):
    """BoC holdings page (by ISIN, daily as-of) + monthly historical blobs (2018-12→) + Valet GOC_OUTSTANDING (nominal by ISIN)
    → net calendars (today) and dense daily net history (replay). Fixture mode reads fixtures/cad/boc_holdings_*.html and GOC_OUTSTANDING_latest.csv."""
    from . import ops_cad_holdings as H
    from .providers import _get as _pget
    import time as _time
    from datetime import date, timedelta
    src = cfg["sources"].get("boc_holdings", {})
    page_url = src.get("url", "https://www.bankofcanada.ca/markets/government-securities-auctions/bank-of-canada-holdings/")
    h_arch = os.path.join(hist_dir, "boc_holdings.csv")
    o_arch = os.path.join(hist_dir, "goc_outstanding.csv")
    note: Dict[str, object] = {}
    if a.fixtures:
        rows = H.parse_boc_holdings_html(open(os.path.join(a.fixtures, "boc_holdings_2026-09-10.html"), encoding="utf-8").read())
        bp = os.path.join(a.fixtures, "boc_holdings_blob_boc_holdings_2026_08.html")
        if os.path.exists(bp):
            rows += H.parse_boc_holdings_html(open(bp, encoding="utf-8").read())
        outstanding = H.goc_outstanding_from_csv(os.path.join(a.fixtures, "GOC_OUTSTANDING_latest.csv"))
        hist_rows, out_hist = rows, outstanding
    else:
        rows = H.parse_boc_holdings_html(_pget(page_url, as_json=False, timeout=60))
        hist_rows = H.merge_holdings_archive(h_arch, rows)
        have = {r["asof"][:7] for r in hist_rows}
        want = [n for n in H.blob_names() if n[13:20].replace("_", "-") not in have]
        if a.backfill or len(have) < 3:
            got = 0
            for n in want[-120:]:
                try:
                    hist_rows = H.merge_holdings_archive(h_arch, H.parse_boc_holdings_html(_pget(H.blob_url(n), as_json=False, timeout=60)))
                    got += 1
                except Exception as e:  # noqa
                    errors.append("boc_holdings_blob[%s]: %s" % (n, str(e)[:80]))
                    if got == 0 and len(errors) > 3:
                        break
                _time.sleep(0.6)
            note["blobs_fetched"] = got
        else:
            note["blobs_pending"] = len(want)
        since = (date.today() - timedelta(days=21)).isoformat()
        obs = gp.fetch("GOC_OUTSTANDING", start_date=since)
        outstanding = H.parse_goc_outstanding(obs)
        out_hist = _merge_outstanding_archive(o_arch, outstanding)
    netcal = H.net_calendar(outstanding, rows)
    nethist = H.net_daily_history(hist_rows, out_hist, days)
    ha = netcal.get("holdings_asof", [])
    note.update({"holdings_asof": ha[-1][0] if ha else None, "holdings_rows": len(rows), "history_asofs": len({r["asof"] for r in hist_rows}),
                 "outstanding_asof": outstanding[0]["asof"] if outstanding else None, "outstanding_isins": len(outstanding), "unmatched": netcal.get("_unmatched", [])})
    return netcal, nethist, note


def _merge_outstanding_archive(path: str, snap: List[dict]) -> List[dict]:
    """month-end style archive of GOC_OUTSTANDING snapshots: keeps the latest as-of per calendar month plus the latest snapshot"""
    cols = ["asof", "isin", "security_type", "instrument_type", "coupon", "issue_date", "maturity", "outstanding", "inflation_adjusted"]
    old: List[dict] = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r["outstanding"] = float(r["outstanding"]) if r.get("outstanding") else None
                r["inflation_adjusted"] = float(r["inflation_adjusted"]) if r.get("inflation_adjusted") else None
                r["coupon"] = float(r["coupon"]) if r.get("coupon") else None
                old.append(r)
    by_month: Dict[str, str] = {}
    for r in old + snap:
        m = r["asof"][:7]
        if r["asof"] >= by_month.get(m, ""):
            by_month[m] = r["asof"]
    keep_asofs = set(by_month.values())
    rows = [r for r in old + snap if r["asof"] in keep_asofs]
    seen = set()
    out: List[dict] = []
    for r in sorted(rows, key=lambda r: (r["asof"], r["isin"])):
        k = (r["asof"], r["isin"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in out:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
    return out


def _merge_group_rows(path: str, fresh: List[dict]) -> List[dict]:
    """append-only archive of group observations keyed by the group's id column (first column ending in '_id' or 'id')"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old: List[dict] = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = [dict(r) for r in csv.DictReader(f)]
    allrows = old + fresh
    if not allrows:
        return []
    keycol = next((c for c in allrows[0].keys() if c.endswith("_id") or c == "id"), None)
    merged: Dict[str, dict] = {}
    for r in allrows:
        k = r.get(keycol) if keycol else json.dumps(r, sort_keys=True)
        merged[k] = r
    cols: List[str] = []
    for r in merged.values():
        for c in r:
            if c not in cols:
                cols.append(c)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in merged.values():
            w.writerow(r)
    return list(merged.values())


def fetch_gbp(cfg: dict, a, prev: dict, hist_dir: str, oplog: str, errors: List[str]) -> Dict[str, dict]:
    """GBP lanes: weekly (Weekly Report + rates), daily (rates), monthly (ONS fiscal + Money & Credit).
    IADB rule: one batched request per lane, verified batch first, >= 2.5 s apart, never parallel."""
    blocks: Dict[str, dict] = {k: v for k, v in prev.items() if v}
    src = cfg["sources"]
    raw_dir = os.path.join(ROOT, "logs", "gbp", "raw") if not a.fixtures else None
    iadb = IadbProvider(src["boe_iadb"]["base_url"], fixtures_dir=a.fixtures, raw_dir=raw_dir)
    ons = OnsProvider(src["ons_api"]["base_url"], fixtures_dir=a.fixtures)
    lanes = ["weekly", "daily", "monthly"] if a.lane == "all" else [a.lane]
    today = E.now_iso()[:10]
    from datetime import date, timedelta
    def _from(days: int) -> str:
        return (date.today() - timedelta(days=days)).isoformat()

    def _iadb(ids: List[str], backfill_days: int, incremental_days: int, tag: str) -> Dict[str, Series]:
        try:
            got = iadb.fetch(ids, _from(backfill_days if a.backfill else incremental_days), today)
        except ProviderError as e:
            errors.append("boe_iadb[%s]: %s" % (tag, e))
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "boe_iadb", "batch": tag, "error": str(e)})
            got = {i: [] for i in ids}
        if not a.fixtures:
            got = _merge_hist(hist_dir, got, ids)  # always merge: a failed batch keeps the last good history (stale, never synthetic)
        return got

    if "weekly" in lanes or "daily" in lanes:
        ids = series_ids(cfg, "rates") + [cfg["desk_exports"]["gbpusd"]["id"], cfg["desk_exports"]["eurgbp_inv"]["id"]]
        r_raw = _iadb(ids, 3 * 365 + 30, 30, "daily")
        blocks["rates"] = BG.build_rates(cfg, r_raw, prev.get("rates"))
        for i in ids:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, r_raw.get(i, []))
    if "weekly" in lanes:
        ids = series_ids(cfg, "central_bank")
        cb_raw = _iadb(ids, 6 * 365 + 30, 60, "weekly")
        blocks["central_bank"] = BG.build_central_bank(cfg, cb_raw, prev.get("central_bank"))
        for i in ids:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, cb_raw.get(i, []))
    if "monthly" in lanes or (a.backfill and "weekly" in lanes):
        ids = series_ids(cfg, "fiscal")
        try:
            f_raw = ons.fetch(ids)
        except ProviderError as e:
            errors.append("ons: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "ons_api", "error": str(e)})
            f_raw = {i: [] for i in ids}
        if not a.fixtures:
            f_raw = _merge_hist(hist_dir, f_raw, ids)
        blocks["fiscal"] = BG.build_fiscal(cfg, f_raw, prev.get("fiscal"))
        for i in ids:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, f_raw.get(i, []))
        ids = series_ids(cfg, "banking")
        bk_raw = _iadb(ids, 10 * 365, 120, "monthly")
        blocks["banking"] = BG.build_banking(cfg, bk_raw, blocks.get("rates"), prev.get("banking"))
        for i in ids:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, bk_raw.get(i, []))
    # ── v0.4 · operation-level sources (daily + weekly lanes): BoE XLSX by operation, DMO D1A/D2.2D, APF, Exchequer residual ──
    if "daily" in lanes or "weekly" in lanes:
        _gbp_v04(cfg, a, blocks, hist_dir, oplog, errors)
    return blocks


def _gbp_v04(cfg: dict, a, blocks: Dict[str, dict], hist_dir: str, oplog: str, errors: List[str]) -> None:
    """GBP v0.4 (CAMBIOS G1–G5). Blocks enriched in place; live scores untouched."""
    from .providers import BoeOpsProvider, DmoProvider
    from . import ops_gbp as O
    from . import blocks_gbp_v04 as V4
    raw_dir = os.path.join(ROOT, "logs", "gbp", "raw") if not a.fixtures else None
    boe, dmo = BoeOpsProvider(fixtures_dir=a.fixtures, raw_dir=raw_dir), DmoProvider(fixtures_dir=a.fixtures, raw_dir=raw_dir)
    rows: Dict[str, List[dict]] = {}
    import time as _t
    for kind in ("str", "iltr", "ctrf", "apf_sales", "apf_profile"):
        try:
            rows[kind] = boe.fetch(kind)
        except (ProviderError, Exception) as e:  # never block the lane
            rows[kind] = []
            errors.append("boe_ops[%s]: %s" % (kind, e))
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "boe_ops", "kind": kind, "error": str(e)})
        if not a.fixtures:
            _t.sleep(2.5)
    for kind in ("d1a", "d22d", "d21e", "d1c"):  # d21e/d1c: seed of the gilt series before the D1A archive
        try:
            rows[kind] = dmo.fetch(kind)
        except (ProviderError, Exception) as e:
            rows[kind] = []
            errors.append("dmo[%s]: %s" % (kind, e))
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "dmo_xml", "kind": kind, "error": str(e)})
        if not a.fixtures:
            _t.sleep(2.5)
    from datetime import date, timedelta
    today = date.today().isoformat()
    days = O.business_days((date.today() - timedelta(days=_v04_window_days(a))).isoformat(), today)
    ops = O.repo_series(rows.get("str", []), rows.get("iltr", []), rows.get("ctrf", []), days)
    apf = O.apf_series(rows.get("apf_sales", []), rows.get("apf_profile", []))
    apf_name = O.apf_holdings_by_name(rows.get("apf_profile", []))
    # D1A archive (append-only; gilt issuance = Δ amount in issue between snapshots)
    d1a_path = os.path.join(hist_dir, "dmo_gilts_in_issue.csv")
    arch = O.append_d1a_archive(d1a_path, rows.get("d1a", [])) if (rows.get("d1a") and not a.fixtures) else O.read_d1a_archive(d1a_path)
    if a.fixtures and rows.get("d1a"):
        arch = {r["date"]: {} for r in rows["d1a"][:1]}
        for r in rows["d1a"]:
            v = O._num(r.get("amount_in_issue_m"))
            if v is not None:
                arch[r["date"]][r["isin"]] = v
    red_by_isin = {r["isin"]: r["redemption_date"] for r in rows.get("d1a", []) if r.get("isin")}
    apf_by_isin = {r["isin"]: apf_name.get(O._norm_name(r.get("name", "")), 0.0) for r in rows.get("d1a", [])}
    gi = O.issuance_from_archive(arch, red_by_isin, apf_by_isin, {r["isin"]: r.get("first_issue_date", "") for r in rows.get("d1a", []) if r.get("isin")})
    cal = O.gilt_calendar(rows.get("d1a", []), apf_name)
    tb = O.tbill_series(rows.get("d22d", []))
    tb["tbill_issued"], tb["tbill_matured"] = O._dense(tb["tbill_issued"], days), O._dense(tb["tbill_matured"], days)  # true sessions for 5-day sums
    # coupons paid in the last 60 days: estimated from the current snapshot (amounts barely change between coupon date and today)
    cp_paid = O.coupons_paid_recent(rows.get("d1a", []), apf_name, 60)
    iss = dict(gi)
    iss.update(tb)
    iss["coupons_private_paid"] = cp_paid
    iss["net_issuance_private_daily"] = O.net_issuance_private(gi["gilt_issued_daily"], gi["gilt_redeemed_private"], tb["tbill_issued"], tb["tbill_matured"], cp_paid, days)
    # Seed before the first D1A archive snapshot (ADJUDICACION_GBP_EMISION.md, "Diseño del seed GBP"): D2.1E issuance by settlement,
    # D1C gross redemptions, rule coupons on the back-solved private outstanding, D2.2D bills (full history). Strictly before the
    # first snapshot; from that date the archive path above rules untouched. Deterministic → re-runs are idempotent on the CSVs.
    first_snap = min(arch) if arch else today
    seed_days = O.business_days(O.SEED_START, (date.fromisoformat(first_snap) - timedelta(days=1)).isoformat())
    name_of = {r["isin"]: r.get("name", "") for r in rows.get("d1a", []) if r.get("isin")}
    snap_by_name = {name_of[i]: (v, red_by_isin.get(i, "")) for i, v in (arch.get(first_snap) or {}).items() if i in name_of}
    seed, seed_stats = O.seed_flows(rows.get("d21e", []), rows.get("d1c", []), (first_snap, snap_by_name), seed_days)
    if seed_days and rows.get("d21e") and rows.get("d1c"):
        tb_raw = O.tbill_series(rows.get("d22d", []))  # undensed full history (tb above is densed to the flow window)
        seed_net = O.net_issuance_private(seed["gilt_issued_daily"], seed["gilt_redeemed_private"], tb_raw["tbill_issued"], tb_raw["tbill_matured"], seed["coupons_private_paid"], seed_days)
        for k, s in (("gilt_issued_daily", seed["gilt_issued_daily"]), ("gilt_redeemed_private", seed["gilt_redeemed_private"]), ("coupons_private_paid", seed["coupons_private_paid"]),
                     ("tbill_issued", O._dense(tb_raw["tbill_issued"], seed_days)), ("tbill_matured", O._dense(tb_raw["tbill_matured"], seed_days)), ("net_issuance_private_daily", seed_net)):
            iss[k] = O.splice(s, iss.get(k, []), first_snap)
    E.log_event(oplog, "GBP_SEED", "system", dict(seed_stats, first_snapshot=first_snap, seed_days=len(seed_days),
                                                  seed_last=seed_days[-1] if seed_days else None, tbill_first=(rows.get("d22d") or [{}])[0].get("tender_date")))
    # Exchequer residual from the weekly history CSVs
    def _h(code: str) -> Series:
        p = os.path.join(hist_dir, "%s.csv" % code)
        return clean([(r[0], float(r[1])) for r in csv.reader(open(p)) if r and r[0] != "date"]) if os.path.exists(p) else []
    resid = O.exchequer_residual_weekly({"reserves": _h("RPWB56A"), "str": _h("RPWB67A"), "ltr": _h("RPWB69A"), "apf": _h("RPWZ4TM"),
                                         "tfsme": _h("RPWZOQ4"), "wm": _h("RPWB72A"), "notes": _h("RPWB55A")})
    cb = blocks.get("central_bank")
    reserves_w: Series = _h("RPWB56A")
    if cb:
        V4.enrich_central_bank(cb, cfg, ops, apf, resid)
    if blocks.get("fiscal"):
        V4.enrich_fiscal(blocks["fiscal"], cfg, iss, cal, resid, reserves_w)
    for k in ("str_net_daily", "str_outstanding_ops", "iltr_net_daily", "iltr_outstanding_ops", "repo_net_daily"):
        append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, ops.get(k, []))
    append_history_csv(os.path.join(hist_dir, "apf_sales_daily.csv"), "apf_sales_daily", apf.get("apf_sales_daily", []))
    for k in ("gilt_issued_daily", "gilt_redeemed_private", "coupons_private_paid", "tbill_issued", "tbill_matured", "net_issuance_private_daily"):
        append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, iss.get(k, []))
    append_history_csv(os.path.join(hist_dir, "exchequer_residual_weekly.csv"), "exchequer_residual_weekly", resid.get("exchequer_residual_weekly", []))
    E.log_event(oplog, "GBP_V04", "system", {"rows": {k: len(v) for k, v in rows.items()}, "d1a_snapshots": len(arch),
                                             "residual_last": resid["exchequer_residual_weekly"][-1] if resid.get("exchequer_residual_weekly") else None})


def fetch_aud(cfg: dict, a, prev: dict, hist_dir: str, oplog: str, errors: List[str]) -> Dict[str, dict]:
    """AUD lanes: daily (A3 ES + F1), weekly (A1 + F2 + A2), monthly (D1 + D3). One GET per table, >= 2 s apart."""
    blocks: Dict[str, dict] = {k: v for k, v in prev.items() if v}
    src = cfg["sources"]["rba_tables"]
    raw_dir = os.path.join(ROOT, "logs", "aud", "raw") if not a.fixtures else None
    rba = RbaProvider(src["base_url"], fixtures_dir=a.fixtures, raw_dir=raw_dir)
    lanes = ["weekly", "daily", "monthly"] if a.lane == "all" else [a.lane]
    from datetime import date, timedelta
    def _since(days: int) -> Optional[str]:
        return (date.today() - timedelta(days=days)).isoformat()
    T = src["tables"]
    FIX = {"a3_es": "rba_a3_es.csv"}

    def _ids(block: str, table_key: str) -> List[str]:
        return [s["id"] for s in cfg["blocks"][block]["series"].values() if s.get("id") and s.get("table") == table_key]

    def _tab(table_key: str, ids: List[str], back_days: int, inc_days: int) -> Dict[str, Series]:
        if not ids:
            return {}
        try:
            got = rba.fetch(T[table_key]["file"].replace(".csv", ""), ids, since=_since(back_days if a.backfill else inc_days), fixture_name=FIX.get(table_key))
        except ProviderError as e:
            errors.append("rba[%s]: %s" % (table_key, e))
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "rba_tables", "table": table_key, "error": str(e)})
            got = {i: [] for i in ids}
        if not a.fixtures:
            got = _merge_hist(hist_dir, got, ids)
        return got

    data: Dict[str, Series] = {}
    if "daily" in lanes or "weekly" in lanes:
        data.update(_tab("a3_es", _ids("central_bank", "a3_es"), 3 * 365, 45))
        data.update(_tab("f1", _ids("rates", "f1"), 3 * 365 + 30, 45))
        data.update(_tab("a2", _ids("rates", "a2") + _ids("central_bank", "a2"), 6 * 365, 6 * 365))
    if "weekly" in lanes:
        data.update(_tab("a1", _ids("central_bank", "a1") + _ids("fiscal", "a1"), 6 * 365, 90))
        data.update(_tab("f2", _ids("rates", "f2"), 3 * 365 + 30, 45))
        data.update(_tab("f11", [cfg["desk_exports"]["audusd"]["id"]], 3 * 365, 90))
    if "monthly" in lanes or (a.backfill and "weekly" in lanes):
        data.update(_tab("d1", _ids("banking", "d1"), 8 * 365, 400))
        data.update(_tab("d3", _ids("banking", "d3"), 8 * 365, 400))
    for i, ser in data.items():
        append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, ser)
    # builders (daily lane rebuilds rates + central bank; weekly adds fiscal; monthly adds banking)
    if "daily" in lanes or "weekly" in lanes:
        blocks["rates"] = BA.build_rates(cfg, data, prev.get("rates"))
        if "weekly" not in lanes and not a.fixtures:  # daily lane: weekly A1 series from history so the block stays complete
            data = _merge_hist(hist_dir, data, _ids("central_bank", "a1") + _ids("fiscal", "a1") + _ids("rates", "f2"))
        blocks["central_bank"] = BA.build_central_bank(cfg, data, prev.get("central_bank"))
    if "weekly" in lanes:
        blocks["fiscal"] = BA.build_fiscal(cfg, data, prev.get("fiscal"))
    if "monthly" in lanes or (a.backfill and "weekly" in lanes):
        blocks["banking"] = BA.build_banking(cfg, data, blocks.get("rates"), prev.get("banking"))
    if str(cfg.get("config_version", "")).startswith("0.4"):
        try:
            _aud_v04(cfg, a, blocks, data, hist_dir, oplog, errors, a.fixtures, raw_dir)
        except Exception as e:  # noqa
            errors.append("aud_v04: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "aud_v04", "error": str(e)})
    return blocks


def _aud_v04(cfg: dict, a, blocks: Dict[str, dict], data: dict, hist_dir: str, oplog: str, errors: List[str], fx, raw_dir) -> None:
    """AUD v0.4 (CAMBIOS A1–A6): OMO by operation + unwinds schedule, AOFM issuance by settlement (link discovery on the Data Hub), TB gross calendar."""
    from . import ops_aud as O
    from . import blocks_aud_v04 as V4
    from . import series as S
    from .providers_chf import xlsx_sheets
    from .providers_jpy import _snapshot
    from datetime import date, timedelta
    import time as _time
    today = date.today().isoformat()
    days = O.business_days((date.today() - timedelta(days=_v04_window_days(a))).isoformat(), today)

    def _get(url: str, binary: bool = False, timeout: int = 120):
        """RBA: plain requests. AOFM (Akamai): the Chrome-impersonating ladder from providers_nzd (curl_cffi → curl → requests), 2 tries, then the
        verified fixture file as fallback — the AOFM files are full histories, so a stale copy is labelled, never invented."""
        if "aofm.gov.au" in url:
            from .providers_nzd import _http as _ladder
            try:
                return _ladder(url, timeout=min(timeout, 60), retries=2, binary=binary)
            except Exception as e:  # noqa
                raise ProviderError("aofm: %s" % e)
        import requests  # type: ignore
        from .providers import UA
        r = requests.get(url, headers=dict(UA, Accept="*/*"), timeout=timeout)
        if r.status_code != 200:
            raise ProviderError("HTTP %s for %s" % (r.status_code, url))
        return r.content if binary else r.content.decode("utf-8-sig", errors="replace")

    # 1 · RBA OMO per operation + unwinds
    ops, unw = [], []
    try:
        if fx:
            det = open(os.path.join(fx, "rba_%s.csv" % O.RBA_OMO_DETAILS.replace("-", "_")), encoding="utf-8").read()
            unt = open(os.path.join(fx, "rba_%s.csv" % O.RBA_OMO_UNWINDS.replace("-", "_")), encoding="utf-8").read()
        else:
            base = cfg["sources"]["rba_tables"]["base_url"].rstrip("/") + "/"
            det = _get(base + O.RBA_OMO_DETAILS + ".csv")
            _snapshot(raw_dir, "rba_%s.csv" % O.RBA_OMO_DETAILS, det)
            _time.sleep(2.0)
            unt = _get(base + O.RBA_OMO_UNWINDS + ".csv")
            _snapshot(raw_dir, "rba_%s.csv" % O.RBA_OMO_UNWINDS, unt)
        ops, unw = O.parse_omo_details(det), O.parse_omo_unwinds(unt)
    except Exception as e:  # noqa
        errors.append("rba_omo_v04: %s" % e)
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "rba_omo_v04", "error": str(e)})
    omo = O.omo_flows(ops, unw, days) if ops else {}
    omo_cut = omo["omo_cut"][0][0] if omo else today
    recon = O.reconcile_stock(omo.get("omo_stock_full", []), S.clean(data.get("AORROMO", []))) if omo else []
    # 2 · AOFM issuance by settlement (Data Hub link discovery; fixtures = aud_hist XLSX + buyback / face-value CSVs)
    recs: Dict[str, list] = {}
    bb: Dict[str, list] = {}
    lines: list = []
    links_note = "fixtures"
    hist_fx = os.path.join(ROOT, "fixtures", "aud_hist")
    try:
        if fx:
            for k, fn in (("tb", "aofm_treasury_bonds_issuance.xlsx"), ("tn", "aofm_treasury_notes_issuance.xlsx"), ("tib", "aofm_treasury_indexed_bonds_issuance.xlsx")):
                pth = os.path.join(hist_fx, fn)
                if os.path.exists(pth):
                    recs[k] = O.parse_transactions(xlsx_sheets(open(pth, "rb").read())["Transactions"])
            bb = {"tb": O.records_from_csv(os.path.join(hist_fx, "aofm_tb_buybacks.csv"), "buyback"), "tib": O.records_from_csv(os.path.join(hist_fx, "aofm_tib_buybacks.csv"), "buyback")}
            lines = O.face_value_from_csv(os.path.join(hist_fx, "aofm_tb_face_value_by_line.csv"))
        else:
            try:
                links = O.discover_links(_get(O.DATA_HUB, timeout=45))
                links_note = "resolved on the Data Hub: " + ", ".join("%s=%s" % (k, v.rsplit("/", 2)[-2]) for k, v in links.items())
            except Exception as e:  # noqa
                links = {k: v[1] for k, v in O.AOFM_FILES.items()}
                links_note = "Data Hub unreachable (%s): fallback URLs verified 2026-09-10" % e
            fallback_used = []
            aofm_down = [False]  # after one failed download the site is treated as down for this run (no 12-minute wall of timeouts)

            def _aofm(url, timeout=60):
                if aofm_down[0]:
                    raise ProviderError("aofm skipped: site unreachable earlier in this run")
                try:
                    return _get(url, binary=True, timeout=timeout)
                except Exception:
                    aofm_down[0] = True
                    raise
            for k, key, fn in (("tb", "tb_issuance", "aofm_treasury_bonds_issuance.xlsx"), ("tn", "tn_issuance", "aofm_treasury_notes_issuance.xlsx"), ("tib", "tib_issuance", "aofm_treasury_indexed_bonds_issuance.xlsx")):
                cache = os.path.join(hist_dir, "aofm_%s.xlsx" % key)
                try:
                    blob = _aofm(links[key])
                    _snapshot(raw_dir, "aofm_%s.xlsx" % key, blob)
                    os.makedirs(hist_dir, exist_ok=True)
                    open(cache, "wb").write(blob)  # last good copy for the next timeout
                except Exception as e:  # noqa
                    errors.append("aofm_%s: %s (using the last good copy)" % (key, e))
                    src_path = cache if os.path.exists(cache) else os.path.join(hist_fx, fn)
                    blob = open(src_path, "rb").read()
                    fallback_used.append("%s←%s" % (key, "history" if src_path == cache else "fixture 2026-09-10"))
                recs[k] = O.parse_transactions(xlsx_sheets(blob)["Transactions"])
                _time.sleep(1.5)
            if fallback_used:
                links_note += " · FALLBACK (AOFM unreachable): " + ", ".join(fallback_used)
            for k, key in (("tb", "tb_buybacks"), ("tib", "tib_buybacks")):
                try:
                    blob = _aofm(links[key])
                    _snapshot(raw_dir, "aofm_%s.xlsx" % key, blob)
                    bb[k] = O.parse_transactions(xlsx_sheets(blob)["Transactions"])
                    for r in bb[k]:
                        r["method"] = r.get("tender number / buyback method", "")
                except Exception as e:  # noqa
                    errors.append("aofm_%s: %s (using the fixture)" % (key, e))
                    bb[k] = O.records_from_csv(os.path.join(hist_fx, "aofm_%s_buybacks.csv" % k), "buyback")
                _time.sleep(1.5)
            try:
                blob = _aofm(links["tb_portfolio"])
                _snapshot(raw_dir, "aofm_tb_portfolio.xlsx", blob)
                lines = O.parse_face_value_sheet(xlsx_sheets(blob)["FaceValue"])
                O_lines_path = os.path.join(hist_dir, "aofm_tb_face_value_by_line.csv")
                with open(O_lines_path, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=["date", "maturity", "coupon", "face"])
                    w.writeheader()
                    for l in lines:
                        w.writerow(l)
            except Exception as e:  # noqa
                errors.append("aofm_tb_portfolio: %s (using the last good copy)" % e)
                cache = os.path.join(hist_dir, "aofm_tb_face_value_by_line.csv")
                lines = O.face_value_from_csv(cache if os.path.exists(cache) else os.path.join(hist_fx, "aofm_tb_face_value_by_line.csv"))
    except Exception as e:  # noqa
        errors.append("aofm_v04: %s" % e)
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "aofm_v04", "error": str(e)})
    iss = O.issuance_flows(recs, bb, days) if recs else {}
    cal = O.tb_calendar(lines)
    es = S.clean(data.get("AESAT", []))
    es_level = es[-1][1] if es else None
    if blocks.get("central_bank") and omo:
        V4.enrich_central_bank(blocks["central_bank"], cfg, omo, recon, omo_cut)
    if blocks.get("fiscal") and iss:
        V4.enrich_fiscal(blocks["fiscal"], cfg, iss, cal, es_level, links_note)
        # ── round 2: RBA A3.1 holdings by line → Treasury Bond redemptions / coupons NET ──
        try:
            from . import ops_aud_holdings as H
            if fx:
                a31 = open(os.path.join(hist_fx, "rba_a3.1_ags_bonds.csv"), encoding="utf-8").read()
            else:
                a31 = _get(cfg["sources"]["rba_tables"]["base_url"].rstrip("/") + "/a3.1-ags---bonds.csv")
                _snapshot(raw_dir, "rba_a3.1_ags_bonds.csv", a31)
                with open(os.path.join(hist_dir, "rba_a3.1_ags_bonds.csv"), "w", encoding="utf-8") as f:
                    f.write(a31)
            rba_rows = H.parse_a31_csv(a31)
            netcal = H.net_tb_calendar(lines, rba_rows)
            nethist = H.net_daily_history(lines, rba_rows, days)
            V4.enrich_fiscal_net(blocks["fiscal"], cfg, iss, netcal, nethist, es_level)
            for k in ("net_issuance_private_v2_daily", "tb_redemptions_net_daily", "tb_coupons_net_daily"):
                if nethist.get(k):
                    append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, [(d, v) for d, v in nethist[k] if v is not None])
            ha = netcal.get("tb_holdings_asof", [])
            E.log_event(oplog, "AUD_HOLDINGS", "system", {"a31_rows": len(rba_rows), "rba_asof": ha[-1][0] if ha else None, "unmatched": netcal.get("_unmatched", []),
                                                          "rba_share": (netcal.get("tb_rba_share") or [(None, None)])[-1][1]})
        except Exception as e:  # noqa
            errors.append("rba_a31: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "rba_a31", "error": str(e)})
    if blocks.get("rates") and iss:
        V4.enrich_rates(blocks["rates"], cfg, iss.get("tn_wa_yield", []))
    for k, ser in (("omo_net_daily", omo.get("omo_net_daily", []) if omo else []), ("omo_stock_daily", omo.get("omo_stock_daily", []) if omo else []),
                   ("net_issuance_private_daily", iss.get("net_issuance_private_daily", []) if iss else []), ("tn_stock_daily", iss.get("tn_stock_daily", []) if iss else [])):
        if ser:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, ser)
    E.log_event(oplog, "AUD_V04", "system", {"omo_ops": len(ops), "omo_cut": omo_cut, "unwind_days": len(unw), "tenders": {k: len(v) for k, v in recs.items()},
                                             "buybacks": {k: len(v) for k, v in bb.items()}, "tb_lines": len({l["maturity"] for l in lines if l.get("date") == max((x["date"] for x in lines), default="")}), "links": links_note[:200]})


def fetch_jpy(cfg: dict, a, prev: dict, hist_dir: str, oplog: str, errors: List[str]) -> Dict[str, dict]:
    """JPY lanes: daily (jd XLSX T-1 + TONA API + fcall snapshot + MoF yields + JSDA TRR), daily_provisional (jx/jp), ten_day (BoJ Accounts),
    weekly (auction results XLS + ITS snapshot), monthly (MD13/MD02/MD01/MD06/MD08 + MoF receipts). One request per source, >= 1 s apart."""
    blocks: Dict[str, dict] = {k: v for k, v in prev.items() if v}
    src = cfg["sources"]
    fx = a.fixtures
    raw_dir = os.path.join(ROOT, "logs", "jpy", "raw") if not fx else None
    lanes = ["daily", "daily_provisional", "ten_day", "weekly", "monthly"] if a.lane == "all" else [a.lane]
    from datetime import date, timedelta
    today = date.today()

    def _err(tag: str, e: Exception) -> None:
        errors.append("%s: %s" % (tag, e))
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": tag, "error": str(e)})

    def _ym(days_back: int) -> str:
        d = today - timedelta(days=days_back)
        return "%04d%02d" % (d.year, d.month)

    data: Dict[str, Series] = {}
    # ── corridor (event) ──
    try:
        data.update(PJ.BojPolicyRateProvider(src["boj_policy_rates_csv"]["url"], fixtures_dir=fx, raw_dir=raw_dir).fetch())
    except Exception as e:  # noqa
        _err("boj_policy_rates_csv", e)
    # ── daily XLSX (final) ──
    if "daily" in lanes or "daily_provisional" in lanes:
        back = 400 if a.backfill else 12
        dates = [(today - timedelta(days=i)).isoformat() for i in range(back, 0, -1) if (today - timedelta(days=i)).weekday() < 5]
        prov = PJ.BojDailyCabProvider(src["boj_daily_cab"]["url_final"].split("jd/")[0], fixtures_dir=fx, raw_dir=raw_dir)
        got, errs, hashes = prov.fetch(dates, "jd")
        for x in errs:
            _err("boj_daily_cab", Exception(x))
        if not fx:
            got = _merge_hist(hist_dir, got, sorted(set(list(got) + [k for k, _ in PJ.BojDailyCabProvider.ITEMS])))
        data.update(got)
        if hashes:
            E.log_event(oplog, "STRUCTURE_HASH", "system", {"jd_latest": max(hashes), "hash": hashes[max(hashes)]})
        # projection (jp) is cheap (2 requests) — fetch it on the daily lane too, not only on the 09:30 UTC provisional lane,
        # otherwise the projection card sits 'unavailable' after any manual/backfill run
        if not fx:
            try:
                gp, ep, _ = prov.fetch([today.isoformat(), (today + timedelta(days=1)).isoformat()], "jp")
                if gp.get("treasury"):
                    data["treasury_proj"] = clean(_merge_hist(hist_dir, {"treasury_proj": gp["treasury"]}, ["treasury_proj"])["treasury_proj"])
                for x in ep:
                    _err("boj_daily_cab[jp]", Exception(x))
            except Exception as e:  # noqa
                _err("boj_daily_cab[jp]", e)
        elif fx:
            data.update({"treasury_proj": []})
    if "daily" in lanes:
        api = PJ.BojApiProvider(src["boj_api"]["base"], fixtures_dir=fx, raw_dir=raw_dir)
        try:
            got = api.fetch("FM01", ["STRDCLUCON", "STRDCLUCONH", "STRDCLUCONL", "STRDCLUCV"], _ym(800 if a.backfill else 70), _ym(0))
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
        except Exception as e:  # noqa
            _err("boj_api[FM01]", e)
        try:
            got, errs = PJ.BojCallMarketProvider(fixtures_dir=fx, raw_dir=raw_dir).fetch_fcall()
            for x in errs:
                _err("boj_call_market", Exception(x))
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
        except Exception as e:  # noqa
            _err("boj_call_market", e)
        try:
            y = PJ.MofYieldsProvider(src["mof_jgb_yields"]["url_current_month"], src["mof_jgb_yields"]["url_history"], fixtures_dir=fx, raw_dir=raw_dir).fetch(history=a.backfill, since="2023-01-01")
            data.update(_merge_hist(hist_dir, y, list(y)) if not fx else y)
        except Exception as e:  # noqa
            _err("mof_jgb_yields", e)
        try:
            t = PJ.JsdaRepoProvider(src["jsda_tokyo_repo_rate"]["url_daily"], src["jsda_tokyo_repo_rate"]["url_history"], fixtures_dir=fx, raw_dir=raw_dir).fetch(history=a.backfill, since="2023-01-01")
            t = {"trr_%s" % k: v for k, v in t.items()}
            data.update(_merge_hist(hist_dir, t, list(t)) if not fx else t)
        except Exception as e:  # noqa
            _err("jsda_tokyo_repo_rate", e)
    # ── ten-day: BoJ Accounts ──
    if "ten_day" in lanes or "daily" in lanes:
        try:
            since = (today - timedelta(days=700 if a.backfill else 45)).isoformat()
            got, errs = PJ.BojAccountsProvider(src["boj_accounts"]["url"].split("{YYYY}")[0], fixtures_dir=fx, raw_dir=raw_dir).fetch(PJ.BojAccountsProvider.candidate_dates(since, today.isoformat()))
            for x in errs:
                _err("boj_accounts", Exception(x))
            got = {"ac_%s" % k: v for k, v in got.items()}
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
        except Exception as e:  # noqa
            _err("boj_accounts", e)
    # ── weekly: auctions + ITS snapshot ──
    if "weekly" in lanes or "daily" in lanes:
        try:
            au = PJ.MofAuctionProvider(src["mof_auction_results"]["url_jgb"], fixtures_dir=fx, raw_dir=raw_dir).fetch(since="2022-01-01")
            data.update(_merge_hist(hist_dir, au, list(au)) if not fx else au)
        except Exception as e:  # noqa
            _err("mof_auction_results", e)
        # HTML calendar + per-auction result pages: covers the ~2-month lag of the XLS and adds the TAIL (yield at lowest accepted − average)
        try:
            xls_last = max([s[-1][0] for k, s in data.items() if k.startswith("btc_") and s] or ["2026-01-01"])
            since = xls_last if a.backfill else max(xls_last, (today - timedelta(days=45)).isoformat())
            months, d = [], date(int(since[:4]), int(since[5:7]), 1)
            while d <= today.replace(day=1):
                months.append("%02d%02d" % (d.year % 100, d.month))
                d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
            nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
            months.append("%02d%02d" % (nxt.year % 100, nxt.month))  # next month's calendar (404 until published)
            html_p = PJ.MofAuctionHtmlProvider(src["mof_auction_calendar"]["url"].split("{YY}")[0], fixtures_dir=fx, raw_dir=raw_dir)
            got, cal, errs = html_p.fetch(months, since=since, today=today.isoformat())
            for x in errs:
                _err("mof_auction_html", Exception(x))
            if not fx:
                got = _merge_hist(hist_dir, got, list(got))
            data.update(got)
            if cal:
                data["_auction_calendar"] = cal  # type: ignore  (list of dicts; not a Series — excluded from history CSVs)
        except Exception as e:  # noqa
            _err("mof_auction_html", e)
        try:
            PJ.MofItsProvider(src["mof_its_weekly"]["url"], fixtures_dir=fx, raw_dir=raw_dir).snapshot()
        except Exception as e:  # noqa
            _err("mof_its_weekly", e)
    # ── monthly: API + MoF receipts ──
    if "monthly" in lanes or (a.backfill and "daily" in lanes):
        api = PJ.BojApiProvider(src["boj_api"]["base"], fixtures_dir=fx, raw_dir=raw_dir)
        for db, codes in (("MD13", ["FAAP@01", "FAAPOBAL1", "FAAPOBAL1@", "FAAPOBRDCD5"]), ("MD02", ["MAM1NAM2M2MO", "MAM1NAM3M3MO", "MAM1NAM3M1MO", "MAM1NAM3DMMO"]),
                          ("MD01", ["MABS1AN11", "MABS1AN113", "MABS1AN114"]), ("MD06", ["MASDM@01", "MASDM253", "MASDM254", "MASDM255", "MASDM273", "MASDM26", "MASDM58", "MASDM5F", "MASDM51", "MASDM@03", "MASDM@07", "MABCLE16"]),
                          ("MD08", ["MACAB1013", "MACAB1023", "MACAB1043", "MACAB1053", "MACAB1183", "MACAB1201"])):
            try:
                got = api.fetch(db, codes, _ym(3700 if a.backfill else 400), _ym(0))
                data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
            except Exception as e:  # noqa
                _err("boj_api[%s]" % db, e)
        try:
            months = []
            d = today
            for i in range(30 if a.backfill else 4):
                months.append("%04d-%02d" % (d.year, d.month))
                d = (d.replace(day=1) - timedelta(days=1))
            got, errs = PJ.MofReceiptsProvider(src["mof_treasury_receipts_payments"]["url"].split("e{YYYYMM}")[0], fixtures_dir=fx, raw_dir=raw_dir).fetch(sorted(months))
            for x in errs:
                _err("mof_treasury_receipts_payments", Exception(x))
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
        except Exception as e:  # noqa
            _err("mof_treasury_receipts_payments", e)
    # history CSVs
    for i, ser in data.items():
        if ser and not i.startswith("_"):
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, ser)
    # daily lane on a live run: pull monthly/ten-day/weekly series from history so all blocks stay complete
    if not fx:
        need = ["ac_" + k for k, _ in PJ.BojAccountsProvider.ITEMS] + ["FAAP@01", "FAAPOBAL1", "FAAPOBAL1@", "FAAPOBRDCD5", "MAM1NAM2M2MO", "MAM1NAM3M3MO", "MAM1NAM3M1MO", "MAM1NAM3DMMO", "MABS1AN11",
                                                                     "MASDM@01", "MASDM254", "MASDM255", "MASDM273", "MASDM26", "MASDM@03", "MACAB1043", "MACAB1183", "btc_20y", "btc_30y", "btc_40y", "btc_10y", "tail_10y", "tail_20y", "tail_30y", "tail_40y",
                                                                     "taxes_receipts", "pension_payments", "fefsa_receipts", "fefsa_receipts_py", "fefsa_payments", "gov_bonds_over_1y_receipts", "tbills_balance",
                                                                     "on_col_same_avg", "on_unc_same_avg", "on_unc_same_max", "on_unc_same_min", "1w_unc_fwd_avg", "1m_unc_fwd_avg", "3m_unc_same_avg", "call_outstanding_total", "treasury_proj"]
        for k in need:
            if k not in data:
                p = os.path.join(hist_dir, "%s.csv" % k)
                if os.path.exists(p):
                    data[k] = clean([(r[0], float(r[1])) for r in csv.reader(open(p)) if r and r[0] != "date"])
    blocks["rates"] = BJ.build_rates(cfg, data, prev.get("rates"))
    blocks["central_bank"] = BJ.build_central_bank(cfg, data, prev.get("central_bank"))
    blocks["fiscal"] = BJ.build_fiscal(cfg, data, prev.get("fiscal"))
    blocks["banking"] = BJ.build_banking(cfg, data, blocks.get("rates"), prev.get("banking"))
    if cfg.get("version", "0.3.0") >= "0.4.0":
        try:
            _jpy_v04(cfg, a, blocks, data, hist_dir, oplog, errors, fx, raw_dir)
        except Exception as e:  # noqa
            errors.append("jpy_v04: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "jpy_v04", "error": str(e)})
    return blocks


def _jpy_v04(cfg: dict, a, blocks: Dict[str, dict], data: dict, hist_dir: str, oplog: str, errors: List[str], fx, raw_dir) -> None:
    """JPY v0.4 (round 4): daily file with its three columns (予想/速報/確報) archived by business day, operations by operation (ope XLSX),
    monthly projection (juqp), BoJ holdings by issue (mei) + MoF auction XLS → net issuance by issue date. Shadow components only."""
    from . import ops_jpy as J
    from . import blocks_jpy_v04 as V4
    from . import series as S
    from .providers import _get as _pget
    from .providers_jpy import _snapshot
    import time as _time
    from datetime import date, timedelta
    import requests  # type: ignore
    src = cfg["sources"]
    today = date.today()
    days = J.business_days((today - timedelta(days=_v04_window_days(a))).isoformat(), today.isoformat())
    hx = os.path.join(ROOT, "fixtures", "jpy_hist")
    base = src["boj_daily_cab"]["url_final"].split("jd/")[0]  # …/juq/d_release/
    ope_base = base.replace("/juq/", "/ope/") + "ope/"
    note: Dict[str, object] = {}

    def _bin(url: str, timeout: int = 60) -> Optional[bytes]:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (mesa-macro)"}, timeout=timeout)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            if "mof.go.jp" in url and r.status_code >= 500:
                return PJ.mof_ladder(url, timeout=timeout, binary=True)  # runner blocked with 503 while browsers get 200 (2026-09-11)
            raise ProviderError("HTTP %s for %s" % (r.status_code, url))
        return r.content

    # ── daily files, three columns ──
    d_arch = os.path.join(hist_dir, "boj_daily_v04.csv")
    recs: List[dict] = []
    if fx:
        for fn in ("jd20260909.xlsx", "jx20260910.xlsx", "jp20260911.xlsx"):
            recs.append(J.parse_daily_file(open(os.path.join(hx, fn), "rb").read(), fn))
        daily_recs = recs
    else:
        old = J.read_daily_archive(d_arch)
        have_final = {r["date"] for r in old if r.get("version") == "final"}
        back = 400 if a.backfill else 15
        want = [d for d in J.business_days((today - timedelta(days=back)).isoformat(), (today - timedelta(days=1)).isoformat()) if d not in have_final]
        n = 0
        for d in want:
            try:
                blob = _bin("%sjd/%s/jd%s.xlsx" % (base, d[:4], d.replace("-", "")))
                if blob:
                    recs.append(J.parse_daily_file(blob, "jd%s.xlsx" % d.replace("-", "")))
                    n += 1
            except Exception as e:  # noqa
                errors.append("boj_jd_v04[%s]: %s" % (d, str(e)[:60]))
            _time.sleep(1.0)
        for kind, d in (("jx", today.isoformat()), ("jp", (today + timedelta(days=1)).isoformat()), ("jp", today.isoformat())):
            try:
                blob = _bin("%s%s/%s%s.xlsx" % (base, kind, kind, d.replace("-", "")))
                if blob:
                    recs.append(J.parse_daily_file(blob, "%s%s.xlsx" % (kind, d.replace("-", ""))))
                    _snapshot(raw_dir, "%s%s.xlsx" % (kind, d.replace("-", "")), blob)
            except Exception as e:  # noqa
                errors.append("boj_%s_v04[%s]: %s" % (kind, d, str(e)[:60]))
            _time.sleep(1.0)
        daily_recs = J.merge_daily_archive(d_arch, recs) if recs else old
        note["daily_new"] = n
    daily = J.daily_records_to_wide(daily_recs)
    # the v0.3 daily archive (final column only) fills the history behind the three-column archive
    seed: Dict[str, Series] = {}
    # the long jd capture (fixtures/jpy_hist/boj_daily_jd_hist_wide.csv, 2023-01 → 2025-10, final column only, verified 2026-09-10)
    # seeds the runner too: the current d_release/ tree starts in Oct-2025 and the JPY era starts 2024-07-31, so without it the
    # replay covered 43 % of the era. Only dates the three-column archive does not have; the seed is never written into the archive.
    pth = os.path.join(hx, "boj_daily_jd_hist_wide.csv")
    if os.path.exists(pth):
        with open(pth, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                for k in ("treasury", "cab", "jgb_purch", "ops_ex_lsp", "banknotes", "net_change", "reserve_bal", "excess"):
                    v = r.get(k)
                    if v not in (None, ""):
                        seed.setdefault(k, []).append((r["date"], float(v)))
    for k in ("treasury", "cab", "jgb_purch", "ops_ex_lsp", "banknotes", "net_change", "reserve_bal", "excess"):
        have = {d for d, _ in daily["final"].get(k, [])}
        extra = [(d, v) for d, v in S.clean(list(data.get(k, [])) + seed.get(k, [])) if d not in have]
        if extra:
            daily["final"][k] = S.clean(daily["final"].get(k, []) + extra)
    note["daily_files"] = len({r["date"] for r in daily_recs})
    # ── operations by operation ──
    o_arch = os.path.join(hist_dir, "boj_ops_v04.csv")
    ops: List[dict] = []
    if fx:
        for fn in ("ope20260909.xlsx", "ope20260910.xlsx"):
            ops += J.parse_ope_file(open(os.path.join(hx, fn), "rb").read(), fn)
    else:
        old_ops = _read_csv_rows(o_arch)
        have = {r["date"] for r in old_ops}
        back = 400 if a.backfill else 15
        want = [d for d in J.business_days((today - timedelta(days=back)).isoformat(), today.isoformat()) if d not in have]
        new_ops: List[dict] = []
        for d in want:
            try:
                blob = _bin("%s%s/ope%s.xlsx" % (ope_base, d[:4], d.replace("-", "")))
                if blob:
                    new_ops += J.parse_ope_file(blob, "ope%s.xlsx" % d.replace("-", ""))
            except Exception as e:  # noqa
                errors.append("boj_ope[%s]: %s" % (d, str(e)[:60]))
            _time.sleep(1.0)
        ops = _merge_csv_rows(o_arch, old_ops, new_ops, ["date", "kind", "instrument_jp", "instrument_en", "offered", "start", "end", "rate", "yield", "bids", "allotted"],
                              key=lambda r: (r["date"], r["instrument_jp"], str(r.get("start")), str(r.get("allotted"))))
        for r in ops:
            for k in ("offered", "rate", "yield", "bids", "allotted"):
                r[k] = float(r[k]) if r.get(k) not in (None, "") else None
        note["ops_new"] = len(new_ops)
    opsf = J.ops_flows(ops, {"jgb_purch": S.clean(J.best_realized(daily["final"].get("jgb_purch", []), daily["prov"].get("jgb_purch", [])))}, days)
    recon = opsf.get("jgb_purch_face_minus_cash", [])
    last_ops = max((r["date"] for r in ops), default=None)
    ops_note = {"last_date": last_ops, "lag_days": (today - date.fromisoformat(last_ops)).days if last_ops else None, "ope_files": len({r["date"] for r in ops}), "daily_files": note["daily_files"]}
    # ── monthly projection ──
    juqp = None
    try:
        if fx:
            juqp = J.parse_juqp(open(os.path.join(hx, "juqp2609.xlsx"), "rb").read())
        else:
            for m in (today, (today.replace(day=1) - timedelta(days=1))):
                blob = _bin("https://www.boj.or.jp/en/statistics/boj/fm/juqp/juqp%s.xlsx" % m.strftime("%y%m"))
                if blob:
                    juqp = J.parse_juqp(blob)
                    _snapshot(raw_dir, "juqp%s.xlsx" % m.strftime("%y%m"), blob)
                    break
                _time.sleep(1.0)
    except Exception as e:  # noqa
        errors.append("boj_juqp: %s" % str(e)[:80])
    # ── mei + MoF XLS → net issuance ──
    ni: Dict[str, Series] = {}
    mei_note: Dict[str, object] = {}
    try:
        if fx:
            mei = J.parse_mei(open(os.path.join(hx, "mei260831.xlsx"), "rb").read(), "mei260831.xlsx")
            jgb = J.parse_mof_jgb_xls(os.path.join(hx, "mof_auction_results_jgbs.xls"))
            tb = J.parse_mof_tbill_xls(os.path.join(hx, "mof_auction_results_tbills.xls"))
        else:
            idx = _pget(src["boj_jgb_holdings_xlsx"]["index"], as_json=False, timeout=60)
            import re as _re
            m = _re.search(r'href="([^"]*mei\d{6}\.xlsx)"', idx)
            if not m:
                raise ProviderError("mei link not found on the index page")
            u = m.group(1) if m.group(1).startswith("http") else "https://www.boj.or.jp" + m.group(1)
            blob = _bin(u)
            _snapshot(raw_dir, u.rsplit("/", 1)[-1], blob)
            with open(os.path.join(hist_dir, "mei_latest.xlsx"), "wb") as f:
                f.write(blob)
            mei = J.parse_mei(blob, u.rsplit("/", 1)[-1])
            _time.sleep(1.0)
            jb = _bin(src["mof_auction_results"]["url_jgb"], timeout=120)
            _time.sleep(1.0)
            tbb = _bin(src["mof_auction_results"]["url_tbills"], timeout=120)
            for nm, b in (("mof_auction_results_jgbs.xls", jb), ("mof_auction_results_tbills.xls", tbb)):
                if b:
                    with open(os.path.join(hist_dir, nm), "wb") as f:
                        f.write(b)
            jgb = J.parse_mof_jgb_xls(jb if jb else os.path.join(hx, "mof_auction_results_jgbs.xls"))
            tb = J.parse_mof_tbill_xls(tbb if tbb else os.path.join(hx, "mof_auction_results_tbills.xls"))
        imap = J.issue_map(jgb)
        by_mat = J.mei_to_maturity(mei, imap)
        unm = by_mat.pop("_unmapped", [])
        cl = J.coupon_lines(imap, mei)
        # the MoF 'past auction results' XLS lags the calendar by weeks: flows are cut at the last ISSUE date in the file (never
        # maturities without the issuance that refinances them); the calendars ahead stay complete
        mof_cut = max([r["issue"] for r in jgb + tb if r.get("issue")] or [today.isoformat()])
        mof_cut = min(mof_cut, today.isoformat())
        ni = J.net_issuance(jgb, tb, by_mat, cl, [d for d in days if d <= mof_cut], today=mof_cut)
        for k in ("jgb_redemptions_net_ahead", "jgb_redemptions_gross_ahead", "tbill_maturities_ahead", "jgb_coupons_net_ahead", "jgb_coupons_gross_ahead"):
            full = J.net_issuance(jgb, tb, by_mat, cl, [], today=today.isoformat()).get(k, [])
            ni[k] = [(d, v) for d, v in full if d > today.isoformat()]
        mei_note = {"asof": mei.get("asof"), "published": mei.get("published"), "total": round(sum(r["amount"] for r in mei.get("rows", [])), 1),
                    "unmapped": [list(x) for x in unm][:10], "jgb_records": len(jgb), "tbill_records": len(tb), "mof_cut": mof_cut,
                    "mof_lag_days": (today - date.fromisoformat(mof_cut)).days}
    except Exception as e:  # noqa
        errors.append("jpy_net_issuance: %s" % e)
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "jpy_net_issuance", "error": str(e)})
    cab = S.clean(J.best_realized(daily["final"].get("cab", []), daily["prov"].get("cab", [])))
    cab_level = cab[-1][1] if cab else (S.clean(data.get("cab", []))[-1][1] if data.get("cab") else None)
    if blocks.get("fiscal"):
        V4.enrich_fiscal(blocks["fiscal"], cfg, daily, ni, juqp, cab_level, mei_note)
    if blocks.get("central_bank"):
        V4.enrich_central_bank(blocks["central_bank"], cfg, daily, opsf, recon, cab_level, ops_note)
    for k, ser in (("treasury_realized_daily", S.clean(J.best_realized(daily["final"].get("treasury", []), daily["prov"].get("treasury", [])))),
                   ("treasury_projection_daily", S.clean(daily["proj"].get("treasury", []))), ("net_issuance_private_daily", ni.get("net_issuance_private_daily", [])),
                   ("ops_net_daily", opsf.get("ops_net_daily", []))):
        if ser:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, ser)
    E.log_event(oplog, "JPY_V04", "system", dict(note, ops=ops_note, mei=mei_note, juqp=juqp.get("month") if juqp else None,
                                                  net_issuance_last=ni.get("net_issuance_private_daily", [])[-1] if ni.get("net_issuance_private_daily") else None))


def _read_csv_rows(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _merge_csv_rows(path: str, old: List[dict], new: List[dict], cols: List[str], key) -> List[dict]:
    seen = {}
    for r in old + new:
        seen[key(r)] = r
    rows = sorted(seen.values(), key=lambda r: (str(r.get("date")), str(r.get(cols[1]))))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
    return rows

def fetch_chf(cfg: dict, a, prev: dict, hist_dir: str, oplog: str, errors: List[str]) -> Dict[str, dict]:
    """CHF lanes (SNB data portal, no auth, one request per cube ≥ 1 s apart):
      daily      snbgwdzid (policy/SARON/tier, T-1 10:00 CET) + warehouse NSS Confederation curve (11:00 CET) + zirepo (3-week lag)
      weekly     Monday: snbgwdchfsgw sight deposits + snbgwdmigirow (minimum-reserve sight deposits)
      weekly_thu EFV MMDRC results (Tuesday auction) + bond results (resultate-*.xlsx)
      monthly    snbbipo balance sheet, snbmoba, bamire, snbbillshreg register, gmges.xlsx operations, banks (bakredinausbm, babilpobm), snbmonagg, zikrepro, zimoma
      quarterly  snbfxtr FX transactions
    Every lane rebuilds all four blocks from history CSVs so no card sits unavailable after a partial run."""
    blocks: Dict[str, dict] = {k: v for k, v in prev.items() if v}
    src = cfg["sources"]
    fx = a.fixtures
    raw_dir = os.path.join(ROOT, "logs", "chf", "raw") if not fx else None
    lanes = ["daily", "weekly", "weekly_thu", "monthly", "quarterly"] if a.lane == "all" else [a.lane]
    from datetime import date, timedelta
    today = date.today()

    def _err(tag: str, e: Exception) -> None:
        errors.append("%s: %s" % (tag, e))
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": tag, "error": str(e)})

    def _since(days_backfill: int, days_incr: int) -> str:
        return (today - timedelta(days=days_backfill if a.backfill else days_incr)).isoformat()

    data: Dict[str, Series] = {}
    cube = PC.SnbCubeProvider(fixtures_dir=fx, raw_dir=raw_dir)
    efv_records: Dict[str, list] = {}
    ops_rows: list = []

    def _cube(tag: str, cube_id: str, dim_sel, since: str, warehouse: bool = False, fixture=None) -> None:
        try:
            got = cube.fetch(cube_id, dim_sel, since, today.isoformat(), warehouse=warehouse, fixture=fixture)
            if not got:
                raise ProviderError("no series returned")
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
        except Exception as e:  # noqa
            _err(tag, e)

    # ── daily ──
    if "daily" in lanes:
        # policy/tier parameters are step series: always pull from the last regime change so the fixture and the live run agree
        _cube("snbgwdzid[policy]", "snbgwdzid", "D0(LZ,ENG,ZIGBL,ZIG,ZIABP,FREI)", "2021-01-01" if a.backfill else _since(0, 45), fixture="snbgwdzid_policy")
        _cube("snbgwdzid[saron]", "snbgwdzid", "D0(SARON)", _since(900, 45), fixture="snbgwdzid_saron")
        _cube("nss_curve", src["snb_confed_curve_daily"]["warehouse_cube"], src["snb_confed_curve_daily"]["dimSel"], _since(900, 45), warehouse=True, fixture="nss")
        _cube("zirepo", "zirepo", "D0(H0,H1,H2,H4,H5,H6,H7,H8)", _since(900, 60))
    # ── weekly (Monday) ──
    if "weekly" in lanes or "daily" in lanes:
        _cube("snbgwdchfsgw", "snbgwdchfsgw", "D0(GI,UEB,TG)", _since(2000, 60))
        _cube("snbgwdmigirow", "snbgwdmigirow", "D0(GU)", _since(2000, 60))
    # ── weekly_thu: EFV auctions ──
    if "weekly_thu" in lanes or "weekly" in lanes or "daily" in lanes:
        try:
            efv = PC.EfvAuctionsProvider(src["efv_mmdrc_auctions"]["url"], src["efv_bond_auctions"]["url"], fixtures_dir=fx, raw_dir=raw_dir)
            got, errs = efv.fetch()
            for x in errs:
                _err("efv_auctions", Exception(x))
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
            efv_records = efv.records
        except Exception as e:  # noqa
            _err("efv_auctions", e)
    # ── monthly ──
    if "monthly" in lanes or (a.backfill and "daily" in lanes):
        m_since = "2019-01-01" if a.backfill else _since(0, 120)
        _cube("snbbipo", "snbbipo", "D0(GFG,D,FRGSF,GSGSF,GD,T0,N,GB,VB,GBI,US,VRGSF,ES,UT,T1)", m_since)
        _cube("snbmoba", "snbmoba", src["snb_monetary_base"]["dimSel"], m_since)
        _cube("bamire", "bamire", src["snb_min_reserves"]["dimSel"], m_since)
        _cube("bakredinausbm", "bakredinausbm", src["snb_banks_credit"]["dimSel"], m_since)
        _cube("babilpobm", "babilpobm", src["snb_banks_balance_sheet"]["dimSel"], m_since)
        _cube("snbmonagg", "snbmonagg", src["snb_monetary_aggregates"]["dimSel"], m_since)
        _cube("zikrepro", "zikrepro", src["snb_published_rates"]["dimSel"], m_since)
        _cube("zimoma", "zimoma", "D0(EG3M)", m_since)
        try:
            got, ops = PC.SnbOpsProvider(src["snb_money_market_operations"]["url"], fixtures_dir=fx, raw_dir=raw_dir).fetch()
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
            ops_rows = ops
        except Exception as e:  # noqa
            _err("snb_money_market_operations", e)
    # SNB Bills register: small list, needed by the daily ladder → every lane
    try:
        rows, pub = PC.SnbBillsRegisterProvider(src["snb_bills_register"]["url"], fixtures_dir=fx, raw_dir=raw_dir).fetch()
        if rows:
            data["_bills_rows"] = rows  # type: ignore  (list of dicts; excluded from history CSVs)
            if pub:
                E.log_event(oplog, "BILLS_REGISTER", "system", {"publishing_date": pub, "lines": len(rows), "total_m": PC.SnbBillsRegisterProvider.total(rows)})
    except Exception as e:  # noqa
        _err("snb_bills_register", e)
    # ── quarterly ──
    if "quarterly" in lanes or (a.backfill and "daily" in lanes):
        _cube("snbfxtr", "snbfxtr", None, "2015-01-01" if a.backfill else _since(0, 400))
    # history CSVs
    for i, ser in data.items():
        if ser and not i.startswith("_"):
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, ser)
    # any lane on a live run: reload every mapped key from history so all four blocks stay complete
    if not fx:
        need = sorted(set(v for m in (BC.MAP_CB, BC.MAP_FI, BC.MAP_BK, BC.MAP_RT) for v in m.values() if v) |
                      {"zirepo:H0", "snbbipo:UT", "snbbipo:T1", "snbbipo:GFG", "bamire:TB|T", "bamire:TB|GN", "snbmonagg:B|S0", "bills_yield_28d", "ops_swaps_month",
                       "mmdrc_yield", "mmdrc_issued", "bond_yield", "bond_issued", "bond_own_share", "nss:J01M0", "nss:J02M0", "nss:J05M0", "nss:J20M0", "nss:J30M0"})
        for k in need:
            if k not in data:
                p = os.path.join(hist_dir, "%s.csv" % k)
                if os.path.exists(p):
                    data[k] = clean([(r[0], float(r[1])) for r in csv.reader(open(p)) if r and r[0] != "date"])
    # tier parameters are step series (the portal repeats them daily; fixtures/history keep only the changes) → carry forward onto the SARON grid
    sar = data.get("snbgwdzid:SARON")
    if sar:
        for k in ("snbgwdzid:LZ", "snbgwdzid:ENG", "snbgwdzid:ZIGBL", "snbgwdzid:ZIG", "snbgwdzid:ZIABP", "snbgwdzid:FREI"):
            if data.get(k):
                ev = data[k]
                data[k] = clean(ev + [x for x in BJ._ffill(ev, sar) if x[0] > ev[-1][0]])
    blocks["rates"] = BC.build_rates(cfg, data, prev.get("rates"))
    blocks["central_bank"] = BC.build_central_bank(cfg, data, prev.get("central_bank"))
    blocks["fiscal"] = BC.build_fiscal(cfg, data, prev.get("fiscal"))
    blocks["banking"] = BC.build_banking(cfg, data, blocks.get("rates"), prev.get("banking"))
    if str(cfg.get("config_version", "")).startswith("0.4"):
        try:
            _chf_v04(cfg, a, blocks, data, ops_rows, efv_records, hist_dir, oplog, errors, fx, src, raw_dir)
        except Exception as e:  # noqa
            _err("chf_v04", e)
    return blocks


def _chf_v04(cfg: dict, a, blocks: Dict[str, dict], data: dict, ops_rows: list, efv_records: dict, hist_dir: str, oplog: str, errors: List[str], fx, src: dict, raw_dir) -> None:
    """CHF v0.4 (CAMBIOS S1–S3): absorption by operation date, Confederation issuance by settlement, coupons/redemptions, weekly proxy v0.4."""
    from . import ops_chf as O
    from . import blocks_chf_v04 as V4
    from . import series as S
    from datetime import date, timedelta
    import json as _json
    today = date.today().isoformat()
    days = O.business_days((date.today() - timedelta(days=_v04_window_days(a))).isoformat(), today)
    # 1 · SNB operations: the monthly lane fetches gmges; every other lane reads the archive (and fetches once if the archive is empty)
    arch = os.path.join(hist_dir, "snb_ops_rows.csv")
    if not fx and not ops_rows and not os.path.exists(arch):
        try:
            _, ops_rows = PC.SnbOpsProvider(src["snb_money_market_operations"]["url"], fixtures_dir=None, raw_dir=raw_dir).fetch()
        except Exception as e:  # noqa
            errors.append("snb_money_market_operations(v04): %s" % e)
    ops = O.merge_ops_archive(arch, ops_rows) if not fx else ops_rows
    rf = O.repo_flows(ops, days)
    bf = O.bills_flows(ops, days)
    ops_cut = rf["ops_cut"][0][0] if rf.get("ops_cut") else today
    absorption = O.absorption_stock(bf["bills_stock_daily"], rf["repo_ct_stock_daily"])
    es = S.clean(data.get("snbbipo:ES", []))
    vr = S.clean(data.get("snbbipo:VRGSF", []))
    recon_es = O.reconcile_month_end(bf["bills_stock_full"], es)
    recon_vr = O.reconcile_month_end(rf["repo_ct_stock_full"], vr)
    cal_b = O.bills_calendar(data.get("_bills_rows") or [], es[-1][1] if es else None)
    # 2 · Confederation: EFV records (settlement/maturity), bonds outstanding (redemptions, coupons)
    if fx and not efv_records.get("mmdrc"):
        for tag in ("mmdrc", "bonds"):
            pj = os.path.join(ROOT, "fixtures", "chf_hist", "efv_%s_cells.json" % tag)
            if os.path.exists(pj):
                efv_records[tag] = O.efv_records_from_cells(_json.load(open(pj, encoding="utf-8")))
    mm = O.mmdrc_flows(efv_records.get("mmdrc") or [], days)
    bfl = O.bond_flows(efv_records.get("bonds") or [], days)
    out_path = os.path.join(hist_dir, "efv_bonds_outstanding.csv")
    outstanding, asof = ([], None)
    if fx:
        outstanding, asof = O.read_outstanding_csv(os.path.join(fx, "efv_bonds_outstanding.csv"))
    else:
        try:
            blob = PC._http(src.get("efv_bonds_outstanding", {}).get("url", O.OUTSTANDING_URL), binary=True, timeout=120)
            PC._snapshot(raw_dir, "efv_outstanding.xlsx", blob)
            outstanding, asof = O.parse_outstanding_xlsx(blob)
            if outstanding:
                O.write_outstanding_csv(out_path, outstanding, asof)
        except Exception as e:  # noqa
            errors.append("efv_bonds_outstanding: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "efv_bonds_outstanding", "error": str(e)})
        if not outstanding:
            outstanding, asof = O.read_outstanding_csv(out_path)
    cal = O.bond_calendar(outstanding)
    ni = O.net_issuance_private(mm, bfl, cal, days)
    own_avail = round(sum(O._num(r.get("own_available")) or 0.0 for r in outstanding), 1) if outstanding else None
    # 3 · weekly proxy v0.4 on the GI grid
    gi = S.clean(data.get("snbgwdchfsgw:GI", []))
    ops_net = S.merge_series(bf["bills_net_daily"], rf["repo_net_daily"], lambda x, y: round(x + y, 3)) if bf["bills_net_daily"] and rf["repo_net_daily"] else (bf["bills_net_daily"] or rf["repo_net_daily"])
    px = O.intervention_proxy(gi, ops_net, ni, ops_cut)
    gi_level = gi[-1][1] if gi else None
    V4.enrich_central_bank(blocks["central_bank"], cfg, rf, bf, cal_b, absorption, recon_es, recon_vr, px, ops_cut)
    V4.enrich_fiscal(blocks["fiscal"], cfg, mm, bfl, cal, ni, asof, own_avail, gi_level)
    for k, ser in (("ops_net_daily", ops_net), ("absorption_stock_daily", absorption), ("net_issuance_private_daily", ni), ("fx_intervention_proxy_v04", px.get("proxy_weekly", []))):
        if ser:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, ser)
    E.log_event(oplog, "CHF_V04", "system", {"ops_rows": len(ops), "ops_cut": ops_cut, "mmdrc_records": len(efv_records.get("mmdrc") or []), "bond_records": len(efv_records.get("bonds") or []),
                                             "bonds_outstanding": len(outstanding), "outstanding_asof": asof, "es_recon_months": len(recon_es), "proxy_weeks": len(px.get("proxy_weekly", []))})


def fetch_nzd(cfg: dict, a, prev: dict, hist_dir: str, oplog: str, errors: List[str]) -> Dict[str, dict]:
    """NZD lanes (RBNZ stable XLSX URLs + NZDM HTML/XLSX; one request per file >= 1 s apart):
      daily / daily_retry  B2 (rates, T-1 15:00 NZT) + D12 (settlement cash, ORRF, FX swaps, BLF) + D3 (weekly OMO stock, LSAP sales)
      weekly_tue           NZDM T-bill listing + latest result page (14:35 NZT Tuesday)
      weekly_thu           NZDM bond listing + latest result page + D3 (Thursday OMO)
      weekly_mon           D9 weekly turnover
      monthly              R1, R3, D10, D30, C5, C50, L2 + NZDM XLSX histories + bonds on issue (coupon / maturity calendar)
    Every lane rebuilds all four blocks from history CSVs."""
    blocks: Dict[str, dict] = {k: v for k, v in prev.items() if v}
    fx = a.fixtures
    raw_dir = os.path.join(ROOT, "logs", "nzd", "raw") if not fx else None
    lanes = ["daily", "weekly_tue", "weekly_thu", "weekly_mon", "monthly"] if a.lane == "all" else [{"daily_retry": "daily"}.get(a.lane, a.lane)]
    from datetime import date, timedelta
    today = date.today()

    def _err(tag: str, e: Exception) -> None:
        errors.append("%s: %s" % (tag, e))
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": tag, "error": str(e)})

    def _since(days_backfill: int, days_incr: int) -> str:
        return (today - timedelta(days=days_backfill if a.backfill else days_incr)).isoformat()

    data: Dict[str, Series] = {}
    T = PN.RbnzTableProvider(fixtures_dir=fx, raw_dir=raw_dir)

    def _tbl(tag: str, table: str, path: str, since: str) -> None:
        try:
            got = T.fetch(table, path, since)
            if not got:
                raise ProviderError("no series returned")
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
        except Exception as e:  # noqa
            _err(tag, e)

    d3_rows = None
    if "daily" in lanes or "weekly_thu" in lanes:
        _tbl("rbnz_b2", "B2", "b/b2/hb2-daily-close.xlsx", _since(1000, 45))
        try:
            got, blf = PN.RbnzD12Provider(fixtures_dir=fx, raw_dir=raw_dir).fetch_d12(_since(1000, 45))
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
        except Exception as e:  # noqa
            _err("rbnz_d12", e)
        try:
            d3_rows = PN.RbnzD3Provider(fixtures_dir=fx, raw_dir=raw_dir).fetch_d3("2024-01-01")
        except Exception as e:  # noqa
            _err("rbnz_d3", e)
    if "weekly_mon" in lanes or "daily" in lanes:
        _tbl("rbnz_d9", "D9", "d/d9/hd9-weekly.xlsx", _since(1000, 60))
    N = PN.NzdmProvider(fixtures_dir=fx, raw_dir=raw_dir)
    tender_rows: List[dict] = []
    upcoming: List[dict] = []
    for kind, lane in (("tbill", "weekly_tue"), ("bond", "weekly_thu")):
        if lane in lanes or "daily" in lanes:
            try:
                up, comp = N.listing(kind)
                upcoming += [dict(t, kind=kind) for t in up]
                # latest completed tender → HTML result (same day); the XLSX history is the backfill (monthly lane)
                for c in comp[:1 if not a.backfill else 4]:
                    res = N.result(kind, c["number"], c.get("url"))
                    for x in res:
                        tender_rows.append({"tender_date": c["tender"], "settlement_date": c["settlement"], "tender_no": c["number"], "kind": kind, "maturity": x.get("maturity"), "coupon": x.get("coupon"),
                                            "offered": x.get("offered"), "accepted": x.get("allocated"), "bid": x.get("bid"), "bids_n": x.get("bids_n"), "success_n": x.get("success_n"),
                                            "coverage": x.get("coverage"), "low_acc": x.get("low_acc"), "high_acc": x.get("high_acc"), "wavg": x.get("wavg"), "source": "html"})
            except Exception as e:  # noqa
                _err("nzdm_%s" % kind, e)
    if "monthly" in lanes or (a.backfill and "daily" in lanes):
        m_since = "2019-01-01" if a.backfill else _since(0, 120)
        _tbl("rbnz_r1", "R1", "d-f-r/r1/hr1.xlsx", m_since)
        _tbl("rbnz_r3", "R3", "d-f-r/r3/hr3.xlsx", m_since)
        _tbl("rbnz_d30", "D30", "d/d30/hd30.xlsx", m_since)
        _tbl("rbnz_c5", "C5", "c/c5/hc5.xlsx", m_since)
        _tbl("rbnz_c50", "C50", "c/c50/hc50.xlsx", m_since)
        _tbl("rbnz_l2", "L2", "l-s/l2/hl2.xlsx", m_since)
        try:
            got = PN.RbnzD10Provider(fixtures_dir=fx, raw_dir=raw_dir).fetch_d10(m_since)
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
        except Exception as e:  # noqa
            _err("rbnz_d10", e)
        try:
            links = None if fx else N.data_links()
            for kind in ("tbill", "bond"):
                for x in N.history(kind, "2019-01-01" if a.backfill else _since(0, 120), links):
                    tender_rows.append(dict(x, kind=kind, source="xlsx"))
            data["_bonds_on_issue_all"] = N.bonds_on_issue_all(links)  # type: ignore  # every month-end (v0.4 two-sided bond flows)
            data["_bonds_on_issue"] = PN.latest_month_end(data["_bonds_on_issue_all"])  # type: ignore
        except Exception as e:  # noqa
            _err("nzdm_history", e)
    if getattr(N, "fallbacks", None):
        _err("nzdm_last_good_copy", ProviderError("NZDM blocked (HTTP 403): served from the committed raw snapshots — " + "; ".join(N.fallbacks)))
    # persist tender rows / upcoming / bonds on issue as JSON side files (not Series)
    side = os.path.join(hist_dir, "_side.json")
    prev_side = load_json(side) or {}
    if tender_rows:
        merged = {(r["kind"], r["tender_date"], r.get("maturity")): r for r in prev_side.get("tender_rows", [])}
        for r in tender_rows:
            merged[(r["kind"], r["tender_date"], r.get("maturity"))] = r  # HTML rows (same day) overwrite XLSX rows for the same tender
        tender_rows = sorted(merged.values(), key=lambda r: (r["tender_date"], r["kind"], r.get("maturity") or ""))
    else:
        tender_rows = prev_side.get("tender_rows", [])
    upcoming = upcoming or prev_side.get("upcoming", [])
    bonds_on_issue = data.get("_bonds_on_issue") or prev_side.get("bonds_on_issue", [])
    bonds_on_issue_all = data.get("_bonds_on_issue_all") or prev_side.get("bonds_on_issue_all", [])
    if d3_rows is None:
        d3_rows = prev_side.get("d3_rows")
    if not fx:
        save_json(side, {"tender_rows": tender_rows, "upcoming": upcoming, "bonds_on_issue": bonds_on_issue, "bonds_on_issue_all": bonds_on_issue_all, "d3_rows": d3_rows})
    data["_tender_rows"] = tender_rows  # type: ignore
    data["_upcoming_tenders"] = upcoming  # type: ignore
    data["_bonds_on_issue"] = bonds_on_issue  # type: ignore
    data["_bonds_on_issue_all"] = bonds_on_issue_all  # type: ignore
    # tender series (volume-weighted per tender date)
    for kind in ("tbill", "bond"):
        ts = PN.NzdmProvider.tender_series([r for r in tender_rows if r["kind"] == kind])
        for k, ser in ts.items():
            data["NZDM:%s_%s" % (kind, k)] = ser
    # history CSVs (Series only)
    for i, ser in list(data.items()):
        if ser and not i.startswith("_") and isinstance(ser, list) and ser and isinstance(ser[0], tuple):
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, ser)
    if not fx:
        need = sorted(set(v for m in (BN.MAP_CB, BN.MAP_FI, BN.MAP_BK, BN.MAP_RT) for v in m.values() if v) | {"D10:cash_end", "D10:rbnz_transactions", "D10:fx", "D9:BTO.WAF"} |
                      {k for k in os.listdir(hist_dir) if k.startswith("D9:BTO.WAF.N")} )
        for k in need:
            k = k[:-4] if k.endswith(".csv") else k
            if k not in data:
                p = os.path.join(hist_dir, "%s.csv" % k)
                if os.path.exists(p):
                    data[k] = clean([(r[0], float(r[1])) for r in csv.reader(open(p)) if r and r[0] != "date"])
    # OMO stock on the settlement-cash grid (needs D3 rows + D12 dates)
    if d3_rows and data.get("D12:settlement_cash"):
        omo = PN.RbnzD3Provider.omo_series(d3_rows, [d for d, _ in data["D12:settlement_cash"]])
        data.update(omo)
        for i, ser in omo.items():
            if ser:
                append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, ser)
    blocks["central_bank"] = BN.build_central_bank(cfg, data, prev.get("central_bank"))
    blocks["rates"] = BN.build_rates(cfg, data, prev.get("rates"))
    blocks["fiscal"] = BN.build_fiscal(cfg, data, prev.get("fiscal"), blocks["central_bank"])
    blocks["banking"] = BN.build_banking(cfg, data, blocks.get("rates"), prev.get("banking"))
    try:
        _nzd_v04(cfg, a, blocks, data, d3_rows, hist_dir, oplog, errors, fx, N)
    except Exception as e:  # noqa — never block the lane
        errors.append("nzd_v04: %s" % e)
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "nzd_v04", "error": str(e)})
    return blocks


def _nzd_v04(cfg: dict, a, blocks: Dict[str, dict], data: dict, d3_rows, hist_dir: str, oplog: str, errors: List[str], fx, N) -> None:
    """NZD v0.4 (CAMBIOS N1–N6): tenders by settlement, bond calendar, OMO per operation, D10 / OIA reconciliations, ECP."""
    from . import ops_nzd as O
    from . import blocks_nzd_v04 as V4
    from . import series as S
    from datetime import date, timedelta
    today = date.today().isoformat()
    days = O.business_days((date.today() - timedelta(days=_v04_window_days(a))).isoformat(), today)
    tf = O.tender_flows(data.get("_tender_rows") or [], data.get("_upcoming_tenders") or [])
    cal = O.bond_calendar(data.get("_bonds_on_issue") or [])
    # two-sided over the window: market-held redemptions + coupons from every month-end of the register (not only the latest one)
    bf = O.bond_flows_history(data.get("_bonds_on_issue_all") or data.get("_bonds_on_issue") or [], days)
    cal["coupons_market_paid"], cal["bond_redeemed_market"] = bf["coupons_market_paid"], bf["bond_redeemed_market"]
    ni = O.net_issuance_private(tf["tender_settled"], tf["bill_matured"], bf["coupons_market_paid"], days, bf["bond_redeemed_market"])
    tf["tender_settled"], tf["bill_matured"] = O._dense(tf["tender_settled"], days), O._dense(tf["bill_matured"], days)  # true sessions for 5-day sums
    omo = O.omo_flows((d3_rows or {}).get("rr") or [], days)
    # daily residual proxy recomputed on the full history (the block keeps only a window)
    sc = S.clean(data.get("D12:settlement_cash", []))
    omo_out = S.clean(data.get("D3:rr_omo_outstanding", []))
    res = S.diff_series(sc, 1)
    for comp in (S.diff_series(omo_out, 1), S.diff_series(S.clean(data.get("D12:fx_swaps", [])), 1), S.diff_series(S.clean(data.get("D12:overnight_reverse_repo", [])), 1)):
        res = S.merge_series(res, comp, lambda x, y: round(x - y, 1))
    res = S.clean(res)
    gci = S.clean(data.get("D10:govt_cash_influence", []))
    recon_d10 = O.reconcile_monthly(res, gci)
    # OIA daily CSA: fetched once into history/nzd/csa_daily_oia.csv (the Treasury does not update the release)
    oia_path = os.path.join(hist_dir, "csa_daily_oia.csv")
    csa = O.read_csv_series(oia_path)
    if fx:
        csa = O.read_csv_series(os.path.join(fx, "csa_daily_oia.csv"))
    elif not csa:
        try:
            from .providers_nzd import _http
            csa = O.parse_oia_csa_xlsx(_http(O.OIA_CSA_URL, timeout=180, binary=True))
            append_history_csv(oia_path, "csa_daily_oia", csa)
        except Exception as e:  # noqa
            errors.append("oia_csa: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "oia_csa", "error": str(e)})
    recon_oia = O.reconcile_monthly(res, O.monthly_sum(O.csa_flow_from_balance(csa))) if csa else {}
    # ECP on issue (monthly xlsx on the NZDM data page)
    ecp: List = []
    try:
        if fx:
            ecp = O.read_csv_series(os.path.join(fx, "nzdm_ecp_on_issue.csv"))
        else:
            links = N.data_links_all() if hasattr(N, "data_links_all") else {}
            if links.get("ecp"):
                ecp = O.parse_ecp_xlsx(N._get(links["ecp"], "nzdm_ecp.xlsx", binary=True))
    except Exception as e:  # noqa
        errors.append("nzdm_ecp: %s" % e)
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "nzdm_ecp", "error": str(e)})
    sc_level = sc[-1][1] if sc else 0.0
    V4.enrich_central_bank(blocks["central_bank"], cfg, omo, recon_d10, recon_oia, csa)
    V4.enrich_fiscal(blocks["fiscal"], cfg, tf, cal, ni, ecp, res, sc_level)
    for k, ser in (("net_issuance_private_daily", ni), ("omo_net_daily", omo.get("omo_net_daily", [])), ("residual_flow_daily", res), ("ecp_on_issue", ecp),
                   ("bond_redeemed_market", bf["bond_redeemed_market"]), ("coupons_market_paid", bf["coupons_market_paid"])):
        if ser:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, ser)
    E.log_event(oplog, "NZD_V04", "system", {"tenders": len(data.get("_tender_rows") or []), "omo_ops": len((d3_rows or {}).get("rr") or []), "csa_days": len(csa),
                                             "bond_flows_two_sided_from": bf.get("two_sided_from"), "bond_month_ends": len({b.get("month_end") for b in data.get("_bonds_on_issue_all") or []}),
                                             "d10_recon_months": len(recon_d10.get("error", [])), "oia_recon_months": len(recon_oia.get("error", [])) if recon_oia else 0})


def fetch_usd(cfg: dict, a, prev: dict, hist_dir: str, oplog: str, errors: List[str]) -> Dict[str, dict]:
    """USD lanes (FRED keyless CSV + Fiscal Data API; one request per series >= 0.6 s apart):
      daily / daily_retry  DTS (cash, transactions, debt; T-1) + SOFR/IORB/RRP + H.15 (DFF, DTB3, DGS2, DGS10)
      weekly_thu           H.4.1 (WALCL, TREAST, WSHOMCB, WLCFLPCL, WTREGEN, WRESBAL) — Thursday 16:30 ET
      weekly               H.8 (TOTBKCR, TOTLL, TOTCI, DPSACBW027SBOG, H8B3094NCBA) — Friday 16:15 ET
      monthly              BUSLOANS (monthly C&I, legacy id) + everything (revalidation)
    Every lane rebuilds all four blocks from history CSVs (weekly series merged from history on daily lanes)."""
    blocks: Dict[str, dict] = {k: v for k, v in prev.items() if v}
    fx = a.fixtures
    raw_dir = os.path.join(ROOT, "logs", "usd", "raw") if not fx else None
    lanes = ["daily", "weekly_thu", "weekly", "monthly"] if a.lane == "all" else [{"daily_retry": "daily"}.get(a.lane, a.lane)]
    from datetime import date, timedelta
    today = date.today()

    def _err(tag: str, e: Exception) -> None:
        errors.append("%s: %s" % (tag, e))
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": tag, "error": str(e)})

    def _since(days_backfill: int, days_incr: int) -> str:
        return (today - timedelta(days=days_backfill if a.backfill else days_incr)).isoformat()

    def _ids(block: str, freq_prefix: Optional[str] = None, only: Optional[List[str]] = None) -> List[str]:
        out = []
        for s in cfg["blocks"][block]["series"].values():
            if not s.get("id"):
                continue
            if freq_prefix and not s.get("freq", "").startswith(freq_prefix):
                continue
            if only is not None and s["id"] not in only:
                continue
            out.append(s["id"])
        return out

    fred = PU.FredProvider(fixtures_dir=fx, raw_dir=raw_dir)
    data: Dict[str, Series] = {}

    def _fred(tag: str, ids: List[str], since: str) -> None:
        if not ids:
            return
        try:
            got = fred.fetch(ids, since)
            data.update(_merge_hist(hist_dir, got, ids) if not fx else got)
        except Exception as e:  # noqa
            _err(tag, e)

    H41 = ["WALCL", "TREAST", "WSHOMCB", "WLCFLPCL", "WTREGEN", "WRESBAL"]
    H8 = ["TOTBKCR", "TOTLL", "TOTCI", "DPSACBW027SBOG", "H8B3094NCBA"]
    if "daily" in lanes:
        _fred("fred_daily", ["RRPONTTLD"] + _ids("rates"), _since(4 * 365, 60))
    if "weekly_thu" in lanes:
        _fred("fred_h41", H41, _since(4 * 365, 120))
    if "weekly" in lanes:
        _fred("fred_h8", H8, _since(4 * 365, 120))
    if "monthly" in lanes:
        _fred("fred_monthly", ["BUSLOANS"], _since(6 * 365, 400))
    # DTS
    fd = PU.FiscalDataProvider(fixtures_dir=fx, raw_dir=raw_dir)
    if "daily" in lanes:
        since = _since(460, 120)
        fb = cfg["blocks"]["fiscal"]
        try:
            data.update(fd.cash_series(fd.cash(since)))
            data.update(fd.tx_series(fd.tx(since), fb["dts_items"]["deposits"], fb["dts_items"]["withdrawals"]))
            data.update(fd.debt_series(fd.debt(since)))
            if fd.truncated:
                _err("fiscaldata_truncated", ProviderError("; ".join(fd.truncated)))
        except Exception as e:  # noqa
            _err("fiscaldata", e)
        if not fx:
            dts_ids = [k for k in data if k.startswith("DTS:")]
            data = _merge_hist_named(hist_dir, data, dts_ids)
    for i, ser in data.items():
        append_history_csv(os.path.join(hist_dir, "%s.csv" % i.replace("/", "_").replace("|", "_").replace(" ", "_")), i, ser)
    # every lane rebuilds all four blocks: reload what this lane did not fetch from history
    if not fx:
        need = [i for i in _ids("central_bank") + _ids("rates") + _ids("banking") + _ids("fiscal") if i not in data]
        need += [i + "|" + s for i in _ids("fiscal") if i.startswith("DTS:D|") or i.startswith("DTS:W|") or i in ("DTS:debt_issues", "DTS:debt_redemptions") for s in ("mtd", "fytd")]
        need += ["DTS:tot_dep_tx", "DTS:tot_wd_tx"] + ["DTS:tot_dep_tx|" + s for s in ("mtd", "fytd")] + ["DTS:tot_wd_tx|" + s for s in ("mtd", "fytd")]
        data = _merge_hist_named(hist_dir, data, sorted(set(n for n in need if n not in data)))
    blocks["central_bank"] = BU.build_central_bank(cfg, data, prev.get("central_bank"))
    blocks["fiscal"] = BU.build_fiscal(cfg, data, prev.get("fiscal"))
    blocks["banking"] = BU.build_banking(cfg, data, prev.get("banking"))
    blocks["rates"] = BU.build_rates(cfg, data, prev.get("rates"), blocks["central_bank"])
    return blocks


def fetch_eur(cfg: dict, a, prev: dict, hist_dir: str, oplog: str, errors: List[str]) -> Dict[str, dict]:
    """EUR lanes (ECB Data Portal csvdata, one key per request ≥ 1.5 s apart; ECB APP/PEPP CSVs; Finanzagentur XLSX):
      daily / daily_retry  ILM daily (7 keys) + EST (€STR, volume, R25/R75, banks, compounded 3m) + FM key rates + YC + EXR  (T+1 ~09:30 CET)
      weekly_tue           WFS weekly items (MRO, LTRO, MonPol/other securities, MPO liabilities, government deposits, govt debt, L5 total) + Finanzagentur results
      weekly               APP / PEPP holdings + redemptions (Friday)
      monthly              TGB TARGET, IRS, BSI, MIR, BLS, GFS, EURIBOR monthly, HICP + everything (revalidation)
    Every lane rebuilds all four blocks from history CSVs."""
    blocks: Dict[str, dict] = {k: v for k, v in prev.items() if v}
    fx = a.fixtures
    raw_dir = os.path.join(ROOT, "logs", "eur", "raw") if not fx else None
    lanes = ["daily", "weekly_tue", "weekly", "monthly"] if a.lane == "all" else [{"daily_retry": "daily"}.get(a.lane, a.lane)]
    from datetime import date, timedelta
    today = date.today()

    def _err(tag: str, e: Exception) -> None:
        errors.append("%s: %s" % (tag, e))
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": tag, "error": str(e)})

    def _since(days_backfill: int, days_incr: int) -> str:
        return (today - timedelta(days=days_backfill if a.backfill else days_incr)).isoformat()

    def _ids(block: str, freq_prefix: Optional[str] = None, flows: Optional[List[str]] = None) -> List[str]:
        out = []
        for s in cfg["blocks"][block]["series"].values():
            sid = s.get("id")
            if not sid or ":" in sid:
                continue
            if freq_prefix and not s.get("freq", "").startswith(freq_prefix):
                continue
            if flows is not None and sid.split(".")[0] not in flows:
                continue
            out.append(sid)
        return out

    ecb = PE.EcbProvider(fixtures_dir=fx, raw_dir=raw_dir)
    data: Dict[str, Series] = {}

    def _ecb(tag: str, ids: List[str], since: str) -> None:
        ids = sorted(set(ids))
        if not ids:
            return
        errs: List[str] = []
        got = ecb.fetch(ids, since, errs)
        for x in errs:
            _err(tag, ProviderError(x))
        if ecb.no_new:
            E.log_event(oplog, "NO_NEW_OBSERVATIONS", "system", {"source": tag, "keys": list(ecb.no_new)})
            ecb.no_new = []
        got = {k: v for k, v in got.items() if v or fx}
        data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)

    all_blocks = ("central_bank", "fiscal", "banking", "rates")
    if "daily" in lanes:
        _ecb("ecb_daily", _ids("central_bank", "daily") + _ids("rates", "daily"), _since(8 * 365, 45))
    if "weekly_tue" in lanes:
        _ecb("ecb_weekly", _ids("central_bank", "weekly") + _ids("fiscal", "weekly"), _since(12 * 365, 120))
        fa = PE.FinanzagenturProvider(fixtures_dir=fx, raw_dir=raw_dir)
        try:
            got = fa.fetch()
            data.update(_merge_hist_named(hist_dir, got, list(got)) if not fx else got)
            blocks["_de_rows"] = fa.rows  # auction lines for the fiscal history table (not written as a block)
        except Exception as e:  # noqa
            _err("finanzagentur", e)
    if "weekly" in lanes:
        ap = PE.AppPeppProvider(fixtures_dir=fx, raw_dir=raw_dir)
        try:
            got = ap.fetch()
            data.update(_merge_hist_named(hist_dir, got, list(got)) if not fx else got)
        except Exception as e:  # noqa
            _err("ecb_app_pepp", e)
    if "monthly" in lanes:
        _ecb("ecb_monthly", [i for b in all_blocks for i in _ids(b) if i.split(".")[1] in ("M", "Q")], _since(12 * 365, 400))
    for i, ser in data.items():
        append_history_csv(os.path.join(hist_dir, "%s.csv" % i.replace("/", "_").replace("|", "_").replace(" ", "_").replace(":", "_")), i, ser)
    if not fx:
        need = [i for b in all_blocks for i in _ids(b) if i not in data]
        need += [i for i in ("APP:holdings", "PEPP:holdings", "APP:redemptions", "PEPP:redemptions", "DE:bid_to_cover", "DE:avg_yield", "DE:retention", "DE:volume", "DE:bills_bid_to_cover", "DE:bonds_bid_to_cover") if i not in data]
        data = _merge_hist_named(hist_dir, data, sorted(set(need)))
    de_rows = blocks.pop("_de_rows", None)
    blocks["central_bank"] = BE.build_central_bank(cfg, data, prev.get("central_bank"))
    blocks["fiscal"] = BE.build_fiscal(cfg, data, prev.get("fiscal"), aux={"de_rows": de_rows or ((prev.get("fiscal") or {}).get("history") or {}).get("auction_lines")})
    blocks["banking"] = BE.build_banking(cfg, data, prev.get("banking"))
    blocks["rates"] = BE.build_rates(cfg, data, prev.get("rates"), blocks["central_bank"])
    if str(cfg.get("config_version", "")).startswith("0.4"):
        try:
            _eur_v04(cfg, a, blocks, data, de_rows, hist_dir, oplog, errors, fx, raw_dir)
        except Exception as e:  # noqa
            _err("eur_v04", e)
    return blocks


def _merge_hist_named(hist_dir: str, got: Dict[str, Series], names: List[str]) -> Dict[str, Series]:
    """history CSV lookup for series whose ids carry '|' or spaces (DTS line items): file name = sanitised id."""
    out = dict(got)
    for n in names:
        # the archive is written by append_history_csv with ':' kept (history/usd/DTS:D_....csv); older code looked it up with ':'
        # replaced too, so a lane that did not fetch the series (weekly_thu / weekly) rebuilt the block from nothing → try both names
        base = n.replace("/", "_").replace("|", "_").replace(" ", "_")
        p = next((c for c in (os.path.join(hist_dir, "%s.csv" % base), os.path.join(hist_dir, "%s.csv" % base.replace(":", "_"))) if os.path.exists(c)), None)
        if p:
            with open(p, encoding="utf-8") as f:
                rows = list(csv.reader(f))
            ser = [(r[0], float(r[1])) for r in rows[1:] if len(r) >= 2 and r[1] not in ("", "None")]
            if ser or got.get(n):
                out[n] = clean(ser + list(got.get(n, [])))
    return out


def apply_engine_settings(cfg: dict) -> None:
    """Engine v0.3 session settings from config regime.dual: era-anchored percentile windows and the level weight.
    Absent keys = v0.2 behaviour (rolling windows, level weight 1.0)."""
    from . import thresholds as TH
    from . import scoring as SC
    dual = (cfg.get("regime") or {}).get("dual") or {}
    TH.set_era_anchor(dual.get("era_start") if dual.get("anchor_percentiles", bool(dual.get("era_start"))) else None)
    SC.set_level_weight(dual.get("level_weight"))



def _eur_v04(cfg: dict, a, blocks: Dict[str, dict], data: dict, de_rows, hist_dir: str, oplog: str, errors: List[str], fx, raw_dir) -> None:
    """EUR v0.4 (CAMBIOS E1–E4): net issuance by settlement issuer by issuer (DE XLSX, FR XLSX + HTML, ES HTML archive, IT PDF archive, EU HTML archive),
    German gross calendar, fiscal impulse v0.4, MonPol w/w shadow flow."""
    from . import ops_eur as O
    from . import blocks_eur_v04 as V4
    from . import providers_eur as PE
    from . import series as S
    from .providers_chf import xlsx_sheets
    from .providers_jpy import _snapshot
    from datetime import date, timedelta
    import json as _json
    import re as _re
    import time as _time
    today = date.today().isoformat()
    days = O.business_days((date.today() - timedelta(days=_v04_window_days(a))).isoformat(), today)
    hx = os.path.join(ROOT, "fixtures", "eur_hist")
    arch = os.path.join(hist_dir, "issuance_records.csv")
    recs: List[dict] = []
    notes: Dict[str, str] = {}

    def _get(url: str, binary: bool = False, timeout: int = 90, post: Optional[dict] = None):
        from .providers import UA
        from . import tls as T
        hdr = dict(UA, Accept="*/*")
        # T.request = requests + chain completion via AIA when a host omits its intermediate certificate (tesoro.es, 2026-09-10); verify stays on
        r = T.request("POST" if post is not None else "GET", url, raw_dir=raw_dir, notes=notes, data=post, headers=hdr, timeout=timeout)
        if r.status_code != 200:
            raise ProviderError("HTTP %s for %s" % (r.status_code, url))
        return r.content if binary else r.content.decode("utf-8", errors="replace")

    def _pdf_text(blob: bytes) -> str:
        import io as _io
        try:
            import pdfplumber  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise ProviderError("pdfplumber missing (add to requirements.txt): %s" % e)
        with pdfplumber.open(_io.BytesIO(blob)) as p:
            return "\n".join(pg.extract_text() or "" for pg in p.pages)

    # ── DE ──
    rows = de_rows
    if rows is None:
        try:
            fa = PE.FinanzagenturProvider(fixtures_dir=fx, raw_dir=raw_dir)
            fa.fetch()
            rows = fa.rows
        except Exception as e:  # noqa
            errors.append("finanzagentur(v04): %s" % e)
            rows = []
    # issuance history since 1999 (both sides of the German flow: settled issuance over the whole window — the current-year file only
    # adds the rows newer than the history — and the outstanding of every line at its redemption / coupon dates, ops_eur.de_lines)
    de_hist: List[dict] = []
    try:
        if fx:
            blob = open(os.path.join(hx, "emissionshistorie_en.xlsx"), "rb").read()
        else:
            blob = _get(O.DE_HISTORY_XLSX, binary=True)
            _snapshot(raw_dir, "de_emissionshistorie.xlsx", blob)
        de_hist = PE.FinanzagenturProvider.parse(blob)
    except Exception as e:  # noqa
        errors.append("de_history: %s (using the 2026-09-08 fixture)" % str(e)[:120])
        de_hist = PE.FinanzagenturProvider.parse(open(os.path.join(hx, "emissionshistorie_en.xlsx"), "rb").read())
    last_h = max((r["date"] for r in de_hist), default="")
    recs += O.de_records(de_hist + [r for r in (rows or []) if r["date"] > last_h])
    notes["DE"] = "history file to %s (%d rows) + %d current-year rows" % (last_h, len(de_hist), sum(1 for r in (rows or []) if r["date"] > last_h))
    outstanding: List[dict] = []
    de_cal: List[dict] = []
    if fx:
        outstanding = O.de_outstanding_from_csv(os.path.join(hx, "de_outstanding_securities_2026-08-31.csv"))
    else:
        try:
            blob = _get(O.DE_OUTSTANDING, binary=True)
            _snapshot(raw_dir, "de_einzelaufstellung.xlsx", blob)
            outstanding = O.parse_de_outstanding(next(iter(xlsx_sheets(blob).values())))
            if outstanding:
                with open(os.path.join(hist_dir, "de_outstanding_securities.csv"), "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=["type", "isin", "coupon", "issue_date", "maturity", "nominal", "asof"])
                    w.writeheader()
                    for r in outstanding:
                        w.writerow(r)
        except Exception as e:  # noqa
            errors.append("de_outstanding: %s" % e)
            outstanding = O.de_outstanding_from_csv(os.path.join(hist_dir, "de_outstanding_securities.csv"))
        try:
            html = _get(O.DE_CALENDAR_PAGE)
            m = _re.search(r'href="([^"]*[Ii]ssuance_outlook_\d{4}[^"]*\.xlsx)"', html)
            if m:
                url = m.group(1) if m.group(1).startswith("http") else "https://www.deutsche-finanzagentur.de" + m.group(1)
                de_cal = O.parse_de_calendar(next(iter(xlsx_sheets(_get(url, binary=True)).values())))
        except Exception as e:  # noqa
            errors.append("de_calendar: %s" % e)
    # ── FR ──
    if fx:
        recs += O.fr_records_from_csv(os.path.join(hx, "aft_oat_auctions.csv"), os.path.join(hx, "aft_btf_auctions.csv"))
        for fn in ("aft_latest_auctions_2026-08.html", "aft_latest_auctions_2026-09.html"):
            recs += O.fr_records_from_html(open(os.path.join(hx, fn), encoding="utf-8").read())
    else:
        try:
            links = {}
            for page, pat, key in ((O.AFT_OAT_PAGE, r'href="([^"]*_hist_mlt\.xlsx)"', "oat"), (O.AFT_BTF_PAGE, r'href="([^"]*_hist_btf\.xlsx)"', "btf")):
                m = _re.search(pat, _get(page))
                if m:
                    links[key] = m.group(1) if m.group(1).startswith("http") else "https://www.aft.gouv.fr" + m.group(1)
                _time.sleep(1.0)
            fr_hist = O.fr_records_from_xlsx(_get(links["oat"], binary=True) if "oat" in links else None, _get(links["btf"], binary=True) if "btf" in links else None)
            recs += fr_hist
            last_x = max((r["settlement"] for r in fr_hist), default="2000-01-01")
            # bridge the monthly file with the HTML months from the last month in the file to today
            y, mth = int(last_x[:4]), int(last_x[5:7])
            months = []
            while (y, mth) <= (date.today().year, date.today().month):
                months.append((y, mth))
                mth += 1
                if mth > 12:
                    y, mth = y + 1, 1
            for (yy, mm) in months[-4:]:
                html = _get(O.AFT_LATEST, post={"op": "ok", "period_textfield[month]": str(mm), "period_textfield[year]": str(yy)})
                recs += O.fr_records_from_html(html)
                _time.sleep(1.0)
            notes["FR"] = "history file to %s; HTML months %s" % (last_x, ",".join("%d-%02d" % m for m in months[-4:]))
        except Exception as e:  # noqa
            errors.append("aft_v04: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "aft_v04", "error": str(e)})
    # ── ES ──
    es_arch = os.path.join(hist_dir, "es_tesoro_auctions.csv")
    if fx:
        recs += O.es_records_from_csv(os.path.join(hx, "es_tesoro_auctions.csv"))
    else:
        try:
            if not os.path.exists(es_arch) and os.path.exists(os.path.join(hx, "es_tesoro_auctions.csv")):
                import shutil
                os.makedirs(hist_dir, exist_ok=True)
                shutil.copy(os.path.join(hx, "es_tesoro_auctions.csv"), es_arch)  # seed with the 2022→2026-09 crawl
            known = {r["nid"] for r in csv.DictReader(open(es_arch, encoding="utf-8"))} if os.path.exists(es_arch) else set()
            new_rows = []
            for page in range(0, 3 if a.backfill else 2):
                items = O.es_parse_listing(_get(O.ES_LIST % page))
                for it in items:
                    if it["nid"] in known:
                        continue
                    html = _get(O.ES_BASE + it["href"])
                    for r in O.es_parse_auction_page(html, it["title"], it["nid"]):
                        new_rows.append({"nid": it["nid"], "list_date": it["date"], "title": it["title"], "plazo": "", "denominacion": "", "auction": r["auction"], "maturity": r["maturity"],
                                         "settlement": r["settlement"], "nominal_bid": "", "nominal_alloc": r["nominal"], "nominal_2nd": 0, "cash_alloc": r["cash"], "cash_2nd": 0,
                                         "btc": r["cover"] if r["cover"] is not None else "", "avg_yield": r["yield"] if r["yield"] is not None else "", "marginal_yield": ""})
                    known.add(it["nid"])
                    _time.sleep(0.8)
                _time.sleep(1.0)
            if new_rows:
                exists = os.path.exists(es_arch)
                with open(es_arch, "a", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=list(new_rows[0].keys()))
                    if not exists:
                        w.writeheader()
                    for r in new_rows:
                        w.writerow(r)
            recs += O.es_records_from_csv(es_arch)
            notes["ES"] = "%d new auction pages" % len(new_rows)
        except Exception as e:  # noqa
            errors.append("tesoro_v04: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "tesoro_v04", "error": str(e)})
            recs += O.es_records_from_csv(es_arch)
    # ── IT ──
    it_arch = os.path.join(hist_dir, "it_mef_auctions.csv")
    if fx:
        for fn in ("mef_btp10_2026-07-30.pdf", "mef_bot6_latest.pdf"):
            pth = os.path.join(hx, fn)
            if os.path.exists(pth):
                try:
                    recs += O.it_parse_pdf_text(_pdf_text(open(pth, "rb").read()), fn)
                except Exception as e:  # noqa
                    errors.append("mef_pdf(%s): %s" % (fn, e))
    else:
        try:
            old = O.read_records(it_arch)
            seen = {r["source"] for r in old}
            new_recs = []
            years = list(range(2022, date.today().year + 1)) if (a.backfill or not old) else [date.today().year]
            for key, page in O.IT_PAGES.items():
                for yy in years:
                    try:
                        html = _get(O.IT_INDEX % (page, yy))
                    except Exception as e:  # noqa
                        errors.append("mef_index(%s,%d): %s" % (key, yy, e))
                        continue
                    for url in O.it_pdf_links(html):
                        tag = "mef_pdf:" + url.rsplit("/", 1)[-1]
                        if tag in seen or (tag + "#supplementary") in seen:
                            continue
                        try:
                            got = O.it_parse_pdf_text(_pdf_text(_get(url, binary=True, timeout=60)), url)
                            new_recs += got
                            seen.add(tag)
                        except Exception as e:  # noqa
                            errors.append("mef_pdf(%s): %s" % (url.rsplit("/", 1)[-1], e))
                        _time.sleep(0.5)
                    _time.sleep(0.8)
            all_it = O.merge_records(it_arch, new_recs) if new_recs else old
            recs += all_it
            notes["IT"] = "%d new PDFs, %d records" % (len(new_recs), len(all_it))
        except Exception as e:  # noqa
            errors.append("mef_v04: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "mef_v04", "error": str(e)})
            recs += O.read_records(it_arch)
    # ── EU ──
    eu_arch = os.path.join(hist_dir, "eu_auctions.csv")
    # round 3: the Commission's Qlik app (all operations since Jun-2020 with Date of settlement + NCB settlement) is the primary EU
    # source; the auction news pages stay as a contrast archive only. Seed fixture from 2026-09-10 when the engine is unreachable.
    from . import ops_eu_qlik as Q
    from . import ops_esm as ESM
    eu_q_recs: List[dict] = []
    eu_out: List[dict] = []
    q_tx_path = os.path.join(hist_dir, "eu_qlik_transactions.csv")
    q_out_path = os.path.join(hist_dir, "eu_qlik_outstanding.csv")
    seed_tx, seed_out = os.path.join(hx, "eu_transactions_qlik_2026-09-10.csv"), os.path.join(hx, "eu_outstanding_qlik_2026-09-10.csv")
    if fx:
        eu_q_recs = Q.records_from_fixture_csv(seed_tx)
        eu_out = Q.outstanding_from_fixture_csv(seed_out)
        notes["EU_qlik"] = "fixture seed"
    else:
        try:
            rows_tx = Q.fetch_qlik_table(Q.TX_FIELDS_EXTRA)
            rows_out = Q.fetch_qlik_table(Q.OUT_FIELDS)
            with open(q_tx_path, "w", encoding="utf-8") as f:
                f.write(Q.rows_to_csv(Q.TX_FIELDS_EXTRA, rows_tx))
            with open(q_out_path, "w", encoding="utf-8") as f:
                f.write(Q.rows_to_csv(Q.OUT_FIELDS, rows_out))
            eu_q_recs = Q.transactions_from_rows(Q.TX_FIELDS_EXTRA, rows_tx)
            eu_out = Q.outstanding_from_rows(Q.OUT_FIELDS, rows_out)
            notes["EU_qlik"] = "engine: %d rows / %d outstanding" % (len(rows_tx), len(rows_out))
        except Exception as e:  # noqa
            errors.append("eu_qlik: %s (using the last good copy)" % str(e)[:160])
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "eu_qlik", "error": str(e)[:300]})
            eu_q_recs = Q.records_from_fixture_csv(q_tx_path if os.path.exists(q_tx_path) else seed_tx)
            eu_out = Q.outstanding_from_fixture_csv(q_out_path if os.path.exists(q_out_path) else seed_out)
            notes["EU_qlik"] = "last good copy (%s)" % ("archive" if os.path.exists(q_tx_path) else "seed 2026-09-10")
    if fx:
        eu_news = O.eu_records_from_tables(_json.load(open(os.path.join(hx, "eu_auction_result_tables.json"), encoding="utf-8")))
        recs += eu_q_recs if eu_q_recs else eu_news
    else:
        try:
            old = O.read_records(eu_arch)
            seen = {r["source"].split("#")[0] for r in old}
            tables = {}
            years = [date.today().year - 1, date.today().year] if (a.backfill or not old) else [date.today().year]
            for kind in ("bills", "bonds"):
                for yy in years:
                    for u in O.eu_result_links(_get(O.EU_YEAR % (kind, yy))):
                        tag = "eu_news:" + u.rsplit("/", 1)[-1]
                        if tag in seen:
                            continue
                        tables[u] = O._html_tables(_get(O.EU_BASE + u))
                        _time.sleep(0.6)
                    _time.sleep(0.8)
            new_recs = O.eu_records_from_tables(tables)
            all_eu = O.merge_records(eu_arch, new_recs) if new_recs else old
            if eu_q_recs:
                recs += eu_q_recs  # Qlik is the source of record; the news archive is contrast only
                qk = {(r["isin"], r["settlement"]) for r in eu_q_recs}
                miss = [r for r in all_eu if (r["isin"], r["settlement"]) not in qk]
                notes["EU"] = "qlik %d records; news archive %d (%d new pages; %d news records not in qlik)" % (len(eu_q_recs), len(all_eu), len(tables), len(miss))
            else:
                recs += all_eu
                notes["EU"] = "news only: %d new result pages, %d records" % (len(tables), len(all_eu))
        except Exception as e:  # noqa
            errors.append("eu_v04: %s" % e)
            E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "eu_v04", "error": str(e)})
            recs += eu_q_recs if eu_q_recs else O.read_records(eu_arch)
    # ── ESM / EFSF (round 3): outstanding list (public CSV) + ESM bill auctions via the Bundesbank press PDFs (value date published) ──
    esm_rows: List[dict] = []
    esm_arch = os.path.join(hist_dir, "esm_bills.csv")
    esm_fx = os.path.join(hx, "esm")
    try:
        if fx:
            esm_rows = ESM.parse_esm_transactions_csv(open(os.path.join(esm_fx, "esm_transactions_outstanding_2026-09-10.csv"), encoding="utf-8").read())
            ann = [ESM.parse_esm_announcement(_pdf_text(open(os.path.join(esm_fx, "esm_bill_announcement_2026-08-28.pdf"), "rb").read()))]
            res = [ESM.parse_esm_result(_pdf_text(open(os.path.join(esm_fx, "esm_bill_result_2026-09-01.pdf"), "rb").read()))]
            esm_recs = ESM.esm_bill_records(ann, res)
        else:
            try:
                txt = _get(ESM.ESM_CSV_URL if hasattr(ESM, "ESM_CSV_URL") else "https://www.esm.europa.eu/export-transactions-list?_format=csv")
                esm_rows = ESM.parse_esm_transactions_csv(txt)
                with open(os.path.join(hist_dir, "esm_transactions_outstanding.csv"), "w", encoding="utf-8") as f:
                    f.write(txt)
            except Exception as e:  # noqa
                errors.append("esm_csv: %s" % str(e)[:120])
                p = os.path.join(hist_dir, "esm_transactions_outstanding.csv")
                esm_rows = ESM.parse_esm_transactions_csv(open(p if os.path.exists(p) else os.path.join(esm_fx, "esm_transactions_outstanding_2026-09-10.csv"), encoding="utf-8").read())
            old_esm = O.read_records(esm_arch)
            seen_isin = {r["isin"] for r in old_esm}
            pages = range(0, 113) if (a.backfill or not old_esm) else range(0, 2)
            ann, res = [], []
            for pg in pages:
                try:
                    items = ESM.bundesbank_list_links(_get(ESM.bundesbank_list_url(pg), timeout=60))
                except Exception as e:  # noqa
                    errors.append("bbk_esm_list(%d): %s" % (pg, str(e)[:80]))
                    break
                if not items:
                    break
                for it in items:
                    if it["kind"] not in ("announcement", "result") or it["issuer"] != "ESM":
                        continue
                    try:
                        txt = _pdf_text(_get(it["url"], binary=True, timeout=60))
                        (ann if it["kind"] == "announcement" else res).append(ESM.parse_esm_announcement(txt) if it["kind"] == "announcement" else ESM.parse_esm_result(txt))
                    except Exception as e:  # noqa
                        errors.append("bbk_esm_pdf(%s): %s" % (it["date"], str(e)[:60]))
                    _time.sleep(0.4)
                if not a.backfill and old_esm and all((r.get("isin") in seen_isin) for r in res if r.get("isin")):
                    break
                _time.sleep(0.6)
            new_esm = [r for r in ESM.esm_bill_records(ann, res) if r["isin"] not in seen_isin or a.backfill]
            esm_recs = O.merge_records(esm_arch, new_esm) if new_esm else old_esm
            notes["ESM"] = "%d bill records (%d new); outstanding list %d issues" % (len(esm_recs), len(new_esm), len(esm_rows))
        recs += esm_recs
    except Exception as e:  # noqa
        errors.append("esm_v04: %s" % e)
        E.log_event(oplog, "SOURCE_ERROR", "system", {"source": "esm_v04", "error": str(e)})
        recs += O.read_records(esm_arch) if not fx else []
    eu_cal = Q.eu_calendar(eu_out) if eu_out else {}
    esm_cal = ESM.esm_calendar(esm_rows) if esm_rows else {}
    # ── flows ──
    if not fx:
        recs = O.merge_records(arch, recs)
    # GROSS bond redemptions + coupons enter the net for the issuers whose outstanding per line is primary (DE history file, EU Qlik operations);
    # FR / ES / IT / ESM stay one-sided (no per-line outstanding source wired) — see ops_eur module docstring
    lines = O.de_lines(de_hist, outstanding) + Q.eu_lines(eu_q_recs, eu_out)
    fl = O.issuance_flows(recs, days, lines)
    notes["bonds"] = "redemptions + coupons GROSS from %d DE lines + %d EU lines; FR/ES/IT/ESM one-sided" % (sum(1 for l in lines if l["issuer"] == "DE"), sum(1 for l in lines if l["issuer"] == "EU"))
    cal = O.de_calendar(outstanding)
    de_ahead = O.de_supply_ahead(de_cal)
    gd = S.clean(data.get("ILM.W.U2.C.L050100.U2.EUR", []))
    ex = S.clean(data.get("ILM.D.U2.C.EXLIQ.U2.EUR", []))
    grid = [d for d, _ in gd] or [d for d, _ in S.clean(data.get("ILM.W.U2.C.A070100.U2.EUR", []))]
    ni_weekly = O.weekly_on(fl["net_issuance_private_daily"], grid[-160:]) if grid else []
    impulse = []
    if gd and ni_weekly:
        dgd = [(gd[i][0], round(-(gd[i][1] - gd[i - 1][1]), 3)) for i in range(1, len(gd))]
        impulse = S.merge_series(dgd, ni_weekly, lambda x, y: round(x - y, 3))
    cov_by: Dict[str, Dict[str, list]] = {}
    last_by: Dict[str, str] = {}
    for r in recs:
        c = O._num(r.get("cover"))
        if c is not None and r.get("auction"):
            cov_by.setdefault(r["issuer"], {}).setdefault(r["auction"], []).append(c)
        if r.get("settlement"):
            last_by[r["issuer"]] = max(last_by.get(r["issuer"], ""), r["settlement"])
    coverage = {iss: S.clean(sorted((d, round(sum(v) / len(v), 3)) for d, v in m.items())) for iss, m in cov_by.items()}
    V4.enrich_fiscal(blocks["fiscal"], cfg, fl, cal, de_ahead, ni_weekly, impulse, coverage, last_by, ex[-1][1] if ex else None)
    V4.enrich_fiscal_eu_esm(blocks["fiscal"], cfg, eu_cal, esm_cal, notes)
    V4.enrich_central_bank(blocks["central_bank"], cfg)
    for k, ser in (("net_issuance_private_daily", fl["net_issuance_private_daily"]), ("net_issuance_private_weekly", ni_weekly), ("fiscal_impulse_v04_weekly", impulse),
                   ("bond_redeemed_all", fl.get("bond_redeemed_all", [])), ("coupons_paid_all", fl.get("coupons_paid_all", []))):
        if ser:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % k), k, ser)
    E.log_event(oplog, "EUR_V04", "system", {"records": len(recs), "by_issuer": {iss: sum(1 for r in recs if r["issuer"] == iss) for iss in ("DE", "FR", "ES", "IT", "EU", "ESM")},
                                             "last_settlement": last_by, "de_lines": len(outstanding), "de_calendar": len(de_cal), "weeks": len(ni_weekly), "notes": notes})


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccy", default="cad")
    ap.add_argument("--lane", default="all", choices=["weekly", "weekly_mon", "weekly_tue", "weekly_thu", "daily", "daily_retry", "daily_provisional", "ten_day", "monthly", "quarterly", "all"])
    ap.add_argument("--backfill", action="store_true", help="fetch full history (first run / monthly revalidation)")
    ap.add_argument("--fixtures", default=None, help="offline mode: read CSV fixtures from this dir instead of HTTP")
    ap.add_argument("--no-rss", action="store_true")
    a = ap.parse_args(argv)

    ccy = a.ccy.lower()
    cfg = json.load(open(os.path.join(ROOT, "config", "%s.json" % ccy), encoding="utf-8"))
    apply_engine_settings(cfg)
    data_dir = os.path.join(ROOT, "data", ccy)
    hist_dir = os.path.join(ROOT, "history", ccy)
    log_dir = os.path.join(ROOT, "logs", ccy)
    oplog = os.path.join(log_dir, "oplog.json")
    errors: List[str] = []

    prev = {b: load_json(os.path.join(data_dir, "%s.json" % b)) for b in ("central_bank", "fiscal", "banking", "rates")}
    fetch = {"cad": fetch_cad, "gbp": fetch_gbp, "aud": fetch_aud, "jpy": fetch_jpy, "chf": fetch_chf, "nzd": fetch_nzd, "usd": fetch_usd, "eur": fetch_eur}[ccy]
    blocks = fetch(cfg, a, prev, hist_dir, oplog, errors)

    # ── quality (system-wide) ──
    per: Dict[str, dict] = {}
    for bname, blk in blocks.items():
        for k, e in blk.get("series", {}).items():
            if isinstance(e, dict) and "confidence" in e:
                if e.get("source_id") is None and e.get("status") == "unavailable":
                    continue  # pending-by-design (no source wired yet): shown as — in the UI, excluded from system confidence
                per[bname + "." + k] = {"freshness": e["status"], "confidence": {"score": e["confidence"], "tier": "HIGH" if e["confidence"] >= 90 else "MEDIUM" if e["confidence"] >= 70 else "LOW" if e["confidence"] >= 50 else "CRITICAL"},
                                        "last_valid_date": e.get("date"), "age_days": e.get("age_days"), "latest_outlier": e.get("latest_outlier", False)}
    quality = {"currency": cfg["currency"], "generated_at": E.now_iso(), "series": per, "system": system_summary({k: {"confidence": v["confidence"]} for k, v in per.items()}), "errors": errors}
    # heartbeat / degraded flags at block level
    for bname, blk in blocks.items():
        if errors and blk["source_health"]["series_loaded"] == 0:
            blk["source_health"]["status"] = "unavailable"
        blk["source_health"]["errors"] = [x for x in errors]

    # ── regime, scenarios, alerts, revisions ──
    regime = E.classify_regime(cfg, blocks, load_json(os.path.join(data_dir, "regime.json")), hist_dir=hist_dir)  # hist_dir: v0.4 components read the archive
    scenarios = E.evaluate_scenarios(cfg, blocks)
    alerts_path = os.path.join(log_dir, "alerts.json")
    existing = (load_json(alerts_path) or {}).get("alerts", [])
    alerts = E.evaluate_alerts(cfg, blocks, quality, existing)
    revs: List[dict] = []
    keep = cfg.get("revisions", {}).get("series", [])
    for bname, blk in blocks.items():
        if prev.get(bname):
            revs += E.detect_revisions(E.block_history_map(prev[bname]), E.block_history_map(blk), keep)
    rev_path = os.path.join(log_dir, "revisions.json")
    old_revs = (load_json(rev_path) or {}).get("revisions", [])
    all_revs = (revs + old_revs)[:cfg.get("revisions", {}).get("keep_last", 50)]
    # regime history (52-week heatmap) + changelog
    rh_path = os.path.join(log_dir, "regime_history.json")
    rh = load_json(rh_path) or {"weeks": [], "changelog": []}
    as_of = blocks.get("central_bank", {}).get("as_of") or E.now_iso()[:10]
    week = {"week_of": as_of, "regime": regime["regime"], "score": regime["weighted_score"],
            "cells": {b: {"traffic_light": blocks[b]["signals"]["traffic_light"], "score": blocks[b]["signals"]["score"]} for b in blocks},
            "flags": regime["flags"]}
    rh["weeks"] = [w for w in rh["weeks"] if w["week_of"] != as_of] + [week]
    rh["weeks"] = rh["weeks"][-52:]
    prev_reg = rh.get("current")
    if prev_reg and prev_reg != regime["regime"]:
        rh["changelog"].insert(0, {"timestamp": E.now_iso(), "old": prev_reg, "new": regime["regime"], "score": regime["weighted_score"], "cause": "DATA_DRIVEN"})
        rh["changelog"] = rh["changelog"][:50]
        E.log_event(oplog, "REGIME_CHANGE", "system", {"old": prev_reg, "new": regime["regime"]})
    rh["current"] = regime["regime"]

    # ── news wire (optional) ──
    news = []
    if not a.no_rss and not a.fixtures:
        try:
            news = fetch_rss((cfg["sources"].get("boc_rss") or cfg["sources"].get("boe_rss") or {}).get("feeds", []))
        except Exception:
            news = []

    # ── write outputs ──
    for bname, blk in blocks.items():
        save_json(os.path.join(data_dir, "%s.json" % bname), blk)
    save_json(os.path.join(data_dir, "calendar.json"), E.build_calendar(cfg, blocks))
    save_json(os.path.join(data_dir, "quality.json"), quality)
    save_json(os.path.join(data_dir, "regime.json"), {"currency": cfg["currency"], "generated_at": E.now_iso(), "as_of": as_of, "config_version": cfg["config_version"],
                                                       **regime, "scenarios": scenarios, "heartbeat": {"lane": a.lane, "backfill": a.backfill, "errors": errors}})
    save_json(os.path.join(data_dir, "news.json"), {"generated_at": E.now_iso(), "items": news})
    save_json(alerts_path, {"generated_at": E.now_iso(), "alerts": alerts})
    save_json(rev_path, {"generated_at": E.now_iso(), "revisions": all_revs})
    save_json(rh_path, rh)
    # mirror logs into data for the frontend (single read root)
    save_json(os.path.join(data_dir, "alerts.json"), {"generated_at": E.now_iso(), "alerts": alerts})
    save_json(os.path.join(data_dir, "revisions.json"), {"generated_at": E.now_iso(), "revisions": all_revs})
    save_json(os.path.join(data_dir, "regime_history.json"), rh)
    E.log_event(oplog, "REFRESH_AUTO", "system", {"lane": a.lane, "backfill": a.backfill, "blocks": list(blocks), "errors": errors, "regime": regime["regime"], "new_revisions": len(revs)})
    # ── daily_log (template 1.0) + jefe de mesa + anti-invention gate → data/<ccy>/agent.json, data/mesa/jefe.json ──
    try:
        from . import narrative as N
        ag = N.run(ccy, ROOT)
        E.log_event(oplog, "AGENT_DAILY_LOG", "system", {"gate": ag["gate"]["pass"], "failures": ag["gate"]["failures"], "hash": ag["hash"], "degraded": ag["degraded"], "streaks": ag["streaks"]})
        print("daily_log gate=%s hash=%s degraded=%d" % ("PASS" if ag["gate"]["pass"] else "FAIL", ag["hash"], len(ag["degraded"])))
    except Exception as e:  # the narrative never blocks the data refresh
        E.log_event(oplog, "AGENT_DAILY_LOG_ERROR", "system", {"error": str(e)})
        print("daily_log error: %s" % e)
    # ── Telegram (config/notify.json): one message per transition; dry run without secrets ──
    try:
        from . import notify as NT
        nres = NT.run_events(ccy, ROOT)
        E.log_event(oplog, "NOTIFY", "system", nres)
        print("notify mode=%s messages=%d delivered=%d" % (nres.get("mode"), nres.get("messages", 0), nres.get("ok", 0)))
    except Exception as e:
        E.log_event(oplog, "NOTIFY_ERROR", "system", {"error": str(e)})
        print("notify error: %s" % e)
    save_json(os.path.join(data_dir, "oplog.json"), load_json(oplog) or {"entries": []})

    print("regime=%s score=%s flags=%s blocks=%s errors=%s" % (regime["regime"], regime["weighted_score"], regime["flags"], list(blocks), errors))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())