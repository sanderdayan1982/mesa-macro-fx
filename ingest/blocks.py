"""Block builders: central_bank, fiscal, banking, rates → schema/block.schema.json documents.
Layer order and titles follow the operator rule: central bank → treasury/equivalent → banking transmission → rates."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, List, Optional
from . import series as S
from .series import Series
from .thresholds import classify, signal_band
from .scoring import Comps
from .quality import evaluate_series, system_summary

SCHEMA_VERSION = "0.3.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def entry(name: str, ser: Series, label: str, freq: str, unit: str, cfg: dict, source_id: Optional[str] = None,
          usd_analog: Optional[str] = None, status: Optional[str] = None, spec: Optional[dict] = None,
          prev_level: Optional[str] = None, equivalence_note: Optional[str] = None, hist: int = 52,
          quality: Optional[dict] = None, z_window: Optional[int] = None, lag_days: int = 0) -> dict:
    ser = S.clean(ser)
    L, P = S.last(ser), S.last(ser, 1)
    q = quality or evaluate_series(name, ser, freq, cfg, lag_days=lag_days)
    st = status or q["freshness"]
    if not ser:
        st = "unavailable"
    val = L[1] if L else None
    e = {"source_id": source_id, "label": label, "usd_analog": usd_analog, "unit": unit, "frequency": freq,
         "status": st, "value": val, "date": L[0] if L else None,
         "prev_value": P[1] if P else None, "prev_date": P[0] if P else None,
         "change_abs": round(L[1] - P[1], 4) if (L and P) else None,
         "change_pct": round((L[1] - P[1]) / abs(P[1]) * 100, 4) if (L and P and P[1]) else None,
         "zscore": None, "percentile": None, "window": (spec or {}).get("window"), "level": "NO DATA" if val is None else "SAFE",
         "sparkline": [v for _, v in S.tail(ser, hist)], "high_low": S.high_low(ser, hist), "age_days": q.get("age_days"),
         "confidence": q["confidence"]["score"], "latest_outlier": q.get("latest_outlier", False)}
    if equivalence_note:
        e["equivalence_note"] = equivalence_note
    zw = z_window or (26 if freq == "weekly" else 30 if freq == "daily" else 12)
    zs = S.rolling_zscore(ser, zw)
    e["zscore"] = zs[-1][1] if zs else None
    if spec and val is not None:
        c = classify(val, ser, spec, freq, prev_level)
        e["level"] = c["level"]
        e["percentile"] = c.get("percentile")
        e["thresholds"] = c.get("thresholds", {})
        if "in_range" in c:
            e["in_range"] = c["in_range"]
        if "above_range" in c:
            e["above_range"] = c["above_range"]
        if c.get("secondary"):
            e["secondary_level"] = c["secondary"].get("level")
    return e


def _prev_levels(prev_block: Optional[dict]) -> Dict[str, str]:
    out = {}
    for sec in ("series", "derived"):
        for k, v in ((prev_block or {}).get(sec) or {}).items():
            if isinstance(v, dict) and v.get("level") in ("WATCH", "STRESS", "CRISIS"):
                out[k] = v["level"]
    return out


def _alert(metric: str, e: dict, hint: str = "") -> dict:
    return {"metric": metric, "level": e.get("level", "NO DATA"), "value": e.get("value"),
            "threshold": (e.get("thresholds") or {}).get("levels"), "status": e.get("status"), "action_hint": hint}


def _health(entries: Dict[str, dict], expected: int) -> dict:
    loaded = sum(1 for e in entries.values() if e.get("status") != "unavailable")
    ok = ("fresh", "proxy")
    st = "fresh" if loaded == expected and all(e["status"] in ok for e in entries.values()) else \
        "unavailable" if loaded == 0 else "degraded" if loaded < max(3, expected // 2) else "stale"
    return {"status": st, "series_loaded": loaded, "series_expected": expected, "last_fetch_ok": loaded > 0, "errors": []}


def _base(ccy: str, block: str, cfg: dict, bcfg: dict, entries: dict, derived: dict, signals: dict, history: dict) -> dict:
    dates = [e["date"] for e in list(entries.values()) + list(derived.values()) if isinstance(e, dict) and e.get("date")]
    # the block's as-of is the last OBSERVED date: calendar-type entries dated in the future (announced settlements, horizons)
    # must not push it forward (NZD showed "as of 2026-09-14" on 2026-09-10 and the fiscal horizon cascaded from it)
    today = datetime.now(timezone.utc).date().isoformat()
    past = [d for d in dates if d <= today] or dates
    return {"currency": ccy, "block": block, "schema_version": SCHEMA_VERSION, "config_version": cfg.get("config_version"),
            "generated_at": now_iso(), "as_of": max(past) if past else None,
            "equivalence_quality": bcfg.get("equivalence_quality"), "equivalence_note": bcfg.get("equivalence_note", ""),
            "source_health": _health(entries, len(bcfg.get("series", {}))), "series": entries, "derived": derived,
            "signals": signals, "history": history}


# ═══════════════════════ 1 · CENTRAL BANK LIQUIDITY ═══════════════════════
def build_central_bank(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["central_bank"]
    unit, freq = cfg["units"]["balance_sheet"], "weekly"
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E: Dict[str, dict] = {}
    raw: Dict[str, Series] = {}
    for key, sc in b["series"].items():
        raw[key] = S.clean(data.get(sc["id"], []))
        spec = th.get(key)
        E[key] = entry(key, raw[key], sc["label"], freq, unit, cfg, sc["id"], sc.get("usd_analog"), spec=spec, prev_level=pl.get(key))
    # derived
    ta, ga, rr = raw["total_assets"], raw["government_account"], raw.get("reverse_repo", [])
    rr_map = {d: v for d, v in rr}
    nl = [(d, v - (dict(ga).get(d, 0.0)) - rr_map.get(d, 0.0)) for d, v in ta if d in dict(ga)]
    nl = S.clean(nl)
    D: Dict[str, dict] = {}
    D["net_liquidity"] = entry("net_liquidity", nl, "Net Liquidity = Total assets − GoC deposits − SRA", freq, unit, cfg, usd_analog="WALCL − WTREGEN − RRPONTTLD", status="fresh" if nl else "unavailable")
    nlw = S.pct_change_series(nl)
    D["net_liquidity_wow_pct"] = entry("net_liquidity_wow_pct", nlw, "Net Liquidity Δ% w/w", freq, "%", cfg, usd_analog="Net Liquidity Δ%", status="fresh" if nlw else "unavailable")
    sb = signal_band(D["net_liquidity_wow_pct"]["value"], nlw, th["net_liquidity_wow_pct"], freq)
    D["net_liquidity_wow_pct"]["signal"] = sb["signal"]
    D["net_liquidity_wow_pct"]["percentile"] = sb["percentile"]
    D["net_liquidity_wow_pct"]["thresholds"] = sb.get("thresholds", {})
    D["reserves_wow_pct"] = entry("reserves_wow_pct", S.pct_change_series(raw["reserves"]), "Settlement balances Δ% w/w", freq, "%", cfg, status="fresh", spec=th.get("reserves_wow_pct"), prev_level=pl.get("reserves_wow_pct"))
    D["active_drains"] = entry("active_drains", S.add_series(ga, rr) if rr else ga, "Active drains = GoC deposits + SRA", freq, unit, cfg, usd_analog="TGA + RRP", status="fresh")
    notes = raw.get("notes_in_circulation", [])
    cd = [(d, -v) for d, v in S.diff_series(notes)]
    D["currency_drain"] = entry("currency_drain", cd, "Currency drain (−Δ notes in circulation, autonomous)", freq, unit, cfg, status="fresh" if cd else "unavailable",
                                equivalence_note="Outside money: NOT subtracted from Net Liquidity (cross-currency comparability); shown as autonomous drain")
    rex = S.add_series(S.diff_series(raw["reserves"]), S.diff_series(notes))
    D["reserves_ex_currency_effect"] = entry("reserves_ex_currency_effect", rex, "Δ Reserves excluding currency demand", freq, unit, cfg, status="fresh" if rex else "unavailable")
    for k in ("sovereign_bonds", "liquidity_repos", "notes_in_circulation", "bills"):
        w = S.pct_change_series(raw.get(k, []))
        D[k + "_wow_pct"] = entry(k + "_wow_pct", w, E[k]["label"] + " Δ% w/w", freq, "%", cfg, status="fresh" if w else "unavailable",
                                  spec=th.get(k + "_wow_pct"), prev_level=pl.get(k + "_wow_pct"))
    # balance-sheet phase (informational label)
    sbw = D["sovereign_bonds_wow_pct"]["value"] or 0.0
    bw = D["bills_wow_pct"]["value"] or 0.0
    rw = D["liquidity_repos_wow_pct"]["value"] or 0.0
    phase = "QE" if sbw > 0.5 else "QT" if sbw < -0.5 and bw <= 0 and rw <= 0 else "NORMALIZATION" if (bw > 0 or rw > 0) else "STEADY"
    D["balance_sheet_phase"] = {"label": "Balance-sheet phase", "value": None, "phase": phase, "status": "fresh", "date": E["total_assets"]["date"],
                                "note": "informational; post-QT BoC offsets currency growth with term repo, bills (Q4 2025) and bonds (late 2026)"}
    # score & signals
    C = Comps(cfg, "mean2")
    sig = D["net_liquidity_wow_pct"]["signal"]
    C.flow("net_liquidity_band", 1.0 if sig == "BAND_HIGH" else -1.0 if sig == "BAND_LOW" else 0.0)
    lvl = E["reserves"]["level"]
    C.level("reserves_vs_range", {"SAFE": 0.5 if E["reserves"].get("in_range") else 0.0, "WATCH": -1.0, "STRESS": -1.5, "CRISIS": -2.0}.get(lvl, 0.0))
    if (E["emergency_lending"]["value"] or 0) > 0:
        C.event("emergency_lending", -2.0)
    rw_ = D["reserves_wow_pct"]["value"]
    C.flow("reserves_wow", max(-1.0, min(1.0, (rw_ or 0.0) / 10.0)))
    score = C.score()
    alerts = [_alert("reserves", E["reserves"], "below BoC 50–70B range = scarcity zone"),
              _alert("emergency_lending", E["emergency_lending"], "any Advances > 0 = standing facility in use"),
              _alert("government_account", E["government_account"], "high/rising = fiscal drain"),
              _alert("sovereign_bonds_wow_pct", D["sovereign_bonds_wow_pct"], "QT drag")]
    label = "NO SIGNAL" if not nl else ("INJECTION" if score >= 0.5 else "DRAIN" if score <= -0.5 else "NEUTRAL")
    tl = "NONE" if not nl else "GREEN" if score >= 0.5 else "RED" if score <= -0.75 else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": label, "components": C.to_dict(),
               "detail": "NetLiq %s · reserves %s (%s) · phase %s" % (sig, lvl, "in range" if E["reserves"].get("in_range") else "out of range", phase),
               "alerts": alerts}
    hist_dates = [d for d, _ in S.tail(nl, 52)]
    history = {"dates": hist_dates, "rows": {
        "net_liquidity": [dict(nl).get(d) for d in hist_dates], "reserves": [dict(raw["reserves"]).get(d) for d in hist_dates],
        "government_account": [dict(ga).get(d) for d in hist_dates], "total_assets": [dict(ta).get(d) for d in hist_dates],
        "net_liquidity_wow_pct": [dict(nlw).get(d) for d in hist_dates]}, "signal_log": (prev or {}).get("history", {}).get("signal_log", [])[-52:]}
    if hist_dates:
        history["signal_log"] = [x for x in history["signal_log"] if x.get("date") != hist_dates[-1]] + [{"date": hist_dates[-1], "label": label, "score": score, "note": signals["detail"]}]
    return _base(cfg["currency"], "central_bank", cfg, b, E, D, signals, history)


# ═══════════════════════ 2 · TREASURY / FISCAL EQUIVALENT ═══════════════════════
def build_fiscal(cfg: dict, valet: Dict[str, Series], rg: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["fiscal"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    E: Dict[str, dict] = {}
    E["rg_closing_balance"] = entry("rg_closing_balance", rg.get("rg_closing_balance", []), "Receiver General closing cash balance at BoC", "daily", unit, cfg, "RG:Closing-Cash-Balance", "DTS TGA closing balance", lag_days=7)
    E["rg_term_deposits"] = entry("rg_term_deposits", rg.get("rg_term_deposits", []), "RG term deposits at financial institutions", "daily", unit, cfg, "RG:Term-Deposit-Outstanding", None,
                                  equivalence_note="cash moved BoC→banks: adds reserves, not fiscal flow", lag_days=7)
    E["rg_prudential_fund"] = entry("rg_prudential_fund", rg.get("rg_prudential_fund", []), "Prudential Liquidity Fund", "daily", unit, cfg, "RG:Prudential-Liquidity-Fund", lag_days=7)
    gcb = S.clean(valet.get("V36628", []))
    E["government_account_cb"] = entry("government_account_cb", gcb, "GoC deposits at BoC (weekly, Valet)", "weekly", unit, cfg, "V36628", "WTREGEN")
    gdb = S.clean(valet.get("V36811", []))
    E["government_deposits_banks"] = entry("government_deposits_banks", gdb, "GoC deposits at chartered banks (monthly)", "monthly", unit, cfg, "V36811")
    # derived (daily)
    cb, td = S.clean(rg.get("rg_closing_balance", [])), S.clean(rg.get("rg_term_deposits", []))
    D: Dict[str, dict] = {}
    ri = [(d, -v) for d, v in S.diff_series(cb)]
    D["reserve_impact_daily"] = entry("reserve_impact_daily", ri, "Reserve impact = −Δ RG balance at BoC", "daily", unit, cfg, usd_analog="−ΔTGA", status="proxy" if ri else "unavailable")
    # term deposits: an empty cell in the RG file = no term deposits outstanding (Sep-2020 → Feb-2024 has none) → 0, never a hole
    # (calibration replay 2026-09-09 found the common-date sum froze the fiscal flow for 3.5 years)
    tdm = {d: v for d, v in td}
    tot = [(d, v + tdm.get(d, 0.0)) for d, v in cb]
    ff = [(d, -v) for d, v in S.diff_series(tot)]
    D["fiscal_flow_proxy_daily"] = entry("fiscal_flow_proxy_daily", ff, "Fiscal flow proxy = −Δ(BoC balance + term deposits)", "daily", unit, cfg, usd_analog="Net Treasury Flow (Mosler)", status="proxy" if ff else "unavailable",
                                         equivalence_note="positive = net injection of NFA proxy; excludes BoC↔bank cash transfers")
    z = S.rolling_zscore(ff, 30)
    D["fiscal_flow_zscore"] = entry("fiscal_flow_zscore", [(d, v) for d, v in z if v is not None], "Fiscal flow Z-score (30 business days)", "daily", "σ", cfg, usd_analog="DTS 30d Z", status="proxy" if ff else "unavailable", spec=b["thresholds"]["fiscal_flow_zscore"])
    c7 = S.rolling_sum(ff, 7)
    D["fiscal_flow_7d_cum"] = entry("fiscal_flow_7d_cum", c7, "Fiscal flow 7-day cumulative", "daily", unit, cfg, usd_analog="7-day cumulative", status="proxy" if c7 else "unavailable")
    st = S.rolling_stats(ff, 30)
    D["fiscal_flow_30d_mean"] = {"label": "30-day mean", "value": st["mean"], "unit": unit, "status": "proxy", "date": E["rg_closing_balance"]["date"]}
    D["fiscal_flow_30d_sd"] = {"label": "30-day std dev", "value": st["sd"], "unit": unit, "status": "proxy", "date": E["rg_closing_balance"]["date"]}
    wk = [(d, -v) for d, v in S.diff_series(gcb)]
    D["fiscal_flow_weekly_valet"] = entry("fiscal_flow_weekly_valet", wk, "Weekly cross-check: −Δ GoC deposits at BoC (Valet)", "weekly", unit, cfg, status="proxy" if wk else "unavailable")
    D["net_issuance"] = {"label": "Net issuance (auctions)", "value": None, "status": "unavailable", "date": None, "unit": unit, "note": "pending: Valet auction groups"}
    # regime
    zv, cum = D["fiscal_flow_zscore"]["value"], D["fiscal_flow_7d_cum"]["value"]
    pcts = signal_band(cum, c7, {"window": "750d", "risk_on_above": "p80", "risk_off_below": "p20"}, "daily") if cum is not None else {"signal": "NO DATA", "percentile": None}
    if cum is None:
        reg, score = "NO DATA", 0.0
    else:
        reg = "INJECTION" if pcts["signal"] == "BAND_HIGH" or (pcts["percentile"] is None and cum > 0 and (zv or 0) > 0.5) else \
              "DRAIN" if pcts["signal"] == "BAND_LOW" or (pcts["percentile"] is None and cum < 0 and (zv or 0) < -0.5) else "NEUTRAL"
        score = round(max(-2.0, min(2.0, (zv or 0.0))), 2)
    CF = Comps(cfg, "sum").flow("fiscal_flow_z", score)
    D["fiscal_flow_7d_cum"]["percentile"] = pcts.get("percentile")
    D["fiscal_regime"] = {"label": "Fiscal regime", "value": None, "regime": reg, "status": "proxy", "date": E["rg_closing_balance"]["date"]}
    D["fiscal_regime_score"] = {"label": "Fiscal regime score", "value": score, "range": [-2, 2], "status": "proxy", "date": E["rg_closing_balance"]["date"]}
    D["fiscal_stress"] = {"label": "Fiscal stress (|Z| > 2)", "value": (abs(zv) > 2) if zv is not None else None, "status": "proxy", "date": E["rg_closing_balance"]["date"]}
    D["mmt_note"] = {"label": "MMT note", "value": None, "status": "fresh", "date": None, "text": b["derived"].get("mmt_note", "")}
    alerts = [_alert("fiscal_flow_zscore", D["fiscal_flow_zscore"], "|Z|>2 = extraordinary daily flow"),
              {"metric": "fiscal_flow_7d_cum", "level": "WATCH" if reg == "DRAIN" else "SAFE" if reg != "NO DATA" else "NO DATA", "value": cum, "threshold": None, "status": D["fiscal_flow_7d_cum"]["status"], "action_hint": "7d cumulative below p20 = fiscal drain"}]
    tl = "NONE" if reg == "NO DATA" else "GREEN" if reg == "INJECTION" else "RED" if reg == "DRAIN" else "YELLOW"
    # daily data freshness: RG publishes in batches; if > 10 days old, mark degraded
    if E["rg_closing_balance"]["status"] != "fresh":
        for k in ("reserve_impact_daily", "fiscal_flow_proxy_daily", "fiscal_flow_zscore", "fiscal_flow_7d_cum"):
            D[k]["status"] = "stale" if E["rg_closing_balance"]["status"] == "stale" else "unavailable"
    signals = {"traffic_light": tl, "score": score, "label": reg, "components": CF.to_dict(), "detail": "7d cum %s · Z %s · weekly Valet cross-check %s" % (cum, zv, D["fiscal_flow_weekly_valet"]["value"]), "alerts": alerts}
    hd = [d for d, _ in S.tail(ff, 60)]
    history = {"dates": hd, "rows": {"fiscal_flow_proxy_daily": [dict(ff).get(d) for d in hd], "reserve_impact_daily": [dict(ri).get(d) for d in hd],
                                     "rg_closing_balance": [dict(cb).get(d) for d in hd], "rg_term_deposits": [dict(td).get(d) for d in hd],
                                     "fiscal_flow_zscore": [dict(z).get(d) for d in hd]},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": reg, "score": score}] if hd else []))[-60:]}
    return _base(cfg["currency"], "fiscal", cfg, b, E, D, signals, history)


# ═══════════════════════ 3 · BANKING TRANSMISSION ═══════════════════════
def build_banking(cfg: dict, valet: Dict[str, Series], rates_block: Optional[dict] = None, prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["banking"]
    unit, freq = cfg["units"]["balance_sheet"], "monthly"
    E: Dict[str, dict] = {}
    for key, sc in b["series"].items():
        sid = sc.get("id")
        ser = S.clean(valet.get(sid, [])) if sid else []
        st = None if sid else "unavailable"
        E[key] = entry(key, ser, sc["label"], freq, unit, cfg, sid, sc.get("usd_analog"), status=st, z_window=26)
        if sc.get("status") == "pending":
            E[key]["equivalence_note"] = "pending: StatCan candidates " + ", ".join(sc.get("statcan_candidates", []))
        if sc.get("status") == "display_only":
            E[key]["equivalence_note"] = sc.get("triangulation") or sc.get("quality_note", "display only")
            if sc.get("quality_note"):
                E[key]["status"] = "degraded"
    D: Dict[str, dict] = {}
    applies = b["derived"]["mom_pct"]["applies_to"]
    chg = {}
    for k in applies:
        sid = b["series"][k].get("id")
        ser = S.clean(valet.get(sid, [])) if sid else []
        mom = S.pct_change_series(ser)
        D[k + "_mom_pct"] = entry(k + "_mom_pct", mom, E[k]["label"] + " Δ% m/m", freq, "%", cfg, status="fresh" if mom else "unavailable", spec={"method": "zscore", "notable_above": 1.0, "extraordinary_above": 2.0}, z_window=26)
        # zscore-based level uses the z itself
        zz = D[k + "_mom_pct"]["zscore"]
        D[k + "_mom_pct"]["level"] = "NO DATA" if not mom else "STRESS" if zz is not None and abs(zz) >= 2 else "WATCH" if zz is not None and abs(zz) >= 1 else "SAFE"
        chg[k] = D[k + "_mom_pct"]["value"]
    disp = (rates_block or {}).get("derived", {}).get("corra_dispersion_bps", {})
    # base-100 index (last 24 months) for deposits/assets
    for k in ("deposits_public", "household_loans_banks"):
        sid = b["series"][k]["id"]
        ser = S.clean(valet.get(sid, []))[-24:]
        if ser:
            base = ser[0][1]
            D[k + "_base100"] = {"label": E[k]["label"] + " (base 100)", "value": round(ser[-1][1] / base * 100, 2), "status": E[k]["status"], "date": ser[-1][0], "unit": "index", "sparkline": [round(v / base * 100, 2) for _, v in ser]}
    valid = [k for k in applies if chg.get(k) is not None]
    grn = sum(1 for k in valid if chg[k] > 0) + (1 if disp.get("level") in ("SAFE",) else 0)
    red = sum(1 for k in valid if chg[k] < -0.1) + (1 if disp.get("level") in ("STRESS", "CRISIS") else 0)
    n_valid = len(valid) + (1 if disp.get("value") is not None else 0)
    if n_valid < 3:
        sig, tl, score = "NO SIGNAL", "NONE", 0.0
    elif red >= 3:
        sig, tl, score = "RED", "RED", -1.5
    elif grn >= 3:
        sig, tl, score = "GREEN", "GREEN", 1.0
    else:
        sig, tl, score = "YELLOW", "YELLOW", 0.0
    D["transmission_signal"] = {"label": "Transmission signal", "value": None, "signal": sig, "status": "stale" if valid else "unavailable", "date": E["deposits_public"]["date"],
                                "rule": b["derived"]["transmission_signal"]["rule"], "valid_series": n_valid}
    alerts = [_alert(k + "_mom_pct", D[k + "_mom_pct"], "|Z|≥2 extraordinary monthly change") for k in applies]
    signals = {"traffic_light": tl, "score": score, "label": sig, "detail": "%d/%d series valid · monthly, ~%d-day lag" % (n_valid, len(applies) + 1, b.get("publication_lag_days_approx", 75)), "alerts": alerts}
    ser_assets = S.clean(valet.get(b["series"]["deposits_public"]["id"], []))
    hd = [d for d, _ in S.tail(ser_assets, 24)]
    history = {"dates": hd, "rows": {k: [dict(S.clean(valet.get(b["series"][k]["id"], []))).get(d) for d in hd] for k in ("bank_assets", "deposits_public", "household_loans_banks", "deposits_government", "reserves_on_bank_books")},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": sig, "score": score}] if hd else []))[-24:]}
    return _base(cfg["currency"], "banking", cfg, b, E, D, signals, history)


# ═══════════════════════ 4 · RATES / MONEY MARKET ═══════════════════════
def build_rates(cfg: dict, valet: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["rates"]
    freq = "daily"
    pl = _prev_levels(prev)
    th = b["thresholds"]
    E: Dict[str, dict] = {}
    raw: Dict[str, Series] = {}
    for key, sc in b["series"].items():
        sid = sc.get("id")
        if sid:
            raw[key] = S.clean(valet.get(sid, []))
            E[key] = entry(key, raw[key], sc["label"], freq, "%" if "volume" not in key else "CAD", cfg, sid, sc.get("usd_analog"))
    # deposit rate = target − 5 bp from 2025-01-30, = target before
    pol = raw["policy_rate"]
    dep = [(d, round(v - 0.05, 4) if d >= "2025-01-30" else v) for d, v in pol]
    raw["deposit_rate"] = dep
    E["deposit_rate"] = entry("deposit_rate", dep, b["series"]["deposit_rate"]["label"], freq, "%", cfg, "derived:V39079−0.05", "IORB", status="proxy",
                              equivalence_note=b["series"]["deposit_rate"]["source_note"])
    D: Dict[str, dict] = {}
    on = raw["overnight_rate"]
    od = S.merge_series(on, dep, lambda a, c: (a - c) * 100)
    D["overnight_minus_deposit_bps"] = entry("overnight_minus_deposit_bps", od, "CORRA − deposit rate (bps)", freq, "bps", cfg, usd_analog="SOFR − IORB", status="fresh" if od else "unavailable",
                                             spec=th["overnight_minus_deposit_bps"], prev_level=pl.get("overnight_minus_deposit_bps"), z_window=30)
    op = S.merge_series(on, pol, lambda a, c: (a - c) * 100)
    D["overnight_minus_policy_bps"] = entry("overnight_minus_policy_bps", op, "CORRA − target (bps, secondary)", freq, "bps", cfg, status="fresh" if op else "unavailable",
                                            spec=th["overnight_minus_policy_bps"], prev_level=pl.get("overnight_minus_policy_bps"), z_window=30)
    br = raw.get("bank_rate", [])
    bp = S.merge_series(S.merge_series(on, dep, lambda a, c: a - c), S.merge_series(br, dep, lambda a, c: a - c), lambda x, y: x / y if y else None)
    D["band_position"] = entry("band_position", bp, "Position in operating band (0 = deposit floor, 1 = Bank Rate)", freq, "ratio", cfg, status="fresh" if bp else "unavailable", spec=th["band_position"], z_window=30)
    p3 = S.merge_series(pol, raw["bill_3m"], lambda a, c: (a - c) * 100)
    D["policy_minus_3m_bps"] = entry("policy_minus_3m_bps", p3, "Target − 3M bill (bps)", freq, "bps", cfg, usd_analog="FF − 3M", status="fresh" if p3 else "unavailable", spec=th["policy_minus_3m_bps"], z_window=30)
    c = S.merge_series(raw["bond_10y"], raw["bond_2y"], lambda a, b_: (a - b_) * 100)
    D["curve_10y_2y_bps"] = entry("curve_10y_2y_bps", c, "10Y − 2Y (bps)", freq, "bps", cfg, usd_analog="10Y − 2Y", status="fresh" if c else "unavailable", spec=th["curve_10y_2y_bps"], z_window=30)
    disp = S.merge_series(raw.get("corra_p95", []), raw.get("corra_p5", []), lambda a, b_: (a - b_) * 100)
    D["corra_dispersion_bps"] = entry("corra_dispersion_bps", disp, "CORRA dispersion p95 − p5 (bps)", freq, "bps", cfg, status="fresh" if disp else "unavailable",
                                      spec={"method": "percentile", "window": "750d", "watch_above": "p80", "stress_above": "p90", "crisis_above": "p97", "hysteresis": {"exit_on": "p70/p80/p90"}}, prev_level=pl.get("corra_dispersion_bps"), z_window=30)
    # curve absolute rule (inversion below 0 etc.)
    cv = D["curve_10y_2y_bps"]["value"]
    if cv is not None:
        D["curve_10y_2y_bps"]["level"] = "CRISIS" if cv < th["curve_10y_2y_bps"]["deep_inversion_below"] else "STRESS" if cv < th["curve_10y_2y_bps"]["inverted_below"] else "WATCH" if cv < th["curve_10y_2y_bps"]["flat_below"] else "SAFE"
        D["curve_10y_2y_bps"]["curve_state"] = "DEEP INVERSION" if D["curve_10y_2y_bps"]["level"] == "CRISIS" else "INVERTED" if D["curve_10y_2y_bps"]["level"] == "STRESS" else "FLAT" if D["curve_10y_2y_bps"]["level"] == "WATCH" else "STEEPENING"
    pv = D["policy_minus_3m_bps"]["value"]
    if pv is not None:
        D["policy_minus_3m_bps"]["level"] = "STRESS" if pv > th["policy_minus_3m_bps"]["tight_above"] else "WATCH" if pv > th["policy_minus_3m_bps"]["normal_below"] else "SAFE"
    # score
    lvl = D["overnight_minus_deposit_bps"]["level"]
    comps = [{"SAFE": 0.5, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}.get(lvl, 0.0),
             {"SAFE": 0.5, "WATCH": 0.0, "STRESS": -0.5, "CRISIS": -1.0}.get(D["curve_10y_2y_bps"].get("level"), 0.0),
             {"SAFE": 0.25, "WATCH": 0.0, "STRESS": -0.5}.get(D["policy_minus_3m_bps"].get("level"), 0.0)]
    score = round(max(-2.0, min(2.0, sum(comps))), 2)
    label = "NO SIGNAL" if not od else "FUNDING STRESS" if lvl in ("STRESS", "CRISIS") else "FRICTION" if lvl == "WATCH" else "EASY"
    tl = "NONE" if not od else "RED" if lvl in ("STRESS", "CRISIS") else "YELLOW" if lvl == "WATCH" or D["curve_10y_2y_bps"].get("level") in ("STRESS", "CRISIS") else "GREEN"
    alerts = [_alert("overnight_minus_deposit_bps", D["overnight_minus_deposit_bps"], "CORRA above floor: +5 = at target, +30 = at Bank Rate"),
              _alert("band_position", D["band_position"], "0.17 = at target; 1.0 = at ceiling"),
              _alert("curve_10y_2y_bps", D["curve_10y_2y_bps"], "negative = inverted"),
              _alert("policy_minus_3m_bps", D["policy_minus_3m_bps"], "> 0 = market prices cuts"),
              _alert("corra_dispersion_bps", D["corra_dispersion_bps"], "wide dispersion = uneven distribution of reserves")]
    signals = {"traffic_light": tl, "score": score, "label": label,
               "detail": "CORRA−deposit %s bps (%s) · band %s · curve %s" % (D["overnight_minus_deposit_bps"]["value"], lvl, D["band_position"]["value"], D["curve_10y_2y_bps"].get("curve_state")), "alerts": alerts}
    hd = [d for d, _ in S.tail(od, 120)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("overnight_minus_deposit_bps", od), ("overnight_minus_policy_bps", op), ("curve_10y_2y_bps", c), ("policy_minus_3m_bps", p3),
                                                                                 ("policy_rate", pol), ("overnight_rate", on), ("bill_3m", raw["bill_3m"]), ("bond_2y", raw["bond_2y"]), ("bond_10y", raw["bond_10y"]), ("corra_dispersion_bps", disp))},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": label, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "rates", cfg, b, E, D, signals, history)
