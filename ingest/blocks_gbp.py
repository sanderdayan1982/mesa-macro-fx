"""GBP block builders (Sterling Monetary Framework). Same four layers and schema as CAD, different mechanics:
  1 central bank  — Weekly Report B1.1.2: reserves vs PMRR, Policy Balance Sheet (not 'Net Liquidity'), repo-led absorption
  2 fiscal        — ONS Public Sector Finances (monthly): net_spending = expenditure − receipts (NFA flow), CGNCR = issuance drain
  3 banking       — Money & Credit (monthly): flows, z-scores, M4Lex as the loans-create-deposits channel
  4 rates         — SONIA − Bank Rate (floor system: normally negative; ≥ 0 persistent = friction), 5/10/20Y par curve
Config: config/gbp.json v0.2.x (triangulated 2026-09-08)."""
from __future__ import annotations
from typing import Dict, List, Optional
from . import series as S
from .series import Series
from .thresholds import classify, signal_band
from .scoring import Comps
from .blocks import entry, _prev_levels, _alert, _base as _base0, _health


def _base(ccy, block, cfg, bcfg, E, D, signals, history):
    out = _base0(ccy, block, cfg, bcfg, E, D, signals, history)
    wired = {k: e for k, e in E.items() if bcfg["series"].get(k, {}).get("id")}
    out["source_health"] = _health(wired, len(wired))
    out["source_health"]["series_pending"] = len(E) - len(wired)
    return out


def _ser(data: Dict[str, Series], sc: dict) -> Series:
    sid = sc.get("id")
    return S.clean(data.get(sid, [])) if sid else []


def _entries(cfg: dict, block: str, data: Dict[str, Series], freq: str, unit: str, pl: Dict[str, str], th: dict) -> Dict[str, dict]:
    E: Dict[str, dict] = {}
    for key, sc in cfg["blocks"][block]["series"].items():
        ser = _ser(data, sc)
        st = None if sc.get("id") else "unavailable"
        u = sc.get("unit", unit)
        e = entry(key, ser, sc["label"], sc.get("freq", freq), u, cfg, sc.get("id"), sc.get("usd_analog"), status=st,
                  spec=th.get(key), prev_level=pl.get(key), z_window=26 if freq == "weekly" else 12 if freq == "monthly" else 30)
        if sc.get("freq") == "event" and ser:
            e["status"] = "fresh"  # event series (maintenance-period / per-operation): age is not staleness
            e["equivalence_note"] = sc.get("note") or sc.get("role", "")
        if sc.get("display_only"):
            e["display_only"] = True
        if sc.get("note") or sc.get("role"):
            e["equivalence_note"] = sc.get("note") or sc.get("role")
        if sc.get("status") in ("pending", "unavailable") and not sc.get("id"):
            e["status"] = "unavailable"
            e["equivalence_note"] = sc.get("fallback") or sc.get("source") or sc.get("label")
        E[key] = e
    return E


# ═══════════════════════ 1 · CENTRAL BANK LIQUIDITY (Weekly Report) ═══════════════════════
def build_central_bank(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["central_bank"]
    unit, freq = cfg["units"]["balance_sheet"], "weekly"
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "central_bank", data, freq, unit, pl, th)
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    res, notes = raw["reserves"], raw["notes_in_circulation"]
    # Policy Balance Sheet = STR + long-term ops + TFSME + APF loan + sterling bonds (all reserve-creating assets)
    pbs: Series = []
    parts = [raw[k] for k in ("str_lending", "ltr_lending", "tfsme", "apf_loan", "sterling_bonds") if raw.get(k)]
    if parts:
        pbs = parts[0]
        for p in parts[1:]:
            pbs = S.add_series(pbs, p)
    D: Dict[str, dict] = {}
    D["policy_balance_sheet"] = entry("policy_balance_sheet", pbs, "Policy Balance Sheet (assets) = STR + LTR + TFSME + APF loan + £ bonds", freq, unit, cfg,
                                      usd_analog="WALCL policy portfolio (no TGA term: HMG deposits not in the Weekly Report)", status="fresh" if pbs else "unavailable",
                                      equivalence_note=b["derived"]["policy_balance_sheet"]["note"])
    pw = S.pct_change_series(pbs)
    D["policy_balance_sheet_wow_pct"] = entry("policy_balance_sheet_wow_pct", pw, "Policy Balance Sheet Δ% w/w", freq, "%", cfg, status="fresh" if pw else "unavailable")
    sb = signal_band(D["policy_balance_sheet_wow_pct"]["value"], pw, th["net_liquidity_wow_pct"], freq)
    D["policy_balance_sheet_wow_pct"].update({"signal": sb["signal"], "percentile": sb["percentile"], "thresholds": sb.get("thresholds", {})})
    D["net_liquidity_wow_pct"] = dict(D["policy_balance_sheet_wow_pct"], label="alias of policy_balance_sheet_wow_pct (alert/scenario key)")
    D["reserves_wow_pct"] = entry("reserves_wow_pct", S.pct_change_series(res), "Reserve balances Δ% w/w", freq, "%", cfg, status="fresh" if res else "unavailable",
                                  spec=th.get("reserves_wow_pct"), prev_level=pl.get("reserves_wow_pct"))
    ro = S.add_series(raw["str_lending"], raw["ltr_lending"]) if raw.get("ltr_lending") else raw["str_lending"]
    D["repo_offset"] = entry("repo_offset", ro, "Repo offset = STR + long-term ops (demand-driven)", freq, unit, cfg, usd_analog="none (repo-led framework)", status="fresh" if ro else "unavailable",
                             spec=th.get("repo_offset"), prev_level=pl.get("repo_offset"), equivalence_note=b["derived"]["repo_offset"].get("note"))
    rdr = S.merge_series(ro, res, lambda a, c: round(a / c, 4) if c else None)
    D["repo_dependence_ratio"] = entry("repo_dependence_ratio", rdr, "Repo dependence = (STR + LTR) / reserves", freq, "ratio", cfg, status="fresh" if rdr else "unavailable",
                                       spec=th.get("repo_dependence_ratio"), prev_level=pl.get("repo_dependence_ratio"), equivalence_note=b["derived"]["repo_dependence_ratio"]["note"])
    qt_w = S.diff_series(raw["apf_loan"])
    qt = []  # 13-week average weekly pace (APF moves stepwise on maturities/sales; weekly diff alone is mostly 0)
    for i in range(len(qt_w)):
        win = [v for _, v in qt_w[max(0, i - 25): i + 1]]
        qt.append((qt_w[i][0], round(sum(win) / len(win), 1)))
    D["qt_pace"] = entry("qt_pace", qt, "QT pace = Δ APF loan, 26-week average per week (negative = sales + maturities)", freq, unit, cfg, usd_analog="Δ SOMA", status="fresh" if qt else "unavailable",
                         spec=th.get("qt_pace"), prev_level=pl.get("qt_pace"), equivalence_note="announced pace ≈ −1,346/w (£70bn/yr); WATCH < −1,700, STRESS < −2,400")
    D["qt_pace_weekly_raw"] = entry("qt_pace_weekly_raw", qt_w, "Δ APF loan w/w (raw)", freq, unit, cfg, status="fresh" if qt_w else "unavailable")
    cd = [(d, -v) for d, v in S.diff_series(notes)]
    D["currency_drain"] = entry("currency_drain", cd, "Currency drain (−Δ notes in circulation, autonomous)", freq, unit, cfg, status="fresh" if cd else "unavailable",
                                equivalence_note="Outside money: not subtracted from the policy balance sheet (cross-currency rule)")
    rng = th["reserves"]["primary_absolute"]["boc_target_range"]
    dist = [(d, v - rng[1]) for d, v in res]
    D["reserves_vs_pmrr_ceiling"] = entry("reserves_vs_pmrr_ceiling", dist, "Reserves − PMRR ceiling (%d bn)" % (rng[1] // 1000), freq, unit, cfg, status="fresh" if dist else "unavailable",
                                          equivalence_note="the clock to watch under QT: weeks to the PMRR ceiling at the current pace")
    qv = D["qt_pace"]["value"]
    if dist and qv is not None and qv < 0 and dist[-1][1] > 0:
        D["reserves_vs_pmrr_ceiling"]["weeks_to_ceiling"] = round(dist[-1][1] / abs(qv))
    ctrf = E.get("ctrf", {}).get("value")
    phase = "QT" if (qv or 0) < 0 else "STEADY"
    D["balance_sheet_phase"] = {"label": "Balance-sheet phase", "value": None, "phase": phase, "status": "fresh", "date": E["apf_loan"]["date"],
                                "note": "APF run-off (gilt sales + maturities) with reserves supplied on demand via STR/ILTR"}
    # flags (orthogonal)
    flags: List[str] = []
    if ctrf and ctrf > 0:
        flags.append("CTRF_ACTIVE")
    rd_lvl = D["repo_dependence_ratio"].get("level")
    if rd_lvl in ("WATCH", "STRESS", "CRISIS"):
        flags.append("REPO_DEPENDENCE_ELEVATED")  # engine upgrades to *_STRESS only with price confirmation
    # score: reserves vs PMRR (absolute), balance-sheet Δ, QT pace, emergency
    C = Comps(cfg, "mean2")
    lvl = E["reserves"]["level"]
    above = E["reserves"].get("above_range")
    C.level("reserves_vs_pmrr", {"SAFE": 0.75 if above else 0.25, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}.get(lvl, 0.0))
    sig = D["policy_balance_sheet_wow_pct"]["signal"]
    C.flow("balance_sheet_band", 1.0 if sig == "RISK_ON" else -1.0 if sig == "RISK_OFF" else 0.0)
    C.level("qt_pace_level", {"SAFE": 0.0, "WATCH": -0.5, "STRESS": -1.0}.get(D["qt_pace"].get("level"), 0.0))
    if ctrf and ctrf > 0:
        C.event("ctrf", -2.0)
    score = C.score()
    alerts = [_alert("reserves", E["reserves"], "below PMRR floor 365bn = scarcity zone (price must confirm)"),
              _alert("ctrf", E.get("ctrf", {"level": "NO DATA"}), "any CTRF > 0 = contingent facility in use"),
              _alert("qt_pace", D["qt_pace"], "APF run-off faster than -10bn/w = STRESS"),
              _alert("repo_dependence_ratio", D["repo_dependence_ratio"], "informational unless SONIA ≥ Bank Rate")]
    label = "NO SIGNAL" if not res else ("INJECTION" if score >= 0.5 else "DRAIN" if score <= -0.5 else "NEUTRAL")
    tl = "NONE" if not res else "GREEN" if score >= 0.5 else "RED" if score <= -0.75 else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags, "components": C.to_dict(),
               "detail": "reserves %s (%s PMRR) · PBS %s · QT %s/w · repo/reserves %s" % (lvl, "above" if above else "inside" if E["reserves"].get("in_range") else "below",
                                                                                          sig, qv, D["repo_dependence_ratio"]["value"]), "alerts": alerts}
    hd = [d for d, _ in S.tail(res, 52)]
    rows = {k: [dict(v).get(d) for d in hd] for k, v in (("reserves", res), ("policy_balance_sheet", pbs), ("repo_offset", ro), ("apf_loan", raw["apf_loan"]),
                                                        ("str_lending", raw["str_lending"]), ("ltr_lending", raw["ltr_lending"]), ("notes_in_circulation", notes),
                                                        ("policy_balance_sheet_wow_pct", pw), ("qt_pace", qt))}
    history = {"dates": hd, "rows": rows, "signal_log": (prev or {}).get("history", {}).get("signal_log", [])[-52:]}
    if hd:
        history["signal_log"] = [x for x in history["signal_log"] if x.get("date") != hd[-1]] + [{"date": hd[-1], "label": label, "score": score, "note": signals["detail"]}]
    return _base(cfg["currency"], "central_bank", cfg, b, E, D, signals, history)


# ═══════════════════════ 2 · HM TREASURY / ONS PUBLIC SECTOR FINANCES ═══════════════════════
def build_fiscal(cfg: dict, ons: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["fiscal"]
    unit, freq = cfg["units"]["balance_sheet"], "monthly"
    pl = _prev_levels(prev)
    E = _entries(cfg, "fiscal", ons, freq, unit, pl, {})
    exp_, rec, cgncr = _ser(ons, b["series"]["cg_expenditure"]), _ser(ons, b["series"]["cg_receipts"]), _ser(ons, b["series"]["cgncr"])
    D: Dict[str, dict] = {}
    ns = S.merge_series(exp_, rec, lambda a, c: a - c)
    D["net_spending"] = entry("net_spending", ns, "Net spending = CG expenditure − receipts (NFA flow, before issuance)", freq, unit, cfg, usd_analog="Net Treasury Flow (Mosler)",
                              status="fresh" if ns else "unavailable", z_window=12, equivalence_note=b["derived"]["net_spending"]["sign"])
    yoy = []
    for i, (d, v) in enumerate(ns):
        if i >= 12:
            yoy.append((d, round(v - ns[i - 12][1], 2)))
    D["net_spending_yoy"] = entry("net_spending_yoy", yoy, "Net spending vs same month last year (seasonality-adjusted flow)", freq, unit, cfg, status="fresh" if yoy else "unavailable", z_window=12)
    sb = signal_band(D["net_spending_yoy"]["value"], yoy, {"window": "60m", "risk_on_above": b["thresholds"]["net_spending_yoy"]["injection_above"],
                                                           "risk_off_below": b["thresholds"]["net_spending_yoy"]["drain_below"]}, freq) if yoy else {"signal": "NO DATA", "percentile": None}
    D["net_spending_yoy"].update({"signal": sb["signal"], "percentile": sb.get("percentile")})
    z = S.rolling_zscore(cgncr, 24)
    zc = [(d, v) for d, v in z if v is not None]
    D["cgncr_zscore"] = entry("cgncr_zscore", zc, "CGNCR Z-score (24m) — issuance/cash drain intensity", freq, "σ", cfg, status="fresh" if zc else "unavailable", z_window=12,
                              equivalence_note=b["derived"]["cgncr_role"]["note"])
    zv = D["cgncr_zscore"]["value"]
    if zv is not None:
        D["cgncr_zscore"]["level"] = "STRESS" if abs(zv) >= b["thresholds"]["cgncr_zscore"]["extraordinary_above"] else "WATCH" if abs(zv) >= b["thresholds"]["cgncr_zscore"]["normal_within"] else "SAFE"
    c3 = S.rolling_sum(ns, 3)
    D["fiscal_flow_3m_cum"] = entry("fiscal_flow_3m_cum", c3, "Net spending 3-month cumulative", freq, unit, cfg, status="fresh" if c3 else "unavailable", z_window=12)
    nsz = S.rolling_zscore(ns, 24)
    nz = nsz[-1][1] if nsz and nsz[-1][1] is not None else None
    big = nz is not None and abs(nz) >= 2
    D["fiscal_big_month"] = {"label": "FISCAL_BIG_MONTH (|Z net spending 24m| ≥ 2)", "value": big, "zscore": nz, "status": "fresh" if nz is not None else "unavailable", "date": D["net_spending"]["date"]}
    reg = "NO DATA" if not yoy else "INJECTION" if sb["signal"] == "RISK_ON" else "DRAIN" if sb["signal"] == "RISK_OFF" else "NEUTRAL"
    cap = b.get("influence_cap", {}).get("cap", 0.5)
    raw_score = 0.0 if reg == "NO DATA" else (1.0 if reg == "INJECTION" else -1.0 if reg == "DRAIN" else 0.0) * (1.0 + min(1.0, abs(nz or 0) / 2))
    score = round(max(-cap * 2, min(cap * 2, raw_score)), 2)  # capped: monthly layer cannot flip the regime alone
    CF = Comps(cfg, "sum", -cap * 2, cap * 2).flow("net_spending_band_x_z", score)
    D["fiscal_regime"] = {"label": "Fiscal regime", "value": None, "regime": reg, "status": "fresh" if yoy else "unavailable", "date": D["net_spending"]["date"]}
    D["fiscal_regime_score"] = {"label": "Fiscal regime score (capped ±%s)" % cap, "value": score, "range": [-2, 2], "status": "fresh", "date": D["net_spending"]["date"]}
    D["dmo_gilt_auction"] = {"label": "DMO gilt auctions (cover / tail)", "value": None, "status": "unavailable", "date": None, "note": "Phase 3: per-event parser"}
    D["mmt_note"] = {"label": "MMT note", "value": None, "status": "fresh", "date": None, "text": b["derived"].get("mmt_note", "")}
    alerts = [_alert("cgncr_zscore", D["cgncr_zscore"], "|Z|≥2 = extraordinary cash requirement (issuance drain)"),
              {"metric": "net_spending_yoy", "level": "WATCH" if reg == "DRAIN" else "SAFE" if reg != "NO DATA" else "NO DATA", "value": D["net_spending_yoy"]["value"],
               "threshold": None, "status": D["net_spending_yoy"]["status"], "action_hint": "y/y net spending below p20 = fiscal drain"}]
    tl = "NONE" if reg == "NO DATA" else "GREEN" if reg == "INJECTION" else "RED" if reg == "DRAIN" else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": reg, "flags": ["FISCAL_BIG_MONTH"] if big else [], "components": CF.to_dict(),
               "detail": "net spending %s (y/y %s, %s) · CGNCR Z %s · monthly, ~3-week lag" % (D["net_spending"]["value"], D["net_spending_yoy"]["value"], sb["signal"], zv), "alerts": alerts}
    hd = [d for d, _ in S.tail(ns, 36)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("net_spending", ns), ("net_spending_yoy", yoy), ("cg_expenditure", exp_), ("cg_receipts", rec),
                                                                                  ("cgncr", cgncr), ("psnb_ex", _ser(ons, b["series"]["psnb_ex"])), ("cgncr_zscore", zc))},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": reg, "score": score}] if hd else []))[-36:]}
    return _base(cfg["currency"], "fiscal", cfg, b, E, D, signals, history)


# ═══════════════════════ 3 · BANKING TRANSMISSION (Money & Credit) ═══════════════════════
def build_banking(cfg: dict, data: Dict[str, Series], rates_block: Optional[dict] = None, prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["banking"]
    unit, freq = cfg["units"]["balance_sheet"], "monthly"
    E = _entries(cfg, "banking", data, freq, unit, {}, {})
    D: Dict[str, dict] = {}
    # flows: monthly-change series (already flows) → z-score 24m; stocks → m/m % change
    flow_keys = ["m4_lending_ex_change", "lending_to_individuals_change", "secured_lending_change", "consumer_credit_change", "pnfc_lending_change", "m4_ex_change"]
    stock_keys = ["household_m4", "mortgage_approvals"]
    chg: Dict[str, Optional[float]] = {}
    for k in flow_keys:
        ser = _ser(data, b["series"][k])
        e = entry(k + "_z", ser, E[k]["label"] + " (flow)", freq, unit, cfg, status="fresh" if ser else "unavailable", z_window=24)
        zz = e["zscore"]
        e["level"] = "NO DATA" if not ser else "STRESS" if zz is not None and abs(zz) >= 2 else "WATCH" if zz is not None and abs(zz) >= 1 else "SAFE"
        D[k + "_z"] = e
        chg[k] = e["value"]
    for k in stock_keys:
        ser = _ser(data, b["series"][k])
        mom = S.pct_change_series(ser)
        e = entry(k + "_mom_pct", mom, E[k]["label"] + " Δ% m/m", freq, "%", cfg, status="fresh" if mom else "unavailable", z_window=24)
        zz = e["zscore"]
        e["level"] = "NO DATA" if not mom else "STRESS" if zz is not None and abs(zz) >= 2 else "WATCH" if zz is not None and abs(zz) >= 1 else "SAFE"
        D[k + "_mom_pct"] = e
        chg[k] = e["value"]
    # aliases used by scenarios/alerts config keys
    D["pnfc_lending_mom_pct"] = dict(D["pnfc_lending_change_z"], label="alias: PNFC net lending flow")
    D["household_deposits_mom_pct"] = dict(D["household_m4_mom_pct"], label="alias: household M4 Δ% m/m")
    D["m4_lending_mom_pct"] = dict(D["m4_lending_ex_change_z"], label="alias: M4Lex flow")
    # 12m growth of M4Lex (context)
    ml = _ser(data, b["series"]["m4_lending_ex"])
    g = []
    for i, (d, v) in enumerate(ml):
        if i >= 12 and ml[i - 12][1]:
            g.append((d, round((v / ml[i - 12][1] - 1) * 100, 3)))
    D["m4_lending_ex_yoy_pct"] = entry("m4_lending_ex_yoy_pct", g, "M4Lex growth y/y %", freq, "%", cfg, status="fresh" if g else "unavailable", z_window=24)
    valid = [k for k in ("m4_lending_ex_change", "pnfc_lending_change", "lending_to_individuals_change", "household_m4", "mortgage_approvals") if chg.get(k) is not None]
    grn = sum(1 for k in valid if (chg[k] or 0) > 0)
    red = sum(1 for k in valid if (chg[k] or 0) < 0)
    n_valid = len(valid)
    if n_valid < b.get("signal_rule", {}).get("min_series_valid", 3):
        sig, tl, score = "NO SIGNAL", "NONE", 0.0
    elif red >= 4 or (red >= 3 and grn <= 1):
        sig, tl, score = "RED", "RED", -1.5
    elif grn >= 4 or (grn >= 3 and red <= 1):
        sig, tl, score = "GREEN", "GREEN", 1.0
    else:
        sig, tl, score = "YELLOW", "YELLOW", 0.0
    D["transmission_signal"] = {"label": "Transmission signal", "value": None, "signal": sig, "status": "fresh" if valid else "unavailable", "date": E["m4_lending_ex_change"]["date"],
                                "rule": "green if ≥4 of {M4Lex flow, PNFC flow, individuals flow, household M4 Δ, approvals Δ} > 0 (or 3 up / ≤1 down); red mirror; NO SIGNAL if < 3 valid", "valid_series": n_valid}
    alerts = [_alert(k + "_z", D[k + "_z"], "|Z|≥2 extraordinary monthly flow") for k in ("m4_lending_ex_change", "pnfc_lending_change", "consumer_credit_change")]
    signals = {"traffic_light": tl, "score": score, "label": sig, "flags": [],
               "detail": "%d/5 series valid · %d up / %d down · monthly, ~1-month lag" % (n_valid, grn, red), "alerts": alerts}
    hd = [d for d, _ in S.tail(ml, 24)]
    history = {"dates": hd, "rows": {k: [dict(_ser(data, b["series"][k])).get(d) for d in hd] for k in ("m4_lending_ex", "m4_lending_ex_change", "pnfc_lending_change", "lending_to_individuals_change",
                                                                                                         "secured_lending_change", "consumer_credit_change", "household_m4", "mortgage_approvals", "m4_ex")},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": sig, "score": score}] if hd else []))[-24:]}
    return _base(cfg["currency"], "banking", cfg, b, E, D, signals, history)


# ═══════════════════════ 4 · RATES / STERLING MONEY MARKET ═══════════════════════
def _persistent_level(vals: List[float], abs_spec: dict, n: int = 3) -> str:
    """Asymmetric floor rule: level from the LAST n prints (all must clear the bar) — single prints never escalate above WATCH."""
    if not vals:
        return "NO DATA"
    last = vals[-1]
    tail = vals[-n:]
    lvl = "SAFE"
    if last >= abs_spec["watch"]:
        lvl = "WATCH"  # early flag, single print
    if len(tail) == n and all(v >= abs_spec["stress"] for v in tail):
        lvl = "STRESS"
    if len(tail) == n and all(v >= abs_spec["crisis"] for v in tail):
        lvl = "CRISIS"
    return lvl


def build_rates(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["rates"]
    freq = "daily"
    pl = _prev_levels(prev)
    th = b["thresholds"]
    E: Dict[str, dict] = {}
    raw: Dict[str, Series] = {}
    for key, sc in b["series"].items():
        sid = sc.get("id")
        if sid:
            raw[key] = _ser(data, sc)
            E[key] = entry(key, raw[key], sc["label"], freq, "%", cfg, sid, sc.get("usd_analog"))
        else:
            E[key] = {"source_id": None, "label": sc["label"], "unit": "%", "frequency": freq, "status": "unavailable" if sc.get("status") != "derived" else "proxy", "value": None, "date": None,
                      "level": "NO DATA", "equivalence_note": sc.get("fallback") or sc.get("role") or sc.get("note", "")}
    pol, on = raw["policy_rate"], raw["overnight_rate"]
    # floor system: reserves remunerated at Bank Rate → deposit_rate = policy_rate
    E["deposit_rate"] = dict(entry("deposit_rate", pol, "Rate paid on reserves = Bank Rate", freq, "%", cfg, "derived:IUDBEDR", "IORB", status="proxy"))
    osf = [(d, round(v + 0.25, 4)) for d, v in pol]
    E["osf_ceiling"] = entry("osf_ceiling", osf, "OSF lending rate = Bank Rate + 25bp (reference ceiling)", freq, "%", cfg, "derived:IUDBEDR+0.25", "Primary credit rate", status="proxy")
    D: Dict[str, dict] = {}
    sp = S.merge_series(on, pol, lambda a, c: round((a - c) * 100, 2))
    D["overnight_minus_policy_bps"] = entry("overnight_minus_policy_bps", sp, "SONIA − Bank Rate (bps; floor system: normally −3/−5)", freq, "bps", cfg, usd_analog="SOFR − IORB",
                                            status="fresh" if sp else "unavailable", spec=th["overnight_minus_policy_bps"], prev_level=pl.get("overnight_minus_policy_bps"), z_window=30)
    absr = th["overnight_minus_policy_bps"]["secondary_absolute"]
    pers = _persistent_level([v for _, v in sp], absr)
    D["overnight_minus_policy_bps"]["percentile_level"] = D["overnight_minus_policy_bps"]["level"]
    D["overnight_minus_policy_bps"]["level"] = pers  # absolute-with-persistence is the primary reading (v0.2 C4)
    D["overnight_minus_policy_bps"]["persistence_rule"] = absr.get("persistence")
    last3 = [v for _, v in sp[-3:]]
    D["overnight_minus_policy_bps"]["friction_confirmed"] = bool(len(last3) == 3 and all(v >= 0 for v in last3))
    D["overnight_minus_deposit_bps"] = dict(D["overnight_minus_policy_bps"], label="alias (deposit rate = Bank Rate)")
    vs_osf = S.merge_series(on, osf, lambda a, c: round((a - c) * 100, 2))
    D["overnight_minus_osf_bps"] = entry("overnight_minus_osf_bps", vs_osf, "SONIA − OSF ceiling (bps; ≥ 0 = above the standing facility)", freq, "bps", cfg, status="fresh" if vs_osf else "unavailable", z_window=30)
    D["gc_minus_policy_bps"] = {"label": "GC repo − Bank Rate (bps)", "value": None, "status": "unavailable", "date": None, "level": "NO DATA", "unit": "bps",
                                "equivalence_note": "no free official sterling GC series; thresholds +10/+20/+30 ready (Nov-2025 spike calibration)"}
    c = S.merge_series(raw["bond_10y"], raw["bond_5y"], lambda a, b_: round((a - b_) * 100, 2))
    D["curve_10y_5y_bps"] = entry("curve_10y_5y_bps", c, "10Y − 5Y gilt par (bps)", freq, "bps", cfg, usd_analog="10Y − 2Y (2Y not in IADB)", status="fresh" if c else "unavailable", z_window=30)
    cv = D["curve_10y_5y_bps"]["value"]
    tc = th["curve_10y_5y_bps"]
    if cv is not None:
        D["curve_10y_5y_bps"]["level"] = "CRISIS" if cv < tc["deep_inversion_below"] else "STRESS" if cv < tc["inverted_below"] else "WATCH" if cv < tc["flat_below"] else "SAFE"
        D["curve_10y_5y_bps"]["curve_state"] = {"CRISIS": "DEEP INVERSION", "STRESS": "INVERTED", "WATCH": "FLAT"}.get(D["curve_10y_5y_bps"]["level"], "STEEPENING")
    c2 = S.merge_series(raw["bond_20y"], raw["bond_10y"], lambda a, b_: round((a - b_) * 100, 2))
    D["curve_20y_10y_bps"] = entry("curve_20y_10y_bps", c2, "20Y − 10Y gilt par (bps; long-end supply/term premium)", freq, "bps", cfg, status="fresh" if c2 else "unavailable", z_window=30)
    p5 = S.merge_series(pol, raw["bond_5y"], lambda a, b_: round((a - b_) * 100, 2))
    D["policy_minus_5y_bps"] = entry("policy_minus_5y_bps", p5, "Bank Rate − 5Y (bps; > 0 = market prices cuts)", freq, "bps", cfg, usd_analog="FF − 2Y", status="fresh" if p5 else "unavailable", z_window=30)
    pv = D["policy_minus_5y_bps"]["value"]
    tp = th["policy_minus_5y_bps"]
    if pv is not None:
        D["policy_minus_5y_bps"]["level"] = "STRESS" if pv > tp["tight_above"] else "WATCH" if pv > tp["normal_below"] else "SAFE"
    lvl = pers
    # calm floor = mildly positive (max +0.5); friction/stress dominate the downside
    comps = [{"SAFE": 0.25, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}.get(lvl, 0.0),
             {"SAFE": 0.25, "WATCH": 0.0, "STRESS": -0.5, "CRISIS": -1.0}.get(D["curve_10y_5y_bps"].get("level"), 0.0),
             {"SAFE": 0.0, "WATCH": 0.0, "STRESS": -0.5}.get(D["policy_minus_5y_bps"].get("level"), 0.0)]
    score = round(max(-2.0, min(2.0, sum(comps))), 2)
    label = "NO SIGNAL" if not sp else "FUNDING STRESS" if lvl in ("STRESS", "CRISIS") else "FLOOR FRICTION" if lvl == "WATCH" else "FLOOR INTACT"
    tl = "NONE" if not sp else "RED" if lvl in ("STRESS", "CRISIS") else "YELLOW" if lvl == "WATCH" or D["curve_10y_5y_bps"].get("level") in ("STRESS", "CRISIS") else "GREEN"
    alerts = [_alert("overnight_minus_policy_bps", D["overnight_minus_policy_bps"], "≥ −1 early flag; ≥ +3 for 3 sessions = STRESS; ≥ +10 = CRISIS"),
              _alert("overnight_minus_osf_bps", D["overnight_minus_osf_bps"], "≥ 0 = SONIA above the OSF ceiling"),
              _alert("curve_10y_5y_bps", D["curve_10y_5y_bps"], "negative = inverted"),
              _alert("policy_minus_5y_bps", D["policy_minus_5y_bps"], "> 30 = market prices deep cuts")]
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": [],
               "detail": "SONIA−Bank Rate %s bps (%s, pct %s) · 10Y−5Y %s · Bank Rate−5Y %s" % (D["overnight_minus_policy_bps"]["value"], lvl, D["overnight_minus_policy_bps"]["percentile_level"],
                                                                                           D["curve_10y_5y_bps"].get("curve_state"), pv), "alerts": alerts}
    hd = [d for d, _ in S.tail(sp, 120)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("overnight_minus_policy_bps", sp), ("overnight_minus_osf_bps", vs_osf), ("curve_10y_5y_bps", c), ("curve_20y_10y_bps", c2),
                                                                                  ("policy_minus_5y_bps", p5), ("policy_rate", pol), ("overnight_rate", on), ("bond_5y", raw["bond_5y"]), ("bond_10y", raw["bond_10y"]), ("bond_20y", raw["bond_20y"]))},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": label, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "rates", cfg, b, E, D, signals, history)
