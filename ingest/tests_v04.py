"""v0.4 self-checks (run: python -m ingest.tests_v04). No pytest dependency; exits 1 on failure.
Checks are reconciliations against primary data already in the repo, never against hand-typed expectations."""
from __future__ import annotations
import csv
import os
import sys
from . import ops_cad as O

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "fixtures", "cad")


def rows(name):
    return O.rows_from_csv(open(os.path.join(FIX, name + ".csv"), encoding="utf-8").read())


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def main_gbp() -> int:
    from . import ops_gbp as G
    fails = []
    fx = os.path.join(ROOT, "fixtures", "gbp")
    rd = lambda n: G.rows_from_csv(open(os.path.join(fx, n), encoding="utf-8").read())
    days = G.business_days("2025-01-01", "2026-09-10")
    ops = G.repo_series(rd("boe_str_by_operation.csv"), rd("boe_iltr_by_operation.csv"), rd("boe_ctrf_by_operation.csv"), days)
    # STR: the operation of 2026-08-27 (124 825) is the stock the Weekly Report shows on 2026-09-02 (RPWB67A = 124 825)
    iadb = {r[0]: float(r[1]) for r in csv.reader(open(os.path.join(ROOT, "history", "gbp", "RPWB67A.csv"))) if r and r[0] != "date"}
    st = dict(ops["str_outstanding_ops"])
    if "2026-09-02" in iadb and "2026-09-02" in st:
        check(abs(st["2026-09-02"] - iadb["2026-09-02"]) < 1.0, "STR stock from operations %.0f = IADB RPWB67A %.0f on 2026-09-02" % (st["2026-09-02"], iadb["2026-09-02"]), fails)
    check(dict(ops["str_net_daily"]).get("2026-09-03") == 123656.0 - 124825.0, "STR net 2026-09-03 = new op − maturing op", fails)
    check(all(d > "2026-09-03" for d, _ in ops["repo_maturities_ahead"]), "repo maturity calendar strictly after the last published operation", fails)
    apf = G.apf_series(rd("boe_apf_gilt_sales.csv"), rd("boe_apf_maturity_profile.csv"))
    check(abs(dict(apf["apf_sales_daily"]).get("2026-08-18", 0) - (-(380.712935 + 284.865799 + 59.337239))) < 0.01, "APF sales 2026-08-18 = −Σ proceeds (three gilts)", fails)
    check(dict(apf["apf_redemptions_ahead"]).get("2026-10-22") == 5742.8, "APF redemption calendar 2026-10-22 = 5 742.8 (0 3/8% 2026)", fails)
    check(G.coupon_from_name("0 3/8% Treasury Gilt 2026") == 0.375 and G.coupon_from_name("4¼% Treasury Stock 2032") == 4.25 and G.coupon_from_name("1 5/8% Treasury Gilt 2071") == 1.625, "coupon parsed from the gilt name", fails)
    check(G.dividend_dates("22 Apr/Oct", "2026-09-10", "2027-09-10") == ["2026-10-22", "2027-04-22"], "dividend dates from '22 Apr/Oct'", fails)
    d1a = rd("dmo_gilts_in_issue_D1A.csv")
    prof = G.apf_holdings_by_name(rd("boe_apf_maturity_profile.csv"))
    cal = G.gilt_calendar(d1a, prof)
    red = dict(cal["gilt_redemptions_private_ahead"])
    check(abs(red.get("2026-10-22", 0) - (33660.598 - 5742.8)) < 0.01, "private-held redemption of the 0 3/8% 2026 = amount in issue − APF nominal", fails)
    tb = G.tbill_series(rd("dmo_tbill_tenders_D22D.csv"))
    check(dict(tb["tbill_issued"]).get("2026-09-07") == 4500.0, "T-bills issued 2026-09-07 = 4 500 (1m+3m+6m tenders of 2026-09-04)", fails)
    arch = {"2026-09-08": {"A": 100.0, "B": 50.0}, "2026-09-09": {"A": 103.0, "C": 7.0, "D": 9.0}}
    gi = G.issuance_from_archive(arch, {"B": "2026-09-09"}, {"B": 20.0}, {"C": "2026-09-09", "D": "2020-01-01"})
    check(dict(gi["gilt_issued_daily"]).get("2026-09-09") == 10.0 and dict(gi["gilt_redeemed_private"]).get("2026-09-09") == 30.0 and dict(gi["gilt_redeemed_apf"]).get("2026-09-09") == 20.0, "D1A archive: Δ issue + new gilt = issuance (old gilt missing before ≠ issuance); vanished gilt = redemption split private/APF", fails)
    res = G.exchequer_residual_weekly({"reserves": [("w1", 100.0), ("w2", 110.0)], "str": [("w1", 10.0), ("w2", 12.0)], "ltr": [("w1", 5.0), ("w2", 5.0)], "apf": [("w1", 50.0), ("w2", 48.0)],
                                       "tfsme": [("w1", 8.0), ("w2", 7.0)], "wm": [("w1", 0.0), ("w2", 0.0)], "notes": [("w1", 30.0), ("w2", 31.0)]})
    check(dict(res["exchequer_residual_weekly"]).get("w2") == 10.0 - 2.0 - 0.0 + 2.0 + 1.0 + 1.0, "Exchequer residual identity (ΔR − ΔSTR − ΔLTR − ΔAPF − ΔTFSME − ΔW&M + ΔNotes)", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


def main_nzd() -> int:
    from . import ops_nzd as N
    import json
    fails = []
    fx = os.path.join(ROOT, "fixtures", "nzd")
    rd = lambda n: [dict(r) for r in csv.DictReader(open(os.path.join(fx, n), encoding="utf-8"))]
    days = N.business_days("2025-01-01", "2026-09-10")
    rr = [{"date_held": r["date_held"], "maturity": r["maturity"], "allocated": float(r["allocated"])} for r in rd("d3_rr_omo.csv")]
    omo = N.omo_flows(rr, days)
    check(dict(omo["omo_settled_daily"]).get("2026-09-03") == 5068.0, "OMO settled 2026-09-03 = 5 068 (D3 per operation)", fails)
    check(all(d > "2026-09-03" for d, _ in omo["omo_maturities_ahead"]), "OMO maturity calendar strictly after the last published operation", fails)
    check(N.bd_add("2026-09-08", 1) == "2026-09-09" and N.bd_add("2026-09-03", 3) == "2026-09-08", "settlement convention bills T+1 / bonds T+3 matches the tender listing", fails)
    tb = rd("nzdm_tbill_tenders.csv")
    rows = [dict(r, kind="tbill", accepted=r["accepted"], maturity=r["maturity"], tender_date=r["tender_date"]) for r in tb]
    tf = N.tender_flows(rows)
    check(dict(tf["tender_settled"]).get("2026-09-09") == 225.0, "bills of the 2026-09-08 tender settle 2026-09-09 (100 + 100 + 25)", fails)
    bo = [{"month_end": r["month_end"], "maturity": r["maturity"], "coupon": float(r["coupon"]), "market": float(r["market"])} for r in rd("nzdm_bonds_on_issue.csv")]
    cal = N.bond_calendar(bo)
    check(dict(cal["bond_redemptions_market_ahead"]).get("2027-04-15") == 15980.0, "market-held redemption 2027-04-15 = 15 980 (total 16 330 − RBNZ 350)", fails)
    res = N.reconcile_monthly([("2026-07-01", 100.0)] + [("2026-07-%02d" % d, 10.0) for d in range(2, 24)] + [("2026-07-31", 5.0)], [("2026-07-31", 300.0)])
    check(dict(res["error"]).get("2026-07-31") == 100.0 + 220.0 + 5.0 - 300.0, "monthly reconciliation error = Σ proxy − reference", fails)
    csa = N.read_csv_series(os.path.join(fx, "csa_daily_oia.csv"))
    fl = dict(N.csa_flow_from_balance(csa))
    check(abs(fl["1997-11-11"] - (458.189 - 411.495)) < 1e-6, "−ΔCSA = Crown flow into settlement cash (sign)", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


def main_chf() -> int:
    """CHF: reconciliations of the per-operation stocks against the SNB balance sheet (snbbipo ES / VRGSF), sign conventions, cuts."""
    from . import ops_chf as C
    import calendar as _cal
    import json
    fails = []
    fx = os.path.join(ROOT, "fixtures", "chf")
    ops = [dict(r) for r in csv.DictReader(open(os.path.join(fx, "snb_ops_rows.csv"), encoding="utf-8"))]
    days = C.business_days("2019-11-01", "2026-09-10")
    rf, bf = C.repo_flows(ops, days), C.bills_flows(ops, days)
    rows = list(csv.reader(open(os.path.join(fx, "snbbipo.csv"), encoding="utf-8")))
    h = rows[0]
    def me(ym):
        y, m = map(int, ym.split("-"))
        return "%s-%02d" % (ym, _cal.monthrange(y, m)[1])
    es = C.clean([(me(r[0]), float(dict(zip(h, r))["snbbipo:ES"])) for r in rows[1:]])
    vr = C.clean([(me(r[0]), float(dict(zip(h, r))["snbbipo:VRGSF"])) for r in rows[1:]])
    re_es = dict(C.reconcile_month_end(bf["bills_stock_full"], es))
    re_vr = dict(C.reconcile_month_end(rf["repo_ct_stock_full"], vr))
    check(all(abs(re_es[d]) <= 10 for d in ("2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31")), "Bills stock from gmges = balance-sheet ES within CHF 10 m at every month-end Mar–Jul 2026 (Jul: %.0f vs %.0f)" % (dict(bf["bills_stock_full"])["2026-07-31"], dict(es)["2026-07-31"]), fails)
    check(all(re_vr[d] == 0.0 for d in ("2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31")), "absorbing-repo stock from gmges = balance-sheet VRGSF exactly at every month-end Mar–Jul 2026", fails)
    cut = rf["ops_cut"][0][0]
    check(cut == "2026-07-31", "operations cut = last settlement ('from') date in the file (2026-07-31; last transaction 07-29 settles T+2)", fails)
    check(all(d <= cut for d, _ in rf["repo_net_daily"]) and all(d > cut for d, _ in rf["repo_maturities_ahead"]), "repo flows stop at the cut; later maturities go to the calendar", fails)
    check(dict(rf["repo_ct_settled"]).get("2026-07-31") == -17420.0 and dict(rf["repo_ct_matured"]).get("2026-07-31") == 15220.0 and dict(rf["repo_maturities_ahead"]).get("2026-08-03") == 13070.0, "repo 2026-07-31: settled −17 420, matured +15 220; 08-03 maturity 13 070 in the calendar", fails)
    check(dict(rf["repo_ct_stock_daily"])["2026-07-31"] == dict(vr)["2026-07-31"], "displayed repo stock at the cut (2026-07-31) = VRGSF July exactly (%.0f)" % dict(vr)["2026-07-31"], fails)
    check(dict(bf["bills_issued"]).get("2026-07-27") == -16225.0 and dict(bf["bills_repaid"]).get("2026-07-27") == 9592.0, "Bills 2026-07-27: placed −(15 645 + 580), repaid +(9 177 + 415) from the gmges rows", fails)
    mm = C.efv_records_from_cells(json.load(open(os.path.join(ROOT, "fixtures", "chf_hist", "efv_mmdrc_cells.json"), encoding="utf-8")))
    mf = C.mmdrc_flows(mm, days)
    check(dict(mf["mmdrc_settled"]).get("2026-09-10") == -469.2 and dict(mf["mmdrc_matured"]).get("2026-09-10") == 400.0, "MMDRC 2026-09-10: settled −469.2 (Liberierung), matured +400 (Fälligkeit)", fails)
    check(mf["mmdrc_settlements_announced"] == [("2026-09-17", 0.0)] and all(d <= "2026-09-10" for d, _ in mf["mmdrc_net_daily"]), "announced MMDRC auction (no amount) in the calendar, not in the flows", fails)
    out, asof = C.read_outstanding_csv(os.path.join(fx, "efv_bonds_outstanding.csv"))
    check(asof == "2026-08-31" and abs(sum(C._num(r["placed_market"]) for r in out) - 73655.65) < 0.5, "bonds outstanding list as of 31.08.2026, placed on the market Σ 73 655.65 (file total row)", fails)
    cal = C.bond_calendar(out)
    check(dict(cal["coupons_market_paid"]).get("2026-06-25") == round(3190.555 * 0.02, 3), "coupon 2026-06-25 = Eidg. 25.06.14/64 placed 3 190.555 × 2%", fails)
    check(cal["bond_redemptions_market_ahead"] == [("2027-06-27", 2865.515)], "next market redemption Eidg. 27.06.07/27: 2 865.515 placed (own placed 385 included, own available 215 excluded)", fails)
    gi = [("2026-07-10", 100.0), ("2026-07-17", 105.0), ("2026-07-24", 104.0)]
    px = C.intervention_proxy(gi, [("2026-07-13", 2.0), ("2026-07-20", -1.0)], [("2026-07-15", -1.0)], "2026-07-20")
    check(px["proxy_weekly"] == [("2026-07-17", 4.0)] and px["proxy_weekly_partial"] == [("2026-07-24", 0.0)], "proxy = ΔGI − ops − Confederation over (prev Friday, Friday]; weeks after the cut are partial", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


def main_aud() -> int:
    """AUD: OMO per operation vs the RBA unwind schedule and A3 outstanding; AOFM settlement dates and proceeds; TB gross calendar."""
    from . import ops_aud as A
    from .providers import RbaProvider
    from .providers_chf import xlsx_sheets
    fails = []
    fx = os.path.join(ROOT, "fixtures", "aud")
    hx = os.path.join(ROOT, "fixtures", "aud_hist")
    days = A.business_days("2023-01-01", "2026-09-10")
    ops = A.parse_omo_details(open(os.path.join(fx, "rba_a3_omo_repo_transaction_details.csv"), encoding="utf-8").read())
    unw = A.parse_omo_unwinds(open(os.path.join(fx, "rba_a3_omo_repo_unwinds.csv"), encoding="utf-8").read())
    omo = A.omo_flows(ops, unw, days)
    check(dict(omo["omo_dealt_daily"]).get("2026-09-09") == 2231.0 + 5459.0, "OMO dealt 2026-09-09 = 2 231 (7 d) + 5 459 (28 d)", fails)
    imp = dict(omo["omo_maturities_implied_ahead"])
    check(imp.get("2026-09-16") == 2231.0 + 7041.0 and dict(unw).get("2026-09-16") == 9296.0, "implied maturity 2026-09-16 = 9 272 (dealt + term, same-day settlement) vs published unwind 9 296 (interest)", fails)
    check(all(0 < v < 1.0 for _, v in omo["unwinds_vs_implied_pct"]), "published unwinds exceed implied maturities by < 1 % on every scheduled day (accrued interest)", fails)
    ref = RbaProvider.parse(open(os.path.join(fx, "rba_a3_es.csv"), encoding="utf-8").read(), ["AORROMO"], strict=False)["AORROMO"]
    rec = dict(A.reconcile_stock(omo["omo_stock_full"], ref))
    check(all(abs(rec[d]) / dict(ref)[d] < 0.005 for d in ("2026-08-27", "2026-09-02", "2026-09-07")), "OMO stock from operations = A3 outstanding (AORROMO) within 0.5 % (interest) on 27-Aug / 02-Sep / 07-Sep 2026", fails)
    check(omo["omo_cut"][0][0] == "2026-09-09" and all(d > "2026-09-09" for d, _ in omo["omo_unwinds_ahead"]), "OMO cut at the last operation; unwind schedule strictly ahead", fails)
    recs = {}
    for k, fn in (("tb", "aofm_treasury_bonds_issuance.xlsx"), ("tn", "aofm_treasury_notes_issuance.xlsx"), ("tib", "aofm_treasury_indexed_bonds_issuance.xlsx")):
        recs[k] = A.parse_transactions(xlsx_sheets(open(os.path.join(hx, fn), "rb").read())["Transactions"])
    bb = {"tb": A.records_from_csv(os.path.join(hx, "aofm_tb_buybacks.csv"), "buyback"), "tib": A.records_from_csv(os.path.join(hx, "aofm_tib_buybacks.csv"), "buyback")}
    iss = A.issuance_flows(recs, bb, days)
    last_tb = recs["tb"][-1]
    check(last_tb["held"] == "2026-09-09" and last_tb["settled"] == "2026-09-11" and dict(iss["aofm_settlements_ahead"]).get("2026-09-11") == 742.719, "TB1711 held 09-09 settles 09-11 with proceeds 742.719 m (nominal 800 m) → calendar, not flows", fails)
    tn = [r for r in recs["tn"] if r["held"] == "2026-09-03"]
    check(len(tn) == 3 and all(r["settled"] == "2026-09-04" for r in tn) and abs(dict(iss["tn_settled"]).get("2026-09-04", 0) + sum(r["settlement proceeds"] for r in tn) / 1e6) < 1e-3,
          "three Treasury Note lines held 09-03 settle 09-04 (T+1): −3 929.401 m proceeds", fails)
    check(dict(iss["tn_matured"]).get("2026-08-21") == 6000.0 and dict(iss["tn_maturities_ahead"]).get("2026-09-11") == 7000.0, "note maturities: 6 000 m on 2026-08-21, 7 000 m due 2026-09-11", fails)
    check(dict(iss["buybacks_settled"]).get("2024-12-03") == 3026.46 and not any(d == "2018-08-03" for d, _ in iss["buybacks_settled"]), "buyback proceeds by Date Settled; 'RBA' transfers (e.g. 2018-08-01 3 000 m) excluded", fails)
    check(all(d <= "2026-09-10" for d, _ in iss["net_issuance_private_daily"]) and len(iss["net_issuance_private_daily"]) == len(days), "net issuance dense over business days, nothing future-dated", fails)
    lines = A.face_value_from_csv(os.path.join(hx, "aofm_tb_face_value_by_line.csv"))
    cal = A.tb_calendar(lines)
    check(cal["tb_face_total"] == [("2026-08-31", 921749.274)] and dict(cal["tb_redemptions_gross_ahead"]).get("2026-09-21") == 39400.0, "TB face value 2026-08-31 Σ 921 749.274 m; 21-Sep-2026 line 39 400 m (gross, RBA holdings included)", fails)
    check(abs(dict(cal["tb_coupons_gross_ahead"]).get("2026-09-21", 0) - (39400.0 * 0.5 + 28200.0 * 4.25 + 14800.0 * 3.0) / 200) < 1e-6,
          "coupons 2026-09-21 = Σ face × coupon / 2 over the 21-Sep-2026, 21-Mar-2036 and 21-Mar-2047 lines (semi-annual on the maturity day-of-month)", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


def main_eur() -> int:
    """EUR: settlement conventions and cash per issuer against the captured primary pages/files; PDF and HTML parsers."""
    from . import ops_eur as U
    from .providers_eur import FinanzagenturProvider
    import json
    fails = []
    hx = os.path.join(ROOT, "fixtures", "eur_hist")
    days = U.business_days("2024-01-01", "2026-09-10")
    fa = FinanzagenturProvider(fixtures_dir=os.path.join(ROOT, "fixtures", "eur"))
    fa.fetch()
    de = U.de_records(fa.rows)
    r = next(x for x in de if x["auction"] == "2026-09-08" and x["isin"] == "DE000BU3F007")
    check(r["settlement"] == "2026-09-10" and r["nominal"] == 644.0 and abs(r["cash"] - 644 * 88.28 / 100) < 0.01, "DE Green 15y 2026-09-08: allotted 644 (retention 106 excluded), value date T+2 = 09-10, cash = 644 × 88.28 %", fails)
    fr = U.fr_records_from_csv(os.path.join(hx, "aft_oat_auctions.csv"), os.path.join(hx, "aft_btf_auctions.csv"))
    b = [x for x in fr if x["kind"] == "bill"][-1]
    check(b["auction"] == "2026-07-27" and b["settlement"] == "2026-07-29" and b["maturity"] == "2027-07-14" and b["nominal"] == 2476.0, "FR BTF 2026-07-27 (history XLSX): settled 07-29 (T+2), matures 2027-07-14, total issued 2 476 (NCTs included)", fails)
    o = [x for x in fr if x["kind"] == "bond" and x["isin"] == "FR0014008181"][-1]
    check(o["settlement"] == "2026-07-20" and o["maturity"] == "2053-07-25", "FR OAT€i 0,1% 25 juillet 2053: settlement from the file, maturity parsed from the line name", fails)
    h = U.fr_records_from_html(open(os.path.join(hx, "aft_latest_auctions_2026-09.html"), encoding="utf-8").read())
    check(len(h) == 8 and h[0]["settlement"] == "2026-09-07" and h[0]["nominal"] == 4193.0 and h[-1]["kind"] == "bill" and h[-1]["settlement"] == "2026-09-09" and h[-1]["maturity"] == "2027-09-08",
          "FR latest-auctions HTML (Sep 2026): 4 OAT lines settled 09-07 (4 193 m first line) + 4 BTF settled 09-09; maturities parsed", fails)
    es = U.es_records_from_csv(os.path.join(hx, "es_tesoro_auctions.csv"))
    e = [x for x in es if x["source"] == "tesoro_nid_46359"][0]
    check(e["settlement"] == "2026-09-08" and e["maturity"] == "2036-04-30" and abs(e["nominal"] - (1996.03 + 415.35)) < 0.01 and abs(e["cash"] - (1949.81 + 405.71)) < 0.01,
          "ES Obligaciones 10y 2026-09-03: settled 09-08 (T+3), nominal incl. 2ª vuelta, cash 1 949.81 + 405.71", fails)
    html_es = open(os.path.join(hx, "es_tesoro_auctions.csv"), encoding="utf-8").read()
    fake = '<table><tr><th>Plazo</th><td>10 AÑOS</td></tr><tr><th>Fecha subasta</th><td>03/09/2026</td></tr><tr><th>Fecha vencimiento</th><td>30/04/2036</td></tr><tr><th>Fecha de liquidación</th><td>08/09/2026</td></tr><tr><th>Nominal adjudicado</th><td>1.996,03</td></tr><tr><th>Nominal adjudicado (2ª vuelta)</th><td>415.35</td></tr><tr><th>Efectivo adjudicado</th><td>1.949,81</td></tr><tr><th>Efectivo adjudicado (2ª vuelta)</th><td>405.71</td></tr><tr><th>Ratio de cobertura</th><td>2,29</td></tr><tr><th>Tipo de interés medio</th><td>3,736</td></tr></table>'
    p = U.es_parse_auction_page(fake, "Subasta de Obligaciones a 10 años", "46359")[0]
    check(abs(p["nominal"] - 2411.38) < 0.01 and abs(p["cash"] - 2355.52) < 0.01 and p["cover"] == 2.29, "ES page parser handles '1.996,03' and '415.35' number styles on the same page", fails)
    try:
        import pdfplumber  # type: ignore
        import io as _io
        for fn, exp in (("mef_btp10_2026-07-30.pdf", ("2026-07-30", "2026-08-03", 1750.0, 236.135)), ("mef_bot6_latest.pdf", ("2026-08-27", "2026-08-31", 2500.0, 107.055))):
            with pdfplumber.open(os.path.join(hx, fn)) as pp:
                txt = "\n".join(pg.extract_text() or "" for pg in pp.pages)
            rr = U.it_parse_pdf_text(txt, fn)
            check(len(rr) == 2 and rr[0]["auction"] == exp[0] and rr[0]["settlement"] == exp[1] and rr[0]["nominal"] == exp[2] and rr[1]["nominal"] == exp[3], "IT PDF %s: auction %s → settlement %s, allotted %s + specialists %s" % ((fn,) + exp), fails)
    except ImportError:
        print("skip IT PDF checks (pdfplumber missing)")
    eu = U.eu_records_from_tables(json.load(open(os.path.join(hx, "eu_auction_result_tables.json"), encoding="utf-8")))
    bo = [x for x in eu if x["isin"] == "EU000A4EXVK3" and x["auction"] == "2026-08-31"]
    check(len(bo) == 1 and bo[0]["settlement"] == "2026-09-02" and abs(bo[0]["cash"] - 2183 * 98.28 / 100) < 0.01, "EU-Bond auction 2026-08-31: settled 09-02 (T+2), cash = 2 183 × 98.280 %; zero non-competitive leg not duplicated", fails)
    bi = [x for x in eu if x["isin"] == "EU000A4E0DU7"][0]
    check(bi["settlement"] == "2026-09-04" and bi["maturity"] == "2027-09-03" and bi["nominal"] == 1920.0, "EU-Bill 2026-09-02: settled 09-04, matures 2027-09-03, 1 920 m", fails)
    out = U.de_outstanding_from_csv(os.path.join(hx, "de_outstanding_securities_2026-08-31.csv"))
    cal = U.de_calendar(out)
    check(dict(cal["de_redemptions_gross_ahead"]).get("2026-09-16") == 14000.0 and cal["de_outstanding_total"][0][0] == "2026-08-31", "DE outstanding list 2026-08-31: 14 000 m redeeming 2026-09-16 (gross)", fails)
    fl = U.issuance_flows(de + fr + h + es + eu, days)
    check(len(fl["net_issuance_private_daily"]) == len(days) and all(d <= "2026-09-10" for d, _ in fl["net_issuance_private_daily"]) and dict(fl["settlements_ahead"]).get("2026-09-11") == 1446.18,
          "net issuance dense over business days; Letras settling 2026-09-11 in the calendar, not in the flows", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


def main() -> int:
    if "--ccy" in sys.argv and sys.argv[sys.argv.index("--ccy") + 1] == "eur":
        return main_eur()
    if "--ccy" in sys.argv and sys.argv[sys.argv.index("--ccy") + 1] == "aud":
        return main_aud()
    if "--ccy" in sys.argv and sys.argv[sys.argv.index("--ccy") + 1] == "chf":
        return main_chf()
    if "--ccy" in sys.argv and sys.argv[sys.argv.index("--ccy") + 1] == "gbp":
        return main_gbp()
    if "--ccy" in sys.argv and sys.argv[sys.argv.index("--ccy") + 1] == "nzd":
        return main_nzd()
    fails = []
    days = O.business_days("2025-01-01", "2026-09-10")
    tr = O.term_repo_series(rows("TERM_REPO_RESULTS"), days)
    st = dict(tr["term_repo_outstanding"])
    # B2 weekly "securities purchased under resale agreements" V44201362 on 2026-09-02 = 46 530 (history/cad); operations-based stock must reconcile within 1 %
    b2 = {r[0]: float(r[1]) for r in csv.reader(open(os.path.join(ROOT, "history", "cad", "V44201362.csv"))) if r and r[0] != "date"}
    if "2026-09-02" in b2 and "2026-09-02" in st:
        diff = abs(st["2026-09-02"] - b2["2026-09-02"]) / b2["2026-09-02"]
        check(diff < 0.01, "term repo stock from operations %.0f vs B2 %.0f (diff %.2f%%)" % (st["2026-09-02"], b2["2026-09-02"], diff * 100), fails)
    check(dict(tr["term_repo_settled"]).get("2026-09-03") == 22561.0, "term repos settled 2026-09-03 = 22 561 (indicators table shows 22 561)", fails)
    check(all(d <= "2026-09-10" for d, _ in tr["term_repo_net_daily"]), "no future-dated term repo flows", fails)
    check(tr["term_repo_maturities_ahead"] and all(d > "2026-09-10" for d, _ in tr["term_repo_maturities_ahead"]), "maturity calendar is strictly ahead", fails)
    rg = O.rgam_series(rows("AUC_RGAM_RESULTS"), days)
    check(dict(rg["rg_am_placed"]).get("2026-09-08") == 16500.0, "RG AM placed 2026-09-08 = 10 000 + 6 500 (+ reserves)", fails)
    check(dict(rg["rg_am_matured"]).get("2026-09-09") == -15000.0, "RG AM matured 2026-09-09 = −(10 000 + 5 000)", fails)
    iss = O.issuance_series(rows("AUC_TBILL_RESULTS"), rows("AUC_BOND_RESULTS"), rows("AUC_BOND_S_RESULTS_REPURCHASE"), start="2005-01-01", days=days)
    check(all(d <= "2026-09-10" for d, _ in iss["net_issuance_private_daily"]), "announced auctions excluded from flows", fails)
    check(len(iss["issued_private"]) == len(days), "issuance densified over business days", fails)
    tb = rows("AUC_TBILL_RESULTS")
    one = next(r for r in tb if r["AUC_TBILL_ISSUE_DATE"] == "1998-10-15" and r["AUC_TBILL_TERM_DAYS"] == "98")
    check(abs(float(one["AUC_TBILL_AMOUNT"]) - float(one["AUC_TBILL_BOC_PURCHASE"]) - 2475.0) < 1e-6, "private take = amount − BoC purchase (3 300 − 825)", fails)
    html = '<table><tr><th></th><th>2024-12-12</th><th>2025-01-30</th><th>2025-03-13</th></tr><tr><td>Bank Rate</td><td>3.50</td><td>3.25</td><td>3.00</td></tr></table><table><tr><th></th><th>2026-09-08</th><th>2026-09-09</th><th>2026-09-10</th></tr><tr><td>Target (Available)</td><td></td><td></td><td></td></tr><tr><td>Actual</td><td>65,188</td><td>66,140</td><td></td></tr><tr><td>Term Repos</td><td>0.0</td><td>0.0</td><td>16,000.0</td></tr></table>'
    ind = O.parse_indicators_html(html)
    check(ind["settlement_actual"] == [("2026-09-08", 65188.0), ("2026-09-09", 66140.0)] and ind["ind_term_repos"][-1] == ("2026-09-10", 16000.0), "indicators table parser", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
