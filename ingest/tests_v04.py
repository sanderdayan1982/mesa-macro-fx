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


def _pdf(path):
    import io
    import pdfplumber  # type: ignore
    with pdfplumber.open(io.BytesIO(open(path, "rb").read())) as p:
        return "\n".join(pg.extract_text() or "" for pg in p.pages)


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
    # seed before the D1A archive: D2.1E (fixtures/gbp_hist) + D1C xls + rule coupons, strictly before the first snapshot
    hx = os.path.join(ROOT, "fixtures", "gbp_hist")
    d21e = G.rows_from_csv(open(os.path.join(hx, "dmo_gilt_issuance_history_D21E_2018.csv"), encoding="utf-8").read())
    d1c = G.parse_d1c_xls(open(os.path.join(hx, "dmo_redeemed_gilts_D1C.xls"), "rb").read())
    snap = ("2026-09-09", {r["name"]: (float(r["amount_in_issue_m"]), r["redemption_date"]) for r in d1a})
    seed, st = G.seed_flows(d21e, d1c, snap, G.business_days(G.SEED_START, "2026-09-08"))
    gi_, cp_, rd_ = dict(seed["gilt_issued_daily"]), dict(seed["coupons_private_paid"]), dict(seed["gilt_redeemed_private"])
    check(st.get("d21e_collateral", 0) == 372 and "2025-04-15" not in gi_ and "2024-07-16" not in gi_, "D2.1E price-N/A rows (NLF→DMA collateral, 62 on 2025-04-15) contribute 0 cash", fails)
    check(gi_.get("2025-01-22") == 8500.0, "syndication 4 3/8% 2040 counted at settlement 2025-01-22 (8 500 nominal, not cash)", fails)
    check(rd_.get("2025-10-22") == 36016.346 and rd_.get("2026-07-22") == 44673.738, "D1C redemption lands on its date (3½% 2025 on 2025-10-22 = 36 016.346, gross)", fails)
    check(cp_ and all(G.next_business_day(d) == d for d in cp_) and G.coupon_dates("2025-06-07", "2025-01-01", "2025-12-31") == ["2025-06-09"], "coupon dates on business days (7-Jun-2025 Saturday → Monday 9-Jun), none after maturity", fails)
    check(seed["net"] and seed["net"][0][0] == "2019-01-01" and seed["net"][-1][0] == "2026-09-08" and all(d < "2026-09-09" for d, _ in seed["gilt_issued_daily"]), "seed spans 2019-01-01 → the day before the first D1A snapshot (2026-09-09)", fails)
    check(dict(G.splice([("a", 1.0), ("c", 2.0)], [("b", 5.0), ("c", 9.0)], "c")) == {"a": 1.0, "c": 9.0}, "splice: seed strictly before the cut, archive path from the cut on", fails)
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
    # two-sided bond flows from every month-end: the fixture register has one month-end (2026-08-31) → add the 15-Apr-2025 line as it stood
    # at 2025-03-31 (market 6 942 = D10 bond maturities Apr-2025) and a 2025-04-30 snapshot without it (matured)
    snaps = bo + [{"month_end": "2025-03-31", "maturity": "2025-04-15", "coupon": 0.0275, "market": 6942.0}] + [dict(b, month_end="2025-04-30") for b in bo]
    bf = N.bond_flows_history(snaps, days)
    check(dict(bf["bond_redeemed_market"]).get("2025-04-15") == 6942.0, "15-Apr-2025 redemption lands on its date with the market nominal of the preceding month-end (6 942)", fails)
    check(bf["two_sided_from"] == "2025-03-31" and all(d >= "2025-03-31" for d, _ in bf["coupons_market_paid"]), "no bond flow before the first month-end on file (two-sided from 2025-03-31, no fabrication)", fails)
    want = sum(b["market"] * b["coupon"] / 2 for b in bo if b["maturity"][5:] == "04-15")
    check(abs(dict(bf["coupons_market_paid"]).get("2026-04-15", 0.0) - want) < 0.01, "coupon 2026-04-15 = Σ market × coupon / 2 of the 15-Apr lines in the latest month-end ≤ that date (%.1f)" % want, fails)
    check(all(N.date.fromisoformat(d).weekday() < 5 for d, _ in bf["coupons_market_paid"] + bf["bond_redeemed_market"]), "coupon and redemption dates fall on business days (rolled forward)", fails)
    mm = sorted({d[5:7] for d, _ in bf["coupons_market_paid"]})
    check(all(any(abs(int(a) - int(b)) in (6,) for b in mm) for a in mm), "coupon months come in semi-annual pairs (m, m+6)", fails)
    # v2: LSAP holding by line + NZDM repurchases (fixtures/nzd_hist raw D3 sheets + every month-end of the register) reconciled to D10 bond maturities
    from . import providers_nzd as PN
    d3 = PN.RbnzD3Provider(fixtures_dir=fx).fetch_d3()
    snaps = PN.NzdmProvider(fixtures_dir=fx).bonds_on_issue_all()
    lsap = N.lsap_holdings_by_line(d3.get("lsap_purchases", []), d3.get("lsap", []), snaps)
    check(not lsap["unmapped"] and "2025-09-20" in lsap["holdings"] and "2023-04-15" in lsap["holdings"], "every LSAP tender label maps to a register line ('Apr 2023' → 2023-04-15, 'Sep 2025' → the IIB 2025-09-20)", fails)
    check(dict(lsap["holdings"]["2023-04-15"]).get("2021-07-12") == 7471.0 and lsap["holdings"]["2023-04-15"][-1] == ("2023-04-15", 0.0), "LSAP 2023-04-15 line peaks at 7 471 (2021-07-12) and is written off at maturity", fails)
    peak = max(sum(N._level_at(st, d) for st in lsap["holdings"].values()) for d in ("2021-07-21", "2021-07-31"))
    check(50000 <= peak <= 54000, "total NZGB LSAP holding peaks ≈ NZ$52 bn in July 2021 (public ~53 bn)", fails)
    days_h = N.business_days("2019-01-01", "2026-09-10")
    bf2 = N.bond_flows_history(snaps, days_h, lsap, d3.get("repurchases", []))
    d10 = N.read_csv_series(os.path.join(ROOT, "history", "nzd", "D10:bond_maturities.csv"))
    rec = {r["month"]: r for r in N.reconcile_redemptions_d10(bf2["bond_redeemed_market"], d10, bf2["bond_repurchased_market"])}
    check(abs(rec["2023-04"]["redeemed"] - 7010) <= 70 and abs(rec["2025-04"]["redeemed"] - 6942) <= 70 and abs(rec["2019-03"]["redeemed"] - 4509) <= 5,
          "redemptions to market vs D10 bond maturities: 2023-04 ≈ 7 010, 2025-04 ≈ 6 942 (±1 %), 2019-03 = 4 509 (repurchases only, pre-LSAP)", fails)
    nominal = [r for k, r in rec.items() if k not in ("2025-09", "2026-05")]  # IIB (indexation) and 2026-05 (D10 = whole register total) explained apart
    check(nominal and all(abs(r["pct"]) <= 10 for r in nominal), "every nominal maturity 2019-03 → 2025-04 within ±10 %% of D10 (%s)" % [(r["month"], r["pct"]) for r in nominal], fails)
    rp2 = dict(bf2["bond_repurchased_market"])
    check(rp2.get("2024-03-04") == 100.0 and all(v > 0 for v in rp2.values()), "repurchases enter as injections (+) on settlement (2024-03-04 = 100)", fails)
    ni2 = N.net_issuance_private([], [], [], ["2024-03-04"], [], bf2["bond_repurchased_market"])
    check(dict(ni2).get("2024-03-04") == 100.0, "net_issuance_private adds repurchases with + sign", fails)
    days_t = N.business_days("2025-01-01", "2026-09-10")
    tfx = N.tender_flows(rows)
    ni = N.net_issuance_private(tfx["tender_settled"], tfx["bill_matured"], bf["coupons_market_paid"], days_t, bf["bond_redeemed_market"])
    lhs = -sum(v for _, v in tfx["tender_settled"] if "2025-01-01" <= _ <= "2026-09-10") + sum(v for _, v in tfx["bill_matured"] if "2025-01-01" <= _ <= "2026-09-10") \
        + sum(v for _, v in bf["bond_redeemed_market"]) + sum(v for _, v in bf["coupons_market_paid"])
    check(abs(sum(v for _, v in ni) - lhs) < 0.01, "identity: Σ net = −tenders settled + bills matured + market redemptions + market coupons over the window", fails)
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
    from . import ops_aud_holdings as AH
    a31 = AH.parse_a31_csv(open(os.path.join(ROOT, "fixtures", "aud_hist", "rba_a3.1_ags_bonds.csv"), encoding="utf-8").read())
    asof, bym = AH.rba_by_maturity(a31)
    check(asof == "2026-08-31" and bym.get("2026-09-21") == 12756.0, "RBA A3.1 2026-08-31: Treasury Bond 164 (21-Sep-2026) held 12 756 $m by line", fails)
    lines = A.face_value_from_csv(os.path.join(ROOT, "fixtures", "aud_hist", "aofm_tb_face_value_by_line.csv"))
    nc = AH.net_tb_calendar(lines, a31, today="2026-09-10")
    check(dict(nc["tb_redemptions_gross_ahead"]).get("2026-09-21") == 39400.0 and dict(nc["tb_redemptions_net_ahead"]).get("2026-09-21") == 26644.0,
          "21-Sep-2026 redemption: gross 39 400 (AOFM face) → net 26 644 to the market (round 2)", fails)
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
    from . import ops_eu_qlik as Q
    from . import ops_esm as ESM
    qr = Q.records_from_fixture_csv(os.path.join(hx, "eu_transactions_qlik_2026-09-10.csv"))
    syn = [r for r in qr if r["source"].endswith(":syndication")]
    first = min(qr, key=lambda r: r["settlement"])
    check(len([r for r in qr if "#noncomp" not in r["source"]]) == 488 and len(syn) == 103 and first["isin"] == "EU000A28X702" and first["settlement"] == "2020-06-10",
          "EU Qlik seed: 488 operations (103 syndications) since 2020-06-03; first syndication settled 2020-06-10 (T+5)", fails)
    dw8 = {r["settlement"]: r["nominal"] for r in qr if r["isin"] == "EU000A3K4DW8" and r["auction"] == "2025-10-20"}
    check(dw8 == {"2025-10-22": 1798.0, "2025-10-23": 300.0} and sum(r["nominal"] for r in qr if r["isin"] == "EU000A3K4DW8" and r["settlement"] <= "2025-10-23") == 15704.0,
          "EU Qlik NCB split: 'Volume issued' 2 098 = 1 798 competitive (T+2) + 300 NCB (T+3), once; Σ legs to 2025-10-23 = 'New o/s amounts' 15 704", fails)
    esm_rows = ESM.parse_esm_transactions_csv(open(os.path.join(hx, "esm", "esm_transactions_outstanding_2026-09-10.csv"), encoding="utf-8").read())
    ann = ESM.parse_esm_announcement(_pdf(os.path.join(hx, "esm", "esm_bill_announcement_2026-08-28.pdf")))
    res = ESM.parse_esm_result(_pdf(os.path.join(hx, "esm", "esm_bill_result_2026-09-01.pdf")))
    rec = ESM.esm_bill_records([ann], [res])[0]
    check(rec["settlement"] == "2026-09-03" and rec["nominal"] == 1599.95 and abs(rec["cash"] - 1599.95 * 0.9937152) < 0.01 and rec["maturity"] == "2026-12-03",
          "ESM 3-month bill 2026-09-01: value date 2026-09-03 from the Bundesbank announcement, 1 599.95 allotted at 99.37152", fails)
    check(len(esm_rows) == 119 and all(r["maturity"] > "2026-09-10" for r in esm_rows if r["maturity"]), "ESM export = 119 outstanding issues (no matured lines)", fails)
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
    # two-sided (DE + EU gross): lines from the issuance history / Qlik operations, redemptions + coupons into the net
    hist = FinanzagenturProvider.parse(open(os.path.join(hx, "emissionshistorie_en.xlsx"), "rb").read())
    dl = U.de_lines(hist, out)
    alive = {o["isin"]: o["nominal"] for o in out if o["nominal"] and "strip" not in o["type"].lower() and "discount" not in o["type"].lower()}
    full = {l["isin"]: sum(n for _, n in l["tranches"]) for l in dl}
    last = {l["isin"]: max(d for d, _ in l["tranches"]) for l in dl}
    diff = [i for i, n in alive.items() if i not in full or (abs(full[i] - n) > 1 and last[i] <= "2026-08-31")]
    check(len(dl) == 285 and len(alive) == 80 and not diff, "DE lines (285): Σ issuance volume per ISIN = einzelaufstellung nominal 2026-08-31 for all 80 alive bond lines (taps after month-end excepted)", fails)
    check("DE0001134922" not in full and full.get("DE0001135085") == 13750.0, "DE pre-1999 lines: matured 6.25 % Bund 2024 dropped (history incomplete, not fabricated); alive 4.75 % Bund 2028 constant at the outstanding-list nominal", fails)
    one = U.bond_redemptions_coupons([l for l in dl if l["isin"] == "DE0001102374"], days, "2026-09-10")
    check(one["bond_redeemed_DE"] == [("2025-02-17", 30500.0)] and one["coupons_paid_DE"] == [("2024-02-15", 152.5), ("2025-02-17", 152.5)],
          "Bund 0.5 % 15-Feb-2025 (DE0001102374): 30 500 m (incl. 2015 tranches) redeemed Monday 2025-02-17 (weekend roll) with the last 152.5 m coupon; 2024-02-15 (Thursday) unrolled", fails)
    one = U.bond_redemptions_coupons([l for l in dl if l["isin"] == "DE000BU2Z049"], days, "2026-09-10")
    check(one["coupons_paid_DE"] == [("2025-02-17", 23.425), ("2026-02-16", 875.0)] and not one["bond_redeemed_all"],
          "Bund 2.5 % 2035 (DE000BU2Z049, created 2025-01-10): first coupon pro-rata 36/365 on 9 500 m, then 875 m on 35 000 m (2026-02-15 Sunday → 02-16); no redemption in the grid", fails)
    ql = Q.eu_lines(qr, Q.outstanding_from_fixture_csv(os.path.join(hx, "eu_outstanding_qlik_2026-09-10.csv")))
    check(len(ql) == 58 and dict(U.bond_redemptions_coupons(ql, days, "2026-09-10")["bond_redeemed_EU"]).get("2025-07-04") == 18014.0,
          "EU lines: 58 bonds; 0.8 % EU 04-Jul-2025 redeemed 18 014 m (Σ NEW + TAP volumes, NCB leg not double counted)", fails)
    fl2 = U.issuance_flows(de + fr + h + es + eu, days, dl + ql)
    parts = [dict(fl2[k]) for k in ("settled_all", "bills_matured_all", "bond_redeemed_all", "coupons_paid_all")]
    ident = [d for d, v in fl2["net_issuance_private_daily"] if abs(v - sum(p.get(d, 0.0) for p in parts)) > 0.01]
    check(not ident and fl2["bond_redeemed_all"] and fl2["coupons_paid_all"], "identity − settled + bills + bond redemptions + coupons = net on every day of the grid", fails)
    # ── FR / IT / ES lines (ops_eur_lines, sources captured 2026-09-11) ──
    from . import ops_eur_lines as L
    import glob as _glob
    fr_hist = U.fr_records_from_xlsx(open(os.path.join(hx, "aft_hist_mlt_2026-09.xlsx"), "rb").read(), None)
    fr_html = h + U.fr_records_from_html(open(os.path.join(hx, "aft_latest_auctions_2026-08.html"), encoding="utf-8").read())
    synd = L.fr_parse_syndications(open(os.path.join(hx, "aft_syndications_1999_2026.xlsx"), "rb").read())
    check(len(fr_hist) == 2299 and fr_hist[0]["settlement"] == "1999-01-14" and len(synd) == 45 and synd[-1] == {"settlement": "2026-04-21", "isin": "FR0014017Z10", "line": "OAT 3,8% 25 juin 2037", "volume": 10000.0}
          and any(s["volume"] < 0 for s in synd), "FR history XLSX 1999→ (2 299 auction rows, first settled 1999-01-14) + 45 syndications (last: 10 000 m Green OAT 2037 on 2026-04-21; buybacks negative)", fails)
    bb = []
    try:
        for fn, exp in (("aft_ops_mensuelles_0726_UK.pdf", ("2026-07", "2026-07-31", 8677.0, 130.0, "OAT 2,50% 24/09/2027", 5665.0, 7)),
                        ("aft_ops_mensuelles_0119_UK.pdf", ("2019-01", "2019-01-31", 1000.0, 0.0, "OAT 3.50% 25 April 2020", 1000.0, 1))):
            p = L.fr_parse_buyback_pdf(_pdf(os.path.join(hx, fn)), fn)
            got = {i["line"]: i["amount"] for i in p["items"]}
            check(p["month"] == exp[0] and p["date"] == exp[1] and p["total"] == exp[2] and p["bills"] == exp[3] and got.get(exp[4]) == exp[5] and len(p["items"]) == exp[6]
                  and abs(sum(got.values()) + p["bills"] - p["total"]) < 0.01,
                  "FR review %s: month %s → dated %s (last business day), OTC total %s = Σ lines + BTF %s; '%s' → %s €m (%d OAT lines)" % ((fn,) + exp), fails)
            bb += [dict(i, date=p["date"], month=p["month"]) for i in p["items"]]
    except ImportError:
        print("skip FR review PDF checks (pdfplumber missing)")
    asof, enc = L.fr_encours_from_csv(os.path.join(hx, "aft_encours_oat_2026-09-11.csv"))
    frl, recon = L.fr_lines(fr_hist + fr_html, synd, bb, enc, asof)
    t20 = dict(next(l for l in frl if l["isin"] == "FR0010854182")["tranches"])
    t27 = dict(next(l for l in frl if l["isin"] == "FR001400NBC6")["tranches"])
    check(bb == [] or (t20.get("2019-01-31") == -1000.0 and t27.get("2026-07-31") == -5665.0), "FR buybacks mapped by coupon + maturity: 2019 format → FR0010854182 −1 000 m on 2019-01-31; 2026 format → FR001400NBC6 −5 665 m on 2026-07-31", fails)
    print("FR reconciliation vs AFT outstanding list %s: %d/%d alive lines within ±1 %%, %d pre-1999 line snapped, %d buyback months in the archive" % (asof, recon["matched"], recon["alive"], recon["snapped"], len(recon["buyback_months"])))
    for r in recon["rows"][:8]:
        print("   %s list %10.1f calc %10.1f diff %9.1f (%s %%)" % r)
    strict = len(recon["buyback_months"]) >= 24  # runner: the review archive is complete → every alive line must reconcile; offline: two reviews only
    check(recon["alive"] == 59 and not recon["unmapped_buybacks"] and recon["snapped"] == 1 and (recon["matched"] == recon["alive"] if strict else recon["matched"] >= 45),
          "FR lines reconcile to the AFT list (%s): 43 lines to the euro from auctions + syndications alone; the rest are bought-back lines (buyback archive: %d months locally, tolerant) + OAT 5.5 %% 2029 (pre-1999, snapped)" % ("strict" if strict else "tolerant", len(recon["buyback_months"])), fails)
    snaps = [L.it_parse_scadenze(open(f, encoding="utf-8").read()) for f in sorted(_glob.glob(os.path.join(hx, "mef_scadenze", "scadenze_*.csv")))]
    itl, iti = L.it_lines(snaps)
    check([s[0] for s in snaps] == ["2020-12-31", "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31", "2026-08-31"] and all(len(s[1]) >= 239 for s in snaps) and iti["excluded"].get("BOT", 0) == 252,
          "IT scadenze snapshots: 7 files (2020-12-31 … 2026-08-31), ≥ 239 market-held rows each (repo-portfolio section cut), BOT rows excluded (bills via the auction records)", fails)
    b25 = U.bond_redemptions_coupons([l for l in itl if l["isin"] == "IT0004513641"], days, "2026-09-10")
    check(dict(b25["bond_redeemed_IT"]) == {"2025-03-03": 23403.793} and dict(b25["coupons_paid_IT"]).get("2024-09-02") == round(24718.669 * 0.025, 3) and dict(b25["coupons_paid_IT"]).get("2025-03-03") == round(23403.793 * 0.025, 3),
          "BTP 5 % 01-Mar-2025 (IT0004513641): 23 403.793 m redeemed Monday 2025-03-03 (2025 file, weekend roll); semi-annual 2.5 % coupons on 1 Mar / 1 Sep — Sep-2024 on the 2023 snapshot (24 718.669), Mar-2025 on the 2024 one (1 314.876 bought back in 2024)", fails)
    l30 = next(l for l in itl if l["isin"] == "IT0005024234")
    check(l30["coupon_months"] == 6 and l30["tranches"][0] == ("2014-03-01", 25156.449) and ("2022-12-31", 1250.0) in l30["tranches"] and sum(n for _, n in l30["tranches"]) == 28206.449,
          "BTP 3.5 % 2030 (IT0005024234): first tranche at the issue date with the 2020 nominal, later snapshots as deltas (28 206.449 today; the 1 000 m repo-portfolio tranche excluded)", fails)
    lv = next(l for l in itl if l["isin"] == "IT0005547390")
    cct = [l for l in itl if l["isin"] == "IT0005451361"]
    check(lv["coupon_months"] == 3 and lv["coupon"] == 3.25 and cct and cct[0]["coupon"] == 0.0 and cct[0]["maturity"] == "2029-04-15", "BTP Valore Jun-2027 quarterly on the first step (3.25 %); CCTeu Apr-2029 kept for the redemption, no coupon (spread field)", fails)
    from .providers_chf import xlsx_sheets, _rows_of
    blob = open(os.path.join(hx, "tesoro_13_financiacion_neta.xlsx"), "rb").read()
    am = L.es_parse_financiacion(blob, "2026-09")
    tot25 = None
    for cells in xlsx_sheets(blob).values():
        rows_ = _rows_of(cells)
        if any("2025" in str(v) for v in rows_[min(rows_)].values()) and any("acumulados" not in str(v).lower() and "(importes efectivos)" in str(v).lower() for r in sorted(rows_)[:3] for v in rows_[r].values()):
            tr = next(r for r in sorted(rows_) if str(rows_[r].get("B", "")).strip().upper().startswith("TOTAL A"))
            tot25 = sum(U._num(rows_[tr].get(c)) or 0.0 for c in ("P", "Q", "R"))  # AMORTIZACIONES: Bonos, Oblig., Bonos y Oblig. Index.
    s25 = sum(r["bonos"] + r["oblig"] + r["index"] for r in am if r["year"] == 2025)
    check(tot25 is not None and abs(s25 - tot25) < 0.01 and abs(tot25 - (41115.12 + 72461.78)) < 0.01 and len([r for r in am if r["year"] == 2025]) == 5,
          "ES 13.xlsx 2025: Σ monthly Bonos + Oblig. + Index. = TOTAL AÑO %.2f (41 115.12 + 72 461.78 + Index. empty; 'Resto y asumidas' excluded); 5 months with bond redemptions" % (tot25 or 0), fails)
    esl, esi = L.es_lines(am, es)
    check(dict((l["maturity"], l["tranches"][0][1]) for l in esl).get("2026-07-30") == 24608.597 and esi["from"] == "2025-01" and esi["to"] == "2026-07" and esi["skipped_coupon_maturities"] > 0,
          "ES daily row 30-Jul-2026 → 24 608.6 m on the day; coverage 2025-01 → 2026-07; coupons not derived (%d maturities without a known nominal)" % esi["skipped_coupon_maturities"], fails)
    for l in itl:
        l["from"] = "2024-01-01"
    fl3 = U.issuance_flows(de + fr + h + es + eu, days, dl + ql + frl + itl + esl)
    parts = [dict(fl3[k]) for k in ("settled_all", "bills_matured_all", "bond_redeemed_all", "coupons_paid_all")]
    ident = [d for d, v in fl3["net_issuance_private_daily"] if abs(v - sum(p.get(d, 0.0) for p in parts)) > 0.01]
    check(not ident and all(fl3.get("bond_redeemed_%s" % i) for i in ("DE", "EU", "FR", "IT", "ES")) and all(fl3.get("coupons_paid_%s" % i) for i in ("DE", "EU", "FR", "IT")) and "coupons_paid_ES" not in fl3,
          "identity holds with the five issuers' lines; redemptions DE/EU/FR/IT/ES and coupons DE/EU/FR/IT in the flow, no ES coupons", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0



def main_jpy() -> int:
    """JPY: the daily file's three columns, operations by operation (face) vs the cash line, mei ↔ MoF issue map, net redemptions."""
    from . import ops_jpy as J
    fails = []
    hx = os.path.join(ROOT, "fixtures", "jpy_hist")
    rd = lambda fn: open(os.path.join(hx, fn), "rb").read()
    jd = J.parse_daily_file(rd("jd20260909.xlsx"), "jd20260909.xlsx")
    check(jd["date"] == "2026-09-09" and jd["proj"]["treasury"] == -33600 and jd["prov"]["treasury"] == -35900 and jd["final"]["treasury"] == -35900,
          "jd 2026-09-09 keeps the three columns: treasury 予想 −33 600 / 速報 −35 900 / 確報 −35 900 (revision 2 300)", fails)
    check(jd["final"]["cab"] == 4116600 and jd["final"]["reserve_bal"] == 3811200, "jd stocks: 当座預金残高 4 116 600, 準備預金残高 3 811 200 (100m)", fails)
    jp = J.parse_daily_file(rd("jp20260911.xlsx"), "jp20260911.xlsx")
    check(jp["date"] == "2026-09-11" and jp["proj"]["treasury"] == -10400 and jp["prov"].get("treasury") is None, "jp 2026-09-11: projection only (−10 400), no provisional/final", fails)
    import tempfile
    _ap = tempfile.mktemp(suffix=".csv")
    _rows = J.merge_daily_archive(_ap, [jd, jp])
    _w = J.daily_records_to_wide(_rows)
    check(_w["proj"].get("treasury", [])[-1:] == [("2026-09-11", -10400.0)] and _w["prov"].get("treasury", [])[-1:] == [("2026-09-09", -35900.0)],
          "runner path: flat archive rows (merge/read_daily_archive) → wide keeps proj/prov/final (2026-09-11 the flat rows were ignored → projection unavailable in production)", fails)
    jx = J.parse_daily_file(rd("jx20260910.xlsx"), "jx20260910.xlsx")
    check(jx["prov"]["jgb_purch"] == 7200 and jx["proj"]["treasury"] == 2200 and jx["prov"]["treasury"] == 3400, "jx 2026-09-10: 国債買入 cash 7 200; treasury surprise 3 400 − 2 200", fails)
    ops = J.parse_ope_file(rd("ope20260909.xlsx"), "ope20260909.xlsx")
    jg = [o for o in ops if o["kind"] == "jgb_purch"]
    check(len(jg) == 3 and round(sum(o["allotted"] for o in jg)) == 7659 and all(o["start"] == "2026-09-10" for o in jg), "ope 2026-09-09: 3 outright JGB purchases, face 7 659, Date of Exercise 09-10 (T+1)", fails)
    days = J.business_days("2026-08-01", "2026-09-10")
    fl = J.ops_flows(ops + J.parse_ope_file(rd("ope20260910.xlsx"), "ope20260910.xlsx"), {"jgb_purch": [("2026-09-10", 7200.0)]}, days, today="2026-09-10")
    check(dict(fl["jgb_purch_settled"]).get("2026-09-10") == 7659.0 and dict(fl["jgb_purch_face_minus_cash"]).get("2026-09-10") == 459.0, "face 7 659 vs cash 7 200 on the settlement date → reconciliation 459 (the reserve flow is the cash)", fails)
    q = J.parse_juqp(rd("juqp2609.xlsx"))
    check(q["month"] == "2026-09" and q["treasury"] == -76100 and q["jgb_net"] == -62500 and q["tbill_net"] == 36700 and q["other"] == -50300 and q["published"] == "2026-09-03",
          "juqp September 2026: 財政等要因 −76 100 = 国債等 −62 500 + 国庫短期証券等 36 700 + その他 −50 300; published 09-03", fails)
    check(q["shortage_days"] == ["2026-09-01", "2026-09-02", "2026-09-09", "2026-09-11", "2026-09-29"] and q["surplus_days"] == ["2026-09-24"], "juqp days with large shortage / surplus", fails)
    mei = J.parse_mei(rd("mei260831.xlsx"), "mei260831.xlsx")
    jgb = J.parse_mof_jgb_xls(os.path.join(hx, "mof_auction_results_jgbs.xls"))
    tb = J.parse_mof_tbill_xls(os.path.join(hx, "mof_auction_results_tbills.xls"))
    imap = J.issue_map(jgb)
    bm = J.mei_to_maturity(mei, imap)
    unm = bm.pop("_unmapped")
    tot = sum(r["amount"] for r in mei["rows"])
    check(mei["asof"] == "2026-08-31" and abs(sum(bm.values()) + sum(x[2] for x in unm) - tot) < 1 and len(unm) <= 2,
          "mei 2026-08-31: %d issues, %.0f (100m) mapped to maturities via the MoF XLS; unmapped %s" % (len(mei["rows"]), sum(bm.values()), unm), fails)
    cl = J.coupon_lines(imap, mei)
    cut = max(r["issue"] for r in jgb + tb if r.get("issue"))
    ni = J.net_issuance(jgb, tb, bm, cl, [d for d in J.business_days("2024-01-01", cut)], today=cut)
    ah0 = J.net_issuance(jgb, tb, bm, cl, [], today="2026-09-10")
    g = dict(ah0["jgb_redemptions_gross_ahead"]); n = dict(ah0["jgb_redemptions_net_ahead"])
    held = [d for d in g if d in bm and bm[d] > 0]
    check(held and all(n[d] < g[d] for d in held) and all(abs(g[d] - n[d] - min(bm[d], g[d])) < 1 for d in held),
          "JGB redemptions ahead: net = gross − BoJ holding of the maturity (%d held maturities in the next 12 months; past redemptions need the mei archive)" % len(held), fails)
    check(len(ni["net_issuance_private_daily"]) == len(J.business_days("2024-01-01", cut)), "net issuance dense over business days up to the MoF cut (%s)" % cut, fails)
    ah = J.net_issuance(jgb, tb, bm, cl, [], today="2026-09-10")
    check(all(d > "2026-09-10" for d, _ in ah["jgb_redemptions_net_ahead"]) and ah["jgb_redemptions_net_ahead"], "redemption calendar strictly ahead", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


def main_activation() -> int:
    """activation v0.4 (2026-09-11): live print = replay print; the fixture-run JSONs read engine 0.4 on the approved blocks; revert restores v0.3"""
    import json
    from datetime import date, timedelta
    from . import v04_component as V
    from . import replay_v04 as R
    from . import engine as E
    from . import apply_v04 as A
    fails = []
    # 1 · value_asof parity with replay_v04 on a synthetic business-day series (gaps, holidays, lags 0/1/2/7)
    ser, d = [], date(2026, 6, 1)
    while d <= date(2026, 9, 10):
        if d.weekday() < 5 and d != date(2026, 8, 3):
            ser.append((d.isoformat(), float(((d.day * 7) % 11) - 5)))
        d += timedelta(days=1)
    wk = [(x, v) for x, v in ser if date.fromisoformat(x).weekday() == 4]
    n = 0
    for k in range(0, 110):
        dd = (date(2026, 5, 25) + timedelta(days=k)).isoformat()
        for lag in (0, 1, 2, 7, 35):
            n += 1
            if V.value_asof(ser, dd, "daily5", lag) != R._value_asof(ser, dd, "daily5", lag) or V.value_asof(wk, dd, "weekly", lag) != R._value_asof(wk, dd, "weekly", lag):
                fails.append("value_asof parity %s lag %d" % (dd, lag))
    check(not [f for f in fails if f.startswith("value_asof")], "value_asof daily5/weekly = replay_v04._value_asof on %d as-of/lag pairs" % n, fails)
    check(V.value_asof(ser, "2026-09-10", "daily5", 0) == sum(v for _, v in ser[-5:]), "daily5 = sum of the last 5 sessions ≤ cutoff", fails)
    check(V.value_asof(wk, "2026-09-11", "weekly", 7) == wk[-1][1] and V.value_asof(wk, "2026-09-25", "weekly", 7) is None, "weekly step: latest value ≤ cutoff, stale after 10 days", fails)
    # 2 · classify_regime on the fixture-run JSONs: approved blocks read engine 0.4 with the v0.3 shadow beside them
    for ccy, blocks_ok in A.APPROVED.items():
        cfg = json.load(open(os.path.join(ROOT, "config", "%s.json" % ccy), encoding="utf-8"))
        dd = os.path.join(ROOT, "data", ccy)
        blocks = {b: json.load(open(os.path.join(dd, "%s.json" % b), encoding="utf-8")) for b in ("central_bank", "fiscal", "banking", "rates") if os.path.exists(os.path.join(dd, "%s.json" % b))}
        check(cfg["regime"]["dual"].get("version") == "0.4" and set(cfg["regime"]["dual"].get("v04", {})) == set(blocks_ok), "%s config: dual.version 0.4 on %s" % (ccy, sorted(blocks_ok)), fails)
        reg = E.classify_regime(cfg, blocks, None, hist_dir=os.path.join(ROOT, "history", ccy))
        for b in ("central_bank", "fiscal"):
            r = reg["regimes"][b]
            if b in blocks_ok:
                comp = r.get("component") or {}
                ok = r.get("engine") == "0.4" and "v03_shadow" in r and r["v03_shadow"].get("regime") in E_BLOCK_ENUM and comp.get("name") == cfg["regime"]["dual"]["v04"][b]["component"]["name"] \
                    and r.get("cuts") == cfg["regime"]["dual"]["v04"][b]["cuts"] and r["state"].get("engine") == "0.4"
                if r["score"] is None:
                    # a component not known as of today reads NO SIGNAL with the reason (never the v0.3 score under v0.4 cuts); CHF fx_proxy_w
                    # is archived only for the weeks the monthly gmges amounts cover (~35 d after month-end) → structurally late vs lag 7 d
                    ok = ok and r["regime"] == "NO SIGNAL" and bool((r.get("print") or {}).get("note"))
                    print("note %s %s: v0.4 print unavailable — %s" % (ccy, b, r["print"]["note"]))
                else:
                    ok = ok and isinstance(r["score"], float) and r["regime"] in ("INJECTION", "DRAIN", "NEUTRAL") and abs(r["score"] - round(r["print"]["raw"] / r["print"]["denominator"] * 100, 4)) < 1e-9
                check(ok, "%s %s: engine 0.4 · %s = %s → %s (v0.3 shadow %s %s)" % (ccy, b, comp.get("name"), r["score"], r["regime"], r["v03_shadow"].get("regime"), r["v03_shadow"].get("score")), fails)
                check(blocks[b]["signals"]["score"] == r["v03_shadow"]["score"], "%s %s: signals.score untouched (v0.3 published)" % (ccy, b), fails)
            else:
                check(r.get("engine") is None and "v03_shadow" not in r and r["score"] == blocks[b]["signals"]["score"], "%s %s: stays v0.3" % (ccy, b), fails)
        check(reg["regimes"]["general"]["engine"] == "0.3" and set(reg["regimes"]["general"]["v04_blocks"]) == set(blocks_ok), "%s general: agreement rule unchanged, v04_blocks %s" % (ccy, sorted(blocks_ok)), fails)
        # first v0.4 run starts from confirmed NEUTRAL even when the previous regime.json carries a v0.3 state on another side
        b0 = next((b for b in sorted(blocks_ok) if reg["regimes"][b]["score"] is not None), None)
        if b0:
            d0 = (date.fromisoformat(min(reg["regimes"][b0]["as_of"], reg["regimes"][b0]["v03_shadow"]["as_of"])) - timedelta(days=1)).isoformat()
            prev = {"regimes": {b0: {"state": {"confirmed": "INJECTION", "recent": [[d0, 1e6]]}, "as_of": d0}}}  # a v0.3 state (no engine tag)
            reg2 = E.classify_regime(cfg, blocks, prev, hist_dir=os.path.join(ROOT, "history", ccy))
            r2 = reg2["regimes"][b0]
            check([list(x) for x in r2["state"]["recent"]] == [[reg["regimes"][b0]["as_of"], r2["score"]]] and r2["regime"] == reg["regimes"][b0]["regime"] and 1e6 in [v for _, v in r2["v03_shadow"]["state"]["recent"]],
                  "%s %s: a v0.3 state is not carried into the v0.4 hysteresis (first v0.4 run starts from NEUTRAL); the shadow continues it" % (ccy, b0), fails)
            reg3 = E.classify_regime(cfg, blocks, reg2, hist_dir=os.path.join(ROOT, "history", ccy))
            check([list(x) for x in reg3["regimes"][b0]["state"]["recent"]] == [list(x) for x in r2["state"]["recent"]] and reg3["regimes"][b0]["state"].get("engine") == "0.4", "%s %s: the v0.4 state continues from a v0.4 regime.json" % (ccy, b0), fails)
        # without hist_dir the daily5/weekly prints are skipped with a note (dweekly needs no archive)
        reg3 = E.classify_regime(cfg, blocks, None)
        for b in blocks_ok:
            r3 = reg3["regimes"][b]
            if cfg["regime"]["dual"]["v04"][b]["component"]["kind"] != "dweekly":
                check(r3["score"] is None and "history dir" in (r3["print"]["note"] or ""), "%s %s: no hist_dir → skipped with a note" % (ccy, b), fails)
    # 3 · revert restores dual.version 0.3 (round trip on the file, restored byte for byte afterwards)
    cp = os.path.join(ROOT, "config", "cad.json")
    raw = open(cp, encoding="utf-8").read()
    try:
        A.apply("cad", revert=True)
        c2 = json.load(open(cp, encoding="utf-8"))
        check(c2["regime"]["dual"].get("version") == "0.3" and "v04" not in c2["regime"]["dual"] and "dual_v03" not in c2["regime"], "cad --revert: dual.version 0.3, v04 gone", fails)
        check(c2["regime"]["dual"]["block_thresholds"]["fiscal"]["injection_enter"] == 0.55, "cad --revert: v0.3 fiscal cuts back", fails)
    finally:
        open(cp, "w", encoding="utf-8").write(raw)
    check(open(cp, encoding="utf-8").read() == raw, "cad config restored after the revert test", fails)
    # ledger as-of regression (JPY 2026-09-11: v0.3 run wrote (09-11, DRAIN), v0.4 printed NEUTRAL as-of 09-10 → gate A3 1 vs 2)
    from .narrative import update_ledger
    prev = {"ledger": {"fiscal": [["2026-09-07", "INJECTION"], ["2026-09-10", "DRAIN"], ["2026-09-11", "DRAIN"]]}}
    reg = {"as_of": "2026-09-10", "regimes": {"fiscal": {"as_of": "2026-09-10", "regime": "NEUTRAL"}, "central_bank": {"as_of": "2026-09-10", "regime": "NEUTRAL"}, "general": {"regime": "NEUTRAL"}}}
    led, st = update_ledger(prev, reg, {})
    check(led["fiscal"] == [["2026-09-07", "INJECTION"], ["2026-09-10", "NEUTRAL"]] and st["fiscal"] == 1, "ledger: an as-of regression drops the later entry and the streak equals the ledger run (gate A3)", fails)
    main_jefe_v2(fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


def main_jefe_v2(fails: list) -> None:
    """jefe de mesa v2: the pure-python Φ⁻¹ against scipy (when installed), the era-percentile convention against
    conviction.asof_percentile (numpy/scipy path, when installed), the label rule, and a consistent published jefe.json."""
    import json
    from . import jefe as J
    ps = [1e-12, 1e-6, 0.001, 0.01, 0.02425, 0.05, 0.1, 0.3, 0.5, 0.7, 0.9, 0.95, 0.97575, 0.99, 0.999, 1 - 1e-6, 1 - 1e-12]
    try:
        from scipy.stats import norm  # type: ignore
        err = max(abs(J.norm_ppf(p) - float(norm.ppf(p))) for p in ps)
        check(err < 1e-9, "jefe.norm_ppf vs scipy.stats.norm.ppf: max abs error %.2e over %d points" % (err, len(ps)), fails)
    except ImportError:
        check(abs(J.norm_ppf(0.5)) < 1e-12 and abs(J.norm_ppf(0.975) - 1.959963984540054) < 1e-9 and abs(J.norm_ppf(0.001) + 3.090232306167813) < 1e-9,
              "jefe.norm_ppf against tabulated quantiles (scipy not installed)", fails)
    grid = J._fridays("2020-01-03", "2022-12-30")
    import random
    rnd = random.Random(3)
    ser = [(g, round(rnd.uniform(-2, 2), 1)) for g in grid]   # 1-dp values → ties, as in the block score
    mine = J.asof_era_percentile(dict(ser), "2020-06-01", grid)
    try:
        from . import conviction as C  # numpy/scipy
        ref = C.asof_percentile(ser, "2020-06-01", grid)
        pairs = [(mine[g], ref[g]) for g in grid]
        same_none = all((a is None) == (b is None) for a, b in pairs)
        err = max((abs(a - b) for a, b in pairs if a is not None), default=0.0)
        check(same_none and err < 1e-9, "jefe.asof_era_percentile = conviction.asof_percentile ((r−0.5)/N, min 26, clip ±2.5): max abs diff %.2e" % err, fails)
    except ImportError:
        check(mine[grid[0]] is None and any(v is not None for v in mine.values()), "jefe.asof_era_percentile runs (conviction path not importable)", fails)
    L = J.plumbing_label
    check(L(1, 8, 4, 8, False) == "abundante" and L(5, 8, 2, 8, True) == "abundante", "label: a top tercile and no bottom → abundante (gate irrelevant)", fails)
    check(L(8, 8, 4, 8, False) == "escasa" and L(8, 8, 4, 8, True) == "vulnerable" and L(4, 8, 7, 8, True) == "vulnerable", "label: a bottom tercile and no top → escasa; with the price gate → vulnerable", fails)
    check(L(1, 8, 8, 8, True) == "sin señal" and L(None, 8, 1, 8, False) == "sin señal" and L(4, 8, 5, 8, True) == "sin señal", "label: opposite terciles, a missing ranking or both mid → sin señal", fails)
    check(J._tercile(3, 8) == "top" and J._tercile(4, 8) == "mid" and J._tercile(6, 8) == "bottom" and J._tercile(2, 5) == "top" and J._tercile(3, 5) == "mid", "terciles: top size = ceil(n/3)", fails)
    p = os.path.join(ROOT, "data", "mesa", "jefe.json")
    if os.path.exists(p):
        j = json.load(open(p, encoding="utf-8"))
        T = j.get("treasury") or {}
        ok = T.get("status") == "ok" and [r["rank"] for r in T["ranking"]] == list(range(1, T["n"] + 1)) and all(r["z"] >= r2["z"] for r, r2 in zip(T["ranking"], T["ranking"][1:])) \
            and abs(sum(r["z"] for r in T["ranking"])) < 0.05 * T["n"] and set(j.get("labels", {}).values()) <= set(J.LABELS) and j.get("stamp") == J.stamp(j) and len(j.get("stamp", "")) == 12 and bool(j.get("generated_at")) and (not j.get("low_dispersion") or set(j["labels"].values()) == {J.COMPRESSED}) and set((j.get("completeness") or {}).keys()) == set(J.NAMES.values()) and all(v["treasury"]["truth"] == "proxy" for k, v in j["completeness"].items() if k.lower() in J.PROXY) and len((j.get("evidence") or {}).get("tests", [])) >= 5 and any(t["id"] == "H2" for t in j["evidence"]["tests"]) and j.get("numeraire") and (j.get("live_tracking") or {}).get("started") == J.LIVE_TRACKING_START and (j.get("treasury") or {}).get("clock_note") and all(r.get("object") and r.get("as_of") for r in j["ranking"]) and j.get("pair_max_z_gap") is not None and all(r["proxy"] == (r["ccy"].lower() in J.PROXY) for r in T["ranking"])
        check(ok, "data/mesa/jefe.json: treasury ranking ordered by Z, demeaned, proxy flags, labels in the enum, stamp recomputable, compression withholds labels, completeness for the eight (proxy legs marked), evidence published incl. H2, numeraire, live_tracking, clock_note", fails)
    # round 2 (institutionality): required scenario conditions — «min of n» never substitutes the price/fiscal condition
    from . import engine as EN
    cfg_t = {"scenarios": {"items": [{"id": "T", "name": "t", "bias": "RESERVE SCARCITY", "min": 2, "required": ["rates.x level >= WATCH"],
                                      "conditions": ["central_bank.a level >= WATCH", "central_bank.b level >= WATCH", "rates.x level >= WATCH"]}]}}
    blk = {"central_bank": {"series": {}, "derived": {"a": {"level": "WATCH"}, "b": {"level": "WATCH"}}}, "rates": {"series": {}, "derived": {"x": {"level": "SAFE"}}}}
    r1 = EN.evaluate_scenarios(cfg_t, blk)[0]
    blk["rates"]["derived"]["x"]["level"] = "WATCH"
    r2 = EN.evaluate_scenarios(cfg_t, blk)[0]
    blk["rates"]["derived"] = {}
    r3 = EN.evaluate_scenarios(cfg_t, blk)[0]
    check(r1["conditions_met"] == 2 and not r1["active"] and not r1["required_met"] and r2["active"] and r2["required_met"] and not r3["active"] and r3["unknown"] == 1,
          "scenarios: 2 of 3 without the required condition does not activate; with it, it does; null required → unknown, inactive", fails)
    cfg_f = {"scenarios": {"items": [{"id": "F", "name": "f", "bias": "FISCAL INJECTION", "min": 2, "required": ["regime.fiscal == INJECTION"],
                                      "conditions": ["regime.fiscal == INJECTION", "central_bank.a level >= WATCH", "central_bank.b level >= WATCH"]}]}}
    blk_f = {"central_bank": {"series": {}, "derived": {"a": {"level": "WATCH"}, "b": {"level": "WATCH"}}}}
    f1 = EN.evaluate_scenarios(cfg_f, blk_f, {"regimes": {"fiscal": {"regime": "NEUTRAL"}}})[0]
    f2 = EN.evaluate_scenarios(cfg_f, blk_f, {"regimes": {"fiscal": {"regime": "INJECTION"}}})[0]
    f3 = EN.evaluate_scenarios(cfg_f, blk_f, None)[0]
    check(not f1["active"] and f2["active"] and not f3["active"] and f3["unknown"] == 1, "scenarios: fiscal scenarios require the CONFIRMED fiscal regime (regime.fiscal), not the block heuristic", fails)
    import re as _re
    for c in ("usd", "eur", "gbp", "jpy", "chf", "cad", "aud", "nzd"):
        items = json.load(open(os.path.join(ROOT, "config", "%s.json" % c), encoding="utf-8"))["scenarios"]["items"]
        check(not any(_re.search(r"RISK|BULL|BEAR|DEFENSIVE|CONSTRUCTIVE|CAUTION|SUPPORTIVE", it["bias"]) for it in items) and all(all(r in it["conditions"] for r in it.get("required", [])) for it in items),
              "config %s: scenario biases are liquidity states and every required condition exists in its scenario" % c.upper(), fails)
    for c in ("usd", "eur"):  # lote blotter: the canonical state is explicit in the JSON (confirmed == regime, canonical = "confirmed")
        rp = os.path.join(ROOT, "data", c, "regime.json")
        if os.path.exists(rp):
            rg = json.load(open(rp, encoding="utf-8"))["regimes"]
            check(all(rg[b].get("confirmed") == rg[b].get("regime") and rg[b].get("canonical") == "confirmed" for b in ("central_bank", "fiscal", "general")),
                  "regime.json %s: confirmed == regime and canonical = confirmed on the three regimes" % c.upper(), fails)
    from . import regime_changelog as RC
    for c in ("usd", "eur", "nzd"):
        r = RC.build(c)
        check(r.get("status") == "ok" and set(r["blocks"]) == {"central_bank", "fiscal", "general"} and all(b["current"] and b["since"] and b["weeks_in_current"] >= 1 for b in r["blocks"].values())
              and all(len(b["transitions"]) <= 12 for b in r["blocks"].values()) and r["blocks"]["central_bank"]["cuts_v03"] is not None,
              "regime_changelog %s: reconstructed from the v0.3 replay with current spell, ≤ 12 transitions per block and the v0.3 cuts" % c.upper(), fails)


E_BLOCK_ENUM = {"INJECTION", "DRAIN", "NEUTRAL", "NO SIGNAL"}


def main() -> int:
    if "--ccy" in sys.argv and sys.argv[sys.argv.index("--ccy") + 1] == "activation":
        return main_activation()
    if "--ccy" in sys.argv and sys.argv[sys.argv.index("--ccy") + 1] == "jpy":
        return main_jpy()
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
    from . import ops_cad_holdings as H
    hold = H.parse_boc_holdings_html(open(os.path.join(FIX, "boc_holdings_2026-09-10.html"), encoding="utf-8").read())
    outs = H.goc_outstanding_from_csv(os.path.join(FIX, "GOC_OUTSTANDING_latest.csv"))
    nc = H.net_calendar(outs, hold, today="2026-09-10")
    sb = dict(nc["boc_share_bonds"]); ha = nc["holdings_asof"][-1][0]
    check(ha == "2026-09-10" and 0.10 < sb.get(ha, 0) < 0.13, "BoC holdings 2026-09-10 by ISIN: bonds share %.4f of GOC_OUTSTANDING nominal (round 2 netting)" % sb.get(ha, 0), fails)
    g = dict(nc["bond_redemptions_gross_ahead"]); n = dict(nc["bond_redemptions_net_ahead"])
    check(all(n[d] <= g[d] + 1e-6 for d in g) and any(n[d] < g[d] for d in g), "net redemptions ≤ gross and strictly lower where the BoC holds the line", fails)
    check(dict(nc["bond_coupons_net_ahead"]).get("2026-11-01", 0) > 0 and n.get("2026-11-01") == 11787.128, "CA135087S398 2026-11-01: not held by the BoC → private = outstanding 11 787.128; coupon on the same day", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
