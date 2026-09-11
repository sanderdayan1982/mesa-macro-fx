"""Replay v0.4 — which shadow component enters each regime (round 1 adjudication, ADJUDICACION_REPLAY_V04.md).

Inputs (all already in the repo):
  calibration/<ccy>_v03/scores.csv   the v0.3 as-of replay on the block's weekly grid: v0.3 scores (variant A), reserves (denominator),
                                     government account (weekly), stress spread (method-B truth)
  history/<ccy>/<flow>.csv           the v0.4 flows by settlement (daily) or on a weekly grid, as the engine archives them
Design (pre-registered, nothing set by hand):
  * every flow enters as the sum over the 5 sessions ending at the print in % of the stock (weekly series enter as a step)
  * as-of clock = PUBLICATION: a component whose amounts arrive late (SNB gmges, ~35 days after month-end) is evaluated with that lag
  * variants per block: A = v0.3 published score · B = v0.4 base (the round-1 table) · C = the round-1 candidate; the identity rule
    forbids summing the government account and net issuance (they are compared, never added)
  * cuts = the v0.3 era rule (_era_cuts on the 2-print mean), regimes = the live hysteresis (engine.block_regime_step)
  * selection ladder: (1) coverage + reconciliation known → (2) method B marginal (forward Δ stress spread 4/12 w, Spearman with
    block bootstrap; also on scarcity weeks |spread| > 5 bp) → (3) revision robustness (not testable without vintages: reported as such)
  * stability: rolling origin every 13 weeks — a cut is 'estable' when its position moves < 10 % of the era IQR and the state sequence
    on the common window agrees ≥ 90 % with the full-sample cuts; otherwise 'provisional'
  * automatic checks: double counting (forbidden pairs), look-ahead (lags), frequency aliasing (weekly steps never summed daily)
Outputs: calibration/<ccy>_v04/replay_v04.json + report.md; calibration/REPLAY_V04.md (all currencies). Decision support only."""
from __future__ import annotations
import bisect
import csv
import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
from .calibrate import ERA_DEFAULT, PERSISTENCE, _era_cuts, _regime_series, _spells, spearman, block_bootstrap_p

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Series = List[Tuple[str, float]]

# component spec: key → (source, kind, lag_days, sign, reconciliation note)
#   source: ("hist", "<file>") daily/weekly CSV under history/<ccy>/ ; ("scores", "<column>") from the v0.3 replay grid
#   kind:   daily5 = 5-session sum ending at the print · weekly = latest weekly value ≤ print (step) · dweekly = −Δ of a weekly level
FORBIDDEN_PAIRS = [("govt_delta", "net_issuance_5d"), ("omo_net_5d", "omo_stock"), ("ops_net_5d", "absorption_stock")]
SPEC: Dict[str, dict] = {
    "cad": {"central_bank": {"A": "v0.3 (Δ reserves semanal, Δ13s, dependencia de repos)",
                             "B": {"term_repo_net_5d": ("hist", "term_repo_net_daily", "daily5", 1, +1, "stock = B2 V44201362 ±1 %"),
                                   "overnight_ops_net_5d": ("hist", "overnight_ops_net_daily", "daily5", 1, +1, "OR/ORR por operación")},
                             "C": {}, "note": "saldos de liquidación diarios sin histórico en fixtures (tabla HTML de 6 días) → fuera del replay hasta que el archivo diario madure"},
            "fiscal": {"A": "v0.3 (−Δ cuenta del gobierno semanal + banda)",
                       "B": {"govt_delta": ("scores", "govt_account", "dweekly", 0, +1, "cuenta del gobierno (Valet) — identidad")},
                       "C": {"net_issuance_5d": ("hist", "net_issuance_private_daily", "daily5", 1, +1, "emisión neta por liquidación (AUC groups; sin cupones — la v2 neta de la cartera del BoC se archiva desde el lote 2)")}}},
    "gbp": {"central_bank": {"A": "v0.3 (Δ reservas semanal, Δ13s, dependencia de repos)",
                             "B": {"repo_net_5d": ("hist", "repo_net_daily", "daily5", 1, +1, "STR/ILTR/CTRF por operación; stock STR = IADB exacto"),
                                   "apf_sales_5d": ("hist", "apf_sales_daily", "daily5", 1, -1, "ventas APF por fecha (drenan)")},
                             "C": {}},
            "fiscal": {"A": "v0.3 (banda CGNCR mensual)",
                       "B": {"net_issuance_5d": ("hist", "net_issuance_private_daily", "daily5", 1, +1, "gilts + letras − APF − vencimientos − cupones, por liquidación (D2.1A/D2.2D/D1A)")},
                       "C": {"exchequer_residual_w": ("hist", "exchequer_residual_weekly", "weekly", 7, +1, "residual del Exchequer semanal (canal de renta)")}}},
    "nzd": {"central_bank": {"A": "v0.3 (settlement cash Δ)",
                             "B": {"omo_net_5d": ("hist", "omo_net_daily", "daily5", 1, +1, "OMO por operación (D3); settlement cash = conciliación")},
                             "C": {}},
            "fiscal": {"A": "v0.3 (R3 mensual + proxy)",
                       "B": {"net_issuance_5d": ("hist", "net_issuance_private_daily", "daily5", 1, +1, "tenders por liquidación − letras vencidas − reembolsos y cupones BRUTOS al tenedor de mercado (NZDM bonds on issue, todos los cierres de mes; dos lados sólo desde el primer cierre de mes archivado)")},
                       "C": {"residual_5d": ("hist", "residual_flow_daily", "daily5", 1, +1, "proxy residual diario (conciliado D10 −7 mm)")}}},
    "chf": {"central_bank": {"A": "v0.3 (Δ GI semanal, cuota de absorción mensual)",
                             # publication lag 35 d (was 7): the proxy = ΔGI − ops − Confederation is only complete when the monthly gmges amounts
                             # arrive (~35 d after month-end); the 7-day lag overstated its as-of coverage (activation review 2026-09-11)
                             "B": {"fx_proxy_w": ("hist", "fx_intervention_proxy_v04", "weekly", 35, +1, "ΔGI − operaciones − Confederación, semanas completas")},
                             "C": {"ops_net_5d": ("hist", "ops_net_daily", "daily5", 35, +1, "Bills + repos por fecha; importes publicados ~35 días tras fin de mes (reloj de publicación)")}},
            "fiscal": {"A": "v0.3 (saldos de la Confederación mensuales)",
                       "B": {"net_issuance_5d": ("hist", "net_issuance_private_daily", "daily5", 2, +1, "MMDRC + bonos por liquidación T+2 (EFV)")},
                       "C": {}}},
    "aud": {"central_bank": {"A": "v0.3 (Δ ES diaria/20d)",
                             "B": {"omo_net_5d": ("hist", "omo_net_daily", "daily5", 1, +1, "OMO por operación; stock = A3 AORROMO ±0,1 %")},
                             "C": {}},
            "fiscal": {"A": "v0.3 (−Δ depósitos del gobierno semanal)",
                       "B": {"govt_delta": ("scores", "govt_account", "dweekly", 0, +1, "depósitos del gobierno semanales (A1) — identidad")},
                       "C": {"net_issuance_v2_5d": ("hist", "net_issuance_private_v2_daily", "daily5", 1, +1, "v2: tenders AOFM por Date Settled (caja) − notas/indexados − recompras + reembolsos y cupones de TB NETOS de la cartera del RBA (A3.1)")}}},
    "eur": {"central_bank": {"A": "v0.3 (exceso de liquidez diario)", "B": {}, "C": {}, "note": "Δ cartera WFS semanal sin histórico archivado (monpol_wow) → empate 3-3 sin resolver aquí"},
            "fiscal": {"A": "v0.3 (déficit estructural GFS.Q + −ΔL050100)",
                       "B": {"net_issuance_5d": ("hist", "net_issuance_private_daily", "daily5", 1, +1, "DE+FR+ES+IT+UE(+ESM) por liquidación + reembolsos y cupones BRUTOS de DE (historial Finanzagentur 1999→) y UE (Qlik 2020→); FR/ES/IT/ESM sólo un lado (sin saldo vivo por línea); ES/IT sólo desde 2022 (cobertura parcial antes)")},
                       "C": {}}},
    "jpy": {"central_bank": {"A": "v0.3 (CAB 20d, d/d, banda del balance)", "B": {}, "C": {}, "note": "operaciones por operación (ope) sólo desde el backfill del runner → replay pendiente de ese archivo"},
            "fiscal": {"A": "v0.3 (z del flujo del Tesoro)",
                       "B": {"treasury_5d": ("hist", "treasury_realized_daily", "daily5", 0, +1, "財政等要因 realizado (速報/確報) = −Δ cuenta del gobierno")},
                       "C": {"net_issuance_5d": ("hist", "net_issuance_private_daily", "daily5", 1, +1, "emisión neta del MoF por fecha de emisión, neta de mei")}}},
}
STRESS_GATE_BP = 5.0
ROLL_STEP_W = 13
MIN_WEEKS_ERA = 40


def _load_scores(ccy: str) -> List[dict]:
    p = os.path.join(ROOT, "calibration", "%s_v03" % ccy, "scores.csv")
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "None") else None
    except ValueError:
        return None


def _load_hist(ccy: str, name: str) -> Series:
    p = os.path.join(ROOT, "history", ccy, "%s.csv" % name)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for r in csv.reader(f):
            if r and r[0] != "date" and _f(r[1]) is not None:
                out.append((r[0], float(r[1])))
    out = sorted(out)
    # dense archives are zero-filled before the source's first record: a leading run of exact zeros is 'no data', not 'no flow'
    k = 0
    while k < len(out) and out[k][1] == 0.0:
        k += 1
    return out[k:] if k < len(out) else out


def _value_asof(ser: Series, d: str, kind: str, lag: int) -> Optional[float]:
    """as-of evaluation: only points whose date ≤ d − lag are known at d"""
    if not ser:
        return None
    cutoff = (date.fromisoformat(d) - timedelta(days=lag)).isoformat()
    ds = [x for x, _ in ser]
    i = bisect.bisect_right(ds, cutoff)
    if i == 0:
        return None
    if kind == "daily5":
        pts = ser[max(0, i - 5):i]
        first = date.fromisoformat(pts[0][0])
        if len(pts) < 5 or (date.fromisoformat(cutoff) - first).days > 12:
            return None
        return float(sum(v for _, v in pts))
    if kind == "weekly":
        d0, v = ser[i - 1]
        return v if (date.fromisoformat(cutoff) - date.fromisoformat(d0)).days <= 10 else None
    return None


def _component_series(ccy: str, comp: tuple, grid: List[str], scores: List[dict]) -> List[Optional[float]]:
    source, key, kind, lag, sign, _ = comp
    if source == "scores":
        col = [_f(r.get(key)) for r in scores]
        if kind == "dweekly":
            out = [None]
            for k in range(1, len(col)):
                out.append(-(col[k] - col[k - 1]) * sign if (col[k] is not None and col[k - 1] is not None) else None)
            return out
        return col
    ser = _load_hist(ccy, key)
    out = []
    for d in grid:
        v = _value_asof(ser, d, kind, lag)
        out.append(None if v is None else v * sign)
    return out


def _eff(sc: List[Optional[float]], dates: List[str]) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for k, v in enumerate(sc):
        pv = sc[k - 1] if k > 0 else None
        gap = (date.fromisoformat(dates[k]) - date.fromisoformat(dates[k - 1])).days if k > 0 else 99
        out.append(None if v is None else (round((v + pv) / 2, 4) if (pv is not None and gap <= PERSISTENCE["entry_days"]) else v))
    return out


def _fwd(series: List[Optional[float]], h: int) -> List[Optional[float]]:
    return [(series[i + h] - series[i]) if (i + h < len(series) and series[i] is not None and series[i + h] is not None) else None for i in range(len(series))]


def _method_b(eff: List[Optional[float]], stress: List[Optional[float]], gate: Optional[List[bool]] = None) -> dict:
    out = {}
    for h in (4, 12):
        fw = _fwd(stress, h)
        x = [e if (gate is None or gate[i]) else None for i, e in enumerate(eff)]
        rho, p, n = spearman(x, fw)
        out[str(h)] = {"rho": None if rho is None else round(rho, 3), "p": None if p is None else round(p, 4), "n": n,
                       "p_block_bootstrap": (lambda q: None if q is None else round(q, 4))(block_bootstrap_p(x, fw)),
                       "mmt_sign": (rho is not None and rho < 0)}
    return out


def _stability(scores_: List[Optional[float]], dates: List[str]) -> dict:
    """rolling-origin cuts: every 13 weeks from week 52 of the era to the end; compares the cut position and the state sequence"""
    full = [v for v in scores_ if v is not None]
    if len(full) < MIN_WEEKS_ERA:
        return {"status": "insuficiente", "weeks": len(full)}
    x = np.array(full, dtype=float)
    iqr = float(np.percentile(x, 80) - np.percentile(x, 20)) or 1e-9
    cuts_full = _era_cuts(x)
    reg_full = _regime_series(scores_, dates, cuts_full, PERSISTENCE)
    drift, agree, origins = [], [], []
    for o in range(52, len(scores_), ROLL_STEP_W):
        part = [v for v in scores_[:o] if v is not None]
        if len(part) < MIN_WEEKS_ERA:
            continue
        c = _era_cuts(np.array(part, dtype=float))
        reg = _regime_series(scores_[:o], dates[:o], c, PERSISTENCE)
        drift.append(max(abs(c["injection_enter"] - cuts_full["injection_enter"]), abs(c["drain_enter"] - cuts_full["drain_enter"])) / iqr)
        agree.append(float(np.mean([a == b for a, b in zip(reg, reg_full[:o])])))
        origins.append(dates[o - 1])
    if not drift:
        return {"status": "insuficiente", "weeks": len(full)}
    last_drift, last_agree = drift[-1], agree[-1]
    ok = last_drift < 0.10 and last_agree >= 0.90
    return {"status": "estable" if ok else "provisional", "weeks": len(full), "origins": len(origins), "last_origin": origins[-1],
            "cut_drift_last_over_iqr": round(last_drift, 3), "cut_drift_max_over_iqr": round(max(drift), 3), "state_agreement_last": round(last_agree, 3),
            "state_agreement_min": round(min(agree), 3)}


def _variant(ccy: str, block: str, label: str, comps: dict, grid: List[str], scores: List[dict], reserves: List[Optional[float]],
             stress: List[Optional[float]], base: Optional[List[Optional[float]]] = None) -> dict:
    checks = []
    names = list(comps)
    for a, b in FORBIDDEN_PAIRS:
        if a in names and b in names:
            checks.append("DOUBLE_COUNT %s+%s" % (a, b))
    if base is not None:
        sc = base
        cov = float(np.mean([v is not None for v in sc])) if sc else 0.0
        parts = {}
    else:
        parts = {n: _component_series(ccy, c, grid, scores) for n, c in comps.items()}
        sc = []
        for i, d in enumerate(grid):
            vals = [parts[n][i] for n in names]
            r = reserves[i]
            if not names or any(v is None for v in vals) or not r:
                sc.append(None)
            else:
                sc.append(round(sum(vals) / r * 100, 4))
        cov = float(np.mean([v is not None for v in sc])) if sc else 0.0
    eff = _eff(sc, grid)
    x = np.array([v for v in eff if v is not None], dtype=float)
    out = {"label": label, "components": {n: {"source": c[0] + ":" + c[1], "kind": c[2], "publication_lag_days": c[3], "sign": c[4], "reconciliation": c[5],
                                              "coverage": round(float(np.mean([v is not None for v in parts[n]])), 3) if n in parts else None} for n, c in comps.items()},
           "coverage_era": round(cov, 3), "weeks": int(len(x)), "checks": checks}
    if len(x) < MIN_WEEKS_ERA:
        out["status"] = "insuficiente (%d semanas con dato)" % len(x)
        return out
    cuts = _era_cuts(x)
    if cuts["injection_enter"] <= 0 or cuts["drain_enter"] >= 0:
        checks.append("ONE_SIDED: el corte de %s no cruza el cero (la serie no cambia de signo en la era; el 'régimen' opuesto sería sólo menos drenaje/inyección)"
                      % ("inyección" if cuts["injection_enter"] <= 0 else "drenaje"))
    reg = _regime_series(sc, grid, cuts, PERSISTENCE)
    n = len(reg)
    out.update({"cuts": cuts, "percentiles": {p: round(float(np.percentile(x, p)), 4) for p in (10, 20, 33, 50, 67, 80, 90)},
                "shares": {k: round(sum(1 for r in reg if r == k) / n, 3) for k in ("INJECTION", "NEUTRAL", "DRAIN", "NO SIGNAL")},
                "spells": _spells([r for r in reg if r != "NO SIGNAL"]), "stability": _stability(sc, grid),
                "B": _method_b(eff, stress), "B_scarcity_weeks": _method_b(eff, stress, [s is not None and abs(s) > STRESS_GATE_BP for s in stress]),
                "_regimes": reg, "_eff": eff})
    return out


def _compare(a: dict, b: dict) -> Optional[float]:
    ra, rb = a.get("_regimes"), b.get("_regimes")
    if not ra or not rb:
        return None
    pairs = [(x, y) for x, y in zip(ra, rb) if x != "NO SIGNAL" and y != "NO SIGNAL"]
    return round(float(np.mean([x == y for x, y in pairs])), 3) if pairs else None


def _select(variants: Dict[str, dict], note: Optional[str]) -> dict:
    """selection ladder (round 1): coverage/reconciliation → method B marginal (12 w primary, 4 w secondary; scarcity weeks as tie-break) → revisions (n/a)"""
    ok = {k: v for k, v in variants.items() if v.get("cuts")}
    if len(ok) <= 1:
        return {"decision": "A" if "A" in ok else None, "reason": "sólo una variante evaluable" + (" · " + note if note else "")}
    def _b(v, h="12"):
        b = v["B"].get(h, {})
        return (b.get("p_block_bootstrap") if b.get("mmt_sign") else None, abs(b.get("rho") or 0.0))
    sig = {k: _b(v) for k, v in ok.items() if _b(v)[0] is not None and _b(v)[0] <= 0.05}
    cands = {k: v for k, v in ok.items() if k == "A" or v["coverage_era"] >= 0.8}
    if sig:
        best = sorted(sig.items(), key=lambda kv: (kv[1][0], -kv[1][1]))[0][0]
        if best in cands:
            os_ = [c for c in ok[best].get("checks", []) if c.startswith("ONE_SIDED")]
            return {"decision": best, "reason": "método B a 12 s: ρ<0 con p_bootstrap ≤ 0,05 (%s); cobertura %.2f%s" % (best, ok[best]["coverage_era"],
                    " · aviso: la serie es de un solo signo — el estado 'inyección' es sólo menos drenaje (reembolsos y cupones de bonos fuera del flujo o cubiertos sólo en parte)" if os_ else "")}
    # no significant B: accounting truth decides — B (v0.4 base) when it covers the era, else A; C never by default
    if "B" in cands and ok["B"]["stability"].get("status") in ("estable", "provisional") and not any(c.startswith("ONE_SIDED") for c in ok["B"].get("checks", [])):
        rb = ok["B"]["B"].get("12", {})
        warn = " · aviso: ρ a 12 s con signo no MMT (%s, no significativo)" % rb.get("rho") if (rb.get("rho") or 0) > 0.1 else ""
        return {"decision": "B", "reason": "sin evidencia B significativa en ninguna variante → manda la verdad contable: v0.4 base por liquidación (cobertura %.2f, corte %s)%s"
                % (ok["B"]["coverage_era"], ok["B"]["stability"].get("status"), warn)}
    why = "no cubre la era (cobertura %s)" % ok.get("B", {}).get("coverage_era") if ok.get("B", {}).get("coverage_era", 0) < 0.8 else "es de un solo signo (%s)" % "; ".join(ok.get("B", {}).get("checks", []))[:80]
    return {"decision": "A", "reason": "sin evidencia B y la variante v0.4 %s → se mantiene v0.3" % why}


def replay(ccy: str) -> dict:
    scores = _load_scores(ccy)
    era = ERA_DEFAULT[ccy]
    rows = [r for r in scores if r["date"] >= era]
    grid = [r["date"] for r in rows]
    reserves = [_f(r.get("reserves")) for r in rows]
    stress = [_f(r.get("stress_bps")) for r in rows]
    res = {"currency": ccy, "era_start": era, "weeks": len(grid), "first": grid[0] if grid else None, "last": grid[-1] if grid else None,
           "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "truth": "stress_bps (v0.3 replay)", "blocks": {}}
    for block in ("central_bank", "fiscal"):
        spec = SPEC[ccy][block]
        base = [_f(r.get("cb_score" if block == "central_bank" else "fi_score")) for r in rows]
        variants = {"A": _variant(ccy, block, spec["A"], {}, grid, scores, reserves, stress, base=base)}
        if spec.get("B"):
            variants["B"] = _variant(ccy, block, "v0.4 base", spec["B"], grid, rows, reserves, stress)
        if spec.get("C"):
            variants["C"] = _variant(ccy, block, "candidato ronda 1", spec["C"], grid, rows, reserves, stress)
        agree = {k: _compare(variants["A"], v) for k, v in variants.items() if k != "A"}
        sel = _select(variants, spec.get("note"))
        for v in variants.values():
            v.pop("_regimes", None)
            v.pop("_eff", None)
        res["blocks"][block] = {"variants": variants, "agreement_with_A": agree, "selection": sel, "note": spec.get("note")}
    return res


def _md(res: dict) -> str:
    L = ["# Replay v0.4 · %s · era desde %s · %d semanas (%s → %s)" % (res["currency"].upper(), res["era_start"], res["weeks"], res["first"], res["last"]), ""]
    for block, b in res["blocks"].items():
        L.append("## %s" % block)
        if b.get("note"):
            L.append("_%s_" % b["note"])
        L.append("")
        L.append("| variante | cobertura | semanas | corte inyección (entra/sale) | corte drenaje | cuota INY/NEU/DRE | estabilidad | B 4s ρ (p_boot) | B 12s ρ (p_boot) | B escasez 12s | acuerdo con A |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for k, v in b["variants"].items():
            if not v.get("cuts"):
                L.append("| %s — %s | %s | %s | %s | | | | | | | |" % (k, v["label"], v.get("coverage_era"), v.get("weeks"), v.get("status", "")))
                continue
            c, s, st = v["cuts"], v["shares"], v["stability"]
            b4, b12, bs = v["B"]["4"], v["B"]["12"], v["B_scarcity_weeks"]["12"]
            L.append("| %s — %s | %.2f | %d | %s / %s | %s / %s | %.2f / %.2f / %.2f | %s | %s (%s) | %s (%s) | %s (%s) | %s |" % (
                k, v["label"], v["coverage_era"], v["weeks"], c["injection_enter"], c["injection_exit"], c["drain_enter"], c["drain_exit"],
                s["INJECTION"], s["NEUTRAL"], s["DRAIN"], st.get("status"), b4["rho"], b4["p_block_bootstrap"], b12["rho"], b12["p_block_bootstrap"], bs["rho"], bs["p_block_bootstrap"],
                b.get("agreement_with_A", {}).get(k, "—")))
        L.append("")
        for k, v in b["variants"].items():
            for n, cinfo in v.get("components", {}).items():
                L.append("- %s · `%s` ← %s · %s · retraso de publicación %d d · cobertura %s · conciliación: %s" % (k, n, cinfo["source"], cinfo["kind"], cinfo["publication_lag_days"], cinfo["coverage"], cinfo["reconciliation"]))
            if v.get("checks"):
                L.append("- **comprobaciones**: %s" % ", ".join(v["checks"]))
        L.append("")
        L.append("**Selección (escalera de la ronda 1): %s** — %s" % (b["selection"].get("decision"), b["selection"].get("reason")))
        L.append("")
    L.append("Robustez a revisiones (peldaño 3): no evaluable sin vintages archivados; el archivo por fecha de publicación empieza con el lote 2 (JPY tres columnas, BoC diario).")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ccys = [a for a in argv if a in SPEC] or list(SPEC)
    summary = ["# Replay v0.4 — resumen · %s" % datetime.utcnow().date().isoformat(), "",
               "| divisa | bloque | decisión | variante | corte inyección (entra/sale, % del stock en 5 sesiones) | corte drenaje | estabilidad | B 12 s ρ (p_boot) | motivo |",
               "|---|---|---|---|---|---|---|---|---|"]
    for ccy in ccys:
        res = replay(ccy)
        out_dir = os.path.join(ROOT, "calibration", "%s_v04" % ccy)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "replay_v04.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, ensure_ascii=False)
        with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
            f.write(_md(res))
        print("%s: %s" % (ccy, {k: v["selection"].get("decision") for k, v in res["blocks"].items()}))
    # the summary is rebuilt from every currency's JSON on disk, so a partial run (replay-v04 gbp eur nzd) never drops the other rows
    for ccy in SPEC:
        p = os.path.join(ROOT, "calibration", "%s_v04" % ccy, "replay_v04.json")
        if not os.path.exists(p):
            continue
        res = json.load(open(p, encoding="utf-8"))
        for block, b in res["blocks"].items():
            d = b["selection"].get("decision")
            v = b["variants"].get(d or "A", {})
            c = v.get("cuts") or {}
            b12 = (v.get("B") or {}).get("12", {})
            summary.append("| %s | %s | %s | %s | %s / %s | %s / %s | %s | %s (%s) | %s |" % (
                ccy.upper(), block, d, v.get("label", ""), c.get("injection_enter"), c.get("injection_exit"), c.get("drain_enter"), c.get("drain_exit"),
                (v.get("stability") or {}).get("status"), b12.get("rho"), b12.get("p_block_bootstrap"), b["selection"].get("reason")))
    with open(os.path.join(ROOT, "calibration", "REPLAY_V04.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
