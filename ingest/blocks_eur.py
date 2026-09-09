"""EUR block builders — config/eur.json v0.2 (triangulated 2026-09-09, changes E1–E15), desk's four layers:
  1 Eurosystem   — ILM daily (excess liquidity, deposit facility, current accounts, minimum reserves, autonomous factors, MRO+LTRO take-up, MLF),
                   WFS weekly (MRO, LTRO, MonPol securities, other securities, MPO liabilities), APP/PEPP holdings at amortised cost + scheduled redemptions;
                   dead-man anchors 1.5/1.0/0.75tn (no regime trigger), TOMO 30/100/250bn price-gated (E7), balance-sheet phase (13w Δ MonPol ±20bn),
                   APP+PEPP reconciliation (E4), residual autonomous-factor flow
  2 Treasury eq. — central government deposits at the Eurosystem (WFS L050100; Δ w/w, fiscal impulse 4w/13w), general government debt held,
                   Finanzagentur auctions (bid-to-cover, yield, retention, volume), TARGET balances (Δ 3m fragmentation, E13), GFS deficit (E1)
  3 Banking      — BSI M1/M3/loans growth, loan stocks → credit impulse in EUR (E10), MIR cost of credit (E3), BLS credit standards (E2)
  4 Rates        — €STR − DFR compression spread with anchors by liquidity regime (E5), dispersion R75−R25 (E6), compounded 3m, corridor position,
                   AAA curve 10−2, periphery premium (all-EA − AAA), BTP/OAT/Bonos − Bund monthly, EURIBOR 3M − DFR, EUR/USD
No triangulation of thresholds beyond the matrix: every anchor is either the desk proposal recorded in the config or an institutional citation."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from . import series as S
from .series import Series
from .thresholds import classify
from .scoring import Comps
from .blocks import entry, _prev_levels, _alert, _health, _base as _base0
from .blocks_gbp import _ser
from .blocks_usd import _freq, _latest_at_or_before, _clamp, _lvl

LEVEL_SCORE = {"SAFE": 0.5, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}


def _base(ccy, block, cfg, bcfg, E, D, signals, history):
    out = _base0(ccy, block, cfg, bcfg, E, D, signals, history)
    wired = {k: e for k, e in E.items() if bcfg["series"].get(k, {}).get("id")}
    out["source_health"] = _health(wired, len(wired))
    out["source_health"]["series_pending"] = len(E) - len(wired)
    return out


def _fq(f: str) -> str:
    return "quarterly" if f.startswith("quarter") else "event" if f.startswith("event") else _freq(f)


def _entries(cfg: dict, block: str, data: Dict[str, Series], unit: str, pl: Dict[str, str], th: dict) -> Dict[str, dict]:
    E: Dict[str, dict] = {}
    for key, sc in cfg["blocks"][block]["series"].items():
        ser = _ser(data, sc)
        fq = _fq(sc.get("freq", "weekly"))
        if fq == "quarterly":   # portal quarter end → quarter start, with the ~90-day publication lag allowed in freshness
            ser = [((d[:5] + {"03": "01", "06": "04", "09": "07", "12": "10"}.get(d[5:7], d[5:7]) + "-01"), v) for d, v in ser]
        if sc.get("schedule"):  # forward-looking schedule (redemptions): the entry shows the current month; the block keeps the full path
            today = date.today().isoformat()[:7]
            ser = [(d, v) for d, v in ser if d[:7] <= today]
        e = entry(key, ser, sc["label"], fq, sc.get("unit", unit), cfg, sc.get("id"), sc.get("usd_analog"), status=None if sc.get("id") else "unavailable",
                  spec=th.get(key), prev_level=pl.get(key), z_window=30 if fq == "daily" else 26 if fq == "weekly" else 12 if fq == "monthly" else 8,
                  lag_days=90 if fq == "quarterly" else 0)
        for f in ("display_only", "group"):
            if sc.get(f):
                e[f] = sc[f]
        if sc.get("note") or sc.get("role"):
            e["equivalence_note"] = sc.get("note") or sc.get("role")
        if not sc.get("id"):
            e["status"] = "unavailable"
            e["pending"] = sc.get("status", "pending")
        E[key] = e
    return E


def _thin(e: dict, spec: Optional[dict], freq: str) -> bool:
    """percentile history below min_n (thresholds.percentile_level never escalates then; neither do the two-sided extensions here)."""
    n = (e.get("thresholds") or {}).get("n")
    if n is None or e.get("percentile") is None:
        return True
    return n < (spec or {}).get("min_n", {"daily": 120, "weekly": 26, "monthly": 12}.get(freq, 20))


def _col(dates: List[str], ser: Series, ffill: bool = False) -> List[Optional[float]]:
    m = {d: v for d, v in ser}
    return [(_latest_at_or_before(ser, d) if ffill else m.get(d)) for d in dates]


def _spread(a: Series, b_step: Series, mult: float = 100.0, nd: int = 1) -> Series:
    """a(d) − b(latest at or before d), step series b forward-filled (policy rates are published on change dates only)."""
    out: Series = []
    for d, v in a:
        bv = _latest_at_or_before(b_step, d)
        if v is not None and bv is not None:
            out.append((d, round((v - bv) * mult, nd)))
    return out


def _estr_minus_dfr(data: Dict[str, Series], cfg: dict) -> Series:
    r = cfg["blocks"]["rates"]["series"]
    return _spread(_ser(data, r["estr"]), _ser(data, r["dfr"]))


def _anchor_spec(th: dict, excess_latest: Optional[float]) -> Tuple[dict, str]:
    """E5: anchors 0/5/10 while excess liquidity > 1.5tn; 5/10/15 below (€STR expected to migrate toward the MRO)."""
    spec = dict(th["estr_minus_dfr_bps"])
    alt = spec.pop("anchors_by_liquidity_regime", None)
    if alt and excess_latest is not None and excess_latest < alt.get("excess_liquidity_below", 0):
        spec.update({k: alt[k] for k in ("watch_above", "stress_above", "crisis_above") if k in alt})
        return spec, "scarce-liquidity anchors (excess < %.1ftn): WATCH ≥ %s · STRESS ≥ %s · CRISIS ≥ %s" % (alt["excess_liquidity_below"] / 1e6, alt["watch_above"], alt["stress_above"], alt["crisis_above"])
    return spec, "abundant-liquidity anchors (excess ≥ 1.5tn): WATCH > %s · STRESS ≥ %s · CRISIS ≥ %s" % (spec.get("watch_above"), spec.get("stress_above"), spec.get("crisis_above"))


# ═══════════════════════ 1 · EUROSYSTEM LIQUIDITY ═══════════════════════
def build_central_bank(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["central_bank"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "central_bank", data, unit, pl, th)
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    ex, df, ca, mrr, nliq, tomo, mlf = raw["excess_liquidity"], raw["deposit_facility"], raw["current_accounts"], raw["minimum_reserves"], raw["net_autonomous_factors"], raw["omo_takeup"], raw["mlf_usage"]
    monpol, mro_w, ltro_w = raw["monpol_securities"], raw["mro_weekly"], raw["ltro_weekly"]
    app, pepp = raw.get("app_holdings", []), raw.get("pepp_holdings", [])
    D: Dict[str, dict] = {}
    exv = E["excess_liquidity"]["value"]
    # ILM daily: business days only (weekend rows repeat Friday's value on the portal)
    ex_bd = [(d, v) for d, v in ex if date.fromisoformat(d).weekday() < 5]
    dod = S.diff_series(ex_bd, 1)
    D["excess_liquidity_dod"] = entry("excess_liquidity_dod", dod, "Δ excess liquidity d/d (business days)", "daily", unit, cfg, status="fresh" if dod else "unavailable", z_window=30)
    wow = S.diff_series(ex_bd, 5)
    D["excess_liquidity_wow"] = entry("excess_liquidity_wow", wow, "Δ excess liquidity 5 sessions (percentile, two-sided)", "daily", unit, cfg, status="fresh" if wow else "unavailable",
                                      spec=th.get("excess_liquidity_wow"), prev_level=pl.get("excess_liquidity_wow"), z_window=30)
    wv = D["excess_liquidity_wow"]["value"]
    wp = D["excess_liquidity_wow"]["percentile"]
    if wv is not None and wp is not None and not _thin(D["excess_liquidity_wow"], th.get("excess_liquidity_wow"), "daily"):
        # two-sided: high percentile of a rise = injection watch, low percentile of a fall = drain watch (level already set for the low side)
        D["excess_liquidity_wow"]["direction"] = "INJECTION" if wv > 0 else "DRAIN" if wv < 0 else "FLAT"
        if wp >= 90 and wv > 0:
            D["excess_liquidity_wow"]["level"] = "WATCH" if wp < 97 else "STRESS"
    t20 = S.diff_series(ex_bd, 20)
    D["excess_liquidity_trend_20s"] = entry("excess_liquidity_trend_20s", t20, "Δ excess liquidity 20 sessions (trend; percentile 156w)", "daily", unit, cfg, status="fresh" if t20 else "unavailable",
                                            spec=th.get("excess_liquidity_wow"), prev_level=None, z_window=30)
    share = S.merge_series(df, ex, lambda a, c: round(a / c * 100, 2) if c else None)
    share = [(d, v) for d, v in share if v is not None]
    D["df_share_of_excess"] = entry("df_share_of_excess", share, "Deposit facility / excess liquidity (%)", "daily", "%", cfg, status="fresh" if share else "unavailable", z_window=30)
    rel = S.merge_series(tomo, ex, lambda a, c: round(a / c * 100, 3) if c else None)
    rel = [(d, v) for d, v in rel if v is not None]
    D["omo_reliance_share"] = entry("omo_reliance_share", rel, "MRO + LTRO take-up / excess liquidity (%) — read with the absolute stock", "daily", "%", cfg, status="fresh" if rel else "unavailable",
                                    spec=th.get("omo_reliance_share"), prev_level=pl.get("omo_reliance_share"), z_window=30)
    # E7: TOMO quantity alone is structural under full allotment; escalation needs price confirmation (€STR − DFR ≥ WATCH)
    sp = _estr_minus_dfr(data, cfg)
    spec_sp, _ = _anchor_spec(cfg["blocks"]["rates"]["thresholds"], exv)
    sp_lvl = classify(sp[-1][1], sp, spec_sp, "daily")["level"] if sp else "NO DATA"
    price_ok = sp_lvl in ("WATCH", "STRESS", "CRISIS")
    tomo_lvl = _lvl(E["omo_takeup"])
    tomo_read = "NO DATA" if E["omo_takeup"]["value"] is None else "ROUTINE" if tomo_lvl == "SAFE" else ("STRUCTURAL (no price confirmation)" if not price_ok else "SCARCITY-CONFIRMED (%s)" % tomo_lvl)
    E["omo_takeup"]["escalation"] = tomo_read
    if tomo_lvl in ("STRESS", "CRISIS") and not price_ok:
        E["omo_takeup"]["level_quantity_only"] = tomo_lvl
        E["omo_takeup"]["level"] = "WATCH"
    D["omo_escalation"] = {"label": "MRO/LTRO take-up escalation (E7: quantity + €STR − DFR price gate)", "value": E["omo_takeup"]["value"], "unit": unit, "date": E["omo_takeup"]["date"],
                           "status": E["omo_takeup"]["status"], "level": E["omo_takeup"]["level"], "badge": tomo_read, "price_gate": {"estr_minus_dfr_bps": sp[-1][1] if sp else None, "level": sp_lvl, "confirmed": price_ok}}
    # WFS weekly: QT pace and balance-sheet phase
    r13 = [(monpol[i][0], round(monpol[i][1] - monpol[i - 13][1], 1)) for i in range(13, len(monpol))]
    D["monpol_runoff_13w"] = entry("monpol_runoff_13w", r13, "Δ 13 weeks of MonPol securities (QT pace, WFS)", "weekly", unit, cfg, status="fresh" if r13 else "unavailable", z_window=26)
    c13 = D["monpol_runoff_13w"]["value"]
    phase = "NO DATA" if c13 is None else "QT" if c13 < -20000 else "QE" if c13 > 20000 else "STEADY"
    D["balance_sheet_phase"] = {"label": "Balance-sheet phase (13w Δ MonPol securities: < −20bn QT · > +20bn QE)", "value": c13, "phase": phase, "unit": unit,
                                "status": "fresh" if c13 is not None else "unavailable", "date": E["monpol_securities"]["date"]}
    wk = S.diff_series(monpol, 1)
    D["monpol_wow"] = entry("monpol_wow", wk, "Δ MonPol securities w/w (WFS)", "weekly", unit, cfg, status="fresh" if wk else "unavailable", z_window=26)
    # E4: APP + PEPP (monthly, amortised cost) vs WFS A070100
    rec: Series = []
    for d, v in monpol:
        a, p = _latest_at_or_before(app, d), _latest_at_or_before(pepp, d)
        if a is not None and p is not None and (a + p):
            rec.append((d, round((v - (a + p)) / (a + p) * 100, 2)))
    D["app_pepp_reconciliation"] = entry("app_pepp_reconciliation", rec, "WFS MonPol securities − (APP + PEPP holdings) in % (E4: within ±1% once both months are in)", "weekly", "%", cfg,
                                         status="fresh" if rec else "unavailable", z_window=26)
    rv = D["app_pepp_reconciliation"]["value"]
    D["app_pepp_reconciliation"]["badge"] = "NO DATA" if rv is None else "RECONCILED" if abs(rv) <= 1 else "MONTH LAG" if abs(rv) <= 3 else "CHECK"
    tot = S.add_series(app, pepp) if app and pepp else []
    D["app_pepp_total"] = entry("app_pepp_total", tot, "APP + PEPP holdings at amortised cost (monthly, ECB files)", "monthly", unit, cfg, status="fresh" if tot else "unavailable", z_window=12)
    # scheduled redemptions (QT expected): next 3 calendar months from the APP/PEPP redemption files
    red = S.add_series(S.clean(data.get("APP:redemptions", [])), S.clean(data.get("PEPP:redemptions", [])))
    today = date.today()
    nxt = [(d, v) for d, v in red if date.fromisoformat(d) >= today.replace(day=1)][:3]
    D["qt_scheduled_3m"] = {"label": "Scheduled APP + PEPP redemptions, next 3 months (ECB redemption files; no reinvestment since Dec-2024)", "value": round(sum(v for _, v in nxt), 1) if nxt else None,
                            "unit": unit, "status": "fresh" if nxt else "unavailable", "date": E["excess_liquidity"]["date"], "through": nxt[-1][0][:7] if nxt else None, "months": [{"month": d[:7], "amount": v} for d, v in nxt]}
    # residual daily flow (autonomous factors incl. government deposits, coincident)
    res_flow: Series = []
    tm = {d: v for d, v in tomo}
    for i in range(1, len(ex_bd)):
        d0, d1 = ex_bd[i - 1][0], ex_bd[i][0]
        if d0 in tm and d1 in tm:
            res_flow.append((d1, round((ex_bd[i][1] - ex_bd[i - 1][1]) - (tm[d1] - tm[d0]), 1)))
    D["residual_flow_daily"] = entry("residual_flow_daily", res_flow, "Δ excess liquidity − Δ OMO take-up (autonomous factors, coincident)", "daily", unit, cfg, status="fresh" if res_flow else "unavailable", z_window=30)
    # reconciliation: EXLIQ ≈ DF + CA − MRR
    chk = None
    if exv is not None and E["deposit_facility"]["value"] is not None and E["current_accounts"]["value"] is not None and E["minimum_reserves"]["value"] is not None:
        calc = E["deposit_facility"]["value"] + E["current_accounts"]["value"] - E["minimum_reserves"]["value"]
        chk = round((exv - calc) / calc * 100, 3) if calc else None
    D["exliq_identity_check"] = {"label": "Excess liquidity − (DF + CA − MRR), %", "value": chk, "status": "fresh" if chk is not None else "unavailable", "date": E["excess_liquidity"]["date"], "unit": "%",
                                 "badge": "NO DATA" if chk is None else "OK" if abs(chk) <= 0.5 else "MISMATCH"}
    # signals
    flags: List[str] = []
    if tomo_lvl != "SAFE" and E["omo_takeup"]["value"] is not None:
        flags.append("MRO_RELIANCE")
    if _lvl(E["mlf_usage"]) != "SAFE" and E["mlf_usage"]["value"] is not None:
        flags.append("MLF_USED")
    if phase in ("QT", "QE"):
        flags.append("PHASE_" + phase)
    ex_lvl = _lvl(E["excess_liquidity"])
    C = Comps(cfg, "mean2")
    C.level("excess_liquidity_level", LEVEL_SCORE.get(ex_lvl, 0.0))
    # flow components in absolute scale (percentiles stay informational: under QT the distribution of Δ is negative, so a small rise
    # would read as p90 'injection' — the desk reads the sign and size vs the stock instead): Δ5s vs 1 % of excess liquidity, Δ20s vs 2 %
    tv = D["excess_liquidity_trend_20s"]["value"]
    if wv is not None and exv:
        C.flow("excess_wow_vs_stock", _clamp(wv / (0.01 * exv), -1.0, 1.0))
    if tv is not None and exv:
        C.flow("excess_20s_vs_stock", _clamp(tv / (0.02 * exv), -1.0, 1.0))
    C.level("phase", {"QT": -0.5, "QE": 0.75}.get(phase, 0.0))
    C.level("tomo_level", -1.0 if (tomo_lvl in ("STRESS", "CRISIS") and price_ok) else -0.25 if tomo_lvl != "SAFE" and E["omo_takeup"]["value"] is not None else 0.0)
    if "MLF_USED" in flags:
        C.event("mlf_used", -0.5)
    score = C.score() if ex else 0.0
    if ex_lvl == "CRISIS":
        score = -2.0
    alerts = [_alert("excess_liquidity", E["excess_liquidity"], "dead-man anchors 1.5/1.0/0.75tn (no regime trigger) — scarcity needs €STR price confirmation"),
              _alert("omo_takeup", E["omo_takeup"], "≥ 30bn structural watch · ≥ 100bn stress only with €STR ≥ WATCH · ≥ 250bn crisis"),
              _alert("mlf_usage", E["mlf_usage"], "routine use is a few million; ≥ 1bn = a bank paying the ceiling"),
              _alert("excess_liquidity_wow", D["excess_liquidity_wow"], "5-session Δ beyond p10/p90 = unusual drain/injection week")]
    label = "NO SIGNAL" if not ex else ("INJECTION" if score >= 0.5 else "DRAIN" if score <= -0.5 else "NEUTRAL")
    tl = "NONE" if not ex else "GREEN" if score >= 0.5 else "RED" if score <= -0.75 else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags, "components": C.to_dict(),
               "detail": "excess liquidity %s M (%s) · Δ5s %s (p%s) · TOMO %s M (%s) · MLF %s M · €STR−DFR %s bp (%s) · MonPol 13w %s · phase %s · APP+PEPP rec %s" % (
                   exv, ex_lvl, wv, wp, E["omo_takeup"]["value"], tomo_read, E["mlf_usage"]["value"], sp[-1][1] if sp else None, sp_lvl, c13, phase, D["app_pepp_reconciliation"]["badge"]),
               "alerts": alerts}
    dates = [d for d, _ in ex_bd][-60:]
    spm = {d: v for d, v in sp}
    history = {"dates": dates,
               "rows": {"excess_liquidity": _col(dates, ex), "deposit_facility": _col(dates, df), "current_accounts": _col(dates, ca), "minimum_reserves": _col(dates, mrr),
                        "net_autonomous_factors": _col(dates, nliq), "omo_takeup": _col(dates, tomo), "mlf_usage": _col(dates, mlf), "excess_liquidity_dod": _col(dates, dod),
                        "residual_flow_daily": _col(dates, res_flow), "estr_minus_dfr_bps": [spm.get(d) for d in dates]},
               "weekly_dates": [d for d, _ in monpol][-52:],
               "weekly_rows": {k: _col([d for d, _ in monpol][-52:], s) for k, s in (("mro_weekly", mro_w), ("ltro_weekly", ltro_w), ("monpol_securities", monpol), ("other_securities", raw["other_securities"]),
                                                                                    ("mpo_liabilities", raw["mpo_liabilities"]), ("monpol_wow", wk), ("monpol_runoff_13w", r13))},
               "monthly": {"dates": [d for d, _ in tot][-24:], "app": _col([d for d, _ in tot][-24:], app), "pepp": _col([d for d, _ in tot][-24:], pepp), "redemptions": _col([d for d, _ in tot][-24:], red)},
               "signal_log": [{"date": d, "label": "inject" if v > 0 else "drain", "score": v, "note": "Δ excess liquidity 5s"} for d, v in wow[-15:]][::-1]}
    return _base("EUR", "central_bank", cfg, b, E, D, signals, history)


# ═══════════════════════ 2 · TREASURY EQUIVALENT ═══════════════════════
def build_fiscal(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None, aux: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["fiscal"]
    aux = aux or {}
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "fiscal", data, unit, pl, th)
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    gd = raw["govt_deposits"]
    D: Dict[str, dict] = {}
    gw = S.diff_series(gd, 1)
    D["govt_deposits_wow"] = entry("govt_deposits_wow", gw, "Δ w/w central government deposits at the Eurosystem (+ = drain from excess liquidity)", "weekly", unit, cfg,
                                   status="fresh" if gw else "unavailable", spec=th.get("govt_deposits_wow"), prev_level=pl.get("govt_deposits_wow"), z_window=26)
    gwv, gwp = D["govt_deposits_wow"]["value"], D["govt_deposits_wow"]["percentile"]
    if gwv is not None and gwp is not None and not _thin(D["govt_deposits_wow"], th.get("govt_deposits_wow"), "weekly") and gwp <= 10:
        D["govt_deposits_wow"]["level"] = "WATCH" if gwp > 3 else "STRESS"     # two-sided: a large fall is an injection watch
    D["govt_deposits_wow"]["direction"] = None if gwv is None else "DRAIN" if gwv > 0 else "INJECTION" if gwv < 0 else "FLAT"
    for n, key in ((4, "fiscal_impulse_4w"), (13, "fiscal_impulse_13w")):
        imp = [(gd[i][0], round(-(gd[i][1] - gd[i - n][1]), 1)) for i in range(n, len(gd))]
        D[key] = entry(key, imp, "Fiscal impulse %dw = −Δ%d weeks of government deposits (+ = cash released into excess liquidity)" % (n, n), "weekly", unit, cfg,
                       status="fresh" if imp else "unavailable", spec=th.get(key), prev_level=pl.get(key), z_window=26)
    i4 = D["fiscal_impulse_4w"]
    thin = _thin(i4, th.get("fiscal_impulse_4w"), "weekly")
    i4["direction"] = None if i4["value"] is None else "INJECTION" if i4["value"] > 0 else "DRAIN" if i4["value"] < 0 else "FLAT"
    i4["thin_history"] = thin
    # TARGET fragmentation: |IT| + |ES| + |FR| liabilities, Δ 3 months (E13)
    tg = [raw[k] for k in ("target_it", "target_es", "target_fr")]
    frag_lvl: Series = []
    if all(tg):
        dates = sorted(set(d for d, _ in tg[0]) & set(d for d, _ in tg[1]) & set(d for d, _ in tg[2]))
        ms = [{d: v for d, v in s} for s in tg]
        frag_lvl = [(d, round(sum(abs(m[d]) for m in ms), 1)) for d in dates]
    frag = S.diff_series(frag_lvl, 3)
    D["target_fragmentation"] = entry("target_fragmentation", frag, "TARGET fragmentation: Δ 3m of |IT| + |ES| + |FR| liabilities (+ = periphery losing reserves to the core)", "monthly", unit, cfg,
                                      status="fresh" if frag else "unavailable", spec=th.get("target_fragmentation"), prev_level=pl.get("target_fragmentation"), z_window=12)
    D["target_periphery_level"] = entry("target_periphery_level", frag_lvl, "|IT| + |ES| + |FR| TARGET liabilities (level)", "monthly", unit, cfg, status="fresh" if frag_lvl else "unavailable", z_window=12)
    # Finanzagentur auctions
    bc, yl, ret, vol = raw["de_auction_bid_to_cover"], raw["de_auction_avg_yield"], raw["de_auction_retention"], S.clean(data.get("DE:volume", []))
    bcv = E["de_auction_bid_to_cover"]["value"]
    bc_mean = round(sum(v for _, v in bc[-26:]) / len(bc[-26:]), 2) if bc else None
    E["de_auction_bid_to_cover"]["badge"] = "NO DATA" if bcv is None else "WEAK" if bcv < 1.2 else "SOFT" if bcv < 1.5 else "STRONG" if bcv >= 2.0 else "NORMAL"
    E["de_auction_bid_to_cover"]["avg_26"] = bc_mean
    E["de_auction_bid_to_cover"]["level"] = "NO DATA" if bcv is None else "STRESS" if bcv < 1.0 else "WATCH" if bcv < 1.2 else "SAFE"
    sup4: Series = []
    for i, (d, _) in enumerate(vol):
        d0 = (date.fromisoformat(d) - timedelta(days=28)).isoformat()
        sup4.append((d, round(sum(v for dd, v in vol if d0 < dd <= d), 1)))
    D["de_supply_4w"] = entry("de_supply_4w", sup4, "Bund/Bubill issuance volume, rolling 4 weeks (Finanzagentur)", "event", unit, cfg, status="fresh" if sup4 else "unavailable", z_window=8)
    bills = S.clean(data.get("DE:bills_bid_to_cover", []))
    bonds = S.clean(data.get("DE:bonds_bid_to_cover", []))
    D["de_bills_bid_to_cover"] = entry("de_bills_bid_to_cover", bills, "Bubill bid-to-cover (latest auction)", "event", "x", cfg, status="fresh" if bills else "unavailable", z_window=8)
    D["de_bonds_bid_to_cover"] = entry("de_bonds_bid_to_cover", bonds, "Bund/Bobl/Schatz/Green bid-to-cover (latest auction)", "event", "x", cfg, status="fresh" if bonds else "unavailable", z_window=8)
    # GFS deficit: structural fiscal stance (MMT: deficit = net financial assets injected; sign kept as published, negative = deficit)
    dv, pv = E["ea_deficit_gdp"]["value"], E["ea_primary_deficit_gdp"]["value"]
    stance = "NO DATA" if dv is None else "SURPLUS (drain)" if dv >= 0 else "SMALL DEFICIT" if dv > -1.5 else "DEFICIT (injection)" if dv > -3 else "LARGE DEFICIT (injection)"
    D["fiscal_stance_structural"] = {"label": "Euro-area general government balance (% GDP, GFS quarterly) — structural stance", "value": dv, "primary": pv, "unit": "% GDP", "badge": stance,
                                     "status": E["ea_deficit_gdp"]["status"], "date": E["ea_deficit_gdp"]["date"]}
    # fiscal regime: impulse percentile (156w) → INJECTION ≥ p80 / DRAIN ≤ p20; structural deficit and auction health as secondary components
    ip = i4["percentile"]
    imp_comp = 0.0 if (ip is None or thin) else _clamp((ip - 50) / 30, -1.0, 1.0)
    struct_comp = 0.0 if dv is None else _clamp(-dv / 3, -1.0, 1.0)      # −3% GDP deficit → +1
    auc_comp = 0.0 if bcv is None else (-1.0 if bcv < 1.2 else -0.5 if bcv < 1.5 else 0.25)
    CF = Comps(cfg, "weighted").flow("impulse_4w_percentile", imp_comp, 0.5).level("structural_deficit", struct_comp, 0.35).level("auction_health", auc_comp, 0.15)
    score = CF.score()
    reg = "NO DATA" if not gd else "INJECTION" if (ip is not None and ip >= 80) else "DRAIN" if (ip is not None and ip <= 20) else "NEUTRAL"
    D["fiscal_regime"] = {"label": "Fiscal regime (weekly rule: impulse 4w ≥ p80 INJECTION · ≤ p20 DRAIN · else NEUTRAL)", "value": None, "regime": reg, "status": "fresh" if gd else "unavailable",
                          "date": E["govt_deposits"]["date"], "inputs": {"impulse_4w": i4["value"], "percentile": ip, "thin_history": thin, "deficit_gdp": dv, "bid_to_cover": bcv},
                          "components": {"impulse": round(imp_comp, 2), "structural": round(struct_comp, 2), "auctions": auc_comp, "weights": [0.5, 0.35, 0.15]}}
    flags: List[str] = []
    if D["govt_deposits_wow"]["level"] in ("STRESS", "CRISIS"):
        flags.append("GOVT_DEPOSIT_JUMP")
    if _lvl(D["target_fragmentation"]) in ("STRESS", "CRISIS"):
        flags.append("TARGET_FRAGMENTATION")
    if bcv is not None and bcv < 1.2:
        flags.append("WEAK_AUCTION")
    if dv is not None and dv <= -3:
        flags.append("STRUCTURAL_DEFICIT_INJECTION")
    alerts = [_alert("govt_deposits_wow", D["govt_deposits_wow"], "beyond p90/p97 = government cash build (drain) or release (injection) of unusual size"),
              _alert("fiscal_impulse_4w", i4, "≤ p20 = 4-week cash build draining excess liquidity"),
              _alert("target_fragmentation", D["target_fragmentation"], "periphery TARGET liabilities rising fast = fragmentation"),
              _alert("de_auction_bid_to_cover", E["de_auction_bid_to_cover"], "< 1.2 weak demand · < 1.0 uncovered")]
    label = "NO SIGNAL" if not gd else ("INJECTION" if score >= 0.5 else "DRAIN" if score <= -0.5 else "NEUTRAL")
    tl = "NONE" if not gd else "GREEN" if score >= 0.5 else "RED" if score <= -0.75 else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags, "components": CF.to_dict(),
               "detail": "govt deposits %s M (Δw %s, p%s) · impulse 4w %s (p%s%s) · 13w %s · deficit %s%% GDP (%s) · DE b/c %s (%s, avg26 %s) · TARGET Δ3m %s · rule %s" % (
                   E["govt_deposits"]["value"], gwv, gwp, i4["value"], ip, ", thin" if thin else "", D["fiscal_impulse_13w"]["value"], dv, stance, bcv, E["de_auction_bid_to_cover"]["badge"], bc_mean,
                   D["target_fragmentation"]["value"], reg),
               "alerts": alerts}
    wd = [d for d, _ in gd][-52:]
    ad = [d for d, _ in bc][-40:]
    md = [d for d, _ in frag_lvl][-36:]
    imp4 = [(gd[i][0], round(-(gd[i][1] - gd[i - 4][1]), 1)) for i in range(4, len(gd))]
    history = {"dates": wd, "rows": {"govt_deposits": _col(wd, gd), "govt_deposits_wow": _col(wd, gw), "fiscal_impulse_4w": _col(wd, imp4), "govt_debt_held": _col(wd, raw["govt_debt_held"])},
               "auction_dates": ad, "auction_rows": {"bid_to_cover": _col(ad, bc), "avg_yield": _col(ad, yl), "retention": _col(ad, ret), "volume": _col(ad, vol), "supply_4w": _col(ad, sup4)},
               "auction_lines": list(aux.get("de_rows") or [])[-30:],
               "monthly_dates": md, "monthly_rows": {"target_de": _col(md, raw["target_de"]), "target_it": _col(md, raw["target_it"]), "target_es": _col(md, raw["target_es"]), "target_fr": _col(md, raw["target_fr"]),
                                                     "periphery_level": _col(md, frag_lvl), "fragmentation_3m": _col(md, frag)},
               "signal_log": [{"date": d, "label": "inject" if v > 0 else "drain", "score": v, "note": "−Δw govt deposits"} for d, v in [(d, -v) for d, v in gw[-15:]]][::-1]}
    return _base("EUR", "fiscal", cfg, b, E, D, signals, history)


# ═══════════════════════ 3 · BANKING TRANSMISSION ═══════════════════════
def build_banking(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["banking"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "banking", data, "%", pl, th)
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    D: Dict[str, dict] = {}
    stock = S.add_series(raw["loans_nfc_stock"], raw["loans_hh_stock"])
    ci = S.diff_series(stock, 3)
    D["credit_impulse"] = entry("credit_impulse", ci, "Credit impulse: Δ 3m of loans to NFCs + households (EUR millions, BSI stocks — E10)", "monthly", cfg["units"]["balance_sheet"], cfg,
                                status="fresh" if ci else "unavailable", z_window=12)
    dfr = _ser(data, cfg["blocks"]["rates"]["series"]["dfr"])
    for k, key in (("mir_nfc_cost", "mir_nfc_minus_dfr_bps"), ("mir_hh_cost", "mir_hh_minus_dfr_bps")):
        s = _spread(raw[k], dfr)
        D[key] = entry(key, s, "%s − DFR (bps): policy pass-through to the cost of credit" % ("NFC composite cost of borrowing" if k == "mir_nfc_cost" else "Household mortgage cost"), "monthly", "bps", cfg,
                       status="fresh" if s else "unavailable", z_window=12)
    m3, ln, lh = E["m3_yoy"]["value"], E["loans_nfc_yoy"]["value"], E["loans_hh_yoy"]["value"]
    if m3 is None or ln is None or lh is None:
        sig, txt = "NONE", "BSI: NO SIGNAL — growth series unavailable"
    elif m3 > 3 and ln > 2 and lh > 1:
        sig, txt = "GREEN", "BSI: GREEN — broad money and credit expanding (M3 > 3, NFC > 2, HH > 1)"
    elif m3 < 1 or ln < 0:
        sig, txt = "RED", "BSI: RED — money or NFC credit contracting (M3 < 1 or NFC < 0)"
    else:
        sig, txt = "YELLOW", "BSI: YELLOW — mixed / transitional"
    D["transmission_signal"] = {"label": "Transmission signal (v5 rule: M3 > 3 & loans NFC > 2 & HH > 1 GREEN · M3 < 1 or NFC < 0 RED)", "value": None, "signal": sig, "detail": txt,
                                "status": "fresh" if sig != "NONE" else "unavailable", "date": E["m3_yoy"]["date"]}
    bn, bh = E["bls_standards_nfc"]["value"], E["bls_standards_hh"]["value"]
    D["bls_read"] = {"label": "BLS credit standards (net % of banks tightening; + = tighter)", "value": bn, "hh": bh, "unit": "net %", "status": E["bls_standards_nfc"]["status"], "date": E["bls_standards_nfc"]["date"],
                     "badge": "NO DATA" if bn is None else "TIGHTENING" if bn >= 10 else "EASING" if bn <= -10 else "BROADLY UNCHANGED"}
    civ = D["credit_impulse"]["value"]
    flags: List[str] = []
    if sig == "RED":
        flags.append("TRANSMISSION_WEAK")
    if bn is not None and bn >= 10:
        flags.append("BLS_TIGHTENING")
    comps = [{"GREEN": 1.0, "RED": -1.0}.get(sig, 0.0)]
    if civ is not None:
        comps.append(0.5 if civ > 0 else -0.5)
    if bn is not None:
        comps.append(-0.5 if bn >= 10 else 0.25 if bn <= -10 else 0.0)
    score = _clamp(sum(comps) / len(comps) * 2) if sig != "NONE" else 0.0
    alerts = [_alert("m3_yoy", E["m3_yoy"], "< 1% broad money stalling"), _alert("loans_nfc_yoy", E["loans_nfc_yoy"], "< 0% corporate credit contracting"), _alert("loans_hh_yoy", E["loans_hh_yoy"], "< 0% household credit contracting")]
    label = "NO SIGNAL" if sig == "NONE" else {"GREEN": "EXPANDING", "RED": "CONTRACTING", "YELLOW": "MIXED"}[sig]
    signals = {"traffic_light": sig, "score": score, "label": label, "flags": flags,
               "detail": "M3 %s · M1 %s · loans NFC %s · HH %s · credit impulse 3m %s M · MIR NFC %s (%s bp over DFR) · BLS NFC %s / HH %s (%s)" % (
                   m3, E["m1_yoy"]["value"], ln, lh, civ, E["mir_nfc_cost"]["value"], D["mir_nfc_minus_dfr_bps"]["value"], bn, bh, D["bls_read"]["badge"]),
               "alerts": alerts}
    md = [d for d, _ in raw["m3_yoy"]][-36:]
    history = {"dates": md, "rows": {k: _col(md, raw[k]) for k in ("m3_yoy", "m1_yoy", "loans_nfc_yoy", "loans_hh_yoy", "loans_nfc_stock", "loans_hh_stock", "mir_nfc_cost", "mir_hh_cost")},
               "signal_log": []}
    history["rows"]["credit_impulse"] = _col(md, ci)
    qd = [d for d, _ in raw["bls_standards_nfc"]][-16:]
    history["quarterly"] = {"dates": qd, "bls_nfc": _col(qd, raw["bls_standards_nfc"]), "bls_hh": _col(qd, raw["bls_standards_hh"])}
    return _base("EUR", "banking", cfg, b, E, D, signals, history)


# ═══════════════════════ 4 · RATES & MONEY MARKET ═══════════════════════
def build_rates(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None, cb_block: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["rates"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "rates", data, "percent", pl, th)
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    estr, dfr, mlf, mro = raw["estr"], raw["dfr"], raw["mlf_rate"], raw["mro_rate"]
    ex = _ser(data, cfg["blocks"]["central_bank"]["series"]["excess_liquidity"])
    exv = ex[-1][1] if ex else None
    D: Dict[str, dict] = {}
    # policy rates are step series: show the current level with its effective date
    for k in ("dfr", "mro_rate", "mlf_rate"):
        E[k]["status"] = "fresh" if E[k]["value"] is not None else "unavailable"
        E[k]["effective_since"] = E[k]["date"]
        E[k]["confidence"] = 100 if E[k]["value"] is not None else 0
        E[k]["equivalence_note"] = "step series: published on change dates only (FM); level in force since effective_since"
    sp = _spread(estr, dfr)
    spec_sp, regime_txt = _anchor_spec(th, exv)
    D["estr_minus_dfr_bps"] = entry("estr_minus_dfr_bps", sp, "€STR − DFR stress spread (compression toward the floor — E5)", "daily", "bps", cfg, usd_analog="SOFR − IORB",
                                    status="fresh" if sp else "unavailable", spec=spec_sp, prev_level=pl.get("estr_minus_dfr_bps"), z_window=30)
    v = D["estr_minus_dfr_bps"]["value"]
    lvl = _lvl(D["estr_minus_dfr_bps"])
    watch_a = spec_sp.get("watch_above", 0)
    tail = [x for _, x in sp[-3:]]
    fc = bool(v is not None and lvl != "SAFE" and sum(1 for x in tail[:-1] if x > watch_a) >= 1)
    D["estr_minus_dfr_bps"].update({"friction_confirmed": fc, "anchor_regime": regime_txt,
                                    "badge": "NO DATA" if v is None else "CRISIS" if lvl == "CRISIS" else "STRESS" if lvl == "STRESS" else "AT THE FLOOR" if lvl == "WATCH" else "ABUNDANCE SIGNATURE" if v <= -10 else "NORMAL",
                                    "fx_signal": "NO DATA" if v is None else "EUR BULLISH (funding)" if lvl in ("STRESS", "CRISIS") else "EUR WATCH" if lvl == "WATCH" else "NEUTRAL"})
    D["friction_confirmed"] = {"label": "€STR − DFR ≥ WATCH on the latest print and ≥ 1 of the 2 prior sessions", "value": fc, "status": "fresh" if sp else "unavailable", "date": sp[-1][0] if sp else None}
    # history stats of the spread (verified min −12.0 on 2023-09-29)
    lo = min(sp, key=lambda x: x[1]) if sp else None
    D["estr_minus_dfr_bps"]["history_min"] = {"date": lo[0], "value": lo[1]} if lo else None
    disp = S.merge_series(raw["estr_r75"], raw["estr_r25"], lambda a, c: round((a - c) * 100, 1))
    D["estr_dispersion_bps"] = entry("estr_dispersion_bps", disp, "€STR dispersion R75 − R25 (bps) — E6", "daily", "bps", cfg, status="fresh" if disp else "unavailable",
                                     spec=th.get("estr_dispersion_bps"), prev_level=pl.get("estr_dispersion_bps"), z_window=30)
    c3 = _spread(raw["estr_3m_compounded"], dfr)
    D["estr_3m_compounded_minus_dfr_bps"] = entry("estr_3m_compounded_minus_dfr_bps", c3, "Compounded €STR 3m − DFR (bps): backward-looking, context for the EURIBOR gap (E6)", "daily", "bps", cfg,
                                                  status="fresh" if c3 else "unavailable", z_window=30)
    cp: Series = []
    for d, x in estr:
        dv, mv = _latest_at_or_before(dfr, d), _latest_at_or_before(mlf, d)
        if dv is not None and mv is not None and mv > dv:
            cp.append((d, round((x - dv) / (mv - dv), 3)))
    D["corridor_position"] = entry("corridor_position", cp, "Corridor position (€STR − DFR) / (MLF − DFR): 0 floor · 1 ceiling", "daily", "x", cfg, status="fresh" if cp else "unavailable", z_window=30)
    c102 = S.merge_series(raw["aaa_10y"], raw["aaa_2y"], lambda a, c: round((a - c) * 100, 1))
    D["curve_10y_2y_bps"] = entry("curve_10y_2y_bps", c102, "AAA curve 10Y − 2Y (bps)", "daily", "bps", cfg, status="fresh" if c102 else "unavailable", spec=th.get("curve_10y_2y_bps"), prev_level=pl.get("curve_10y_2y_bps"), z_window=30)
    cv = D["curve_10y_2y_bps"]["value"]
    D["curve_10y_2y_bps"]["badge"] = "NO DATA" if cv is None else "DEEP INVERSION" if cv < -50 else "INVERTED" if cv < 0 else "FLAT" if cv < 50 else "STEEPENING"
    pp = S.merge_series(raw["all_10y"], raw["aaa_10y"], lambda a, c: round((a - c) * 100, 1))
    D["periphery_premium_bps"] = entry("periphery_premium_bps", pp, "Periphery premium: all-EA 10Y − AAA 10Y (bps, daily fragmentation gauge)", "daily", "bps", cfg, status="fresh" if pp else "unavailable",
                                       spec=th.get("periphery_premium_bps"), prev_level=pl.get("periphery_premium_bps"), z_window=30)
    for k, a, c in (("btp_bund_bps", "it_10y_m", "de_10y_m"), ("oat_bund_bps", "fr_10y_m", "de_10y_m"), ("bonos_bund_bps", "es_10y_m", "de_10y_m")):
        s = S.merge_series(raw[a], raw[c], lambda x, y: round((x - y) * 100, 1))
        D[k] = entry(k, s, "%s − Bund 10Y (bps, monthly convergence yields)" % {"btp_bund_bps": "BTP", "oat_bund_bps": "OAT", "bonos_bund_bps": "Bonos"}[k], "monthly", "bps", cfg,
                     status="fresh" if s else "unavailable", spec=th.get(k), prev_level=pl.get(k), z_window=12)
    eu = _spread(raw["euribor_3m_m"], dfr)
    D["euribor_minus_dfr_bps"] = entry("euribor_minus_dfr_bps", eu, "EURIBOR 3M (monthly avg) − DFR (bps): hike/cut pricing + term premium", "monthly", "bps", cfg, status="fresh" if eu else "unavailable", z_window=12)
    d5 = S.diff_series(raw["aaa_10y"], 5, 100)
    D["aaa_10y_5d_change_bps"] = entry("aaa_10y_5d_change_bps", d5, "AAA 10Y Δ 5 sessions (bps)", "daily", "bps", cfg, status="fresh" if d5 else "unavailable", z_window=30)
    if D["aaa_10y_5d_change_bps"]["value"] is not None:
        a = abs(D["aaa_10y_5d_change_bps"]["value"])
        D["aaa_10y_5d_change_bps"]["level"] = "STRESS" if a >= 25 else "WATCH" if a >= 15 else "SAFE"
    for k in ("estr", "aaa_2y", "aaa_10y", "all_10y"):
        if E[k]["change_abs"] is not None:
            E[k]["change_bps"] = round(E[k]["change_abs"] * 100, 1)
    flags: List[str] = []
    if v is not None and v <= -10:
        flags.append("ABUNDANCE_SIGNATURE")
    if cv is not None and cv < 0:
        flags.append("CURVE_INVERTED")
    ppl, btl = _lvl(D["periphery_premium_bps"]), _lvl(D["btp_bund_bps"])
    if ppl in ("STRESS", "CRISIS") or btl != "SAFE" and D["btp_bund_bps"]["value"] is not None:
        flags.append("PERIPHERY_STRESS")
    wide = [k for k in ("oat_bund_bps", "bonos_bund_bps") if _lvl(D[k]) in ("WATCH", "STRESS", "CRISIS")]
    if wide:
        flags.append("COUNTRY_SPREAD_WATCH")
    comps = [LEVEL_SCORE.get(lvl, 0.0), {"SAFE": 0.25, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}.get(ppl, 0.0),
             -0.5 if (cv is not None and cv < 0) else 0.25 if cv is not None else 0.0, {"SAFE": 0.0, "WATCH": -0.5, "STRESS": -1.0, "CRISIS": -2.0}.get(btl, 0.0)]
    score = _clamp(sum(comps) / len(comps) * 2) if sp else 0.0
    if lvl == "CRISIS":
        score = -2.0
    alerts = [_alert("estr_minus_dfr_bps", D["estr_minus_dfr_bps"], "compression to the DFR = floor no longer leaky = liquidity turning scarce (EUR bullish funding)"),
              _alert("periphery_premium_bps", D["periphery_premium_bps"], "≥ p85 / 60 bp fragmentation watch"),
              _alert("btp_bund_bps", D["btp_bund_bps"], "150 / 180 / 250 (v5 anchors)"),
              _alert("curve_10y_2y_bps", D["curve_10y_2y_bps"], "negative = inverted")]
    label = "NO SIGNAL" if not sp else "FUNDING CRISIS" if lvl == "CRISIS" else "FUNDING STRESS" if lvl == "STRESS" else "FLOOR WATCH" if lvl == "WATCH" else "FRAGMENTATION" if "PERIPHERY_STRESS" in flags else "SPREAD WATCH" if wide else "CORRIDOR CALM"
    tl = "NONE" if not sp else "RED" if lvl in ("STRESS", "CRISIS") or ppl in ("STRESS", "CRISIS") else "YELLOW" if (lvl == "WATCH" or "PERIPHERY_STRESS" in flags or "CURVE_INVERTED" in flags or wide) else "GREEN"
    if wide:
        comps.append(-0.5 * len(wide))
        score = _clamp(sum(comps) / len(comps) * 2) if sp and lvl != "CRISIS" else score
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags,
               "detail": "€STR %s (−DFR %s bp, %s, %s) · dispersion %s bp · corridor %s · 10−2 %s (%s) · periphery %s bp (%s) · BTP−Bund %s (%s) · OAT %s · Bonos %s · EURIBOR−DFR %s · EUR/USD %s" % (
                   E["estr"]["value"], v, D["estr_minus_dfr_bps"]["badge"], regime_txt.split(":")[0], D["estr_dispersion_bps"]["value"], D["corridor_position"]["value"], cv, D["curve_10y_2y_bps"]["badge"],
                   D["periphery_premium_bps"]["value"], ppl, D["btp_bund_bps"]["value"], btl, D["oat_bund_bps"]["value"], D["bonos_bund_bps"]["value"], D["euribor_minus_dfr_bps"]["value"], E["eurusd"]["value"]),
               "alerts": alerts}
    dates = [d for d, _ in estr][-60:]
    history = {"dates": dates, "rows": {"estr": _col(dates, estr), "dfr": _col(dates, dfr, True), "mro_rate": _col(dates, mro, True), "mlf_rate": _col(dates, mlf, True), "estr_minus_dfr_bps": _col(dates, sp),
                                        "estr_volume": _col(dates, raw["estr_volume"]), "estr_dispersion_bps": _col(dates, disp), "estr_banks": _col(dates, raw["estr_banks"]), "corridor_position": _col(dates, cp),
                                        "aaa_2y": _col(dates, raw["aaa_2y"]), "aaa_10y": _col(dates, raw["aaa_10y"]), "all_10y": _col(dates, raw["all_10y"]), "curve_10y_2y_bps": _col(dates, c102),
                                        "periphery_premium_bps": _col(dates, pp), "eurusd": _col(dates, raw["eurusd"])},
               "monthly_dates": [d for d, _ in raw["de_10y_m"]][-36:], "signal_log": []}
    md = history["monthly_dates"]
    history["monthly_rows"] = {"de_10y": _col(md, raw["de_10y_m"]), "fr_10y": _col(md, raw["fr_10y_m"]), "it_10y": _col(md, raw["it_10y_m"]), "es_10y": _col(md, raw["es_10y_m"]),
                               "btp_bund_bps": _col(md, S.merge_series(raw["it_10y_m"], raw["de_10y_m"], lambda x, y: round((x - y) * 100, 1))),
                               "oat_bund_bps": _col(md, S.merge_series(raw["fr_10y_m"], raw["de_10y_m"], lambda x, y: round((x - y) * 100, 1))),
                               "bonos_bund_bps": _col(md, S.merge_series(raw["es_10y_m"], raw["de_10y_m"], lambda x, y: round((x - y) * 100, 1))),
                               "euribor_3m": _col(md, raw["euribor_3m_m"]), "euribor_minus_dfr_bps": _col(md, eu)}
    return _base("EUR", "rates", cfg, b, E, D, signals, history)
