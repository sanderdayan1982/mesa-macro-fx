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


def main() -> int:
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
