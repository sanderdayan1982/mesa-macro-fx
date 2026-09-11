"""NZD v0.4 enrichment — Treasury flows by settlement, OMO calendar, proxy reconciliations (D10 monthly, OIA daily CSA),
added to the v0.3 blocks WITHOUT touching the live scores (shadow components in signals.components_v04)."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict
from . import series as S
from .series import Series
from .blocks import entry
from .scoring import Comps
from . import ops_nzd as O


def _cal_card(label: str, ahead: Series, unit: str, days: int = 28, n: int = 8) -> dict:
    lim = (date.today() + timedelta(days=days)).isoformat()
    sel = [(d, v) for d, v in ahead if d <= lim]
    return {"label": label, "value": round(sum(v for _, v in sel), 3) if ahead else None, "unit": unit,
            "status": "fresh" if ahead else "unavailable", "date": date.today().isoformat(), "calendar": sel[:n]}


def enrich_central_bank(block: dict, cfg: dict, omo: Dict[str, Series], recon_d10: Dict[str, Series], recon_oia: Dict[str, Series], csa_oia: Series) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    for k, label in (("omo_settled_daily", "OMO reverse repos settled (+; by operation, D3)"), ("omo_matured_daily", "OMO maturities (−; 7/28 d)"),
                     ("omo_net_daily", "OMO net flow (daily)")):
        ser = omo.get(k, [])
        D[k] = entry(k, ser, label, "daily", unit, cfg, "RBNZ:D3 per operation", status="fresh" if ser else "unavailable")
    D["omo_maturities_next_4w"] = _cal_card("OMO maturing in the next 4 weeks (scheduled drain, rolled on Thursdays)", omo.get("omo_maturities_ahead", []), unit)
    n5 = S.rolling_sum(omo.get("omo_net_daily", []), 5)
    D["omo_net_5d"] = entry("omo_net_5d", n5, "OMO net flow, 5 sessions", "daily", unit, cfg, status="fresh" if n5 else "unavailable")
    D["proxy_vs_d10_error"] = entry("proxy_vs_d10_error", recon_d10.get("error", []), "Reconciliation: Σ monthly residual flow − D10 government cash influence (NZ$m)", "monthly", unit, cfg, "derived",
                                    status="fresh" if recon_d10.get("error") else "unavailable", equivalence_note="N3 quality control; not a signal")
    D["proxy_vs_d10_error_pct"] = entry("proxy_vs_d10_error_pct", recon_d10.get("error_pct", []), "Reconciliation error as % of |D10 cash influence|", "monthly", "%", cfg, status="fresh" if recon_d10.get("error_pct") else "unavailable")
    D["csa_daily_oia"] = entry("csa_daily_oia", csa_oia, "Crown Settlement Account — DAILY balance (NZ Treasury OIA-20250819, 1997-11-10 → 2025-10-31)", "daily", unit, cfg, "treasury.govt.nz:oia-20250819-overdraft-facility-csa.xlsx",
                               status="fresh" if csa_oia else "unavailable", equivalence_note="historical release for replay and proxy validation; not updated by the Treasury", lag_days=400)
    if csa_oia:
        D["csa_daily_oia"]["status"] = "proxy"
    D["proxy_vs_csa_error"] = entry("proxy_vs_csa_error", recon_oia.get("error", []), "Validation: Σ monthly residual flow − (−ΔCSA) over the OIA overlap (2024-01 → 2025-10)", "monthly", unit, cfg, "derived",
                                    status="fresh" if recon_oia.get("error") else "unavailable")
    if recon_oia.get("error"):
        errs = [abs(v) for _, v in recon_oia["error"]]
        D["proxy_vs_csa_error"]["mean_abs_error"] = round(sum(errs) / len(errs), 1)
        D["proxy_vs_csa_error"]["months"] = len(errs)
    C = Comps(cfg, "sum")
    sc = block["series"].get("settlement_cash_daily", {}).get("value")
    if sc:
        C.flow("omo_net_5d_pct", round((D["omo_net_5d"]["value"] or 0.0) / sc * 100, 4))
        for k in ("settlement_cash_wow", "settlement_cash_20d"):
            v = (block["signals"].get("components") or {}).get("flow", {}).get(k)
            if v is not None:
                C.flow(k, v)
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: not in the live score until the v0.4 replay sets the cuts")
    return block


def enrich_fiscal(block: dict, cfg: dict, tf: Dict[str, Series], cal: Dict[str, Series], ni: Series, ecp: Series, resid_daily: Series, sc_level: float) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    for k, label, src in (("tender_settled", "Tenders settled (bills + bonds; − settlement cash)", "NZDM tenders, settlement by convention T+1 bills / T+3 bonds"),
                          ("bill_matured", "Treasury bills matured (+)", "NZDM tenders"),
                          ("bond_redeemed_market", "Bond redemptions to market holders (+; market holding of the month-end before maturity)", "NZDM bonds on issue, every month-end"),
                          ("coupons_market_paid", "Coupons to market holders (+; semi-annual, market nominal of the latest month-end ≤ coupon date)", "NZDM bonds on issue, every month-end"),
                          ("tender_coverage", "Tender coverage (bills + bonds, mean per day)", "NZDM tenders")):
        ser = (tf if k in tf else cal).get(k, [])
        D[k] = entry(k, ser, label, "daily", "ratio" if k == "tender_coverage" else unit, cfg, src, status="fresh" if ser else "unavailable")
    D["net_issuance_private_daily"] = entry("net_issuance_private_daily", ni, "Net issuance to the private sector (daily; − = drain)", "daily", unit, cfg, "derived", status="fresh" if ni else "unavailable")
    wk = S.rolling_sum(ni, 5)
    D["net_issuance_private_5d"] = entry("net_issuance_private_5d", wk, "Net issuance to the private sector, 5 sessions (− = drain)", "daily", unit, cfg, "derived", status="fresh" if wk else "unavailable",
                                         equivalence_note="v0.4: −tenders settled + bill maturities + market bond redemptions + market coupons (two-sided from the first month-end of the register on file)")
    D["tender_settlements_next_4w"] = _cal_card("Tender settlements ahead (scheduled drain)", tf.get("tender_settlements_ahead", []), unit)
    D["bill_maturities_next_4w"] = _cal_card("Bill maturities ahead (scheduled injection)", tf.get("bill_maturities_ahead", []), unit)
    D["bond_redemptions_market_next_12m"] = _cal_card("Market-held bond redemptions, next 12 months", cal.get("bond_redemptions_market_ahead", []), unit, 365, 6)
    D["coupons_market_next_4w"] = _cal_card("Market coupons, next 4 weeks", cal.get("coupons_market_ahead", []), unit)
    D["ecp_on_issue"] = entry("ecp_on_issue", ecp, "Euro-Commercial Paper on issue (month-end, NZDM)", "monthly", unit, cfg, "NZDM:ECP-onissue.xlsx", status="fresh" if ecp else "unavailable",
                              equivalence_note="Crown cash outside the RBNZ (context)")
    r5 = S.rolling_sum(resid_daily, 5)
    C = Comps(cfg, "sum")
    if sc_level:
        C.flow("net_issuance_5d_pct", round((wk[-1][1] if wk else 0.0) / sc_level * 100, 4))
        C.flow("residual_5d_pct", round((r5[-1][1] if r5 else 0.0) / sc_level * 100, 4))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: daily residual proxy + weekly net issuance; D10 band stays live until the replay")
    return block
