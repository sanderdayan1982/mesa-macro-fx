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


def effective_score(score, recent, persistence):
    """Persistence mode 'mean': the score the cuts are applied to is the mean of the block's prints over the last entry_days
    (a weekly block: this print and the previous one; a daily block: the last week of prints). Fewer than two prints = the print itself."""
    pers = persistence or {}
    if score is None:
        return None
    if pers.get("mode", "mean") == "mean" and pers.get("entry_days", 0) > 0 and len(recent) >= 2:
        return round(sum(v for _, v in recent) / len(recent), 3)
    return score


def block_regime_step(score: Optional[float], cuts: dict, prev_state: Optional[dict], as_of: Optional[str], persistence: Optional[dict]) -> dict:
    """One as-of step of the per-block regime: Schmitt cuts (enter / exit) on the effective score, plus persistence.
    mode 'mean' (default, engine v0.3): effective score = mean of the prints over the last entry_days (two weekly prints /
    one week of daily prints); the cuts are era percentiles of that same smoothed score, so entry and exit are consistent.
    mode 'consecutive': the raw print must sit beyond the enter cut on every print over entry_days before the side is confirmed.
    exit_days: prints inside the exit cut needed before leaving a side (0 = the first one). Measured on the block's as-of dates."""
    prev_state = prev_state or {}
    confirmed = prev_state.get("confirmed") or "NEUTRAL"
    pers = persistence or {}
    entry_days, exit_days, mode = pers.get("entry_days", 0), pers.get("exit_days", 0), pers.get("mode", "mean")
    recent = [tuple(x) for x in (prev_state.get("recent") or [])]
    if score is None:
        return {"confirmed": confirmed, "raw": "NO SIGNAL", "effective_score": None, "candidate": None, "candidate_since": None, "as_of": as_of, "recent": recent[-12:]}
    if as_of:
        recent = [(d, v) for d, v in recent if d < as_of] + [(as_of, float(score))]
        lo = (datetime.fromisoformat(as_of[:10]) - timedelta(days=max(entry_days, 0))).date().isoformat()
        recent = [(d, v) for d, v in recent if d >= lo][-12:]
    s = effective_score(score, recent, pers)
    # raw reading with hysteresis relative to the confirmed regime
    if confirmed == "INJECTION":
        raw = "INJECTION" if s >= cuts["injection_exit"] else ("DRAIN" if s <= cuts["drain_enter"] else "NEUTRAL")
    elif confirmed == "DRAIN":
        raw = "DRAIN" if s <= cuts["drain_exit"] else ("INJECTION" if s >= cuts["injection_enter"] else "NEUTRAL")
    else:
        raw = "INJECTION" if s >= cuts["injection_enter"] else "DRAIN" if s <= cuts["drain_enter"] else "NEUTRAL"
    cand, since = prev_state.get("candidate"), prev_state.get("candidate_since")
    if raw == confirmed:
        cand, since = None, None
    else:
        if cand != raw or not since:
            cand, since = raw, as_of
        held = (datetime.fromisoformat(as_of[:10]) - datetime.fromisoformat(since[:10])).days if (as_of and since) else 0
        need = exit_days if raw == "NEUTRAL" else (entry_days if mode == "consecutive" else 0)
        if held >= need:
            confirmed, cand, since = raw, None, None
    return {"confirmed": confirmed, "raw": raw, "effective_score": s, "candidate": cand, "candidate_since": since, "as_of": as_of, "recent": recent,
            "pending_days": ((datetime.fromisoformat(as_of[:10]) - datetime.fromisoformat(since[:10])).days if (as_of and since) else None)}


def classify_regime(cfg: dict, blocks: Dict[str, dict], prev_regime: Optional[dict] = None, hist_dir: Optional[str] = None) -> dict:
    """hist_dir = history/<ccy> (the append-only CSV archive); needed by the v0.4 daily5/weekly components — when None those prints are
    skipped with a note and the block reads NO SIGNAL (never the v0.3 score under the v0.4 cuts)."""
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
    # ── three regimes (desk rule 2026-09-09): central bank, treasury/equivalent, general ──
    # v0.2: block regime from the block score at flat ±0.5; general = agreement, conflicts resolved by dual weights.
    # v0.3 (triangulation round 2, 2026-09-09): per-block entry/exit cuts calibrated on the operating era, persistence
    # (entry_days / exit_days on the block's as-of dates), general regime = agreement rule only (conflict / partial = NEUTRAL,
    # labelled), dual weights kept as context, evidence label per cut, agreement-only forced while the era is younger than
    # agreement_only_until_weeks. Everything defaults to the v0.2 behaviour when the keys are absent.
    dual = rc.get("dual") or {}
    v03 = str(dual.get("version", "")).startswith("0.3") or "persistence" in dual or isinstance((dual.get("block_thresholds") or {}).get("central_bank"), dict)
    prev_regs = (prev_regime or {}).get("regimes") or {}

    def _cuts(name: str) -> dict:
        bt = dual.get("block_thresholds") or {}
        c = bt.get(name) if isinstance(bt.get(name), dict) else bt
        inj, drn = c.get("injection_enter", c.get("injection", 0.5)), c.get("drain_enter", c.get("drain", -0.5))
        return {"injection_enter": inj, "injection_exit": c.get("injection_exit", inj), "drain_enter": drn, "drain_exit": c.get("drain_exit", drn),
                "evidence": c.get("evidence") or {}, "rule": c.get("rule")}

    # v0.4 (activation lot 2026-09-11): a block listed in dual.v04 with active=true reads ONE settlement/flow component (replay_v04 cuts)
    # instead of its v0.3 score; the v0.3 reading is kept beside it as v03_shadow for continuity. Blocks not listed stay v0.3.
    v04 = dual.get("v04") or {}
    CUT_KEYS = ("injection_enter", "injection_exit", "drain_enter", "drain_exit")

    def _blk_v03(name: str, prev_state: dict) -> dict:
        b = blocks.get(name)
        cuts = _cuts(name)
        if not b or b["signals"]["traffic_light"] == "NONE":
            # no print this run (source outage / lane without the series): the block reads NO SIGNAL but its hysteresis state is
            # carried forward untouched, so the confirmed regime resumes where it was when the data returns (v0.3.1 hotfix)
            return {"regime": "NO SIGNAL", "score": None, "label": None, "traffic_light": "NONE", "as_of": None,
                    "state": prev_state, "cuts": {k: cuts[k] for k in CUT_KEYS},
                    "last_confirmed": prev_state.get("confirmed"), "last_as_of": (prev_regs.get(name) or {}).get("as_of")}
        sc = b["signals"]["score"]
        st = block_regime_step(sc, cuts, prev_state, b.get("as_of"), dual.get("persistence"))
        out = {"regime": st["confirmed"], "score": sc, "label": b["signals"]["label"], "traffic_light": b["signals"]["traffic_light"], "as_of": b.get("as_of"),
               "detail": b["signals"].get("detail", ""), "raw_regime": st["raw"], "cuts": {k: cuts[k] for k in CUT_KEYS},
               "evidence": cuts["evidence"], "state": st, "components": b["signals"].get("components")}
        return out

    def _blk_v04(name: str, spec: dict, prev: dict) -> dict:
        from .v04_component import compute_print  # local import: pure-python helper, kept out of the module import path
        comp, cuts4 = spec.get("component") or {}, {k: spec["cuts"][k] for k in CUT_KEYS}
        prev_state = prev.get("state") or {}
        # the block state continues from the v0.4 print history only: the first v0.4 run starts from confirmed NEUTRAL (a v0.3 state
        # is on another scale and is not carried into the v0.4 hysteresis); the v0.3 shadow keeps its own state under v03_shadow
        if prev_state.get("engine") != "0.4":
            shadow_prev, prev_state = prev_state, {}
        else:
            shadow_prev = (prev.get("v03_shadow") or {}).get("state") or {}
        v3 = _blk_v03(name, shadow_prev)
        pr = compute_print(comp, blocks, hist_dir)
        st = block_regime_step(pr["score"], cuts4, prev_state, pr["as_of"], dual.get("persistence"))
        st["engine"] = "0.4"
        out = {"regime": st["confirmed"] if pr["score"] is not None else "NO SIGNAL", "score": pr["score"], "label": v3.get("label"), "traffic_light": v3.get("traffic_light"),
               "as_of": pr["as_of"] or v3.get("as_of"), "detail": v3.get("detail", ""), "raw_regime": st["raw"], "cuts": cuts4, "evidence": spec.get("evidence") or {},
               "state": st, "components": v3.get("components"), "engine": "0.4", "component": comp, "selected": spec.get("selected"),
               "print": {k: pr[k] for k in ("raw", "denominator", "denominator_date", "today", "note")},
               "v03_shadow": {"regime": v3["regime"], "score": v3["score"], "raw_regime": v3.get("raw_regime"), "cuts": v3.get("cuts"), "as_of": v3.get("as_of"), "state": v3.get("state")}}
        if pr["score"] is None:
            out["last_confirmed"], out["last_as_of"] = st["confirmed"], prev.get("as_of")
        return out

    def _blk(name: str) -> dict:
        prev = prev_regs.get(name) or {}
        spec = v04.get(name) if isinstance(v04.get(name), dict) else None
        if spec and spec.get("active") and spec.get("cuts") and all(k in spec["cuts"] for k in CUT_KEYS):
            return _blk_v04(name, spec, prev)
        return _blk_v03(name, prev.get("state") or {})

    cbr, fir = _blk("central_bank"), _blk("fiscal")
    dw = dual.get("weights") or {"central_bank": 0.6, "fiscal": 0.4}
    gth = dual.get("general_thresholds") or {"injection": 0.5, "drain": -0.5}
    era_start = dual.get("era_start")
    era_weeks = None
    if era_start:
        asof = max([x for x in (cbr.get("as_of"), fir.get("as_of")) if x] or [now_iso()[:10]])
        era_weeks = max(0, (datetime.fromisoformat(asof[:10]) - datetime.fromisoformat(era_start)).days // 7)
    agree_only = bool(dual.get("agreement_only", v03))
    until = dual.get("agreement_only_until_weeks")
    if until and era_weeks is not None and era_weeks < until:
        agree_only = True
    avail = {k: v for k, v in (("central_bank", cbr), ("fiscal", fir)) if v["score"] is not None}
    if not avail:
        g_reg, g_score, rule = "NO SIGNAL", None, "no block available"
    else:
        tw = sum(dw[k] for k in avail) or 1.0
        # the dual score is context only and stays on the v0.3 scale: a v0.4 block contributes its v0.3 shadow score (its own print is in % of reserves)
        _sc = lambda v: v["v03_shadow"]["score"] if (v.get("engine") == "0.4" and (v.get("v03_shadow") or {}).get("score") is not None) else v["score"]
        g_score = round(sum(dw[k] * _sc(v) for k, v in avail.items()) / tw, 3)
        if len(avail) == 1 and agree_only:
            # agreement rule: with one dual block missing no agreement is possible → NEUTRAL, never the surviving block's side
            # (a source outage must not move the general regime; v0.3.1 hotfix)
            k = next(iter(avail))
            g_reg, rule = "NEUTRAL", "single block (%s) — the other has no signal: no agreement possible → NEUTRAL by the agreement rule (v0.3)" % k
        elif len(avail) == 1:
            k = next(iter(avail))
            g_reg, rule = {"INJECTION": "LIQUIDITY_INJECTION", "DRAIN": "LIQUIDITY_DRAIN", "NEUTRAL": "NEUTRAL"}[avail[k]["regime"]], "single block (%s) — the other has no signal" % k
        elif cbr["regime"] == "INJECTION" and fir["regime"] == "INJECTION":
            g_reg, rule = "LIQUIDITY_INJECTION", "agreement: both inject"
        elif cbr["regime"] == "DRAIN" and fir["regime"] == "DRAIN":
            g_reg, rule = "LIQUIDITY_DRAIN", "agreement: both drain"
        elif agree_only:
            g_reg = "NEUTRAL"
            kind = "conflict" if "NEUTRAL" not in (cbr["regime"], fir["regime"]) else "partial"
            rule = "%s (%s vs %s) → NEUTRAL by the agreement rule (v0.3: no dual weights%s); dual score %+.2f shown for context" % (
                kind, cbr["regime"], fir["regime"], (", era %d weeks < %d" % (era_weeks, until)) if (until and era_weeks is not None and era_weeks < until) else "", g_score)
        else:
            g_reg = "LIQUIDITY_INJECTION" if g_score >= gth["injection"] else "LIQUIDITY_DRAIN" if g_score <= gth["drain"] else "NEUTRAL"
            rule = ("conflict (%s vs %s) resolved by dual weights %s/%s and thresholds %+.2f/%+.2f — provisional, to calibrate per currency"
                    % (cbr["regime"], fir["regime"], dw["central_bank"], dw["fiscal"], gth["injection"], gth["drain"])) if "NEUTRAL" not in (cbr["regime"], fir["regime"]) \
                else "partial (%s vs %s): dual score %+.2f vs thresholds %+.2f/%+.2f" % (cbr["regime"], fir["regime"], g_score, gth["injection"], gth["drain"])
    gate = None
    if used < rc.get("min_blocks_for_signal", 2):
        regime = "NO SIGNAL"
    elif in_range is False and not res.get("above_range") and r_lvl in ("WATCH", "STRESS", "CRISIS") and LEVEL_RANK[s_lvl] >= LEVEL_RANK["STRESS"]:
        regime, gate = "LIQUIDITY_SCARCITY", "price gate: reserves below range AND stress spread >= STRESS"
    elif ample and friction:
        regime, gate = ("FLOOR_FRICTION" if g_reg != "LIQUIDITY_DRAIN" else "LIQUIDITY_DRAIN"), "price gate: reserves ample AND friction confirmed"
    else:
        regime = g_reg
    regimes = {"central_bank": cbr, "fiscal": fir,
               "general": {"regime": regime, "score": g_score, "rule": rule, "price_gate": gate, "dual_weights": dw, "thresholds": gth,
                           "block_thresholds": {"central_bank": cbr.get("cuts"), "fiscal": fir.get("cuts")} if v03 else (dual.get("block_thresholds") or {"injection": 0.5, "drain": -0.5}),
                           "engine": "0.3" if v03 else "0.2", "v04_blocks": [n for n, r in (("central_bank", cbr), ("fiscal", fir)) if r.get("engine") == "0.4"],
                           "agreement_only": agree_only, "era_start": era_start, "era_weeks": era_weeks,
                           "persistence": dual.get("persistence"), "level_weight": dual.get("level_weight"),
                           "calibration": dual.get("status", "provisional — per-currency thresholds pending")}}
    flags = []
    tsig = _get(blocks, "banking.transmission_signal").get("signal")
    if tsig == "RED" and (in_range or res.get("above_range")):
        flags.append("TRANSMISSION_FAILURE")
    if ample and friction and regime != "FLOOR_FRICTION":
        flags.append("FLOOR_FRICTION")
    phase = _get(blocks, "central_bank.balance_sheet_phase").get("phase")
    if phase and phase != "NO DATA":
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
    overlays = _overlays(cfg, blocks, (prev_regime or {}).get('overlays') or {})
    for ov, st in overlays.items():
        if isinstance(st, str) and st.endswith("_HIGH") and ov not in flags:
            flags.append(ov)
    tl = {"LIQUIDITY_INJECTION": "GREEN", "NEUTRAL": "YELLOW", "FLOOR_FRICTION": "YELLOW", "LIQUIDITY_DRAIN": "RED", "LIQUIDITY_SCARCITY": "RED", "NO SIGNAL": "NONE"}[regime]
    return {"regime": regime, "traffic_light": tl, "weighted_score": weighted, "block_scores": scores, "weights": w, "blocks_used": used,
            "regimes": regimes, "composite_note": "weighted_score = 4-block desk composite (context); the reported regime is the general regime from central bank + treasury",
            "flags": flags, "overlays": overlays, "inputs": {"reserves_level": r_lvl, "reserves_in_range": in_range, "reserves_above_range": res.get("above_range"), "spread_level": s_lvl, "spread_bps": spr.get("value"), "friction_confirmed": friction},
            "rules": rc.get("rules", {})}


def _overlays(cfg: dict, blocks: Dict[str, dict], prev: Optional[Dict[str, object]] = None) -> Dict[str, Optional[str]]:
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
        st = None if not conds else ("%s_HIGH" % name if n >= need else "%s_LOW" % name if n > 0 else None)
        # persistence (NZD N10): HIGH only when the previous run also met the minimum (or was already HIGH); otherwise LOW + pending
        pers = ov.get("persistence")
        if pers and st and st.endswith("_HIGH"):
            pm = (prev or {}).get(name + "_conditions_met") or 0
            ps = (prev or {}).get(name)
            if not (pm >= need or (isinstance(ps, str) and ps.endswith("_HIGH"))):
                st = "%s_LOW" % name
                out[name + "_pending_persistence"] = True  # type: ignore
        out[name] = st
        out[name + "_conditions_met"] = n  # type: ignore
    return out


# ───────────────────────────── scenarios ─────────────────────────────
def _resolve_condition(cond: str, blocks: Dict[str, dict], regime: Optional[dict] = None) -> Optional[bool]:
    """Mini-language: '<path> level >= WATCH' | '<path> level == SAFE' | '<path> <= drain' | '<path> >= injection' |
    '<path> <= p20' | '<path> > 0' | '<path> == RED' | '<path> mom_pct zscore >= 1' | 'regime.<block> == INJECTION'
    (the engine's CONFIRMED block regime with hysteresis — round 2: fiscal scenarios require it, not the block heuristic)."""
    parts = cond.split()
    path = parts[0]
    if path.startswith("regime."):
        r = (((regime or {}).get("regimes") or {}).get(path.split(".", 1)[1]) or {}).get("regime")
        if r in (None, "NO DATA", "NO SIGNAL"):
            return None
        return r == parts[2] if parts[1] == "==" else r != parts[2]
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
    if tgt in ("band_low", "band_high", "risk_off", "risk_on"):  # era-band position (risk_* kept as aliases of old configs)
        want = {"band_low": "BAND_LOW", "risk_off": "BAND_LOW", "band_high": "BAND_HIGH", "risk_on": "BAND_HIGH"}[tgt]
        return (e.get("signal") == want) if e.get("signal") not in (None, "NO DATA") else None
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


def evaluate_scenarios(cfg: dict, blocks: Dict[str, dict], regime: Optional[dict] = None) -> List[dict]:
    out = []
    for sc in cfg.get("scenarios", {}).get("items", []):
        det = []
        for cnd in sc["conditions"]:
            try:
                met = _resolve_condition(cnd, blocks, regime)
            except Exception:
                met = None
            det.append({"condition": cnd, "met": met})
        n = sum(1 for d in det if d["met"])
        unknown = sum(1 for d in det if d["met"] is None)  # conditions without data are declared, not counted as met (round 2)
        # required conditions (institutionality round 2, CURSOR): a scarcity scenario needs its price condition and a fiscal
        # scenario its fiscal condition — «min of n» can never substitute them; null or false → the chip does not light
        req = sc.get("required") or []
        req_met = all(next((d["met"] for d in det if d["condition"] == r), None) is True for r in req)
        out.append({"id": sc["id"], "name": sc["name"], "bias": sc["bias"], "active": bool(n >= sc["min"] and req_met), "conditions_met": n, "total": len(det),
                    "unknown": unknown, "required": req, "required_met": req_met, "details": det})
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
    if when in ("<= risk_off", "<= band_low"):
        return None if not e.get("signal") else e["signal"] == "BAND_LOW"
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
    if cfg.get("currency") == "NZD":
        return _calendar_nzd(cfg, cal, now)
    if cfg.get("currency") == "USD":
        return _calendar_usd(cfg, cal, now)
    if cfg.get("currency") == "EUR":
        return _calendar_eur(cfg, cal, now)
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


def _calendar_nzd(cfg: dict, cal: dict, now: datetime) -> dict:
    items = []
    mps = set(cal.get("rbnz_mps", []))
    for d in cal.get("rbnz_mpc_2026", []) + cal.get("rbnz_mpc_2027", []):
        items.append({"date": d, "title": "RBNZ OCR decision" + (" + Monetary Policy Statement" if d in mps else " (Monetary Policy Review)"), "type": "central_bank", "impact": "HIGH", "time_local": cal.get("decision_time", "14:00 Auckland")})
    d = now.date()
    nb = d + timedelta(days=1)
    while nb.weekday() >= 5:
        nb += timedelta(days=1)
    items.append({"date": nb.isoformat(), "title": "RBNZ daily tables after 15:00 NZT: B2 rates, D12 settlement cash / ORRF, D3 operations (T-1)", "type": "rates", "impact": "MEDIUM", "time_local": "15:00 Auckland"})
    def nxt(wd):
        x = d + timedelta(days=1)
        while x.weekday() != wd:
            x += timedelta(days=1)
        return x
    items.append({"date": nxt(1).isoformat(), "title": "NZDM Treasury bill tender (results 14:35 NZT, settlement T+1)", "type": "fiscal", "impact": "MEDIUM", "time_local": "14:00–14:30 Wellington"})
    items.append({"date": nxt(3).isoformat(), "title": "RBNZ weekly reverse-repo OMO (7d + 28d, full allotment at OCR + 10 bp) 11:30 NZT · NZDM bond tender 14:00 (settlement T+3)", "type": "central_bank", "impact": "HIGH", "time_local": "11:30 / 14:00 Auckland"})
    items.append({"date": nxt(0).isoformat(), "title": "RBNZ D9 weekly NZGB turnover (week to Friday)", "type": "rates", "impact": "LOW", "time_local": "15:00 Auckland"})
    y, m = now.year, now.month
    nm = datetime(y + (m == 12), m % 12 + 1, 1).date()
    d14 = datetime(y, m, 14).date() if now.day < 14 else datetime(nm.year, nm.month, 14).date()
    items.append({"date": d14.isoformat(), "title": "RBNZ R1 balance sheet + R3 analytical accounts (Crown settlement account, monetary base)", "type": "central_bank", "impact": "MEDIUM", "time_local": "15:00 Auckland"})
    items.append({"date": (d14 + timedelta(days=1)).isoformat(), "title": "RBNZ LSAP bond sale to NZDM (~NZ$415m, mid-month) — drain", "type": "central_bank", "impact": "LOW", "time_local": ""})
    import calendar as _c
    last = datetime(y, m, _c.monthrange(y, m)[1]).date()
    if last < d:
        last = datetime(nm.year, nm.month, _c.monthrange(nm.year, nm.month)[1]).date()
    items.append({"date": last.isoformat(), "title": "RBNZ D10 influences on settlement cash (government cash influence), C5 sector lending, C50 money & credit (previous month)", "type": "fiscal", "impact": "MEDIUM", "time_local": "15:00 Auckland"})
    d18 = datetime(y, m, 18).date() if now.day < 18 else datetime(nm.year, nm.month, 18).date()
    items.append({"date": d18.isoformat(), "title": "RBNZ D30 holdings of NZGS by sector (non-residents)", "type": "fiscal", "impact": "LOW", "time_local": ""})
    for md in cal.get("tax_dates", {}).get("provisional_tax_standard", []):
        for yy in (y, y + 1):
            dd = "%d-%s" % (yy, md)
            if dd >= d.isoformat():
                items.append({"date": dd, "title": "IRD provisional tax instalment (Crown receipts → settlement cash drain)", "type": "fiscal", "impact": "MEDIUM", "time_local": ""})
                break
    items.append({"date": None, "title": "NZGB coupons on the 15th (Apr/May/Sep/Oct/Nov…) and maturities 15-Apr / 15-May — injections tagged in the residual flow", "type": "fiscal", "impact": "MEDIUM", "time_local": ""})
    upcoming = sorted([i for i in items if (i["date"] or "9999") >= now.date().isoformat()], key=lambda x: x["date"] or "9999")
    for i in upcoming:
        if i["date"]:
            i["days_until"] = (datetime.strptime(i["date"], "%Y-%m-%d").date() - now.date()).days
    return {"currency": cfg["currency"], "block": "calendar", "generated_at": now_iso(), "timezone_operator": cfg.get("timezone_operator"),
            "wat_offset_note": "Auckland = WAT + 11h (NZST) / + 12h (NZDT, last Sunday of September to first Sunday of April)", "upcoming": upcoming[:40], "source_health": {"status": "fresh", "series_loaded": 1, "series_expected": 1, "last_fetch_ok": True, "errors": []},
            "series": {}, "derived": {}, "signals": {"traffic_light": "NONE", "score": 0, "label": "CALENDAR"}, "history": {}}


def _calendar_usd(cfg: dict, cal: dict, now: datetime) -> dict:
    """USD: FOMC (verified federalreserve.gov), H.4.1 Thu 16:30 ET, H.8 Fri 16:15 ET, DTS daily ~16:00 ET (T-1), SOFR 08:00 ET, H.15 T+1,
    DTS seasonal windows (quarter-end, tax days, mid-month settlement, payments window), NYSE holidays."""
    items = []
    sep = set(cal.get("fomc_sep_dates", []))
    for d in cal.get("fomc_dates_2026", []) + cal.get("fomc_dates_2027", []):
        items.append({"date": d, "title": "FOMC decision" + (" + Summary of Economic Projections" if d in sep else ""), "type": "central_bank", "impact": "HIGH", "time_local": "14:00 ET (20:00 WAT)"})
    d = now.date()
    def nxt(wd, allow_today=False):
        x = d if allow_today else d + timedelta(days=1)
        while x.weekday() != wd:
            x += timedelta(days=1)
        return x
    nb = d + timedelta(days=1)
    while nb.weekday() >= 5:
        nb += timedelta(days=1)
    items.append({"date": nb.isoformat(), "title": "Daily Treasury Statement (~16:00 ET, record T-1) · SOFR 08:00 ET · H.15 daily closes · ON RRP 13:15 ET", "type": "fiscal", "impact": "MEDIUM", "time_local": "16:00 ET (22:00 WAT)"})
    items.append({"date": nxt(3).isoformat(), "title": "Fed H.4.1 balance sheet (Wednesday levels): WALCL, TREAST, MBS, primary credit, TGA, reserves — operative window 22:30 → 02:30 WAT", "type": "central_bank", "impact": "HIGH", "time_local": "16:30 ET (22:30 WAT)"})
    items.append({"date": nxt(4).isoformat(), "title": "Fed H.8 commercial banks (Wednesday levels): bank credit, loans, C&I, deposits, borrowings", "type": "banking", "impact": "MEDIUM", "time_local": "16:15 ET (22:15 WAT)"})
    y, m = now.year, now.month
    import calendar as _c
    seas = []
    for yy in (y, y + 1):
        for mm in range(1, 13):
            seas.append(("%d-%02d-15" % (yy, mm), "DTS mid-month settlement window (14–16)" + (" — estimated tax day" if mm in (1, 6, 9) else " — Tax Day" if mm == 4 else "")))
            seas.append(("%d-%02d-25" % (yy, mm), "DTS payments window (≥ 25: SNAP, SSI, month-end payrolls)"))
            if mm in (3, 6, 9, 12):
                seas.append(("%d-%02d-%02d" % (yy, mm, _c.monthrange(yy, mm)[1]), "Quarter-end (DTS seasonal flag; corporate tax / settlement flows)"))
    for dd, t in seas:
        if dd >= d.isoformat():
            items.append({"date": dd, "title": t, "type": "fiscal", "impact": "MEDIUM" if "Quarter" in t or "Tax" in t else "LOW", "time_local": ""})
    for h in cal.get("us_market_holidays_2026", []) + cal.get("us_market_holidays_2027", []):
        items.append({"date": h, "title": "US market holiday (no DTS / H.15)", "type": "holiday", "impact": "LOW", "time_local": ""})
    upcoming = sorted([i for i in items if (i["date"] or "9999") >= d.isoformat()], key=lambda x: x["date"] or "9999")
    for i in upcoming:
        if i["date"]:
            i["days_until"] = (datetime.strptime(i["date"], "%Y-%m-%d").date() - d).days
    return {"currency": cfg["currency"], "block": "calendar", "generated_at": now_iso(), "timezone_operator": cfg.get("timezone_operator"),
            "wat_offset_note": "New York = WAT − 5h (EDT) / − 6h (EST)", "upcoming": upcoming[:40], "source_health": {"status": "fresh", "series_loaded": 1, "series_expected": 1, "last_fetch_ok": True, "errors": []},
            "series": {}, "derived": {}, "signals": {"traffic_light": "NONE", "score": 0, "label": "CALENDAR"}, "history": {}}


def _calendar_eur(cfg: dict, cal: dict, now: datetime) -> dict:
    """EUR: Governing Council monetary-policy meetings (verified ecb.europa.eu 2026-09-09), WFS Tuesday 15:00 CET, ILM daily T+1, €STR 08:00 CET,
    APP/PEPP Friday, MRO Tuesday allotment / Wednesday settlement, 3m LTRO last Wednesday of the month, reserve maintenance periods 2026
    (press release 2025-04-24; last MP day = €STR volatility day), TARGET holidays."""
    items = []
    for d in cal.get("ecb_gc_monetary_policy_2026", []) + cal.get("ecb_gc_monetary_policy_2027", []):
        items.append({"date": d, "title": "ECB Governing Council monetary policy decision (14:15 CET) + press conference (14:45 CET)" + (" — Berlin" if d == "2026-09-10" else ""),
                      "type": "central_bank", "impact": "HIGH", "time_local": "14:15 CET (13:15 WAT)"})
    d = now.date()
    def nxt(wd, allow_today=False):
        x = d if allow_today else d + timedelta(days=1)
        while x.weekday() != wd:
            x += timedelta(days=1)
        return x
    nb = d + timedelta(days=1)
    while nb.weekday() >= 5:
        nb += timedelta(days=1)
    items.append({"date": nb.isoformat(), "title": "ILM daily liquidity (T+1 ~09:30 CET): excess liquidity, DF, current accounts, autonomous factors, MRO/LTRO, MLF · €STR 08:00 CET · AAA/all-EA curves ~17:00 CET · EUR/USD 16:00 CET",
                  "type": "central_bank", "impact": "MEDIUM", "time_local": "09:30 CET (08:30 WAT)"})
    items.append({"date": nxt(1).isoformat(), "title": "Eurosystem weekly financial statement (15:00 CET, position as at the previous Friday): MonPol securities, MRO/LTRO, government deposits · MRO allotment", "type": "central_bank", "impact": "HIGH", "time_local": "15:00 CET (14:00 WAT)"})
    items.append({"date": nxt(2).isoformat(), "title": "MRO settlement (full allotment at the MRO rate)", "type": "central_bank", "impact": "LOW", "time_local": ""})
    items.append({"date": nxt(4).isoformat(), "title": "APP / PEPP holdings update (~15:00 CET, holdings as at the previous Friday)", "type": "central_bank", "impact": "LOW", "time_local": "15:00 CET"})
    for a, b in cal.get("reserve_maintenance_periods_2026", []):
        items.append({"date": a, "title": "Reserve maintenance period starts (new DFR/MRO/MLF apply)", "type": "central_bank", "impact": "MEDIUM", "time_local": ""})
        items.append({"date": b, "title": "Last day of the reserve maintenance period — €STR / volume volatility day", "type": "rates", "impact": "MEDIUM", "time_local": ""})
    # Finanzagentur: auctions on Mondays (Bubill) / Tuesdays–Wednesdays (Bund, Bobl, Schatz) — the desk reads the results file the same afternoon
    items.append({"date": nxt(0).isoformat(), "title": "Finanzagentur Bubill auction (results ~11:30 CET; XLSX same day)", "type": "fiscal", "impact": "LOW", "time_local": "11:30 CET"})
    # monthly releases (approximate day; verified pattern on the portal)
    import calendar as _c
    for yy, mm in ((now.year, now.month), (now.year + (now.month // 12), now.month % 12 + 1)):
        items.append({"date": "%d-%02d-10" % (yy, mm), "title": "TARGET balances (TGB monthly, ~10th) · IRS convergence yields", "type": "fiscal", "impact": "LOW", "time_local": ""})
        items.append({"date": "%d-%02d-27" % (yy, mm), "title": "BSI monetary developments (M1/M3, loans, ~27th) · MIR cost of borrowing · EURIBOR monthly average", "type": "banking", "impact": "MEDIUM", "time_local": "10:00 CET"})
    for h in cal.get("target_holidays", []):
        items.append({"date": h, "title": "TARGET holiday (no ILM / €STR)", "type": "holiday", "impact": "LOW", "time_local": ""})
    upcoming = sorted([i for i in items if (i["date"] or "9999") >= d.isoformat()], key=lambda x: x["date"] or "9999")
    for i in upcoming:
        if i["date"]:
            i["days_until"] = (datetime.strptime(i["date"], "%Y-%m-%d").date() - d).days
    return {"currency": cfg["currency"], "block": "calendar", "generated_at": now_iso(), "timezone_operator": cfg.get("timezone_operator"),
            "wat_offset_note": "Frankfurt = WAT + 1h (CEST) / + 0h (CET)", "upcoming": upcoming[:40], "source_health": {"status": "fresh", "series_loaded": 1, "series_expected": 1, "last_fetch_ok": True, "errors": []},
            "series": {}, "derived": {}, "signals": {"traffic_light": "NONE", "score": 0, "label": "CALENDAR"}, "history": {}}
