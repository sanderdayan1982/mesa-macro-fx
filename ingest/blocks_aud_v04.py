"""AUD v0.4 enrichment — RBA OMO by operation (dealt / matured / unwinds schedule / take-up by term / spread), AOFM issuance by settlement
(bonds, notes, indexed bonds, buybacks), Treasury Bond gross calendar (redemptions, coupons; RBA holdings included), tender health, notes yield.
Added to the v0.3 blocks WITHOUT touching the live scores (shadow components in signals.components_v04)."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Optional
from . import series as S
from .series import Series
from .blocks import entry
from .scoring import Comps


def _cal_card(label: str, ahead: Series, unit: str, days: int = 28, n: int = 8, note: Optional[str] = None) -> dict:
    lim = (date.today() + timedelta(days=days)).isoformat()
    sel = [(d, v) for d, v in ahead if d <= lim and v]
    out = {"label": label, "value": round(sum(v for _, v in sel), 3) if ahead else None, "unit": unit,
           "status": "fresh" if ahead else "unavailable", "date": date.today().isoformat(), "calendar": sel[:n]}
    if note:
        out["note"] = note
    return out


def enrich_central_bank(block: dict, cfg: dict, omo: Dict[str, Series], recon: Series, omo_cut: str) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    src = "RBA:a3-omo-repo-transaction-details.csv per operation"
    lag = max(0, (date.today() - date.fromisoformat(omo_cut)).days) if omo_cut else 0
    for k, label in (("omo_dealt_daily", "OMO repos dealt (+; same-day settlement)"), ("omo_matured_daily", "OMO repos matured (−; dealt + term)"),
                     ("omo_net_daily", "OMO net flow (daily)"), ("omo_stock_daily", "OMO reverse repos outstanding — from operations (principal)"),
                     ("omo_takeup_7d", "OMO take-up, 7-day term (per operation day)"), ("omo_takeup_28d", "OMO take-up, 28-day term (per operation day)")):
        ser = omo.get(k, [])
        D[k] = entry(k, ser, label, "daily" if "takeup" not in k else "weekly", unit, cfg, src, status="fresh" if ser else "unavailable", lag_days=lag)
    n5 = S.rolling_sum(omo.get("omo_net_daily", []), 5)
    D["omo_net_5d"] = entry("omo_net_5d", n5, "OMO net flow, 5 sessions", "daily", unit, cfg, src, status="fresh" if n5 else "unavailable")
    sp = omo.get("omo_wa_spread_bp", [])
    D["omo_wa_spread_bp"] = entry("omo_wa_spread_bp", sp, "OMO weighted-average spread to the cash rate target (bp; full allotment at +10 since 2025-04-09)", "weekly", "bps", cfg, src,
                                  status="fresh" if sp else "unavailable", equivalence_note="A3: a spread above the fixed +10 bp would mean the fixed-price full-allotment framework changed")
    D["omo_unwinds_next_4w"] = _cal_card("OMO unwinds next 4 weeks (RBA published schedule; principal + interest)", omo.get("omo_unwinds_ahead", []), unit,
                                         note="A4: scheduled drain; rolled weekly on Wednesdays")
    D["unwinds_vs_implied_pct"] = entry("unwinds_vs_implied_pct", omo.get("unwinds_vs_implied_pct", []), "Reconciliation: published unwind − (dealt + term) implied maturity, % (≈ accrued interest)", "weekly", "%", cfg, "derived",
                                        status="fresh" if omo.get("unwinds_vs_implied_pct") else "unavailable", equivalence_note="quality control: same-day settlement convention verified when this stays ≈ 0.3 %")
    D["omo_stock_vs_a3_error"] = entry("omo_stock_vs_a3_error", recon, "Reconciliation: OMO stock from operations − A3 outstanding (AORROMO, interest included)", "daily", unit, cfg, "derived",
                                       status="fresh" if recon else "unavailable")
    D["omo_data_cut"] = {"label": "Last OMO operation in the file", "value": float(lag) if omo_cut else None, "unit": "days behind today", "cut_date": omo_cut, "status": "fresh" if omo_cut else "unavailable", "date": date.today().isoformat()}
    C = Comps(cfg, "sum")
    es = block["series"].get("es_balances_daily", {}).get("value")
    if es:
        C.flow("omo_net_5d_pct", round((n5[-1][1] if n5 else 0.0) / es * 100, 4))
        tk = omo.get("omo_takeup_7d", []), omo.get("omo_takeup_28d", [])
        wk = (tk[0][-1][1] if tk[0] else 0.0) + (tk[1][-1][1] if tk[1] else 0.0)
        C.flow("omo_takeup_week_pct", round(wk / es * 100, 4))
        st = omo.get("omo_stock_daily", [])
        if st:
            C.level("omo_stock_share", round(st[-1][1] / es * 100, 4))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: not in the live score until the v0.4 replay sets the cuts")
    return block


def enrich_fiscal(block: dict, cfg: dict, iss: Dict[str, Series], cal: Dict[str, Series], es_level: Optional[float], links_note: str) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    for k, label, src in (("aofm_settled", "AOFM tenders settled (−; settlement proceeds on Date Settled: bonds + notes + indexed)", "AOFM Data Hub issuance XLSX"),
                          ("tb_settled", "Treasury Bond tenders settled (−; proceeds)", "AOFM:treasury bonds - issuance.xlsx"),
                          ("tn_settled", "Treasury Note tenders settled (−; proceeds)", "AOFM:Treasury Notes - Issuance.xlsx"),
                          ("tib_settled", "Treasury Indexed Bond tenders settled (−; proceeds)", "AOFM:Treasury Indexed Bonds - Issuance.xlsx"),
                          ("tn_matured", "Treasury Notes matured (+; nominal)", "AOFM:Treasury Notes - Issuance.xlsx"),
                          ("tib_matured", "Treasury Indexed Bonds matured (+; nominal)", "AOFM:Treasury Indexed Bonds - Issuance.xlsx"),
                          ("buybacks_settled", "Buybacks settled (+; proceeds; transfers to the RBA excluded)", "AOFM:treasury bonds / indexed bonds - buybacks.xlsx"),
                          ("tn_stock_daily", "Treasury Notes on issue — daily from tenders", "AOFM:Treasury Notes - Issuance.xlsx"),
                          ("tender_coverage", "Tender coverage (mean per tender day, all instruments)", "AOFM issuance XLSX"),
                          ("tb_tail_bp", "Treasury Bond tender tail (highest accepted − weighted average, bp)", "AOFM:treasury bonds - issuance.xlsx"),
                          ("tb_wa_yield", "Treasury Bond tender weighted-average yield (%)", "AOFM:treasury bonds - issuance.xlsx")):
        ser = iss.get(k, [])
        u = "x" if k == "tender_coverage" else "bps" if k == "tb_tail_bp" else "%" if "yield" in k else unit
        D[k] = entry(k, ser, label, "daily" if k.endswith(("_settled", "_matured", "_daily")) else "event", u, cfg, src, status="fresh" if ser else "unavailable")
    ni = iss.get("net_issuance_private_daily", [])
    days = [d for d, _ in ni]
    def _dense_pos(sers, sign):
        m: Dict[str, float] = {}
        for ser in sers:
            for d, v in ser:
                m[d] = m.get(d, 0.0) + sign * v
        return [(d, round(m.get(d, 0.0), 3)) for d in days]
    gross = _dense_pos((iss.get("aofm_settled", []),), -1.0)
    red = _dense_pos((iss.get("tn_matured", []), iss.get("tib_matured", []), iss.get("buybacks_settled", [])), 1.0)
    D["aofm_issued_gross"] = entry("aofm_issued_gross", gross, "Gross issuance settled (proceeds; bonds + notes + indexed; daily)", "daily", unit, cfg, "derived", status="fresh" if gross else "unavailable")
    D["aofm_redeemed_gross"] = entry("aofm_redeemed_gross", red, "Note / indexed maturities + buybacks (daily; Treasury Bond redemptions in the gross calendar)", "daily", unit, cfg, "derived", status="fresh" if red else "unavailable")
    D["net_issuance_private_daily"] = entry("net_issuance_private_daily", ni, "Net issuance to the private sector (daily; − = drain)", "daily", unit, cfg, "derived", status="fresh" if ni else "unavailable")
    wk = S.rolling_sum(ni, 5)
    D["net_issuance_private_5d"] = entry("net_issuance_private_5d", wk, "Net issuance to the private sector, 5 sessions (− = drain)", "daily", unit, cfg, "derived", status="fresh" if wk else "unavailable",
                                         equivalence_note="v0.4 (A1): − tenders settled (proceeds) + note / indexed maturities + buybacks; Treasury Bond redemptions and coupons in the gross calendar (RBA share not by line)")
    D["aofm_settlements_ahead"] = _cal_card("Tender settlements ahead (scheduled drain)", iss.get("aofm_settlements_ahead", []), unit)
    D["tn_maturities_next_4w"] = _cal_card("Treasury Note maturities next 4 weeks (scheduled injection)", iss.get("tn_maturities_ahead", []), unit)
    D["tb_redemptions_gross_next_12m"] = _cal_card("Treasury Bond redemptions next 12 months — GROSS (RBA holdings included)", cal.get("tb_redemptions_gross_ahead", []), unit, 365, 6,
                                                   note="A5: the RBA-held part is an OPA→RBA transfer; market-held share not published by line")
    D["tb_coupons_gross_next_4w"] = _cal_card("Treasury Bond coupons next 4 weeks — GROSS (RBA holdings included)", cal.get("tb_coupons_gross_ahead", []), unit)
    tf = cal.get("tb_face_total", [])
    D["tb_face_total"] = entry("tb_face_total", tf, "Treasury Bonds on issue — face value, all lines (month-end)", "monthly", unit, cfg, "AOFM:portfolio_aggregate_-_treasury_bonds_-_settlement.xlsx", status="fresh" if tf else "unavailable")
    D["aofm_links"] = {"label": "AOFM Data Hub link discovery", "value": None, "status": "fresh", "date": date.today().isoformat(), "note": links_note}
    C = Comps(cfg, "sum")
    if es_level:
        C.flow("net_issuance_5d_pct", round((wk[-1][1] if wk else 0.0) / es_level * 100, 4))
        cov = iss.get("tender_coverage", [])
        if cov:
            C.level("tender_coverage_latest", round(cov[-1][1], 4))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: weekly net issuance by settlement + tender health (A1/A2); the −Δ government deposits band stays live until the replay")
    return block


def enrich_rates(block: dict, cfg: dict, tn_yield: Series) -> dict:
    D = block["derived"]
    tgt = block["series"].get("cash_rate_target", {}) or block["series"].get("policy_rate", {}) or {}
    D["tn_wa_yield"] = entry("tn_wa_yield", tn_yield, "Treasury Note tender weighted-average yield (%)", "event", "%", cfg, "AOFM:Treasury Notes - Issuance.xlsx", status="fresh" if tn_yield else "unavailable")
    if tn_yield and tgt.get("value") is not None:
        d, y = tn_yield[-1]
        D["tn_yield_minus_target_bps"] = {"label": "Treasury Note tender yield − cash rate target (bp)", "value": round((y - tgt["value"]) * 100, 1), "unit": "bps", "status": "fresh", "date": d,
                                          "note": "A6: layer-4 context (money-market pricing of the Commonwealth vs the target)"}
    return block
