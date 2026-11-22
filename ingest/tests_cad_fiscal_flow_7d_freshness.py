"""t330u: Friday weekly presentation calendar for CAD fiscal_flow_7d_cum.

Does not edit older tests. The 7-day cumulative remains a daily rolling sum
(methodology unchanged). Only the freshness presentation rule changes.
  python -m ingest.tests_cad_fiscal_flow_7d_freshness
"""
from __future__ import annotations
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def _cfg():
    return {"status_rules": {"fresh_multiplier": 1.5, "stale_multiplier": 3.0,
                             "nominal_period_days": {"daily": 4, "weekly": 7, "monthly": 31}}}


def _now(iso):
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def test_weekly_friday_calendar(fails):
    from .quality import freshness, weekly_friday_freshness
    from datetime import date

    # Last print Friday 13-nov-2026 (ISO week 46). Following week ends Sun 22-nov.
    check(freshness("2026-11-13", "daily", _cfg(), now=_now("2026-11-13T18:00:00"),
                    calendar="weekly_friday")["status"] == "fresh",
          "Friday of the print week is FRESH", fails)
    check(freshness("2026-11-13", "daily", _cfg(), now=_now("2026-11-15T23:00:00"),
                    calendar="weekly_friday")["status"] == "fresh",
          "Sunday of the print week is still FRESH", fails)
    check(freshness("2026-11-13", "daily", _cfg(), now=_now("2026-11-16T08:00:00"),
                    calendar="weekly_friday")["status"] == "fresh",
          "Monday of the following week is still FRESH", fails)
    check(freshness("2026-11-13", "daily", _cfg(), now=_now("2026-11-22T18:00:00"),
                    calendar="weekly_friday")["status"] == "fresh",
          "Sunday of the following week is still FRESH (not yet past it)", fails)
    check(freshness("2026-11-13", "daily", _cfg(), now=_now("2026-11-23T00:00:00"),
                    calendar="weekly_friday")["status"] == "stale",
          "Monday after the following week is STALE", fails)

    # Default 1.5×/3× rule is unchanged when calendar is omitted (daily period 4).
    # 13-nov → 22-nov is 9 days > 1.5×4=6 and <= 3×4=12 → stale under the old rule.
    old = freshness("2026-11-13", "daily", _cfg(), now=_now("2026-11-22T18:00:00"))
    check(old["status"] == "stale" and old["age_days"] == 9,
          "without calendar, 9-day-old daily print stays STALE (1.5×/3× untouched)", fails)

    check(weekly_friday_freshness(date(2026, 11, 2), date(2026, 11, 22)) == "stale",
          "last print Mon 2-nov: following week ended 15-nov, 22-nov is STALE", fails)
    check(weekly_friday_freshness(date(2026, 11, 20), date(2026, 11, 22)) == "fresh",
          "last print Friday 20-nov is FRESH on Sunday 22-nov (same week)", fails)


def test_cad_7d_entry_uses_calendar_not_methodology(fails):
    """frequency stays daily; clamp keeps PROXY inside the window and STALE past it."""
    from .blocks import entry

    cfg = _cfg()
    # Rolling 7d ending Friday 13-nov, observed Sunday 22-nov (still inside following week).
    # Patch now via evaluate path: entry uses datetime.now unless we pass quality.
    # Call freshness through entry by building a short series and a pinned evaluate.
    from .quality import evaluate_series
    ser = [("2026-11-07", 1.0), ("2026-11-13", 2.0)]
    now = _now("2026-11-22T18:00:00")
    q = evaluate_series("fiscal_flow_7d_cum", ser, "daily", cfg, now=now, calendar="weekly_friday")
    check(q["freshness"] == "fresh" and q["last_valid_date"] == "2026-11-13",
          "evaluate_series with weekly_friday is FRESH on 22-nov for a 13-nov print", fails)
    e = entry("fiscal_flow_7d_cum", ser, "Fiscal flow 7-day cumulative", "daily", "CAD millions",
              cfg, usd_analog="7-day cumulative", status="proxy", freshness_calendar="weekly_friday",
              quality=q)
    check(e["frequency"] == "daily" and e["date"] == "2026-11-13" and e["value"] == 2.0,
          "methodology fields (frequency daily, last value/date) are unchanged", fails)
    check(e["status"] == "proxy",
          "inside the window, explicit PROXY is kept (not STALE, not promoted past clamp)", fails)

    q_stale = evaluate_series("fiscal_flow_7d_cum", ser, "daily", cfg,
                              now=_now("2026-11-23T00:00:00"), calendar="weekly_friday")
    check(q_stale["freshness"] == "stale",
          "evaluate_series is STALE on Mon 23-nov after the following week", fails)
    e_stale = entry("fiscal_flow_7d_cum", ser, "Fiscal flow 7-day cumulative", "daily", "CAD millions",
                    cfg, usd_analog="7-day cumulative", status="proxy", freshness_calendar="weekly_friday",
                    quality=q_stale)
    check(e_stale["status"] == "stale",
          "past the following week, computed STALE wins over requested PROXY (INTEGRIDAD-01)", fails)


def main():
    fails = []
    test_weekly_friday_calendar(fails)
    test_cad_7d_entry_uses_calendar_not_methodology(fails)
    if fails:
        print("FAILED %d" % len(fails))
        return 1
    print("ok   all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
