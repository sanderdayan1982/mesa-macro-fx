"""JPY v0.4 enrichment (round 4 design, 2026-09-10):
  Treasury flow of the regime = 財政等要因 REALIZED (速報 live, 確報 history) = −Δ government account; the MoF net issuance by issue date
  (net of the BoJ's holdings by issue, `mei`) is a decomposition / reconciliation candidate, never summed with it. The projection (予想)
  is archived by publication date and enters only as `surprise = realized − projected` (shadow / intervention detector).
  Central bank: BoJ operations by operation (ope files: FACE, settlement = Date of Exercise) reconciled with the daily file's CASH line.
  Denominator: 当座預金残高 total. Shadow components only (signals.components_v04); live scores untouched. Units: JPY 100 million."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, List, Optional
from . import series as S
from .series import Series
from .blocks import entry
from .scoring import Comps
from .ops_jpy import best_realized


def _cal_card(label: str, ahead: Series, unit: str, days: int = 28, n: int = 8, note: Optional[str] = None) -> dict:
    lim = (date.today() + timedelta(days=days)).isoformat()
    sel = [(d, v) for d, v in ahead if d <= lim and v]
    out = {"label": label, "value": round(sum(v for _, v in sel), 1) if ahead else None, "unit": unit,
           "status": "fresh" if ahead else "unavailable", "date": date.today().isoformat(), "calendar": sel[:n]}
    if note:
        out["note"] = note
    return out


def _pct(v: Optional[float], base: Optional[float]) -> Optional[float]:
    if v is None or not base:
        return None
    return round(v / base * 100, 4)


def enrich_fiscal(block: dict, cfg: dict, daily: Dict[str, Dict[str, Series]], ni: Dict[str, Series], juqp: Optional[dict], cab_level: Optional[float],
                  mei_note: Dict[str, object]) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    fin, prov, proj = daily.get("final", {}), daily.get("prov", {}), daily.get("proj", {})
    real = S.clean(best_realized(fin.get("treasury", []), prov.get("treasury", [])))
    D["treasury_realized_daily"] = entry("treasury_realized_daily", real, "財政等要因 realized — Treasury funds and others (+ = net payment → reserves created; 速報 today, 確報 history)", "daily", unit, cfg,
                                         "boj:juq jx/jd", status="fresh" if real else "unavailable",
                                         equivalence_note="J1: = −Δ government account (spending − taxes + redemptions − issuance + FX intervention + other); the regime's Treasury flow")
    t5 = S.rolling_sum(real, 5)
    D["treasury_realized_5d"] = entry("treasury_realized_5d", t5, "Treasury funds and others, 5 sessions (+ = injection)", "daily", unit, cfg, "derived", status="fresh" if t5 else "unavailable")
    pj = S.clean(proj.get("treasury", []))
    D["treasury_projection_daily"] = entry("treasury_projection_daily", pj, "財政等要因 projected (予想, published ~18:00 Tokyo the previous business day)", "daily", unit, cfg, "boj:juq jp",
                                           status="fresh" if pj else "unavailable", equivalence_note="J2: expected component only; never a realized flow")
    sp = S.merge_series(real, pj, lambda a, b: round(a - b, 1))
    D["treasury_surprise_daily"] = entry("treasury_surprise_daily", sp, "Treasury surprise = realized − projected (intervention / tax-day detector)", "daily", unit, cfg, "derived",
                                         status="fresh" if sp else "unavailable", z_window=60)
    sp5 = S.rolling_sum(sp, 5)
    D["treasury_surprise_5d"] = entry("treasury_surprise_5d", sp5, "Treasury surprise, 5 sessions", "daily", unit, cfg, "derived", status="fresh" if sp5 else "unavailable")
    rev = S.merge_series(S.clean(fin.get("treasury", [])), S.clean(prov.get("treasury", [])), lambda a, b: round(a - b, 1))
    D["treasury_revision_daily"] = entry("treasury_revision_daily", rev, "Revision 確報 − 速報 (restatement layer)", "daily", unit, cfg, "derived", status="fresh" if rev else "unavailable")
    # MoF net issuance by issue date, net of the BoJ's holdings (mei)
    for k, label in (("net_issuance_private_daily", "MoF net issuance to the private sector by issue date (daily; − = drain): −JGB −T-Bill issued + T-Bill matured + JGB redeemed NET of BoJ holdings"),
                     ("issued_jgb", "JGBs issued (issue date; −; competitive + non-price competitive I/II)"), ("issued_tbill", "T-Bills issued (issue date; −)"),
                     ("matured_tbill", "T-Bills matured (+; gross — not in mei)"), ("matured_jgb_net", "JGBs redeemed to the private sector (+; Σ issued − BoJ holding of the line)"),
                     ("matured_jgb_gross", "JGBs redeemed — gross"), ("coupons_jgb_net", "JGB coupons to the private sector (+; net of BoJ holdings by issue)")):
        ser = ni.get(k, [])
        D[k] = entry(k, ser, label, "daily", unit, cfg, "mof:auction results XLS + boj:mei", status="fresh" if ser else "unavailable")
    nd = ni.get("net_issuance_private_daily", [])
    days = [d for d, _ in nd]
    def _dense_pos(sers, sign):
        m: Dict[str, float] = {}
        for ser in sers:
            for d, v in ser:
                m[d] = m.get(d, 0.0) + sign * (v or 0.0)
        return [(d, round(m.get(d, 0.0), 1)) for d in days]
    D["mof_issued_gross"] = entry("mof_issued_gross", _dense_pos((ni.get("issued_jgb", []), ni.get("issued_tbill", [])), -1.0), "MoF issuance settled — JGBs + T-Bills (daily, issue date)", "daily", unit, cfg, "derived", status="fresh" if nd else "unavailable")
    D["mof_redeemed_net"] = entry("mof_redeemed_net", _dense_pos((ni.get("matured_tbill", []), ni.get("matured_jgb_net", [])), 1.0), "MoF redemptions to the private sector — T-Bills gross + JGBs net of BoJ holdings (daily)", "daily", unit, cfg, "derived", status="fresh" if nd else "unavailable")
    n5 = S.rolling_sum(nd, 5)
    D["net_issuance_private_5d"] = entry("net_issuance_private_5d", n5, "MoF net issuance to the private sector, 5 sessions (− = drain)", "daily", unit, cfg, "derived", status="fresh" if n5 else "unavailable",
                                         equivalence_note="J3: decomposition of the Treasury flow — never summed with 財政等要因 (identity, round 1)")
    resid = S.merge_series(real, nd, lambda a, b: round(a - b, 1))
    D["treasury_ex_issuance_daily"] = entry("treasury_ex_issuance_daily", resid, "Treasury funds ex issuance = realized − MoF net issuance (taxes, spending, pensions, intervention, other)", "daily", unit, cfg, "derived",
                                            status="fresh" if resid else "unavailable", equivalence_note="income channel; contaminated by その他 (foreign central banks' yen accounts) — Kimi, round 4")
    D["jgb_redemptions_net_next_12m"] = _cal_card("JGB redemptions next 12 months — NET of BoJ holdings (mei)", ni.get("jgb_redemptions_net_ahead", []), unit, 365, 6,
                                                  note="gross %s" % round(sum(v for _, v in ni.get("jgb_redemptions_gross_ahead", [])), 0))
    D["jgb_coupons_net_next_4w"] = _cal_card("JGB coupons next 4 weeks — NET of BoJ holdings", ni.get("jgb_coupons_net_ahead", []), unit)
    D["tbill_maturities_next_4w"] = _cal_card("T-Bill maturities next 4 weeks (gross)", ni.get("tbill_maturities_ahead", []), unit)
    D["boj_share_by_maturity"] = entry("boj_share_by_maturity", ni.get("boj_share_by_maturity", []), "BoJ share of each JGB maturity (mei / Σ issued)", "event", "ratio", cfg, "boj:mei", status="fresh" if ni.get("boj_share_by_maturity") else "unavailable")
    D["mof_data_cut"] = {"label": "MoF auction-results XLS — last issue date in the file (net issuance flows stop here)", "value": mei_note.get("mof_lag_days"), "cut_date": mei_note.get("mof_cut"),
                         "status": "fresh" if mei_note.get("mof_cut") else "unavailable", "date": date.today().isoformat(), "note": "the XLS lags the auction calendar by weeks; maturities after the cut are in the calendars, not in the flow"}
    D["mei_asof"] = {"label": "BoJ JGB holdings snapshot (mei) used for netting", "value": mei_note.get("total"), "cut_date": mei_note.get("asof"), "published": mei_note.get("published"),
                     "unit": unit, "status": "fresh" if mei_note.get("asof") else "unavailable", "date": date.today().isoformat(), "unmapped": mei_note.get("unmapped", [])}
    if juqp:
        D["monthly_projection"] = {"label": "BoJ monthly projection (見込み) %s — Treasury funds and others" % juqp.get("month"), "value": juqp.get("treasury"), "unit": unit,
                                   "status": "fresh", "date": juqp.get("published") or date.today().isoformat(),
                                   "breakdown": {"jgb_net": juqp.get("jgb_net"), "tbill_net": juqp.get("tbill_net"), "other": juqp.get("other"), "banknotes": juqp.get("banknotes"), "surplus": juqp.get("surplus")},
                                   "shortage_days": juqp.get("shortage_days", []), "surplus_days": juqp.get("surplus_days", []),
                                   "note": "monthly reconciliation target: MoF net issuance (net of mei) vs 国債等 + 国庫短期証券等 (BoJ-held redemptions excluded, note 4)"}
        m = juqp.get("month")
        if m and nd:
            mo = [v for d, v in nd if d.startswith(m) and v is not None]
            D["monthly_reconciliation"] = {"label": "Month-to-date MoF net issuance vs BoJ projected JGB + T-Bill net", "value": round(sum(mo), 1) if mo else None, "unit": unit,
                                           "projected": (juqp.get("jgb_net") or 0) + (juqp.get("tbill_net") or 0), "days": len(mo), "status": "fresh" if mo else "unavailable", "date": date.today().isoformat()}
    C = Comps(cfg, "sum")
    if cab_level:
        C.flow("treasury_5d_pct", _pct(t5[-1][1], cab_level) if t5 else 0.0)
        if sp5:
            C.flow("treasury_surprise_5d_pct", _pct(sp5[-1][1], cab_level))
        if n5:
            C.flow("net_issuance_5d_pct", _pct(n5[-1][1], cab_level))
        for k, v in ((block["signals"].get("components") or {}).get("flow", {})).items():
            C.flow(k, v)
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow (J1–J3): 財政等要因 realized 5 sessions in % of 当座預金残高 + surprise + MoF net issuance (decomposition); cuts by the v0.4 replay")
    return block


def enrich_central_bank(block: dict, cfg: dict, daily: Dict[str, Dict[str, Series]], ops: Dict[str, Series], recon: Series, cab_level: Optional[float], ops_note: Dict[str, object]) -> dict:
    unit = cfg["units"]["balance_sheet"]
    D = block["derived"]
    fin, prov = daily.get("final", {}), daily.get("prov", {})
    for k, label in (("ops_ex_lsp", "BOJ Loans and Market Operations excl. Loan Support Program (daily file; cash)"), ("jgb_purch", "Outright purchases of JGBs settled (daily file; CASH)"),
                     ("banknotes", "Banknotes factor (− = net issuance)"), ("net_change", "Net change in current account balances"), ("cab", "Current account balances (amount outstanding)")):
        ser = S.clean(best_realized(fin.get(k, []), prov.get(k, [])))
        D["%s_v04" % k] = entry("%s_v04" % k, ser, label, "daily", unit, cfg, "boj:juq jx/jd", status="fresh" if ser else "unavailable")
    for k, label in (("jgb_purch_settled", "Outright JGB purchases by operation — FACE, at Date of Exercise (T+1)"), ("ops_net_daily", "BoJ operations net by operation (face; start + / end −)"),
                     ("slf_out", "Securities lending facility — JGSs sold under repo (− at start)"), ("pooled_supplied", "Funds-supplying against pooled collateral (+ at start)")):
        ser = ops.get(k, [])
        D[k] = entry(k, ser, label, "daily", unit, cfg, "boj:ope XLSX by operation", status="fresh" if ser else "unavailable")
    D["jgb_purch_face_minus_cash"] = entry("jgb_purch_face_minus_cash", recon, "Reconciliation: JGB purchases FACE (ope) − CASH (daily file), same settlement date", "daily", unit, cfg, "derived",
                                           status="fresh" if recon else "unavailable", equivalence_note="the reserve flow is the cash line; face is what the market delivered (7,659 vs 7,200 on 2026-09-10)")
    o5 = S.rolling_sum(ops.get("ops_net_daily", []), 5)
    D["ops_net_5d"] = entry("ops_net_5d", o5, "BoJ operations net, 5 sessions (face)", "daily", unit, cfg, "derived", status="fresh" if o5 else "unavailable")
    D["ops_calendar_next_4w"] = _cal_card("Operation end dates next 4 weeks (− repayments of funds-supplying ops, + SLF repurchases)", ops.get("ops_calendar_ahead", []), unit)
    D["ops_data_cut"] = {"label": "Last operations file parsed", "value": ops_note.get("lag_days"), "cut_date": ops_note.get("last_date"), "status": "fresh" if ops_note.get("last_date") else "unavailable",
                         "date": date.today().isoformat(), "note": "ope files: %s; daily files: %s" % (ops_note.get("ope_files"), ops_note.get("daily_files"))}
    C = Comps(cfg, "mean2")
    if cab_level:
        j = D.get("jgb_purch_v04", {}).get("value")
        C.flow("ops_net_5d_pct", _pct(o5[-1][1], cab_level) if o5 else 0.0)
        cash5 = S.rolling_sum(S.clean(best_realized(fin.get("ops_ex_lsp", []), prov.get("ops_ex_lsp", []))), 5)
        if cash5:
            C.flow("ops_cash_5d_pct", _pct(cash5[-1][1], cab_level))
        for k, v in ((block["signals"].get("components") or {}).get("flow", {})).items():
            C.flow(k, v)
    block["signals"]["components_v04"] = dict(C.to_dict(), note="shadow (J4): operations by operation (face) + 金融調節 cash line, 5 sessions in % of 当座預金残高; cuts by the v0.4 replay")
    return block
