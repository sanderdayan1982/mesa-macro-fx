"""USD block builders — exact metric set of Sander's three USD dashboards, laid out in the desk's four layers:
  1 central bank  — H.4.1 (WALCL, TREAST, WSHOMCB, WLCFLPCL, WTREGEN, WRESBAL) + ON RRP daily; Net Liquidity = WALCL − TGA − RRP; Δ% w/w ±2%;
                    WRESBAL 3.0T/2.5T; TGA 750/900B; RRP 200B; Primary Credit +20% w/w; balance-sheet phase
  2 fiscal        — DTS daily (T-1): TGA close/open, totals, debt (public / intragov / total / limit), 6 deposit + 12 withdrawal line items
                    (today / MTD / FYTD), Net Spending, Net Deposits, Net Treasury Flow (MMT sign) with 30-day Z / mean / σ, 7-day sum,
                    −ΔTGA reserve impact, seasonal flag
  3 banking       — H.8 weekly: bank credit, loans & leases, C&I (TOTCI), deposits, borrowings (H8B3094NCBA); Δ% w/w statuses, 26-week Z heatmap,
                    base-100 index, traffic-light vote
  4 rates         — SOFR − IORB stress spread (5/15/30 bp), H.15: DFF, DTB3, DGS2, DGS10, 10Y−2Y, FF−3M (common dates), stance, H.15 signal,
                    H.4.1 forex signal matrix
Config: config/usd.json v0.1.x (no triangulation — Sander's instruction 2026-09-08)."""
from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple
from . import series as S
from .series import Series
from .thresholds import classify, signal_band
from .scoring import Comps
from .blocks import entry, _prev_levels, _alert, _health, _base as _base0
from .blocks_gbp import _ser


# legacy net-liquidity band (±2 % w/w, H.4.1 suite): published as a liquidity state, never as a risk posture (round 2)
NL_TXT = {"BAND_HIGH": "NL UP", "BAND_LOW": "NL DOWN", "NEUTRAL": "NEUTRAL"}

def _base(ccy, block, cfg, bcfg, E, D, signals, history):
    out = _base0(ccy, block, cfg, bcfg, E, D, signals, history)
    wired = {k: e for k, e in E.items() if bcfg["series"].get(k, {}).get("id")}
    out["source_health"] = _health(wired, len(wired))
    out["source_health"]["series_pending"] = len(E) - len(wired)
    return out


def _freq(f: str) -> str:
    return "daily" if f.startswith("daily") else "weekly" if f.startswith("weekly") else "monthly" if f.startswith("monthly") else "weekly"


def _entries(cfg: dict, block: str, data: Dict[str, Series], unit: str, pl: Dict[str, str], th: dict) -> Dict[str, dict]:
    E: Dict[str, dict] = {}
    for key, sc in cfg["blocks"][block]["series"].items():
        ser = _ser(data, sc)
        fq = _freq(sc.get("freq", "weekly"))
        st = None if sc.get("id") else "unavailable"
        e = entry(key, ser, sc["label"], fq, sc.get("unit", unit), cfg, sc.get("id"), sc.get("usd_analog"), status=st, spec=th.get(key), prev_level=pl.get(key),
                  z_window=30 if fq == "daily" else 26 if fq == "weekly" else 12, lag_days=int(sc.get("lag_days", 0) or 0))
        if sc.get("display_only"):
            e["display_only"] = True
        if sc.get("note") or sc.get("role"):
            e["equivalence_note"] = sc.get("note") or sc.get("role")
        if sc.get("group"):
            e["group"] = sc["group"]
        if not sc.get("id"):
            e["status"] = "unavailable"
        E[key] = e
    return E


def _latest_at_or_before(ser: Series, d: str) -> Optional[float]:
    best = None
    for dd, v in ser:
        if dd <= d and v is not None:
            best = v
        elif dd > d:
            break
    return best


def _clamp(x: float, lo: float = -2.0, hi: float = 2.0) -> float:
    return round(max(lo, min(hi, x)), 2)


def _lvl(e: dict) -> str:
    return e.get("level", "NO DATA")


# ═══════════════════════ 1 · FEDERAL RESERVE (H.4.1 + ON RRP) ═══════════════════════
def build_central_bank(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["central_bank"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "central_bank", data, unit, pl, th)
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    wa, tga, rrp, res, pc = raw["total_assets"], raw["tga"], raw["on_rrp"], raw["reserves"], raw["primary_credit"]
    D: Dict[str, dict] = {}
    # Net Liquidity = WALCL − WTREGEN − RRPONTTLD on H.4.1 dates (skip weeks without TGA/RRP coverage — v2.0 fix A1)
    nl: Series = []
    for d, w in wa:
        t, r = _latest_at_or_before(tga, d), _latest_at_or_before(rrp, d)
        if w is not None and t is not None and r is not None:
            nl.append((d, round(w - t - r, 1)))
    D["net_liquidity"] = entry("net_liquidity", nl, "Fed Net Liquidity = WALCL − TGA − ON RRP", "weekly", unit, cfg, usd_analog="WALCL − WTREGEN − RRPONTTLD",
                               status="fresh" if nl else "unavailable", equivalence_note=b["derived"]["net_liquidity"]["formula"])
    nlw = S.pct_change_series(nl)
    D["net_liquidity_wow_pct"] = entry("net_liquidity_wow_pct", nlw, "Net Liquidity Δ% w/w (≥ +2% NL UP · ≤ −2% NL DOWN; heurística heredada, sin dirección)", "weekly", "%", cfg, status="fresh" if nlw else "unavailable")
    sb = signal_band(D["net_liquidity_wow_pct"]["value"], nlw, th["net_liquidity_wow_pct"], "weekly")
    D["net_liquidity_wow_pct"].update({"signal": sb["signal"], "percentile": sb["percentile"], "thresholds": sb.get("thresholds", {})})
    # H.4.1 status badges (exact rules)
    rv = E["reserves"]["value"]
    r_status = None if rv is None else "CRITICAL" if rv < 2500000 else "NERVOUS" if rv < 3000000 else "AMPLE"
    D["reserves_status"] = {"label": "Reserve Balances status (H.4.1: < 3.0T NERVOUS · < 2.5T CRITICAL)", "value": rv, "status": E["reserves"]["status"], "date": E["reserves"]["date"], "unit": unit,
                            "level": _lvl(E["reserves"]), "badge": r_status or "NO DATA", "thresholds": {"levels": {"NERVOUS": 3000000, "CRITICAL": 2500000}}}
    tv = E["tga"]["value"]
    t_status = None if tv is None else "HEAVY DRAIN" if tv >= 900000 else "DRAIN WATCH" if tv >= 750000 else "SAFE"
    D["tga_status"] = {"label": "TGA status (H.4.1: ≥ 750B DRAIN WATCH · ≥ 900B HEAVY DRAIN)", "value": tv, "status": E["tga"]["status"], "date": E["tga"]["date"], "unit": unit,
                       "level": _lvl(E["tga"]), "badge": t_status or "NO DATA", "high_drain_800": bool(tv is not None and tv >= 800000)}
    rrv = E["on_rrp"]["value"]
    D["rrp_status"] = {"label": "ON RRP status (H.4.1: ≥ 200B WATCH = capital parked)", "value": rrv, "status": E["on_rrp"]["status"], "date": E["on_rrp"]["date"], "unit": unit,
                       "level": _lvl(E["on_rrp"]), "badge": ("WATCH" if rrv >= 200000 else "LOW") if rrv is not None else "NO DATA"}
    pcw = S.pct_change_series(pc)
    D["primary_credit_wow_pct"] = entry("primary_credit_wow_pct", pcw, "Primary Credit Δ% w/w (> +20% = PANIC)", "weekly", "%", cfg, status="fresh" if pcw else "unavailable",
                                        spec=th.get("primary_credit_wow_pct"), prev_level=pl.get("primary_credit_wow_pct"))
    D["primary_credit_wow_pct"]["badge"] = "NO DATA" if D["primary_credit_wow_pct"]["value"] is None else "PANIC" if D["primary_credit_wow_pct"]["value"] > 20 else "LOW"
    waw = S.diff_series(wa)
    D["total_assets_wow"] = entry("total_assets_wow", waw, "Δ WALCL w/w (QT ↓ / QE ↑)", "weekly", unit, cfg, status="fresh" if waw else "unavailable",
                                  spec=th.get("total_assets_wow"), prev_level=pl.get("total_assets_wow"))
    drains: Series = [(d, round(t + (_latest_at_or_before(rrp, d) or 0.0), 1)) for d, t in tga if _latest_at_or_before(rrp, d) is not None]
    D["drains_total"] = entry("drains_total", drains, "Active drains: TGA + ON RRP (stacked)", "weekly", unit, cfg, status="fresh" if drains else "unavailable")
    ch13 = [(wa[i][0], round(wa[i][1] - wa[i - 13][1], 1)) for i in range(13, len(wa))]
    D["total_assets_13w_change"] = entry("total_assets_13w_change", ch13, "Δ WALCL 13 weeks", "weekly", unit, cfg, status="fresh" if ch13 else "unavailable")
    c13 = D["total_assets_13w_change"]["value"]
    phase = "QT" if (c13 is not None and c13 < -50000) else "QE" if (c13 is not None and c13 > 50000) else "STEADY"
    D["balance_sheet_phase"] = {"label": "Balance-sheet phase", "value": None, "phase": phase, "status": "fresh" if c13 is not None else "unavailable", "date": E["total_assets"]["date"],
                                "note": "13-week Δ WALCL: < −50B QT · > +50B QE · else STEADY"}
    flags: List[str] = []
    if D["primary_credit_wow_pct"]["badge"] == "PANIC":
        flags.append("PRIMARY_CREDIT_PANIC")
    if D["rrp_status"]["badge"] == "WATCH":
        flags.append("RRP_REBOUND")
    if t_status == "HEAVY DRAIN":
        flags.append("TGA_HEAVY_DRAIN")
    C = Comps(cfg, "mean2")
    C.level("reserves_status", {"AMPLE": 0.5, "NERVOUS": -1.0, "CRITICAL": -2.0}.get(r_status, 0.0))
    C.flow("net_liquidity_band", 1.0 if sb["signal"] == "BAND_HIGH" else -1.0 if sb["signal"] == "BAND_LOW" else 0.0)
    C.flow("tga_status", {"SAFE": 0.25, "DRAIN WATCH": -0.5, "HEAVY DRAIN": -1.0}.get(t_status, 0.0))
    C.level("rrp_status", -0.5 if D["rrp_status"]["badge"] == "WATCH" else 0.25)
    C.level("phase", {"QT": -0.25, "QE": 0.5}.get(phase, 0.0))
    if D["primary_credit_wow_pct"]["badge"] == "PANIC":
        C.event("primary_credit_panic", -2.0)
    score = C.score()
    alerts = [_alert("reserves", E["reserves"], "H.4.1: < 3.0T tensions in repo / fed funds; < 2.5T crisis — Fed pauses QT"),
              _alert("primary_credit_wow_pct", D["primary_credit_wow_pct"], "+20% weekly = a bank in trouble"),
              _alert("tga", E["tga"], "> 800B rising = active drain"),
              _alert("on_rrp", E["on_rrp"], "rebound > 200B = liquidity retreating")]
    label = "NO SIGNAL" if not res else ("INJECTION" if score >= 0.5 else "DRAIN" if score <= -0.5 else "NEUTRAL")
    tl = "NONE" if not res else "GREEN" if score >= 0.5 else "RED" if score <= -0.75 else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags, "components": C.to_dict(),
               "detail": "WRESBAL %s · NL Δ%% %s (%s) · TGA %s · RRP %s · Primary credit %s · phase %s" % (
                   r_status, D["net_liquidity_wow_pct"]["value"], NL_TXT.get(sb["signal"], sb["signal"]), t_status, D["rrp_status"]["badge"], D["primary_credit_wow_pct"]["badge"], phase),
               "alerts": alerts}
    # weekly record (H.4.1 historical table) — last 52 H.4.1 dates
    dates = [d for d, _ in wa][-52:]
    def col(ser: Series, fn=None) -> List[Optional[float]]:
        m = {d: v for d, v in ser}
        return [(m.get(d) if fn is None else fn(d)) for d in dates]
    nlm = {d: v for d, v in nl}
    nlwm = {d: v for d, v in nlw}
    history = {"dates": dates, "rows": {"total_assets": col(wa), "treasury_securities": col(raw["treasury_securities"]), "mbs": col(raw["mbs"]), "primary_credit": col(pc),
                                        "tga": col(tga), "on_rrp": col([], lambda d: _latest_at_or_before(rrp, d)), "reserves": col(res),
                                        "net_liquidity": [nlm.get(d) for d in dates], "net_liquidity_wow_pct": [nlwm.get(d) for d in dates],
                                        "total_assets_wow": col(waw)},
               "signal_log": [{"date": d, "label": "NL UP" if v >= 2 else "NL DOWN" if v <= -2 else "NEUTRAL", "score": v, "note": "NL Δ% w/w"} for d, v in nlw[-15:]][::-1]}
    return _base("USD", "central_bank", cfg, b, E, D, signals, history)


# ═══════════════════════ 2 · U.S. TREASURY (DTS daily) ═══════════════════════
def _seasonal_flag(d: str) -> str:
    y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
    if (m, dd) in ((3, 31), (6, 30), (9, 30), (12, 31)):
        return "Quarter-End"
    if m == 4 and 14 <= dd <= 16:
        return "Tax Day"
    if 14 <= dd <= 16 and m in (1, 6, 9):
        return "Est. Tax Day"
    if 14 <= dd <= 16:
        return "Mid-Month Settl."
    if dd >= 25:
        return "Payments Window"
    return ""


def _z_incl(ser: Series, window: int = 30) -> Tuple[Series, Series, Series]:
    """DTS Tracker statistics: rolling mean / population σ / Z with the window INCLUDING the current day (as the hero card)."""
    vals = [v for _, v in ser]
    zs: Series = []
    ms: Series = []
    sds: Series = []
    for i in range(len(ser)):
        if i < window - 1:
            zs.append((ser[i][0], None)); ms.append((ser[i][0], None)); sds.append((ser[i][0], None))
            continue
        w = vals[i - window + 1:i + 1]
        m = sum(w) / len(w)
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / len(w))
        zs.append((ser[i][0], 0.0 if sd == 0 else round((vals[i] - m) / sd, 4)))
        ms.append((ser[i][0], round(m, 1))); sds.append((ser[i][0], round(sd, 1)))
    return zs, ms, sds


def build_fiscal(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["fiscal"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "fiscal", data, unit, pl, th)
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    # MTD / FYTD views on every line item and total (DTS Tracker view toggle)
    for key, sc in b["series"].items():
        sid = sc.get("id")
        if sid and (sid.startswith("DTS:D|") or sid.startswith("DTS:W|") or sid in ("DTS:debt_issues", "DTS:debt_redemptions")):
            for suf in ("mtd", "fytd"):
                s2 = S.clean(data.get(sid + "|" + suf, []))
                E[key][suf] = s2[-1][1] if s2 else None
        if sid in ("DTS:total_deposits", "DTS:total_withdrawals"):
            alt = "DTS:tot_dep_tx" if sid.endswith("deposits") else "DTS:tot_wd_tx"
            for suf in ("mtd", "fytd"):
                s2 = S.clean(data.get(alt + "|" + suf, []))
                E[key][suf] = s2[-1][1] if s2 else None
    tw, td, dr, di, tga = raw["total_withdrawals"], raw["total_deposits"], raw["debt_redemptions"], raw["debt_issues"], raw["tga_closing"]
    D: Dict[str, dict] = {}
    ns = S.merge_series(tw, dr, lambda w, r: abs(w) - abs(r))
    nd = S.merge_series(td, di, lambda d_, i: abs(d_) - abs(i))
    ntf = S.merge_series(ns, nd, lambda a, c: a - c)
    D["net_spending"] = entry("net_spending", ns, "Net Spending = Total Withdrawals − Debt Redemptions", "daily", unit, cfg, status="fresh" if ns else "unavailable", z_window=30)
    D["net_deposits"] = entry("net_deposits", nd, "Net Deposits = Total Deposits − Debt Issues", "daily", unit, cfg, status="fresh" if nd else "unavailable", z_window=30)
    zs, ms, sds = _z_incl(ntf, 30)
    D["net_treasury_flow"] = entry("net_treasury_flow", ntf, "Net Treasury Flow = Net Spending − Net Deposits (+ inject / − drain, MMT sign)", "daily", unit, cfg,
                                   usd_analog="DTS Tracker hero", status="fresh" if ntf else "unavailable", z_window=30)
    z = zs[-1][1] if zs else None
    D["net_treasury_flow"]["zscore"] = z
    if z is not None:
        c = classify(z, ntf, th["net_treasury_flow"], "daily")
        D["net_treasury_flow"].update({"level": c["level"], "thresholds": c.get("thresholds", {})})
    D["net_treasury_flow"]["badge"] = ("insufficient data" if z is None else "extraordinary inject" if z >= 2 else "notable inject" if z >= 1 else "within normal range" if z > -1
                                       else "notable drain" if z > -2 else "extraordinary drain")
    D["net_treasury_flow"]["direction"] = None if not ntf else ("net fiscal injection — NFA creation" if ntf[-1][1] >= 0 else "net fiscal drain — NFA destruction")
    D["ntf_mean_30d"] = entry("ntf_mean_30d", [p for p in ms if p[1] is not None], "NTF 30-day mean", "daily", unit, cfg, status="fresh" if ms else "unavailable")
    D["ntf_sd_30d"] = entry("ntf_sd_30d", [p for p in sds if p[1] is not None], "NTF 30-day σ", "daily", unit, cfg, status="fresh" if sds else "unavailable")
    ntf7 = S.rolling_sum(ntf, 7)
    D["net_treasury_flow_7d"] = entry("net_treasury_flow_7d", ntf7, "NTF 7-day cumulative", "daily", unit, cfg, status="fresh" if ntf7 else "unavailable", z_window=30)
    tdod = S.diff_series(tga)
    D["tga_dod"] = entry("tga_dod", tdod, "Δ TGA closing d/d", "daily", unit, cfg, status="fresh" if tdod else "unavailable", spec=th.get("tga_dod"), prev_level=pl.get("tga_dod"), z_window=30)
    imp = [(d, -v) for d, v in tdod]
    D["tga_reserve_impact"] = entry("tga_reserve_impact", imp, "ΔTGA reserve impact = −ΔTGA (TGA down = reserves added)", "daily", unit, cfg, status="fresh" if imp else "unavailable", z_window=30)
    D["tga_reserve_impact"]["badge"] = None if not imp else ("reserves add" if imp[-1][1] >= 0 else "reserves drain")
    ddod = S.diff_series(raw["debt_total"])
    D["debt_total_dod"] = entry("debt_total_dod", ddod, "Δ Total public debt d/d", "daily", unit, cfg, status="fresh" if ddod else "unavailable", z_window=30)
    # MTD / FYTD net flows (from the DTS cumulative fields)
    for suf, lab in (("mtd", "Month to Date"), ("fytd", "Fiscal Year to Date")):
        g = lambda sid: S.clean(data.get(sid + "|" + suf, []))
        ns2 = S.merge_series(g("DTS:tot_wd_tx"), g("DTS:debt_redemptions"), lambda w, r: abs(w) - abs(r))
        nd2 = S.merge_series(g("DTS:tot_dep_tx"), g("DTS:debt_issues"), lambda d_, i: abs(d_) - abs(i))
        nt2 = S.merge_series(ns2, nd2, lambda a, c: a - c)
        D["net_treasury_flow_" + suf] = entry("net_treasury_flow_" + suf, nt2, "Net Treasury Flow — %s (cumulative)" % lab, "daily", unit, cfg, status="fresh" if nt2 else "unavailable", z_window=30)
        D["net_spending_" + suf] = entry("net_spending_" + suf, ns2, "Net Spending — %s" % lab, "daily", unit, cfg, status="fresh" if ns2 else "unavailable", z_window=30)
        D["net_deposits_" + suf] = entry("net_deposits_" + suf, nd2, "Net Deposits — %s" % lab, "daily", unit, cfg, status="fresh" if nd2 else "unavailable", z_window=30)
    last_d = ntf[-1][0] if ntf else None
    D["seasonal_flag"] = {"label": "Seasonal flag (DTS Tracker)", "value": None, "flag": _seasonal_flag(last_d) if last_d else "", "status": "fresh" if last_d else "unavailable", "date": last_d}
    # ── v0.1.1 structural fiscal impulse (desk addition, Sander 2026-09-09): the LEVEL of the injection, not the daily surprise ──
    ntf20, ntf60 = S.rolling_sum(ntf, 20), S.rolling_sum(ntf, 60)
    D["ntf_20d"] = entry("ntf_20d", ntf20, "NTF 20-session cumulative (structural impulse, Z vs 250 sessions)", "daily", unit, cfg, status="fresh" if ntf20 else "unavailable", z_window=250)
    D["ntf_60d"] = entry("ntf_60d", ntf60, "NTF 60-session cumulative (structural impulse, Z vs 250 sessions)", "daily", unit, cfg, status="fresh" if ntf60 else "unavailable", z_window=250)
    # FYTD vs the same point of the previous fiscal year (DTS cumulative fields; needs ≥ 13 months of history)
    fy_now = D["net_treasury_flow_fytd"]
    fyser = S.clean(S.merge_series(S.merge_series(S.clean(data.get("DTS:tot_wd_tx|fytd", [])), S.clean(data.get("DTS:debt_redemptions|fytd", [])), lambda w, r: abs(w) - abs(r)),
                                   S.merge_series(S.clean(data.get("DTS:tot_dep_tx|fytd", [])), S.clean(data.get("DTS:debt_issues|fytd", [])), lambda d_, i: abs(d_) - abs(i)), lambda a, c: a - c))
    prior = None
    if last_d and fyser:
        y, rest = int(last_d[:4]) - 1, last_d[4:]
        target = "%d%s" % (y, rest)
        prior = _latest_at_or_before(fyser, target)
        # guard: the prior-year value must belong to the same fiscal year window (Oct–Sep), i.e. dated after the previous Oct-1
        fy_start_prev = "%d-10-01" % (y - 1 if int(last_d[5:7]) < 10 else y)
        pd = max([d for d, _ in fyser if d <= target], default=None)
        if pd is None or pd < fy_start_prev:
            prior = None
    yoy = None if (prior in (None, 0) or fy_now["value"] is None) else round((fy_now["value"] - prior) / abs(prior) * 100, 2)
    D["ntf_fytd_vs_prior_fy"] = {"label": "NTF fiscal-year-to-date vs same point of the prior fiscal year", "value": yoy, "unit": "%", "status": "fresh" if yoy is not None else "unavailable", "date": last_d,
                                 "prior_fytd": prior, "current_fytd": fy_now["value"], "note": "DTS cumulative fields; +% = the deficit runs above last year's pace"}
    z20, z60 = D["ntf_20d"]["zscore"], D["ntf_60d"]["zscore"]
    v20, v60 = D["ntf_20d"]["value"], D["ntf_60d"]["value"]
    # structural score: sign of the 60-session sum sets the direction; magnitude from the Z of the 20/60 sums vs their own 250-session history
    if v60 is None:
        struct = None
    else:
        sgn = 1.0 if v60 > 0 else -1.0 if v60 < 0 else 0.0
        mag = 1.0  # a sustained deficit is an injection by construction (MMT sign): base magnitude 1 (= INJECTION on its own)
        if z60 is not None:
            mag = max(0.5, min(2.0, 1.0 + 0.5 * z60 * sgn))  # faster than its own history → up to 2, slower → down to 0.5
        if yoy is not None:
            mag = max(0.5, min(2.0, mag + (0.25 if yoy > 10 else -0.25 if yoy < -10 else 0.0)))
        struct = round(sgn * mag, 2)
    s7 = D["net_treasury_flow_7d"]["value"]
    surprise = None if z is None else _clamp(0.75 * max(-2.0, min(2.0, z)) + (0.5 if (s7 or 0) > 0 else -0.5 if (s7 or 0) < 0 else 0.0))
    D["fiscal_impulse"] = {"label": "Fiscal impulse score = 50% structural (NTF 60d sign × pace) + 50% daily surprise (Z 30d + 7d sign)", "value": None, "unit": "score", "status": "fresh" if struct is not None else "unavailable", "date": last_d,
                           "structural": struct, "surprise": surprise, "inputs": {"ntf_20d": v20, "z20_vs_250": z20, "ntf_60d": v60, "z60_vs_250": z60, "fytd_vs_prior_pct": yoy}}
    if z is None or s7 is None:
        reg = "NO DATA"
    elif (s7 > 0 and z >= 0) or z >= 1:
        reg = "INJECTION"
    elif (s7 < 0 and z <= 0) or z <= -1:
        reg = "DRAIN"
    else:
        reg = "NEUTRAL"
    D["fiscal_regime"] = {"label": "Fiscal regime (daily surprise rule — DTS Tracker)", "value": None, "regime": reg, "status": "fresh" if reg != "NO DATA" else "unavailable", "date": last_d, "inputs": {"ntf_7d": s7, "z": z}}
    flags: List[str] = []
    if z is not None and abs(z) >= 2:
        flags.append("NTF_EXTRAORDINARY")
    if struct is not None and struct >= 1.0:
        flags.append("STRUCTURAL_DEFICIT_INJECTION")
    CF = Comps(cfg, "weighted")
    if struct is None:
        CF.flow("daily_surprise", 0.0 if surprise is None else surprise)
    else:
        CF.level("structural_ntf_60d", struct, 0.5).flow("daily_surprise", surprise if surprise is not None else 0.0, 0.5)
    score = CF.score()
    D["fiscal_impulse"]["value"] = score
    alerts = [_alert("net_treasury_flow", D["net_treasury_flow"], "|Z| ≥ 2 = extraordinary daily flow (check the seasonal flag)"),
              _alert("tga_closing", E["tga_closing"], "≥ 750B / 900B: TGA rebuild drains reserves"),
              _alert("tga_dod", D["tga_dod"], "large TGA build = reserve drain day")]
    label = "NO SIGNAL" if not ntf else ("INJECTION" if score >= 0.5 else "DRAIN" if score <= -0.5 else "NEUTRAL")
    tl = "NONE" if not ntf else "GREEN" if score >= 0.5 else "RED" if score <= -0.75 else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags, "components": CF.to_dict(),
               "detail": "NTF %s (%s) · Z %s · 7d %s · 60d %s (Z250 %s) · FYTD %s vs prior FY %s%% · structural %s · surprise %s · TGA close %s · −ΔTGA %s%s" % (
                   D["net_treasury_flow"]["value"], D["net_treasury_flow"]["badge"], z, s7, v60, z60, fy_now["value"], yoy, struct, surprise, E["tga_closing"]["value"],
                   D["tga_reserve_impact"]["value"], (" · " + D["seasonal_flag"]["flag"]) if D["seasonal_flag"]["flag"] else ""),
               "alerts": alerts}
    dates = [d for d, _ in tga][-60:]
    def col(ser: Series) -> List[Optional[float]]:
        m = {d: v for d, v in ser}
        return [m.get(d) for d in dates]
    rows = {"tga_closing": col(tga), "tga_opening": col(raw["tga_opening"]), "total_deposits": col(td), "total_withdrawals": col(tw), "debt_issues": col(di), "debt_redemptions": col(dr),
            "net_spending": col(ns), "net_deposits": col(nd), "net_treasury_flow": col(ntf), "ntf_z": col(zs), "ntf_mean": col(ms), "ntf_sd": col(sds),
            "debt_public": col(raw["debt_public"]), "debt_total": col(raw["debt_total"])}
    for key, sc in b["series"].items():
        if sc.get("group"):
            rows[key] = col(raw[key])
    items = [{"key": k, "label": sc["label"], "group": sc["group"], "today": E[k]["value"], "mtd": E[k].get("mtd"), "fytd": E[k].get("fytd"), "date": E[k]["date"], "dod": E[k]["change_abs"]}
             for k, sc in b["series"].items() if sc.get("group")]
    history = {"dates": dates, "rows": rows, "items": items, "seasonal": {d: _seasonal_flag(d) for d in dates if _seasonal_flag(d)},
               "signal_log": [{"date": d, "label": "inject" if v >= 0 else "drain", "score": v, "note": "NTF daily"} for d, v in ntf[-15:]][::-1]}
    return _base("USD", "fiscal", cfg, b, E, D, signals, history)


# ═══════════════════════ 3 · BANKING TRANSMISSION (H.8 weekly) ═══════════════════════
def build_banking(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["banking"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "banking", data, unit, pl, th)
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    keys = ["bank_credit", "loans_leases", "ci_loans", "deposits", "borrowings"]
    D: Dict[str, dict] = {}
    chg: Dict[str, Optional[float]] = {}
    for k in keys:
        w = S.pct_change_series(raw[k])
        D[k + "_wow_pct"] = entry(k + "_wow_pct", w, "%s Δ%% w/w" % b["series"][k]["label"].split(" (")[0], "weekly", "%", cfg, status="fresh" if w else "unavailable",
                                  spec=th.get(k + "_wow_pct"), prev_level=pl.get(k + "_wow_pct"), z_window=26)
        c = D[k + "_wow_pct"]["value"]
        chg[k] = c
        if c is None:
            st = "NO DATA"
        elif k in ("bank_credit", "loans_leases"):
            st = "EXPANDING" if c > 0 else "CONTRACTING" if c < -0.1 else "FLAT"
        elif k == "ci_loans":
            st = "EXPANDING" if c > 0 else "WEAK" if c < -0.1 else "FLAT"
        elif k == "deposits":
            st = "STABLE" if c > 0 else "WEAKENING" if c < -0.1 else "FLAT"
        else:
            st = "FALLING" if c < 0 else "RISING FAST" if c > 0.5 else "STABLE"
        D[k + "_wow_pct"]["badge"] = st
        # Z of the latest weekly change vs the previous 26 weeks (no lookahead) — heatmap colour
        zz = S.rolling_zscore(w, 26, min_points=10)
        D[k + "_wow_pct"]["zscore"] = zz[-1][1] if zz else None
    # vote (H.8 v2.1, symmetric bank credit)
    red = grn = valid = 0
    def vote(k, up_ok, dn_bad):
        nonlocal red, grn, valid
        c = chg.get(k)
        if c is None:
            return
        valid += 1
        if up_ok(c):
            grn += 1
        elif dn_bad(c):
            red += 1
    vote("loans_leases", lambda c: c > 0, lambda c: c < -0.1)
    vote("deposits", lambda c: c > 0, lambda c: c < -0.1)
    vote("borrowings", lambda c: c < 0, lambda c: c > 0.5)
    vote("ci_loans", lambda c: c > 0, lambda c: c < -0.1)
    vote("bank_credit", lambda c: c > 0, lambda c: c < -0.1)
    if valid < 3:
        sig, txt = "NONE", "H.8: NO SIGNAL — only %d/5 series" % valid
    elif red >= 3:
        sig, txt = "RED", "H.8: RED — Credit Contraction"
    elif grn >= 3:
        sig, txt = "GREEN", "H.8: GREEN — Healthy Transmission"
    else:
        sig, txt = "YELLOW", "H.8: YELLOW — Mixed Conditions"
    D["transmission_signal"] = {"label": "H.8 banking signal", "value": None, "signal": sig, "status": "fresh" if valid else "unavailable", "date": E["bank_credit"]["date"],
                                "detail": "%s · green %d · red %d · valid %d/5" % (txt, grn, red, valid), "inputs": chg}
    # base-100 index of loans / deposits / borrowings (combined chart), last 52 weeks
    dates = [d for d, _ in raw["bank_credit"]][-52:]
    def col(ser: Series) -> List[Optional[float]]:
        m = {d: v for d, v in ser}
        return [m.get(d) for d in dates]
    idx = {}
    for k in ("loans_leases", "deposits", "borrowings"):
        c = col(raw[k])
        base = next((v for v in c if v), None)
        idx[k + "_idx"] = [round(v / base * 100, 2) if (v is not None and base) else None for v in c]
    # heatmap: last 12 weeks × 5 series (Δ%, Z)
    heat = []
    for k in keys:
        w = S.pct_change_series(raw[k])
        zz = dict(S.rolling_zscore(w, 26, min_points=10))
        wm = dict(w)
        heat.append({"key": k, "cells": [{"date": d, "pct": wm.get(d), "z": zz.get(d)} for d in dates[-12:]]})
    flags: List[str] = []
    score = 0.0 if not valid else _clamp((grn - red) / valid * 2)
    alerts = [_alert("loans_leases_wow_pct", D["loans_leases_wow_pct"], "loans contracting"), _alert("deposits_wow_pct", D["deposits_wow_pct"], "deposits weakening = funding stress"),
              _alert("borrowings_wow_pct", D["borrowings_wow_pct"], "borrowings rising fast = banks under pressure")]
    tl = sig if sig != "NONE" else "NONE"
    label = "NO SIGNAL" if sig == "NONE" else {"GREEN": "HEALTHY TRANSMISSION", "RED": "CREDIT CONTRACTION", "YELLOW": "MIXED"}[sig]
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags, "detail": txt + " · " + " · ".join("%s %s" % (k.replace("_", " "), D[k + "_wow_pct"]["badge"]) for k in keys), "alerts": alerts}
    rows = {k: col(raw[k]) for k in keys}
    rows.update({k + "_wow_pct": col(S.pct_change_series(raw[k])) for k in keys})
    rows.update(idx)
    history = {"dates": dates, "rows": rows, "heatmap": heat, "signal_log": []}
    return _base("USD", "banking", cfg, b, E, D, signals, history)


# ═══════════════════════ 4 · RATES (SOFR − IORB + H.15) ═══════════════════════
def build_rates(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None, cb_block: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["rates"]
    pl = _prev_levels(prev)
    th = b.get("thresholds", {})
    E = _entries(cfg, "rates", data, "percent", pl, th)
    raw = {k: _ser(data, sc) for k, sc in b["series"].items()}
    sofr, iorb, ff, tb3, y2, y10 = raw["sofr"], raw["iorb"], raw["fed_funds"], raw["tbill_3m"], raw["ust_2y"], raw["ust_10y"]
    D: Dict[str, dict] = {}
    sp: Series = []
    for d, v in sofr:
        ib = _latest_at_or_before(iorb, d)
        if ib is not None and ib > 0:
            sp.append((d, round((v - ib) * 100, 1)))
    D["sofr_minus_iorb_bps"] = entry("sofr_minus_iorb_bps", sp, "SOFR − IORB stress spread (0–5 safe · 5–15 watch · > 15 stress · > 30 crisis)", "daily", "bps", cfg,
                                     usd_analog="SOFR − IORB", status="fresh" if sp else "unavailable", spec=th["sofr_minus_iorb_bps"], prev_level=pl.get("sofr_minus_iorb_bps"), z_window=30)
    v = D["sofr_minus_iorb_bps"]["value"]
    tail = [x for _, x in sp[-3:]]
    fc = bool(v is not None and v > 15 and sum(1 for x in tail[:-1] if x > 15) >= 1)
    D["sofr_minus_iorb_bps"].update({"friction_confirmed": fc, "badge": "NO DATA" if v is None else "CRITICAL" if v > 30 else "STRESS" if v > 15 else "NORMAL",
                                     "fx_signal": "NO DATA" if v is None else "FUNDING STRESS" if v > 30 else "FUNDING WATCH" if v > 15 else "NEUTRAL",
                                     "fx_signal_note": "heurística heredada de la suite USD (cortes 15/30 pb sin replay): describe tensión de financiación, no dirección del USD; la mesa no publica dirección"})
    D["friction_confirmed"] = {"label": "SOFR − IORB > 15 bp on the latest print and ≥ 1 of the 2 prior sessions", "value": fc, "status": "fresh" if sp else "unavailable", "date": sp[-1][0] if sp else None}
    c102 = S.merge_series(y10, y2, lambda a, c: (a - c) * 100)
    D["curve_10y_2y_bps"] = entry("curve_10y_2y_bps", c102, "10Y − 2Y spread (bps)", "daily", "bps", cfg, status="fresh" if c102 else "unavailable", spec=th["curve_10y_2y_bps"], prev_level=pl.get("curve_10y_2y_bps"), z_window=30)
    cv = D["curve_10y_2y_bps"]["value"]
    D["curve_10y_2y_bps"]["badge"] = "NO DATA" if cv is None else "DEEP INVERSION" if cv < -50 else "INVERTED" if cv < 0 else "FLAT" if cv < 50 else "STEEPENING"
    D["curve_10y_2y_bps"]["overlay"] = "NO DATA" if cv is None else "DEEP INVERSION" if cv < -50 else "INVERTED" if cv < 0 else "FLAT CURVE" if cv < 25 else "STEEPENING"
    f3 = S.merge_series(ff, tb3, lambda a, c: (a - c) * 100)
    D["ff_minus_3m_bps"] = entry("ff_minus_3m_bps", f3, "Fed Funds − 3M T-Bill (bps): FF > 3M = market prices cuts", "daily", "bps", cfg, status="fresh" if f3 else "unavailable", spec=th["ff_minus_3m_bps"], prev_level=pl.get("ff_minus_3m_bps"), z_window=30)
    fv = D["ff_minus_3m_bps"]["value"]
    D["ff_minus_3m_bps"]["badge"] = "NO DATA" if fv is None else "TIGHT" if fv > 30 else "ELEVATED" if fv > 10 else "NORMAL"
    ffv = E["fed_funds"]["value"]
    D["fed_funds_stance"] = {"label": "Fed funds stance (H.15: > 5 RESTRICTIVE · > 3 ELEVATED · else ACCOMMODATIVE)", "value": ffv, "status": E["fed_funds"]["status"], "date": E["fed_funds"]["date"], "unit": "percent",
                             "badge": "NO DATA" if ffv is None else "RESTRICTIVE" if ffv > 5 else "ELEVATED" if ffv > 3 else "ACCOMMODATIVE"}
    d5 = S.diff_series(y10, 5, 100)
    D["ust_10y_5d_change_bps"] = entry("ust_10y_5d_change_bps", d5, "10Y Δ 5 sessions (bps)", "daily", "bps", cfg, status="fresh" if d5 else "unavailable", spec=th.get("ust_10y_5d_change_bps"), prev_level=pl.get("ust_10y_5d_change_bps"), z_window=30)
    if D["ust_10y_5d_change_bps"]["value"] is not None:
        a = abs(D["ust_10y_5d_change_bps"]["value"])
        D["ust_10y_5d_change_bps"]["level"] = "STRESS" if a >= 25 else "WATCH" if a >= 15 else "SAFE"
    # daily changes of the four rates (KPI sub-line: bps vs previous)
    for k in ("fed_funds", "tbill_3m", "ust_2y", "ust_10y", "sofr"):
        if E[k]["change_abs"] is not None:
            E[k]["change_bps"] = round(E[k]["change_abs"] * 100, 1)
    if cv is None or fv is None:
        hsig, htxt = "NONE", "H.15: NO SIGNAL — spread series unavailable"
    elif cv < -20 and fv > 20:
        hsig, htxt = "RED", "H.15: RED — Restrictive Backdrop (deep inversion, short-end tight)"
    elif cv > 0 and fv < 10:
        hsig, htxt = "GREEN", "H.15: GREEN — Curve Improving (normalizing, easing)"
    else:
        hsig, htxt = "YELLOW", "H.15: YELLOW — Mixed / Transitional"
    D["rates_signal"] = {"label": "H.15 rates signal", "value": None, "signal": hsig, "status": "fresh" if hsig != "NONE" else "unavailable", "date": E["ust_10y"]["date"], "detail": htxt}
    # H.4.1 forex signal matrix (needs the central-bank block)
    cb = cb_block or {}
    nlsig = ((cb.get("derived") or {}).get("net_liquidity_wow_pct") or {}).get("signal")
    rsv = ((cb.get("series") or {}).get("reserves") or {}).get("value")
    tgv = ((cb.get("series") or {}).get("tga") or {}).get("value")
    D["forex_signal_matrix"] = {"label": "Forex Signal Matrix (H.4.1)", "note": "heurística heredada (cortes ±2 %, 15/30 pb, sin replay): estados de tensión, no dirección del USD", "value": None, "status": "fresh" if cb else "unavailable", "date": sp[-1][0] if sp else None,
                                "cells": {"nl_wow": NL_TXT.get(nlsig, "—"),
                                          "sofr_iorb": D["sofr_minus_iorb_bps"]["fx_signal"],
                                          "wresbal": "—" if rsv is None else "NERVOUS" if rsv < 3000000 else "AMPLE",
                                          "tga": "—" if tgv is None else "HIGH DRAIN" if tgv >= 800000 else "SAFE"}}
    flags: List[str] = []
    if cv is not None and cv < 0:
        flags.append("CURVE_INVERTED")
    lvl = _lvl(D["sofr_minus_iorb_bps"])
    comps = [1.0 if hsig == "GREEN" else -1.0 if hsig == "RED" else 0.0 if hsig == "YELLOW" else 0.0,
             {"SAFE": 0.5, "WATCH": -0.5, "STRESS": -1.5, "CRISIS": -2.0}.get(lvl, 0.0)]
    score = _clamp(sum(comps) / len(comps) * 2) if sp else 0.0
    if lvl == "CRISIS":
        score = -2.0
    alerts = [_alert("sofr_minus_iorb_bps", D["sofr_minus_iorb_bps"], "> 15 bp interbank stress · > 30 bp liquidity crisis (heurística heredada, sin dirección)"),
              _alert("curve_10y_2y_bps", D["curve_10y_2y_bps"], "negative = inverted = recession signal"),
              _alert("ff_minus_3m_bps", D["ff_minus_3m_bps"], "> 30 bp tight; FF above 3M = cuts priced")]
    label = "NO SIGNAL" if not sp else "FUNDING CRISIS" if lvl == "CRISIS" else "FUNDING STRESS" if lvl == "STRESS" else "FLOOR WATCH" if lvl == "WATCH" else {"GREEN": "CURVE IMPROVING", "RED": "RESTRICTIVE", "YELLOW": "MIXED", "NONE": "CORRIDOR CALM"}[hsig]
    tl = "NONE" if not sp else "RED" if lvl in ("STRESS", "CRISIS") or hsig == "RED" else "GREEN" if (lvl == "SAFE" and hsig == "GREEN") else "YELLOW"
    signals = {"traffic_light": tl, "score": score, "label": label, "flags": flags,
               "detail": "SOFR−IORB %s bp (%s) · 10Y−2Y %s (%s) · FF−3M %s (%s) · FF %s%% (%s) · %s" % (v, D["sofr_minus_iorb_bps"]["badge"], cv, D["curve_10y_2y_bps"]["badge"], fv, D["ff_minus_3m_bps"]["badge"], ffv, D["fed_funds_stance"]["badge"], htxt),
               "alerts": alerts}
    dates = [d for d, _ in tb3][-60:]
    def col(ser: Series) -> List[Optional[float]]:
        m = {d: v for d, v in ser}
        return [m.get(d) for d in dates]
    history = {"dates": dates, "rows": {"sofr": col(sofr), "iorb": col([(d, _latest_at_or_before(iorb, d)) for d in dates]), "sofr_minus_iorb_bps": col(sp), "fed_funds": col(ff), "tbill_3m": col(tb3),
                                        "ust_2y": col(y2), "ust_10y": col(y10), "curve_10y_2y_bps": col(c102), "ff_minus_3m_bps": col(f3)}, "signal_log": []}
    return _base("USD", "rates", cfg, b, E, D, signals, history)
