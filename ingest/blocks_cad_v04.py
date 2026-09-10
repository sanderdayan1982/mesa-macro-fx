"""CAD v0.4 enrichment — adds the operation-level series to the v0.3 blocks WITHOUT touching the live scores.

Every new metric is published (series_v04 / derived) and the candidate regime components are exposed as
signals.components_v04 (shadow). The live regime keeps the v0.3 calibrated components until the replay of step 5
(CAMBIOS_V04_PENDIENTES.md) sets the cuts. Rule of the house: no threshold by hand."""
from __future__ import annotations
from typing import Dict, List, Optional
from . import series as S
from .series import Series
from .blocks import entry
from .scoring import Comps
from . import ops_cad as O

CB_LABELS = {
    "settlement_actual": ("Lynx settlement balances — actual (daily, BoC indicators table)", "daily"),
    "settlement_target": ("Lynx settlement balances — target (available)", "daily"),
    "ind_term_repos": ("Term repos settled (daily, indicators table)", "daily"),
    "ind_securities_lending": ("Securities lending outstanding (daily)", "daily"),
}


def _pct_of(a: Series, level: Series) -> Series:
    lv = dict(level)
    out = []
    last = None
    for d, v in a:
        if d in lv:
            last = lv[d]
        elif last is None:
            continue
        if last:
            out.append((d, round(v / last * 100, 4)))
    return out


def _last_n_sum(s: Series, n: int) -> Optional[float]:
    t = S.tail(s, n)
    return round(sum(v for _, v in t), 3) if len(t) == n else None


def enrich_central_bank(block: dict, cfg: dict, ind: Dict[str, Series], ops: Dict[str, Series]) -> dict:
    unit = cfg["units"]["balance_sheet"]
    b = cfg["blocks"]["central_bank"]
    E, D = block["series"], block["derived"]
    reserves_w = S.clean([(d, v) for d, v in zip(block["history"]["dates"], block["history"]["rows"].get("reserves", [])) if v is not None])
    sv = block.setdefault("series_v04", {})
    for k, (label, freq) in CB_LABELS.items():
        ser = ind.get(k, [])
        sv[k] = entry(k, ser, label, freq, unit, cfg, "BoC:market-operations-indicators:%s" % k, status=None if ser else "unavailable",
                      equivalence_note="HTML table with a 6-day window; history accumulates in history/cad/market_ops_indicators.csv from 2026-09-10")
    sa = ind.get("settlement_actual", [])
    D["settlement_daily_chg"] = entry("settlement_daily_chg", S.diff_series(sa), "Δ settlement balances (daily)", "daily", unit, cfg, status="fresh" if len(sa) > 1 else "unavailable")
    D["settlement_5d_chg"] = entry("settlement_5d_chg", S.diff_series(sa, 5), "Δ settlement balances (5 sessions)", "daily", unit, cfg, status="fresh" if len(sa) > 5 else "unavailable")
    D["settlement_20d_chg"] = entry("settlement_20d_chg", S.diff_series(sa, 20), "Δ settlement balances (20 sessions)", "daily", unit, cfg, status="fresh" if len(sa) > 20 else "unavailable")
    for k, label in (("term_repo_settled", "Term repos settled (injection, by settlement date)"), ("term_repo_matured", "Term repos matured (drain, by maturity date)"),
                     ("term_repo_net_daily", "Term repo net flow (daily)"), ("term_repo_outstanding", "Term repos outstanding (from operations)"),
                     ("overnight_ops_net_daily", "OR − ORR net flow (daily)")):
        ser = ops.get(k, [])
        D[k] = entry(k, ser, label, "daily", unit, cfg, "Valet:group:%s" % ("TERM_REPO_RESULTS" if k.startswith("term") else "OR_RESULTS+ORR"), status="fresh" if ser else "unavailable")
    from datetime import date, timedelta
    d28 = (date.today() + timedelta(days=28)).isoformat()
    ah = ops.get("term_repo_maturities_ahead", [])
    D["term_repo_maturities_next_4w"] = {"label": "Term repos maturing in the next 4 weeks (scheduled drain)", "value": round(sum(v for d, v in ah if d <= d28), 3) if ah else None,
                                         "unit": unit, "status": "fresh" if ah else "unavailable", "date": date.today().isoformat(), "calendar": [(d, v) for d, v in ah if d <= d28]}
    tr5 = S.rolling_sum(ops.get("term_repo_net_daily", []), 5)
    D["term_repo_net_5d"] = entry("term_repo_net_5d", tr5, "Term repo net flow (5 sessions)", "daily", unit, cfg, status="fresh" if tr5 else "unavailable")
    # shadow components (normalised by the weekly reserves level so the replay can cut on percentiles)
    C = Comps(cfg, "mean2")
    lvl = S.last(reserves_w)
    lv = lvl[1] if lvl else None
    s5, s20, t5 = D["settlement_5d_chg"]["value"], D["settlement_20d_chg"]["value"], D["term_repo_net_5d"]["value"]
    if lv:
        C.flow("settlement_5d_pct", round((s5 or 0.0) / lv * 100, 4))
        C.flow("settlement_20d_pct", round((s20 or 0.0) / lv * 100, 4))
        C.flow("term_repo_net_5d_pct", round((t5 or 0.0) / lv * 100, 4))
        C.level("term_repo_dependence", round((dict(ops.get("term_repo_outstanding", [])).get(S.last(ops.get("term_repo_outstanding", []))[0], 0.0) if ops.get("term_repo_outstanding") else 0.0) / lv * 100, 4))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: not in the live score until the v0.4 replay sets the cuts")
    # daily history rows for the dashboard
    hd = [d for d, _ in S.tail(sa, 60)]
    block["history_daily"] = {"dates": hd, "rows": {"settlement_actual": [dict(sa).get(d) for d in hd],
                                                    "term_repo_net_daily": [dict(ops.get("term_repo_net_daily", [])).get(d) for d in hd],
                                                    "term_repo_outstanding": [dict(ops.get("term_repo_outstanding", [])).get(d) for d in hd]}}
    return block


def enrich_fiscal(block: dict, cfg: dict, iss: Dict[str, Series], rg: Dict[str, Series], reserves_w: Series) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    for k, label, src in (("issued_private", "Bills + bonds issued to the private sector (amount − BoC purchase), by issue date", "Valet:group:AUC_TBILL_RESULTS+AUC_BOND_RESULTS"),
                          ("matured_private", "Private-held bills + bonds matured, by maturity date", "Valet:group:AUC_TBILL_RESULTS+AUC_BOND_RESULTS"),
                          ("repurchased_private", "Bond switch repurchases from the private sector, by settlement", "Valet:group:AUC_BOND_S_RESULTS_REPURCHASE"),
                          ("boc_primary_purchase", "BoC primary-market purchase at auction", "Valet:group:AUC_*_RESULTS"),
                          ("net_issuance_private_daily", "Net issuance to the private sector (daily; − = drain, + = maturities/repurchases)", "derived"),
                          ("rg_am_placed", "Receiver General AM auction placed (BoC → banks)", "Valet:group:AUC_RGAM_RESULTS"),
                          ("rg_am_matured", "Receiver General AM deposits matured (banks → BoC)", "Valet:group:AUC_RGAM_RESULTS"),
                          ("rg_am_net_daily", "Receiver General AM net flow (daily)", "derived"),
                          ("rg_am_outstanding", "Receiver General AM deposits outstanding (from auctions)", "derived"),
                          ("rg_am_coverage", "Receiver General AM auction coverage", "Valet:group:AUC_RGAM_RESULTS")):
        ser = (iss if k in iss else rg).get(k, [])
        D[k] = entry(k, ser, label, "daily", "ratio" if k.endswith("coverage") else unit, cfg, src, status="fresh" if ser else "unavailable")
    # replace the v0.3 placeholder
    nd = iss.get("net_issuance_private_daily", [])
    wk = S.rolling_sum(nd, 5)
    D["net_issuance"] = entry("net_issuance", wk, "Net issuance to the private sector (5 sessions; − = drain)", "daily", unit, cfg, "derived", status="fresh" if wk else "unavailable",
                              equivalence_note="v0.4 first pass: bills + bonds − BoC purchase − private maturities + repurchases; coupons pending")
    ahead = iss.get("maturities_ahead", [])
    from datetime import date, timedelta
    d28 = (date.today() + timedelta(days=28)).isoformat()
    D["maturities_next_4w"] = {"label": "Private-held maturities in the next 4 weeks", "value": round(sum(v for d, v in ahead if d <= d28), 3) if ahead else None,
                               "unit": unit, "status": "fresh" if ahead else "unavailable", "date": date.today().isoformat(), "calendar": [(d, v) for d, v in ahead if d <= d28]}
    C = Comps(cfg, "sum")
    lvl = S.last(reserves_w)
    lv = lvl[1] if lvl else None
    rg5 = _last_n_sum(rg.get("rg_am_net_daily", []), 5)
    if lv:
        C.flow("net_issuance_5d_pct", round((D["net_issuance"]["value"] or 0.0) / lv * 100, 4))
        C.flow("rg_am_net_5d_pct", round((rg5 or 0.0) / lv * 100, 4))
        C.flow("fiscal_flow_z", block["signals"]["components"]["flow"].get("fiscal_flow_z", 0.0))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: not in the live score until the v0.4 replay sets the cuts")
    return block


def enrich_rates(block: dict, cfg: dict, valet: Dict[str, Series]) -> dict:
    E, D = block["series"], block["derived"]
    p25, p75 = S.clean(valet.get("CORRA_RATE_AT_PERCENTILE_25", [])), S.clean(valet.get("CORRA_RATE_AT_PERCENTILE_75", []))
    iqr = S.merge_series(p75, p25, lambda a, b: (a - b) * 100)
    D["corra_iqr_bps"] = entry("corra_iqr_bps", iqr, "CORRA interquartile range p75 − p25 (bps)", "daily", "bps", cfg, status="fresh" if iqr else "unavailable", z_window=30)
    return block
