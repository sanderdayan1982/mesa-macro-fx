"""GBP v0.4 enrichment — operation-level BoE series, DMO issuance by settlement, APF calendar and the Exchequer residual,
added to the v0.3 blocks WITHOUT touching the live scores (shadow components in signals.components_v04)."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Optional
from . import series as S
from .series import Series
from .blocks import entry
from .scoring import Comps


def _cal_card(label: str, ahead: Series, unit: str, days: int = 28, n: int = 8) -> dict:
    lim = (date.today() + timedelta(days=days)).isoformat()
    sel = [(d, v) for d, v in ahead if d <= lim]
    return {"label": label, "value": round(sum(v for _, v in sel), 3) if ahead else None, "unit": unit,
            "status": "fresh" if ahead else "unavailable", "date": date.today().isoformat(), "calendar": sel[:n]}


def enrich_central_bank(block: dict, cfg: dict, ops: Dict[str, Series], apf: Dict[str, Series], resid: Dict[str, Series]) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    reserves_w = S.clean([(d, v) for d, v in zip(block["history"]["dates"], block["history"]["rows"].get("reserves", [])) if v is not None])
    for k, label, src in (("str_net_daily", "STR net flow (+ allocated, − matured; by operation)", "BoE:short-term-repo-omos-by-operation.xlsx"),
                          ("str_outstanding_ops", "STR outstanding (from operations)", "BoE:short-term-repo-omos-by-operation.xlsx"),
                          ("iltr_net_daily", "ILTR net flow (+ allocated, − matured)", "BoE:indexed-long-term-repo-omos-by-operation.xlsx"),
                          ("iltr_outstanding_ops", "ILTR outstanding (from operations)", "BoE:indexed-long-term-repo-omos-by-operation.xlsx"),
                          ("ctrf_net_daily", "CTRF net flow", "BoE:contingent-term-repo-operations-results.xlsx"),
                          ("repo_net_daily", "STR + ILTR + CTRF net flow (daily)", "derived"),
                          ("iltr_cover", "ILTR cover (total bids / allocated)", "BoE:ILTR by operation"),
                          ("apf_sales_daily", "APF gilt sales settled (− reserves, proceeds)", "BoE:gilt-sales-time-series.xlsx")):
        ser = (ops if k in ops else apf).get(k, [])
        D[k] = entry(k, ser, label, "daily", "ratio" if k == "iltr_cover" else unit, cfg, src, status="fresh" if ser else "unavailable")
    D["repo_maturities_next_4w"] = _cal_card("STR/ILTR/CTRF maturing in the next 4 weeks (scheduled drain)", ops.get("repo_maturities_ahead", []), unit)
    D["apf_redemptions_next_12m"] = _cal_card("APF gilt redemptions in the next 12 months (HMT → BoE, no reserve effect; refinancing need)", apf.get("apf_redemptions_ahead", []), unit, 365, 6)
    a5 = S.rolling_sum(apf.get("apf_sales_daily", []), 5)
    D["apf_sales_5d"] = entry("apf_sales_5d", a5, "APF sales, 5 sessions", "daily", unit, cfg, status="fresh" if a5 else "unavailable")
    r5 = S.rolling_sum(ops.get("repo_net_daily", []), 5)
    D["repo_net_5d"] = entry("repo_net_5d", r5, "Repo net flow, 5 sessions", "daily", unit, cfg, status="fresh" if r5 else "unavailable")
    D["exchequer_residual_weekly"] = entry("exchequer_residual_weekly", resid.get("exchequer_residual_weekly", []),
                                           "Exchequer residual = ΔR − ΔSTR − ΔLTR − ΔAPF − ΔTFSME − ΔW&M + ΔNotes (weekly identity)", "weekly", unit, cfg, "derived:IADB",
                                           status="fresh" if resid.get("exchequer_residual_weekly") else "unavailable",
                                           equivalence_note="Exchequer + unobserved clients (foreign central banks, CCPs); cleaned per ADJUDICACION_METRICAS_GBP.md 4b")
    D["exchequer_residual_4w"] = entry("exchequer_residual_4w", resid.get("exchequer_residual_4w", []), "Exchequer residual, 4 weeks", "weekly", unit, cfg, status="fresh" if resid.get("exchequer_residual_4w") else "unavailable")
    C = Comps(cfg, "mean2")
    lvl = S.last(reserves_w)
    lv = lvl[1] if lvl else None
    if lv:
        C.flow("repo_net_5d_pct", round((D["repo_net_5d"]["value"] or 0.0) / lv * 100, 4))
        C.flow("apf_sales_5d_pct", round((D["apf_sales_5d"]["value"] or 0.0) / lv * 100, 4))
        so = S.last(ops.get("str_outstanding_ops", []))
        io_ = S.last(ops.get("iltr_outstanding_ops", []))
        C.level("repo_dependence_ops_pct", round(((so[1] if so else 0.0) + (io_[1] if io_ else 0.0)) / lv * 100, 4))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: not in the live score until the v0.4 replay sets the cuts")
    return block


def enrich_fiscal(block: dict, cfg: dict, iss: Dict[str, Series], cal: Dict[str, Series], resid: Dict[str, Series], reserves_w: Series) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    for k, label, src in (("gilt_issued_daily", "Gilts issued (Δ amount in issue, by settlement; D1A daily archive)", "DMO:D1A archive"),
                          ("gilt_redeemed_private", "Private-held gilt redemptions (+ reserves)", "DMO:D1A archive − APF profile"),
                          ("gilt_redeemed_apf", "APF-held gilt redemptions (HMT → BoE, no reserve effect)", "DMO:D1A archive × APF profile"),
                          ("tbill_issued", "T-bills issued (− reserves, by issue date)", "DMO:D2.2D"),
                          ("tbill_matured", "T-bills matured (+ reserves)", "DMO:D2.2D"),
                          ("tbill_cover", "T-bill tender cover", "DMO:D2.2D"),
                          ("coupons_private_paid", "Coupons paid to private holders (+ reserves)", "DMO:D1A × APF profile"),
                          ("net_issuance_private_daily", "Net issuance to the private sector (daily; − = drain)", "derived")):
        ser = iss.get(k, [])
        D[k] = entry(k, ser, label, "daily", "ratio" if k == "tbill_cover" else unit, cfg, src, status="fresh" if ser else "unavailable")
    wk = S.rolling_sum(iss.get("net_issuance_private_daily", []), 5)
    D["net_issuance"] = entry("net_issuance", wk, "Net issuance to the private sector, 5 sessions (− = drain)", "daily", unit, cfg, "derived", status="fresh" if wk else "unavailable",
                              equivalence_note="v0.4: gilts (D1A Δ amount in issue) + T-bills − private redemptions − T-bill maturities − private coupons; gilt history starts with the archive (2026-09-10)")
    D["gilt_redemptions_private_next_4w"] = _cal_card("Private-held gilt redemptions, next 4 weeks", cal.get("gilt_redemptions_private_ahead", []), unit)
    D["gilt_coupons_private_next_4w"] = _cal_card("Coupons to private holders, next 4 weeks", cal.get("gilt_coupons_private_ahead", []), unit)
    D["tbill_maturities_next_4w"] = _cal_card("T-bill maturities, next 4 weeks", iss.get("tbill_maturities_ahead", []), unit)
    D["exchequer_residual_weekly"] = entry("exchequer_residual_weekly", resid.get("exchequer_residual_weekly", []), "Exchequer residual (weekly identity on the Weekly Report)", "weekly", unit, cfg, "derived:IADB",
                                           status="fresh" if resid.get("exchequer_residual_weekly") else "unavailable")
    D["exchequer_residual_4w"] = entry("exchequer_residual_4w", resid.get("exchequer_residual_4w", []), "Exchequer residual, 4 weeks", "weekly", unit, cfg, status="fresh" if resid.get("exchequer_residual_4w") else "unavailable")
    C = Comps(cfg, "sum")
    lvl = S.last(reserves_w)
    lv = lvl[1] if lvl else None
    if lv:
        C.flow("net_issuance_5d_pct", round((D["net_issuance"]["value"] or 0.0) / lv * 100, 4))
        C.flow("exchequer_residual_4w_pct", round((D["exchequer_residual_4w"]["value"] or 0.0) / lv * 100, 4))
        C.flow("net_spending_band_x_z", (block["signals"].get("components") or {}).get("flow", {}).get("net_spending_band_x_z", 0.0))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: not in the live score until the v0.4 replay sets the cuts; CGNCR stays as the monthly anchor")
    return block
