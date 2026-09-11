"""EUR v0.4 enrichment — weekly net issuance to the private sector by settlement (DE + FR + ES + IT + EU auctions), bills calendar,
German gross redemption / coupon calendar, fiscal impulse v0.4 (−ΔL050100 − net issuance), MonPol w/w as a shadow flow (E4), GFS.Q to context (E1).
Added to the v0.3 blocks WITHOUT touching the live scores (shadow components in signals.components_v04)."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, List, Optional
from . import series as S
from .series import Series
from .blocks import entry
from .scoring import Comps

ISSUERS = ("DE", "FR", "ES", "IT", "EU", "ESM")
NOT_WIRED = "round 3: EU auctions + syndications from the Commission Qlik app (Date of settlement per operation); ESM bills via Bundesbank PDFs (value date); ESM/EFSF bond syndications NOT in the flow (settlement not published in the CSV) — calendar only"


def _cal_card(label: str, ahead: Series, unit: str, days: int = 28, n: int = 8, note: Optional[str] = None) -> dict:
    lim = (date.today() + timedelta(days=days)).isoformat()
    sel = [(d, v) for d, v in ahead if d <= lim and v]
    out = {"label": label, "value": round(sum(v for _, v in sel), 3) if ahead else None, "unit": unit,
           "status": "fresh" if ahead else "unavailable", "date": date.today().isoformat(), "calendar": sel[:n]}
    if note:
        out["note"] = note
    return out


def enrich_fiscal(block: dict, cfg: dict, fl: Dict[str, Series], cal: Dict[str, Series], de_ahead: Series, ni_weekly: Series, impulse: Series,
                  coverage_by_issuer: Dict[str, Series], last_by_issuer: Dict[str, str], exliq_level: Optional[float]) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    ni = fl.get("net_issuance_private_daily", [])
    D["settled_all"] = entry("settled_all", fl.get("settled_all", []), "Auctions settled — DE + FR + ES + IT + EU (−; cash where a price is published)", "daily", unit, cfg, "derived (ops_eur)",
                             status="fresh" if fl.get("settled_all") else "unavailable", equivalence_note=NOT_WIRED)
    D["bills_matured_all"] = entry("bills_matured_all", fl.get("bills_matured_all", []), "Bills matured — Bubill + BTF + Letras + BOT + EU-Bills (+; nominal)", "daily", unit, cfg, "derived (ops_eur)",
                                   status="fresh" if fl.get("bills_matured_all") else "unavailable")
    D["bond_redeemed_all"] = entry("bond_redeemed_all", fl.get("bond_redeemed_all", []), "Bond redemptions — DE + EU, GROSS (+; nominal at maturity; FR/ES/IT/ESM not covered)", "daily", unit, cfg, "derived (ops_eur)",
                                   status="fresh" if fl.get("bond_redeemed_all") else "unavailable")
    D["coupons_paid_all"] = entry("coupons_paid_all", fl.get("coupons_paid_all", []), "Coupons paid — DE + EU, GROSS (+; annual on the maturity day/month; FR/ES/IT/ESM not covered)", "daily", unit, cfg, "derived (ops_eur)",
                                  status="fresh" if fl.get("coupons_paid_all") else "unavailable")
    for iss in ISSUERS:
        ser = fl.get("settled_%s" % iss, [])
        D["settled_%s" % iss] = entry("settled_%s" % iss, ser, "%s auctions settled (−)" % iss, "daily", unit, cfg, "ops_eur:%s" % iss, status="fresh" if ser else "unavailable",
                                      equivalence_note="last record %s" % last_by_issuer.get(iss, "—"))
    days = [d for d, _ in ni]
    def _dense_pos(ser, sign):
        m: Dict[str, float] = {}
        for d, v in ser:  # several series may share a date (bills + bond redemptions + coupons)
            m[d] = m.get(d, 0.0) + sign * v
        return [(d, round(m.get(d, 0.0), 3)) for d in days]
    D["issued_gross"] = entry("issued_gross", _dense_pos(fl.get("settled_all", []), -1.0), "Gross issuance settled — all wired issuers (daily)", "daily", unit, cfg, "derived", status="fresh" if ni else "unavailable")
    D["redeemed_gross"] = entry("redeemed_gross", _dense_pos(fl.get("bills_matured_all", []) + fl.get("bond_redeemed_all", []) + fl.get("coupons_paid_all", []), 1.0),
                                "Bill maturities (all wired issuers) + bond redemptions and coupons (DE + EU, gross) — daily", "daily", unit, cfg, "derived", status="fresh" if ni else "unavailable")
    D["net_issuance_private_daily"] = entry("net_issuance_private_daily", ni, "Net issuance to the private sector (daily; − = drain)", "daily", unit, cfg, "derived", status="fresh" if ni else "unavailable")
    wk = S.rolling_sum(ni, 5)
    D["net_issuance_private_5d"] = entry("net_issuance_private_5d", wk, "Net issuance to the private sector, 5 sessions (− = drain)", "daily", unit, cfg, "derived", status="fresh" if wk else "unavailable",
                                         equivalence_note="E2: − auctions settled + bill maturities + bond redemptions + coupons (DE + EU gross; FR/ES/IT/ESM bonds one-sided — no per-line outstanding source)")
    D["net_issuance_private_weekly"] = entry("net_issuance_private_weekly", ni_weekly, "Net issuance to the private sector — weekly on the WFS grid (− = drain)", "weekly", unit, cfg, "derived",
                                             status="fresh" if ni_weekly else "unavailable", z_window=26)
    D["fiscal_impulse_v04_weekly"] = entry("fiscal_impulse_v04_weekly", impulse, "Fiscal impulse v0.4 — −Δ government deposits − net issuance ≈ spending − taxes (weekly)", "weekly", unit, cfg, "derived",
                                           status="fresh" if impulse else "unavailable", z_window=26,
                                           equivalence_note="E3: income channel; L050100 exists only since 2025-W45 → short history until the replay")
    D["settlements_ahead"] = _cal_card("Auction settlements ahead (scheduled drain; results published, not yet settled)", fl.get("settlements_ahead", []), unit)
    D["bill_maturities_next_4w"] = _cal_card("Bill maturities next 4 weeks — all wired issuers (scheduled injection)", fl.get("bill_maturities_ahead", []), unit)
    D["de_supply_next_4w"] = _cal_card("German supply next 4 weeks (issuance outlook; value date = auction + 2)", de_ahead, unit, note="planned volumes; retention unknown until the auction")
    D["de_redemptions_gross_next_12m"] = _cal_card("German redemptions next 12 months — GROSS (Eurosystem holdings included)", cal.get("de_redemptions_gross_ahead", []), unit, 365, 6)
    D["de_coupons_gross_next_4w"] = _cal_card("German coupons next 4 weeks — GROSS", cal.get("de_coupons_gross_ahead", []), unit)
    tot = cal.get("de_outstanding_total", [])
    D["de_outstanding_total"] = entry("de_outstanding_total", tot, "German Federal securities outstanding (nominal, ex strips; month-end)", "monthly", unit, cfg, "finanzagentur:einzelaufstellung_en.xlsx", status="fresh" if tot else "unavailable")
    cov = fl.get("tender_coverage", [])
    D["tender_coverage_all"] = entry("tender_coverage_all", cov, "Auction coverage — mean per auction day, all wired issuers", "event", "x", cfg, "derived", status="fresh" if cov else "unavailable")
    for iss, ser in coverage_by_issuer.items():
        D["coverage_%s" % iss] = entry("coverage_%s" % iss, ser, "%s auction coverage (mean per auction day)" % iss, "event", "x", cfg, "ops_eur:%s" % iss, status="fresh" if ser else "unavailable")
    D["gfs_context"] = {"label": "GFS.Q structural deficit (quarterly) → context in v0.4", "value": None, "status": "fresh", "date": date.today().isoformat(),
                        "note": "E1: the quarterly deficit leaves the Treasury regime in the replay; weekly net issuance + −ΔL050100 take its place"}
    C = Comps(cfg, "sum")
    if exliq_level:
        if ni_weekly:
            C.flow("net_issuance_weekly_pct", round(ni_weekly[-1][1] / exliq_level * 100, 4))
        gd = (block["signals"].get("components") or {}).get("flow", {})
        for k in ("govt_deposits_wow", "fiscal_impulse_4w"):
            if k in gd:
                C.flow(k, gd[k])
        if impulse:
            C.flow("fiscal_impulse_v04_pct", round(impulse[-1][1] / exliq_level * 100, 4))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow (E1–E3): weekly net issuance by settlement + −ΔL050100; GFS.Q out; cuts by the v0.4 replay")
    return block


def enrich_central_bank(block: dict, cfg: dict) -> dict:
    """E4: MonPol securities w/w (already computed in v0.3 as derived.monpol_wow) enters the shadow flows"""
    D = block["derived"]
    C = Comps(cfg, "sum")
    ex = block["series"].get("excess_liquidity", {}).get("value")
    if ex:
        mw = D.get("monpol_wow", {}).get("value")
        if mw is not None:
            C.flow("monpol_wow_pct", round(mw / ex * 100, 4))
        for k, v in ((block["signals"].get("components") or {}).get("flow", {})).items():
            C.flow(k, v)
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow (E4): MonPol w/w joins the v0.3 excess-liquidity flows; cuts by the v0.4 replay")
    return block


def enrich_fiscal_eu_esm(block: dict, cfg: dict, eu_cal: Dict[str, Series], esm_cal: Dict[str, Series], notes: Dict[str, str]) -> dict:
    """Round 3: EU-Bonds/Bills outstanding by ISIN (Commission Qlik) and ESM/EFSF outstanding (public CSV) → GROSS redemption / coupon
    calendars (the Eurosystem does not publish APP/PEPP holdings by ISIN). All issuers stay in the flow: their cash sits at the ECB
    (Decision (EU) 2022/1521 art. 2), so settlement drains reserves like a sovereign auction."""
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    D["eu_redemptions_gross_next_12m"] = _cal_card("EU-Bonds/Bills redemptions next 12 months — GROSS (Commission outstanding by ISIN)", eu_cal.get("eu_redemptions_gross_ahead", []), unit, 365, 6,
                                                   note="source: EU debt securities data (Qlik) · %s" % notes.get("EU_qlik", ""))
    D["eu_coupons_gross_next_4w"] = _cal_card("EU-Bonds coupons next 4 weeks — GROSS", eu_cal.get("eu_coupons_gross_ahead", []), unit)
    tot = eu_cal.get("eu_outstanding_total", [])
    D["eu_outstanding_total"] = entry("eu_outstanding_total", tot, "EU-Bonds and EU-Bills outstanding (Commission, by ISIN)", "daily", unit, cfg, "commission.europa.eu:eu-debt-securities-data (Qlik)",
                                      status="fresh" if tot else "unavailable")
    D["esm_redemptions_next_12m"] = _cal_card("ESM/EFSF redemptions next 12 months — EUR issues (outstanding list)", esm_cal.get("esm_redemptions_ahead", []), unit, 365, 6,
                                              note="ESM enters gross (loan disbursements are transfers inside the Eurosystem); USD issues excluded: %s" % ",".join(esm_cal.get("_non_eur", [])[:4]))
    D["esm_coupons_next_4w"] = _cal_card("ESM/EFSF coupons next 4 weeks — EUR bonds", esm_cal.get("esm_coupons_ahead", []), unit)
    et = esm_cal.get("esm_outstanding_total", [])
    D["esm_outstanding_total"] = entry("esm_outstanding_total", et, "ESM + EFSF EUR issues outstanding (transactions export)", "daily", unit, cfg, "esm.europa.eu:export-transactions-list", status="fresh" if et else "unavailable")
    D["esm_bills_note"] = {"label": "ESM bill auctions (Bundesbank EBS)", "value": None, "status": "fresh", "date": date.today().isoformat(),
                           "note": notes.get("ESM", "fixture: one auction (1-Sep-2026, value date 3-Sep-2026)")}
    return block
