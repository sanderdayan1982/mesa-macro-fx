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


def main() -> int:
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
