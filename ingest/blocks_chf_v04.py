"""CHF v0.4 enrichment — SNB absorption by operation date (Bills + repos from gmges, calendar from the register), Confederation
issuance by settlement (MMDRC + bonds), redemptions and coupons from the outstanding list, improved weekly intervention proxy.
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
    sel = [(d, v) for d, v in ahead if d <= lim]
    out = {"label": label, "value": round(sum(v for _, v in sel), 3) if ahead else None, "unit": unit,
           "status": "fresh" if ahead else "unavailable", "date": date.today().isoformat(), "calendar": sel[:n]}
    if note:
        out["note"] = note
    return out


def enrich_central_bank(block: dict, cfg: dict, rf: Dict[str, Series], bf: Dict[str, Series], cal: Dict[str, Series], absorption: Series,
                        recon_es: Series, recon_vr: Series, px: Dict[str, Series], ops_cut: str) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    lag = max(0, (date.today() - date.fromisoformat(ops_cut)).days) if ops_cut else 0
    src = "SNB:gmges.xlsx per operation (monthly file; amounts up to ~5 weeks late)"
    for k, ser, label in (("bills_issued", bf.get("bills_issued", []), "SNB Bills placed (−; payment date)"),
                          ("bills_repaid", bf.get("bills_repaid", []), "SNB Bills repaid (+; repayment date)"),
                          ("bills_net_daily", bf.get("bills_net_daily", []), "SNB Bills net flow (daily)"),
                          ("repo_ct_settled", rf.get("repo_ct_settled", []), "Liquidity-absorbing repos settled (−; 'from' date)"),
                          ("repo_ct_matured", rf.get("repo_ct_matured", []), "Liquidity-absorbing repos matured (+; 'to' date)"),
                          ("repo_net_daily", rf.get("repo_net_daily", []), "Repos net flow (daily; CT − / CP +)")):
        D[k] = entry(k, ser, label, "daily", unit, cfg, src, status="fresh" if ser else "unavailable", lag_days=lag)
        if ser:
            D[k]["status"] = "fresh" if lag <= 45 else "stale"
            D[k]["equivalence_note"] = "dates from the operation; amounts published monthly (last data %s)" % ops_cut
    for k, ser, label in (("bills_stock_daily", bf.get("bills_stock_daily", []), "SNB Bills outstanding — daily stock from operations"),
                          ("repo_ct_stock_daily", rf.get("repo_ct_stock_daily", []), "Liquidity-absorbing repos outstanding — daily stock from operations"),
                          ("absorption_stock_daily", absorption, "Absorption stock (Bills + repos) — daily, from operations")):
        D[k] = entry(k, ser, label, "daily", unit, cfg, src, status="fresh" if ser else "unavailable", lag_days=lag,
                     equivalence_note="S1: daily in dates, monthly in amounts; reconciled to the balance sheet at month-end")
        if ser:
            D[k]["status"] = "fresh" if lag <= 45 else "stale"
    ops_net = S.merge_series(bf.get("bills_net_daily", []), rf.get("repo_net_daily", []), lambda a, b: round(a + b, 3)) if bf.get("bills_net_daily") and rf.get("repo_net_daily") else (bf.get("bills_net_daily") or rf.get("repo_net_daily") or [])
    n5 = S.rolling_sum(ops_net, 5)
    D["ops_net_daily"] = entry("ops_net_daily", ops_net, "SNB operations net flow (Bills + repos; daily)", "daily", unit, cfg, src, status="fresh" if ops_net else "unavailable")
    D["ops_net_5d"] = entry("ops_net_5d", n5, "SNB operations net flow, 5 sessions", "daily", unit, cfg, src, status="fresh" if n5 else "unavailable")
    ahead = rf.get("repo_maturities_ahead", [])
    lim = (date.today() + timedelta(days=28)).isoformat()
    sel = [(d, v) for d, v in ahead if d <= lim]
    D["repo_maturities_after_cut"] = {"label": "Repos maturing after the operations cut (known 'to' dates; %s → +4 weeks)" % ops_cut, "value": round(sum(v for _, v in sel), 3) if ahead else None, "unit": unit,
                                      "status": "fresh" if ahead else "unavailable", "date": date.today().isoformat(), "calendar": sel[:10],
                                      "note": "one-week repos rolled daily: the injections listed are matched by new absorptions the file has not published yet"}
    D["bills_repayments_next_4w"] = _cal_card("SNB Bills repaying in the next 4 weeks (register shape × balance-sheet stock)", cal.get("bills_repayments_ahead", []), unit,
                                              note="the register lists issued lines incl. SNB own holdings → shape only; amounts scaled to ES")
    rme = cal.get("register_minus_es", [])
    D["register_minus_es"] = entry("register_minus_es", rme, "Bills register total − balance-sheet SNB Bills (lines not placed / own holdings)", "monthly", unit, cfg, "SNB:snbbillshreg vs snbbipo{ES}",
                                   status="fresh" if rme else "unavailable", equivalence_note="context: why the register is not used for amounts")
    D["bills_stock_vs_es_error"] = entry("bills_stock_vs_es_error", recon_es, "Reconciliation: Bills stock from operations − balance-sheet ES at month-end", "monthly", unit, cfg, "derived",
                                         status="fresh" if recon_es else "unavailable", equivalence_note="S1 quality control; not a signal")
    D["repo_stock_vs_vrgsf_error"] = entry("repo_stock_vs_vrgsf_error", recon_vr, "Reconciliation: absorbing-repo stock from operations − balance-sheet VRGSF at month-end", "monthly", unit, cfg, "derived",
                                           status="fresh" if recon_vr else "unavailable")
    pw = px.get("proxy_weekly", [])
    D["fx_intervention_proxy_v04"] = entry("fx_intervention_proxy_v04", pw, "FX intervention proxy v0.4 — ΔGI − SNB ops net − Confederation net (weekly, complete weeks only)", "weekly", unit, cfg, "derived",
                                           status="fresh" if pw else "unavailable", z_window=26, lag_days=lag,
                                           equivalence_note="S3: banknotes, swap volumes and third parties remain as recognised noise; weeks after the gmges cut are in proxy_partial")
    if pw:
        D["fx_intervention_proxy_v04"]["status"] = "fresh" if lag <= 45 else "stale"
    pp = px.get("proxy_weekly_partial", [])
    D["fx_intervention_proxy_v04_partial"] = entry("fx_intervention_proxy_v04_partial", pp, "Proxy v0.4 for weeks not yet covered by the gmges amounts (ΔGI − Confederation only)", "weekly", unit, cfg, "derived",
                                                   status="fresh" if pp else "unavailable", equivalence_note="incomplete by construction until the monthly file arrives")
    D["ops_data_cut"] = {"label": "Last day covered by the SNB operations file", "value": float(lag) if ops_cut else None, "unit": "days behind today", "cut_date": ops_cut,
                         "status": "fresh" if ops_cut else "unavailable", "date": date.today().isoformat(), "lag_days": lag}
    C = Comps(cfg, "sum")
    gi = block["series"].get("sight_deposits_domestic_weekly", {}).get("value")
    if gi:
        C.flow("ops_net_5d_pct", round((n5[-1][1] if n5 else 0.0) / gi * 100, 4))
        if pw:
            C.flow("fx_proxy_v04_pct", round(pw[-1][1] / gi * 100, 4))
        ab = absorption[-1][1] if absorption else None
        if ab is not None:
            C.level("absorption_share_daily", round(ab / gi * 100, 4))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: not in the live score until the v0.4 replay sets the cuts")
    return block


def enrich_fiscal(block: dict, cfg: dict, mm: Dict[str, Series], bfl: Dict[str, Series], cal: Dict[str, Series], ni: Series, outstanding_asof: Optional[str], own_available: Optional[float], gi_level: Optional[float]) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    for k, ser, label, src in (("mmdrc_settled", mm.get("mmdrc_settled", []), "MMDRC settled (−; Liberierung)", "EFV:resultate-gmbf.xlsx"),
                               ("mmdrc_matured", mm.get("mmdrc_matured", []), "MMDRC matured (+; Fälligkeit)", "EFV:resultate-gmbf.xlsx"),
                               ("mmdrc_net_daily", mm.get("mmdrc_net_daily", []), "MMDRC net flow (daily)", "EFV:resultate-gmbf.xlsx"),
                               ("mmdrc_stock_daily", mm.get("mmdrc_stock_daily", []), "MMDRC outstanding — daily stock from auctions", "EFV:resultate-gmbf.xlsx"),
                               ("bond_settled", bfl.get("bond_settled", []), "Confederation bonds settled (−; market amount, own tranches not placed excluded)", "EFV:resultate-anleihen.xlsx"),
                               ("bond_own_retained", bfl.get("bond_own_retained", []), "Own holdings retained at auction (not placed; context)", "EFV:resultate-anleihen.xlsx"),
                               ("coupons_market_paid", cal.get("coupons_market_paid", []), "Coupons to market holders (+; annual, from bonds outstanding)", "EFV:ausstehende-anleihen.xlsx")):
        D[k] = entry(k, ser, label, "daily", unit, cfg, src, status="fresh" if ser else "unavailable")
    days = [d for d, _ in ni]
    def _dense_pos(sers, sign):
        m: Dict[str, float] = {}
        for ser in sers:
            for d, v in ser:
                m[d] = m.get(d, 0.0) + sign * v
        return [(d, round(m.get(d, 0.0), 3)) for d in days]
    gross = _dense_pos((mm.get("mmdrc_settled", []), bfl.get("bond_settled", [])), -1.0)
    red = _dense_pos((mm.get("mmdrc_matured", []), cal.get("coupons_market_paid", [])), 1.0)
    D["confed_issued_gross"] = entry("confed_issued_gross", gross, "Confederation gross issuance settled (MMDRC + bonds, market amounts; daily)", "daily", unit, cfg, "derived", status="fresh" if gross else "unavailable")
    D["confed_redeemed_gross"] = entry("confed_redeemed_gross", red, "Confederation maturities + market coupons (daily)", "daily", unit, cfg, "derived", status="fresh" if red else "unavailable")
    D["net_issuance_private_daily"] = entry("net_issuance_private_daily", ni, "Net issuance to the private sector (daily; − = drain)", "daily", unit, cfg, "derived", status="fresh" if ni else "unavailable")
    wk = S.rolling_sum(ni, 5)
    D["net_issuance_private_5d"] = entry("net_issuance_private_5d", wk, "Net issuance to the private sector, 5 sessions (− = drain)", "daily", unit, cfg, "derived", status="fresh" if wk else "unavailable",
                                         equivalence_note="v0.4 (S2): − MMDRC settled − bonds settled + MMDRC matured + market coupons; bond redemptions in the calendar; VB monthly stays live until the replay")
    D["mmdrc_maturities_next_4w"] = _cal_card("MMDRC maturing in the next 4 weeks (scheduled injection)", mm.get("mmdrc_maturities_ahead", []), unit)
    D["mmdrc_settlements_announced"] = _cal_card("MMDRC auctions announced (settlement dates; amount known after the auction)", mm.get("mmdrc_settlements_announced", []), unit, 28, 4)
    D["bond_settlements_ahead"] = _cal_card("Bond settlements ahead (scheduled drain)", bfl.get("bond_settlements_ahead", []), unit)
    D["bond_redemptions_market_next_12m"] = _cal_card("Market-held bond redemptions, next 12 months", cal.get("bond_redemptions_market_ahead", []), unit, 365, 6)
    D["coupons_market_next_4w"] = _cal_card("Market coupons, next 4 weeks", cal.get("coupons_market_ahead", []), unit)
    D["bonds_outstanding_asof"] = {"label": "Bonds outstanding list — own holdings available (CHF m)", "value": own_available, "as_of": outstanding_asof, "own_available_m": own_available, "status": "fresh" if outstanding_asof else "unavailable",
                                   "date": date.today().isoformat(), "note": "own-holding sales in the secondary market are not dated (S6)"}
    C = Comps(cfg, "sum")
    if gi_level:
        C.flow("net_issuance_5d_pct", round((wk[-1][1] if wk else 0.0) / gi_level * 100, 4))
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow: weekly net issuance by settlement; the VB monthly band stays live until the replay")
    return block
