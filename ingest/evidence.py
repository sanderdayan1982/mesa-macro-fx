"""Completeness of each leg and the published evidence — read-only views of files that already exist (adjudication 2026-09-11,
institutionality round, ideas C and D). Nothing is measured here: config/<ccy>.json (engine per block, equivalence_quality),
calibration/<ccy>_v04/replay_v04.json (variant B checks: ONE_SIDED / DOUBLE_COUNT, selection), calibration/conviction/
results.json (ICL 1.0), T123.json (T1–T3) and T4.json (T4). Published inside data/mesa/jefe.json so ESTADO reads one file.
Every reader is tolerant: a missing file yields «no disponible», never a guess."""
from __future__ import annotations

import json
import os
from typing import Dict, Optional

CCYS = ["cad", "gbp", "aud", "jpy", "chf", "nzd", "usd", "eur"]
NAMES = {"usd": "USD", "eur": "EUR", "gbp": "GBP", "jpy": "JPY", "chf": "CHF", "cad": "CAD", "aud": "AUD", "nzd": "NZD"}
PROXY_T = {"gbp", "nzd", "chf"}  # jefe.PROXY: Treasury driver is a proxy/band (no government account)
# decisions recorded in the adjudications where the engine deliberately differs from the replay selection
NO_REPLAY = {"usd": "sin replay v0.4 por diseño: el USD es la migración exacta de los tres dashboards (H.4.1, DTS, H.8/H.15) con sus anclas absolutas; sigue en v0.3"}
NOTES = {("chf", "central_bank"): "replay B pero no activado: la impresión completa (repos y SNB Bills) llega con 35 días de retraso; v0.3 semanal (3 días) manda",
         ("nzd", "fiscal"): "se queda v0.3: ONE_SIDED por economía (sin pata del gasto; el Tesoro NZ no publica cuenta diaria/semanal)",
         ("gbp", "fiscal"): "proxy: residual BoE + emisión neta DMO anclados al CGNCR; sin cuenta del gobierno pública",
         ("chf", "fiscal"): "régimen vivo v0.4 contable (MMDRC/bonos por liquidación); la columna Tesoro del jefe lee el score v0.3 (banda mensual de la Confederación) → proxy en el ranking hasta T1'/T2' sobre v0.4"}


def _rj(p: str) -> Optional[dict]:
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _engine(cfg: Optional[dict], block: str) -> str:
    v04 = (((cfg or {}).get("regime") or {}).get("dual") or {}).get("v04") or {}
    b = v04.get(block) or {}
    return "v0.4" if b.get("active") else "v0.3"


def _replay_checks(rep: Optional[dict], block: str) -> dict:
    """variant B checks and selection of the runner replay for one block; empty when the replay is absent."""
    if not rep:
        return {"replay": None}
    blk = ((rep.get("blocks") or {}).get(block)) or {}
    B = ((blk.get("variants") or {}).get("B")) or {}
    sel = blk.get("selection") or {}
    return {"replay": rep.get("generated_at"), "checks": B.get("checks") or [], "coverage_era": B.get("coverage_era"), "reason": sel.get("reason"),
            "stability": ((B.get("stability") or {}).get("status")), "selected": sel.get("decision"),
            "B_rho_12w": ((B.get("B") or {}).get("12") or {}).get("rho"), "B_p_12w": ((B.get("B") or {}).get("12") or {}).get("p_block_bootstrap")}


def completeness(root: str) -> Dict[str, dict]:
    """Per currency, per leg: what the number is made of. Marks only — nothing weights the ranking (weighting would need
    pre-registration). truth: «contable» (two-signed daily/weekly primary flow) · «proxy» (band/residual, jefe.PROXY) ·
    «unilateral» (replay check ONE_SIDED on the v0.4 base variant)."""
    out: Dict[str, dict] = {}
    for c in CCYS:
        cfg = _rj(os.path.join(root, "config", "%s.json" % c))
        rep = _rj(os.path.join(root, "calibration", "%s_v04" % c, "replay_v04.json"))
        blocks = (cfg or {}).get("blocks") or {}
        legs = {}
        for leg, block in (("bc", "central_bank"), ("treasury", "fiscal")):
            rc = _replay_checks(rep, block)
            checks = rc.get("checks") or []
            one_sided = "ONE_SIDED" in checks
            proxy = leg == "treasury" and c in PROXY_T
            truth = "proxy" if proxy else "unilateral" if one_sided else "contable"
            legs[leg] = {"engine": _engine(cfg, block), "truth": truth, "proxy": proxy, "one_sided": one_sided,
                         "equivalence_quality": (blocks.get(block) or {}).get("equivalence_quality"),
                         "replay_checks": checks, "replay_selected": rc.get("selected"), "replay_stability": rc.get("stability"),
                         "replay_coverage_era": rc.get("coverage_era"), "replay_generated_at": rc.get("replay")}
        out[NAMES[c]] = legs
    return out


def _ic(rec: Optional[dict]) -> Optional[dict]:
    if not isinstance(rec, dict):
        return None
    return {"mean": rec.get("mean"), "ci95": rec.get("ci95"), "p": rec.get("p"), "n": rec.get("n"), "block": rec.get("block")}


def evidence(root: str) -> dict:
    """The pre-registered tests behind the two jefe columns and the v0.4 activations, as published in calibration/."""
    conv = os.path.join(root, "calibration", "conviction")
    R = _rj(os.path.join(conv, "results.json")) or {}
    T = _rj(os.path.join(conv, "T123.json")) or {}
    T4 = _rj(os.path.join(conv, "T4.json")) or {}
    tests = []
    # ICL 1.0 — the BC column (secondary pre-registered arm, one look, BH family)
    absR = ((R.get("secondary") or {}).get("absolute")) or {}
    for h in ("8", "13", "26"):
        r = absR.get("reserves_d13_pct_%s" % h)
        if r:
            tests.append({"id": "ICL-BC-%s" % h, "column": "BC", "hypothesis": "Δ13 s de reservas del BC en %% del stock, demeaned entre las ocho, predice el retorno residual a %s s" % h,
                          "preregistered": "2026-09-09 (ronda 2, diseño 1.0)", "run": "2026-09-09", "horizon_weeks": int(h), "ic": _ic(r),
                          "q_bh": r.get("q_bh_family"), "first_half": r.get("first_half"), "second_half": r.get("second_half"),
                          "status": "validado" if (r.get("q_bh_family") is not None and r["q_bh_family"] < 0.05) else "no pasa"})
    if not absR:
        tests.append({"id": "ICL-BC", "column": "BC", "hypothesis": "Δ13 s de reservas del BC en % del stock (ICL 1.0, brazo secundario)", "preregistered": "2026-09-09", "run": "2026-09-09",
                      "horizon_weeks": None, "ic": None, "q_bh": None, "status": "no disponible: calibration/conviction/results.json no está en el repo (la firma vive en jefe.signature)"})
    prim = ((R.get("primary") or {}).get("tests")) or []
    if prim:
        best = min(prim, key=lambda t: (t.get("q_bh") if t.get("q_bh") is not None else 9))
        tests.append({"id": "ICL-primario", "column": "BC", "hypothesis": "posición semanal de flujos (n = Φ⁻¹ del percentil de era) predice el retorno residual (brazo primario)",
                      "preregistered": "2026-09-09", "run": "2026-09-09", "horizon_weeks": best.get("h"), "ic": _ic(best.get("ic")), "q_bh": best.get("q_bh"),
                      "status": "no pasa (ruido blanco semanal; ninguna q < 0,27)"})
    h2 = R.get("H2_elasticity") or {}
    if h2:
        tests.append({"id": "H2", "column": "puerta de precio", "hypothesis": "el spread de financiación (capa 4, |spread| > 5 pb) predice el retorno residual FX (elasticidad del precio del dinero)",
                      "preregistered": "2026-09-09 (diseño 1.0, H2)", "run": "2026-09-09", "horizon_weeks": None,
                      "ic": {"mean": h2.get("spearman"), "ci95": None, "p": h2.get("p"), "n": h2.get("n"), "block": None}, "q_bh": None,
                      "status": "no pasa: el precio del dinero no predice la dirección del FX; la puerta de precio confirma o niega el régimen de reservas, no ordena (ρ %s, p %s, n %s)" % (h2.get("spearman"), h2.get("p"), h2.get("n"))})
    for t in T.get("tests") or []:
        tests.append({"id": t.get("test"), "column": "Tesoro", "hypothesis": {"T1": "Φ⁻¹ del percentil de era de la media 13 s del flujo fiscal predice el retorno residual a 13 s",
                                                                                "T2": "misma medida a 26 s", "T3": "−Δ13 s de la cuenta del gobierno en % de reservas, a 13 s (GBP excluido: sin cuenta)"}.get(t.get("test"), t.get("signal")),
                      "preregistered": "2026-09-09 (adjudicación ronda 3 §3)", "run": "2026-09-11", "horizon_weeks": t.get("h"), "ic": _ic(t.get("ic")), "q_bh": t.get("q_bh"),
                      "first_half": t.get("ic_first_half"), "second_half": t.get("ic_second_half"), "tercile_spread_pct": _ic(t.get("tercile_spread_pct")),
                      "excluded": t.get("excluded"), "status": "validado" if t.get("survives") else "no pasa"})
    for t in T4.get("tests") or []:
        tests.append({"id": t.get("test"), "column": "Tesoro (aceleración)", "hypothesis": "la aceleración (Δ de la media 13 s) añade IC parcial sobre la velocidad a %s s" % t.get("h"),
                      "preregistered": "2026-09-11 (adjudicación fontanería §2)", "run": "2026-09-11", "horizon_weeks": t.get("h"), "ic": _ic(t.get("ic_partial")), "q_bh": t.get("q_bh"),
                      "status": "no pasa → sólo marca de cruce por cero (zero_cross)" if not t.get("survives") else "validado"})
    # v0.4 activations: selection per block from the runner replays (accounting truth ladder), nothing predictive claimed
    acts = []
    for c in CCYS:
        rep = _rj(os.path.join(root, "calibration", "%s_v04" % c, "replay_v04.json"))
        cfg = _rj(os.path.join(root, "config", "%s.json" % c))
        for block in ("central_bank", "fiscal"):
            rc = _replay_checks(rep, block)
            acts.append({"ccy": NAMES[c], "block": block, "engine": _engine(cfg, block), "replay_selected": rc.get("selected"), "checks": rc.get("checks"), "note": NOTES.get((c, block)) or (rc.get("reason") if rep else NO_REPLAY.get(c)),
                         "coverage_era": rc.get("coverage_era"), "stability": rc.get("stability"), "B_rho_12w": rc.get("B_rho_12w"), "B_p_12w": rc.get("B_p_12w"),
                         "replay_generated_at": rc.get("replay")})
    return {"rule": "una mirada por prerregistro; BH (Benjamini–Hochberg) por familia; bootstrap por bloques; nada entra en el ranking sin pasar su test; los cortes v0.4 salen del replay (escalera: verdad contable → B marginal → robustez), no de la predicción",
            "tests": tests, "activations": acts,
            "files": ["calibration/conviction/results.json", "calibration/conviction/T123.json", "calibration/conviction/T4.json", "calibration/<ccy>_v04/replay_v04.json"]}
