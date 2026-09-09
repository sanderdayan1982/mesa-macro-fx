"""NZD block builders — RBNZ floor system under the LSAP unwind, weekly full-allotment OMO at OCR + 10 bp (config/nzd.json v0.2, triangulated 2026-09-08).
  1 central bank — DAILY settlement cash (D12), ORRF / FX swaps / BLF, weekly reverse-repo OMO (D3: allocated + stock), LSAP sales & repurchases,
                   monthly R1/R3 (balance sheet, CSA, monetary base) and D10 (influences on settlement cash); residual daily flow (coincident, noisy)
  2 fiscal       — Crown Settlement Account (R3), D10 government cash influence and debt transactions, NZDM tenders (T-bills Tuesday, bonds Thursday),
                   upcoming tenders (SUPPLY_AHEAD), non-resident holdings (D30), coupon / maturity calendar (bonds on issue)
  3 banking      — C5 sector lending, C50 broad money / private credit, L2 core funding ratio (display + RED gate only)
  4 rates        — OCR / ODR / ORRF corridor, overnight interbank (sparse), bank bills 30/60/90, NZGB 1/2/5/10, swaps, D9 turnover
Data keys from run.py: 'D12:settlement_cash', 'D12:overnight_reverse_repo', 'D12:fx_swaps', 'D12:blf_amount', 'D3:rr_omo_allocated',
'D3:rr_omo_outstanding', 'D3:rr_omo_spread_bps', 'D3:lsap_sales', 'D3:govt_bond_repurchases', 'D3:bmls_nzgb', 'R1:<id>', 'R3:<id>', 'D10:<name>',
'D30:<id>', 'C5:<id>', 'C50:<id>', 'L2:<id>', 'B2:<id>', 'D9:<id>', 'NZDM:tbill_*', 'NZDM:bond_*', '_upcoming_tenders', '_bonds_on_issue', '_tender_rows'."""
from __future__ import annotations
import datetime as _dt
from typing import Dict, List, Optional, Tuple
from . import series as S
from .series import Series
from .thresholds import classify
from .scoring import Comps
from .blocks import entry, _prev_levels, _alert, _health
from .blocks_jpy import _entries, _base, _ffill, _spec, _cap_watch
from .blocks_chf import _two_sided, _apply
from .blocks_gbp import _persistent_level

MAP_CB = {"settlement_cash_daily": "D12:settlement_cash", "orrf_usage_daily": "D12:overnight_reverse_repo", "fx_swaps_daily": "D12:fx_swaps", "blf_usage_daily": "D12:blf_amount",
          "omo_allocated_weekly": "D3:rr_omo_allocated", "omo_outstanding": "D3:rr_omo_outstanding", "omo_spread_to_ocr_bps": "D3:rr_omo_spread_bps",
          "lsap_sales_month": "D3:lsap_sales_month", "bond_repurchases": "D3:govt_bond_repurchases", "bmls_holdings": "D3:bmls_nzgb",
          "total_assets": "R1:RBNZ.MRA", "lsap_holdings": "R1:RBNZ.MRA1222", "reverse_repos_monthly": "R1:RBNZ.MRA135", "fx_investments": "R1:RBNZ.MRA103",
          "deposits_total": "R1:RBNZ.MRL121", "currency_in_circulation": "R1:RBNZ.MRL124", "monetary_base": "R3:UGEN.MR7019",
          "settlement_balances_monthly": "R3:MFS.MRL02211.DZZZZZA", "net_foreign_assets": "R3:UGEN.MR7001",
          "d10_govt_cash_influence": "D10:govt_cash_influence", "d10_rbnz_transactions": "D10:rbnz_transactions", "d10_fx": "D10:fx",
          "d10_net_reverse_repos": "D10:net_reverse_repos", "d10_net_fx_swaps": "D10:net_fx_swaps"}
MAP_FI = {"crown_settlement_account": "R3:MFS.MRL02221.DZP01ZZZN", "govt_cash_influence_month": "D10:govt_cash_influence", "bonds_issued_month": "D10:bonds_issued",
          "bond_maturities_month": "D10:bond_maturities", "tbills_issued_month": "D10:tbills_issued", "tbills_matured_month": "D10:tbills_matured",
          "tbill_tender_btc": "NZDM:tbill_coverage", "tbill_tender_yield": "NZDM:tbill_wavg_short", "tbill_tender_volume": "NZDM:tbill_accepted",
          "tbill_allocation_ratio": "NZDM:tbill_allocation_ratio", "tbill_1y_yield": "NZDM:tbill_wavg_long",
          "bond_tender_coverage": "NZDM:bond_coverage", "bond_tender_tail_bp": "NZDM:bond_tail_bp", "bond_tender_volume": "NZDM:bond_accepted",
          "tender_schedule_month": "NZDM:schedule_month", "nzgb_non_resident_holdings": "D30:ROSN.MAB2.P1ZZW", "nzgb_outstanding": "D30:ROSI.MAA1.P1",
          "treasury_residual_cash": None, "nzdm_ecp_on_issue": None, "kauri_holdings": None}
MAP_BK = {"housing_lending": "C5:CRDS.MALP1", "business_lending": "C5:CRDS.MALP3", "agriculture_lending": "C5:CRDS.MALP4", "consumer_lending": "C5:CRDS.MALP2",
          "broad_money": "C50:MCA.MDB.BM", "private_sector_credit": "C50:MCA.MDC.PSC", "core_funding_ratio": "L2:LIQ.MBA7.ZZZZZR4", "core_funding": "L2:LIQ.MBA5.ZZZZZR4",
          "loans_and_advances": "L2:LIQ.MBA8", "mismatch_ratio_1w": None, "deposits_by_sector_total": None, "mortgage_rate_2y_special": None}
MAP_RT = {"ocr": "B2:INM.DP1.N", "odr": "B2:INM.DD1.N", "orrf_rate": "B2:INM.DD2.N", "overnight_interbank": "B2:INM.DN.NZK", "bank_bill_30d": "B2:INM.DB01.NZZV",
          "bank_bill_60d": "B2:INM.DB02.NZZV", "bank_bill_90d": "B2:INM.DB03.NZZV", "nzgb_1y": "B2:INM.DG101.NZZCF", "nzgb_2y": "B2:INM.DG102.NZZCF",
          "nzgb_5y": "B2:INM.DG105.NZZCF", "nzgb_10y": "B2:INM.DG110.NZZCF", "swap_1y": "B2:INM.DS01.NZZC", "swap_2y": "B2:INM.DS02.NZZC", "swap_10y": "B2:INM.DS10.NZZC",
          "swap_2_10_spread_bps": "B2:INM.DS61.NZZC", "nzgb_turnover_weekly": "D9:BTO.WAF"}
ZERO_IF_EMPTY_CB = ("orrf_usage_daily", "fx_swaps_daily", "blf_usage_daily")
RANK = {"NO DATA": -1, "SAFE": 0, "WATCH": 1, "STRESS": 2, "CRISIS": 3}


def _bd(d: str, n: int, holidays: set) -> str:
    """add n business days"""
    x = _dt.date.fromisoformat(d)
    step = 1 if n >= 0 else -1
    while n != 0:
        x += _dt.timedelta(days=step)
        if x.weekday() < 5 and x.isoformat() not in holidays:
            n -= step
    return x.isoformat()


def _event_days(cfg: dict, data: dict, upto: str) -> Dict[str, List[str]]:
    """coupon / maturity / LSAP-sale / tender-settlement / tax days from the calendars in data + config (N4/N9/N14)"""
    out: Dict[str, List[str]] = {"coupon": [], "maturity": [], "lsap": [], "settlement": [], "tax": []}
    for b in data.get("_bonds_on_issue") or []:
        m = b["maturity"]
        out["maturity"].append(m)
        y, mo, dd = int(m[:4]), int(m[5:7]), int(m[8:10])
        for yy in range(2019, y + 1):
            for mm in (mo, (mo + 5) % 12 + 1):
                try:
                    out["coupon"].append(_dt.date(yy, mm, dd).isoformat())
                except ValueError:
                    pass
    out["lsap"] = [d for d, _ in S.clean(data.get("D3:lsap_sales", []))]
    out["settlement"] = [t.get("settlement") for t in (data.get("_upcoming_tenders") or []) if t.get("settlement")] + [t["settlement_date"] for t in (data.get("_tender_rows") or []) if t.get("settlement_date")]
    tx = cfg.get("calendar", {}).get("tax_dates", {}).get("provisional_tax_standard", [])
    for yy in range(2019, int(upto[:4]) + 2):
        for md in tx:
            out["tax"].append("%d-%s" % (yy, md))
    return {k: sorted(set(x for x in v if x)) for k, v in out.items()}


# ═══════════════════════ 1 · CENTRAL BANK ═══════════════════════
def build_central_bank(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["central_bank"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    sc = S.clean(data.get("D12:settlement_cash", []))
    # monthly LSAP sales from the per-settlement series
    ls = S.clean(data.get("D3:lsap_sales", []))
    mon: Dict[str, float] = {}
    last_d: Dict[str, str] = {}
    for d, v in ls:
        mon[d[:7]] = mon.get(d[:7], 0.0) + v
        last_d[d[:7]] = max(last_d.get(d[:7], ""), d)
    data = dict(data)
    data["D3:lsap_sales_month"] = S.clean([(last_d[k], round(v, 1)) for k, v in mon.items()])
    E, raw = _entries(cfg, "central_bank", data, MAP_CB, unit, pl, {}, zero_if_empty=ZERO_IF_EMPTY_CB, anchor=sc)
    E["omo_spread_to_ocr_bps"]["unit"] = "bps"
    for k in ("omo_allocated_weekly", "omo_spread_to_ocr_bps", "lsap_sales_month", "bond_repurchases"):
        if raw[k]:
            E[k]["status"] = "fresh" if k != "lsap_sales_month" else E[k]["status"]
    D: Dict[str, dict] = {}
    # ── reserves: dead-man switch (N1) ──
    spec_r = _spec(th, "reserves") or {}
    E["settlement_cash_daily"] = entry("settlement_cash_daily", sc, E["settlement_cash_daily"]["label"], "daily", unit, cfg, E["settlement_cash_daily"]["source_id"], "WRESBAL (daily)",
                                       spec=dict(spec_r, method="absolute_primary"), prev_level=pl.get("settlement_cash_daily"), z_window=30)
    E["settlement_cash_daily"]["above_range"] = bool(sc) and sc[-1][1] >= spec_r.get("primary_absolute", {}).get("ample_above", 20000)
    E["settlement_cash_daily"]["in_range"] = bool(sc) and not E["settlement_cash_daily"]["above_range"] and sc[-1][1] >= spec_r.get("primary_absolute", {}).get("watch_below", 15000)
    E["settlement_cash_daily"]["note"] = "N1: dead-man switch only (RBNZ publishes no sufficient level; pre-COVID 6–8 bn) — never a regime trigger"
    dod = S.diff_series(sc, 1)
    D["settlement_cash_dod"] = entry("settlement_cash_dod", dod, "Settlement cash Δ day/day (reserve impulse)", "daily", unit, cfg, z_window=250)
    if dod:
        z = D["settlement_cash_dod"].get("zscore") or 0
        D["settlement_cash_dod"]["level"] = "STRESS" if abs(z) >= 3 else "WATCH" if abs(z) >= 2 else "SAFE"
        D["settlement_cash_dod"]["thresholds"] = {"method": "zscore", "levels": {"WATCH": 2.0, "STRESS": 3.0}, "window": "250d"}
    wow = S.diff_series(sc, 5)
    D["settlement_cash_wow"] = entry("settlement_cash_wow", wow, "Settlement cash Δ 5 sessions (V3.1 weekly change)", "daily", unit, cfg, z_window=60)
    _apply(D["settlement_cash_wow"], _two_sided("settlement_cash_wow", wow, _spec(th, "settlement_cash_wow") or {}, "daily", pl.get("settlement_cash_wow")))
    d20 = S.diff_series(sc, 20)
    D["settlement_cash_20d_change"] = entry("settlement_cash_20d_change", d20, "Settlement cash Δ 20 sessions", "daily", unit, cfg, z_window=60)
    # ── OMO ──
    omo_out = raw["omo_outstanding"]
    alloc = raw["omo_allocated_weekly"]
    share = S.merge_series(omo_out, sc, lambda a, c: round(a / c, 4) if c else None)
    share = S.clean([(d, v) for d, v in share if v is not None])
    D["omo_reliance_share"] = entry("omo_reliance_share", share, "OMO stock / settlement cash (reserves supplied by the RBNZ)", "daily", "ratio", cfg, spec=_spec(th, "omo_reliance_share"), prev_level=pl.get("omo_reliance_share"), z_window=60)
    sp_share = _spec(th, "omo_reliance_share") or {}
    if share and sp_share.get("secondary_absolute"):
        _cap_watch(D["omo_reliance_share"], sp_share["secondary_absolute"])
    D["omo_reliance_share"]["note"] = "N2: rises mechanically as the denominator shrinks — read with omo_outstanding and omo_takeup_wow"
    D["omo_outstanding_level"] = entry("omo_outstanding_level", omo_out, "OMO stock outstanding (absolute, N2)", "daily", unit, cfg, spec=_spec(th, "omo_outstanding"), prev_level=pl.get("omo_outstanding_level"), z_window=60)
    sp_o = _spec(th, "omo_outstanding") or {}
    if omo_out and sp_o.get("secondary_absolute"):
        _cap_watch(D["omo_outstanding_level"], sp_o["secondary_absolute"])
    D["omo_outstanding_4w_change"] = entry("omo_outstanding_4w_change", S.diff_series(omo_out, 20), "OMO stock Δ 20 sessions", "daily", unit, cfg, z_window=60)
    tk = S.diff_series(alloc, 1)
    D["omo_takeup_wow"] = entry("omo_takeup_wow", tk, "Weekly OMO take-up Δ vs previous operation (full allotment → demand)", "weekly", unit, cfg, spec=_spec(th, "omo_takeup_wow"), prev_level=pl.get("omo_takeup_wow"), z_window=12)
    sp_t = _spec(th, "omo_takeup_wow") or {}
    if tk and sp_t.get("secondary_absolute"):
        _cap_watch(D["omo_takeup_wow"], sp_t["secondary_absolute"])
    if tk:
        D["omo_takeup_wow"]["status"] = "fresh"
    # ── residual flow (N4) ──
    fxs, orrf = raw["fx_swaps_daily"], raw["orrf_usage_daily"]
    d_omo = S.diff_series(omo_out, 1)
    d_fx = S.diff_series(fxs, 1)
    d_or = S.diff_series(orrf, 1)
    res = dod
    for comp in (d_omo, d_fx, d_or):
        res = S.merge_series(res, comp, lambda a, c: round(a - c, 1))
    res = S.clean(res)
    today = sc[-1][0] if sc else "2026-01-01"
    ev = _event_days(cfg, data, today)
    tagged = set(ev["coupon"]) | set(ev["maturity"]) | set(ev["lsap"]) | set(ev["settlement"])
    D["residual_flow_daily"] = entry("residual_flow_daily", res, "Residual flow = Δ settlement cash − Δ OMO − Δ FX swaps − Δ ORRF (coincident, noisy)", "daily", unit, cfg, z_window=250)
    D["residual_flow_daily"]["note"] = b["derived"]["residual_flow_daily"]["note"]
    D["residual_flow_daily"]["tagged_day"] = [k for k in ("coupon", "maturity", "lsap", "settlement", "tax") if res and res[-1][0] in set(ev[k])]
    D["residual_flow_5d_cum"] = entry("residual_flow_5d_cum", S.rolling_sum(res, 5), "Residual flow — 5-session cumulative", "daily", unit, cfg, z_window=60)
    _apply(D["residual_flow_5d_cum"], _two_sided("residual_flow_5d_cum", S.rolling_sum(res, 5), dict(_spec(th, "residual_flow_5d_cum") or {}, watch_above=(_spec(th, "residual_flow_5d_cum") or {}).get("injection_above", "p80"), watch_below=(_spec(th, "residual_flow_5d_cum") or {}).get("drain_below", "p20")), "daily", None))
    D["residual_flow_20d_cum"] = entry("residual_flow_20d_cum", S.rolling_sum(res, 20), "Residual flow — 20-session cumulative", "daily", unit, cfg, z_window=60)
    # reconciliation band vs D10 (last full month)
    gci, rbt, fxm = raw["d10_govt_cash_influence"], raw["d10_rbnz_transactions"], raw["d10_fx"]
    band = None
    band_note = "no D10 month to reconcile yet"
    if gci and res:
        m = gci[-1][0][:7]
        rsum = sum(v for d, v in res if d[:7] == m)
        n = sum(1 for d, _ in res if d[:7] == m)
        target = gci[-1][1] + (dict(rbt).get(gci[-1][0]) or 0) + (dict(fxm).get(gci[-1][0]) or 0)
        if n >= 10:
            band = round(abs(rsum - target) / n, 1)
            band_note = "%s: residual sum %.0f vs D10 govt cash + RBNZ transactions + FX %.0f over %d sessions → ± %.0f m/day" % (m, rsum, target, n, band)
    D["residual_flow_band"] = {"label": "Residual flow reconciliation band (± NZ$m per day)", "value": band, "status": "fresh" if band is not None else "unavailable", "date": gci[-1][0] if gci else None, "note": band_note}
    big = bool(res) and (abs(res[-1][1]) >= 2000 or abs(D["residual_flow_daily"].get("zscore") or 0) >= 2) and not (res[-1][0] in tagged)
    D["fiscal_big_day"] = {"label": "FISCAL_BIG_DAY", "value": big, "status": "fresh" if res else "unavailable", "date": res[-1][0] if res else None,
                           "direction": ("INJECTION" if res and res[-1][1] > 0 else "DRAIN") if big else None, "excluded_tags": D["residual_flow_daily"]["tagged_day"]}
    exomo = S.merge_series(sc, omo_out, lambda a, c: round(a - c, 1))
    D["settlement_cash_ex_omo"] = entry("settlement_cash_ex_omo", exomo, "Settlement cash − OMO stock ('organic' reserves)", "daily", unit, cfg, z_window=60)
    # ── standing facilities ──
    D["orrf_used"] = entry("orrf_used", orrf, "ORRF usage (NZ$m) — ceiling facility", "daily", unit, cfg, spec=_spec(th, "orrf_usage_daily"), z_window=250)
    D["orrf_used"]["note"] = "small routine use (1–20 m) is normal; ≥ 100 m WATCH, ≥ 500 m STRESS (verified: 1,000 m on 2025-04-08, 550 on 2025-04-22, 189 on 2026-07-21)"
    D["fx_swap_active"] = entry("fx_swap_active", fxs, "RBNZ FX swaps outstanding (liquidity tool)", "daily", unit, cfg, z_window=250)
    fx_spec = {"method": "percentile", "window": "750d", "direction": "high_is_risk", "watch_above": "p90", "stress_above": "p97", "min_n": 120}
    if fxs:
        _apply(D["fx_swap_active"], classify(fxs[-1][1], fxs, fx_spec, "daily", pl.get("fx_swap_active")))
    lsap = raw["lsap_holdings"]
    D["lsap_runoff_12m"] = entry("lsap_runoff_12m", S.diff_series(lsap, 12), "LSAP holdings Δ 12 months (maturities + sales to NZDM)", "monthly", unit, cfg, z_window=12)
    # reconciliation D12 month-end vs R3
    r3 = raw["settlement_balances_monthly"]
    rec = []
    for d, v in r3:
        m = d[:7]
        x = [vv for dd, vv in sc if dd[:7] == m]
        if x:
            rec.append((d, round((x[-1] - v) / v * 100, 2) if v else None))
    rec = S.clean([(d, v) for d, v in rec if v is not None])
    D["reconciliation_settlement_cash"] = entry("reconciliation_settlement_cash", rec, "D12 month-end vs R3 settlement institutions' balances (%)", "monthly", "%", cfg, z_window=12)
    if rec:
        D["reconciliation_settlement_cash"]["level"] = "SAFE" if abs(rec[-1][1]) <= 2 else "WATCH"
    # phase (N2)
    o4 = D["omo_outstanding_4w_change"]["value"]
    o4p = D["omo_outstanding_4w_change"]["sparkline"]
    rising = o4 is not None and o4 > 0 and len(o4p) >= 20 and (o4p[-20] or 0) > 0
    shr = share[-1][1] if share else None
    lr = D["lsap_runoff_12m"]["value"]
    phase = "OMO_SUPPLIED" if (rising and shr is not None and shr >= 0.25) else "LSAP_UNWIND" if (lr is not None and lr < 0) else "STEADY"
    D["balance_sheet_phase"] = {"label": "Balance-sheet phase", "value": None, "phase": phase, "status": "fresh" if (sc and lsap) else "unavailable", "date": sc[-1][0] if sc else None, "note": b["derived"]["balance_sheet_phase"]["formula"]}
    # ── score ──
    lvl_r = E["settlement_cash_daily"]["level"]
    lvl_s = D["omo_reliance_share"]["level"]
    lvl_o = D["orrf_used"]["level"]
    C = Comps(cfg, "sum", -1.5, 1.5)
    if sc:
        C.flow("settlement_cash_wow", 0.5 if D["settlement_cash_wow"]["level"] == "SAFE" and (wow[-1][1] if wow else 0) > 0 else (-0.5 if D["settlement_cash_wow"].get("side") == "low" else 0.0))
        C.flow("settlement_cash_20d", 0.5 if D["settlement_cash_20d_change"]["value"] and D["settlement_cash_20d_change"]["value"] > 0 else -0.25)
        C.level("settlement_cash_level", -{"SAFE": 0, "WATCH": 0.5, "STRESS": 1.0, "CRISIS": 1.5}.get(lvl_r, 0))
        C.level("omo_reliance_level", -{"SAFE": 0, "WATCH": 0.25, "STRESS": 0.5}.get(lvl_s, 0))
        C.event("orrf_used", -{"SAFE": 0, "WATCH": 0.5, "STRESS": 1.0}.get(lvl_o, 0))
    score = C.score()
    label = "NO DATA" if not sc else "INJECTION" if score >= 0.75 else "DRAIN" if score <= -0.75 else "NEUTRAL"
    flags = []
    if orrf and orrf[-1][1] >= 100:
        flags.append("STANDING_FACILITY_USED")
    if D["fx_swap_active"]["level"] in ("WATCH", "STRESS"):
        flags.append("FX_SWAP_ACTIVE")
    if D["omo_takeup_wow"]["level"] in ("WATCH", "STRESS", "CRISIS"):
        flags.append("OMO_TAKEUP_SURGE")
    if rising and D["omo_reliance_share"]["level"] != "SAFE":
        flags.append("OMO_RELIANCE_RISING")
    if big:
        flags.append("FISCAL_BIG_DAY")
    for tag, fl in (("coupon", "COUPON_PAYMENT_DAY"), ("maturity", "BOND_MATURITY_DAY"), ("lsap", "LSAP_SALE_DAY"), ("tax", "TAX_DAY")):
        if sc and sc[-1][0] in set(ev[tag]):
            flags.append(fl)
    alerts = [_alert("settlement_cash_daily", E["settlement_cash_daily"], "dead-man switch: %.1f bn today (ample > 20, WATCH < 15, STRESS < 10, CRISIS < 7 — desk proposal)" % (sc[-1][1] / 1000 if sc else 0)),
              _alert("settlement_cash_wow", D["settlement_cash_wow"], "5-session change (two-sided p90/p10)"),
              _alert("omo_reliance_share", D["omo_reliance_share"], "OMO stock / settlement cash (30% WATCH / 45% STRESS desk proposal)"),
              _alert("omo_outstanding_level", D["omo_outstanding_level"], "absolute OMO stock (8 bn WATCH / 12 bn STRESS desk proposal)"),
              _alert("omo_takeup_wow", D["omo_takeup_wow"], "full allotment → take-up is demand"),
              _alert("orrf_used", D["orrf_used"], "ceiling facility at OCR + 50: ≥ 100 m WATCH, ≥ 500 m STRESS"),
              _alert("fx_swap_active", D["fx_swap_active"], "RBNZ FX swaps as a liquidity tool")]
    tl = "GREEN" if score >= 0.75 else "RED" if score <= -0.75 else "YELLOW"
    signals = {"traffic_light": tl if sc else "NONE", "score": score, "label": label, "flags": flags, "components": C.to_dict(),
               "detail": "settlement cash %s (5d %s, 20d %s, %s) · OMO stock %s (%s%%) · ORRF %s · phase %s" % (
                   sc[-1][1] if sc else None, wow[-1][1] if wow else None, d20[-1][1] if d20 else None, lvl_r, omo_out[-1][1] if omo_out else None,
                   round(shr * 100, 1) if shr is not None else None, orrf[-1][1] if orrf else None, phase), "alerts": alerts}
    hd = [d for d, _ in S.tail(sc, 120)]
    rows = {k: [dict(s).get(d) for d in hd] for k, s in (("settlement_cash_daily", sc), ("settlement_cash_dod", dod), ("omo_outstanding", omo_out), ("omo_reliance_share", share),
                                                        ("residual_flow_daily", res), ("orrf_usage_daily", orrf), ("fx_swaps_daily", fxs), ("settlement_cash_ex_omo", exomo))}
    md = [d for d, _ in S.tail(raw["total_assets"], 36)]
    monthly = {"dates": md, "rows": {k: [dict(raw[k]).get(d) for d in md] for k in ("total_assets", "lsap_holdings", "reverse_repos_monthly", "fx_investments", "deposits_total", "currency_in_circulation", "monetary_base", "settlement_balances_monthly", "d10_govt_cash_influence", "d10_net_reverse_repos", "d10_net_fx_swaps")}}
    history = {"dates": hd, "rows": rows, "monthly": monthly, "omo_operations": [{"date": d, "allocated": v, "spread_bps": dict(raw["omo_spread_to_ocr_bps"]).get(d)} for d, v in S.tail(alloc, 26)],
               "event_days": {k: [x for x in v if x >= (hd[0] if hd else "2026-01-01")][:60] for k, v in ev.items()},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": label, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "central_bank", cfg, b, E, D, signals, history)


# ═══════════════════════ 2 · FISCAL — Crown / NZDM ═══════════════════════
def build_fiscal(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None, cb_block: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["fiscal"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    data = dict(data)
    up = data.get("_upcoming_tenders") or []
    sched: Dict[str, float] = {}
    for t in up:
        if t.get("kind") == "bond" and t.get("volume") and t.get("tender"):
            sched[t["tender"][:7]] = sched.get(t["tender"][:7], 0.0) + t["volume"]
    data["NZDM:schedule_month"] = S.clean([(k + "-01", v) for k, v in sched.items()])
    E, raw = _entries(cfg, "fiscal", data, MAP_FI, unit, pl, {})
    for k in ("tbill_tender_btc", "tbill_tender_yield", "tbill_tender_volume", "tbill_allocation_ratio", "tbill_1y_yield", "bond_tender_coverage", "bond_tender_tail_bp", "bond_tender_volume", "tender_schedule_month"):
        E[k]["frequency"] = "event"
        E[k]["status"] = "fresh" if raw[k] else E[k]["status"]
    for k in ("tbill_tender_btc", "bond_tender_coverage", "tbill_allocation_ratio"):
        E[k]["unit"] = "x" if k != "tbill_allocation_ratio" else "ratio"
    for k in ("tbill_tender_yield", "tbill_1y_yield"):
        E[k]["unit"] = "%"
    E["bond_tender_tail_bp"]["unit"] = "bps"
    D: Dict[str, dict] = {}
    csa = raw["crown_settlement_account"]
    mom = S.diff_series(csa, 1)
    D["csa_mom"] = entry("csa_mom", mom, "Crown settlement account Δ m/m (− = spent into settlement cash)", "monthly", unit, cfg, z_window=12)
    _apply(D["csa_mom"], _two_sided("csa_mom", mom, dict(_spec(th, "csa_mom") or {}, watch_above=(_spec(th, "csa_mom") or {}).get("drain_above", "p80"), watch_below=(_spec(th, "csa_mom") or {}).get("injection_below", "p20")), "monthly", pl.get("csa_mom")))
    gci = raw["govt_cash_influence_month"]
    D["govt_cash_influence"] = entry("govt_cash_influence", gci, "Government cash influence on settlement cash (D10, + = injection)", "monthly", unit, cfg, z_window=12)
    _apply(D["govt_cash_influence"], _two_sided("govt_cash_influence", gci, dict(_spec(th, "govt_cash_influence_month") or {}, watch_above=(_spec(th, "govt_cash_influence_month") or {}).get("injection_above", "p80"), watch_below=(_spec(th, "govt_cash_influence_month") or {}).get("drain_below", "p20")), "monthly", pl.get("govt_cash_influence")))
    ni = S.merge_series(S.add_series(raw["bonds_issued_month"], raw["tbills_issued_month"]), S.add_series(raw["bond_maturities_month"], raw["tbills_matured_month"]), lambda a, c: round(-(a) - c, 1))
    D["net_issuance_month"] = entry("net_issuance_month", ni, "Net drain from Crown debt transactions (D10: −issued − matured)", "monthly", unit, cfg, z_window=12)
    # coupons in month from on-issue file → tender load ratio
    lines = data.get("_bonds_on_issue") or []
    coup: Dict[str, float] = {}
    for x in lines:
        m = x["maturity"]
        mo, dd = int(m[5:7]), int(m[8:10])
        for yy in range(2024, 2028):
            for mm in (mo, (mo + 5) % 12 + 1):
                coup["%d-%02d" % (yy, mm)] = coup.get("%d-%02d" % (yy, mm), 0.0) + x["total"] * x["coupon"] / 2
    gross = S.merge_series(raw["bonds_issued_month"], raw["tbills_issued_month"], lambda a, c: -(a + c))
    offs = S.merge_series(S.add_series(raw["bond_maturities_month"], raw["tbills_matured_month"]), S.clean([(d, coup.get(d[:7], 0.0)) for d, _ in gross]), lambda a, c: a + c)
    tlr = S.merge_series(gross, offs, lambda a, c: round(a / c, 2) if c else None)
    tlr = S.clean([(d, v) for d, v in tlr if v is not None])
    D["tender_load_ratio"] = entry("tender_load_ratio", tlr, "Gross issuance / (maturities + coupons) — V3.1 tender load (display)", "monthly", "x", cfg, z_window=12)
    D["tender_load_ratio"]["display_only"] = True
    ocr = S.clean(data.get("B2:INM.DP1.N", []))
    ty = raw["tbill_tender_yield"]
    tyo = S.merge_series(ty, _ffill(ocr, ty), lambda a, c: round((a - c) * 100, 1))
    D["tbill_yield_minus_ocr_bps"] = entry("tbill_yield_minus_ocr_bps", tyo, "T-bill (~3m) tender yield − OCR (bp)", "weekly", "bps", cfg, z_window=26)
    _apply(D["tbill_yield_minus_ocr_bps"], _two_sided("tbill_yield_minus_ocr_bps", tyo, dict(_spec(th, "tbill_yield_minus_ocr_bps") or {}, window="104w"), "weekly", pl.get("tbill_yield_minus_ocr_bps")))
    if tyo:
        D["tbill_yield_minus_ocr_bps"]["status"] = "fresh"
    # tender levels capped at WATCH unless persistent (N6)

    def _capped(key: str, ser: Series, spec: dict, low: bool) -> dict:
        e = entry(key, ser, E[key]["label"] if key in E else key, "weekly", E[key]["unit"] if key in E else "x", cfg, spec=dict(spec, secondary_percentile=dict(spec.get("secondary_percentile", {}), window="52w")), prev_level=pl.get(key), z_window=26)
        if ser:
            e["status"] = "fresh"
            vals = [v for _, v in ser[-3:]]
            thr_w, thr_s = spec.get("watch_below", spec.get("watch_above")), spec.get("stress_below", spec.get("stress_above"))
            hit = (lambda v, t: v < t) if low else (lambda v, t: v >= t)
            lvl = "SAFE"
            if thr_w is not None and hit(vals[-1], thr_w):
                lvl = "WATCH"
            if thr_s is not None and len(vals) == 3 and sum(1 for v in vals if hit(v, thr_s)) >= 2:
                lvl = "STRESS"
            e["level"] = lvl
            e["thresholds"] = {"method": "absolute", "levels": {"WATCH": thr_w, "STRESS": thr_s}, "note": "capped at WATCH unless 2 of the last 3 tenders (N6)"}
        return e
    D["tbill_bid_to_cover"] = _capped("tbill_tender_btc", raw["tbill_tender_btc"], _spec(th, "tbill_tender_btc") or {}, True)
    D["bond_bid_to_cover"] = _capped("bond_tender_coverage", raw["bond_tender_coverage"], _spec(th, "bond_tender_coverage") or {}, True)
    D["bond_tail_bp"] = _capped("bond_tender_tail_bp", raw["bond_tender_tail_bp"], dict(_spec(th, "bond_tender_tail_bp") or {}, watch_above=((_spec(th, "bond_tender_tail_bp") or {}).get("secondary_absolute") or {}).get("watch", 2), stress_above=((_spec(th, "bond_tender_tail_bp") or {}).get("secondary_absolute") or {}).get("stress", 4)), False)
    D["tbill_allocation"] = _capped("tbill_allocation_ratio", raw["tbill_allocation_ratio"], _spec(th, "tbill_allocation_ratio") or {}, True)
    # supply ahead (N5): settlements in next 5 business days
    hol = set(cfg.get("calendar", {}).get("nz_public_holidays_2026", []) + cfg.get("calendar", {}).get("nz_public_holidays_2027", []))
    today = (cb_block or {}).get("as_of") or (csa[-1][0] if csa else "2026-01-01")
    horizon = _bd(today, 5, hol)
    ahead = [t for t in up if t.get("settlement") and today < t["settlement"] <= horizon and t.get("volume")]
    D["issuance_ahead_5d"] = {"label": "Tender settlements in the next 5 business days (known drain)", "value": round(sum(t["volume"] for t in ahead), 1) if up else None, "unit": unit, "status": "fresh" if up else "unavailable",
                              "date": today, "items": ahead, "level": "WATCH" if sum(t["volume"] for t in ahead) >= 700 else "SAFE"}
    nr, tot = raw["nzgb_non_resident_holdings"], raw["nzgb_outstanding"]
    nrs = S.merge_series(nr, tot, lambda a, c: round(a / c, 4) if c else None)
    nrs = S.clean([(d, v) for d, v in nrs if v is not None])
    D["non_resident_share"] = entry("non_resident_share", nrs, "Non-resident share of nominal NZGBs (monthly)", "monthly", "ratio", cfg, z_window=12)
    if nrs and len(nrs) >= 4 and nrs[-1][1] < nrs[-4][1] - 0.02:
        D["non_resident_share"]["level"] = "WATCH"
    d9 = S.clean(data.get("D9:BTO.WAF", []))
    long_keys = [k for k in data if k.startswith("D9:BTO.WAF.N") and k[-4:] >= "3405"]
    lt: Dict[str, float] = {}
    for k in long_keys:
        for d, v in S.clean(data[k]):
            lt[d] = lt.get(d, 0.0) + v
    les = S.merge_series(S.clean(sorted(lt.items())), d9, lambda a, c: round(a / c, 4) if c else None)
    les = S.clean([(d, v) for d, v in les if v is not None])
    D["long_end_turnover_share"] = entry("long_end_turnover_share", les, "Turnover share of NZGB lines maturing ≥ 2034 (weekly, D9)", "weekly", "ratio", cfg, z_window=26)
    # regime
    band = ((cb_block or {}).get("derived", {}).get("residual_flow_band") or {}).get("value")
    r20 = ((cb_block or {}).get("derived", {}).get("residual_flow_20d_cum") or {})
    fr = "NEUTRAL"
    gl = D["govt_cash_influence"]
    if gl.get("level") != "SAFE" and gl.get("side"):
        fr = "INJECTION" if gl["side"] == "high" else "DRAIN"
    elif r20.get("value") is not None and band is not None and abs(r20["value"]) > 0 and band * 20 <= 0.3 * abs(r20["value"]):
        fr = "INJECTION" if r20["value"] > 0 else "DRAIN"
    score = 0.5 if fr == "INJECTION" else -0.5 if fr == "DRAIN" else 0.0
    CF = Comps(cfg, "sum", -0.5, 0.5).flow("govt_cash_influence_band", score)
    D["fiscal_regime"] = {"label": "Fiscal regime", "value": None, "regime": fr, "status": "fresh" if gci else "unavailable", "date": gci[-1][0] if gci else None, "note": b["derived"]["fiscal_regime"]["formula"]}
    D["fiscal_regime_score"] = {"label": "Fiscal regime score (capped ±0.5)", "value": score, "range": [-0.5, 0.5], "status": "fresh", "date": gci[-1][0] if gci else None}
    D["mmt_note"] = {"label": "MMT note", "value": None, "status": "fresh", "date": None, "text": b["derived"]["mmt_note"]["text"]}
    flags = []
    if D["bond_bid_to_cover"]["level"] != "SAFE" or D["tbill_bid_to_cover"]["level"] != "SAFE":
        flags.append("TENDER_WEAK")
    if D["bond_tail_bp"]["level"] != "SAFE":
        flags.append("TENDER_TAIL")
    if D["tbill_allocation"]["level"] != "SAFE":
        flags.append("TBILL_UNDERALLOCATED")
    if D["issuance_ahead_5d"]["level"] == "WATCH":
        flags.append("SUPPLY_AHEAD")
    if D["non_resident_share"]["level"] == "WATCH":
        flags.append("FOREIGN_DEMAND_FADE")
    alerts = [_alert("govt_cash_influence", D["govt_cash_influence"], "D10 monthly government cash influence (two-sided p80/p20)"),
              _alert("csa_mom", D["csa_mom"], "Crown settlement account swing (R3, monthly)"),
              _alert("tbill_bid_to_cover", D["tbill_bid_to_cover"], "< 2.0x WATCH, < 1.5x STRESS if 2 of 3 (N6)"),
              _alert("bond_bid_to_cover", D["bond_bid_to_cover"], "< 2.0x WATCH, < 1.5x STRESS if 2 of 3 (N6)"),
              _alert("bond_tail_bp", D["bond_tail_bp"], "highest accepted − wavg, worst line (2/4 bp desk proposal)"),
              _alert("tbill_allocation", D["tbill_allocation"], "allocated / offered — NZDM rejecting yields (< 0.9 WATCH)"),
              _alert("tbill_yield_minus_ocr_bps", D["tbill_yield_minus_ocr_bps"], "3m bill at the Crown's cost vs OCR (hike pricing / demand)")]
    tl = "GREEN" if fr == "INJECTION" else "RED" if fr == "DRAIN" else "YELLOW" if gci else "NONE"
    signals = {"traffic_light": tl, "score": score, "label": fr, "flags": flags, "components": CF.to_dict(),
               "detail": "CSA %s (mom %s) · D10 govt cash %s · T-bill %sx at %s%% · bond %sx tail %s bp · settlements next 5d %s · non-resident %s%%" % (
                   csa[-1][1] if csa else None, mom[-1][1] if mom else None, gci[-1][1] if gci else None, raw["tbill_tender_btc"][-1][1] if raw["tbill_tender_btc"] else None,
                   ty[-1][1] if ty else None, raw["bond_tender_coverage"][-1][1] if raw["bond_tender_coverage"] else None, raw["bond_tender_tail_bp"][-1][1] if raw["bond_tender_tail_bp"] else None,
                   D["issuance_ahead_5d"]["value"], round(nrs[-1][1] * 100, 1) if nrs else None), "alerts": alerts}
    hd = [d for d, _ in S.tail(gci, 36)]
    rows = {k: [dict(v).get(d) for d in hd] for k, v in (("crown_settlement_account", csa), ("csa_mom", mom), ("govt_cash_influence", gci), ("bonds_issued_month", raw["bonds_issued_month"]),
                                                        ("bond_maturities_month", raw["bond_maturities_month"]), ("tbills_issued_month", raw["tbills_issued_month"]), ("tbills_matured_month", raw["tbills_matured_month"]), ("net_issuance_month", ni), ("tender_load_ratio", tlr))}
    trows = data.get("_tender_rows") or []
    history = {"dates": hd, "rows": rows,
               "tenders": sorted(trows, key=lambda x: x.get("tender_date", ""))[-40:],
               "upcoming": up,
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": fr, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "fiscal", cfg, b, E, D, signals, history)


# ═══════════════════════ 3 · BANKING ═══════════════════════
def build_banking(cfg: dict, data: Dict[str, Series], rates_block: Optional[dict] = None, prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["banking"]
    unit = cfg["units"]["balance_sheet"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    E, raw = _entries(cfg, "banking", data, MAP_BK, unit, pl, {})
    E["core_funding_ratio"]["unit"] = "%"
    E["core_funding_ratio"]["display_only"] = True
    D: Dict[str, dict] = {}
    hy = S.pct_change_series(raw["housing_lending"], 12)
    D["housing_yoy_pct"] = entry("housing_yoy_pct", hy, "Housing lending y/y %", "monthly", "%", cfg, z_window=12)
    _apply(D["housing_yoy_pct"], _two_sided("housing_yoy_pct", hy, _spec(th, "housing_yoy_pct") or {}, "monthly", pl.get("housing_yoy_pct")))
    ba = S.add_series(raw["business_lending"], raw["agriculture_lending"])
    D["business_agri_yoy_pct"] = entry("business_agri_yoy_pct", S.pct_change_series(ba, 12), "Business + agriculture lending y/y % (productive credit)", "monthly", "%", cfg, z_window=12)
    bm = S.pct_change_series(raw["broad_money"], 12)
    D["broad_money_yoy_pct"] = entry("broad_money_yoy_pct", bm, "Broad money y/y %", "monthly", "%", cfg, spec=_spec(th, "broad_money_yoy_pct"), prev_level=pl.get("broad_money_yoy_pct"), z_window=12)
    D["private_credit_yoy_pct"] = entry("private_credit_yoy_pct", S.pct_change_series(raw["private_sector_credit"], 12), "Private sector credit y/y %", "monthly", "%", cfg, z_window=12)
    ci = S.diff_series(hy, 3)
    D["credit_impulse"] = entry("credit_impulse", ci, "Credit impulse (Δ3m of housing y/y, pp) — display", "monthly", "pp", cfg, z_window=12)
    D["credit_impulse"]["display_only"] = True
    D["loan_to_core_funding"] = entry("loan_to_core_funding", S.merge_series(raw["loans_and_advances"], raw["core_funding"], lambda a, c: round(a / c, 3) if c else None), "Loans and advances / core funding", "monthly", "x", cfg, z_window=12)
    cfr = raw["core_funding_ratio"]
    hr = S.clean([(d, round(v - 75, 1)) for d, v in cfr])
    D["cfr_headroom_pp"] = entry("cfr_headroom_pp", hr, "Core funding ratio − 75% minimum (pp) — display + RED gate", "monthly", "pp", cfg, spec=_spec(th, "cfr_headroom_pp"), z_window=12)
    D["cfr_headroom_pp"]["display_only"] = True

    def pct_of(ser: Series, n: int = 60) -> Optional[float]:
        return S.percentile_rank(ser[-1][1], S.window_sample(ser, n)) if ser else None
    hp, bp = pct_of(hy), pct_of(bm)
    hd_ok = not hr or hr[-1][1] >= 5
    sig = "YELLOW"
    if bm and ((bp is not None and bp <= 10) or (hr and hr[-1][1] < 2)):
        sig = "RED"
    elif bm and bm[-1][1] >= 0 and hd_ok and (hp is None or 20 <= hp <= 80):
        sig = "GREEN"
    D["transmission_signal"] = {"label": "Transmission signal", "value": None, "signal": sig, "status": "fresh" if bm else "unavailable", "date": bm[-1][0] if bm else None,
                                "note": b["derived"]["transmission_signal"]["formula"], "inputs": {"housing_yoy_pctile": hp, "broad_money_yoy_pctile": bp, "cfr_headroom_pp": hr[-1][1] if hr else None}}
    score = {"GREEN": 1.0, "YELLOW": 0.0, "RED": -1.0}[sig] if bm else 0.0
    alerts = [_alert("housing_yoy_pct", D["housing_yoy_pct"], "housing credit vs 10-year history (two-sided)"),
              _alert("broad_money_yoy_pct", D["broad_money_yoy_pct"], "broad money growth (p10 WATCH / p5 STRESS)"),
              _alert("cfr_headroom_pp", D["cfr_headroom_pp"], "structural funding buffer (gate only, N8)")]
    signals = {"traffic_light": sig if bm else "NONE", "score": score, "label": sig if bm else "NO DATA", "flags": [],
               "detail": "housing y/y %s%% · business+agri y/y %s%% · broad money y/y %s%% · CFR %s%% (+%s pp)" % (
                   hy[-1][1] if hy else None, D["business_agri_yoy_pct"]["value"], bm[-1][1] if bm else None, cfr[-1][1] if cfr else None, hr[-1][1] if hr else None), "alerts": alerts}
    hd = [d for d, _ in S.tail(raw["housing_lending"], 36)]
    history = {"dates": hd, "rows": {k: [dict(v).get(d) for d in hd] for k, v in (("housing_lending", raw["housing_lending"]), ("business_lending", raw["business_lending"]), ("broad_money", raw["broad_money"]),
                                                                                  ("housing_yoy_pct", hy), ("broad_money_yoy_pct", bm), ("core_funding_ratio", cfr))},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": sig, "score": score}] if hd else []))[-120:]}
    return _base(cfg["currency"], "banking", cfg, b, E, D, signals, history)


# ═══════════════════════ 4 · RATES ═══════════════════════
def build_rates(cfg: dict, data: Dict[str, Series], prev: Optional[dict] = None) -> dict:
    b = cfg["blocks"]["rates"]
    pl = _prev_levels(prev)
    th = b["thresholds"]
    E, raw = _entries(cfg, "rates", data, MAP_RT, "%", pl, {})
    E["swap_2_10_spread_bps"]["unit"] = "bps"
    E["nzgb_turnover_weekly"]["unit"] = cfg["units"]["balance_sheet"]
    oi = raw["overnight_interbank"]
    if oi:
        E["overnight_interbank"]["status"] = "fresh" if E["overnight_interbank"]["status"] != "unavailable" else "unavailable"
        E["overnight_interbank"]["equivalence_note"] = "published only on days with trades (sparse) — last %s" % oi[-1][0]
    ocr, b30, b90, s1 = raw["ocr"], raw["bank_bill_30d"], raw["bank_bill_90d"], raw["swap_1y"]
    D: Dict[str, dict] = {}
    spr = S.merge_series(b30, ocr, lambda a, c: round((a - c) * 100, 1))
    spec = _spec(th, "bank_bill_30d_minus_ocr_bps") or {}
    absr = spec.get("secondary_absolute", {"watch": 25, "stress": 40, "crisis": 60})
    D["bank_bill_30d_minus_ocr_bps"] = entry("bank_bill_30d_minus_ocr_bps", spr, "Bank bill 30 d − OCR (bp) — STRESS SPREAD (raw, N3)", "daily", "bps", cfg, spec=spec, prev_level=pl.get("bank_bill_30d_minus_ocr_bps"), z_window=30)
    oi_spr = S.merge_series(oi, _ffill(ocr, oi), lambda a, c: round((a - c) * 100, 1)) if oi else []
    D["overnight_interbank_minus_ocr_bps"] = entry("overnight_interbank_minus_ocr_bps", oi_spr, "Overnight interbank − OCR (bp; sparse)", "daily", "bps", cfg, spec=_spec(th, "overnight_interbank_minus_ocr_bps"), z_window=30)
    if oi_spr:
        D["overnight_interbank_minus_ocr_bps"]["status"] = "fresh"
    orrf_used = S.clean(data.get("D12:overnight_reverse_repo", []))
    fc = False
    if spr:
        vals = [v for _, v in spr]
        p_lvl = _persistent_level(vals, absr, 3)
        pct_lvl = D["bank_bill_30d_minus_ocr_bps"].get("level", "SAFE")
        lvl = p_lvl if RANK[p_lvl] >= 2 else ("WATCH" if (RANK[pct_lvl] >= 1 or p_lvl == "WATCH") else "SAFE")
        # confirmation: overnight ≥ OCR + 10 on a published day inside the last 3 sessions, or ORRF ≥ 100 m
        win = [d for d, _ in spr[-3:]]
        oi_hit = any(v >= 10 for d, v in oi_spr if d in win)
        orrf_hit = any(v >= 100 for d, v in orrf_used if d in win)
        fc = len(vals) >= 3 and all(v >= absr["watch"] for v in vals[-3:]) and (oi_hit or orrf_hit)
        D["bank_bill_30d_minus_ocr_bps"].update({"level": lvl, "percentile_level": pct_lvl, "absolute_level": p_lvl, "friction_confirmed": fc,
                                                 "thresholds": {"method": "absolute", "levels": {"WATCH": absr["watch"], "STRESS": absr["stress"], "CRISIS": absr["crisis"]},
                                                                "percentile_levels": (D["bank_bill_30d_minus_ocr_bps"].get("thresholds") or {}).get("levels"), "window": spec.get("window"),
                                                                "note": "raw spread; hike pricing shown beside it, never subtracted (N3)"}})
    D["friction_confirmed"] = {"label": "friction_confirmed (bills ≥ WATCH 3 sessions AND overnight ≥ OCR+10 or ORRF ≥ 100 m)", "value": fc, "status": "fresh" if spr else "unavailable", "date": spr[-1][0] if spr else None}
    fl = bool(oi_spr) and len(oi_spr) >= 3 and all(v <= -5 for _, v in oi_spr[-3:])
    D["floor_leak"] = {"label": "floor_leak (overnight ≤ OCR − 5 for 3 published sessions)", "value": fl, "status": "fresh" if oi_spr else "unavailable", "date": oi_spr[-1][0] if oi_spr else None}
    odr, orr = raw["odr"], raw["orrf_rate"]
    bp = S.merge_series(S.merge_series(oi, _ffill(odr, oi), lambda a, c: a - c), _ffill(S.merge_series(orr, odr, lambda a, c: a - c), oi), lambda a, c: round(a / c, 2) if c else None) if oi else []
    D["band_position"] = entry("band_position", S.clean([(d, v) for d, v in bp if v is not None]), "Position in the corridor (0 = ODR floor · 1 = ORRF ceiling; sparse)", "daily", "ratio", cfg, z_window=30)
    if D["band_position"]["value"] is not None:
        D["band_position"]["status"] = "fresh"
        D["band_position"]["level"] = "WATCH" if D["band_position"]["value"] >= 0.5 else "SAFE"
    b90s = S.merge_series(b90, ocr, lambda a, c: round((a - c) * 100, 1))
    D["bank_bill_90d_minus_ocr_bps"] = entry("bank_bill_90d_minus_ocr_bps", b90s, "Bank bill 90 d (BKBM) − OCR (bp)", "daily", "bps", cfg, z_window=30)
    _apply(D["bank_bill_90d_minus_ocr_bps"], _two_sided("bank_bill_90d_minus_ocr_bps", b90s, _spec(th, "bank_bill_90d_minus_ocr_bps") or {}, "daily", pl.get("bank_bill_90d_minus_ocr_bps")))
    hp = S.merge_series(s1, ocr, lambda a, c: round((a - c) * 100, 1))
    D["hike_pricing_bps"] = entry("hike_pricing_bps", hp, "Swap 1y − OCR (bp) — CONTEXT ONLY (N3)", "daily", "bps", cfg, z_window=30)
    _apply(D["hike_pricing_bps"], _two_sided("hike_pricing_bps", hp, _spec(th, "hike_pricing_bps") or {}, "daily", pl.get("hike_pricing_bps")))
    D["hike_pricing_bps"]["display_only"] = True
    slope = S.merge_series(b90, b30, lambda a, c: round((a - c) * 100, 1))
    D["bill_curve_slope_bps"] = entry("bill_curve_slope_bps", slope, "Bank bill 90 d − 30 d (bp): near-term hike pricing inside the bill curve", "daily", "bps", cfg, z_window=30)
    hike_driver = bool(slope) and slope[-1][1] > 0 and (D["hike_pricing_bps"].get("percentile") or 0) >= 80
    D["hike_pricing_bps"]["explains_bill_spread"] = hike_driver
    y2, y10, s10 = raw["nzgb_2y"], raw["nzgb_10y"], raw["swap_10y"]
    D["nzgb_2y_minus_ocr_bps"] = entry("nzgb_2y_minus_ocr_bps", S.merge_series(y2, ocr, lambda a, c: round((a - c) * 100, 1)), "NZGB 2y − OCR (bp)", "daily", "bps", cfg, z_window=30)
    c102 = S.merge_series(y10, y2, lambda a, c: round((a - c) * 100, 1))
    D["curve_10y_2y_bps"] = entry("curve_10y_2y_bps", c102, "NZGB 10y − 2y (bp)", "daily", "bps", cfg, z_window=30)
    _apply(D["curve_10y_2y_bps"], _two_sided("curve_10y_2y_bps", c102, _spec(th, "curve_10y_2y_bps") or {}, "daily", pl.get("curve_10y_2y_bps")))
    bss = S.merge_series(y10, s10, lambda a, c: round((a - c) * 100, 1))
    D["bond_swap_spread_10y_bps"] = entry("bond_swap_spread_10y_bps", bss, "NZGB 10y − swap 10y (bp): supply / offshore-demand gauge", "daily", "bps", cfg, spec=_spec(th, "bond_swap_spread_10y_bps"), prev_level=pl.get("bond_swap_spread_10y_bps"), z_window=30)
    ch5 = S.diff_series(y10, 5, 100)
    D["nzgb_10y_5d_change_bps"] = entry("nzgb_10y_5d_change_bps", ch5, "NZGB 10y Δ 5 sessions (bp)", "daily", "bps", cfg, z_window=30)
    if ch5:
        a = abs(ch5[-1][1])
        D["nzgb_10y_5d_change_bps"]["level"] = "STRESS" if a >= 25 else "WATCH" if a >= 15 else "SAFE"
        D["nzgb_10y_5d_change_bps"]["thresholds"] = {"method": "absolute", "levels": {"WATCH": 15, "STRESS": 25}}
    tw = raw["nzgb_turnover_weekly"]
    D["turnover_wow_pct"] = entry("turnover_wow_pct", S.pct_change_series(tw, 1), "NZGB turnover w/w % (display)", "weekly", "%", cfg, z_window=26)
    D["turnover_wow_pct"]["display_only"] = True
    # score
    lvl = D["bank_bill_30d_minus_ocr_bps"].get("level", "NO DATA")
    v = spr[-1][1] if spr else None
    calm = v is not None and v <= absr["watch"] and not fc
    score = 0.75 if (calm and lvl == "SAFE") else 0.25 if (lvl == "WATCH" and hike_driver) else 0.0 if lvl in ("SAFE", "WATCH") else -0.75 if lvl == "STRESS" else -1.5 if lvl == "CRISIS" else 0.0
    if fl:
        score -= 0.25
    if D["bond_swap_spread_10y_bps"].get("level") in ("WATCH", "STRESS"):
        score -= 0.25
    score = round(max(-1.5, min(1.5, score)), 2)
    label = "NO DATA" if v is None else "CORRIDOR CALM" if score >= 0.75 else "FLOOR FRICTION" if fc else "FUNDING STRESS" if lvl in ("STRESS", "CRISIS") else "HIKE PRICING" if (lvl == "WATCH" and hike_driver) else "WATCH" if lvl == "WATCH" else "CORRIDOR CALM"
    flags = []
    if fl:
        flags.append("FLOOR_LEAK")
    alerts = [_alert("bank_bill_30d_minus_ocr_bps", D["bank_bill_30d_minus_ocr_bps"], "raw spread: +25 WATCH / +40 STRESS / +60 CRISIS (desk proposal); confirmation by overnight or ORRF"),
              _alert("overnight_interbank_minus_ocr_bps", D["overnight_interbank_minus_ocr_bps"], "floor test on published days (+10 WATCH, +25 STRESS, ≤ −5 leak)"),
              _alert("bank_bill_90d_minus_ocr_bps", D["bank_bill_90d_minus_ocr_bps"], "BKBM − OCR (V3.1): term premium + hike pricing"),
              _alert("hike_pricing_bps", D["hike_pricing_bps"], "swap 1y − OCR: context, never subtracted (N3)"),
              _alert("curve_10y_2y_bps", D["curve_10y_2y_bps"], "NZGB curve slope"),
              _alert("bond_swap_spread_10y_bps", D["bond_swap_spread_10y_bps"], "supply indigestion / offshore demand (p90 WATCH, p97 STRESS)"),
              _alert("nzgb_10y_5d_change_bps", D["nzgb_10y_5d_change_bps"], "±15 bp WATCH, ±25 bp STRESS in 5 sessions")]
    tl = "GREEN" if score >= 0.75 else "YELLOW" if score >= 0 else "RED"
    signals = {"traffic_light": tl if v is not None else "NONE", "score": score, "label": label, "flags": flags,
               "detail": "bill 30d − OCR %s bp (%s) · overnight − OCR %s (%s) · hike pricing %s bp · 2y − OCR %s · 10y − 2y %s · bond-swap 10y %s · turnover %s" % (
                   v, lvl, oi_spr[-1][1] if oi_spr else None, oi_spr[-1][0] if oi_spr else "n/a", hp[-1][1] if hp else None, D["nzgb_2y_minus_ocr_bps"]["value"], c102[-1][1] if c102 else None, bss[-1][1] if bss else None, tw[-1][1] if tw else None), "alerts": alerts}
    hd = [d for d, _ in S.tail(b30, 120)]
    history = {"dates": hd, "rows": {k: [dict(s).get(d) for d in hd] for k, s in (("ocr", ocr), ("bank_bill_30d", b30), ("bank_bill_30d_minus_ocr_bps", spr), ("overnight_interbank_minus_ocr_bps", oi_spr),
                                                                                  ("bank_bill_90d_minus_ocr_bps", b90s), ("hike_pricing_bps", hp), ("nzgb_2y", y2), ("nzgb_10y", y10), ("curve_10y_2y_bps", c102), ("bond_swap_spread_10y_bps", bss))},
               "signal_log": ((prev or {}).get("history", {}).get("signal_log", []) + ([{"date": hd[-1], "label": label, "score": score}] if hd else []))[-120:]}
    out = _base(cfg["currency"], "rates", cfg, b, E, D, signals, history)
    wired = {k: e for k, e in E.items() if e.get("source_id") and k != "overnight_interbank"}
    h = _health(wired, len(wired))
    h["series_loaded"] = sum(1 for e in E.values() if e.get("source_id") and e.get("status") != "unavailable")
    h["series_expected"] = sum(1 for e in E.values() if e.get("source_id"))
    h["sparse_by_design"] = ["overnight_interbank"]
    out["source_health"] = dict(out["source_health"], **h)
    return out
