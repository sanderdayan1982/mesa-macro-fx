"""EU (Qlik dashboard) + ESM/EFSF self-checks (run: python3 -m ingest.tests_eu_esm). No pytest; exits 1 on failure.
Reconciliations against the fixtures of 2026-09-10 (fixtures/eur_hist/eu_*_qlik_2026-09-10.csv, fixtures/eur_hist/esm/*)."""
from __future__ import annotations
import os
import sys
from collections import Counter
from datetime import date
from . import ops_eu_qlik as Q
from . import ops_esm as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HX = os.path.join(ROOT, "fixtures", "eur_hist")
ESM = os.path.join(HX, "esm")


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def _pdf_text(path: str) -> str:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def main() -> int:
    fails = []
    today = date(2026, 9, 10)
    # ── EU transactions ──
    f, rows = Q.csv_to_rows(open(os.path.join(HX, "eu_transactions_qlik_2026-09-10.csv"), encoding="utf-8").read())
    check(len(rows) == 2633 and f == Q.TX_FIELDS, "transactions fixture: 2 633 raw rows, expected field list", fails)
    check(Q.csv_to_rows(Q.rows_to_csv(f, rows)) == (f, rows), "rows_to_csv / csv_to_rows round-trip", fails)
    recs = Q.transactions_from_rows(f, rows)
    main_recs = [r for r in recs if not r["source"].endswith("#noncomp")]
    ncb = [r for r in recs if r["source"].endswith("#noncomp")]
    fmt = Counter(r["source"].rsplit(":", 1)[-1] for r in main_recs)
    print("     transactions: %d records (%d main + %d NCB legs): %s" % (len(recs), len(main_recs), len(ncb), dict(fmt)))
    check(fmt.get("syndication") == 103 and fmt.get("auction") == 385, "103 syndication + 385 auction transaction rows", fails)
    check(len(recs) == len({tuple(str(r[c]) for c in Q.REC_COLS) for r in recs}), "records de-duplicated", fails)
    check(all(r["kind"] in ("bill", "bond") and r["issuer"] == "EU" and r["nominal"] > 0 for r in recs), "every record issuer EU, kind bill|bond, nominal > 0", fails)
    lag = lambda r: (date.fromisoformat(r["settlement"]) - date.fromisoformat(r["auction"])).days
    for k in ("auction", "syndication"):
        dist = Counter(lag(r) for r in main_recs if r["source"].endswith(":" + k) and r["settlement"])
        print("     settlement lag (%s, calendar days): %s" % (k, dict(sorted(dist.items()))))
        mode = dist.most_common(1)[0][0] if dist else None
        check(mode == (2 if k == "auction" else 7), "%s: most common settlement lag = %d days" % (k, 2 if k == "auction" else 7), fails)
    ncb_lag = Counter(lag(r) for r in ncb)
    print("     NCB leg lag: %s; bills %d, bonds %d" % (dict(sorted(ncb_lag.items())), sum(r["kind"] == "bill" for r in recs), sum(r["kind"] == "bond" for r in recs)))
    r0 = recs[0]
    check(r0["isin"] == "EU000A28X702" and r0["settlement"] == "2020-06-10" and r0["auction"] == "2020-06-03" and r0["nominal"] == 500.0, "first record EU000A28X702 03-06-2020 → settles 2020-06-10, 500 m", fails)
    check(all(r["cash"] == r["nominal"] for r in recs), "no price field in the fixture → cash = nominal", fails)
    # ── EU outstanding ──
    fo, orows = Q.csv_to_rows(open(os.path.join(HX, "eu_outstanding_qlik_2026-09-10.csv"), encoding="utf-8").read())
    outs = Q.outstanding_from_rows(fo, orows)
    with_amt = [o for o in outs if o["outstanding"]]
    tot = sum(o["outstanding"] for o in with_amt)
    print("     outstanding: %d raw rows → %d ISINs, %d with amounts, Σ %.0f m (asof %s); %d bills" % (len(orows), len(outs), len(with_amt), tot, max(o["asof"] for o in with_amt), sum(o["kind"] == "bill" for o in with_amt)))
    check(len(orows) == 238 and len(with_amt) == 95 and tot > 500000, "238 raw rows → 157 ISINs, 95 live with a merged amount (Σ > 500 bn)", fails)
    check(all(o["maturity"] < today.isoformat() for o in outs if not o["outstanding"]), "every ISIN without an amount is a matured line", fails)
    x = next(o for o in outs if o["isin"] == "EU000A28X702")
    check(x["coupon"] == 0.13 and x["outstanding"] == 1745.0 and x["asof"] == "2026-09-05" and x["maturity"] == "2035-06-10", "EU000A28X702 merged: coupon 0.13, 1 745 m, asof 2026-09-05", fails)
    cal = Q.eu_calendar(with_amt, today=today)
    for k, s in cal.items():
        print("     %-28s %3d pts  Σ %.1f  last %s" % (k, len(s), sum(v for _, v in s), s[-1] if s else None))
    check(all(d > today.isoformat() for d, _ in cal["eu_redemptions_gross_ahead"]) and all(d <= today.isoformat() for d, _ in cal["eu_coupons_gross_paid"]), "calendar split at today", fails)
    check(all(d in dict(cal["eu_redemptions_gross_ahead"]) for d, _ in cal["eu_bill_maturities_ahead"]), "bill maturities ⊂ redemptions", fails)
    # coupon amount of one sampled bond = outstanding × coupon / 100 (a bond whose coupon date is alone on its day)
    cd = Counter()
    for o in with_amt:
        if o["kind"] == "bond" and o["coupon"]:
            cd[o["maturity"][5:]] += 1
    sample = next(o for o in with_amt if o["kind"] == "bond" and o["coupon"] and cd[o["maturity"][5:]] == 1)
    one = Q.eu_calendar([sample], today=today)
    pts = one["eu_coupons_gross_ahead"] + one["eu_coupons_gross_paid"]
    check(len(pts) >= 1 and all(abs(v - sample["outstanding"] * sample["coupon"] / 100.0) < 0.01 for _, v in pts) and all(d[5:] == sample["maturity"][5:] for d, _ in pts),
          "sampled bond %s: coupon %s on the maturity day-of-month = %.3f" % (sample["isin"], pts, sample["outstanding"] * sample["coupon"] / 100.0), fails)
    check(cal["eu_outstanding_total"][0][1] == round(tot, 3), "eu_outstanding_total = Σ outstanding", fails)
    check(Q.records_from_fixture_csv(os.path.join(HX, "eu_transactions_qlik_2026-09-10.csv")) == recs and Q.outstanding_from_fixture_csv(os.path.join(HX, "eu_outstanding_qlik_2026-09-10.csv")) == outs, "fixture wrappers", fails)
    # ── ESM CSV ──
    esm = E.parse_esm_transactions_csv(open(os.path.join(ESM, "esm_transactions_outstanding_2026-09-10.csv"), encoding="utf-8").read())
    eur_tot = sum(r["amount"] or 0 for r in esm if r["currency"] == "EUR")
    print("     ESM CSV: %d rows, %d bills, issuers %s, EUR Σ %.1f m, non-EUR %s" % (len(esm), sum(r["instrument"] == "Bill" for r in esm), dict(Counter(r["issuer"] for r in esm)), eur_tot, [r["isin"] for r in esm if r["currency"] != "EUR"]))
    check(len(esm) == 119 and sum(r["instrument"] == "Bill" for r in esm) == 4, "ESM CSV: 119 rows, 4 bills", fails)
    e0 = esm[0]
    check(e0["isin"] == "EU000A4DMLZ7" and e0["amount"] == 1599.95 and e0["pricing"] == "2026-09-01" and e0["maturity"] == "2026-12-03" and e0["price"] == 99.37152, "first ESM row: EU000A4DMLZ7 1 599.95 m (bn → m)", fails)
    ecal = E.esm_calendar(esm, today=today)
    for k, s in ecal.items():
        if k != "_non_eur":
            print("     %-24s %3d pts  Σ %.1f" % (k, len(s), sum(v for _, v in s)))
    check("XS3486686333" in ecal["_non_eur"], "_non_eur contains the USD bond XS3486686333", fails)
    check(abs(ecal["esm_outstanding_total"][0][1] - eur_tot) < 0.01, "esm_outstanding_total = Σ EUR amounts", fails)
    check(dict(ecal["esm_redemptions_ahead"]).get("2026-12-03", 0) >= 1599.95, "redemption 2026-12-03 includes the 3m bill", fails)
    # ── Bundesbank list ──
    links = E.bundesbank_list_links(open(os.path.join(ESM, "bundesbank_esm_list_p1.html"), encoding="utf-8").read())
    print("     Bundesbank list: %d items, kinds %s, issuers %s" % (len(links), dict(Counter(l["kind"] for l in links)), dict(Counter(l["issuer"] for l in links))))
    check(len(links) == 10, "10 items on page 1", fails)
    check(links[0]["kind"] == "result" and links[0]["date"] == "2026-09-01" and links[0]["url"].endswith("2026-09-01-auction-result-download.pdf") and links[0]["url"].startswith("https://www.bundesbank.de/"),
          "first item = result of 2026-09-01 with absolute URL", fails)
    check(E.bundesbank_list_url(0).endswith("pageNumString=0"), "bundesbank_list_url(0)", fails)
    # ── PDFs ──
    ann = E.parse_esm_announcement(_pdf_text(os.path.join(ESM, "esm_bill_announcement_2026-08-28.pdf")))
    print("     announcement:", ann)
    check(ann["value_date"] == "2026-09-03" and ann["maturity"] == "2026-12-03" and ann["isin"] == "EU000A4DMLZ7" and ann["envisaged"] == 1600.0 and ann["auction_date"] == "2026-09-01" and ann["days"] == 91,
          "announcement: auction 2026-09-01, value 2026-09-03, maturity 2026-12-03 (91 d), EU000A4DMLZ7, up to 1 600 m", fails)
    res = E.parse_esm_result(_pdf_text(os.path.join(ESM, "esm_bill_result_2026-09-01.pdf")))
    print("     result:", res)
    check(res["allotted"] == 1599.95 and res["avg_price"] == 99.37152 and res["cover"] == 2.3 and res["avg_yield"] == 2.502 and res["auction_date"] == "2026-09-01" and res["bids"] == 3695.0,
          "result: allotted 1 599.95, avg price 99.37152, cover 2.3, avg yield 2.502", fails)
    br = E.esm_bill_records([ann], [res])
    check(len(br) == 1 and br[0]["settlement"] == "2026-09-03" and abs(br[0]["cash"] - 1599.95 * 0.9937152) < 0.001 and br[0]["kind"] == "bill" and br[0]["source"] == "esm_bbk:EU000A4DMLZ7",
          "esm_bill_records: one record, settles 2026-09-03, cash = 1 599.95 × 0.9937152", fails)
    br2 = E.esm_bill_records([], [res])
    check(br2[0]["settlement"] == "2026-09-03" and br2[0]["source"].endswith("#derived"), "without announcement: settlement = maturity − 91 d = 2026-09-03 (#derived)", fails)
    check(set(br[0]) == set(Q.REC_COLS) and set(recs[0]) == set(Q.REC_COLS), "REC_COLS schema", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
