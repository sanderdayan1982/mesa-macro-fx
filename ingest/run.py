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

    return blocks


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
    return blocks


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
    return blocks


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
    return blocks

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
            got, errs = PC.EfvAuctionsProvider(src["efv_mmdrc_auctions"]["url"], src["efv_bond_auctions"]["url"], fixtures_dir=fx, raw_dir=raw_dir).fetch()
            for x in errs:
                _err("efv_auctions", Exception(x))
            data.update(_merge_hist(hist_dir, got, list(got)) if not fx else got)
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
    return blocks

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
            data["_bonds_on_issue"] = N.bonds_on_issue(links)  # type: ignore
        except Exception as e:  # noqa
            _err("nzdm_history", e)
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
    if d3_rows is None:
        d3_rows = prev_side.get("d3_rows")
    if not fx:
        save_json(side, {"tender_rows": tender_rows, "upcoming": upcoming, "bonds_on_issue": bonds_on_issue, "d3_rows": d3_rows})
    data["_tender_rows"] = tender_rows  # type: ignore
    data["_upcoming_tenders"] = upcoming  # type: ignore
    data["_bonds_on_issue"] = bonds_on_issue  # type: ignore
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
    return blocks


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
    return blocks


def _merge_hist_named(hist_dir: str, got: Dict[str, Series], names: List[str]) -> Dict[str, Series]:
    """history CSV lookup for series whose ids carry '|' or spaces (DTS line items): file name = sanitised id."""
    out = dict(got)
    for n in names:
        p = os.path.join(hist_dir, "%s.csv" % n.replace("/", "_").replace("|", "_").replace(" ", "_").replace(":", "_"))
        if os.path.exists(p):
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
    regime = E.classify_regime(cfg, blocks, load_json(os.path.join(data_dir, "regime.json")))
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
    save_json(os.path.join(data_dir, "oplog.json"), load_json(oplog) or {"entries": []})

    print("regime=%s score=%s flags=%s blocks=%s errors=%s" % (regime["regime"], regime["weighted_score"], regime["flags"], list(blocks), errors))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
