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
        if ser:
            append_history_csv(os.path.join(hist_dir, "%s.csv" % i), i, ser)
    # daily lane on a live run: pull monthly/ten-day/weekly series from history so all blocks stay complete
    if not fx:
        need = ["ac_" + k for k, _ in PJ.BojAccountsProvider.ITEMS] + ["FAAP@01", "FAAPOBAL1", "FAAPOBAL1@", "FAAPOBRDCD5", "MAM1NAM2M2MO", "MAM1NAM3M3MO", "MAM1NAM3M1MO", "MAM1NAM3DMMO", "MABS1AN11",
                                                                     "MASDM@01", "MASDM254", "MASDM255", "MASDM273", "MASDM26", "MASDM@03", "MACAB1043", "MACAB1183", "btc_20y", "btc_30y", "btc_40y",
                                                                     "taxes_receipts", "pension_payments", "fefsa_receipts", "fefsa_receipts_py", "fefsa_payments", "gov_bonds_over_1y_receipts", "tbills_balance",
                                                                     "on_col_same_avg", "1w_unc_fwd_avg", "1m_unc_fwd_avg", "3m_unc_same_avg", "call_outstanding_total", "treasury_proj"]
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


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccy", default="cad")
    ap.add_argument("--lane", default="all", choices=["weekly", "daily", "daily_provisional", "ten_day", "monthly", "all"])
    ap.add_argument("--backfill", action="store_true", help="fetch full history (first run / monthly revalidation)")
    ap.add_argument("--fixtures", default=None, help="offline mode: read CSV fixtures from this dir instead of HTTP")
    ap.add_argument("--no-rss", action="store_true")
    a = ap.parse_args(argv)

    ccy = a.ccy.lower()
    cfg = json.load(open(os.path.join(ROOT, "config", "%s.json" % ccy), encoding="utf-8"))
    data_dir = os.path.join(ROOT, "data", ccy)
    hist_dir = os.path.join(ROOT, "history", ccy)
    log_dir = os.path.join(ROOT, "logs", ccy)
    oplog = os.path.join(log_dir, "oplog.json")
    errors: List[str] = []

    prev = {b: load_json(os.path.join(data_dir, "%s.json" % b)) for b in ("central_bank", "fiscal", "banking", "rates")}
    fetch = {"cad": fetch_cad, "gbp": fetch_gbp, "aud": fetch_aud, "jpy": fetch_jpy}[ccy]
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
    regime = E.classify_regime(cfg, blocks)
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
