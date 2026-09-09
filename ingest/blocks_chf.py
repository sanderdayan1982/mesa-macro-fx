"""CHF block builders — Swiss National Bank tiered system at 0% with active absorption (config/chf.json v0.2, triangulated 2026-09-08).
  1 central bank — WEEKLY sight deposits (domestic = reserves, other = foreign/institutions), tier parameters (threshold factor, rates),
                   monthly balance sheet (FX investments, SNB Bills, absorbing/supplying repos, swaps, Confederation), minimum reserves,
                   monthly market operations (gmges), SNB Bills register ladder, quarterly FX transactions
  2 fiscal       — Confederation cash at the SNB (monthly), MMDRC weekly auctions, bond monthly auctions (AFF/EFV)
  3 banking      — domestic loans / mortgages, customer deposits, liquid assets, M1–M3, published mortgage rates (zikrepro)
  4 rates        — SARON vs the absorption anchor (policy − 5 bp), band position, term repo (lagged), Confederation NSS curve (daily)
Data keys expected from run.py: portal keys '<cube>:<dims with |>' (e.g. 'snbgwdzid:SARON', 'bamire:TB|GA', 'snbbipo:ES'), warehouse
'nss:J10M0', ops keys (ops_absorbed_month, ops_supplied_month, ops_swaps_month, bills_btc, bills_yield_28d, repo_stock_month_end),
EFV keys (mmdrc_btc, mmdrc_yield, mmdrc_issued, bond_btc, bond_yield, bond_issued, bond_own_share), '_bills_rows' (register rows)."""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from . import series as S
from .series import Series
from .thresholds import classify, signal_band
from .scoring import Comps
from .blocks import entry, _prev_levels, _alert, _health
from .blocks_jpy import _entries, _base, _ffill, _spec, _cap_watch
from .blocks_gbp import _persistent_level

MAP_CB = {"sight_deposits_domestic_weekly": "snbgwdchfsgw:GI", "sight_deposits_total_weekly": "snbgwdchfsgw:TG", "other_sight_deposits_weekly": "snbgwdchfsgw:UEB",
          "min_reserve_sight_deposits": "snbgwdmigirow:GU", "min_reserve_requirement": "bamire:TB|GA", "min_reserve_compliance_pct": "bamire:TB|EP",
          "policy_rate": "snbgwdzid:LZ", "rate_up_to_threshold": "snbgwdzid:ZIGBL", "rate_above_threshold": "snbgwdzid:ZIG", "threshold_factor": "snbgwdzid:FREI",
          "special_rate": "snbgwdzid:ENG", "fx_investments": "snbbipo:D", "total_assets": "snbbipo:T0", "banknotes": "snbbipo:N",
          "sight_deposits_domestic_monthly": "snbbipo:GB", "sight_deposits_foreign": "snbbipo:GBI", "snb_bills": "snbbipo:ES", "absorbing_repos": "snbbipo:VRGSF",
          "supplying_repos": "snbbipo:FRGSF", "secured_loans": "snbbipo:GD", "monetary_base": "snbmoba:N0", "fx_transactions_quarterly": "snbfxtr:T0",
          "bills_maturity_ladder": "bills_maturing_4w", "mm_operations_absorbed_month": "ops_absorbed_month", "mm_operations_supplied_month": "ops_supplied_month",
          "swap_balances_chf": "snbbipo:GSGSF", "snb_bills_auction_month": "bills_btc"}
MAP_FI = {"amounts_due_to_confederation": "snbbipo:VB", "mmdrc_auction_results": "mmdrc_btc", "bond_auction_results": "bond_btc", "bonds_outstanding": "bonds_outstanding_total",
          "mmdrc_3m_yield_monthly": "zimoma:EG3M", "auction_calendar": None}
MAP_BK = {"loans_domestic_total": "bakredinausbm:AV1|I|T1|F", "mortgages_domestic": "bakredinausbm:AV1|I|H|F", "other_loans_domestic": "bakredinausbm:AV1|I|T2|F",
          "customer_deposits": "babilpobm:VKE|T|T|A40", "bank_liquid_assets": "babilpobm:FMI|T|T|A40", "due_to_banks": "babilpobm:VBA|T|T|A40",
          "m1": "snbmonagg:B|GM1", "m2": "snbmonagg:B|GM2", "m3": "snbmonagg:B|GM3", "monetary_base_monthly": "snbmoba:N0",
          "mortgage_rate_fixed_5y": "zikrepro:05Q|50", "mortgage_rate_fixed_10y": "zikrepro:05Q|10", "mortgage_rate_variable": "zikrepro:05Q|MV"}
MAP_RT = {"saron": "snbgwdzid:SARON", "policy_rate": "snbgwdzid:LZ", "rate_above_threshold": "snbgwdzid:ZIG", "special_rate": "snbgwdzid:ENG",
          "sar1w": "zirepo:H2", "sar1m": "zirepo:H4", "sar3m": "zirepo:H5", "saron_1m_compound": "zirepo:H6", "saron_3m_compound": "zirepo:H7",
          "confed_1y": "nss:J01M0", "confed_2y": "nss:J02M0", "confed_5y": "nss:J05M0", "confed_10y": "nss:J10M0", "confed_20y": "nss:J20M0", "confed_30y": "nss:J30M0",
          "mmdrc_3m_yield": "mmdrc_yield"}
ZERO_IF_EMPTY_CB = ("supplying_repos", "mm_operations_supplied_month")
LAGGED_OK = ("sar1w", "sar1m", "sar3m", "saron_1m_compound", "saron_3m_compound")  # SNB publishes zirepo ~3 weeks late (stale-by-design)


def _two_sided(name: str, ser: Series, spec: dict, freq: str, prev: Optional[str]) -> dict:
    """Two-sided percentile classification: worst of the high side and the low side; returns classify()-like dict + 'side'."""
    L = S.last(ser)
    if not L:
        return {"level": "NO DATA", "percentile": None, "thresholds": {}}
    # hysteresis 'pA/pB' in a two-sided spec = exit percentile of the HIGH side / of the LOW side (not WATCH/STRESS positions):
    # replay bug 2026-09-09 — the shared parser read 'p80/p20' as WATCH-exit p80 / STRESS-exit p20, so a high-side STRESS never exited
    # (still ≥ p20) and a low-side WATCH never exited (still ≤ p80): settlement_cash_wow sat at STRESS 100 % of the weeks.
    ex = str((spec.get("hysteresis") or {}).get("exit_on", "") or "")
    parts = [x.strip() for x in ex.split("/") if x.strip()]
    hi_spec = dict(spec, direction="high_is_risk")
    lo_spec = dict(spec, direction="low_is_risk")
    if len(parts) == 2:
        hi_spec["hysteresis"] = {"exit_on": parts[0]}
        lo_spec["hysteresis"] = {"exit_on": parts[1]}
    hi = classify(L[1], ser, hi_spec, freq, prev)
    for k in ("watch", "stress", "crisis"):
        if spec.get(k + "_below"):
            lo_spec[k + "_below"] = spec[k + "_below"]
    lo = classify(L[1], ser, lo_spec, freq, prev)
    rank = {"NO DATA": -1, "SAFE": 0, "WATCH": 1, "STRESS": 2, "CRISIS": 3}
    pick, side = (hi, "high") if rank[hi["level"]] >= rank[lo["level"]] else (lo, "low")
    out = dict(pick)
    out["side"] = side if pick["level"] != "SAFE" else None
    out["thresholds"] = {"method": "percentile", "two_sided": True, "levels": {"WATCH_high": hi.get("thresholds", {}).get("levels", {}).get("WATCH"), "WATCH_low": lo.get("thresholds", {}).get("levels", {}).get("WATCH"),
                                                                         "STRESS_high": hi.get("thresholds", {}).get("levels", {}).get("STRESS"), "STRESS_low": lo.get("thresholds", {}).get("levels", {}).get("STRESS")},
                         "window": spec.get("window"), "n": hi.get("thresholds", {}).get("n")}
    return out


def _apply(e: dict, c: dict) -> None:
    e["level"] = c.get("level", e.get("level"))
    if c.get("percentile") is not None:
        e["percentile"] = c["percentile"]
    if c.get("thresholds"):
        e["thresholds"] = c["thresholds"]
    if c.get("side"):
        e["side"] = c["side"]


def _ladder(rows: List[dict], asof: str, days: int, stock: Optional[float]) -> Optional[float]:
    """Bills maturing within `days` after asof, scaled to the balance-sheet stock (the register lists issued lines incl. SNB own holdings;
    verified 2026-08-31: register total 201,897 vs balance-sheet ES 81,901 → use the register for the SHAPE, ES for the level)."""
    if not rows or stock is None:
        return None
    from .providers_chf import SnbBillsRegisterProvider as R
    tot = R.total(rows)
    if not tot:
        return None
    return round(stock * R.ladder(rows, asof, days) / tot, 1)


# ═══════════════════════ 1 · CENTRAL BANK ═══════════════════════
def build_central_bank(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["central_bank"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    gi = S.clean(data.get("snbgwdchfsgw:GI", []))
    rows = data.get("_bills_rows") or []  # type: ignore
    es = S.clean(data.get("snbbipo:ES", []))
    # bills ladder as a one-point series at the latest weekly date (recomputed every run from the register)
    if gi and rows and es:
        data = dict(data)
        v4 = _ladder(rows, gi[-1][0], 28, es[-1][1])
        v1 = _ladder(rows, gi[-1][0], 7, es[-1][1])
        data["bills_maturing_4w"] = [(gi[-1][0], v4)] if v4 is not None else []
        data["bills_maturing_week"] = [(gi[-1][0], v1)] if v1 is not None else []
    E, raw = _entries(cfg, "central_bank", data, MAP_CB, unit, pl, {}, zero_if_empty=ZERO_IF_EMPTY_CB, anchor=S.clean(data.get("snbbipo:ES", [])))
    for k in ("threshold_factor",):
        E[k]["unit"] = "x"
    for k in ("policy_rate", "rate_up_to_threshold", "rate_above_threshold", "special_rate"):
        E[k]["unit"] = "%"
        E[k]["frequency"] = "event"
        E[k]["status"] = "fresh" if raw[k] else "unavailable"
    E["min_reserve_compliance_pct"]["unit"] = "%"
    E["fx_transactions_quarterly"]["frequency"] = "quarterly"
    E["snb_bills_auction_month"]["unit"] = "x"
    E["snb_bills_auction_month"]["label"] = "SNB Bills 28-day auction — bid-to-cover (latest)"
    D: Dict[str, dict] = {}
    req = raw["min_reserve_requirement"]
    fac = raw["threshold_factor"]
    # ── weekly reserves ──
    wow = S.diff_series(gi, 1)
    D["sight_deposits_wow"] = entry("sight_deposits_wow", wow, "Sight deposits of domestic banks — week-on-week change", "weekly", unit, cfg, z_window=26)
    if wow:
        _apply(D["sight_deposits_wow"], _two_sided("sight_deposits_wow", wow, _spec(th, "sight_deposits_wow") or {}, "weekly", pl.get("sight_deposits_wow")))
    D["sight_deposits_4w_change"] = entry("sight_deposits_4w_change", S.diff_series(gi, 4), "Sight deposits — 4-week change", "weekly", unit, cfg, z_window=26)
    p13 = S.pct_change_series(gi, 13)
    sb = signal_band(p13[-1][1] if p13 else None, p13, _spec(th, "sight_deposits_13w_change_pct") or {}, "weekly")
    D["sight_deposits_13w_change_pct"] = entry("sight_deposits_13w_change_pct", p13, "Sight deposits — 13-week change (%)", "weekly", "%", cfg, z_window=26)
    D["sight_deposits_13w_change_pct"]["signal"] = sb["signal"]
    D["sight_deposits_13w_change_pct"]["signal_thresholds"] = sb.get("thresholds")
    ratio = S.merge_series(gi, _ffill(req, gi), lambda a, r: round(a / r, 2) if r else None) if req else []
    ratio = [(d, v) for d, v in ratio if v is not None]
    D["excess_to_required_ratio"] = entry("excess_to_required_ratio", ratio, "Sight deposits / minimum reserve requirement (x)", "weekly", "x", cfg,
                                          spec=dict(_spec(th, "reserves") or {}, method="absolute_primary", direction="low_is_risk"), prev_level=pl.get("excess_to_required_ratio"), z_window=26)
    if ratio and D["excess_to_required_ratio"].get("level") == "SAFE":
        pa = (th.get("reserves") or {}).get("primary_absolute", {})
        if pa.get("ample_above") and ratio[-1][1] >= pa["ample_above"]:
            D["excess_to_required_ratio"]["in_range"] = True
            D["excess_to_required_ratio"]["above_range"] = True
    D["excess_to_required_ratio"]["note"] = "C11: dead-man switch under tiering — price (SARON vs the absorption anchor) leads"
    cap = S.merge_series(_ffill(fac, gi), _ffill(req, gi), lambda f, r: round(f * r, 0)) if fac and req else []
    D["threshold_capacity"] = entry("threshold_capacity", cap, "Aggregate 0%-remunerated capacity = threshold factor × minimum reserves", "weekly", unit, cfg, z_window=26)
    util = S.merge_series(gi, cap, lambda a, c: round(a / c, 3) if c else None) if cap else []
    util = [(d, v) for d, v in util if v is not None]
    D["threshold_utilisation"] = entry("threshold_utilisation", util, "Aggregate threshold headroom (sight deposits / capacity) — DISPLAY ONLY", "weekly", "ratio", cfg, z_window=26)
    D["threshold_utilisation"]["display_only"] = True
    D["threshold_utilisation"]["note"] = b["derived"]["threshold_utilisation"]["note"]
    # ── monthly absorption / balance sheet ──
    vrg = raw["absorbing_repos"]
    stock = S.add_series(es, vrg) if (es and vrg) else es
    D["absorption_stock"] = entry("absorption_stock", stock, "Absorption stock = SNB Bills + absorbing repos (monthly)", "monthly", unit, cfg, z_window=12)
    gb = raw["sight_deposits_domestic_monthly"]
    share = S.merge_series(stock, gb, lambda a, g: round(a / (g + a), 4) if (g + a) else None) if stock and gb else []
    share = [(d, v) for d, v in share if v is not None]
    D["absorption_share"] = entry("absorption_share", share, "Absorption share = stock / (sight deposits + stock)", "monthly", "ratio", cfg, spec=_spec(th, "absorption_share"),
                                  prev_level=pl.get("absorption_share"), z_window=12)
    sa = (th.get("absorption_share") or {}).get("secondary_absolute")
    if sa and share:
        _cap_watch(D["absorption_share"], {"watch": sa["watch"], "stress": sa["stress"], "crisis": sa.get("crisis", 9.0)})
    D["gross_reserve_creation"] = entry("gross_reserve_creation", S.add_series(gb, stock) if gb and stock else [], "Gross reserve creation = sight deposits + absorption stock (monthly)", "monthly", unit, cfg, z_window=12)
    D["gross_reserve_creation"]["note"] = b["derived"]["gross_reserve_creation"]["note"]
    vb = raw_vb = S.clean(data.get("snbbipo:VB", []))
    nl = S.merge_series(gb, vb, lambda g, c: g - c) if gb and vb else []
    D["net_liquidity"] = entry("net_liquidity", nl, "Net liquidity = sight deposits − Confederation cash (monthly, display)", "monthly", unit, cfg, z_window=12)
    D["net_liquidity"]["display_only"] = True
    D["net_liquidity"]["note"] = b["derived"]["net_liquidity"]["note"]
    fxi = raw["fx_investments"]
    D["fx_investments_change_pct"] = entry("fx_investments_change_pct", S.pct_change_series(fxi, 1), "Foreign currency investments — month-on-month %", "monthly", "%", cfg, z_window=12)
    # ── bills ladder / FX intervention proxy (weekly) ──
    D["bills_maturing_week"] = entry("bills_maturing_week", S.clean(data.get("bills_maturing_week", [])), "SNB Bills maturing in the coming week (register shape × balance-sheet stock)", "weekly", unit, cfg, z_window=26)
    D["bills_maturing_week"]["status"] = "fresh" if data.get("bills_maturing_week") else "unavailable"
    D["bills_roll_off_4w"] = entry("bills_roll_off_4w", S.clean(data.get("bills_maturing_4w", [])), "SNB Bills maturing in the next 4 weeks", "weekly", unit, cfg, z_window=26)
    D["bills_roll_off_4w"]["status"] = "fresh" if data.get("bills_maturing_4w") else "unavailable"
    mw = D["bills_maturing_week"]["value"] or 0.0
    fxp = [(d, round(v - (mw if d == wow[-1][0] else 0.0), 1)) for d, v in wow] if wow else []
    D["fx_intervention_proxy_weekly"] = entry("fx_intervention_proxy_weekly", fxp, "Weekly sight-deposit jump not explained by Bills maturities (FX purchase proxy)", "weekly", unit, cfg, z_window=26)
    if fxp:
        _apply(D["fx_intervention_proxy_weekly"], _two_sided("fx_intervention_proxy_weekly", fxp, _spec(th, "sight_deposits_wow") or {}, "weekly", pl.get("fx_intervention_proxy_weekly")))
    wow_level = D["sight_deposits_wow"].get("level", "NO DATA")
    fx_suspect = bool(wow and wow[-1][1] > 0 and (wow_level in ("WATCH", "STRESS", "CRISIS") and D["sight_deposits_wow"].get("side") == "high" or wow[-1][1] >= 5000) and (mw < 0.5 * wow[-1][1]))
    fxq = raw["fx_transactions_quarterly"]
    D["fx_intervention_suspect"] = {"label": "FX_INTERVENTION_SUSPECT", "value": fx_suspect, "status": "fresh" if wow else "unavailable", "date": wow[-1][0] if wow else None,
                                    "weekly_jump": wow[-1][1] if wow else None, "bills_maturing_week": mw, "last_quarter_fx_purchases": fxq[-1][1] if fxq else None, "last_quarter": fxq[-1][0] if fxq else None,
                                    "note": "C12: jump ≥ p90 (or ≥ +5 bn) not explained by Bills maturities; monthly confirmation GBI/GSGSF; quarterly snbfxtr"}
    # ── other sight deposits (foreign / institutions) ──
    ueb = raw["other_sight_deposits_weekly"]
    uw = S.diff_series(ueb, 1)
    D["other_sight_deposits_wow"] = entry("other_sight_deposits_wow", uw, "Other sight deposits (foreign banks, institutions, others) — week-on-week", "weekly", unit, cfg, z_window=26)
    if uw:
        _apply(D["other_sight_deposits_wow"], _two_sided("other_sight_deposits_wow", uw, _spec(th, "other_sight_deposits_wow") or {}, "weekly", pl.get("other_sight_deposits_wow")))
    # ── bills auction premium ──
    saron = S.clean(data.get("snbgwdzid:SARON", []))
    by = S.clean(data.get("bills_yield_28d", []))
    byms = S.merge_series(by, _ffill(saron, by), lambda y, s: round((y - s) * 100, 1)) if by and saron else []
    D["bills_yield_minus_saron_bps"] = entry("bills_yield_minus_saron_bps", byms, "SNB Bills 28-day auction yield − SARON (bps)", "event", "bps", cfg, z_window=12)
    if byms:
        D["bills_yield_minus_saron_bps"]["status"] = "fresh"
        D["bills_yield_minus_saron_bps"]["level"] = "WATCH" if abs(byms[-1][1]) > 3 else "SAFE"
    bb = S.clean(data.get("bills_btc", []))
    # ── phase ──
    phase = "STEADY"
    if stock and len(stock) >= 4:
        s3 = [v for _, v in stock[-4:]]
        if s3[-1] > s3[-2] > s3[-3]:
            phase = "ABSORBING"
        elif s3[-1] < s3[-2] < s3[-3]:
            phase = "RELEASING"
    if fxq and fxq[-1][1] > 1000 and p13 and p13[-1][1] > 0:
        phase = "FX_EXPANSION"
    D["balance_sheet_phase"] = {"label": "Balance-sheet phase", "value": None, "phase": phase, "status": "fresh" if stock else "unavailable", "date": stock[-1][0] if stock else None,
                                "note": b["derived"]["balance_sheet_phase"]["formula"]}
    # ── flags & score ──
    flags: List[str] = []
    if fx_suspect:
        flags.append("FX_INTERVENTION_SUSPECT")
    if fac and len(fac) >= 2 and fac[-1][1] != fac[-2][1] and gi and (S.last(gi)[0] <= (fac[-1][0][:7] + "-31")) and fac[-1][0] >= (gi[-1][0][:8] + "01" if gi else ""):
        flags.append("THRESHOLD_FACTOR_CHANGE")
    if D["absorption_share"].get("level") in ("WATCH", "STRESS", "CRISIS"):
        flags.append("ABSORPTION_INTENSITY")
    if D["bills_roll_off_4w"]["value"] and es and D["bills_roll_off_4w"]["value"] >= 0.2 * es[-1][1]:
        flags.append("BILLS_ROLL_OFF_AHEAD")
    if (raw["supplying_repos"] and raw["supplying_repos"][-1][1] > 0) or (raw["mm_operations_supplied_month"] and raw["mm_operations_supplied_month"][-1][1] > 0):
        flags.append("SNB_SUPPLYING")
    if D["other_sight_deposits_wow"].get("level") in ("WATCH", "STRESS", "CRISIS"):
        flags.append("FOREIGN_SIGHT_DEPOSITS_JUMP")
    absm = raw["mm_operations_absorbed_month"]
    if absm and len(absm) >= 2 and absm[-2][1] and abs(absm[-1][1] / absm[-2][1] - 1) >= 0.25:
        flags.append("REPO_ABSORPTION_CHANGE")
    if (byms and abs(byms[-1][1]) > 3) or (bb and bb[-1][1] < 1.0):
        flags.append("SNB_BILLS_AUCTION_ANOMALY")
    C = Comps(cfg, "sum", -1.5, 1.5)
    C.flow("sight_deposits_13w_band", 1.0 if sb["signal"] == "RISK_ON" else -1.0 if sb["signal"] == "RISK_OFF" else 0.0)
    lv = D["absorption_share"].get("level")
    C.level("absorption_share_level", -0.5 if lv == "WATCH" else -1.0 if lv in ("STRESS", "CRISIS") else 0.0)
    if "SNB_SUPPLYING" in flags:
        C.event("snb_supplying", -1.0)
    if fx_suspect:
        C.flow("fx_intervention_suspect", 0.5)
    score = C.score()
    reg = "NO DATA" if not gi else "INJECTION" if score >= 0.5 else "DRAIN" if score <= -0.5 else "NEUTRAL"
    alerts = [_alert("sight_deposits_wow", D["sight_deposits_wow"], "weekly reserve jump / drop (FX purchases, absorption, Confederation)"),
              _alert("excess_to_required_ratio", D["excess_to_required_ratio"], "dead-man switch: 8.7x today"),
              _alert("absorption_share", D["absorption_share"], "SNB holding back an unusual share of reserves (35% WATCH / 45% STRESS)"),
              _alert("other_sight_deposits_wow", D["other_sight_deposits_wow"], "foreign banks / institutions — hot money or intervention settlement"),
              {"metric": "supplying_repos", "level": "STRESS" if "SNB_SUPPLYING" in flags else "SAFE", "value": raw["supplying_repos"][-1][1] if raw["supplying_repos"] else 0.0, "threshold": {"watch": 0},
               "status": E["supplying_repos"]["status"], "action_hint": "any liquidity-supplying operation at 0% policy = scarcity signal"}]
    tl = "GREEN" if reg == "INJECTION" else "RED" if reg == "DRAIN" else "YELLOW" if reg == "NEUTRAL" else "NONE"
    signals = {"traffic_light": tl, "score": score, "label": reg, "flags": flags, "components": C.to_dict(),
               "detail": "GI %s (wow %s, 13w %s%%, %s) · absorption %s (%s%%) · ratio %sx · factor %s · phase %s" % (
                   gi[-1][1] if gi else None, wow[-1][1] if wow else None, p13[-1][1] if p13 else None, sb["signal"], stock[-1][1] if stock else None,
                   round(share[-1][1] * 100, 1) if share else None, ratio[-1][1] if ratio else None, fac[-1][1] if fac else None, phase), "alerts": alerts}
    hd = [d for d, _ in S.tail(gi, 104)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("sight_deposits_domestic_weekly", gi), ("sight_deposits_total_weekly", raw["sight_deposits_total_weekly"]),
                                                                                  ("other_sight_deposits_weekly", ueb), ("sight_deposits_wow", wow), ("excess_to_required_ratio", ratio), ("threshold_utilisation", util))},
               "monthly": {"dates": [d for d, _ in S.tail(gb, 36)], "rows": {k: [dict(v).get(d) for d, _ in S.tail(gb, 36)] for k, v in (("sight_deposits_domestic_monthly", gb), ("fx_investments", fxi), ("snb_bills", es),
                                                                                                                             ("absorbing_repos", vrg), ("absorption_stock", stock), ("absorption_share", share), ("amounts_due_to_confederation", vb), ("net_liquidity", nl))}},
               "bills_register": [{"isin": r["isin"], "repayment": r["repayment"], "outstanding": r["outstanding"]} for r in sorted(rows, key=lambda r: r["repayment"])][:40],
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": reg, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "central_bank", cfg, b, E, D, signals, history)


# ═══════════════════════ 2 · FISCAL — Confederation ═══════════════════════
def build_fiscal(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["fiscal"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    E, raw = _entries(cfg, "fiscal", data, MAP_FI, unit, pl, {})
    E["mmdrc_auction_results"]["unit"] = "x"
    E["bond_auction_results"]["unit"] = "x"
    E["mmdrc_3m_yield_monthly"]["unit"] = "%"
    D: Dict[str, dict] = {}
    vb = raw["amounts_due_to_confederation"]
    mom = S.diff_series(vb, 1)
    D["confed_cash_mom"] = entry("confed_cash_mom", mom, "Confederation cash at the SNB — month-on-month (− = spent into reserves, + = drain)", "monthly", unit, cfg, z_window=12)
    sp = _spec(th, "confed_cash_mom") or {}
    sb = signal_band(mom[-1][1] if mom else None, mom, dict(sp, risk_on_below=None, risk_on_above=sp.get("drain_above"), risk_off_below=sp.get("injection_below")), "monthly")
    # note: signal_band's RISK_ON = high side; for fiscal, high = DRAIN
    fr = "NO DATA" if not mom else "DRAIN" if sb["signal"] == "RISK_ON" else "INJECTION" if sb["signal"] == "RISK_OFF" else "NEUTRAL"
    big = bool(mom) and abs(D["confed_cash_mom"].get("zscore") or 0) >= 1.5
    D["confed_cash_mom"]["level"] = "WATCH" if (fr == "DRAIN" or big) else "SAFE" if mom else "NO DATA"
    D["confed_cash_mom"]["side"] = ("drain" if (mom and mom[-1][1] > 0) else "injection") if big else None
    D["confed_cash_mom"]["percentile"] = sb.get("percentile")
    saron = S.clean(data.get("snbgwdzid:SARON", []))
    btc = S.clean(data.get("mmdrc_btc", []))
    D["mmdrc_bid_to_cover"] = entry("mmdrc_bid_to_cover", btc, "MMDRC (3-month) auction bid-to-cover", "event", "x", cfg, spec=_spec(th, "mmdrc_bid_to_cover"), prev_level=pl.get("mmdrc_bid_to_cover"), z_window=12)
    if btc:
        D["mmdrc_bid_to_cover"]["status"] = "fresh"
    my = S.clean(data.get("mmdrc_yield", []))
    mys = S.merge_series(my, _ffill(saron, my), lambda y, s: round((y - s) * 100, 1)) if my and saron else []
    D["mmdrc_yield_minus_saron_bps"] = entry("mmdrc_yield_minus_saron_bps", mys, "MMDRC 3m auction yield − SARON (bps; negative = tier-arbitrage bid, positive = weak demand)", "event", "bps", cfg,
                                             spec=_spec(th, "mmdrc_yield_minus_saron_bps"), prev_level=pl.get("mmdrc_yield_minus_saron_bps"), z_window=12)
    if mys:
        D["mmdrc_yield_minus_saron_bps"]["status"] = "fresh"
    bbtc = S.clean(data.get("bond_btc", []))
    D["bond_bid_to_cover"] = entry("bond_bid_to_cover", bbtc, "Confederation bond auction bid-to-cover (mean per auction day)", "event", "x", cfg, z_window=12)
    if bbtc:
        D["bond_bid_to_cover"]["status"] = "fresh"
        D["bond_bid_to_cover"]["level"] = "WATCH" if bbtc[-1][1] < 1.2 else "SAFE"
    own = S.clean(data.get("bond_own_share", []))
    D["bond_own_holdings_share"] = entry("bond_own_holdings_share", own, "Own holdings retained / (issued + retained) per auction", "event", "ratio", cfg, z_window=12)
    if own:
        D["bond_own_holdings_share"]["status"] = "fresh"
        D["bond_own_holdings_share"]["level"] = "WATCH" if (own[-1][1] > 0.30 and D["bond_bid_to_cover"].get("level") == "WATCH") else "SAFE"
    D["bond_tail_bp"] = {"label": "Bond auction tail (bp)", "value": None, "status": "unavailable", "date": None, "note": b["derived"]["bond_tail_bp"]["formula"], "pending_by_design": True}
    iss = S.clean(data.get("mmdrc_issued", []))
    bi = S.clean(data.get("bond_issued", []))
    from collections import defaultdict
    mon = defaultdict(float)
    last_d: Dict[str, str] = {}
    for d, v in iss + bi:
        mon[d[:7]] += v
        last_d[d[:7]] = max(last_d.get(d[:7], ""), d)
    ni = S.clean([(last_d[k], round(v, 1)) for k, v in mon.items()])  # dated at the last auction of the month (never a future month-end)
    D["net_issuance_month"] = entry("net_issuance_month", ni, "Gross Confederation issuance in the month (MMDRC + bonds; redemptions Phase 3)", "monthly", unit, cfg, z_window=12)
    score = 0.0 if fr in ("NO DATA", "NEUTRAL") else (-0.5 if fr == "DRAIN" else 0.5)
    CF = Comps(cfg, "sum", -0.5, 0.5).flow("confed_balances_mom_band", score)
    D["fiscal_regime"] = {"label": "Fiscal regime", "value": None, "regime": fr, "status": "fresh" if mom else "unavailable", "date": mom[-1][0] if mom else None}
    D["fiscal_regime_score"] = {"label": "Fiscal regime score (capped ±0.5)", "value": score, "range": [-0.5, 0.5], "status": "fresh", "date": mom[-1][0] if mom else None}
    D["mmt_note"] = {"label": "MMT note", "value": None, "status": "fresh", "date": None,
                     "text": "Confederation spending creates net financial assets; taxes destroy them; MMDRC/bond issuance drains reserves without changing that stock. Switzerland publishes no daily cash statement — the monthly SNB liability and the auctions are the footprint."}
    flags = []
    if D["mmdrc_bid_to_cover"].get("level") in ("WATCH", "STRESS", "CRISIS"):
        flags.append("MMDRC_DEMAND_WEAK")
    if mys and mys[-1][1] <= -5:
        flags.append("TIER_ARBITRAGE_BID")
    if mom and abs(D["confed_cash_mom"].get("zscore") or 0) >= 1.5:
        flags.append("CONFED_CASH_BIG_MOVE")
    alerts = [_alert("confed_cash_mom", D["confed_cash_mom"], "Confederation cash swing at the SNB (monthly)"),
              _alert("mmdrc_bid_to_cover", D["mmdrc_bid_to_cover"], "< 2.0x WATCH, < 1.5x STRESS (C7)"),
              _alert("mmdrc_yield_minus_saron_bps", D["mmdrc_yield_minus_saron_bps"], "weak demand = yield at/above SARON (C7 sign fix)")]
    tl = "GREEN" if fr == "INJECTION" else "RED" if fr == "DRAIN" else "YELLOW" if fr == "NEUTRAL" else "NONE"
    signals = {"traffic_light": tl, "score": score, "label": fr, "flags": flags, "components": CF.to_dict(),
               "detail": "Confederation %s (mom %s) · MMDRC %sx at %s%% (%s bp vs SARON) · bonds %sx" % (vb[-1][1] if vb else None, mom[-1][1] if mom else None, btc[-1][1] if btc else None, my[-1][1] if my else None,
                                                                                                        mys[-1][1] if mys else None, bbtc[-1][1] if bbtc else None), "alerts": alerts}
    hd = [d for d, _ in S.tail(vb, 36)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("amounts_due_to_confederation", vb), ("confed_cash_mom", mom), ("net_issuance_month", ni))},
               "auctions": [{"date": d, "type": "MMDRC", "btc": v, "yield": dict(my).get(d), "issued": dict(iss).get(d)} for d, v in S.tail(btc, 20)] +
                           [{"date": d, "type": "Bond", "btc": v, "yield": dict(S.clean(data.get("bond_yield", []))).get(d), "issued": dict(bi).get(d), "own_share": dict(own).get(d)} for d, v in S.tail(bbtc, 12)],
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": fr, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "fiscal", cfg, b, E, D, signals, history)


# ═══════════════════════ 3 · BANKING ═══════════════════════
def build_banking(cfg: dict, data: Dict[str, Series], rates_block: Optional[dict] = None, prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["banking"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    E, raw = _entries(cfg, "banking", data, MAP_BK, unit, pl, {})
    D: Dict[str, dict] = {}
    loans, mort, dep, liq, m3, mb = raw["loans_domestic_total"], raw["mortgages_domestic"], raw["customer_deposits"], raw["bank_liquid_assets"], raw["m3"], raw["monetary_base_monthly"]
    ly = S.pct_change_series(loans, 12)
    D["loans_yoy_pct"] = entry("loans_yoy_pct", ly, "Domestic loans — y/y %", "monthly", "%", cfg, spec=_spec(th, "loans_yoy_pct"), prev_level=pl.get("loans_yoy_pct"), z_window=12)
    D["mortgages_yoy_pct"] = entry("mortgages_yoy_pct", S.pct_change_series(mort, 12), "Domestic mortgages — y/y %", "monthly", "%", cfg, z_window=12)
    dy = S.pct_change_series(dep, 12)
    D["deposits_yoy_pct"] = entry("deposits_yoy_pct", dy, "Customer deposits — y/y %", "monthly", "%", cfg, z_window=12)
    ci = S.rolling_zscore(S.diff_series(ly, 3), 36)
    D["credit_impulse"] = entry("credit_impulse", ci, "Credit impulse (z of 3m change in loans y/y) — housing/collateral signal, not in the score", "monthly", "σ", cfg, z_window=12)
    if ci:
        z = ci[-1][1]
        D["credit_impulse"]["level"] = "STRESS" if abs(z) >= 2 else "WATCH" if abs(z) >= 1 else "SAFE"
    D["credit_impulse"]["note"] = b["derived"]["credit_impulse"]["note"]
    D["loan_to_deposit"] = entry("loan_to_deposit", S.merge_series(loans, dep, lambda a, c: round(a / c, 4)), "Loans / customer deposits", "monthly", "ratio", cfg, z_window=12)
    lad = S.merge_series(liq, dep, lambda a, c: round(a / c, 4))
    D["liquid_assets_to_deposits"] = entry("liquid_assets_to_deposits", lad, "Bank liquid assets / customer deposits", "monthly", "ratio", cfg, z_window=12)
    D["m3_yoy_pct"] = entry("m3_yoy_pct", S.pct_change_series(m3, 12), "M3 — y/y %", "monthly", "%", cfg, z_window=12)
    D["money_multiplier"] = entry("money_multiplier", S.merge_series(m3, mb, lambda a, c: round(a / c, 3)), "M3 / monetary base", "monthly", "x", cfg, z_window=12)
    pol = S.clean(data.get("snbgwdzid:LZ", []))
    m5 = raw["mortgage_rate_fixed_5y"]
    m5p = S.merge_series(m5, _ffill(pol, m5), lambda a, c: round((a - c) * 100, 1)) if m5 and pol else []
    D["mortgage_5y_minus_policy_bps"] = entry("mortgage_5y_minus_policy_bps", m5p, "Fixed 5y mortgage rate (median) − policy rate (bps)", "monthly", "bps", cfg, z_window=12)
    # transmission
    def pct_of(ser: Series, n: int = 60) -> Optional[float]:
        if not ser:
            return None
        return S.percentile_rank(ser[-1][1], S.window_sample(ser, n))
    dpr = pct_of(dy)
    lpr = pct_of(lad)
    mpr = pct_of(m5p)
    sig = "YELLOW"
    # liquid assets (FMI = cash + sight deposits at central banks) shrink MECHANICALLY while the SNB sterilises via Bills/repos (banks swap
    # sight deposits for SNB Bills, still HQLA) — a low liquid/deposits ratio alone is not a transmission failure; it needs weak deposits too
    dep_weak = dy and dpr is not None and dpr <= 25
    if dy and (dy[-1][1] <= (S.percentile_value(S.window_sample(dy, 60), 10) or -99)) or (lad and lpr is not None and lpr <= 5 and dep_weak):
        sig = "RED"
    elif dy and dy[-1][1] >= 0 and (lpr is None or lpr >= 20 or not dep_weak) and (mpr is None or 20 <= mpr <= 80):
        sig = "GREEN"
    D["transmission_signal"] = {"label": "Transmission signal", "value": None, "signal": sig, "status": "fresh" if dy else "unavailable", "date": dy[-1][0] if dy else None,
                                "note": b["derived"]["transmission_signal"]["formula"], "inputs": {"deposits_yoy_pctile": dpr, "liquid_to_deposits_pctile": lpr, "mortgage_spread_pctile": mpr},
                                "caveat": "liquid assets fall mechanically under SNB sterilisation (sight deposits → SNB Bills); RED on liquidity needs deposits y/y ≤ p25 too"}
    score = {"GREEN": 1.0, "YELLOW": 0.0, "RED": -1.0}[sig] if dy else 0.0
    alerts = [_alert("loans_yoy_pct", D["loans_yoy_pct"], "credit growth vs 10-year history"),
              _alert("credit_impulse", D["credit_impulse"], "housing/collateral signal (display; not in score)"),
              {"metric": "liquid_assets_to_deposits", "level": "WATCH" if (lpr is not None and lpr <= 10) else "SAFE" if lad else "NO DATA", "value": lad[-1][1] if lad else None, "threshold": None,
               "status": D["liquid_assets_to_deposits"]["status"], "action_hint": "bank liquidity buffer vs deposits (p10 of 5y = WATCH)"}]
    signals = {"traffic_light": sig if dy else "NONE", "score": score, "label": sig if dy else "NO DATA", "flags": [],
               "detail": "loans y/y %s%% · deposits y/y %s%% · liquid/deposits %s · mortgage 5y %s%% (+%s bp vs policy) · M3 y/y %s%%" % (
                   ly[-1][1] if ly else None, dy[-1][1] if dy else None, lad[-1][1] if lad else None, m5[-1][1] if m5 else None, m5p[-1][1] if m5p else None, D["m3_yoy_pct"]["value"]), "alerts": alerts}
    hd = [d for d, _ in S.tail(loans, 36)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("loans_domestic_total", loans), ("mortgages_domestic", mort), ("customer_deposits", dep), ("bank_liquid_assets", liq), ("m3", m3),
                                                                                   ("loans_yoy_pct", ly), ("deposits_yoy_pct", dy), ("mortgage_rate_fixed_5y", m5))},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": sig, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "banking", cfg, b, E, D, signals, history)


# ═══════════════════════ 4 · RATES ═══════════════════════
def build_rates(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["rates"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    E, raw = _entries(cfg, "rates", data, MAP_RT, "%", pl, {})
    for k in LAGGED_OK:
        if raw[k] and E[k]["status"] in ("stale", "degraded"):
            E[k]["status"] = "stale"
            E[k]["equivalence_note"] = "SNB publishes term repo / compound rates ~3 weeks late (stale-by-design until SIX is wired)"
    for k in ("policy_rate", "rate_above_threshold", "special_rate"):
        E[k]["frequency"] = "event"
        E[k]["status"] = "fresh" if raw[k] else "unavailable"
    E["mmdrc_3m_yield"]["frequency"] = "event"
    if raw["mmdrc_3m_yield"]:
        E["mmdrc_3m_yield"]["status"] = "fresh"
    saron, pol, zig, eng = raw["saron"], raw["policy_rate"], raw["rate_above_threshold"], raw["special_rate"]
    polf = _ffill(pol, saron)
    D: Dict[str, dict] = {}
    sp = S.merge_series(saron, polf, lambda a, c: round((a - c) * 100, 2))
    anchor = S.merge_series(saron, polf, lambda a, c: round((a - (c - 0.05)) * 100, 2))
    spec = _spec(th, "saron_minus_absorption_rate_bps") or {}
    absr = spec.get("secondary_absolute", {"watch": 5, "stress": 10, "crisis": 20})
    D["saron_minus_absorption_rate_bps"] = entry("saron_minus_absorption_rate_bps", anchor, "SARON − absorption anchor (policy − 5 bp), bps — STRESS SPREAD", "daily", "bps", cfg,
                                                 spec=spec, prev_level=pl.get("saron_minus_absorption_rate_bps"), z_window=30)
    if anchor:
        vals = [v for _, v in anchor]
        p_lvl = _persistent_level(vals, absr, 3)
        pct_lvl = D["saron_minus_absorption_rate_bps"].get("level", "SAFE")
        rank = {"NO DATA": -1, "SAFE": 0, "WATCH": 1, "STRESS": 2, "CRISIS": 3}
        # percentile guard: since 2025-06-20 SARON has been pinned within ±1 bp of the anchor, so p95 can sit at +1 bp — a percentile WATCH
        # only counts when the print is at least half the absolute WATCH (2.5 bp); otherwise the absolute (persistent) level decides
        pct_ok = rank[pct_lvl] >= 1 and vals[-1] >= absr["watch"] / 2
        lvl = p_lvl if rank[p_lvl] >= rank["STRESS"] else ("WATCH" if (pct_ok or p_lvl == "WATCH") else "SAFE")
        D["saron_minus_absorption_rate_bps"]["level"] = lvl
        D["saron_minus_absorption_rate_bps"]["percentile_level"] = pct_lvl
        D["saron_minus_absorption_rate_bps"]["absolute_level"] = p_lvl
        pt = D["saron_minus_absorption_rate_bps"].get("thresholds") or {}
        D["saron_minus_absorption_rate_bps"]["thresholds"] = {"method": "absolute", "levels": {"WATCH": absr["watch"], "STRESS": absr["stress"], "CRISIS": absr["crisis"], "LOW_SIDE": spec.get("low_side_excess", -10)},
                                                              "percentile_levels": pt.get("levels"), "window": pt.get("window"), "n": pt.get("n"),
                                                              "note": "absolute anchors decide (persistent 3 sessions); percentile WATCH counts only above 2.5 bp"}
        fc = len(vals) >= 3 and all(v >= absr["watch"] for v in vals[-3:])
        fl = len(vals) >= 5 and all(v <= spec.get("low_side_excess", -10) for v in vals[-5:])
        D["saron_minus_absorption_rate_bps"]["friction_confirmed"] = fc
        D["saron_minus_absorption_rate_bps"]["floor_leak"] = fl
    else:
        fc = fl = False
    D["saron_minus_policy_bps"] = entry("saron_minus_policy_bps", sp, "SARON − SNB policy rate (bps) — cross-currency alias", "daily", "bps", cfg, z_window=30)
    D["saron_minus_policy_bps"]["level"] = D["saron_minus_absorption_rate_bps"].get("level", "NO DATA")
    D["saron_minus_policy_bps"]["note"] = b["derived"]["saron_minus_policy_bps"]["note"]
    bp = S.merge_series(S.merge_series(saron, _ffill(zig, saron), lambda a, z: a - z), _ffill(S.merge_series(eng, zig, lambda e, z: e - z), saron), lambda n, w: round(n / w, 3) if w else None) if zig and eng else []
    bp = [(d, v) for d, v in bp if v is not None]
    D["band_position"] = entry("band_position", bp, "Position in the band [tier rate above threshold, special rate] (0..1)", "daily", "ratio", cfg, spec=_spec(th, "band_position"), prev_level=pl.get("band_position"), z_window=30)
    if bp:
        _apply(D["band_position"], _two_sided("band_position", bp, dict(_spec(th, "band_position") or {}, method="absolute"), "daily", pl.get("band_position")))
    sar3m = raw["sar3m"]
    t3 = S.merge_series(sar3m, saron, lambda a, s: round((a - s) * 100, 2))
    D["sar3m_minus_saron_bps"] = entry("sar3m_minus_saron_bps", t3, "SAR3M − SARON (bps; term premium / cut-hike pricing; lagged)", "daily", "bps", cfg, spec=_spec(th, "sar3m_minus_saron_bps"), prev_level=pl.get("sar3m_minus_saron_bps"), z_window=30)
    if t3:
        _apply(D["sar3m_minus_saron_bps"], _two_sided("sar3m_minus_saron_bps", t3, _spec(th, "sar3m_minus_saron_bps") or {}, "daily", pl.get("sar3m_minus_saron_bps")))
        D["sar3m_minus_saron_bps"]["status"] = "stale" if E["sar3m"]["status"] != "fresh" else "fresh"
    c3 = raw["saron_3m_compound"]
    D["saron_3m_compound_minus_policy_bps"] = entry("saron_3m_compound_minus_policy_bps", S.merge_series(c3, _ffill(pol, c3), lambda a, c: round((a - c) * 100, 2)), "SARON 3M compound − policy (bps; lagged)", "daily", "bps", cfg, z_window=30)
    y1, y2, y5, y10, y20, y30 = raw["confed_1y"], raw["confed_2y"], raw["confed_5y"], raw["confed_10y"], raw["confed_20y"], raw["confed_30y"]
    D["confed_2y_minus_policy_bps"] = entry("confed_2y_minus_policy_bps", S.merge_series(y2, _ffill(pol, y2), lambda a, c: round((a - c) * 100, 1)), "Confederation 2y − policy rate (bps; next-moves pricing)", "daily", "bps", cfg, z_window=30)
    c102 = S.merge_series(y10, y2, lambda a, c: round((a - c) * 100, 1))
    D["curve_10y_2y_bps"] = entry("curve_10y_2y_bps", c102, "Confederation 10y − 2y (bps)", "daily", "bps", cfg, spec=_spec(th, "curve_10y_2y_bps"), prev_level=pl.get("curve_10y_2y_bps"), z_window=30)
    if c102:
        _apply(D["curve_10y_2y_bps"], _two_sided("curve_10y_2y_bps", c102, _spec(th, "curve_10y_2y_bps") or {}, "daily", pl.get("curve_10y_2y_bps")))
    D["curve_30y_10y_bps"] = entry("curve_30y_10y_bps", S.merge_series(y30, y10, lambda a, c: round((a - c) * 100, 1)), "Confederation 30y − 10y (bps)", "daily", "bps", cfg, spec=_spec(th, "curve_30y_10y_bps"), prev_level=pl.get("curve_30y_10y_bps"), z_window=30)
    d5 = S.diff_series(y10, 5, 100.0)
    D["confed_10y_5d_change_bps"] = entry("confed_10y_5d_change_bps", d5, "Confederation 10y — 5-session change (bps)", "daily", "bps", cfg, z_window=30)
    if d5:
        _apply(D["confed_10y_5d_change_bps"], _two_sided("confed_10y_5d_change_bps", d5, dict(_spec(th, "confed_10y_5d_change_bps") or {}, method="absolute"), "daily", pl.get("confed_10y_5d_change_bps")))
    my = raw["mmdrc_3m_yield"]
    mys = S.merge_series(my, _ffill(saron, my), lambda a, s: round((a - s) * 100, 1)) if my and saron else []
    D["mmdrc_3m_minus_saron_bps"] = entry("mmdrc_3m_minus_saron_bps", mys, "MMDRC 3m auction yield − SARON (bps)", "event", "bps", cfg, z_window=12)
    if mys:
        D["mmdrc_3m_minus_saron_bps"]["status"] = "fresh"
    D["friction_confirmed"] = {"label": "friction_confirmed (SARON ≥ policy 3 sessions)", "value": fc, "status": "fresh" if anchor else "unavailable", "date": anchor[-1][0] if anchor else None}
    D["floor_leak"] = {"label": "floor_leak (SARON ≤ anchor − 10 bp for 5 sessions)", "value": fl, "status": "fresh" if anchor else "unavailable", "date": anchor[-1][0] if anchor else None}
    lvl = D["saron_minus_absorption_rate_bps"].get("level", "NO DATA")
    v = anchor[-1][1] if anchor else None
    calm = v is not None and -5 <= v <= 3
    score = 0.75 if (calm and lvl == "SAFE") else 0.0 if lvl in ("SAFE", "WATCH") else -0.75 if lvl == "STRESS" else -1.5 if lvl == "CRISIS" else 0.0
    if fl:
        score -= 0.25
    score = round(max(-1.5, min(1.5, score)), 2)
    label = "NO DATA" if v is None else "CORRIDOR CALM" if score >= 0.75 else "FLOOR FRICTION" if fc else "FUNDING STRESS" if lvl in ("STRESS", "CRISIS") else "WATCH" if lvl == "WATCH" else "CORRIDOR CALM"
    flags = []
    if fl:
        flags.append("FLOOR_LEAK")
    if fc and mys and mys[-1][1] <= -10:
        flags.append("COLLATERAL_SCARCITY")
    alerts = [_alert("saron_minus_absorption_rate_bps", D["saron_minus_absorption_rate_bps"], "0 = at the absorption anchor; +5 = at policy (friction); +10 STRESS; +20 CRISIS"),
              _alert("band_position", D["band_position"], "0 = −0.25% tier, 1 = special rate"),
              _alert("sar3m_minus_saron_bps", D["sar3m_minus_saron_bps"], "term premium / hike pricing (3-week lag)"),
              _alert("curve_10y_2y_bps", D["curve_10y_2y_bps"], "Confederation curve slope"),
              _alert("confed_10y_5d_change_bps", D["confed_10y_5d_change_bps"], "±15 bp WATCH, ±25 bp STRESS in 5 sessions")]
    tl = "GREEN" if score >= 0.75 else "YELLOW" if score >= 0 else "RED"
    signals = {"traffic_light": tl if v is not None else "NONE", "score": score, "label": label, "flags": flags,
               "detail": "SARON %s vs anchor %s bp (vs policy %s bp) · band %s · SAR3M−SARON %s · 2y−policy %s · 10y−2y %s · MMDRC−SARON %s" % (
                   saron[-1][1] if saron else None, v, sp[-1][1] if sp else None, bp[-1][1] if bp else None, t3[-1][1] if t3 else None, D["confed_2y_minus_policy_bps"]["value"], D["curve_10y_2y_bps"]["value"], mys[-1][1] if mys else None), "alerts": alerts}
    hd = [d for d, _ in S.tail(saron, 120)]
    history = {"dates": hd, "rows": {k: [dict(s).get(d) for d in hd] for k, s in (("saron", saron), ("saron_minus_absorption_rate_bps", anchor), ("saron_minus_policy_bps", sp), ("band_position", bp),
                                                                                  ("confed_2y", y2), ("confed_10y", y10), ("curve_10y_2y_bps", c102), ("sar3m_minus_saron_bps", t3))},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": label, "score": score}] if hd else []))[-120:]}
    out = _base(cfg["currency"], "rates", cfg, b, E, D, signals, history)
    wired = {k: e for k, e in E.items() if e.get("source_id") and k not in LAGGED_OK}
    h = _health(wired, len(wired))
    h["series_loaded"] = sum(1 for e in E.values() if e.get("source_id") and e.get("status") != "unavailable")
    h["series_expected"] = sum(1 for e in E.values() if e.get("source_id"))
    h["lagged_by_design"] = [k for k in LAGGED_OK if E[k].get("status") == "stale"]
    out["source_health"] = dict(out["source_health"], **h)
    return out
