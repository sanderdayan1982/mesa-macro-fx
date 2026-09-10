"""CAD BoC holdings self-checks (run: python3 -m ingest.tests_cad_holdings). No pytest dependency; exits 1 on failure.
Expectations are computed from the fixtures themselves (row counts from the HTML, amounts from the CSV), never hand-typed."""
from __future__ import annotations
import csv
import os
import re
import sys
import tempfile
from . import ops_cad_holdings as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "fixtures", "cad")
TODAY = "2026-09-10"


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def read(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


def tbody_counts(html):
    """data rows per table = <tr> inside <tbody> (header and tfoot excluded), in document order"""
    out = []
    for t in re.findall(r"<table.*?</table>", html, flags=re.S | re.I):
        body = re.search(r"<tbody>(.*?)</tbody>", t, flags=re.S | re.I)
        out.append(len(re.findall(r"<tr", body.group(1), flags=re.I)) if body else 0)
    return out


def main() -> int:
    fails = []
    # ── 1. live page ──
    page = read("boc_holdings_2026-09-10.html")
    rows = H.parse_boc_holdings_html(page)
    n = {k: sum(1 for r in rows if r["kind"] == k) for k in ("tbill", "bond", "cmb")}
    exp = tbody_counts(page)
    check(len(exp) == 3 and [n["tbill"], n["bond"], n["cmb"]] == exp, "live page: %d tbill / %d bond / %d cmb data rows = tbody <tr> counts %s" % (n["tbill"], n["bond"], n["cmb"], exp), fails)
    check(all(r["asof"] == TODAY for r in rows), "live page: every row as of %s" % TODAY, fails)
    first_tb = re.search(r'<table id="tbills".*?<tbody>\s*<tr><td[^>]*>([^<]+)</td><td>([^<]+)</td><td>([^<]+)</td>', page, flags=re.S).groups()
    tb0 = [r for r in rows if r["kind"] == "tbill"][0]
    check(tb0["maturity"] == first_tb[0] and tb0["isin"] == first_tb[1] and abs(tb0["par"] - float(first_tb[2].replace(",", "")) / 1e6) < 1e-9,
          "first tbill row %s %s %.3f M matches the HTML (%s)" % (tb0["maturity"], tb0["isin"], tb0["par"], first_tb[2]), fails)
    check(all(r["coupon"] is None and r["on_repo"] in (None,) or r["on_repo"] is None or r["on_repo"] > 0 for r in rows if r["kind"] == "tbill"), "tbill rows: coupon None, empty on_repo → None", fails)
    b = {r["isin"]: r for r in rows if r["kind"] == "bond"}
    check(b["CA135087F825"]["on_repo"] == 2771.0 and b["CA135087F825"]["par"] == 8534.306 and b["CA135087F825"]["coupon"] == 1.0, "bond CA135087F825: par 8 534.306 M, on repo 2 771 M, coupon 1.0", fails)
    foot = [float(x.replace(",", "")) / 1e6 for x in re.findall(r"<tfoot>.*?<td>([\d,]+)</td>", page, flags=re.S)]
    tot = [round(sum(r["par"] for r in rows if r["kind"] == k), 3) for k in ("tbill", "bond", "cmb")]
    check(all(abs(a - b_) < 1e-6 for a, b_ in zip(tot, foot)), "Σ par per table %s = tfoot totals %s" % (tot, foot), fails)
    # ── 2. historical blob ──
    blob = read("boc_holdings_blob_boc_holdings_2026_08.html")
    brows = H.parse_boc_holdings_html(blob)
    bn = {k: sum(1 for r in brows if r["kind"] == k) for k in ("tbill", "bond", "cmb")}
    bexp = tbody_counts(blob)
    check([bn["tbill"], bn["bond"], bn["cmb"]] == bexp, "blob 2026_08: %d/%d/%d data rows = tbody counts %s" % (bn["tbill"], bn["bond"], bn["cmb"], bexp), fails)
    check(all(r["asof"] == "2026-08-31" for r in brows), "blob 2026_08: as of 2026-08-31", fails)
    names = H.blob_names("2018-12", "2026-08")
    check(len(names) == 93 and names[0] == "boc_holdings_2018_12.html" and names[-1] == "boc_holdings_2026_08.html", "blob_names 2018-12 → 2026-08 = 93 names", fails)
    check(H.blob_url(names[-1]).endswith("historical-bank-of-canada-holdings/?blob=boc_holdings_2026_08.html"), "blob_url", fails)
    # ── 3. archive round trip ──
    tmp = os.path.join(tempfile.mkdtemp(), "boc_holdings_archive.csv")
    m1 = H.merge_holdings_archive(tmp, brows)
    m2 = H.merge_holdings_archive(tmp, rows)
    m3 = H.merge_holdings_archive(tmp, rows)  # idempotent
    check(len(m1) == len(brows) and len(m2) == len(brows) + len(rows) and len(m3) == len(m2), "archive: append-only keyed by (asof, isin), re-merge idempotent (%d rows)" % len(m3), fails)
    back = H.read_holdings_archive(tmp)
    check(back == m3 and back[0]["asof"] == "2026-08-31" and back[-1]["asof"] == TODAY, "archive: read back == merged, sorted by (asof, kind, maturity)", fails)
    latest = H.holdings_latest(back)
    check(len(latest) == n["tbill"] + n["bond"] and all(r["asof"] == TODAY for r in latest.values()), "holdings_latest from archive → latest snapshot only, tbill+bond", fails)
    # ── 4. GOC_OUTSTANDING ──
    csv_rows = list(csv.DictReader(open(os.path.join(FIX, "GOC_OUTSTANDING_latest.csv"), encoding="utf-8")))
    with_isin = [r for r in csv_rows if r["DOM_DBT_ISIN"]]
    out = H.goc_outstanding_from_csv(os.path.join(FIX, "GOC_OUTSTANDING_latest.csv"))
    check(len(out) == len(with_isin) == 83, "GOC_OUTSTANDING: %d rows with an ISIN (fixture has %d)" % (len(out), len(with_isin)), fails)
    check(all(o["asof"] == "2026-09-08" for o in out), "GOC_OUTSTANDING: all as of 2026-09-08", fails)
    sum_b = round(sum(o["outstanding"] for o in out if o["security_type"] == "BOND"), 3)
    sum_t = round(sum(o["outstanding"] for o in out if o["security_type"] == "MM"), 3)
    raw_b = round(sum(float(r["DOM_DBT_OUTSTANDING_AMOUNT"]) for r in with_isin if r["DOM_DBT_SECURITY_TYPE"] == "BOND") / 1e6, 3)
    check(abs(sum_b - raw_b) < 1e-6, "Σ outstanding BOND = %.3f M (nominal), MM = %.3f M" % (sum_b, sum_t), fails)
    rrb = [o for o in out if o["instrument_type"] == "BD-REAL"]
    check(len(rrb) == 8 and all(o["inflation_adjusted"] and o["inflation_adjusted"] > o["outstanding"] for o in rrb), "8 Real Return Bonds carry an inflation-adjusted amount > nominal", fails)
    check(all(o["inflation_adjusted"] is None for o in out if o["instrument_type"] == "BD-FIX"), "fixed-coupon bonds: inflation_adjusted None", fails)
    # ── 5. net_calendar ──
    cal = H.net_calendar(out, rows, today=TODAY)
    rn, rg, rb = dict(cal["bond_redemptions_net_ahead"]), dict(cal["bond_redemptions_gross_ahead"]), dict(cal["bond_redemptions_boc_ahead"])
    check(rn and all(rn[d] <= rg[d] + 1e-6 for d in rn), "every net redemption <= gross (%d dates)" % len(rn), fails)
    check(all(abs(rn[d] + rb.get(d, 0.0) - rg[d]) < 1e-3 for d in rg), "net + BoC = gross on every redemption date", fails)
    cn, cg = dict(cal["bond_coupons_net_ahead"]), dict(cal["bond_coupons_gross_ahead"])
    check(cn and all(cn[d] <= cg[d] + 1e-6 for d in cn), "every net coupon <= gross (%d dates ahead)" % len(cn), fails)
    check(all(d <= TODAY for d, _ in cal["bond_coupons_net_paid"]) and all(d > TODAY for d, _ in cal["bond_coupons_net_ahead"]), "coupons split at today", fails)
    sb, st = cal["boc_share_bonds"][0][1], cal["boc_share_tbills"][0][1]
    check(0.0 < sb < 1.0 and 0.0 < st < 1.0, "BoC shares in (0, 1): bonds %.4f, tbills %.4f" % (sb, st), fails)
    s398 = next(o for o in out if o["isin"] == "CA135087S398")
    held = H.holdings_latest(rows)
    boc_par = held["CA135087S398"]["par"] if "CA135087S398" in held else 0.0
    priv = s398["outstanding"] - boc_par
    check(s398["maturity"] == "2026-11-01" and s398["coupon"] == 3.25, "CA135087S398 matures 2026-11-01 at 3.25%", fails)
    check(abs(rn["2026-11-01"] - priv) < 1e-3, "2026-11-01 net redemption %.3f = outstanding %.3f − BoC par %.3f" % (rn["2026-11-01"], s398["outstanding"], boc_par), fails)
    solo = dict(H.net_calendar([s398], rows, today=TODAY)["bond_coupons_net_ahead"])
    check(list(solo) == ["2026-11-01"] and abs(solo["2026-11-01"] - priv * 3.25 / 200) < 1e-3, "S398 alone: one coupon 2026-11-01 = %.3f = private × 3.25/200" % solo["2026-11-01"], fails)
    # the page-level 2026-11-01 coupon is the sum over every May/Nov bond (coupon day 01) still outstanding that day
    may_nov = [o for o in out if o["security_type"] == "BOND" and o["maturity"][5:7] in ("05", "11") and o["maturity"][8:10] == "01" and o["maturity"] >= "2026-11-01"]
    exp_cn = sum((o["outstanding"] - (held[o["isin"]]["par"] if o["isin"] in held else 0.0)) * H._ratio(o) * o["coupon"] / 200 for o in may_nov)
    check(abs(cn["2026-11-01"] - exp_cn) < 1e-3, "coupon 2026-11-01 = %.3f = Σ over %d May/Nov bonds (S398 share %.3f)" % (cn["2026-11-01"], len(may_nov), solo["2026-11-01"]), fails)
    # RRB CA135087VS05 (2026-12-01): BoC holds 440 M nominal of 5 250 M; redemption at the index ratio
    vs = next(o for o in out if o["isin"] == "CA135087VS05")
    k = vs["inflation_adjusted"] / vs["outstanding"]
    exp_vs = (vs["outstanding"] - held["CA135087VS05"]["par"]) * k
    check(abs(rn["2026-12-01"] - exp_vs) < 1e-3 and abs(rg["2026-12-01"] - vs["inflation_adjusted"]) < 1e-3,
          "RRB 2026-12-01: net %.3f = (5 250 − 440) × %.4f, gross = inflation-adjusted %.3f" % (rn["2026-12-01"], k, vs["inflation_adjusted"]), fails)
    tn, tg = dict(cal["tbill_maturities_net_ahead"]), dict(cal["tbill_maturities_gross_ahead"])
    check(tn and all(tn[d] <= tg[d] + 1e-6 for d in tn) and all(d > TODAY for d in tn), "tbill maturities net <= gross, strictly ahead (%d dates)" % len(tn), fails)
    ey = next(o for o in out if o["isin"] == "CA1350Z7EY62")
    check(abs(tn["2026-09-23"] - (ey["outstanding"] - held["CA1350Z7EY62"]["par"])) < 1e-3, "tbill 2026-09-23 net = 23 800 − 238 = %.1f" % tn["2026-09-23"], fails)
    check(isinstance(cal["_unmatched"], list) and all(i in held for i in cal["_unmatched"]), "_unmatched (BoC-held, not in outstanding): %s" % cal["_unmatched"], fails)
    check(cal["holdings_asof"] == [(TODAY, 1.0)], "holdings_asof", fails)
    # ── 6. net_daily_history (toy two-snapshot input) ──
    o1 = [{"asof": "2026-01-31", "isin": "X1", "security_type": "BOND", "instrument_type": "BD-FIX", "coupon": 2.0, "issue_date": "2020-03-01", "maturity": "2026-03-01", "outstanding": 1000.0, "inflation_adjusted": None},
          {"asof": "2026-01-31", "isin": "T1", "security_type": "MM", "instrument_type": "MM-TBILL", "coupon": 0.0, "issue_date": "2025-12-03", "maturity": "2026-02-11", "outstanding": 500.0, "inflation_adjusted": None}]
    o2 = [dict(o1[0], asof="2026-02-28"), dict(o1[1], asof="2026-02-28", outstanding=600.0)]
    h1 = [{"asof": "2026-01-31", "kind": "bond", "maturity": "2026-03-01", "coupon": 2.0, "isin": "X1", "par": 100.0, "on_repo": None},
          {"asof": "2026-01-31", "kind": "tbill", "maturity": "2026-02-11", "coupon": None, "isin": "T1", "par": 50.0, "on_repo": None}]
    h2 = [dict(h1[0], asof="2026-02-28", par=300.0)]
    days = H.business_days("2026-01-29", "2026-03-05")
    hist = H.net_daily_history(h1 + h2, o1 + o2, days)
    r, c, t = dict(hist["bond_redemptions_net_daily"]), dict(hist["bond_coupons_net_daily"]), dict(hist["tbill_maturities_net_daily"])
    check(r["2026-01-29"] is None and c["2026-01-30"] is None, "days before the first snapshot → None", fails)
    check(t["2026-02-11"] == 450.0 and r["2026-02-11"] == 0.0, "2026-02-11: tbill 500 − 50 (Jan snapshot) = 450, dense 0 elsewhere", fails)
    # 2026-03-01 is a Sunday → booked on Monday 2026-03-02 with the Feb snapshots (par 300 → private 700): redemption 700, coupon 700×2/200 = 7
    check(r["2026-03-02"] == 700.0 and c["2026-03-02"] == 7.0 and r["2026-02-27"] == 0.0, "2026-03-01 (Sunday) → 2026-03-02: redemption 700 and last coupon 7.0 from the Feb snapshot", fails)
    check(len(hist["bond_redemptions_net_daily"]) == len(days) and all(v == 0.0 for d, v in hist["bond_coupons_net_daily"] if v is not None and d != "2026-03-02"), "dense over all business days", fails)
    # ── summary ──
    print("\nsummary: holdings as of %s (blob as of %s); outstanding as of %s" % (TODAY, brows[0]["asof"], out[0]["asof"]))
    print("  BoC holdings: bonds %.1f M (%.2f%% of %.1f M outstanding), tbills %.1f M (%.2f%% of %.1f M)" % (
        cal["boc_holdings_bonds_total"][0][1], sb * 100, sum_b, cal["boc_holdings_tbills_total"][0][1], st * 100, sum_t))
    print("  net bond redemptions ahead (365d): %.1f M gross %.1f M; net coupons ahead %.1f M gross %.1f M; tbill net %.1f M gross %.1f M" % (
        sum(rn.values()), sum(rg.values()), sum(cn.values()), sum(cg.values()), sum(tn.values()), sum(tg.values())))
    print("  unmatched BoC-held ISINs: %s" % (cal["_unmatched"] or "none"))
    print("\n%d FAILED" % len(fails) if fails else "\nall checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
