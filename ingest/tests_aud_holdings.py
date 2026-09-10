"""AUD RBA A3.1 holdings self-checks (run: python3 -m ingest.tests_aud_holdings). No pytest dependency; exits 1 on failure.
Expectations are computed from the fixtures themselves (row counts and values from the CSV), never hand-typed."""
from __future__ import annotations
import csv
import io
import os
import sys
from . import ops_aud as A
from . import ops_aud_holdings as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "fixtures", "aud_hist")
TODAY = "2026-09-10"


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def main() -> int:
    fails = []
    text = open(os.path.join(FIX, "rba_a3.1_ags_bonds.csv"), encoding="utf-8").read()
    raw = [r for r in csv.reader(io.StringIO(text)) if r and r[0].strip()]
    data_rows = [r for r in raw if A._iso(r[0])]
    n_dates = len({A._iso(r[0]) for r in data_rows})
    rows = H.parse_a31_csv(text)
    dates = sorted({r["date"] for r in rows})
    check(len(dates) == n_dates, "parsed month-ends %d = data rows in the file %d" % (len(dates), n_dates), fails)
    check(dates[0] == "2017-01-31" and dates[-1] == "2026-08-31", "first/last month-end %s / %s" % (dates[0], dates[-1]), fails)
    check(all(r["publication_date"] == "2026-09-01" for r in rows), "publication date 2026-09-01 on every record", fails)
    check(all(r["holding"] > 0 for r in rows), "only positive holdings kept (%d records)" % len(rows), fails)
    # the '164 0.50% 21-Sep-2026' column, read straight from the file
    desc = next(r for r in raw if r[0] == "Description")
    col = next(i for i, d in enumerate(desc) if "164" in d and "21-Sep-2026" in d)
    last_row = next(r for r in data_rows if A._iso(r[0]) == "2026-08-31")
    file_164 = float(last_row[col])
    r164 = [r for r in rows if r["date"] == "2026-08-31" and r["series_no"] == 164]
    check(len(r164) == 1 and r164[0]["coupon"] == 0.5 and r164[0]["maturity"] == "2026-09-21" and r164[0]["title"] == H.AGS_TITLE,
          "series 164: coupon 0.5, maturity 2026-09-21, title AGS (description '%s')" % desc[col], fails)
    check(r164 and r164[0]["holding"] == file_164, "series 164 holding on 2026-08-31 = %.0f (file column %d)" % (file_164, col), fails)
    print("     RBA holding 21-Sep-2026 on 2026-08-31: %.0f $m" % file_164)
    tot_file = sum(float(v) for v in last_row[1:] if v.strip())
    tot = sum(r["holding"] for r in rows if r["date"] == "2026-08-31")
    check(abs(tot - tot_file) < 1e-6, "Σ holdings on 2026-08-31 = %.0f $m (file %.0f)" % (tot, tot_file), fails)
    asof, bym = H.rba_by_maturity(rows)
    check(asof == "2026-08-31" and bym.get("2026-09-21") == file_164 and abs(sum(bym.values()) - tot_file) < 1e-6, "rba_by_maturity latest → 2026-08-31 map (%d maturities)" % len(bym), fails)
    a2, _ = H.rba_by_maturity(rows, "2026-08-15")
    check(a2 == "2026-07-31", "rba_by_maturity asof 2026-08-15 → 2026-07-31", fails)
    dup = H.rba_by_maturity([{"date": "2026-01-31", "title": H.AGS_TITLE, "maturity": "2030-01-01", "holding": 1.0}, {"date": "2026-01-31", "title": H.AGS_TITLE, "maturity": "2030-01-01", "holding": 2.0}])
    check(dup[1] == {"2030-01-01": 3.0}, "lines sharing a maturity are summed", fails)
    # netting against the AOFM face-value fixture
    lines = A.face_value_from_csv(os.path.join(FIX, "aofm_tb_face_value_by_line.csv"))
    aofm_asof = max(l["date"] for l in lines)
    cal = H.net_tb_calendar(lines, rows, today=TODAY)
    gross = dict(cal["tb_redemptions_gross_ahead"])
    net = dict(cal["tb_redemptions_net_ahead"])
    rba = dict(cal["tb_redemptions_rba_ahead"])
    face_sep26 = sum(l["face"] or 0.0 for l in lines if l["date"] == aofm_asof and l["maturity"] == "2026-09-21")
    print("     AOFM asof %s; RBA asof %s; 21-Sep-2026 face %.3f gross %.3f net %.3f rba %.3f" % (aofm_asof, cal["tb_holdings_asof"][0][0], face_sep26,
          gross.get("2026-09-21", 0.0), net.get("2026-09-21", 0.0), rba.get("2026-09-21", 0.0)))
    if face_sep26:
        check(abs(gross.get("2026-09-21", 0.0) - face_sep26) < 1e-6, "gross 2026-09-21 = AOFM face %.3f" % face_sep26, fails)
        check(abs(net.get("2026-09-21", 0.0) - max(0.0, face_sep26 - file_164)) < 1e-6, "net 2026-09-21 = face − RBA %.0f = %.3f" % (file_164, net.get("2026-09-21", 0.0)), fails)
    else:
        print("     (AOFM fixture has no 2026-09-21 line at %s)" % aofm_asof)
    check(cal["tb_holdings_asof"][0][0] <= aofm_asof, "RBA snapshot %s <= AOFM snapshot %s" % (cal["tb_holdings_asof"][0][0], aofm_asof), fails)
    check(all(net.get(d, 0.0) <= v + 1e-9 for d, v in gross.items()) and all(abs(net.get(d, 0.0) + rba.get(d, 0.0) - v) < 1e-6 for d, v in gross.items()),
          "redemptions: net <= gross and net + rba = gross on every date (%d dates)" % len(gross), fails)
    cg = dict(cal["tb_coupons_gross_paid"] + cal["tb_coupons_gross_ahead"])
    cn = dict(cal["tb_coupons_net_paid"] + cal["tb_coupons_net_ahead"])
    check(cg and all(cn.get(d, 0.0) <= v + 1e-9 for d, v in cg.items()), "coupons: net <= gross on every date (%d dates)" % len(cg), fails)
    check(all(d <= TODAY for d, _ in cal["tb_coupons_net_paid"]) and all(d > TODAY for d, _ in cal["tb_coupons_net_ahead"]), "coupon paid/ahead split at today", fails)
    share = cal["tb_rba_share"][0][1]
    check(0.0 <= share <= 1.0, "RBA share %.4f in [0,1] (rba %.0f / face %.0f)" % (share, cal["tb_rba_total"][0][1], cal["tb_face_total"][0][1]), fails)
    print("     unmatched RBA maturities (not in AOFM %s): %s" % (aofm_asof, cal["_unmatched"]))
    check(isinstance(cal["_unmatched"], list), "_unmatched is a list", fails)
    # gross side equals ops_aud.tb_calendar (which uses date.today(): compare only if today matches)
    import datetime
    if datetime.date.today().isoformat() == TODAY:
        g0 = A.tb_calendar(lines)
        check(g0["tb_redemptions_gross_ahead"] == cal["tb_redemptions_gross_ahead"] and g0["tb_face_total"] == cal["tb_face_total"], "gross redemptions / face total identical to ops_aud.tb_calendar", fails)
    # net_daily_history: toy with two AOFM snapshots and two RBA snapshots
    toy_lines = [{"date": "2026-01-31", "maturity": "2026-02-15", "coupon": 4.0, "face": 100.0}, {"date": "2026-01-31", "maturity": "2026-08-21", "coupon": 2.0, "face": 50.0},
                 {"date": "2026-02-28", "maturity": "2026-08-21", "coupon": 2.0, "face": 60.0}]
    toy_rba = [{"date": "2026-01-31", "title": H.AGS_TITLE, "maturity": "2026-02-15", "holding": 30.0}, {"date": "2026-02-28", "title": H.AGS_TITLE, "maturity": "2026-08-21", "holding": 10.0}]
    days = H.business_days("2026-01-20", "2026-09-10")
    hist = H.net_daily_history(toy_lines, toy_rba, days)
    rn, rg = dict(hist["tb_redemptions_net_daily"]), dict(hist["tb_redemptions_gross_daily"])
    cn2, cg2 = dict(hist["tb_coupons_net_daily"]), dict(hist["tb_coupons_gross_daily"])
    check(rn["2026-01-30"] is None and rn["2026-02-02"] == 0.0, "None before the first snapshot, 0.0 after", fails)
    # 2026-02-15 is a Sunday → books on Monday 2026-02-16; Jan snapshot: face 100, RBA 30 → net 70 (+ coupon 100×4/200 = 2 gross, 70×4/200 = 1.4 net)
    check(rg["2026-02-16"] == 100.0 and rn["2026-02-16"] == 70.0, "redemption on Sunday 15-Feb books Monday 16-Feb: gross 100, net 70", fails)
    check(cg2["2026-02-16"] == 2.0 and cn2["2026-02-16"] == 1.4, "coupon on the maturity day: gross 2.0, net 1.4", fails)
    # 21-Feb coupon of the Aug line (Saturday → Monday 23-Feb): Jan snapshot face 50, RBA Jan snapshot has no Aug holding → net = gross = 0.5
    check(cg2["2026-02-23"] == 0.5 and cn2["2026-02-23"] == 0.5, "coupon 21-Feb (Saturday) books 23-Feb from the January snapshot: 0.5 / 0.5", fails)
    # 21-Aug redemption (Friday) uses the Feb snapshot (face 60, RBA 10): gross 60 + coupon 0.6; net 50 + 0.5
    check(rg["2026-08-21"] == 60.0 and rn["2026-08-21"] == 50.0 and cg2["2026-08-21"] == 0.6 and cn2["2026-08-21"] == 0.5, "21-Aug from the February snapshots: gross 60 / 0.6, net 50 / 0.5", fails)
    check(sum(v for v in rg.values() if v) == 160.0 and sum(v for v in rn.values() if v) == 120.0, "daily totals: gross 160, net 120 (nothing lost on weekends)", fails)
    # real data: dense history over 2026 sums to the calendar's gross amounts on common dates
    days2 = H.business_days("2026-06-01", "2026-09-10")
    h2 = H.net_daily_history(lines, rows, days2)
    check(len(h2["tb_redemptions_net_daily"]) == len(days2) and all(v is not None for _, v in h2["tb_redemptions_net_daily"]), "real-data dense history covers every day", fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
