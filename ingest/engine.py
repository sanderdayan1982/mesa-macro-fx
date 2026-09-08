"""Regime / scenarios / alerts / revisions / calendar / oplog — the cross-block engine.
Ported from v2.0 regime.mjs, scenarios.mjs, alerts.mjs, revisions.mjs, oplog.mjs, holidays.mjs and rewritten on
the Desk Standard: weighted block scores, LIQUIDITY_SCARCITY and FLOOR_FRICTION rules, orthogonal flags."""
from __future__ import annotations
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

LEVEL_RANK = {"NO DATA": -1, "SAFE": 0, "WATCH": 1, "STRESS": 2, "CRISIS": 3}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ───────────────────────────── regime ─────────────────────────────
def _get(blocks: Dict[str, dict], path: str):
    """'central_bank.reserves' -> entry dict (series or derived)."""
    blk, key = path.split(".", 1)
    b = blocks.get(blk) or {}
    return (b.get("series", {}).get(key) or b.get("derived", {}).get(key) or {})


def classify_regime(cfg: dict, blocks: Dict[str, dict]) -> dict:
    rc = cfg["regime"]
    w = rc["weights"]
    scores, used = {}, 0
    for name, weight in w.items():
        b = blocks.get(name)
        if b and b["signals"]["traffic_light"] != "NONE":
            scores[name] = b["signals"]["score"]
            used += 1
    tot_w = sum(w[n] for n in scores) or 1.0
    weighted = round(sum(w[n] * s for n, s in scores.items()) / tot_w, 3)
    res = _get(blocks, rc.get("reserves_metric", "central_bank.reserves"))
    spr = _get(blocks, rc.get("stress_spread_metric", "rates.overnight_minus_deposit_bps"))
    r_lvl, s_lvl = res.get("level", "NO DATA"), spr.get("level", "NO DATA")
    in_range = res.get("in_range")
    ample = bool(in_range or res.get("above_range"))
    # friction needs price confirmation; blocks may supply a persistence-based flag (GBP), else level >= WATCH (CAD)
    friction = spr.get("friction_confirmed") if "friction_confirmed" in spr else LEVEL_RANK[s_lvl] >= LEVEL_RANK["WATCH"]
    if used < rc.get("min_blocks_for_signal", 2):
        regime = "NO SIGNAL"
    elif in_range is False and not res.get("above_range") and r_lvl in ("WATCH", "STRESS", "CRISIS") and LEVEL_RANK[s_lvl] >= LEVEL_RANK["STRESS"]:
        regime = "LIQUIDITY_SCARCITY"
    elif ample and friction:
        regime = "FLOOR_FRICTION" if weighted > -0.5 else "LIQUIDITY_DRAIN"
    elif weighted <= -0.5:
        regime = "LIQUIDITY_DRAIN"
    elif weighted >= 0.5:
        regime = "LIQUIDITY_INJECTION"
    else:
        regime = "NEUTRAL"
    flags = []
    tsig = _get(blocks, "banking.transmission_signal").get("signal")
    if tsig == "RED" and (in_range or res.get("above_range")):
        flags.append("TRANSMISSION_FAILURE")
    if ample and friction and regime != "FLOOR_FRICTION":
        flags.append("FLOOR_FRICTION")
    phase = _get(blocks, "central_bank.balance_sheet_phase").get("phase")
    if phase:
        flags.append("PHASE_" + phase)
    # block-supplied orthogonal flags (GBP: CTRF_ACTIVE, REPO_DEPENDENCE_*, FISCAL_BIG_MONTH, QT_ACCELERATION)
    price_stress = LEVEL_RANK[s_lvl] >= LEVEL_RANK["STRESS"] or bool(spr.get("friction_confirmed"))
    for bname, blk in blocks.items():
        for f in (blk.get("signals") or {}).get("flags", []) or []:
            if f == "REPO_DEPENDENCE_ELEVATED":
                flags.append("REPO_DEPENDENCE_STRESS" if price_stress else "REPO_DEPENDENCE_HEALTHY")
            elif f not in flags:
                flags.append(f)
    pace = rc.get("qt_announced_pace_per_week")
    qt = _get(blocks, "central_bank.qt_pace")
    if pace and qt.get("sparkline"):
        recent = [v for v in qt["sparkline"][-13:] if v is not None]
        if recent and sum(recent) / len(recent) < pace * 1.25:
            flags.append("QT_ACCELERATION")
    overlays = _overlays(cfg, blocks)
    for ov, st in overlays.items():
        if isinstance(st, str) and st.endswith("_HIGH") and ov not in flags:
            flags.append(ov)
    tl = {"LIQUIDITY_INJECTION": "GREEN", "NEUTRAL": "YELLOW", "FLOOR_FRICTION": "YELLOW", "LIQUIDITY_DRAIN": "RED", "LIQUIDITY_SCARCITY": "RED", "NO SIGNAL": "NONE"}[regime]
    return {"regime": regime, "traffic_light": tl, "weighted_score": weighted, "block_scores": scores, "weights": w, "blocks_used": used,
            "flags": flags, "overlays": overlays, "inputs": {"reserves_level": r_lvl, "reserves_in_range": in_range, "reserves_above_range": res.get("above_range"), "spread_level": s_lvl, "spread_bps": spr.get("value"), "friction_confirmed": friction},
            "rules": rc.get("rules", {})}


def _overlays(cfg: dict, blocks: Dict[str, dict]) -> Dict[str, Optional[str]]:
    """Regime overlays (JPY v0.2 QT_STRESS): counted conditions in the scenario mini-language; result <NAME>_LOW/_HIGH or None."""
    out: Dict[str, Optional[str]] = {}
    for name, ov in (cfg.get("regime", {}).get("overlays") or {}).items():
        conds = ov.get("conditions") or []
        n = 0
        for c in conds:
            try:
                if _resolve_condition(c, blocks):
                    n += 1
            except Exception:
                pass
        need = ov.get("min", 2)
        out[name] = None if not conds else ("%s_HIGH" % name if n >= need else "%s_LOW" % name if n > 0 else None)
        out[name + "_conditions_met"] = n  # type: ignore
    return out


# ───────────────────────────── scenarios ─────────────────────────────
def _resolve_condition(cond: str, blocks: Dict[str, dict]) -> Optional[bool]:
    """Mini-language: '<path> level >= WATCH' | '<path> level == SAFE' | '<path> <= drain' | '<path> >= injection' |
    '<path> <= p20' | '<path> > 0' | '<path> == RED' | '<path> mom_pct zscore >= 1'."""
    parts = cond.split()
    path = parts[0]
    e = _get(blocks, path)
    if parts[1] == "level":
        lvl = e.get("level", "NO DATA")
        op, tgt = parts[2], parts[3]
        if lvl == "NO DATA":
            return None
        return {"==": LEVEL_RANK[lvl] == LEVEL_RANK[tgt], ">=": LEVEL_RANK[lvl] >= LEVEL_RANK[tgt], "<=": LEVEL_RANK[lvl] <= LEVEL_RANK[tgt]}[op]
    if parts[1] == "mom_pct":  # banking.<k> mom_pct zscore >= 1
        e = _get(blocks, path + "_mom_pct")
        z = e.get("zscore")
        if z is None:
            return None
        op, tgt = parts[3], float(parts[4])
        return z >= tgt if op == ">=" else z <= tgt
    op, tgt = parts[1], parts[2]
    if tgt in ("RED", "GREEN", "YELLOW"):
        return (e.get("signal") == tgt) if e.get("signal") else None
    if tgt in ("risk_off", "risk_on"):
        return (e.get("signal") == tgt.upper()) if e.get("signal") not in (None, "NO DATA") else None
    if tgt in ("drain", "injection"):
        reg = e.get("regime") or (blocks.get("fiscal", {}).get("derived", {}).get("fiscal_regime", {}).get("regime"))
        if reg in (None, "NO DATA"):
            return None
        return reg == tgt.upper()
    v = e.get("value")
    if v is None:
        return None
    if tgt.startswith("p"):
        pr = e.get("percentile")
        if pr is None:
            return None
        p = float(tgt[1:])
        return pr <= p if op == "<=" else pr >= p
    t = float(tgt)
    return {">": v > t, "<": v < t, ">=": v >= t, "<=": v <= t, "==": v == t}[op]


def evaluate_scenarios(cfg: dict, blocks: Dict[str, dict]) -> List[dict]:
    out = []
    for sc in cfg.get("scenarios", {}).get("items", []):
        det = []
        for cnd in sc["conditions"]:
            try:
                met = _resolve_condition(cnd, blocks)
            except Exception:
                met = None
            det.append({"condition": cnd, "met": met})
        n = sum(1 for d in det if d["met"])
        out.append({"id": sc["id"], "name": sc["name"], "bias": sc["bias"], "active": n >= sc["min"], "conditions_met": n, "total": len(det), "details": det})
    return out


# ───────────────────────────── alerts ─────────────────────────────
def _rule_hit(rule: dict, blocks: Dict[str, dict], quality: dict) -> Optional[bool]:
    when, metric = rule["when"], rule["metric"]
    if metric.startswith("quality."):
        v = quality.get("system", {}).get(metric.split(".")[-1])
        return None if v is None else v > 0
    e = _get(blocks, metric)
    if when.startswith("level"):
        lvl = e.get("level", "NO DATA")
        if lvl == "NO DATA":
            return None
        op, tgt = when.split()[1], when.split()[2]
        return LEVEL_RANK[lvl] >= LEVEL_RANK[tgt] if op == ">=" else LEVEL_RANK[lvl] == LEVEL_RANK[tgt]
    if when == "<= risk_off":
        return None if not e.get("signal") else e["signal"] == "RISK_OFF"
    if when == "<= drain":
        reg = blocks.get("fiscal", {}).get("derived", {}).get("fiscal_regime", {}).get("regime")
        return None if reg in (None, "NO DATA") else reg == "DRAIN"
    if when.startswith("abs"):
        v = e.get("value")
        return None if v is None else abs(v) >= float(when.split()[-1])
    if when == "== RED":
        return None if not e.get("signal") else e["signal"] == "RED"
    v = e.get("value")
    if v is None:
        return None
    op, t = when.split()[0], float(when.split()[1])
    return {">": v > t, "<": v < t, ">=": v >= t, "<=": v <= t}[op]


def evaluate_alerts(cfg: dict, blocks: Dict[str, dict], quality: dict, existing: List[dict]) -> List[dict]:
    now = now_iso()
    active = {a["rule_id"]: a for a in existing if a.get("status") == "active"}
    out = [a for a in existing if a.get("status") != "active"]
    for rule in cfg.get("alerts", {}).get("rules", []):
        hit = _rule_hit(rule, blocks, quality)
        e = _get(blocks, rule["metric"]) if not rule["metric"].startswith("quality.") else {}
        if hit and rule["id"] not in active:
            out.append({"id": "alert_%s_%s" % (now.replace(":", ""), rule["id"]), "rule_id": rule["id"], "timestamp": now, "severity": rule["severity"],
                        "category": rule["category"], "metric": rule["metric"], "value": e.get("value"), "level": e.get("level"), "message": "%s: %s (%s)" % (rule["category"], rule["metric"], rule["when"]), "status": "active"})
        elif hit and rule["id"] in active:
            a = dict(active[rule["id"]])
            a["value"], a["last_seen"] = e.get("value"), now
            out.append(a)
        elif hit is False and rule["id"] in active:
            a = dict(active[rule["id"]])
            a["status"], a["resolved_at"] = "resolved", now
            out.append(a)
        elif hit is None and rule["id"] in active:
            out.append(active[rule["id"]])  # keep, data missing
    return out[-cfg.get("alerts", {}).get("keep_last", 100):]


# ───────────────────────────── revisions ─────────────────────────────
def detect_revisions(prev_hist: Dict[str, Dict[str, float]], new_hist: Dict[str, Dict[str, float]], keep: List[str]) -> List[dict]:
    out = []
    now = now_iso()
    for name in keep:
        p, n = prev_hist.get(name) or {}, new_hist.get(name) or {}
        for d, v in n.items():
            if d in p and p[d] is not None and v is not None and abs(p[d] - v) > 1e-9:
                delta = v - p[d]
                out.append({"series": name, "date": d, "old_value": p[d], "new_value": v, "delta": round(delta, 4),
                            "delta_pct": round(delta / abs(p[d]) * 100, 4) if p[d] else None, "detected_at": now})
    return out


def block_history_map(block: dict) -> Dict[str, Dict[str, float]]:
    h = block.get("history", {})
    dates = h.get("dates", [])
    return {k: {d: v for d, v in zip(dates, vals)} for k, vals in h.get("rows", {}).items()}


# ───────────────────────────── calendar ─────────────────────────────
def build_calendar(cfg: dict, blocks: Dict[str, dict]) -> dict:
    cal = cfg.get("calendar", {})
    now = datetime.now(timezone.utc)
    items = []
    if cfg.get("currency") == "GBP":
        return _calendar_gbp(cfg, cal, now)
    if cfg.get("currency") == "AUD":
        return _calendar_aud(cfg, cal, now)
    if cfg.get("currency") == "JPY":
        return _calendar_jpy(cfg, cal, now)
    if cfg.get("currency") == "CHF":
        return _calendar_chf(cfg, cal, now)
    for d in cal.get("boc_decision_dates_2026", []):
        items.append({"date": d, "title": "BoC rate decision" + (" + MPR" if d in cal.get("boc_mpr_dates_2026", []) else ""), "type": "central_bank", "impact": "HIGH", "time_local": cal.get("decision_time", "")})
    # next weekly B2 (Friday) and next daily/RG
    d = now.date()
    while d.weekday() != 4:
        d += timedelta(days=1)
    items.append({"date": d.isoformat(), "title": "BoC weekly balance sheet (B2, data as of Wednesday)", "type": "central_bank", "impact": "HIGH", "time_local": "14:30 ET"})
    items.append({"date": (now.date() + timedelta(days=1)).isoformat(), "title": "CORRA + benchmark yields (daily)", "type": "rates", "impact": "MEDIUM", "time_local": "09:00 ET / 16:00 ET"})
    items.append({"date": None, "title": "Receiver General Daily Cash Balance (batch, ~weekly)", "type": "fiscal", "impact": "MEDIUM", "time_local": ""})
    items.append({"date": None, "title": "Chartered banks C1/C2 month-end (Valet, ~75-day lag)", "type": "banking", "impact": "LOW", "time_local": ""})
    for h in cal.get("ca_market_holidays_2026", []):
        items.append({"date": h, "title": "Canada market holiday", "type": "holiday", "impact": "LOW", "time_local": ""})
    def _k(x):
        return x["date"] or "9999"
    upcoming = sorted([i for i in items if (i["date"] or "9999") >= now.date().isoformat()], key=_k)
    for i in upcoming:
        if i["date"]:
            i["days_until"] = (datetime.strptime(i["date"], "%Y-%m-%d").date() - now.date()).days
    return {"currency": cfg["currency"], "block": "calendar", "generated_at": now_iso(), "timezone_operator": cfg.get("timezone_operator"),
            "wat_offset_note": "ET+5h in summer, ET+6h in winter", "upcoming": upcoming[:40], "source_health": {"status": "fresh", "series_loaded": 1, "series_expected": 1, "last_fetch_ok": True, "errors": []},
            "series": {}, "derived": {}, "signals": {"traffic_light": "NONE", "score": 0, "label": "CALENDAR"}, "history": {}}


# ───────────────────────────── oplog ─────────────────────────────
def log_event(path: str, etype: str, category: str, details: dict, keep: int = 500) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    log = {"entries": []}
    if os.path.exists(path):
        try:
            log = json.load(open(path))
        except Exception:
            pass
    log["entries"].insert(0, {"timestamp": now_iso(), "type": etype, "category": category, "details": details})
    log["entries"] = log["entries"][:keep]
    json.dump(log, open(path, "w"), indent=1)


def _calendar_gbp(cfg: dict, cal: dict, now: datetime) -> dict:
    items = []
    for d in cal.get("mpc_decision_dates_2026", []) + cal.get("mpc_decision_dates_2027_provisional", []):
        items.append({"date": d, "title": "MPC decision" + (" + Monetary Policy Report" if d in cal.get("mpc_mpr_dates_2026", []) else ""), "type": "central_bank", "impact": "HIGH", "time_local": cal.get("decision_time", "12:00 London")})
    d = now.date()
    while d.weekday() != 3:
        d += timedelta(days=1)
    items.append({"date": d.isoformat(), "title": "BoE Weekly Report B1.1.2 (data as of Wednesday)", "type": "central_bank", "impact": "HIGH", "time_local": "15:00 London"})
    items.append({"date": (now.date() + timedelta(days=1)).isoformat(), "title": "SONIA + gilt par yields (daily, IADB)", "type": "rates", "impact": "MEDIUM", "time_local": "09:00 / 16:00 London"})
    y, m = now.year, now.month
    ons = datetime(y, m, 22).date() if now.day <= 22 else datetime(y + (m == 12), m % 12 + 1, 22).date()
    items.append({"date": ons.isoformat(), "title": "ONS Public Sector Finances (monthly, ~3-week lag)", "type": "fiscal", "impact": "MEDIUM", "time_local": "07:00 London"})
    mc = datetime(y + (m == 12), m % 12 + 1, 1).date()
    items.append({"date": mc.isoformat(), "title": "BoE Money & Credit (monthly)", "type": "banking", "impact": "LOW", "time_local": "09:30 London"})
    for h in cal.get("uk_bank_holidays_2026", []):
        items.append({"date": h, "title": "UK bank holiday", "type": "holiday", "impact": "LOW", "time_local": ""})
    upcoming = sorted([i for i in items if (i["date"] or "9999") >= now.date().isoformat()], key=lambda x: x["date"] or "9999")
    for i in upcoming:
        if i["date"]:
            i["days_until"] = (datetime.strptime(i["date"], "%Y-%m-%d").date() - now.date()).days
    return {"currency": cfg["currency"], "block": "calendar", "generated_at": now_iso(), "timezone_operator": cfg.get("timezone_operator"),
            "wat_offset_note": "London = WAT in winter (GMT), WAT−1h in summer (BST)", "upcoming": upcoming[:40], "source_health": {"status": "fresh", "series_loaded": 1, "series_expected": 1, "last_fetch_ok": True, "errors": []},
            "series": {}, "derived": {}, "signals": {"traffic_light": "NONE", "score": 0, "label": "CALENDAR"}, "history": {}}


def _calendar_aud(cfg: dict, cal: dict, now: datetime) -> dict:
    items = []
    for d in cal.get("rba_board_dates_2026", []):
        items.append({"date": d, "title": "RBA Monetary Policy Board decision", "type": "central_bank", "impact": "HIGH", "time_local": cal.get("decision_time", "14:30 Sydney")})
    d = now.date()
    while d.weekday() != 2:
        d += timedelta(days=1)
    items.append({"date": d.isoformat(), "title": "RBA weekly OMO (7d + 28d, full allotment at target + 10 bp)", "type": "central_bank", "impact": "MEDIUM", "time_local": "09:20 Sydney"})
    f = now.date()
    while f.weekday() != 4:
        f += timedelta(days=1)
    items.append({"date": f.isoformat(), "title": "RBA A1 balance sheet (Wednesday data) + F2 weekly yields", "type": "central_bank", "impact": "HIGH", "time_local": "16:30 Sydney"})
    items.append({"date": (now.date() + timedelta(days=1)).isoformat(), "title": "A3 ES balances (T+1) + F1 AONIA/BBSW (daily)", "type": "rates", "impact": "MEDIUM", "time_local": "~11:30 Sydney"})
    y, m = now.year, now.month
    nm = datetime(y + (m == 12), m % 12 + 1, 1).date()
    items.append({"date": nm.isoformat(), "title": "RBA financial aggregates D1/D2/D3 (monthly)", "type": "banking", "impact": "LOW", "time_local": "11:30 Sydney"})
    fs = cal.get("fiscal_seasonality", {})
    if isinstance(fs, dict):
        items.append({"date": datetime(y, m, 21).date().isoformat() if now.day <= 21 else datetime(y + (m == 12), m % 12 + 1, 21).date().isoformat(), "title": "Tax day 21st (PAYG/GST monthly) — expect government-deposit build (drain)", "type": "fiscal", "impact": "MEDIUM", "time_local": ""})
        for sg in fs.get("super_guarantee", []):
            items.append({"date": "%d-%s" % (y, sg), "title": "Super guarantee / quarterly BAS window (28th)", "type": "fiscal", "impact": "MEDIUM", "time_local": ""})
        items.append({"date": "%d-06-30" % y, "title": "EOFY — cash rebuild Jul–Oct", "type": "fiscal", "impact": "MEDIUM", "time_local": ""})
    for h in cal.get("au_holidays_2026", []):
        items.append({"date": h, "title": "Australia (NSW) public holiday", "type": "holiday", "impact": "LOW", "time_local": ""})
    upcoming = sorted([i for i in items if (i["date"] or "9999") >= now.date().isoformat()], key=lambda x: x["date"] or "9999")
    for i in upcoming:
        if i["date"]:
            i["days_until"] = (datetime.strptime(i["date"], "%Y-%m-%d").date() - now.date()).days
    return {"currency": cfg["currency"], "block": "calendar", "generated_at": now_iso(), "timezone_operator": cfg.get("timezone_operator"),
            "wat_offset_note": "Sydney = WAT + 9h (AEST) / + 10h (AEDT)", "upcoming": upcoming[:40], "source_health": {"status": "fresh", "series_loaded": 1, "series_expected": 1, "last_fetch_ok": True, "errors": []},
            "series": {}, "derived": {}, "signals": {"traffic_light": "NONE", "score": 0, "label": "CALENDAR"}, "history": {}}


def _calendar_jpy(cfg: dict, cal: dict, now: datetime) -> dict:
    items = []
    for d in cal.get("boj_mpm_2026", []) + cal.get("boj_mpm_2027", []):
        items.append({"date": d, "title": "BoJ Monetary Policy Meeting decision (day 2)", "type": "central_bank", "impact": "HIGH", "time_local": cal.get("decision_time", "12:00 Tokyo")})
    nb = now.date() + timedelta(days=1)
    while nb.weekday() >= 5:
        nb += timedelta(days=1)
    items.append({"date": nb.isoformat(), "title": "BoJ daily CAB / market operations (final T-1 ~10:00 JST) + TONA final + Tokyo Repo Rate", "type": "rates", "impact": "MEDIUM", "time_local": "10:00 / 12:30 Tokyo"})
    y, m = now.year, now.month
    import calendar as _c
    for dd in (10, 20, _c.monthrange(y, m)[1]):
        d = datetime(y, m, dd).date()
        if d >= now.date():
            items.append({"date": d.isoformat(), "title": "BoJ Accounts data date (published 2–3 business days later)", "type": "central_bank", "impact": "MEDIUM", "time_local": ""})
    nm = datetime(y + (m == 12), m % 12 + 1, 1).date()
    items.append({"date": (nm + timedelta(days=7)).isoformat(), "title": "BoJ loans & deposits (MD13) ~8th", "type": "banking", "impact": "LOW", "time_local": "08:50 Tokyo"})
    items.append({"date": (nm + timedelta(days=9)).isoformat(), "title": "BoJ money stock (MD02) ~2nd week", "type": "banking", "impact": "LOW", "time_local": "08:50 Tokyo"})
    items.append({"date": (nm + timedelta(days=4)).isoformat(), "title": "MoF Receipts & Payments of Treasury Funds (monthly Excel)", "type": "fiscal", "impact": "MEDIUM", "time_local": ""})
    d16 = datetime(y, m, 16).date() if now.day < 16 else datetime(y + (m == 12), m % 12 + 1, 16).date()
    items.append({"date": d16.isoformat(), "title": "Reserve maintenance period starts (16th–15th) — TONA highs common around period end", "type": "rates", "impact": "LOW", "time_local": ""})
    items.append({"date": None, "title": "MoF JGB auctions per monthly calendar (10Y/30Y/5Y/20Y/40Y/2Y + weekly T-Bills) — settlement drains reserves", "type": "fiscal", "impact": "MEDIUM", "time_local": "12:35 Tokyo"})
    upcoming = sorted([i for i in items if (i["date"] or "9999") >= now.date().isoformat()], key=lambda x: x["date"] or "9999")
    for i in upcoming:
        if i["date"]:
            i["days_until"] = (datetime.strptime(i["date"], "%Y-%m-%d").date() - now.date()).days
    return {"currency": cfg["currency"], "block": "calendar", "generated_at": now_iso(), "timezone_operator": cfg.get("timezone_operator"),
            "wat_offset_note": "Tokyo = WAT + 8h all year (JST has no DST)", "upcoming": upcoming[:40], "source_health": {"status": "fresh", "series_loaded": 1, "series_expected": 1, "last_fetch_ok": True, "errors": []},
            "series": {}, "derived": {}, "signals": {"traffic_light": "NONE", "score": 0, "label": "CALENDAR"}, "history": {}}


def _calendar_chf(cfg: dict, cal: dict, now: datetime) -> dict:
    items = []
    for d in cal.get("snb_mpa_2026", []) + cal.get("snb_mpa_2027", []):
        items.append({"date": d, "title": "SNB monetary policy assessment (policy rate, threshold factor, FX stance)", "type": "central_bank", "impact": "HIGH", "time_local": cal.get("decision_time", "09:30 Zurich")})
    d = now.date()
    nb = d + timedelta(days=1)
    while nb.weekday() >= 5:
        nb += timedelta(days=1)
    items.append({"date": nb.isoformat(), "title": "SNB policy rates / SARON (T-1, 10:00) + Confederation NSS curve (11:00)", "type": "rates", "impact": "MEDIUM", "time_local": "10:00 / 11:00 Zurich"})
    mon = d + timedelta(days=1)
    while mon.weekday() != 0:
        mon += timedelta(days=1)
    items.append({"date": mon.isoformat(), "title": "SNB weekly sight deposits (week to Friday) — domestic vs other; FX-intervention proxy", "type": "central_bank", "impact": "HIGH", "time_local": "10:00 Zurich"})
    tue = d + timedelta(days=1)
    while tue.weekday() != 1:
        tue += timedelta(days=1)
    items.append({"date": tue.isoformat(), "title": "Confederation MMDRC (money market debt register claims) auction — results Thursday", "type": "fiscal", "impact": "MEDIUM", "time_local": "11:00 Bern"})
    y, m = now.year, now.month
    d20 = datetime(y, m, 20).date() if now.day < 20 else datetime(y + (m == 12), m % 12 + 1, 20).date()
    items.append({"date": d20.isoformat(), "title": "Minimum-reserve period starts (20th–19th) — SARON prints often firm on days 18–20 and at month-end", "type": "rates", "impact": "LOW", "time_local": ""})
    nm = datetime(y + (m == 12), m % 12 + 1, 1).date()
    last = (nm - timedelta(days=1))
    items.append({"date": last.isoformat(), "title": "SNB money-market operations (gmges.xlsx, previous month) + SNB Bills register", "type": "central_bank", "impact": "MEDIUM", "time_local": "09:00 Zurich"})
    items.append({"date": (nm + timedelta(days=12)).isoformat(), "title": "SNB monthly balance sheet (snbbipo) — publication day to confirm", "type": "central_bank", "impact": "MEDIUM", "time_local": ""})
    items.append({"date": (nm + timedelta(days=19)).isoformat(), "title": "Banks (loans, balance sheets), money stock M1–M3, minimum reserves, mortgage rates", "type": "banking", "impact": "LOW", "time_local": ""})
    items.append({"date": None, "title": "SNB Bills 28-day auctions (weekly) and 1-week absorbing repos (daily) — sterilisation of excess reserves", "type": "central_bank", "impact": "MEDIUM", "time_local": ""})
    items.append({"date": None, "title": "Confederation bond auction (monthly, Wednesday; EFV calendar)", "type": "fiscal", "impact": "MEDIUM", "time_local": ""})
    upcoming = sorted([i for i in items if (i["date"] or "9999") >= now.date().isoformat()], key=lambda x: x["date"] or "9999")
    for i in upcoming:
        if i["date"]:
            i["days_until"] = (datetime.strptime(i["date"], "%Y-%m-%d").date() - now.date()).days
    return {"currency": cfg["currency"], "block": "calendar", "generated_at": now_iso(), "timezone_operator": cfg.get("timezone_operator"),
            "wat_offset_note": "Zurich = WAT + 1h (CET) / + 2h (CEST)", "upcoming": upcoming[:40], "source_health": {"status": "fresh", "series_loaded": 1, "series_expected": 1, "last_fetch_ok": True, "errors": []},
            "series": {}, "derived": {}, "signals": {"traffic_light": "NONE", "score": 0, "label": "CALENDAR"}, "history": {}}
