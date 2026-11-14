"""ORDEN INTEGRIDAD-01 (Sander 14-nov-2026). One new check per case. Does not edit older tests.

  python -m ingest.tests_integridad_01
"""
from __future__ import annotations
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def _cfg():
    return {"units": {"balance_sheet": "GBP millions"},
            "status_rules": {"fresh_multiplier": 1.5, "stale_multiplier": 3.0,
                             "nominal_period_days": {"daily": 4, "weekly": 7, "monthly": 31}}}


def test_a2(fails):
    """A stale print requested as fresh stays stale. The value and its own date stay."""
    from datetime import date, timedelta
    from .blocks import entry, clamp_status
    from .blocks_gbp_v04 import enrich_central_bank
    cfg = _cfg()
    stale = [("2020-08-21", 0.0), ("2020-08-28", 0.0)]
    e = entry("ctrf_net_daily", stale, "CTRF net flow", "daily", "GBP millions", cfg, status="fresh")
    check(e["status"] == "stale" and e["value"] == 0.0 and e["date"] == "2020-08-28",
          "A2 entry(status='fresh') does not promote a 2020-08-28 print", fails)
    today = date.today().isoformat()
    yday = (date.today() - timedelta(days=1)).isoformat()
    fresh = entry("x", [(yday, 1.0), (today, 2.0)], "x", "daily", "u", cfg, status="fresh")
    check(fresh["status"] == "fresh", "A2 a print from today stays fresh", fails)
    down = entry("x", [(today, 2.0)], "x", "daily", "u", cfg, status="unavailable")
    check(down["status"] == "unavailable", "A2 an explicit downgrade is kept", fails)
    empty = entry("x", [], "x", "daily", "u", cfg, status="fresh")
    check(empty["status"] == "unavailable" and empty["value"] is None, "A2 an empty series is unavailable, not 0", fails)
    check(clamp_status("stale", "fresh") == "stale" and clamp_status("stale", "proxy") == "stale"
          and clamp_status("fresh", "proxy") == "proxy" and clamp_status("stale", "unavailable") == "unavailable",
          "A2 clamp_status refuses to improve stale and still allows a downgrade", fails)
    block = {"derived": {}, "series": {"apf_gilt_sales_by_bucket": {"label": "APF"}},
             "history": {"dates": ["2026-11-12"], "rows": {"reserves": [100000.0]}}, "signals": {}}
    sales = [("2026-09-09", -1.0), ("2026-09-10", -1.0), ("2026-09-11", -1.0), ("2026-09-12", -1.0), ("2026-09-15", -724.902)]
    enrich_central_bank(block, cfg, {"ctrf_net_daily": stale}, {"apf_sales_daily": sales}, {})
    D = block["derived"]
    bucket = block["series"]["apf_gilt_sales_by_bucket"]
    check(D["ctrf_net_daily"]["status"] == "stale" and D["apf_sales_daily"]["status"] == "stale"
          and D["apf_sales_5d"]["status"] == "stale" and bucket["status"] == "stale",
          "A2 GBP v0.4 apf_sales_daily / apf_sales_5d / ctrf_net_daily / apf bucket stay stale", fails)
    check(D["apf_sales_5d"]["date"] == "2026-09-15" and D["ctrf_net_daily"]["date"] == "2020-08-28",
          "A2 the stale prints keep their own dates", fails)
    flows = (block["signals"]["components_v04"].get("flow") or {})
    check("apf_sales_5d_pct" not in flows, "A2 a stale APF 5-session sum does not enter the shadow vote", fails)


def test_a3(fails):
    """Net liquidity requires one common date. 11-nov must not subtract 10-nov ON RRP."""
    from .blocks_usd import net_liquidity_on_common_dates
    wa = [("2026-11-04", 6748145.0), ("2026-11-11", 6758867.0)]
    tga = [("2026-11-04", 957175.0), ("2026-11-11", 914370.0)]
    rrp = [("2026-11-04", 225.0), ("2026-11-10", 152.0), ("2026-11-13", 325.0)]
    nl, dates = net_liquidity_on_common_dates(wa, tga, rrp)
    mixed = round(6758867.0 - 914370.0 - 152.0, 1)
    check(dict(nl).get("2026-11-11") is None and all(d != "2026-11-11" for d, _ in nl),
          "A3 2026-11-11 is absent: ON RRP has no print that day", fails)
    check(dict(nl).get("2026-11-04") == round(6748145.0 - 957175.0 - 225.0, 1),
          "A3 2026-11-04 uses the ON RRP of that same date (225), not a later or earlier print", fails)
    check(mixed not in [v for _, v in nl], "A3 the mixed-date identity (11-nov assets − 10-nov RRP) is not published", fails)
    check(dates == {"total_assets": "2026-11-04", "tga": "2026-11-04", "on_rrp": "2026-11-04"},
          "A3 component_dates are the three dates that entered the printed point", fails)
    nl0, dates0 = net_liquidity_on_common_dates([("2026-11-11", 6758867.0)], [("2026-11-11", 914370.0)], [("2026-11-10", 152.0)])
    check(nl0 == [] and dates0["total_assets"] == "2026-11-11" and dates0["tga"] == "2026-11-11" and dates0["on_rrp"] == "2026-11-10",
          "A3 with no common date the result is absent and each leg keeps its own latest date", fails)


def test_a6(fails):
    """Absence is «—» and direction None. A real zero stays 0 / NEUTRAL. No alert against None."""
    from . import liquidity_reporter as L
    from . import notify as N
    cb = {"as_of": "2026-11-14", "series": {"cab_daily": {"value": None, "date": None}},
          "derived": {"ops_net_5d": {"value": None, "date": None}}}
    fi = {"as_of": "2026-11-14", "series": {}, "derived": {}}
    out = L._build_jpy(cb, fi, {})
    check("0,0" not in out["cb_message"] and "¥0" not in out["cb_message"],
          "A6 a missing JPY flow is not printed as ¥0,0", fails)
    check(out["cb_direction"] is None and out["treasury_direction"] is None,
          "A6 direction is None when the input is missing", fails)
    check(out["cb_date"] == "—" and L._dt(cb, "series", "cab_daily") == "—",
          "A6 _dt does not inherit the block as_of (2026-11-14)", fails)
    zero = L._build_jpy(
        {"series": {"cab_daily": {"value": 0.0, "date": "2026-11-13", "change_abs": 0.0}},
         "derived": {"ops_net_5d": {"value": 0.0, "date": "2026-11-13"}}},
        {"series": {"government_account": {"value": 0.0, "date": "2026-11-13"}},
         "derived": {"treasury_realized_daily": {"value": 0.0, "date": "2026-11-13"},
                     "treasury_realized_5d": {"value": 0.0}, "net_issuance_private_5d": {"value": 0.0}}},
        {})
    check(zero["cb_direction"] == "NEUTRAL" and zero["treasury_direction"] == "NEUTRAL",
          "A6 a real zero stays NEUTRAL", fails)
    usd = L._build_usd(
        {"as_of": "2026-11-14", "series": {"reserves": {"value": None, "date": None}, "on_rrp": {}, "treasury_securities": {}}},
        {"series": {"tga_closing": {"value": None, "date": None}}, "derived": {}}, {})
    check(usd["cb_direction"] is None and "mantiene estables" not in usd["cb_message"] and "US$0,0" not in usd["treasury_message"],
          "A6 USD does not call a missing reserve change 'estable' or print US$0,0", fails)
    held = L._build_usd(
        {"series": {"reserves": {"value": 1000.0, "date": "2026-11-12", "change_abs": 0.0}, "on_rrp": {"value": 1.0, "date": "2026-11-13"},
                    "treasury_securities": {"value": 1.0, "change_abs": 0.0}},
         "derived": {"on_rrp_dod": {"value": 0.0}, "on_rrp_impulse_5d": {"value": 0.0}}},
        {"series": {"tga_closing": {"value": 5.0, "date": "2026-11-12"}},
         "derived": {"tga_dod": {"value": 0.0}, "tga_reserve_impact": {"value": 0.0},
                     "net_treasury_flow": {"value": 0.0}, "net_treasury_flow_7d": {"value": 0.0}}}, {})
    check(held["cb_direction"] == "NEUTRAL" and "mantiene estables" in held["cb_message"] and "US$0,0" in held["treasury_message"],
          "A6 a real zero reserve change stays 'estable' and US$0,0", fails)
    base = {"as_of": "2026-11-14", "generated_at": "2026-11-14T00:00:00Z", "general": "NEUTRAL", "central_bank": "NEUTRAL",
            "fiscal": "NEUTRAL", "gate": True, "gate_failures": [], "hash": "h", "streaks": {},
            "blocks": {"central_bank": "fresh", "fiscal": "fresh"}, "blocks_asof": {}, "blocks_cadence": {},
            "errors": [], "F1": "", "F5": "", "degraded": [], "lane": "daily", "fiscal_engine": None, "price_gate": None, "flags": []}
    cfg = {"events": {"liquidity_flow_change": {"enabled": True}, "regime_change_general": {"enabled": False},
                      "regime_change_block": {"enabled": False}, "gate_withheld": {"enabled": False},
                      "block_degraded": {"enabled": False}, "refresh_error": {"enabled": False},
                      "jefe_ranking_change": {"enabled": False}}}
    msg = "🇯🇵 sin dato"
    prev = dict(base, liquidity_bulletin={"cb_date": "2026-11-13", "cb_direction": "NEUTRAL", "cb_message": msg,
                                          "treasury_date": "2026-11-13", "treasury_direction": "INJECTION", "treasury_message": msg})
    cur = dict(base, liquidity_bulletin={"cb_date": "2026-11-13", "cb_direction": None, "cb_message": msg,
                                         "treasury_date": None, "treasury_direction": None, "treasury_message": msg})
    ev = N.events_for("jpy", cur, prev, {}, None, cfg)
    check(not any("FLUJO LIQUIDEZ" in x for x in ev), "A6 notify does not alert when comparing a direction or date with None", fails)
    cur2 = dict(base, liquidity_bulletin={"cb_date": "2026-11-13", "cb_direction": "DRAIN", "cb_message": msg,
                                          "treasury_date": "2026-11-13", "treasury_direction": "INJECTION", "treasury_message": msg})
    ev2 = N.events_for("jpy", cur2, prev, {}, None, cfg)
    check(any("FLUJO LIQUIDEZ BC" in x for x in ev2), "A6 notify still alerts a real NEUTRAL → DRAIN giro", fails)


def main() -> int:
    fails = []
    test_a2(fails)
    test_a3(fails)
    test_a6(fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
