"""AUD block builders (RBA ample-reserves, demand-driven framework). Four layers, same schema as CAD/GBP:
  1 central bank  — A3 ES balances DAILY (total, surplus, standing facility at +25, OMO repos) + A1 weekly balance sheet;
                    reserves vs the RBA demand estimate ($70–100bn, Jacobs 2026-08-25); Net Liquidity = assets − government deposits
  2 fiscal        — Australian Government deposits at the RBA (weekly, TGA analogue): flow = −Δ, 4-week cumulative, Z; AOFM events pending
  3 banking       — D1 growth rates (credit ex-financial, housing, business, personal, M3, broad money) + D3 levels; confirmation layer
  4 rates         — AONIA − target (anchored at target since OMO at +10), band position in the −10/+25 corridor, BBSW 3M − target,
                    cash-market dispersion, AGS 10Y − 2Y (F2 weekly file)
Config: config/aud.json v0.2.x (triangulated 2026-09-08)."""
from __future__ import annotations
from typing import Dict, List, Optional
from . import series as S
from .series import Series
from .thresholds import classify, signal_band
from .scoring import Comps
from .blocks import entry, _prev_levels, _alert, _health, _base as _base0
from .blocks_gbp import _ser, _persistent_level


def _base(ccy, block, cfg, bcfg, E, D, signals, history):
    out = _base0(ccy, block, cfg, bcfg, E, D, signals, history)
    wired = {k: e for k, e in E.items() if bcfg["series"].get(k, {}).get("id")}
    out["source_health"] = _health(wired, len(wired))
    out["source_health"]["series_pending"] = len(E) - len(wired)
    return out


def _entries(cfg: dict, block: str, data: Dict[str, Series], unit: str, pl: Dict[str, str], th: dict, zero_if_empty=()) -> Dict[str, dict]:
    E: Dict[str, dict] = {}
    for key, sc in cfg["blocks"][block]["series"].items():
        ser = _ser(data, sc)
        freq = sc.get("freq", "weekly")
        if key in zero_if_empty and sc.get("id") and not ser:
            ser = []  # column present but empty = zero usage; handled below
        st = None if sc.get("id") else "unavailable"
        e = entry(key, ser, sc["label"], "daily" if freq.startswith("daily") else "weekly" if freq.startswith("weekly") else "monthly" if freq.startswith("monthly") else "weekly",
                  sc.get("unit", unit), cfg, sc.get("id"), sc.get("usd_analog"), status=st, spec=th.get(key), prev_level=pl.get(key),
                  z_window=30 if freq.startswith("daily") else 26 if freq.startswith("weekly") else 12)
        if key in zero_if_empty and sc.get("id"):
            # A3 leaves the cell empty when a facility is unused: no row on the latest ES date means 0, not 'stale last use'
            latest = (data.get("AESAT") or [(None, None)])[-1][0]
            if latest and (not ser or ser[-1][0] < latest):
                e.update({"status": "fresh", "value": 0.0, "prev_value": ser[-1][1] if ser else None, "prev_date": ser[-1][0] if ser else None, "change_abs": None, "change_pct": None,
                          "level": "SAFE", "confidence": 100, "date": latest, "age_days": 0,
                          "equivalence_note": ("no usage on %s (last use %s = %s)" % (latest, ser[-1][0], ser[-1][1])) if ser else "column empty in A3 = no usage (0)"})
        if sc.get("freq") == "event" and ser:
            e["status"] = "fresh"
        if sc.get("display_only"):
            e["display_only"] = True
        if sc.get("note") or sc.get("role"):
            e["equivalence_note"] = sc.get("note") or sc.get("role")
        if not sc.get("id"):
            e["status"] = "unavailable"
            e["equivalence_note"] = sc.get("role") or sc.get("source") or sc.get("label")
        E[key] = e
    return E


# ═══════════════════════ 1 · CENTRAL BANK LIQUIDITY (A3 daily + A1 weekly) ═══════════════════════
def build_central_bank(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["central_bank"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "central_bank", data, unit, pl, th, zero_if_empty=("sf_repos_surplus_rate", "sf_repos_margin", "omo_repos_absorb"))
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    es, sur, res, ga, ta = raw["es_balances_daily"], raw["es_surplus_daily"], raw["reserves"], raw["government_account"], raw["total_assets"]
    # apply the RBA demand-range threshold to ES total daily AND weekly reserves
    for key, ser in (("es_balances_daily", es), ("reserves", res)):
        if ser and E[key]["value"] is not None:
            c = classify(E[key]["value"], ser, th["reserves"], "daily" if key.startswith("es") else "weekly", pl.get(key))
            E[key].update({"level": c["level"], "thresholds": c.get("thresholds", {}), "in_range": c.get("in_range"), "above_range": c.get("above_range")})
    D: Dict[str, dict] = {}
    nl = S.merge_series(ta, ga, lambda a, g: a - g)
    D["net_liquidity"] = entry("net_liquidity", nl, "Balance-sheet liquidity = Total assets − Australian Government deposits", "weekly", unit, cfg, usd_analog="WALCL − TGA",
                               status="fresh" if nl else "unavailable", equivalence_note=b["derived"]["net_liquidity"]["note"])
    nlw = S.pct_change_series(nl)
    D["net_liquidity_wow_pct"] = entry("net_liquidity_wow_pct", nlw, "Balance-sheet liquidity Δ% w/w", "weekly", "%", cfg, status="fresh" if nlw else "unavailable")
    sb = signal_band(D["net_liquidity_wow_pct"]["value"], nlw, th["net_liquidity_wow_pct"], "weekly")
    D["net_liquidity_wow_pct"].update({"signal": sb["signal"], "percentile": sb["percentile"], "thresholds": sb.get("thresholds", {})})
    D["reserves_wow_pct"] = entry("reserves_wow_pct", S.pct_change_series(res), "ES balances Δ% w/w (A1)", "weekly", "%", cfg, status="fresh" if res else "unavailable",
                                  spec=th.get("reserves_wow_pct"), prev_level=pl.get("reserves_wow_pct"))
    dod = S.diff_series(es)
    D["es_balances_dod"] = entry("es_balances_dod", dod, "ES balances Δ day/day (daily reserve impulse)", "daily", unit, cfg, usd_analog="Δ WRESBAL daily", status="fresh" if dod else "unavailable",
                                 spec=th.get("es_balances_dod"), prev_level=pl.get("es_balances_dod"), z_window=30)
    D["es_surplus_share"] = entry("es_surplus_share", S.merge_series(sur, es, lambda a, t: round(a / t, 4) if t else None), "ES surplus / ES total (slack share)", "daily", "ratio", cfg,
                                  status="fresh" if sur else "unavailable", z_window=30)
    omo = S.add_series(raw["omo_reverse_repos"], raw["omo_triparty"]) if raw.get("omo_triparty") else raw["omo_reverse_repos"]
    D["omo_outstanding"] = entry("omo_outstanding", omo, "OMO reverse repos outstanding (bilateral + triparty) — reserves supplied on demand", "daily", unit, cfg,
                                 status="fresh" if omo else "unavailable", z_window=30, equivalence_note="RBA Aug-2026: $20–30bn; quantity is demand, not a policy signal")
    share = S.merge_series(omo, es, lambda a, t: round(a / t, 4) if t else None)
    D["omo_share_of_es"] = entry("omo_share_of_es", share, "OMO-supplied share of ES", "daily", "ratio", cfg, status="fresh" if share else "unavailable",
                                 spec=th.get("omo_share_of_es"), prev_level=pl.get("omo_share_of_es"), z_window=30, equivalence_note=b["derived"]["omo_share_of_es"]["note"])
    D["omo_takeup_weekly"] = {"label": "OMO weekly take-up (allotted)", "value": None, "status": "unavailable", "date": None, "unit": unit, "level": "NO DATA",
                              "equivalence_note": "Phase 2b parser of a3-omo-repo-transaction-details; OMO_TAKEUP_SURGE flag"}
    cd = [(d, -v) for d, v in S.diff_series(raw["notes_in_circulation"])]
    D["currency_drain"] = entry("currency_drain", cd, "Currency drain (−Δ notes on issue, autonomous)", "weekly", unit, cfg, status="fresh" if cd else "unavailable",
                                equivalence_note="Outside money: not subtracted from balance-sheet liquidity (cross-currency rule)")
    rng = th["reserves"]["primary_absolute"]["boc_target_range"]
    dist = [(d, v - rng[1]) for d, v in es]
    D["es_vs_demand_ceiling"] = entry("es_vs_demand_ceiling", dist, "ES total − RBA demand estimate ceiling (%d bn)" % (rng[1] // 1000), "daily", unit, cfg, status="fresh" if dist else "unavailable",
                                      equivalence_note="distance to the top of the RBA's $70–100bn demand estimate (Jacobs 2026-08-25)")
    inv = raw["aud_investments"]
    inv13 = [(inv[i][0], round(inv[i][1] - inv[i - 13][1], 1)) for i in range(13, len(inv))]
    D["aud_investments_13w_change"] = entry("aud_investments_13w_change", inv13, "AUD investments Δ 13 weeks (bond-portfolio run-off)", "weekly", unit, cfg, status="fresh" if inv13 else "unavailable")
    ch = D["aud_investments_13w_change"]["value"]
    phase = "RUN_OFF" if ch is not None and ch < -2000 else "STEADY"
    D["balance_sheet_phase"] = {"label": "Balance-sheet phase", "value": None, "phase": phase, "status": "fresh", "date": E["aud_investments"]["date"],
                                "note": "passive run-off of the bond portfolio; reserves replaced on demand via weekly full-allotment OMO (target + 10 bp)"}
    sfm = E["sf_repos_margin"]["value"] or 0.0
    flags: List[str] = []
    if sfm > 0:
        flags.append("STANDING_FACILITY_USED")
    if D["omo_share_of_es"].get("level") in ("WATCH", "STRESS", "CRISIS"):
        flags.append("REPO_DEPENDENCE_ELEVATED")
    # score: ES vs range, daily impulse, balance-sheet Δ, emergency
    lvl = E["es_balances_daily"]["level"]
    above = E["es_balances_daily"].get("above_range")
    C = Comps(cfg, "mean2")
    C.level("es_vs_range", {"SAFE": 0.75 if above else 0.25, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}.get(lvl, 0.0))
    C.flow("es_dod_level", {"SAFE": 0.25, "WATCH": -0.5, "STRESS": -1.0, "CRISIS": -1.5}.get(D["es_balances_dod"].get("level"), 0.0))
    C.flow("balance_sheet_band", 1.0 if sb["signal"] == "RISK_ON" else -1.0 if sb["signal"] == "RISK_OFF" else 0.0)
    if sfm > 0:
        C.event("standing_facility", -2.0)
    score = C.score()
    alerts = [_alert("es_balances_daily", E["es_balances_daily"], "below the RBA demand range 70–100bn = scarcity zone (price must confirm)"),
              _alert("sf_repos_margin", E["sf_repos_margin"], "standing facility at +25 bp > 0 = a bank paid the ceiling"),
              _alert("es_balances_dod", D["es_balances_dod"], "daily ES drop below p10 = drain day (tax/issuance/AOFM)"),
              _alert("omo_share_of_es", D["omo_share_of_es"], "informational unless AONIA > target")]
    label = "NO SIGNAL" if not es else ("INJECTION" if score >= 0.5 else "DRAIN" if score <= -0.5 else "NEUTRAL")
    tl = "NONE" if not es else "GREEN" if score >= 0.5 else "RED" if score <= -0.75 else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags, "components": C.to_dict(),
               "detail": "ES %s (%s demand range) · ΔES d/d %s · BS liq %s · OMO/ES %s · SF+25 %s" % (lvl, "above" if above else "inside" if E["es_balances_daily"].get("in_range") else "below",
                                                                                                   D["es_balances_dod"]["value"], sb["signal"], D["omo_share_of_es"]["value"], sfm), "alerts": alerts}
    hd = [d for d, _ in S.tail(es, 90)]
    rows = {k: [dict(v).get(d) for d in hd] for k, v in (("es_balances_daily", es), ("es_surplus_daily", sur), ("omo_outstanding", omo), ("es_balances_dod", dod), ("omo_share_of_es", share))}
    hw = [d for d, _ in S.tail(res, 52)]
    rows_w = {k: [dict(v).get(d) for d in hw] for k, v in (("reserves", res), ("government_account", ga), ("total_assets", ta), ("net_liquidity", nl), ("net_liquidity_wow_pct", nlw), ("aud_investments", inv))}
    history = {"dates": hd, "rows": rows, "weekly": {"dates": hw, "rows": rows_w}, "signal_log": (prev or {}).get("history", {}).get("signal_log", [])[-90:]}
    if hd:
        history["signal_log"] = [x for x in history["signal_log"] if x.get("date") != hd[-1]] + [{"date": hd[-1], "label": label, "score": score, "note": signals["detail"]}]
    return _base(cfg["currency"], "central_bank", cfg, b, E, D, signals, history)


# ═══════════════════════ 2 · TREASURY — GOVERNMENT DEPOSITS AT THE RBA (weekly) + AOFM (pending) ═══════════════════════
def build_fiscal(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["fiscal"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    E = _entries(cfg, "fiscal", data, unit, pl, {})
    ga = _ser(data, b["series"]["government_account"])
    D: Dict[str, dict] = {}
    ff = [(d, -v) for d, v in S.diff_series(ga)]
    D["fiscal_flow_weekly"] = entry("fiscal_flow_weekly", ff, "Fiscal flow = −Δ Government deposits at the RBA (weekly)", "weekly", unit, cfg, usd_analog="−ΔTGA",
                                    status="fresh" if ff else "unavailable", z_window=52, equivalence_note=b["derived"]["fiscal_flow_weekly"]["sign"])
    z = S.rolling_zscore(ff, 52)
    zc = [(d, v) for d, v in z if v is not None]
    D["fiscal_flow_zscore"] = entry("fiscal_flow_zscore", zc, "Fiscal flow Z-score (52 weeks)", "weekly", "σ", cfg, status="fresh" if zc else "unavailable", z_window=52)
    zv = D["fiscal_flow_zscore"]["value"]
    if zv is not None:
        D["fiscal_flow_zscore"]["level"] = "STRESS" if abs(zv) >= 2 else "WATCH" if abs(zv) >= 1 else "SAFE"
    c4 = S.rolling_sum(ff, 4)
    D["fiscal_flow_4w_cum"] = entry("fiscal_flow_4w_cum", c4, "Fiscal flow 4-week cumulative", "weekly", unit, cfg, status="fresh" if c4 else "unavailable", z_window=26)
    sb = signal_band(D["fiscal_flow_4w_cum"]["value"], c4, {"window": "156w", "risk_on_above": "p80", "risk_off_below": "p20"}, "weekly") if c4 else {"signal": "NO DATA", "percentile": None}
    D["fiscal_flow_4w_cum"].update({"signal": sb["signal"], "percentile": sb.get("percentile")})
    fv = D["fiscal_flow_weekly"]["value"]
    big = (fv is not None and abs(fv) >= 15000) or (zv is not None and abs(zv) >= 2)
    D["fiscal_big_week"] = {"label": "FISCAL_BIG_WEEK (|flow| ≥ 15bn or |Z| ≥ 2)", "value": bool(big), "direction": ("DRAIN" if (fv or 0) < 0 else "INJECTION") if big else None,
                            "status": "fresh" if fv is not None else "unavailable", "date": D["fiscal_flow_weekly"]["date"], "note": b["derived"]["fiscal_big_week"]["note"]}
    reg = "NO DATA" if not c4 else "INJECTION" if sb["signal"] == "RISK_ON" else "DRAIN" if sb["signal"] == "RISK_OFF" else "NEUTRAL"
    score = 0.0 if reg == "NO DATA" else round(max(-2.0, min(2.0, (zv or 0.0))), 2)
    CF = Comps(cfg, "sum").flow("fiscal_flow_z", score)
    D["fiscal_regime"] = {"label": "Fiscal regime", "value": None, "regime": reg, "status": "fresh" if c4 else "unavailable", "date": D["fiscal_flow_weekly"]["date"]}
    D["fiscal_regime_score"] = {"label": "Fiscal regime score", "value": score, "range": [-2, 2], "status": "fresh", "date": D["fiscal_flow_weekly"]["date"]}
    D["net_issuance_event"] = {"label": "AOFM tenders net of maturities", "value": None, "status": "unavailable", "date": None, "note": "Phase 3: AOFM XLSX link discovery"}
    D["mmt_note"] = {"label": "MMT note", "value": None, "status": "fresh", "date": None, "text": b["derived"].get("mmt_note", "")}
    alerts = [_alert("fiscal_flow_zscore", D["fiscal_flow_zscore"], "|Z| ≥ 2 = extraordinary weekly flow (tax/issuance/AOFM cash)"),
              {"metric": "fiscal_flow_4w_cum", "level": "WATCH" if reg == "DRAIN" else "SAFE" if reg != "NO DATA" else "NO DATA", "value": D["fiscal_flow_4w_cum"]["value"], "threshold": None,
               "status": D["fiscal_flow_4w_cum"]["status"], "action_hint": "4-week cumulative below p20 = fiscal drain"}]
    tl = "NONE" if reg == "NO DATA" else "GREEN" if reg == "INJECTION" else "RED" if reg == "DRAIN" else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": reg, "flags": ["FISCAL_BIG_WEEK"] if big else [], "components": CF.to_dict(),
               "detail": "flow %s (Z %s) · 4w cum %s (%s) · gov deposits %s" % (fv, zv, D["fiscal_flow_4w_cum"]["value"], sb["signal"], E["government_account"]["value"]), "alerts": alerts}
    hd = [d for d, _ in S.tail(ga, 52)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("government_account", ga), ("fiscal_flow_weekly", ff), ("fiscal_flow_4w_cum", c4), ("fiscal_flow_zscore", zc))},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": reg, "score": score}] if hd else []))[-52:]}
    return _base(cfg["currency"], "fiscal", cfg, b, E, D, signals, history)


# ═══════════════════════ 3 · BANKING TRANSMISSION (D1 growth rates, D3 levels) ═══════════════════════
def build_banking(cfg: dict, data: Dict[str, Series], rates_block: Optional[dict] = None, prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["banking"]
    unit = cfg["units"]["balance_sheet"]
    E = _entries(cfg, "banking", data, "%", {}, {})
    D: Dict[str, dict] = {}
    growth_keys = ["credit_total_mom", "credit_housing_mom", "credit_business_mom", "credit_personal_mom", "m3_mom", "broad_money_yoy"]
    chg: Dict[str, Optional[float]] = {}
    for k in growth_keys:
        ser = _ser(data, b["series"][k])
        e = entry(k + "_z", ser, E[k]["label"], "monthly", "%", cfg, status="fresh" if ser else "unavailable", z_window=24)
        zz = e["zscore"]
        e["level"] = "NO DATA" if not ser else "STRESS" if zz is not None and abs(zz) >= 2 else "WATCH" if zz is not None and abs(zz) >= 1 else "SAFE"
        D[k + "_z"] = e
        chg[k] = e["value"]
    D["credit_business_mom_mom_pct"] = dict(D["credit_business_mom_z"], label="alias: business credit growth (scenario key)")
    D["m3_mom_mom_pct"] = dict(D["m3_mom_z"], label="alias: M3 growth (scenario key)")
    m3 = _ser(data, b["series"]["m3_level"])
    D["m3_yoy_pct"] = entry("m3_yoy_pct", [(m3[i][0], round((m3[i][1] / m3[i - 12][1] - 1) * 100, 2)) for i in range(12, len(m3)) if m3[i - 12][1]], "M3 y/y % (D3)", "monthly", "%", cfg,
                            status="fresh" if len(m3) > 12 else "unavailable", z_window=24)
    valid = [k for k in ("credit_total_mom", "credit_business_mom", "credit_housing_mom", "m3_mom", "credit_personal_mom") if chg.get(k) is not None]
    grn = sum(1 for k in valid if (chg[k] or 0) > 0 and (D[k + "_z"]["zscore"] or 0) >= 0)
    red = sum(1 for k in valid if (D[k + "_z"]["zscore"] is not None and D[k + "_z"]["zscore"] <= -1))
    n_valid = len(valid)
    if n_valid < b.get("signal_rule", {}).get("min_series_valid", 3):
        sig, tl, score = "NO SIGNAL", "NONE", 0.0
    elif red >= 3:
        sig, tl, score = "RED", "RED", -1.5
    elif grn >= 3:
        sig, tl, score = "GREEN", "GREEN", 1.0
    else:
        sig, tl, score = "YELLOW", "YELLOW", 0.0
    D["transmission_signal"] = {"label": "Transmission signal", "value": None, "signal": sig, "status": "fresh" if valid else "unavailable", "date": E["credit_total_mom"]["date"],
                                "rule": b["derived"]["transmission_signal"]["rule"], "valid_series": n_valid}
    alerts = [_alert(k + "_z", D[k + "_z"], "|Z| ≥ 2 extraordinary monthly growth") for k in ("credit_total_mom", "credit_business_mom", "m3_mom")]
    signals = {"traffic_light": tl, "score": score, "label": sig, "flags": [], "detail": "%d/5 series valid · %d strong / %d weak · monthly, ~1-month lag (APRA D2A transition risk)" % (n_valid, grn, red), "alerts": alerts}
    ct = _ser(data, b["series"]["credit_total_mom"])
    hd = [d for d, _ in S.tail(ct, 24)]
    history = {"dates": hd, "rows": {k: [dict(_ser(data, b["series"][k])).get(d) for d in hd] for k in growth_keys + ["m3_level", "money_base"]},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": sig, "score": score}] if hd else []))[-24:]}
    return _base(cfg["currency"], "banking", cfg, b, E, D, signals, history)


# ═══════════════════════ 4 · RATES — CASH RATE CORRIDOR, BBSW, AGS CURVE ═══════════════════════
def build_rates(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["rates"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    E: Dict[str, dict] = {}
    raw: Dict[str, Series] = {}
    for key, sc in b["series"].items():
        sid = sc.get("id")
        freq = "weekly" if sc.get("lane") == "weekly" else "daily"
        if sid:
            raw[key] = _ser(data, sc)
            E[key] = entry(key, raw[key], sc["label"], "event" if sc.get("freq") == "event" else freq, "AUD_mn" if "volume" in key else "%", cfg, sid, sc.get("usd_analog"))
            if sc.get("freq") == "event" and raw[key]:
                E[key]["status"] = "fresh"
        else:
            E[key] = {"source_id": None, "label": sc["label"], "unit": "%", "frequency": freq, "status": "unavailable", "value": None, "date": None, "level": "NO DATA",
                      "equivalence_note": sc.get("status", "")}
    pol, on = raw["policy_rate"], raw["overnight_rate"]
    # corridor from A2 (event series): forward-fill onto the daily grid
    def _ffill(ev: Series, grid: Series) -> Series:
        out, j, cur = [], 0, None
        for d, _ in grid:
            while j < len(ev) and ev[j][0] <= d:
                cur = ev[j][1]; j += 1
            if cur is not None:
                out.append((d, cur))
        return out
    es_rate = _ffill(raw.get("es_rate", []), pol)
    ceil = _ffill(raw.get("overnight_repo_rate", []), pol)
    D: Dict[str, dict] = {}
    sp = S.merge_series(on, pol, lambda a, c: round((a - c) * 100, 2))
    D["overnight_minus_target_bps"] = entry("overnight_minus_target_bps", sp, "AONIA − cash rate target (bps)", "daily", "bps", cfg, usd_analog="EFFR − target",
                                            status="fresh" if sp else "unavailable", spec=th["overnight_minus_target_bps"], prev_level=pl.get("overnight_minus_target_bps"), z_window=30)
    absr = th["overnight_minus_target_bps"]["secondary_absolute"]
    pers = _persistent_level([v for _, v in sp], absr)
    D["overnight_minus_target_bps"]["percentile_level"] = D["overnight_minus_target_bps"]["level"]
    D["overnight_minus_target_bps"]["level"] = pers
    last3 = [v for _, v in sp[-3:]]
    D["overnight_minus_target_bps"]["friction_confirmed"] = bool(len(last3) == 3 and all(v >= absr["stress"] for v in last3))
    D["overnight_minus_target_bps"]["excess_side"] = bool(len(last3) == 3 and all(v <= absr.get("low_side_excess", -5) for v in last3))
    D["overnight_minus_deposit_bps"] = dict(D["overnight_minus_target_bps"], label="alias (regime key)")
    oe = S.merge_series(on, es_rate, lambda a, c: round((a - c) * 100, 2))
    D["overnight_minus_es_rate_bps"] = entry("overnight_minus_es_rate_bps", oe, "AONIA − ES rate (bps; distance from the floor, normal ≈ +10)", "daily", "bps", cfg, usd_analog="SOFR − IORB",
                                             status="fresh" if oe else "unavailable", z_window=30)
    bp = S.merge_series(S.merge_series(on, es_rate, lambda a, c: a - c), S.merge_series(ceil, es_rate, lambda a, c: a - c), lambda x, y: round(x / y, 3) if y else None)
    D["band_position"] = entry("band_position", bp, "Position in the corridor (0 = ES rate floor, 1 = +25 ceiling; normal ≈ 0.29)", "daily", "ratio", cfg, status="fresh" if bp else "unavailable", z_window=30)
    bv = D["band_position"]["value"]
    if bv is not None:
        D["band_position"]["level"] = "STRESS" if bv > th["band_position"]["stress_above"] else "WATCH" if bv > th["band_position"]["watch_above"] else "SAFE"
    bb = S.merge_series(raw["bbsw_3m"], pol, lambda a, c: round((a - c) * 100, 2))
    D["bbsw_minus_target_bps"] = entry("bbsw_minus_target_bps", bb, "BBSW 3M − cash rate target (bps; bank funding + expectations)", "daily", "bps", cfg, usd_analog="3M − FF",
                                       status="fresh" if bb else "unavailable", spec=th["bbsw_minus_target_bps"], prev_level=pl.get("bbsw_minus_target_bps"), z_window=30)
    # BBSW − target embeds rate expectations: percentile alone may only reach WATCH; STRESS/CRISIS need the absolute anchor
    _bb = D["bbsw_minus_target_bps"]
    _abs = th["bbsw_minus_target_bps"]["secondary_absolute"]
    if _bb["value"] is not None:
        v = _bb["value"]
        a_lvl = "CRISIS" if v >= _abs["crisis"] else "STRESS" if v >= _abs["stress"] else "WATCH" if v >= _abs["watch"] else "SAFE"
        p_lvl = _bb["level"]
        _bb["percentile_level"] = p_lvl
        _bb["level"] = a_lvl if a_lvl in ("STRESS", "CRISIS") else ("WATCH" if (p_lvl in ("WATCH", "STRESS", "CRISIS") or a_lvl == "WATCH") else "SAFE")
    D["bbsw_ois_3m_bps"] = {"label": "BBSW 3M − OIS 3M", "value": None, "status": "unavailable", "date": None, "level": "NO DATA", "unit": "bps", "equivalence_note": "OIS discontinued in F1 (Dec-2022)"}
    disp = S.merge_series(raw.get("overnight_high", []), raw.get("overnight_low", []), lambda a, c: round((a - c) * 100, 2))
    D["cash_market_dispersion_bps"] = entry("cash_market_dispersion_bps", disp, "Cash market dispersion: highest − lowest AONIA trade (bps)", "daily", "bps", cfg, status="fresh" if disp else "unavailable",
                                            spec={"method": "percentile", "window": "750d", "watch_above": "p80", "stress_above": "p90", "crisis_above": "p97", "hysteresis": {"exit_on": "p70/p80/p90"}},
                                            prev_level=pl.get("cash_market_dispersion_bps"), z_window=30)
    if D["cash_market_dispersion_bps"]["value"] == 0:
        D["cash_market_dispersion_bps"]["level"] = "SAFE"  # zero dispersion can never be stress (ties in the percentile sample)
    c = S.merge_series(raw["bond_10y"], raw["bond_2y"], lambda a, b_: round((a - b_) * 100, 2))
    D["curve_10y_2y_bps"] = entry("curve_10y_2y_bps", c, "AGS 10Y − 2Y (bps; F2 weekly file)", "weekly", "bps", cfg, usd_analog="10Y − 2Y", status="fresh" if c else "unavailable", z_window=30)
    cv = D["curve_10y_2y_bps"]["value"]
    tc = th["curve_10y_2y_bps"]
    if cv is not None:
        D["curve_10y_2y_bps"]["level"] = "CRISIS" if cv < tc["deep_inversion_below"] else "STRESS" if cv < tc["inverted_below"] else "WATCH" if cv < tc["flat_below"] else "SAFE"
        D["curve_10y_2y_bps"]["curve_state"] = {"CRISIS": "DEEP INVERSION", "STRESS": "INVERTED", "WATCH": "FLAT"}.get(D["curve_10y_2y_bps"]["level"], "STEEPENING")
    p2 = S.merge_series(pol, raw["bond_2y"], lambda a, b_: round((a - b_) * 100, 2))
    D["target_minus_2y_bps"] = entry("target_minus_2y_bps", p2, "Cash rate target − AGS 2Y (bps; > 0 = market prices cuts)", "weekly", "bps", cfg, usd_analog="FF − 2Y", status="fresh" if p2 else "unavailable", z_window=30)
    pv = D["target_minus_2y_bps"]["value"]
    tp = th["target_minus_2y_bps"]
    if pv is not None:
        D["target_minus_2y_bps"]["level"] = "STRESS" if pv > tp["tight_above"] else "WATCH" if pv > tp["normal_below"] else "SAFE"
    lvl = pers
    comps = [{"SAFE": 0.25, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}.get(lvl, 0.0),
             {"SAFE": 0.25, "WATCH": -0.25, "STRESS": -0.75, "CRISIS": -1.0}.get(D["bbsw_minus_target_bps"].get("level"), 0.0),
             {"SAFE": 0.25, "WATCH": 0.0, "STRESS": -0.5, "CRISIS": -1.0}.get(D["curve_10y_2y_bps"].get("level"), 0.0)]
    score = round(max(-2.0, min(2.0, sum(comps))), 2)
    label = "NO SIGNAL" if not sp else "FUNDING STRESS" if lvl in ("STRESS", "CRISIS") else "FLOOR FRICTION" if lvl == "WATCH" else "CORRIDOR CALM"
    tl = "NONE" if not sp else "RED" if lvl in ("STRESS", "CRISIS") else "YELLOW" if lvl == "WATCH" or D["bbsw_minus_target_bps"].get("level") in ("STRESS", "CRISIS") else "GREEN"
    alerts = [_alert("overnight_minus_target_bps", D["overnight_minus_target_bps"], "≥ +3 early flag; ≥ +5 for 3 sessions = STRESS; ≥ +15 = CRISIS (ceiling +25)"),
              _alert("band_position", D["band_position"], "0.29 = at target; 1.0 = at the standing-facility ceiling"),
              _alert("bbsw_minus_target_bps", D["bbsw_minus_target_bps"], "percentile primary; > 45 bp absolute = STRESS"),
              _alert("cash_market_dispersion_bps", D["cash_market_dispersion_bps"], "wide high−low = uneven reserves"),
              _alert("curve_10y_2y_bps", D["curve_10y_2y_bps"], "negative = inverted")]
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": ["AONIA_BELOW_FLOOR_SIDE"] if D["overnight_minus_target_bps"]["excess_side"] else [],
               "detail": "AONIA−target %s bps (%s) · band %s · BBSW−target %s (%s) · 10Y−2Y %s" % (D["overnight_minus_target_bps"]["value"], lvl, bv, D["bbsw_minus_target_bps"]["value"],
                                                                                                D["bbsw_minus_target_bps"].get("level"), D["curve_10y_2y_bps"].get("curve_state")), "alerts": alerts}
    hd = [d for d, _ in S.tail(sp, 120)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("overnight_minus_target_bps", sp), ("overnight_minus_es_rate_bps", oe), ("band_position", bp), ("bbsw_minus_target_bps", bb),
                                                                                  ("cash_market_dispersion_bps", disp), ("policy_rate", pol), ("overnight_rate", on), ("bbsw_3m", raw["bbsw_3m"]),
                                                                                  ("bond_2y", raw["bond_2y"]), ("bond_10y", raw["bond_10y"]), ("curve_10y_2y_bps", c))},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": label, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "rates", cfg, b, E, D, signals, history)
