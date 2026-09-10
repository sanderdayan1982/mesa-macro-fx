"""JPY v0.4 self-checks (run: python3 -m ingest.tests_jpy_ops). No pytest; ok/FAIL lines; exit 1 on failure.
Fixtures: fixtures/jpy_hist/{jd20260909,jx20260910,jp20260911,ope20260909,ope20260910,juqp2609,mei260831}.xlsx and the MoF XLS files."""
from __future__ import annotations
import os
import sys
import tempfile
from . import ops_jpy as J

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "fixtures", "jpy_hist")
TODAY = "2026-09-10"


def blob(name: str) -> bytes:
    return open(os.path.join(FIX, name), "rb").read()


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def main() -> int:
    fails: list = []
    # ── 1. daily files
    jd = J.parse_daily_file(blob("jd20260909.xlsx"), "jd20260909.xlsx")
    check(jd["date"] == "2026-09-09" and jd["kind"] == "jd", "jd20260909 → date 2026-09-09 kind jd (got %s %s)" % (jd["date"], jd["kind"]), fails)
    check(jd["final"]["treasury"] == -35900 and jd["proj"]["treasury"] == -33600 and jd["prov"]["treasury"] == -35900,
          "jd treasury proj/prov/final = −33600/−35900/−35900 (got %s/%s/%s)" % (jd["proj"]["treasury"], jd["prov"]["treasury"], jd["final"]["treasury"]), fails)
    check(jd["final"]["cab"] == 4116600 and jd["final"]["reserve_bal"] == 3811200 and jd["final"]["req_daily"] == 134800,
          "jd final cab 4116600, reserve_bal 3811200, req_daily 134800 (got %s %s %s)" % (jd["final"]["cab"], jd["final"]["reserve_bal"], jd["final"]["req_daily"]), fails)
    check(jd["final"]["slf"] == 100 and jd["final"]["ops_ex_lsp"] == 100 and jd["final"]["subtotal"] == 100, "jd SLF = JP row 500 + EN row −400 = 100 = ops_ex_lsp = subtotal", fails)
    check(jd["final"]["excess"] == 3811200 and jd["final"]["mbase"] == 5307300 and jd["prov"]["mbase"] is None, "jd excess (indented 4 levels) 3811200, mbase final only", fails)
    check(len(jd["notes"]) >= 6 and any("Complementary Lending" in n for n in jd["notes"]), "jd notes parsed (%d)" % len(jd["notes"]), fails)
    jp = J.parse_daily_file(blob("jp20260911.xlsx"), "jp20260911.xlsx")
    check(jp["date"] == "2026-09-11" and jp["kind"] == "jp", "jp20260911 → date 2026-09-11 (got %s)" % jp["date"], fails)
    check(jp["proj"]["treasury"] == -10400 and jp["prov"]["treasury"] is None and jp["final"]["treasury"] is None, "jp proj treasury −10400, prov/final None", fails)
    check(jp["proj"]["corp_bonds"] == -100, "jp corp_bonds projection −100 taken from the EN row", fails)
    jx = J.parse_daily_file(blob("jx20260910.xlsx"), "jx20260910.xlsx")
    check(jx["date"] == "2026-09-10" and jx["kind"] == "jx", "jx20260910 → date 2026-09-10", fails)
    check(jx["proj"]["treasury"] == 2200 and jx["prov"]["treasury"] == 3400, "jx treasury proj 2200 / prov 3400 (got %s/%s)" % (jx["proj"]["treasury"], jx["prov"]["treasury"]), fails)
    check(jx["prov"]["jgb_purch"] == 7200, "jx jgb_purch prov 7200 (got %s)" % jx["prov"]["jgb_purch"], fails)
    # cells input path
    jd2 = J.parse_daily_file(J.read_xlsx_cells(blob("jd20260909.xlsx"), "当預"), "jd20260909.xlsx")
    check(jd2["final"] == jd["final"], "parse_daily_file accepts the cells list", fails)
    # ── 2/3/4. wide, archive, surprise
    wide = J.daily_records_to_wide([jd, jx, jp])
    check(wide["proj"]["treasury"] == [("2026-09-09", -33600.0), ("2026-09-10", 2200.0), ("2026-09-11", -10400.0)], "wide proj treasury over 3 days", fails)
    check(wide["final"]["treasury"] == [("2026-09-09", -35900.0)], "wide final treasury only where final exists", fails)
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "boj_daily_archive.csv")
        rows = J.merge_daily_archive(p, [jd, jx])
        n1 = len(rows)
        rows = J.merge_daily_archive(p, [jx, jp])
        back = J.read_daily_archive(p)
        # jx / jp also yield a 'final' row: the reference items (所要準備額 積数 / １日平均) sit in column H whatever the file version
        check(n1 == 6 and len(rows) == 8 and len(back) == 8, "archive: jd (3 versions) + jx (3) = 6 rows; + jp (2) = 8; replace same (date, version) (got %d, %d)" % (n1, len(rows)), fails)
        check(jp["final"]["req_daily"] == 134800 and jp["final"]["treasury"] is None, "jp 'final' carries only the reference items (req_daily 134800)", fails)
        check(next(r for r in back if r["date"] == "2026-09-10" and r["version"] == "prov")["jgb_purch"] == 7200.0, "archive round-trip keeps values", fails)
    s = J.surprise(J.best_realized(wide["final"]["treasury"], wide["prov"]["treasury"]), wide["proj"]["treasury"])
    check(s == [("2026-09-09", -2300.0), ("2026-09-10", 1200.0)], "surprise treasury = realized − projected: −2300 (09-09 final), +1200 (09-10 prov) (got %s)" % s, fails)
    # ── 5. operations
    o9 = J.parse_ope_file(blob("ope20260909.xlsx"), "ope20260909.xlsx")
    jg = [o for o in o9 if o["kind"] == "jgb_purch"]
    sl = [o for o in o9 if o["kind"] == "slf"]
    check(len(o9) == 5 and all(o["date"] == "2026-09-09" for o in o9), "ope 09-09: 5 operations dated 2026-09-09 (got %d)" % len(o9), fails)
    check(len(jg) == 3 and sum(o["allotted"] for o in jg) == 7659 and all(o["start"] == "2026-09-10" and o["end"] is None for o in jg),
          "ope 09-09: 3 JGB purchases Σ allotted 7659, start 2026-09-10, no end", fails)
    check(len(sl) == 2 and sum(o["allotted"] for o in sl) == 464 and all(o["start"] == "2026-09-09" and o["end"] == "2026-09-10" for o in sl), "ope 09-09: 2 SLF rows Σ 464, 09-09 → 09-10", fails)
    check(jg[0]["instrument_en"].startswith("Outright purchases of JGBs") and jg[0]["offered"] == 3550 and jg[0]["bids"] == 11080 and jg[0]["yield"] is None and sl[0]["yield"] == 0.5,
          "ope columns by header: offered/bids/yield/EN name", fails)
    o10 = J.parse_ope_file(blob("ope20260910.xlsx"), "ope20260910.xlsx")
    check(len(o10) == 2 and [o["allotted"] for o in o10] == [718, 0] and all(o["kind"] == "slf" for o in o10), "ope 09-10: 2 SLF rows (718 + 0)", fails)
    days = J.business_days("2026-09-01", TODAY)
    fl = J.ops_flows(o9 + o10, wide["prov"], days, today=TODAY)
    check(dict(fl["jgb_purch_settled"]).get("2026-09-10") == 7659, "ops_flows jgb_purch_settled 2026-09-10 = 7659", fails)
    check(dict(fl["slf_out"]) == {"2026-09-09": -464.0, "2026-09-10": -718.0} and dict(fl["slf_back"]) == {"2026-09-10": 464.0, "2026-09-11": 718.0}, "SLF: − at start, + at end", fails)
    check(dict(fl["ops_net_daily"]).get("2026-09-10") == 7659 + 464 - 718 and dict(fl["ops_net_daily"]).get("2026-09-09") == -464, "ops_net_daily 09-09 = −464, 09-10 = 7659 + 464 − 718", fails)
    check(fl["ops_calendar_ahead"] == [("2026-09-11", 718.0)], "ops_calendar_ahead: SLF repurchase 09-11 +718", fails)
    rc = J.reconcile_ops(fl["jgb_purch_settled"], wide["prov"]["jgb_purch"])
    check(rc == [("2026-09-10", 459.0)] and fl["jgb_purch_face_minus_cash"] == rc, "reconcile: face 7659 − cash 7200 = 459 on 2026-09-10", fails)
    # ── 6. monthly projections
    q = J.parse_juqp(blob("juqp2609.xlsx"))
    check(q["month"] == "2026-09" and q["published"] == "2026-09-03", "juqp month 2026-09 published 2026-09-03 (got %s %s)" % (q["month"], q["published"]), fails)
    check(q["treasury"] == -76100 and q["jgb_net"] == -62500 and q["tbill_net"] == 36700 and q["other"] == -50300 and q["banknotes"] == 5100 and q["surplus"] == -71000,
          "juqp treasury −76100, jgb_net −62500, tbill_net 36700, other −50300", fails)
    check(q["prev_year"]["treasury"] == -114751 and q["yoy"]["treasury"] == 38651, "juqp previous year / yoy columns", fails)
    check(q["shortage_days"] == ["2026-09-01", "2026-09-02", "2026-09-09", "2026-09-11", "2026-09-29"] and q["surplus_days"] == ["2026-09-24"], "juqp shortage days 1,2,9,11,29; surplus 24", fails)
    # ── 7. mei
    mei = J.parse_mei(blob("mei260831.xlsx"), "mei260831.xlsx")
    n = len(mei["rows"])
    check(mei["asof"] == "2026-08-31" and mei["published"] == "2026-09-02", "mei asof 2026-08-31 published 2026-09-02 (got %s %s)" % (mei["asof"], mei["published"]), fails)
    check(n == 339, "mei data rows counted = 339 (spec said 359; the file has rows 16-354 → %d)" % n, fails)
    r0 = mei["rows"][0]
    check(r0["type_jp"] == "2年債" and r0["type_en"] == "2-Year JGB" and r0["issue_no"] == 464 and r0["amount"] == 14875 and r0["tenor_years"] == 2, "mei first row 2年債 #464 14875", fails)
    types = sorted(set(r["type_jp"] for r in mei["rows"]))
    tot = sum(r["amount"] for r in mei["rows"])
    print("     mei types: %s" % types)
    print("     mei Σ amount = %.0f (100m) = %.1f trn yen" % (tot, tot / 1e4))
    check(all(r["type_en"] for r in mei["rows"]), "mei every row carries an EN type label", fails)
    hb = J.mei_holdings_by_issue(mei)
    check(len(hb) == n and hb[("2年債", 464)] == 14875, "mei_holdings_by_issue keyed by (type, issue)", fails)
    # ── 8. MoF XLS
    jgb = J.parse_mof_jgb_xls(os.path.join(FIX, "mof_auction_results_jgbs.xls"))
    per = {}
    for r in jgb:
        per[r["type_jp"]] = per.get(r["type_jp"], 0) + 1
    print("     MoF JGB records per sheet: %s" % per)
    check(len(per) == 14 and "TB" in per and "GX10年債" in per, "MoF JGB: 14 sheets parsed (sheet names stripped)", fails)
    two = [r for r in jgb if r["type_jp"] == "2年債"]
    last2 = max(two, key=lambda r: (r["issue_no"], r["auction"]))
    print("     2年債 last: issue %d auction %s issue %s maturity %s coupon %s issued_total %s (accepted %s + npc1 %s + npc2 %s)" % (
        last2["issue_no"], last2["auction"], last2["issue"], last2["maturity"], last2["coupon"], last2["issued_total"], last2["accepted"], last2["npc1"], last2["npc2"]))
    check(last2["issue_no"] == 487 and last2["issue"].startswith("2026-") and last2["maturity"].startswith("2028-"), "2年債 last issue_no 487, issued 2026, matures 2028", fails)
    check(last2["issued_total"] == 21344 + 6648 + 0 and last2["coupon"] == 1.5, "2年債 #487 issued_total = accepted + NPC I + NPC II, coupon 1.5", fails)
    fl15 = [r for r in jgb if r["type_jp"] == "15変動"]
    check(fl15 and all(r["coupon"] is None for r in fl15) and fl15[0]["npc1"] == 0.0 and fl15[0]["issue"] == "2000-06-20", "15変動: no coupon column, '―' → 0, dates via xlrd", fails)
    forty = [r for r in jgb if r["type_jp"] == "40年債"]
    check(forty[0]["npc2"] == 0.0 and forty[1]["npc2"] == 176 and forty[1]["issued_total"] == 2028 + 176, "40年債: NPC II only (no NPC I column)", fails)
    tb = J.parse_mof_tbill_xls(os.path.join(FIX, "mof_auction_results_tbills.xls"))
    t0 = next(r for r in tb if r["issue_no"] == 1372)
    print("     MoF T-Bill records: %d (FY sheets %d)" % (len(tb), len(set(r["fy"] for r in tb))))
    check(abs(t0["accepted"] - 35961.7) < 0.01 and abs(t0["npc1"] - 10038) < 0.01 and abs(t0["issued_total"] - 45999.7) < 0.01 and t0["tenor_label"] == "3-month" and t0["type_jp"] == "TB",
          "T-Bill #1372: billions ×10 → 100m (accepted 35961.7 + NPC I 10038)", fails)
    check(t0["auction"] == "2026-04-03" and t0["issue"] == "2026-04-06" and t0["maturity"] == "2026-07-06", "T-Bill #1372 dates 2026-04-03 / 04-06 / 07-06", fails)
    # ── 9. issue map / holdings by maturity
    imap = J.issue_map(jgb)
    e487 = imap[("2年債", 487)]
    f1 = [r for r in forty if r["issue_no"] == 1]
    check(e487["issued_total"] == last2["issued_total"] and e487["auctions"] == 1 and imap[("40年債", 1)]["auctions"] == len(f1) == 4
          and abs(imap[("40年債", 1)]["issued_total"] - sum(r["issued_total"] for r in f1)) < 1e-6 and imap[("40年債", 1)]["first_issue"] == "2007-11-20",
          "issue_map sums reopenings (40年債 #1: 4 auctions, first issue 2007-11-20)", fails)
    bym = J.mei_to_maturity(mei, imap)
    unm = bym["_unmapped"]
    mapped_amt = sum(v for k, v in bym.items() if k != "_unmapped")
    print("     mei→maturity: mapped %d / unmapped %d pairs; Σ mapped %.0f vs Σ mei %.0f" % (n - len(unm), len(unm), mapped_amt, tot))
    if unm:
        print("     _unmapped: %s" % unm[:20])
    last5 = max(r["issue_no"] for r in jgb if r["type_jp"] == "5年債")
    check(abs(mapped_amt + sum(a for _, _, a in unm) - tot) < 0.5, "Σ by maturity + Σ unmapped = Σ mei", fails)
    check(all(no > last5 for t, no, _ in unm if t == "5年債") and all(t == "5年債" for t, _, _ in unm),
          "unmapped pairs are only issues auctioned after the MoF XLS snapshot (5年債 last in XLS = #%d; mei as of %s holds #187)" % (last5, mei["asof"]), fails)
    check(all(J.mei_type_to_sheet(t) in per for t in types), "mei types map to MoF sheets: %s" % {t: J.mei_type_to_sheet(t) for t in types}, fails)
    mats = sorted(k for k in bym if k != "_unmapped")
    print("     holdings by maturity: %d dates, first %s (%.0f) last %s (%.0f)" % (len(mats), mats[0], bym[mats[0]], mats[-1], bym[mats[-1]]))
    # ── 10. net issuance
    days = J.business_days("2024-01-01", TODAY)
    cl = J.coupon_lines(imap, mei)
    ni = J.net_issuance(jgb, tb, bym, cl, days, today=TODAY)
    dense = ni["net_issuance_private_daily"]
    check([d for d, _ in dense] == days and all(v is not None for _, v in dense), "net_issuance_private_daily is dense over the business days", fails)
    g, nt = dict(ni["matured_jgb_gross"]), dict(ni["matured_jgb_net"])
    partial = [d for d in g if d in nt and 0 < nt[d] < g[d]]
    check(len(partial) > 0, "matured_net < matured_gross where the BoJ holds part (%d maturity dates)" % len(partial), fails)
    check(all(nt.get(d, 0) <= g[d] + 1e-6 for d in g) and all(v >= 0 for v in nt.values()), "matured_net ≤ gross and ≥ 0 everywhere", fails)
    # consistency: dense == −issued + matured on a sample date
    d0 = partial[-1]
    comp = dict(ni["issued_jgb"]).get(d0, 0) + dict(ni["issued_tbill"]).get(d0, 0) + dict(ni["matured_tbill"]).get(d0, 0) + nt.get(d0, 0)
    check(abs(dict(dense)[d0] - comp) < 0.01, "dense net issuance on %s = −issued_jgb − issued_tbill + matured_tbill + matured_jgb_net" % d0, fails)
    cg, cn = dict(ni["coupons_jgb_gross"]), dict(ni["coupons_jgb_net"])
    check(cg and all(cn.get(d, 0) <= cg[d] + 1e-6 for d in cg) and any(cn.get(d, 0) < cg[d] for d in cg), "coupons net ≤ gross, and strictly lower where the BoJ holds the issue", fails)
    check(ni["boj_share_by_maturity"] and all(0 <= s <= 1 for _, s in ni["boj_share_by_maturity"]), "boj_share_by_maturity within [0, 1] (%d maturities ahead)" % len(ni["boj_share_by_maturity"]), fails)
    check(all(d > TODAY for d, _ in ni["jgb_redemptions_net_ahead"] + ni["tbill_maturities_ahead"] + ni["jgb_coupons_net_ahead"]) and all(d <= TODAY for d, _ in ni["issued_jgb"] + ni["matured_tbill"]),
          "everything <= today in flows, > today in calendars", fails)
    nz = [(d, v) for d, v in dense if v != 0]
    print("     last 10 non-zero net issuance flows (100m): %s" % nz[-10:])
    print("     next 5 JGB redemptions net:   %s" % ni["jgb_redemptions_net_ahead"][:5])
    print("     next 5 JGB redemptions gross: %s" % ni["jgb_redemptions_gross_ahead"][:5])
    print("     next 5 T-Bill maturities:     %s" % ni["tbill_maturities_ahead"][:5])
    print("     next 5 JGB coupons net/gross: %s / %s" % (ni["jgb_coupons_net_ahead"][:5], ni["jgb_coupons_gross_ahead"][:5]))
    print("     BoJ share next 5 maturities:  %s" % ni["boj_share_by_maturity"][:5])
    print("%d checks failed" % len(fails) if fails else "all checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
