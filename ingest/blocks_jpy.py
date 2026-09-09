"""JPY block builders — Bank of Japan floor system under QT (config/jpy.json v0.2, triangulated 2026-09-08).
  1 central bank — DAILY current account balances / reserve balances / excess (vs required daily average), market operations by
                   type (JGB purchases vs plan, pooled collateral, CLF, SLF), BoJ Accounts every ten days (JGBs, loans, gov deposits)
  2 fiscal       — 'Treasury funds and others' DAILY (DTS analogue, BoJ sign: minus = net receipt = drain), BoJ next-day projection,
                   MoF monthly receipts/payments (taxes, pension, FEFSA = FX intervention footprint), auction bid-to-cover
  3 banking      — MD13 loans/deposits, MD02 money stock, Loan Support Program, MD08 foreign banks' excess share (canary)
  4 rates        — TONA vs IOER (floor), TONA high vs IOER, Tokyo Repo Rate (GC) vs IOER/TONA, term repo, JGB curve (2/5/10/20/30/40Y)
Data keys expected from run.py: daily XLSX keys (cab, reserve_bal, excess, req_daily, treasury, banknotes, ops_ex_lsp, jgb_purch,
pooled_all, pooled_ho, loans, slf, lsp, net_change, mbase, cab_nonres, [treasury_proj]); BoJ Accounts as 'ac_<item>'; API codes as-is;
MoF yields '1Y'..'40Y'; JSDA 'trr_<tenor>'; fcall keys; MoF receipts '<item>_<field>'; auctions 'btc_<tenor>'; corridor
'basic_loan_rate' / 'policy_rate' / 'ioer'."""
from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple
from . import series as S
from .series import Series
from .thresholds import classify, signal_band
from .scoring import Comps
from .blocks import entry, _prev_levels, _alert, _health, _base as _base0
from .blocks_gbp import _persistent_level

# config series key -> data key (None = pending by design)
MAP_CB = {"cab_daily": "cab", "reserve_balances_daily": "reserve_bal", "excess_reserves_daily": "excess", "cab_non_reserve_daily": "cab_nonres",
          "required_reserves_daily_avg": "req_daily", "cab_net_change_daily": "net_change", "banknotes_factor_daily": "banknotes",
          "ops_subtotal_daily": "ops_ex_lsp", "jgb_purchases_daily": "jgb_purch", "pooled_collateral_ops_daily": "pooled_all",
          "clf_loans_daily": "loans", "slf_daily": "slf", "monetary_base_daily": "mbase", "total_assets": "ac_total_assets",
          "jgb_holdings": "ac_jgb_holdings", "boj_loans": "ac_boj_loans", "loan_support_program": "ac_loan_support_program",
          "pooled_collateral_loans": "ac_pooled_collateral_loans", "foreign_currency_assets": "ac_foreign_currency_assets",
          "banknotes": "ac_banknotes", "current_deposits": "ac_current_deposits", "government_account": "ac_government_account",
          "repos_payable": "ac_repos_payable", "policy_rate": "policy_rate", "ioer": "ioer", "basic_loan_rate": "basic_loan_rate",
          "monthly_fiscal_breakdown": "MASDM@03", "cab_by_sector": "MACAB1043"}
MAP_FI = {"treasury_funds_daily": "treasury", "treasury_funds_projection": "treasury_proj", "government_account": "ac_government_account",
          "net_fiscal_payments_monthly": "MASDM@01", "jgb_issued_monthly": "MASDM254", "jgb_redeemed_monthly": "MASDM255",
          "tbills_net_monthly": "MASDM273", "fx_factor_monthly": "MASDM26", "auction_calendar": None, "auction_results": "btc_30y",
          "receipts_payments_monthly": "taxes_receipts", "taxes_monthly": "taxes_receipts", "pension_payments_monthly": "pension_payments",
          "fefsa_receipts_monthly": "fefsa_receipts", "fefsa_payments_monthly": "fefsa_payments", "jgb_issued_monthly_mof": "gov_bonds_over_1y_receipts",
          "tbills_net_monthly_mof": "tbills_balance", "foreign_jgb_flow_weekly": None}
MAP_BK = {"loans_total": "FAAP@01", "loans_major_regional": "FAAPOBAL1", "loans_yoy_pct": "FAAPOBAL1@", "deposits_total": "FAAPOBRDCD5",
          "m2": "MAM1NAM2M2MO", "m3": "MAM1NAM3M3MO", "m1": "MAM1NAM3M1MO", "deposit_money": "MAM1NAM3DMMO", "monetary_base_monthly": "MABS1AN11",
          "loan_support_program": "ac_loan_support_program", "cab_by_sector": "MACAB1043"}
MAP_RT = {"tona": "STRDCLUCON", "tona_high": "STRDCLUCONH", "tona_low": "STRDCLUCONL", "tona_volume": "STRDCLUCV",
          "collateralized_on": "on_col_same_avg", "call_1w": "1w_unc_fwd_avg", "call_1m": "1m_unc_fwd_avg", "call_3m": "3m_unc_same_avg",
          "call_market_outstanding": "call_outstanding_total", "policy_rate": "policy_rate", "ioer": "ioer", "basic_loan_rate": "basic_loan_rate",
          "jgb_1y": "1Y", "jgb_2y": "2Y", "jgb_5y": "5Y", "jgb_10y": "10Y", "jgb_20y": "20Y", "jgb_30y": "30Y", "jgb_40y": "40Y",
          "trr_on": "trr_on", "trr_on_t0": "trr_on_t0", "trr_1w": "trr_1w", "trr_1m": "trr_1m", "trr_3m": "trr_3m", "trr_1y": "trr_1y"}

PENDING_IF_EMPTY = ("treasury_funds_projection",)  # lives only after the provisional lane runs
FACILITY_ZERO = ("jgb_purchases_daily", "pooled_collateral_ops_daily", "clf_loans_daily", "slf_daily")


def _freq(sc: dict) -> str:
    f = sc.get("freq", "daily")
    return "daily" if f.startswith("daily") else "ten_day" if f.startswith("ten") else "monthly" if f.startswith("monthly") else "weekly" if f.startswith("weekly") else "quarterly" if f.startswith("quarter") else "event" if f == "event" else "daily"


def _spec(th: dict, key: str) -> Optional[dict]:
    """thresholds with parseable windows ('since 2024-08-01 or 750d' → '330d' for daily factors, '750d' otherwise)."""
    sp = th.get(key)
    if not sp:
        return None
    sp = dict(sp)
    w = str(sp.get("window", ""))
    if "since 2025-10" in w:
        sp["window"] = "330d"
    elif "since" in w or " or " in w:
        sp["window"] = "750d"
    elif "ten-day" in w:
        sp["window"] = "108w"
    return sp


def _ffill(ev: Series, grid: Series) -> Series:
    out, j, cur = [], 0, None
    for d, _ in grid:
        while j < len(ev) and ev[j][0] <= d:
            cur = ev[j][1]
            j += 1
        if cur is not None:
            out.append((d, cur))
    return out


def _base(ccy, block, cfg, bcfg, E, D, signals, history):
    out = _base0(ccy, block, cfg, bcfg, E, D, signals, history)
    wired = {k: e for k, e in E.items() if e.get("source_id")}
    out["source_health"] = _health(wired, len(wired))
    out["source_health"]["series_pending"] = len(E) - len(wired)
    return out


def _entries(cfg: dict, block: str, data: Dict[str, Series], MAP: Dict[str, Optional[str]], unit: str, pl: Dict[str, str], th: dict,
             zero_if_empty: Tuple[str, ...] = (), anchor: Optional[Series] = None) -> Tuple[Dict[str, dict], Dict[str, Series]]:
    E: Dict[str, dict] = {}
    raw: Dict[str, Series] = {}
    latest = anchor[-1][0] if anchor else None
    for key, sc in cfg["blocks"][block]["series"].items():
        dk = MAP.get(key)
        ser = S.clean(data.get(dk, [])) if dk else []
        raw[key] = ser
        fq = _freq(sc)
        u = sc.get("unit") or ("%" if fq != "ten_day" and ("rate" in key or key.startswith(("tona", "jgb", "trr", "call_", "ioer", "collateralized")))
                               and not re.search(r"volume|outstanding|purchases|issued|redeemed|holdings", key) else unit)
        if "pct" in key or key.endswith("_yoy"):
            u = "%"
        e = entry(key, ser, sc["label"] if "label" in sc else key, fq, u, cfg, sc.get("id"), sc.get("usd_analog"), status=None if dk else "unavailable",
                  spec=_spec(th, key), prev_level=pl.get(key), z_window=30 if fq == "daily" else 12 if fq == "monthly" else 9 if fq == "ten_day" else 26)
        if key in zero_if_empty and dk and latest and (not ser or ser[-1][0] < latest):
            e.update({"status": "fresh", "value": 0.0, "prev_value": ser[-1][1] if ser else None, "prev_date": ser[-1][0] if ser else None, "change_abs": None,
                      "change_pct": None, "level": "SAFE", "confidence": 100, "date": latest, "age_days": 0,
                      "equivalence_note": ("no usage on %s (last use %s = %s)" % (latest, ser[-1][0], ser[-1][1])) if ser else "empty cell in the daily file = no usage (0)"})
            raw[key] = ser + [(latest, 0.0)]
        if fq == "event" and ser:
            e["status"] = "fresh"
        if sc.get("display_only"):
            e["display_only"] = True
        if sc.get("note") or sc.get("role"):
            e["equivalence_note"] = sc.get("note") or sc.get("role")
        if not dk or (not ser and key in PENDING_IF_EMPTY):
            e["status"] = "unavailable"
            e["source_id"] = None  # pending-by-design: excluded from source_health and system confidence
            e["pending_by_design"] = True
            e["equivalence_note"] = sc.get("status") or sc.get("role") or sc.get("note") or sc.get("label")
        E[key] = e
    return E, raw


# ═══════════════════════ 1 · CENTRAL BANK — BoJ current account balances (daily) + Accounts (ten-day) ═══════════════════════
def build_central_bank(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["central_bank"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    cab = S.clean(data.get("cab", []))
    E, raw = _entries(cfg, "central_bank", data, MAP_CB, unit, pl, th, zero_if_empty=FACILITY_ZERO, anchor=cab)
    resb, req = raw["reserve_balances_daily"], raw["required_reserves_daily_avg"]
    ta, ga, jgb = raw["total_assets"], raw["government_account"], raw["jgb_holdings"]
    D: Dict[str, dict] = {}
    # excess vs required (our own definition: reserve balances − daily-average requirement; the BoJ 'Excess reserves' row is a
    # maintenance-period concept that saw-tooths on the 16th → shown, not scored)
    exc = S.merge_series(resb, req, lambda r, q: r - q)
    D["excess_over_required_daily"] = entry("excess_over_required_daily", exc, "Excess reserves = reserve balances − required (daily avg)", "daily", unit, cfg,
                                            status="fresh" if exc else "unavailable", z_window=30, equivalence_note="desk definition; the BoJ row 'Excess reserves' is period-based")
    ratio = S.merge_series(resb, req, lambda r, q: round((r - q) / q, 2) if q else None)
    D["excess_to_required_ratio"] = entry("excess_to_required_ratio", ratio, "Excess / required reserves (ampleness multiple)", "daily", "x", cfg,
                                          status="fresh" if ratio else "unavailable", z_window=30, equivalence_note=b["derived"]["excess_to_required_ratio"]["note"])
    rv = D["excess_to_required_ratio"]["value"]
    pa = th["reserves"]["primary_absolute"]
    if rv is not None:
        lvl = "CRISIS" if rv < pa["crisis_below"] else "STRESS" if rv < pa["stress_below"] else "WATCH" if rv < pa["watch_below"] else "SAFE"
        D["excess_to_required_ratio"].update({"level": lvl, "in_range": pa["watch_below"] <= rv <= pa["ample_above"], "above_range": rv > pa["ample_above"],
                                              "thresholds": {"method": "absolute", "levels": {"WATCH": pa["watch_below"], "STRESS": pa["stress_below"], "CRISIS": pa["crisis_below"], "ample_above": pa["ample_above"]}}})
    # secondary level anchor on excess (¥200 tn / ¥100 tn, desk proposal)
    sec = pa.get("secondary_level_anchor", {})
    ev = D["excess_over_required_daily"]["value"]
    if ev is not None and sec:
        D["excess_over_required_daily"]["level"] = "STRESS" if ev < sec["stress_below"] else "WATCH" if ev < sec["watch_below"] else "SAFE"
        D["excess_over_required_daily"]["thresholds"] = {"method": "absolute", "levels": {"WATCH": sec["watch_below"], "STRESS": sec["stress_below"]}}
    dod = S.diff_series(cab)
    D["cab_dod"] = entry("cab_dod", dod, "CAB Δ day/day (daily reserve impulse)", "daily", unit, cfg, usd_analog="Δ WRESBAL daily", status="fresh" if dod else "unavailable",
                         spec=_spec(th, "cab_dod"), prev_level=pl.get("cab_dod"), z_window=30)
    c20 = S.diff_series(cab, 20)
    D["cab_20d_change"] = entry("cab_20d_change", c20, "CAB Δ 20 sessions", "daily", unit, cfg, status="fresh" if c20 else "unavailable",
                                spec=_spec(th, "cab_20d_change"), prev_level=pl.get("cab_20d_change"), z_window=30)
    # reconciliation: Δcab vs reported net change
    nc = raw["cab_net_change_daily"]
    recon = S.merge_series(dod, nc, lambda a, c: abs(a - c))
    rec_fail = bool(recon and recon[-1][1] > 200)
    D["reconciliation_cab"] = {"label": "Δ CAB vs reported net change (100m yen)", "value": recon[-1][1] if recon else None, "status": "fresh" if recon else "unavailable",
                               "date": recon[-1][0] if recon else None, "level": "STRESS" if rec_fail else "SAFE", "note": "> 200 = data_degraded"}
    nl = S.merge_series(ta, ga, lambda a, g: a - g)
    D["net_liquidity"] = entry("net_liquidity", nl, "Balance-sheet liquidity = Total assets − Government deposits (ten-day)", "ten_day", unit, cfg, usd_analog="WALCL − TGA",
                               status="fresh" if nl else "unavailable", z_window=9, equivalence_note=b["derived"]["net_liquidity"]["note"])
    D["net_liquidity"]["display_only"] = True
    nlp = S.pct_change_series(nl)
    D["net_liquidity_change_pct"] = entry("net_liquidity_change_pct", nlp, "Balance-sheet liquidity Δ% per ten-day step", "ten_day", "%", cfg, status="fresh" if nlp else "unavailable", z_window=9)
    sb = signal_band(D["net_liquidity_change_pct"]["value"], nlp, dict(_spec(th, "net_liquidity_change_pct") or {}, window="108w"), "ten_day")
    D["net_liquidity_change_pct"].update({"signal": sb["signal"], "percentile": sb.get("percentile")})
    # JGB purchases month-to-date vs plan
    jp = raw["jgb_purchases_daily"]
    plan = cfg["calendar"].get("jgb_purchase_plan", {})
    mtd, mtd_date, plan_v, proj = None, None, None, None
    if jp:
        import calendar as _c
        ym = jp[-1][0][:7]
        y_, m_ = int(ym[:4]), int(ym[5:7])
        if sum(1 for dd in range(1, int(jp[-1][0][8:]) + 1) if _c.weekday(y_, m_, dd) < 5) < 8:
            ym = "%04d-%02d" % ((y_ - 1, 12) if m_ == 1 else (y_, m_ - 1))  # early in the month: judge the last full month
        mtd = round(sum(v for d, v in jp if d[:7] == ym), 1)
        mtd_date = max(d for d, _ in jp if d[:7] == ym) if any(d[:7] == ym for d, _ in jp) else jp[-1][0]
        q = "%sQ%d" % (ym[:4], (int(ym[5:7]) - 1) // 3 + 1)
        plan_v = plan.get(q) or plan.get("from_2027Q2") if ym >= "2027-04" else plan.get(q)
        y, m = int(ym[:4]), int(ym[5:7])
        bdays_total = sum(1 for dd in range(1, _c.monthrange(y, m)[1] + 1) if _c.weekday(y, m, dd) < 5)
        bdays_done = sum(1 for dd in range(1, int(mtd_date[8:]) + 1) if _c.weekday(y, m, dd) < 5)
        proj = round(mtd * bdays_total / max(1, bdays_done), 1)
    D["jgb_purchases_month_to_date"] = {"label": "Outright JGB purchases in the month judged (100m yen)", "month": ym if jp else None, "value": mtd, "date": mtd_date, "status": "fresh" if mtd is not None else "unavailable",
                                        "projected_month": proj, "plan": plan_v, "unit": unit, "note": b["derived"]["jgb_purchases_month_to_date"]["note"]}
    pct = round((proj - plan_v) / plan_v, 3) if (proj is not None and plan_v) else None
    tq = th.get("jgb_purchases_vs_plan_pct", {})
    D["jgb_purchases_vs_plan_pct"] = {"label": "JGB purchases (projected month) vs plan", "value": pct, "date": mtd_date, "status": "fresh" if pct is not None else "unavailable", "unit": "ratio",
                                      "level": "NO DATA" if pct is None else "WATCH" if (pct > tq.get("nimble_above", 0.2) or pct < tq.get("faster_qt_below", -0.2)) else "SAFE",
                                      "direction": None if pct is None else "NIMBLE_SUPPORT" if pct > tq.get("nimble_above", 0.2) else "FASTER_QT" if pct < tq.get("faster_qt_below", -0.2) else "ON_PLAN",
                                      "note": b["derived"]["jgb_purchases_vs_plan_pct"]["note"]}
    # holdings vs expected path (informational)
    hv = None
    if jgb:
        d0, v0 = "2026-08-31", 5199277.0
        d1, v1 = "2027-03-31", 4800000.0
        from datetime import date
        ld = jgb[-1][0]
        t = (date.fromisoformat(ld) - date.fromisoformat(d0)).days / max(1, (date.fromisoformat(d1) - date.fromisoformat(d0)).days)
        hv = round(jgb[-1][1] - (v0 + (v1 - v0) * max(0.0, t)), 1)
    D["holdings_vs_expected_path"] = {"label": "JGB holdings − expected path (519.9 tn → ~480 tn by 2027-03-31)", "value": hv, "date": jgb[-1][0] if jgb else None,
                                      "status": "fresh" if hv is not None else "unavailable", "unit": unit, "display_only": True, "note": b["derived"]["holdings_vs_expected_path"]["note"]}
    j3 = S.diff_series(jgb, 9)
    D["jgb_holdings_90d_change"] = entry("jgb_holdings_90d_change", j3, "JGB holdings Δ over 9 ten-day steps (~quarter; redemptions cluster on the 20th of Mar/Jun/Sep/Dec)", "ten_day", unit, cfg, status="fresh" if j3 else "unavailable", z_window=9)
    dep = S.merge_series(S.add_series(raw["pooled_collateral_loans"], raw["loan_support_program"]) if raw["loan_support_program"] else raw["pooled_collateral_loans"],
                         S.clean([(d, v) for d, v in cab if d in dict(ta)]) or cab, lambda a, c: round(a / c, 4) if c else None)
    # align ten-day loans to the CAB on the same date (Accounts dates are month-days present in the daily file most of the time)
    dep = S.merge_series(S.add_series(raw["pooled_collateral_loans"], raw["loan_support_program"]) if raw["loan_support_program"] else raw["pooled_collateral_loans"],
                         raw["current_deposits"], lambda a, c: round(a / c, 4) if c else None)
    D["boj_credit_dependence"] = entry("boj_credit_dependence", dep, "BoJ credit share of current deposits (pooled collateral + Loan Support Program)", "ten_day", "ratio", cfg,
                                       status="fresh" if dep else "unavailable", spec=dict(_spec(th, "boj_credit_dependence") or {}, window="108w"), prev_level=pl.get("boj_credit_dependence"), z_window=9,
                                       equivalence_note=b["derived"]["boj_credit_dependence"]["note"])
    D["currency_drain_daily"] = entry("currency_drain_daily", raw["banknotes_factor_daily"], "Banknote factor (BoJ sign: minus = net issuance = drain)", "daily", unit, cfg,
                                      status="fresh" if raw["banknotes_factor_daily"] else "unavailable", z_window=30)
    phase = "STEADY"
    if pct is not None and pct > tq.get("nimble_above", 0.2):
        phase = "NIMBLE_SUPPORT"
    elif j3 and j3[-1][1] < 0:
        phase = "QT"
    D["balance_sheet_phase"] = {"label": "Balance-sheet phase", "value": None, "phase": phase, "status": "fresh", "date": jgb[-1][0] if jgb else None, "note": b["derived"]["balance_sheet_phase"]["formula"]}
    clf = E["clf_loans_daily"]["value"] or 0.0
    flags: List[str] = []
    if clf > 0:
        flags.append("CLF_USED")
    if D["boj_credit_dependence"].get("level") in ("WATCH", "STRESS", "CRISIS"):
        flags.append("BOJ_CREDIT_DEPENDENCE_ELEVATED")
    if D["jgb_purchases_vs_plan_pct"].get("direction") in ("NIMBLE_SUPPORT", "FASTER_QT"):
        flags.append("JGB_PURCHASES_VS_PLAN_" + D["jgb_purchases_vs_plan_pct"]["direction"])
    if rec_fail:
        flags.append("DATA_DEGRADED")
    lvl = D["excess_to_required_ratio"].get("level", "NO DATA")
    above = D["excess_to_required_ratio"].get("above_range")
    C = Comps(cfg, "mean2")
    C.level("excess_to_required", {"SAFE": 0.75 if above else 0.25, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}.get(lvl, 0.0))
    C.flow("cab_20d_level", {"SAFE": 0.25, "WATCH": -0.5, "STRESS": -1.0, "CRISIS": -1.5}.get(D["cab_20d_change"].get("level"), 0.0))
    C.flow("cab_dod_level", {"SAFE": 0.0, "WATCH": -0.5, "STRESS": -1.0, "CRISIS": -1.5}.get(D["cab_dod"].get("level"), 0.0))
    C.flow("balance_sheet_band", 1.0 if sb["signal"] == "RISK_ON" else -1.0 if sb["signal"] == "RISK_OFF" else 0.0)
    if clf > 0:
        C.event("clf", -2.0)
    score = C.score()
    alerts = [_alert("excess_to_required_ratio", D["excess_to_required_ratio"], "dead-man switch: < 5x WATCH, < 2x STRESS (desk proposal; price must confirm)"),
              _alert("clf_loans_daily", E["clf_loans_daily"], "Complementary Lending Facility > 0 = a bank paid the ceiling"),
              _alert("cab_20d_change", D["cab_20d_change"], "20-session CAB drop below p15 = drain (QT + fiscal)"),
              _alert("slf_daily", E["slf_daily"], "SLF ≥ p95 only matters with GC repo above the floor"),
              _alert("boj_credit_dependence", D["boj_credit_dependence"], "informational unless TONA at/above IOER")]
    label = "NO SIGNAL" if not cab else ("INJECTION" if score >= 0.5 else "DRAIN" if score <= -0.5 else "NEUTRAL")
    tl = "NONE" if not cab else "GREEN" if score >= 0.5 else "RED" if score <= -0.75 else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags, "components": C.to_dict(),
               "detail": "CAB %s · excess/required %sx (%s) · ΔCAB d/d %s · 20d %s (%s) · JGB purchases vs plan %s · CLF %s" % (
                   E["cab_daily"]["value"], rv, lvl, D["cab_dod"]["value"], D["cab_20d_change"]["value"], D["cab_20d_change"].get("level"), pct, clf), "alerts": alerts}
    hd = [d for d, _ in S.tail(cab, 120)]
    rows = {k: [dict(v).get(d) for d in hd] for k, v in (("cab_daily", cab), ("reserve_balances_daily", resb), ("excess_over_required_daily", exc), ("cab_dod", dod),
                                                        ("treasury_funds_daily", S.clean(data.get("treasury", []))), ("jgb_purchases_daily", raw["jgb_purchases_daily"]),
                                                        ("slf_daily", raw["slf_daily"]), ("cab_net_change_daily", nc))}
    ht = [d for d, _ in S.tail(ta, 36)]
    rows_t = {k: [dict(v).get(d) for d in ht] for k, v in (("total_assets", ta), ("jgb_holdings", jgb), ("government_account", ga), ("net_liquidity", nl),
                                                          ("boj_loans", raw["boj_loans"]), ("current_deposits", raw["current_deposits"]), ("boj_credit_dependence", dep))}
    history = {"dates": hd, "rows": rows, "ten_day": {"dates": ht, "rows": rows_t}, "signal_log": (prev or {}).get("history", {}).get("signal_log", [])[-120:]}
    if hd:
        history["signal_log"] = [x for x in history["signal_log"] if x.get("date") != hd[-1]] + [{"date": hd[-1], "label": label, "score": score, "note": signals["detail"]}]
    return _base(cfg["currency"], "central_bank", cfg, b, E, D, signals, history)


# ═══════════════════════ 2 · FISCAL — treasury funds daily (BoJ) + MoF monthly + auctions ═══════════════════════
def build_fiscal(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["fiscal"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E, raw = _entries(cfg, "fiscal", data, MAP_FI, unit, pl, {})
    tf = raw["treasury_funds_daily"]
    D: Dict[str, dict] = {}
    D["fiscal_flow_daily"] = entry("fiscal_flow_daily", tf, "Fiscal flow daily = Treasury funds and others (positive = net payments = injection)", "daily", unit, cfg, usd_analog="−ΔTGA / DTS net",
                                   status="fresh" if tf else "unavailable", z_window=250, equivalence_note=b["derived"]["fiscal_flow_daily"]["sign"])
    z = [(d, v) for d, v in S.rolling_zscore(tf, 250) if v is not None]
    D["fiscal_flow_zscore"] = entry("fiscal_flow_zscore", z, "Fiscal flow Z-score (250 sessions)", "daily", "σ", cfg, status="fresh" if z else "unavailable", z_window=250)
    zv = D["fiscal_flow_zscore"]["value"]
    if zv is not None:
        D["fiscal_flow_zscore"]["level"] = "STRESS" if abs(zv) >= 2 else "WATCH" if abs(zv) >= 1 else "SAFE"
    c5, c20 = S.rolling_sum(tf, 5), S.rolling_sum(tf, 20)
    D["fiscal_flow_5d_cum"] = entry("fiscal_flow_5d_cum", c5, "Fiscal flow 5-session cumulative", "daily", unit, cfg, status="fresh" if c5 else "unavailable", z_window=60)
    D["fiscal_flow_20d_cum"] = entry("fiscal_flow_20d_cum", c20, "Fiscal flow 20-session cumulative", "daily", unit, cfg, status="fresh" if c20 else "unavailable", z_window=60)
    tw = th.get("fiscal_flow_20d_cum", {})
    sb = signal_band(D["fiscal_flow_20d_cum"]["value"], c20, {"window": "750d", "risk_on_above": tw.get("injection_above", "p80"), "risk_off_below": tw.get("drain_below", "p20")}, "daily") if c20 else {"signal": "NO DATA", "percentile": None}
    D["fiscal_flow_20d_cum"].update({"signal": sb["signal"], "percentile": sb.get("percentile")})
    fv = D["fiscal_flow_daily"]["value"]
    big = (fv is not None and abs(fv) >= 30000) or (zv is not None and abs(zv) >= 2)
    D["fiscal_big_day"] = {"label": "FISCAL_BIG_DAY (|flow| ≥ ¥3 tn or |Z| ≥ 2)", "value": bool(big), "direction": ("DRAIN" if (fv or 0) < 0 else "INJECTION") if big else None,
                           "status": "fresh" if fv is not None else "unavailable", "date": D["fiscal_flow_daily"]["date"], "note": b["derived"]["fiscal_big_day"]["note"]}
    proj = raw["treasury_funds_projection"]
    gap = S.merge_series(tf, proj, lambda a, p: a - p) if proj else []
    D["fiscal_projection_gap"] = entry("fiscal_projection_gap", gap, "Final − BoJ projection (surprise)", "daily", unit, cfg, status="fresh" if gap else "unavailable", z_window=60,
                                       equivalence_note="requires the jp (projection) lane; offline = unavailable")
    # FX intervention suspect: daily outlier without tax/auction context (dates learned later) OR monthly FEFSA ≥ 3x prior year OR MASDM26 outlier
    fef, fefpy = raw["fefsa_receipts_monthly"], S.clean(data.get("fefsa_receipts_py", []))
    fx26 = raw["fx_factor_monthly"]
    ratio = S.merge_series(fef, fefpy, lambda a, p: round(a / p, 2) if p else None)
    monthly_hit = bool(ratio and ratio[-1][1] >= 3)
    z26 = [(d, v) for d, v in S.rolling_zscore(fx26, 36) if v is not None]
    fx_hit = bool(z26 and abs(z26[-1][1]) >= 3)
    daily_hit = bool(zv is not None and zv <= -3)
    D["fx_intervention_suspect"] = {"label": "FX_INTERVENTION_SUSPECT", "value": bool(daily_hit or monthly_hit or fx_hit), "status": "fresh" if (tf or fef) else "unavailable",
                                    "date": max([x for x in (D["fiscal_flow_daily"]["date"], fef[-1][0] if fef else None) if x] or [None]),
                                    "daily_outlier": daily_hit, "fefsa_receipts_vs_prior_year": ratio[-1][1] if ratio else None, "fefsa_month": fef[-1][0] if fef else None,
                                    "masdm26_z": z26[-1][1] if z26 else None, "note": b["derived"]["fx_intervention_suspect"]["sign"]}
    btc = [S.clean(data.get(k, [])) for k in ("btc_20y", "btc_30y", "btc_40y")]
    merged: Dict[str, List[float]] = {}
    for s_ in btc:
        for d, v in s_:
            merged.setdefault(d, []).append(v)
    bsl = S.clean([(d, round(sum(v) / len(v), 3)) for d, v in merged.items()])
    D["bid_to_cover_superlong"] = entry("bid_to_cover_superlong", bsl, "Bid-to-cover — 20Y/30Y/40Y auctions (mean per auction date)", "event", "x", cfg, status="fresh" if bsl else "unavailable",
                                        spec=dict(th.get("bid_to_cover_superlong", {}), direction="low_is_risk", window="36w", min_n=12), prev_level=pl.get("bid_to_cover_superlong"), z_window=12)
    if bsl:
        D["bid_to_cover_superlong"]["status"] = "fresh"
    # ── auction tail (yield at lowest accepted − yield at average, bp) from the MoF per-auction result pages ──
    tails: Dict[str, List[float]] = {}
    for k in ("tail_20y", "tail_30y", "tail_40y"):
        for d, v in S.clean(data.get(k, [])):
            tails.setdefault(d, []).append(v)
    tsl = S.clean([(d, round(sum(v) / len(v), 2)) for d, v in tails.items()])
    tail_spec = dict(th.get("auction_tail_superlong_bp", {"method": "percentile", "window": "36w", "watch_above": "p85", "stress_above": "p95",
                                                          "secondary_absolute": {"watch": 3, "stress": 6, "crisis": 12}}), direction="high_is_risk", window="36w", min_n=12)
    D["auction_tail_superlong_bp"] = entry("auction_tail_superlong_bp", tsl, "Auction tail — 20Y/30Y/40Y (yield at lowest accepted − average, bp)", "event", "bps", cfg,
                                           status="fresh" if tsl else "unavailable", spec=tail_spec, prev_level=pl.get("auction_tail_superlong_bp"), z_window=12,
                                           equivalence_note="MoF result pages only (since the XLS lacks the average yield); the May-2025 20Y auction is the reference stress event")
    if tail_spec.get("secondary_absolute") and tsl:
        _cap_watch(D["auction_tail_superlong_bp"], tail_spec["secondary_absolute"])
    t10 = S.clean(data.get("tail_10y", []))
    D["auction_tail_10y_bp"] = entry("auction_tail_10y_bp", t10, "Auction tail — 10Y (bp)", "event", "bps", cfg, status="fresh" if t10 else "unavailable", z_window=12)
    # ── auction calendar (MoF monthly HTML): next JGB auctions, super-long supply ahead ──
    cal = [c for c in (data.get("_auction_calendar") or []) if isinstance(c, dict)]  # type: ignore
    asof = D["fiscal_flow_daily"]["date"] or (tf[-1][0] if tf else None)
    upcoming = sorted([c for c in cal if c.get("tenor") and asof and c["date"] > asof], key=lambda c: c["date"])[:8]
    nxt = upcoming[0] if upcoming else None
    nxt_sl = next((c for c in upcoming if c["tenor"] in ("20y", "30y", "40y")), None)
    def _days(a: Optional[str], b_: Optional[str]) -> Optional[int]:
        if not a or not b_:
            return None
        from datetime import date as _dt
        return (_dt.fromisoformat(b_) - _dt.fromisoformat(a)).days
    E["auction_calendar"] = {"source_id": "mof_auction_calendar", "label": "JGB auction calendar — next coupon auctions (MoF monthly HTML)", "unit": "days", "frequency": "event",
                             "status": "fresh" if upcoming else "unavailable", "value": _days(asof, nxt["date"]) if nxt else None, "date": asof if upcoming else None,
                             "next": nxt, "next_superlong": nxt_sl, "days_to_superlong": _days(asof, nxt_sl["date"]) if nxt_sl else None,
                             "upcoming": [{"date": c["date"], "tenor": c["tenor"], "issue": c["issue"]} for c in upcoming],
                             "level": "WATCH" if (nxt_sl and _days(asof, nxt_sl["date"]) is not None and _days(asof, nxt_sl["date"]) <= 3) else ("SAFE" if upcoming else "NO DATA"),
                             "note": "supply event: super-long auction within 3 days = WATCH (position for the tail / QT_STRESS read)"}
    if E["auction_calendar"]["status"] == "fresh":
        E["auction_calendar"].pop("pending_by_design", None)
    supply_ahead = E["auction_calendar"]["level"] == "WATCH"
    reg = "NO DATA" if not c20 else "INJECTION" if sb["signal"] == "RISK_ON" else "DRAIN" if sb["signal"] == "RISK_OFF" else "NEUTRAL"
    score = 0.0 if reg == "NO DATA" else round(max(-1.5, min(1.5, (zv or 0.0) * 0.75)), 2)
    CF = Comps(cfg, "sum", -1.5, 1.5).flow("fiscal_flow_z", score)
    D["fiscal_regime"] = {"label": "Fiscal regime", "value": None, "regime": reg, "status": "fresh" if c20 else "unavailable", "date": D["fiscal_flow_daily"]["date"]}
    D["fiscal_regime_score"] = {"label": "Fiscal regime score (capped ±1.5)", "value": score, "range": [-1.5, 1.5], "status": "fresh", "date": D["fiscal_flow_daily"]["date"]}
    D["mmt_note"] = {"label": "MMT note", "value": None, "status": "fresh", "date": None,
                     "text": "Government payments create net financial assets; taxes destroy them; JGB/T-Bill issuance drains reserves without changing that stock. The daily BoJ factor nets all of it — the MoF monthly Excel attributes it."}
    alerts = [_alert("fiscal_flow_zscore", D["fiscal_flow_zscore"], "|Z| ≥ 2 = extraordinary daily flow (tax day, JGB settlement, pension, FX intervention)"),
              {"metric": "fiscal_flow_20d_cum", "level": "WATCH" if reg == "DRAIN" else "SAFE" if reg != "NO DATA" else "NO DATA", "value": D["fiscal_flow_20d_cum"]["value"], "threshold": None,
               "status": D["fiscal_flow_20d_cum"]["status"], "action_hint": "20-session cumulative below p20 = fiscal drain"},
              _alert("bid_to_cover_superlong", D["bid_to_cover_superlong"], "weak super-long demand feeds the QT_STRESS overlay"),
              _alert("auction_tail_superlong_bp", D["auction_tail_superlong_bp"], "wide tail = dealers demanded concession; ≥ 6 bp STRESS, ≥ 12 bp CRISIS (May-2025 20Y type event)"),
              {"metric": "auction_calendar", "level": E["auction_calendar"]["level"], "value": E["auction_calendar"]["value"], "threshold": None, "status": E["auction_calendar"]["status"],
               "action_hint": ("next super-long: %s %s" % (nxt_sl["date"], nxt_sl["tenor"])) if nxt_sl else "no super-long auction in the published calendar"}]
    flags = (["FISCAL_BIG_DAY"] if big else []) + (["FX_INTERVENTION_SUSPECT"] if D["fx_intervention_suspect"]["value"] else []) \
        + (["SUPER_LONG_TAIL"] if D["auction_tail_superlong_bp"].get("level") in ("WATCH", "STRESS", "CRISIS") else []) + (["SUPER_LONG_SUPPLY_AHEAD"] if supply_ahead else [])
    tl = "NONE" if reg == "NO DATA" else "GREEN" if reg == "INJECTION" else "RED" if reg == "DRAIN" else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": reg, "flags": flags, "components": CF.to_dict(),
               "detail": "flow %s (Z %s) · 5d %s · 20d %s (%s) · FEFSA/py %s · BTC super-long %s" % (fv, zv, D["fiscal_flow_5d_cum"]["value"], D["fiscal_flow_20d_cum"]["value"], sb["signal"],
                                                                                            D["fx_intervention_suspect"]["fefsa_receipts_vs_prior_year"], D["bid_to_cover_superlong"]["value"]), "alerts": alerts}
    hd = [d for d, _ in S.tail(tf, 120)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("treasury_funds_daily", tf), ("fiscal_flow_5d_cum", c5), ("fiscal_flow_20d_cum", c20), ("fiscal_flow_zscore", z))},
               "monthly": {"dates": [d for d, _ in S.tail(raw["taxes_monthly"], 24)],
                           "rows": {k: [dict(raw[k]).get(d) for d, _ in S.tail(raw["taxes_monthly"], 24)] for k in ("taxes_monthly", "pension_payments_monthly", "fefsa_receipts_monthly", "jgb_issued_monthly_mof", "tbills_net_monthly_mof", "net_fiscal_payments_monthly", "fx_factor_monthly")}},
               "auctions": _auction_table(data, 30),
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": reg, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "fiscal", cfg, b, E, D, signals, history)


def _auction_table(data: dict, n: int) -> List[dict]:
    """Last n JGB coupon auctions (all tenors) with bid-to-cover, yield at lowest accepted, average yield and tail."""
    rows: Dict[Tuple[str, str], dict] = {}
    for t in ("2y", "5y", "10y", "20y", "30y", "40y"):
        for pref, key in (("btc_", "btc"), ("hy_", "hy"), ("avgy_", "avg_yield"), ("tail_", "tail_bp")):
            for d, v in S.clean(data.get(pref + t, [])):
                rows.setdefault((d, t), {"date": d, "tenor": t})[key] = v
    return sorted(rows.values(), key=lambda r: (r["date"], r["tenor"]))[-n:]


# ═══════════════════════ 3 · BANKING TRANSMISSION (MD13, MD02, Accounts, MD08) ═══════════════════════
def build_banking(cfg: dict, data: Dict[str, Series], rates_block: Optional[dict] = None, prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["banking"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E, raw = _entries(cfg, "banking", data, MAP_BK, unit, pl, {})
    D: Dict[str, dict] = {}
    lt, dep, m2, m1, mb = raw["loans_total"], raw["deposits_total"], raw["m2"], raw["m1"], raw["monetary_base_monthly"]

    def _yoy(s: Series) -> Series:
        return S.clean([(s[i][0], round((s[i][1] / s[i - 12][1] - 1) * 100, 2)) for i in range(12, len(s)) if s[i - 12][1]])
    D["loans_mom_pct"] = entry("loans_mom_pct", S.pct_change_series(lt), "Loans m/m %", "monthly", "%", cfg, status="fresh" if lt else "unavailable", z_window=24)
    ly = _yoy(lt)
    D["loans_yoy_pct_calc"] = entry("loans_yoy_pct_calc", ly, "Loans y/y % (calculated, all surveyed banks)", "monthly", "%", cfg, status="fresh" if ly else "unavailable",
                                    spec=dict(th.get("loans_yoy_pct", {}), direction="low_is_risk"), prev_level=pl.get("loans_yoy_pct_calc"), z_window=24)
    D["deposits_yoy_pct"] = entry("deposits_yoy_pct", _yoy(dep), "Deposits + CDs y/y %", "monthly", "%", cfg, status="fresh" if dep else "unavailable", z_window=24)
    D["m2_yoy_pct"] = entry("m2_yoy_pct", _yoy(m2), "M2 y/y %", "monthly", "%", cfg, status="fresh" if m2 else "unavailable", spec=dict(th.get("m2_yoy_pct", {}), direction="low_is_risk"),
                            prev_level=pl.get("m2_yoy_pct"), z_window=24)
    D["m1_yoy_pct"] = entry("m1_yoy_pct", _yoy(m1), "M1 y/y %", "monthly", "%", cfg, status="fresh" if m1 else "unavailable", z_window=24)
    D["loan_to_deposit"] = entry("loan_to_deposit", S.merge_series(lt, dep, lambda a, c: round(a / c, 4) if c else None), "Loans / deposits", "monthly", "ratio", cfg, status="fresh" if lt and dep else "unavailable", z_window=24)
    D["money_multiplier"] = entry("money_multiplier", S.merge_series(m2, mb, lambda a, c: round(a / c, 3) if c else None), "M2 / monetary base (display)", "monthly", "x", cfg, status="fresh" if m2 and mb else "unavailable", z_window=24)
    D["money_multiplier"]["display_only"] = True
    imp = [(d, v) for d, v in S.rolling_zscore(S.diff_series(raw["loans_yoy_pct"]), 36) if v is not None]
    D["credit_impulse"] = entry("credit_impulse", imp, "Credit impulse = Z of Δ(loans y/y)", "monthly", "σ", cfg, status="fresh" if imp else "unavailable", z_window=24)
    ci = D["credit_impulse"]["value"]
    tci = th.get("credit_impulse", {})
    if ci is not None:
        D["credit_impulse"]["level"] = "STRESS" if ci <= tci.get("red_below", -1.0) else "SAFE"
    fb, allr = S.clean(data.get("MACAB1043", [])), S.clean(data.get("MACAB1183", []))
    share = S.merge_series(fb, allr, lambda a, c: round(a / c, 4) if c else None)
    D["foreign_banks_excess_share"] = entry("foreign_banks_excess_share", share, "Foreign banks' share of reserve balances (funding canary)", "monthly", "ratio", cfg, status="fresh" if share else "unavailable",
                                            spec=dict(th.get("foreign_banks_excess_share", {}), direction="low_is_risk"), prev_level=pl.get("foreign_banks_excess_share"), z_window=24,
                                            equivalence_note=b["derived"]["foreign_banks_excess_share"]["note"])
    keys = ["loans_mom_pct", "loans_yoy_pct_calc", "deposits_yoy_pct", "m2_yoy_pct", "m1_yoy_pct"]
    valid = [k for k in keys if D[k]["value"] is not None]
    improving = sum(1 for k in valid if (D[k]["change_abs"] or 0) > 0)
    weak = sum(1 for k in valid if (D[k]["zscore"] is not None and D[k]["zscore"] <= -1))
    if ci is not None:
        valid.append("credit_impulse")
        improving += 1 if ci >= tci.get("green_above", 0.5) else 0
        weak += 1 if ci <= tci.get("red_below", -1.0) else 0
    if len(valid) < 3:
        sig, tl, score = "NO SIGNAL", "NONE", 0.0
    elif weak >= 3:
        sig, tl, score = "RED", "RED", -1.5
    elif improving >= 3:
        sig, tl, score = "GREEN", "GREEN", 1.0
    else:
        sig, tl, score = "YELLOW", "YELLOW", 0.0
    D["transmission_signal"] = {"label": "Transmission signal", "value": None, "signal": sig, "status": "fresh" if valid else "unavailable", "date": E["loans_total"]["date"],
                                "rule": th.get("score_rule", ""), "valid_series": len(valid)}
    flags = ["FOREIGN_BANK_YEN_SHORT"] if D["foreign_banks_excess_share"].get("level") in ("WATCH", "STRESS", "CRISIS") else []
    alerts = [_alert("loans_yoy_pct_calc", D["loans_yoy_pct_calc"], "loan growth below p20 (10y) = transmission weakening"),
              _alert("m2_yoy_pct", D["m2_yoy_pct"], "M2 growth below p20"),
              _alert("foreign_banks_excess_share", D["foreign_banks_excess_share"], "foreign banks short of yen reserves — confirm with TONA/TRR")]
    signals = {"traffic_light": tl, "score": score, "label": sig, "flags": flags,
               "detail": "%d series valid · %d improving / %d weak · loans y/y %s · M2 y/y %s · foreign-bank share %s" % (len(valid), improving, weak, E["loans_yoy_pct"]["value"], D["m2_yoy_pct"]["value"], D["foreign_banks_excess_share"]["value"]), "alerts": alerts}
    hd = [d for d, _ in S.tail(lt, 36)]
    history = {"dates": hd, "rows": {k: [dict(raw[k]).get(d) for d in hd] for k in ("loans_total", "loans_yoy_pct", "deposits_total", "m2", "m1", "monetary_base_monthly")},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": sig, "score": score}] if hd else []))[-36:]}
    return _base(cfg["currency"], "banking", cfg, b, E, D, signals, history)


# ═══════════════════════ 4 · RATES — TONA vs IOER, Tokyo Repo Rate, JGB curve ═══════════════════════
def build_rates(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["rates"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    E, raw = _entries(cfg, "rates", data, MAP_RT, "%", pl, {})
    for k in ("call_1w", "call_1m", "call_3m", "collateralized_on", "call_market_outstanding"):
        if raw[k] and E[k]["status"] == "stale":
            E[k]["status"] = "proxy"  # fcall snapshot history builds up run by run
    tona, th_, tl_ = raw["tona"], raw["tona_high"], raw["tona_low"]
    # BoJ API lags 2 business days; the fcall summary (T-1) carries the same uncollateralized O/N average/max/min → splice the newest sessions
    spliced = 0
    for key_, fk in (("tona", "on_unc_same_avg"), ("tona_high", "on_unc_same_max"), ("tona_low", "on_unc_same_min")):
        base_, extra = raw[key_], S.clean(data.get(fk, []))
        last = base_[-1][0] if base_ else "0000-00-00"
        add = [(d, v) for d, v in extra if d > last]
        if add:
            raw[key_] = S.clean(base_ + add)
            spliced = max(spliced, len(add))
            E[key_] = entry(key_, raw[key_], E[key_]["label"], "daily", "%", cfg, E[key_].get("source_id"), E[key_].get("usd_analog"), z_window=30)
            E[key_]["equivalence_note"] = "latest %d session(s) from the BoJ call-market summary (fcall, T-1); API value (T+2) replaces them when published" % len(add)
    tona, th_, tl_ = raw["tona"], raw["tona_high"], raw["tona_low"]
    ioer = _ffill(raw["ioer"], tona)
    blr = _ffill(raw["basic_loan_rate"], tona)
    trr = raw["trr_on"]
    D: Dict[str, dict] = {}
    sp = S.merge_series(tona, ioer, lambda a, c: round((a - c) * 100, 2))
    D["tona_minus_ioer_bps"] = entry("tona_minus_ioer_bps", sp, "TONA − IOER (bps; floor spread)", "daily", "bps", cfg, usd_analog="EFFR − IORB", status="fresh" if sp else "unavailable",
                                     spec=_spec(th, "tona_minus_ioer_bps"), prev_level=pl.get("tona_minus_ioer_bps"), z_window=30, equivalence_note=b["derived"]["tona_minus_ioer_bps"]["note"])
    absr = th["tona_minus_ioer_bps"]["secondary_absolute"]
    pers = _persistent_level([v for _, v in sp], absr)
    D["tona_minus_ioer_bps"]["percentile_level"] = D["tona_minus_ioer_bps"]["level"]
    # percentile alone caps at WATCH (a hike day = p99); absolute binding for STRESS/CRISIS
    if pers in ("STRESS", "CRISIS"):
        D["tona_minus_ioer_bps"]["level"] = pers
    else:
        D["tona_minus_ioer_bps"]["level"] = "WATCH" if (pers == "WATCH" or D["tona_minus_ioer_bps"]["level"] in ("WATCH", "STRESS", "CRISIS")) else "SAFE"
    last3 = [v for _, v in sp[-3:]]
    hi_sp = S.merge_series(th_, ioer, lambda a, c: round((a - c) * 100, 2))
    hi3 = [v for _, v in hi_sp[-3:]]
    D["tona_minus_ioer_bps"]["friction_confirmed"] = bool((len(last3) == 3 and all(v >= absr["watch"] for v in last3)) or (len(hi3) == 3 and all(v >= th["tona_high_minus_ioer_bps"]["watch_above"] for v in hi3)))
    last5 = [v for _, v in sp[-5:]]
    D["tona_minus_ioer_bps"]["floor_leak"] = bool(len(last5) == 5 and all(v <= absr.get("low_side_excess", -15) for v in last5))
    D["tona_minus_policy_bps"] = dict(D["tona_minus_ioer_bps"], label="alias: TONA − policy target (= IOER while the two coincide)")
    D["overnight_minus_deposit_bps"] = dict(D["tona_minus_ioer_bps"], label="alias (regime key)")
    D["tona_high_minus_ioer_bps"] = entry("tona_high_minus_ioer_bps", hi_sp, "TONA daily high − IOER (bps; late-day squeeze)", "daily", "bps", cfg, status="fresh" if hi_sp else "unavailable", z_window=30)
    hv = D["tona_high_minus_ioer_bps"]["value"]
    tth = th["tona_high_minus_ioer_bps"]
    if hv is not None:
        lvl_h = "STRESS" if hv >= tth["stress_above"] else "WATCH" if hv >= tth["watch_above"] else "SAFE"
        if lvl_h != "SAFE" and not (len(hi3) == 3 and all(v >= tth["watch_above"] for v in hi3)):
            lvl_h = "WATCH" if lvl_h == "STRESS" else "SAFE"  # one-day spikes (period end) do not escalate
        D["tona_high_minus_ioer_bps"]["level"] = lvl_h
    rng = S.merge_series(th_, tl_, lambda a, c: round((a - c) * 100, 2))
    D["tona_range_bps"] = entry("tona_range_bps", rng, "TONA high − low (bps)", "daily", "bps", cfg, status="fresh" if rng else "unavailable", z_window=30)
    bp = S.merge_series(S.merge_series(tona, ioer, lambda a, c: a - c), S.merge_series(blr, ioer, lambda a, c: a - c), lambda x, y: round(x / y, 3) if y else None)
    D["band_position"] = entry("band_position", bp, "Position in the corridor (0 = IOER floor, 1 = basic loan rate ceiling; normal ≈ −0.1)", "daily", "ratio", cfg, status="fresh" if bp else "unavailable", z_window=30)
    bv = D["band_position"]["value"]
    if bv is not None:
        D["band_position"]["level"] = "STRESS" if bv > th["band_position"]["stress_above"] else "WATCH" if bv > th["band_position"]["watch_above"] else "SAFE"
    gc = S.merge_series(trr, ioer, lambda a, c: round((a - c) * 100, 2))
    D["gc_minus_ioer_bps"] = entry("gc_minus_ioer_bps", gc, "Tokyo Repo Rate O/N − IOER (bps; GC vs floor)", "daily", "bps", cfg, usd_analog="SOFR − IORB", status="fresh" if gc else "unavailable", z_window=30,
                                   equivalence_note=b["derived"]["gc_minus_ioer_bps"]["note"])
    tg = th["gc_minus_ioer_bps"]
    D["gc_minus_ioer_bps"]["level"] = _persistent_level([v for _, v in gc], {"watch": tg["watch_above"], "stress": tg["stress_above"], "crisis": tg["crisis_above"]}) if gc else "NO DATA"
    gt = S.merge_series(trr, tona, lambda a, c: round((a - c) * 100, 2))
    D["gc_minus_tona_bps"] = entry("gc_minus_tona_bps", gt, "Tokyo Repo Rate O/N − TONA (bps)", "daily", "bps", cfg, status="fresh" if gt else "unavailable", spec=_spec(th, "gc_minus_tona_bps"),
                                   prev_level=pl.get("gc_minus_tona_bps"), z_window=30, equivalence_note=b["derived"]["gc_minus_tona_bps"]["note"])
    t3 = S.merge_series(raw["trr_3m"], ioer, lambda a, c: round((a - c) * 100, 2))
    D["trr_3m_minus_ioer_bps"] = entry("trr_3m_minus_ioer_bps", t3, "Tokyo Repo Rate 3M − IOER (bps; term premium / hike pricing)", "daily", "bps", cfg, status="fresh" if t3 else "unavailable",
                                       spec=_spec(th, "trr_3m_minus_ioer_bps"), prev_level=pl.get("trr_3m_minus_ioer_bps"), z_window=30)
    _cap_watch(D["trr_3m_minus_ioer_bps"], th["trr_3m_minus_ioer_bps"]["secondary_absolute"])
    c1 = S.merge_series(raw["call_1m"], _ffill(raw["ioer"], raw["call_1m"]), lambda a, c: round((a - c) * 100, 2))
    D["call_1m_minus_policy_bps"] = entry("call_1m_minus_policy_bps", c1, "Uncollateralized call 1M − IOER (bps; thin)", "daily", "bps", cfg, status="proxy" if c1 else "unavailable",
                                          spec=_spec(th, "call_1m_minus_policy_bps"), prev_level=pl.get("call_1m_minus_policy_bps"), z_window=30)
    _cap_watch(D["call_1m_minus_policy_bps"], th["call_1m_minus_policy_bps"]["secondary_absolute"])
    cu = S.merge_series(raw["collateralized_on"], tona, lambda a, c: round((a - c) * 100, 2))
    D["collateralized_minus_uncollateralized_bps"] = entry("collateralized_minus_uncollateralized_bps", cu, "BoJ collateralized call − TONA (bps; display, thin)", "daily", "bps", cfg, status="proxy" if cu else "unavailable", z_window=30)
    D["collateralized_minus_uncollateralized_bps"]["display_only"] = True
    y2, y5, y10, y20, y30, y40 = raw["jgb_2y"], raw["jgb_5y"], raw["jgb_10y"], raw["jgb_20y"], raw["jgb_30y"], raw["jgb_40y"]

    def _curve(key: str, a: Series, c: Series, label: str, spec_key: Optional[str] = None, absolute: Optional[dict] = None) -> None:
        s_ = S.merge_series(a, c, lambda x, y: round((x - y) * 100, 2))
        D[key] = entry(key, s_, label, "daily", "bps", cfg, status="fresh" if s_ else "unavailable", spec=_spec(th, spec_key) if spec_key else None, prev_level=pl.get(key), z_window=30)
        v = D[key]["value"]
        if absolute and v is not None:
            D[key]["level"] = "CRISIS" if v < absolute["deep_inversion_below"] else "STRESS" if v < absolute["inverted_below"] else "WATCH" if v < absolute["flat_below"] else "SAFE"
            D[key]["curve_state"] = {"CRISIS": "DEEP INVERSION", "STRESS": "INVERTED", "WATCH": "FLAT"}.get(D[key]["level"], "STEEPENING")
    _curve("curve_10y_2y_bps", y10, y2, "JGB 10Y − 2Y (bps)", absolute=th["curve_10y_2y_bps"])
    _curve("curve_20y_10y_bps", y20, y10, "JGB 20Y − 10Y (bps; QT supply gauge, banks' duration sink)", "curve_20y_10y_bps")
    _curve("curve_30y_10y_bps", y30, y10, "JGB 30Y − 10Y (bps; super-long stress)", "curve_30y_10y_bps")
    _curve("curve_40y_30y_bps", y40, y30, "JGB 40Y − 30Y (bps; display)")
    D["curve_40y_30y_bps"]["display_only"] = True
    p2 = S.merge_series(_ffill(raw["policy_rate"], y2), y2, lambda a, c: round((a - c) * 100, 2))
    D["policy_minus_2y_bps"] = entry("policy_minus_2y_bps", p2, "Policy target − JGB 2Y (bps; negative = market prices hikes)", "daily", "bps", cfg, usd_analog="FF − 2Y", status="fresh" if p2 else "unavailable", z_window=30)
    pv = D["policy_minus_2y_bps"]["value"]
    tp = th["policy_minus_2y_bps"]
    if pv is not None:
        D["policy_minus_2y_bps"]["level"] = "STRESS" if pv > tp["tight_above"] else "WATCH" if pv > tp["normal_below"] else "SAFE"
    ch5 = S.diff_series(y10, 5, 100.0)
    D["jgb_10y_5d_change_bps"] = entry("jgb_10y_5d_change_bps", ch5, "JGB 10Y Δ 5 sessions (bps; BoJ 'rapid rise' zone)", "daily", "bps", cfg, status="fresh" if ch5 else "unavailable", z_window=30)
    cv5 = D["jgb_10y_5d_change_bps"]["value"]
    t5 = th["jgb_10y_5d_change_bps"]
    if cv5 is not None:
        D["jgb_10y_5d_change_bps"]["level"] = "STRESS" if cv5 >= t5["stress_above"] else "WATCH" if cv5 >= t5["watch_above"] else "SAFE"
    D["friction_confirmed"] = {"label": "friction_confirmed", "value": D["tona_minus_ioer_bps"]["friction_confirmed"], "status": "fresh" if sp else "unavailable", "date": D["tona_minus_ioer_bps"]["date"], "note": b["derived"]["friction_confirmed"]["formula"]}
    D["floor_leak"] = {"label": "FLOOR_LEAK", "value": D["tona_minus_ioer_bps"]["floor_leak"], "status": "fresh" if sp else "unavailable", "date": D["tona_minus_ioer_bps"]["date"], "note": b["derived"]["floor_leak"]["note"]}
    lvl = D["tona_minus_ioer_bps"]["level"]
    gl = D["gc_minus_ioer_bps"]["level"]
    comps = [{"SAFE": 0.25, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}.get(lvl, 0.0),
             {"SAFE": 0.25, "WATCH": -0.5, "STRESS": -1.0, "CRISIS": -1.5}.get(gl, 0.0),
             {"SAFE": 0.25, "WATCH": 0.0, "STRESS": -0.5, "CRISIS": -1.0}.get(D["curve_10y_2y_bps"].get("level"), 0.0),
             {"SAFE": 0.0, "WATCH": -0.25, "STRESS": -0.5}.get(D["curve_20y_10y_bps"].get("level"), 0.0),
             {"SAFE": 0.0, "WATCH": -0.25, "STRESS": -0.5}.get(D["jgb_10y_5d_change_bps"].get("level"), 0.0)]
    score = round(max(-2.0, min(2.0, sum(comps))), 2)
    flags: List[str] = []
    if D["tona_minus_ioer_bps"]["floor_leak"]:
        flags.append("FLOOR_LEAK")
    if gl in ("WATCH", "STRESS", "CRISIS"):
        flags.append("GC_ABOVE_FLOOR")
    if D["curve_30y_10y_bps"].get("level") in ("STRESS", "CRISIS"):
        flags.append("SUPER_LONG_STRESS")
    label = "NO SIGNAL" if not sp else "FUNDING STRESS" if lvl in ("STRESS", "CRISIS") or gl in ("STRESS", "CRISIS") else "FLOOR FRICTION" if lvl == "WATCH" or gl == "WATCH" else "CORRIDOR CALM"
    tl = "NONE" if not sp else "RED" if label == "FUNDING STRESS" else "YELLOW" if label == "FLOOR FRICTION" or D["curve_20y_10y_bps"].get("level") in ("STRESS", "CRISIS") else "GREEN"
    alerts = [_alert("tona_minus_ioer_bps", D["tona_minus_ioer_bps"], "0 = at the floor (WATCH after 3 sessions); ≥ +5 STRESS; ≥ +15 CRISIS; ceiling +25"),
              _alert("tona_high_minus_ioer_bps", D["tona_high_minus_ioer_bps"], "daily high ≥ IOER + 5 three sessions = squeeze"),
              _alert("gc_minus_ioer_bps", D["gc_minus_ioer_bps"], "GC repo ≥ IOER + 3 persistent = collateral/cash squeeze"),
              _alert("trr_3m_minus_ioer_bps", D["trr_3m_minus_ioer_bps"], "embeds hike expectations; absolute 30/45/70 binding"),
              _alert("curve_20y_10y_bps", D["curve_20y_10y_bps"], "p90/p97 = QT supply stress"),
              _alert("curve_30y_10y_bps", D["curve_30y_10y_bps"], "super-long stress (lifers, QT)"),
              _alert("jgb_10y_5d_change_bps", D["jgb_10y_5d_change_bps"], "≥ 15 bp in 5 sessions = BoJ nimble-response zone")]
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags,
               "detail": "TONA−IOER %s bps (%s) · high−IOER %s · GC−IOER %s (%s) · TRR3M−IOER %s · 10Y−2Y %s · 20Y−10Y %s (%s) · 30Y−10Y %s · policy−2Y %s" % (
                   D["tona_minus_ioer_bps"]["value"], lvl, hv, D["gc_minus_ioer_bps"]["value"], gl, D["trr_3m_minus_ioer_bps"]["value"], D["curve_10y_2y_bps"]["value"],
                   D["curve_20y_10y_bps"]["value"], D["curve_20y_10y_bps"].get("level"), D["curve_30y_10y_bps"]["value"], pv), "alerts": alerts}
    hd = [d for d, _ in S.tail(sp, 120)]
    rows = {k: [dict(v).get(d) for d in hd] for k, v in (("tona_minus_ioer_bps", sp), ("tona_high_minus_ioer_bps", hi_sp), ("gc_minus_ioer_bps", gc), ("gc_minus_tona_bps", gt), ("trr_3m_minus_ioer_bps", t3),
                                                        ("band_position", bp), ("tona", tona), ("ioer", ioer), ("trr_on", trr), ("jgb_2y", y2), ("jgb_10y", y10), ("jgb_30y", y30),
                                                        ("curve_10y_2y_bps", S.merge_series(y10, y2, lambda x, y: round((x - y) * 100, 2))), ("curve_20y_10y_bps", S.merge_series(y20, y10, lambda x, y: round((x - y) * 100, 2))),
                                                        ("curve_30y_10y_bps", S.merge_series(y30, y10, lambda x, y: round((x - y) * 100, 2))))}
    history = {"dates": hd, "rows": rows, "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": label, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "rates", cfg, b, E, D, signals, history)


def _cap_watch(e: dict, absr: dict) -> None:
    """percentile alone may only reach WATCH; STRESS/CRISIS need the absolute anchor (hike expectations embed in term spreads)."""
    v = e.get("value")
    if v is None:
        return
    a_lvl = "CRISIS" if (absr.get("crisis") is not None and v >= absr["crisis"]) else "STRESS" if v >= absr["stress"] else "WATCH" if v >= absr["watch"] else "SAFE"
    p_lvl = e.get("level", "SAFE")
    e["percentile_level"] = p_lvl
    e["level"] = a_lvl if a_lvl in ("STRESS", "CRISIS") else ("WATCH" if (p_lvl in ("WATCH", "STRESS", "CRISIS") or a_lvl == "WATCH") else "SAFE")
    th = e.get("thresholds") or {}
    lv = dict(th.get("levels") or {})
    for k in ("watch", "stress", "crisis"):
        if absr.get(k) is not None:
            lv[k.upper() + "_abs"] = absr[k]
    e["thresholds"] = dict(th, levels=lv, method=th.get("method") or "percentile+absolute")
