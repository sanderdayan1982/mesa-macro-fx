"""t331u: official publication calendar freshness («AL DÍA CON LA FUENTE»).

New tests only. Does not edit older tests, thresholds, or formulas.
  python -m ingest.tests_cad_official_calendar_freshness
"""
from __future__ import annotations
from datetime import date, datetime, timezone

from .quality import (
    freshness, weekly_friday_freshness, next_official_publication,
    official_calendar_freshness, evaluate_series,
)
from .blocks import entry, clamp_status, _health, _FRESH_RANK


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def _cfg():
    return {"status_rules": {"fresh_multiplier": 1.5, "stale_multiplier": 3.0,
                             "nominal_period_days": {"daily": 4, "weekly": 7, "monthly": 31},
                             "monthly_lag_allowance_days": 75}}


def _now(iso):
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def test_next_publication_dates(fails):
    check(next_official_publication("pspc_sqt_dcb", date(2026, 11, 2)) == date(2026, 12, 4),
          "PSPC last obs 2-nov → next expected publication 4-dic (monthly day 4)", fails)
    check(next_official_publication("statcan_10100116", date(2026, 9, 1)) == date(2026, 12, 26),
          "StatCan C2 last obs 1-sep (Oct not out) → month-end Oct + 8 weeks = 26-dic", fails)


def test_source_current_vs_stale(fails):
    r = official_calendar_freshness(date(2026, 11, 2), date(2026, 11, 22), "pspc_sqt_dcb")
    check(r["status"] == "source_current" and r["next_publication"] == "2026-12-04",
          "22-nov with RG last print 2-nov is AL DÍA CON LA FUENTE (next 4-dic)", fails)
    r2 = official_calendar_freshness(date(2026, 11, 2), date(2026, 12, 4), "pspc_sqt_dcb")
    check(r2["status"] == "source_current",
          "on the expected day itself it is still AL DÍA CON LA FUENTE", fails)
    r3 = official_calendar_freshness(date(2026, 11, 2), date(2026, 12, 5), "pspc_sqt_dcb")
    check(r3["status"] == "stale",
          "5-dic with no new RG batch after 4-dic is STALE", fails)

    s = official_calendar_freshness(date(2026, 9, 1), date(2026, 11, 22), "statcan_10100116")
    check(s["status"] == "source_current" and s["next_publication"] == "2026-12-26",
          "22-nov with C2 last print 1-sep is AL DÍA CON LA FUENTE (next 26-dic)", fails)
    s2 = official_calendar_freshness(date(2026, 9, 1), date(2026, 12, 27), "statcan_10100116")
    check(s2["status"] == "stale",
          "27-dic with October C2 still missing is STALE (calendar overdue)", fails)


def test_freshness_dispatcher_and_old_rules_untouched(fails):
    cfg = _cfg()
    fr = freshness("2026-11-02", "daily", cfg, now=_now("2026-11-22T16:00:00"), calendar="pspc_sqt_dcb")
    check(fr["status"] == "source_current" and fr["age_days"] == 20 and fr["next_publication"] == "2026-12-04",
          "freshness(..., calendar=pspc_sqt_dcb) returns source_current + next_publication", fails)
    # default 1.5×/3× unchanged (daily period 4): 20 days > 12 → stale
    old = freshness("2026-11-02", "daily", cfg, now=_now("2026-11-22T16:00:00"))
    check(old["status"] == "stale" and old["age_days"] == 20,
          "without calendar, 20-day-old daily print stays STALE under 1.5×/3×", fails)
    check(weekly_friday_freshness(date(2026, 11, 2), date(2026, 11, 22)) == "stale",
          "weekly_friday rule itself is unchanged (2-nov is STALE on 22-nov)", fails)


def test_entry_and_clamp(fails):
    cfg = _cfg()
    ser = [("2026-08-01", 2965.0), ("2026-09-01", 3407.0)]
    now = _now("2026-11-22T16:04:00")
    q = evaluate_series("government_deposits_banks", ser, "monthly", cfg, now=now, calendar="statcan_10100116")
    check(q["freshness"] == "source_current" and q["next_publication"] == "2026-12-26",
          "evaluate_series C2 on 22-nov is source_current", fails)
    e = entry("government_deposits_banks", ser, "GoC deposits at chartered banks (monthly)",
              "monthly", "CAD millions", cfg, "V36811", quality=q, freshness_calendar="statcan_10100116")
    check(e["status"] == "source_current" and e["date"] == "2026-09-01" and e["value"] == 3407.0,
          "entry keeps the official 1-sep value and shows source_current", fails)
    check(e["next_publication"] == "2026-12-26",
          "entry surfaces the expected next publication date", fails)

    # INTEGRIDAD-01: past the calendar, computed STALE wins over requested proxy
    q_stale = evaluate_series("fiscal_flow_7d_cum", [("2026-11-02", 1.0)], "daily", cfg,
                              now=_now("2026-12-05T00:00:00"), calendar="pspc_sqt_dcb")
    check(q_stale["freshness"] == "stale",
          "7d evaluate is STALE after the PSPC expected day", fails)
    e_stale = entry("fiscal_flow_7d_cum", [("2026-11-02", 1.0)], "Fiscal flow 7-day cumulative",
                    "daily", "CAD millions", cfg, status="proxy", freshness_calendar="pspc_sqt_dcb",
                    quality=q_stale)
    check(e_stale["status"] == "stale",
          "past the official calendar, computed STALE wins over requested PROXY (INTEGRIDAD-01)", fails)

    q_ok = evaluate_series("fiscal_flow_7d_cum", [("2026-11-02", 1.0)], "daily", cfg,
                           now=_now("2026-11-22T16:00:00"), calendar="pspc_sqt_dcb")
    e_ok = entry("fiscal_flow_7d_cum", [("2026-11-02", 1.0)], "Fiscal flow 7-day cumulative",
                 "daily", "CAD millions", cfg, status="proxy", freshness_calendar="pspc_sqt_dcb",
                 quality=q_ok)
    check(e_ok["status"] == "proxy" and e_ok["calendar_status"] == "source_current",
          "inside the official window, explicit PROXY is kept; calendar_status is source_current", fails)

    check(clamp_status("source_current", "proxy") == "proxy",
          "clamp does not treat source_current as stale (proxy may restated)", fails)
    check(_FRESH_RANK["source_current"] == _FRESH_RANK["fresh"],
          "source_current ranks with fresh", fails)


def test_block_health_counts_source_current_as_ok(fails):
    h = _health({"government_deposits_banks": {"status": "source_current"},
                 "government_account_cb": {"status": "fresh"},
                 "rg_closing_balance": {"status": "source_current"}}, 3)
    check(h["status"] == "fresh" and h["series_loaded"] == 3,
          "a fiscal block whose only lag is official-calendar current is FRESH, not STALE", fails)


def main():
    fails = []
    test_next_publication_dates(fails)
    test_source_current_vs_stale(fails)
    test_freshness_dispatcher_and_old_rules_untouched(fails)
    test_entry_and_clamp(fails)
    test_block_health_counts_source_current_as_ok(fails)
    if fails:
        print("FAILED %d" % len(fails))
        return 1
    print("ok   all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
