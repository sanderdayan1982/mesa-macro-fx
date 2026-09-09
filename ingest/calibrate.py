"""Empirical calibration of the dual regime (desk rule 2026-09-09): block thresholds, dual weights, general thresholds and auction anchors
are ESTIMATED from history, never hand-picked.

Method
  1. Replay: every block builder is re-run week by week with only the data that existed on that date (as-of, no look-ahead; hysteresis
     carried through `prev` exactly as the live runner does) → weekly series of central-bank and treasury block scores.
  2. Truth: the desk hypothesis (MMT/Mosler) is that a liquidity INJECTION weakens the currency and a DRAIN strengthens it. The
     observable is the forward log return of the currency vs USD (USD: broad dollar index) at 5 / 10 / 20 sessions; secondary observable
     = forward change of the currency's stress spread.
  3. Statistics: Spearman rank correlation of each block score with the forward returns; walk-forward (expanding window: fit on the
     past, evaluate on the next block of weeks) so nothing is chosen with future data.
  4. Thresholds: for each block, a grid of candidate cut-offs; a cut-off is accepted only if the conditional mean of the forward return
     beyond the cut-off differs from the rest with |t| >= 2 in the training window AND keeps its sign out of sample, with a minimum
     coverage (share of weeks) so the regime is not a curiosity. Otherwise the block keeps the agreement rule (no threshold invented).
  5. Dual weights: OLS of the forward return on the two standardized block scores (walk-forward); weights = normalized |coefficients|
     when both carry the hypothesised sign, else the significant block alone.
  6. Auctions (where the currency has auction data): bid-to-cover / tail anchors = empirical percentiles per instrument, validated the
     same way (do weak auctions precede a different forward yield / FX path?).
Outputs: calibration/<ccy>/scores.csv, report.md, dual_proposal.json (the config patch).
Usage: python -m ingest.calibrate --ccy cad [--start 2008-01-01] [--fixtures fixtures/cad]"""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy import stats
from .series import Series, clean

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HORIZONS = (5, 10, 20)


# ───────────────────────────── helpers ─────────────────────────────
# ── engine v0.3 replay settings ──
# era anchoring of percentile windows switches on when the as-of date enters the operating era (before it, rolling windows as in v0.2)
ERA: Dict[str, Optional[str]] = {"start": None}
ERA_DEFAULT = {"cad": "2020-03-23", "gbp": "2022-11-01", "aud": "2025-04-09", "jpy": "2024-07-31", "chf": "2022-09-22", "nzd": "2022-07-01", "usd": "2022-06-01", "eur": "2022-09-14"}
LW_GRID = [1.0, 0.5, 0.25, 0.0]          # pre-registered level weights (1.0 = v0.2 arithmetic)
PERSISTENCE = {"entry_days": 7, "exit_days": 0, "mode": "mean"}   # operating rule: 2-week mean beyond the enter cut (two weekly prints), one print past the exit cut to leave
PERSISTENCE_VARIANTS = {"none": {"entry_days": 0, "exit_days": 0}, "consecutive_7_0": {"entry_days": 7, "exit_days": 0, "mode": "consecutive"}, "mean_7_0": PERSISTENCE,
                        "mean_7_7": {"entry_days": 7, "exit_days": 7, "mode": "mean"}}


def trunc(data: Dict[str, Series], d: str, lookback_days: int = 1500) -> Dict[str, Series]:
    """as-of view: nothing after d; nothing older than the longest rolling window the blocks use (156 weeks ≈ 1,100 days, margin to 1,500)."""
    from . import thresholds as TH
    TH.set_era_anchor(ERA["start"] if (ERA["start"] and d >= ERA["start"]) else None)
    lo = (date.fromisoformat(d) - timedelta(days=lookback_days)).isoformat()
    return {k: [(x, v) for x, v in s if lo <= x <= d] for k, s in data.items()}


def fwd_returns(fx: Series, dates: List[str], horizons=HORIZONS) -> Dict[int, List[Optional[float]]]:
    """forward log return of the quote (currency per USD → + = currency weaker) from the first session > d, h sessions ahead."""
    fd = [x for x, _ in fx]
    fv = np.array([v for _, v in fx], dtype=float)
    out = {h: [] for h in horizons}
    import bisect
    for d in dates:
        i = bisect.bisect_right(fd, d)   # first session strictly after d
        for h in horizons:
            if i > 0 and i + h < len(fv) and fv[i] > 0 and fv[i + h] > 0:   # i == 0 → the date precedes the FX history: no return
                out[h].append(math.log(fv[i + h] / fv[i]) * 100)
            else:
                out[h].append(None)
    return out


def _clean_pairs(a: List[Optional[float]], b: List[Optional[float]]) -> Tuple[np.ndarray, np.ndarray]:
    x, y = [], []
    for u, v in zip(a, b):
        if u is not None and v is not None and not (isinstance(u, float) and math.isnan(u)):
            x.append(u); y.append(v)
    return np.array(x, dtype=float), np.array(y, dtype=float)


def spearman(x, y) -> Tuple[Optional[float], Optional[float], int]:
    x, y = _clean_pairs(x, y)
    if len(x) < 30 or np.std(x) == 0:
        return None, None, len(x)
    r, p = stats.spearmanr(x, y)
    return float(r), float(p), len(x)


def cond_test(score, ret, cut: float, side: str) -> dict:
    """mean forward return when score beyond cut vs the rest (Welch t)."""
    s, r = _clean_pairs(score, ret)
    if side == "ge":
        m = s >= cut
    else:
        m = s <= cut
    n1, n0 = int(m.sum()), int((~m).sum())
    if n1 < 20 or n0 < 20:
        return {"n_in": n1, "n_out": n0, "t": None, "diff": None}
    t, p = stats.ttest_ind(r[m], r[~m], equal_var=False)
    return {"n_in": n1, "n_out": n0, "coverage": round(n1 / len(s), 3), "mean_in": round(float(r[m].mean()), 3), "mean_out": round(float(r[~m].mean()), 3),
            "diff": round(float(r[m].mean() - r[~m].mean()), 3), "t": round(float(t), 2), "p": round(float(p), 4)}


def threshold_search(score: List[Optional[float]], ret: List[Optional[float]], dates: List[str], split: str, side: str, sign: int,
                     grid: np.ndarray, min_cov: float = 0.10) -> dict:
    """side 'ge' = injection cut (expects sign*diff > 0), 'le' = drain cut. Train = dates < split, test = dates >= split."""
    tr = [i for i, d in enumerate(dates) if d < split]
    te = [i for i, d in enumerate(dates) if d >= split]
    best = None
    rows = []
    for q in grid:
        a = cond_test([score[i] for i in tr], [ret[i] for i in tr], float(q), side)
        b = cond_test([score[i] for i in te], [ret[i] for i in te], float(q), side)
        rows.append({"cut": round(float(q), 2), "train": a, "test": b})
        if a.get("t") is None or a.get("coverage", 0) < min_cov:
            continue
        ok_train = sign * a["diff"] > 0 and abs(a["t"]) >= 2.0
        ok_test = b.get("diff") is not None and sign * b["diff"] > 0
        if ok_train and ok_test:
            key = abs(a["t"])
            if best is None or key > best["key"]:
                best = {"key": key, "cut": round(float(q), 2), "train": a, "test": b}
    return {"best": best, "grid": rows}


def walk_forward_corr(score, ret, dates, blocks_years: int = 2) -> List[dict]:
    """expanding window: correlation measured on each successive block of `blocks_years` using only that block (pure out-of-sample view)."""
    out = []
    ys = sorted(set(d[:4] for d in dates))
    for i in range(0, len(ys), blocks_years):
        yy = ys[i:i + blocks_years]
        idx = [k for k, d in enumerate(dates) if d[:4] in yy]
        r, p, n = spearman([score[k] for k in idx], [ret[k] for k in idx])
        out.append({"years": "%s–%s" % (yy[0], yy[-1]), "n": n, "rho": None if r is None else round(r, 3), "p": None if p is None else round(p, 3)})
    return out


def ols_weights(cb, fi, ret, dates, split: str, sign: int) -> dict:
    idx = [i for i in range(len(dates)) if cb[i] is not None and fi[i] is not None and ret[i] is not None]
    tr = [i for i in idx if dates[i] < split]
    te = [i for i in idx if dates[i] >= split]
    if len(tr) < 60:
        return {"status": "insufficient"}
    X = np.array([[cb[i], fi[i]] for i in tr]); y = np.array([ret[i] for i in tr])
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = (X - mu) / sd
    A = np.column_stack([np.ones(len(Z)), Z])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    dof = max(1, len(y) - 3)
    s2 = resid @ resid / dof
    cov = s2 * np.linalg.pinv(A.T @ A)
    se = np.sqrt(np.diag(cov))
    t = beta / se
    res = {"beta_cb": round(float(beta[1]), 4), "beta_fi": round(float(beta[2]), 4), "t_cb": round(float(t[1]), 2), "t_fi": round(float(t[2]), 2), "n_train": len(tr), "n_test": len(te)}
    ok_cb, ok_fi = sign * beta[1] > 0 and abs(t[1]) >= 2, sign * beta[2] > 0 and abs(t[2]) >= 2
    if ok_cb and ok_fi:
        w = np.abs(beta[1:]) / np.abs(beta[1:]).sum()
        res["weights"] = {"central_bank": round(float(w[0]), 2), "fiscal": round(float(w[1]), 2)}
        res["status"] = "both significant with the hypothesised sign"
    elif ok_cb:
        res["weights"] = {"central_bank": 1.0, "fiscal": 0.0}; res["status"] = "only the central-bank block is significant"
    elif ok_fi:
        res["weights"] = {"central_bank": 0.0, "fiscal": 1.0}; res["status"] = "only the treasury block is significant"
    else:
        res["status"] = "neither block significant in the training window — keep the agreement rule, no dual weights"
    # out-of-sample check of the fitted dual score
    if te and "weights" in res:
        w = res["weights"]
        ds = [w["central_bank"] * cb[i] + w["fiscal"] * fi[i] for i in te]
        r, p, n = spearman(ds, [ret[i] for i in te])
        res["oos"] = {"rho": None if r is None else round(r, 3), "p": None if p is None else round(p, 3), "n": n}
    return res


def load_series_csv(path: str, cols: List[str]) -> Dict[str, Series]:
    out = {c: [] for c in cols}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for c in cols:
                v = row.get(c, "")
                if v not in ("", None):
                    out[c].append((row["date"], float(v)))
    return {k: clean(v) for k, v in out.items()}


# ───────────────────────────── CAD replay ─────────────────────────────
def replay_cad(cfg: dict, fx_dir: str, start: str) -> dict:
    from . import blocks as B
    from .providers import ValetProvider, ReceiverGeneralProvider
    from .run import series_ids
    valet = ValetProvider(fixtures_dir=fx_dir)
    ids = sorted(set(series_ids(cfg, "central_bank") + series_ids(cfg, "rates") + ["V36628", "V36811"]))
    V = valet.fetch(ids)
    rg = ReceiverGeneralProvider("", "", fixtures_dir=fx_dir).fetch()
    b2_dates = [d for d, _ in V["V36610"] if d >= start]
    rows = []
    prev_cb = prev_fi = prev_rt = None
    for d in b2_dates:
        Vd, rgd = trunc(V, d), trunc(rg, d)
        cb = B.build_central_bank(cfg, Vd, prev_cb)
        fi = B.build_fiscal(cfg, Vd, rgd, prev_fi)
        rt = B.build_rates(cfg, Vd, prev_rt)
        prev_cb, prev_fi, prev_rt = cb, fi, rt
        od = rt["derived"].get("overnight_minus_deposit_bps", {})
        rows.append({"date": d, "cb_score": cb["signals"]["score"] if cb["signals"]["traffic_light"] != "NONE" else None, "cb_label": cb["signals"]["label"], "cb_comp": cb["signals"].get("components"), "fi_comp": fi["signals"].get("components"),
                     "fi_score": fi["signals"]["score"] if fi["signals"]["traffic_light"] != "NONE" else None, "fi_label": fi["signals"]["label"],
                     "reserves": cb["series"]["reserves"]["value"], "reserves_level": cb["series"]["reserves"]["level"],
                     "net_liq_wow": cb["derived"]["net_liquidity_wow_pct"]["value"], "govt_account": cb["series"]["government_account"]["value"],
                     "fiscal_7d": fi["derived"]["fiscal_flow_7d_cum"]["value"], "fiscal_z": fi["derived"]["fiscal_flow_zscore"]["value"],
                     "stress_bps": od.get("value"), "stress_level": od.get("level")})
    fx = load_series_csv(os.path.join(fx_dir, "fx_usdcad.csv"), ["FXUSDCAD", "IEXE0101"])
    # splice: noon rate until FXUSDCAD starts (2017-01-03)
    first = fx["FXUSDCAD"][0][0] if fx["FXUSDCAD"] else "9999"
    spot = clean([(d, v) for d, v in fx["IEXE0101"] if d < first] + fx["FXUSDCAD"])
    stress = clean([(r["date"], r["stress_bps"]) for r in rows if r["stress_bps"] is not None])
    auctions = load_auctions_cad(fx_dir)
    return {"rows": rows, "fx": spot, "fx_label": "USD/CAD (Valet FXUSDCAD; IEXE0101 noon before 2017) — + = CAD weaker", "stress": stress, "auctions": auctions,
            "structural_breaks": [{"date": "2020-03-23", "note": "BoC moves to a floor system (settlement balances from ~C$250m to tens of billions; QE); CB anchors 50–70bn only meaningful after this date"}]}


def load_auctions_cad(fx_dir: str) -> dict:
    out = {}
    for name, pre, kind in (("AUC_TBILL_RESULTS.csv", "AUC_TBILL_", "bills"), ("AUC_BOND_RESULTS.csv", "AUC_BOND_", "bonds")):
        p = os.path.join(fx_dir, name)
        if not os.path.exists(p):
            continue
        rows = []
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    cov = float(r.get(pre + "COVERAGE") or "nan"); tail = float(r.get(pre + "TAIL") or "nan"); amt = float(r.get(pre + "AMOUNT") or "nan")
                except ValueError:
                    continue
                term = r.get(pre + "TERM_DAYS") or r.get(pre + "TERM_YEARS") or ""
                rows.append({"date": r[pre + "AUCTION_DATE"], "coverage": cov, "tail": tail, "amount": amt, "term": term, "yield": float(r.get(pre + "AVG_YIELD") or "nan")})
        out[kind] = [x for x in rows if x["date"] and not math.isnan(x["coverage"])]
    return out


def replay_gbp(cfg: dict, fx_dir: str, start: str) -> dict:
    """GBP: IADB weekly Bank Return (since 2006-05 for reserves), daily rates/FX (since 1997), ONS PSF monthly (since 1984/1997);
    DMO outright gilt auctions (D2.1A PDF → CSV, since 1998) and T-bill tenders (D2.2D XML → CSV, since 2001)."""
    from . import blocks_gbp as BG
    from .providers import IadbProvider, OnsProvider
    from .run import series_ids
    iadb = IadbProvider(fixtures_dir=fx_dir)
    ons = OnsProvider("", fixtures_dir=fx_dir)
    codes = sorted(set(series_ids(cfg, "central_bank") + series_ids(cfg, "rates") + [cfg["desk_exports"]["gbpusd"]["id"], cfg["desk_exports"]["eurgbp_inv"]["id"]]))
    V = iadb.fetch(codes, "1997-01-01", "2030-01-01")
    O = ons.fetch(series_ids(cfg, "fiscal"))
    wk = [d for d, _ in V["RPWB56A"] if d >= start]
    rows = []
    prev_cb = prev_fi = prev_rt = None
    for d in wk:
        Vd, Od = trunc(V, d), trunc(O, d)
        cb = BG.build_central_bank(cfg, Vd, prev_cb)
        fi = BG.build_fiscal(cfg, Od, prev_fi)
        rt = BG.build_rates(cfg, Vd, prev_rt)
        prev_cb, prev_fi, prev_rt = cb, fi, rt
        od = rt["derived"].get("overnight_minus_policy_bps", {})
        rows.append({"date": d, "cb_score": cb["signals"]["score"] if cb["signals"]["traffic_light"] != "NONE" else None, "cb_label": cb["signals"]["label"], "cb_comp": cb["signals"].get("components"), "fi_comp": fi["signals"].get("components"),
                     "fi_score": fi["signals"]["score"] if fi["signals"]["traffic_light"] != "NONE" else None, "fi_label": fi["signals"]["label"],
                     "reserves": cb["series"]["reserves"]["value"], "reserves_level": cb["series"]["reserves"]["level"],
                     "net_liq_wow": (cb["derived"].get("net_liquidity_wow_pct") or {}).get("value"), "govt_account": None,
                     "fiscal_7d": (fi["derived"].get("net_spending") or {}).get("value"), "fiscal_z": (fi["derived"].get("cgncr_zscore") or {}).get("value"),
                     "stress_bps": od.get("value"), "stress_level": od.get("level")})
    fx = clean(V.get(cfg["desk_exports"]["gbpusd"]["id"], []))
    spot = clean([(d, round(1.0 / v, 6)) for d, v in fx if v])   # USD per GBP → GBP per USD (+ = GBP weaker)
    stress = clean([(r["date"], r["stress_bps"]) for r in rows if r["stress_bps"] is not None])
    auctions = {}
    p = os.path.join(fx_dir, "gilt_auctions_D21A.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            rs = list(csv.DictReader(f))
        for kind in ("conventional", "index-linked"):
            auctions["gilts_" + kind] = [{"date": r["date"], "coverage": float(r["bid_to_cover"]), "tail": float(r["tail_bp"]) if r["tail_bp"] not in ("", "None") else float("nan"), "amount": float(r["nominal_auction_m"]), "term": r["gilt"], "yield": float(r["yield_aap"]) if r["yield_aap"] else float("nan")}
                                        for r in rs if r["kind"] in (kind, "green" if kind == "conventional" else "-") and r["bid_to_cover"]]
    p = os.path.join(fx_dir, "tbill_tenders_D22D.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            rs = list(csv.DictReader(f))
        auctions["tbills"] = [{"date": r["tender_date"], "coverage": float(r["cover"]), "tail": float(r["tail_bp"]) if r["tail_bp"] else float("nan"), "amount": float(r["size_m"]), "term": r["maturity_type"], "yield": float(r["avg_yield"]) if r["avg_yield"] else float("nan")} for r in rs if r["cover"]]
    return {"rows": rows, "fx": spot, "fx_label": "GBP per USD (1 / XUDLUSS) — + = GBP weaker", "stress": stress, "auctions": auctions,
            "structural_breaks": [{"date": "2009-03-05", "note": "QE + reserves remunerated at Bank Rate: floor system (reserves-averaging corridor before)"},
                                  {"date": "2022-11-01", "note": "APF gilt sales start (active QT); reserves scarcity framework (PMRR 365–515bn) from 2024"}]}


def _load_tenders(path: str, kind_label: str) -> List[dict]:
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                cov = float(r["coverage"]) if r["coverage"] not in ("", "None") else float("nan")
            except ValueError:
                cov = float("nan")
            if math.isnan(cov):
                continue
            tail = float(r["tail_bp"]) if r.get("tail_bp") not in ("", None, "None") else float("nan")
            amt = float(r["allotted"]) / 1e6 if r.get("allotted") not in ("", None, "None") else float("nan")
            out.append({"date": r["date"], "coverage": cov, "tail": tail, "amount": amt, "term": r.get("maturity", ""), "yield": float(r["wa_yield"]) if r.get("wa_yield") not in ("", None, "None") else float("nan")})
    return out


def replay_aud(cfg: dict, fx_dir: str, start: str) -> dict:
    """AUD: RBA tables A1 (weekly since 2013-07), A3 ES balances (daily since 2013-11), F1/F2 (daily since 2011/2013), A2, D1/D3;
    AUD/USD daily from the RBA historical XLS (2010–2022) + F11.1 (2023–); AOFM tender results (Data Hub XLSX: bonds since 1982, notes since 1989)."""
    from . import blocks_aud as BA
    from .providers import RbaProvider
    rba = RbaProvider(fixtures_dir=fx_dir)
    T = {"a1": "rba_a1-data.csv", "a3_es": "rba_a3-es-balances-and-repo-agreements.csv", "f1": "rba_f1-data.csv", "f2": "rba_f2-data.csv", "a2": "rba_a2-data.csv", "d1": "rba_d1-data.csv", "d3": "rba_d3-data.csv"}
    def ids(block, tab):
        return [x["id"] for x in cfg["blocks"][block]["series"].values() if x.get("id") and x.get("table") == tab]
    V: Dict[str, Series] = {}
    for tab, fn in T.items():
        want = sorted(set(i for b in cfg["blocks"] for i in ids(b, tab)))
        if want:
            V.update(rba.fetch(fn.replace(".csv", ""), want, since=None, fixture_name=fn))
    wk = [d for d, _ in V["ARBALESBW"] if d >= start]
    rows = []
    prev_cb = prev_fi = prev_rt = None
    for d in wk:
        Vd = trunc(V, d)
        cb = BA.build_central_bank(cfg, Vd, prev_cb)
        fi = BA.build_fiscal(cfg, Vd, prev_fi)
        rt = BA.build_rates(cfg, Vd, prev_rt)
        prev_cb, prev_fi, prev_rt = cb, fi, rt
        od = rt["derived"].get("overnight_minus_target_bps") or rt["derived"].get("overnight_minus_policy_bps") or {}
        rows.append({"date": d, "cb_score": cb["signals"]["score"] if cb["signals"]["traffic_light"] != "NONE" else None, "cb_label": cb["signals"]["label"], "cb_comp": cb["signals"].get("components"), "fi_comp": fi["signals"].get("components"),
                     "fi_score": fi["signals"]["score"] if fi["signals"]["traffic_light"] != "NONE" else None, "fi_label": fi["signals"]["label"],
                     "reserves": cb["series"]["reserves"]["value"], "reserves_level": cb["series"]["reserves"]["level"],
                     "net_liq_wow": None, "govt_account": cb["series"]["government_account"]["value"],
                     "fiscal_7d": (fi["derived"].get("fiscal_flow_4w_cum") or {}).get("value"), "fiscal_z": (fi["derived"].get("fiscal_flow_zscore") or {}).get("value"),
                     "stress_bps": od.get("value"), "stress_level": od.get("level")})
    fx = load_series_csv(os.path.join(fx_dir, "fx_audusd.csv"), ["FXRUSD"])["FXRUSD"]
    spot = clean([(d, round(1.0 / v, 6)) for d, v in fx if v])   # USD per AUD → AUD per USD (+ = AUD weaker)
    stress = clean([(r["date"], r["stress_bps"]) for r in rows if r["stress_bps"] is not None])
    auctions = {"bonds": _load_tenders(os.path.join(fx_dir, "aofm_bond_tenders.csv"), "bonds"), "notes": _load_tenders(os.path.join(fx_dir, "aofm_note_tenders.csv"), "notes"),
                "indexed": _load_tenders(os.path.join(fx_dir, "aofm_tib_tenders.csv"), "indexed")}
    return {"rows": rows, "fx": spot, "fx_label": "AUD per USD (1 / FXRUSD) — + = AUD weaker", "stress": stress, "auctions": auctions,
            "structural_breaks": [{"date": "2020-03-19", "note": "RBA package: TFF, bond purchases, ES balances from ~A$2–3bn to hundreds of billions (floor)"},
                                  {"date": "2025-04-09", "note": "ample-reserves framework: full-allotment OMO at target + 10 bp, no ES target (calibration era)"}]}


def replay_jpy(cfg: dict, fx_dir: str, start: str) -> dict:
    """JPY: daily 'Sources of Changes in Current Account Balances' (jd) from the BoJ HTML archive 2023-01 → 2025-10 + XLSX since 2025-10,
    BoJ Accounts every ten days (HTML archive), basic loan rate steps, TONA (FM01) and USD/JPY 9:00 Tokyo (FM08 FXERD01) from the BoJ API,
    MoF past auction results (JGBs since 1979 by tenor, T-bills since 2009). Era: end of NIRP/YCC 2024-03-19; first hike 2024-07-31."""
    from . import blocks_jpy as BJ
    from .providers_jpy import read_fixture
    from .series import clean as _c
    D: Dict[str, Series] = {}
    for fn in ("boj_daily_jd_hist_wide.csv", "boj_daily_jd_wide.csv", "boj_accounts_hist_wide.csv", "boj_accounts_wide.csv", "boj_policy_rates.csv", "tona_hist.csv", "tona_volume_hist.csv",
               "boj_api_fm01_wide.csv", "boj_api_md06_wide.csv", "boj_api_md08_wide.csv", "mof_jgbcme_wide.csv", "jsda_trr_wide.csv", "mof_receipts.csv", "boj_fcall.csv"):
        got = read_fixture(os.path.join(fx_dir, fn))
        pre = "ac_" if fn.startswith("boj_accounts") else ""
        for k, v in got.items():
            D[pre + k] = _c(D.get(pre + k, []) + v)
    # policy rates as step series (config: policy_rate = basic_loan_rate − 0.25; ioer = policy_rate)
    blr = D.get("basic_loan_rate", [])
    D["policy_rate"] = [(d, round(v - 0.25, 3)) for d, v in blr]
    D["ioer"] = list(D["policy_rate"])
    cab = D.get("cab", [])
    days = [d for d, _ in cab if d >= start]
    weeks = [d for i, d in enumerate(days) if i % 5 == 0]   # weekly replay (every 5th session) — daily is 5× slower for the same thresholds
    rows = []
    prev_cb = prev_fi = prev_rt = None
    for d in weeks:
        Dd = trunc(D, d)
        cb = BJ.build_central_bank(cfg, Dd, prev_cb)
        fi = BJ.build_fiscal(cfg, Dd, prev_fi)
        rt = BJ.build_rates(cfg, Dd, prev_rt)
        prev_cb, prev_fi, prev_rt = cb, fi, rt
        od = rt["derived"].get("tona_minus_ioer_bps", {})
        rows.append({"date": d, "cb_score": cb["signals"]["score"] if cb["signals"]["traffic_light"] != "NONE" else None, "cb_label": cb["signals"]["label"], "cb_comp": cb["signals"].get("components"), "fi_comp": fi["signals"].get("components"),
                     "fi_score": fi["signals"]["score"] if fi["signals"]["traffic_light"] != "NONE" else None, "fi_label": fi["signals"]["label"],
                     "reserves": cb["series"]["cab_daily"]["value"], "reserves_level": (cb["derived"].get("excess_to_required_ratio") or {}).get("level"),
                     "net_liq_wow": (cb["derived"].get("cab_20d_change") or {}).get("value"), "govt_account": (cb["series"].get("government_account") or {}).get("value"),
                     "fiscal_7d": (fi["derived"].get("fiscal_flow_daily") or {}).get("value"), "fiscal_z": (fi["derived"].get("fiscal_flow_zscore") or {}).get("value"),
                     "stress_bps": od.get("value"), "stress_level": od.get("level")})
    fx = load_series_csv(os.path.join(fx_dir, "fx_usdjpy.csv"), ["FXERD01"])["FXERD01"]   # yen per USD: + = JPY weaker (already the desk sign)
    stress = clean([(r["date"], r["stress_bps"]) for r in rows if r["stress_bps"] is not None])
    # alternative funding truth (triangulation round 2): JSDA Tokyo repo rate, GC overnight (T+0) − IOER, bps — fixture history from 2025-06 only
    io = D.get("ioer", [])

    def _io(d):
        v = None
        for dd, x in io:
            if dd <= d:
                v = x
            else:
                break
        return v
    gc = [(d, round((v - _io(d)) * 100, 1)) for d, v in D.get("on_t0", []) if v is not None and _io(d) is not None]
    stress_alt = _weekly_asof(clean(gc), [r["date"] for r in rows])
    auctions = {}
    p = os.path.join(fx_dir, "mof_jgb_auctions.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            rs = list(csv.DictReader(f))
        for ten in ("2y", "5y", "10y", "20y", "30y", "40y"):
            auctions["jgb_" + ten] = [{"date": r["date"], "coverage": float(r["bid_to_cover"]), "tail": float("nan"), "amount": float(r["accepted"]) / 10, "term": ten, "yield": float(r["highest_accepted_yield"]) if r["highest_accepted_yield"] else float("nan")} for r in rs if r["tenor"] == ten]
    p = os.path.join(fx_dir, "mof_tbill_auctions.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            rs = list(csv.DictReader(f))
        auctions["tbills"] = [{"date": r["date"], "coverage": float(r["bid_to_cover"]), "tail": float(r["tail_bp"]) if r["tail_bp"] else float("nan"), "amount": float(r["accepted_bn"]), "term": r["maturity"], "yield": float(r["avg_yield"]) if r["avg_yield"] else float("nan")} for r in rs]
    return {"rows": rows, "fx": fx, "fx_label": "USD/JPY 9:00 Tokyo (BoJ FM08 FXERD01) — + = JPY weaker", "stress": stress, "auctions": auctions,
            "stress_label": "TONA − IOER (bps)", "stress_alt": stress_alt, "stress_alt_label": "JSDA Tokyo repo rate GC O/N T+0 − IOER (bps; fixture from 2025-06-02, %d weekly prints)" % len(stress_alt),
            "structural_breaks": [{"date": "2024-03-19", "note": "end of NIRP / YCC: policy rate 0–0.1 %, IOER floor; JGB purchase taper from 2024-07"},
                                  {"date": "2024-07-31", "note": "first hike to 0.25 % (basic loan rate 0.50) — positive-rate floor era (calibration era)"}]}


def _load_wide(path: str, prefix: str, norm) -> Dict[str, Series]:
    out: Dict[str, List] = {}
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        rd = csv.reader(f)
        hdr = next(rd)
        for row in rd:
            d = norm(row[0])
            if not d:
                continue
            for k, v in zip(hdr[1:], row[1:]):
                if v not in ("", None):
                    out.setdefault(prefix + k, []).append((d, float(v)))
    return {k: clean(v) for k, v in out.items()}


def replay_chf(cfg: dict, fx_dir: str, start: str) -> dict:
    """CHF: SNB data portal full history (snbgwdchfsgw weekly sight deposits since 2009, snbgwdmigirow, snbgwdzid tier parameters since 2019-06,
    zirepo SARON since 1999, snbbipo monthly balance sheet since 1996, bamire since 2005, snbmoba, snbfxtr quarterly), gmges.en.xlsx money-market
    operations since 2019-11 (repo CT/CP, SNB Bills with maturities → bills ladder as the register would have shown it), EFV MMDRC auctions since 2012
    and Confederation bond auctions since 2011 (cells JSON captured from the official XLSX), USD/CHF = BoE IADB XUDLSFD (CHF per USD, since 2005).
    Publication lags applied as-of: snbbipo +10d, bamire +45d, gmges +31d, snbfxtr +90d."""
    from . import blocks_chf as BC
    from .providers_chf import _norm_date, SnbOpsProvider, EfvAuctionsProvider as P
    D: Dict[str, Series] = {}
    D.update(_load_wide(os.path.join(fx_dir, "snbgwdchfsgw.csv"), "snbgwdchfsgw:", _norm_date))
    D.update(_load_wide(os.path.join(fx_dir, "snbgwdmigirow.csv"), "snbgwdmigirow:", _norm_date))
    D.update(_load_wide(os.path.join(fx_dir, "snbgwdzid.csv"), "snbgwdzid:", _norm_date))
    D.update(_load_wide(os.path.join(fx_dir, "snbbipo.csv"), "snbbipo:", _norm_date))
    D.update(_load_wide(os.path.join(fx_dir, "bamire.csv"), "bamire:", _norm_date))
    D.update(_load_wide(os.path.join(fx_dir, "snbmoba.csv"), "snbmoba:", _norm_date))
    D.update(_load_wide(os.path.join(fx_dir, "snbfxtr.csv"), "snbfxtr:", _norm_date))
    Z = _load_wide(os.path.join(fx_dir, "zirepo.csv"), "zirepo:", _norm_date)
    D.update(Z)
    # SARON: portal series (since 2019-06) spliced on the repo reference series (since 1999)
    sar = D.get("snbgwdzid:SARON", [])
    first = sar[0][0] if sar else "9999"
    D["snbgwdzid:SARON"] = clean([(d, v) for d, v in Z.get("zirepo:H0", []) if d < first] + sar)
    # operations
    ops = []
    p = os.path.join(fx_dir, "gmges.en.xlsx")
    if os.path.exists(p):
        from .providers_chf import xlsx_sheets
        ops = SnbOpsProvider.parse(next(iter(xlsx_sheets(open(p, "rb").read()).values())))
    OPS = SnbOpsProvider.series(ops)
    D.update(OPS)
    bills = [o for o in ops if o["type"].lower().startswith("snb bills") and o["allocation"]]
    # EFV auctions (all years in the captured workbooks)
    def _cells(fn):
        q = os.path.join(fx_dir, fn)
        if not os.path.exists(q):
            return {}
        m = json.load(open(q))
        return {y: {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v) for k, v in c.items()} for y, c in m.items()}
    mm_recs, bd_recs = [], []
    for y, c in _cells("efv_mmdrc_cells.json").items():
        mm_recs += P._table(c)
    for y, c in _cells("efv_bonds_cells.json").items():
        bd_recs += P._table(c)
    D.update(P.series_mmdrc(mm_recs))
    D.update(P.series_bonds(bd_recs))
    LAG = {"snbbipo:": 10, "bamire:": 45, "ops_": 31, "bills_btc": 31, "bills_yield_28d": 31, "repo_absorb_daily": 31, "snbfxtr:": 90, "snbmoba:": 10}

    def tr(d: str) -> Dict[str, Series]:
        out = trunc(D, d)
        for k in list(out):
            lag = next((v for pre, v in LAG.items() if k.startswith(pre)), 0)
            if lag:
                cut = (date.fromisoformat(d) - timedelta(days=lag)).isoformat()
                out[k] = [(x, v) for x, v in out[k] if x <= cut]
        # bills ladder from the operations file (maturity 'to' + allocation): what the register showed on that date
        d7 = (date.fromisoformat(d) + timedelta(days=7)).isoformat()
        d28 = (date.fromisoformat(d) + timedelta(days=28)).isoformat()
        out["bills_maturing_week"] = [(d, round(sum(o["allocation"] for o in bills if d < o["to"] <= d7), 1))] if bills and bills[0]["date"] <= d else []
        out["bills_maturing_4w"] = [(d, round(sum(o["allocation"] for o in bills if d < o["to"] <= d28), 1))] if bills and bills[0]["date"] <= d else []
        return out

    gi = D.get("snbgwdchfsgw:GI", [])
    weeks = [d for d, _ in gi if d >= start]
    rows = []
    prev_cb = prev_fi = prev_rt = None
    for d in weeks:
        Dd = tr(d)
        cb = BC.build_central_bank(cfg, Dd, prev_cb)
        fi = BC.build_fiscal(cfg, Dd, prev_fi)
        rt = BC.build_rates(cfg, Dd, prev_rt)
        prev_cb, prev_fi, prev_rt = cb, fi, rt
        od = rt["derived"].get("saron_minus_absorption_rate_bps", {})
        rows.append({"date": d, "cb_score": cb["signals"]["score"] if cb["signals"]["traffic_light"] != "NONE" else None, "cb_label": cb["signals"]["label"], "cb_comp": cb["signals"].get("components"), "fi_comp": fi["signals"].get("components"),
                     "fi_score": fi["signals"]["score"] if fi["signals"]["traffic_light"] != "NONE" else None, "fi_label": fi["signals"]["label"],
                     "reserves": cb["series"]["sight_deposits_domestic_weekly"]["value"], "reserves_level": (cb["derived"].get("excess_to_required_ratio") or {}).get("level"),
                     "net_liq_wow": (cb["derived"].get("sight_deposits_wow") or {}).get("value"), "govt_account": (fi["series"].get("amounts_due_to_confederation") or {}).get("value"),
                     "fiscal_7d": (fi["derived"].get("confed_cash_mom") or {}).get("value"), "fiscal_z": (fi["derived"].get("confed_cash_mom") or {}).get("zscore"),
                     "stress_bps": od.get("value"), "stress_level": od.get("level"),
                     "abs_share": (cb["derived"].get("absorption_share") or {}).get("value"), "p13": (cb["derived"].get("sight_deposits_13w_change_pct") or {}).get("value"),
                     "p13_signal": (cb["derived"].get("sight_deposits_13w_change_pct") or {}).get("signal"), "fx_suspect": (cb["derived"].get("fx_intervention_suspect") or {}).get("value")})
    # FX
    fx = []
    p = os.path.join(fx_dir, "fx_usdchf_boe.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    fx.append((datetime.strptime(r["DATE"], "%d %b %Y").date().isoformat(), float(r["XUDLSFD"])))
                except (ValueError, KeyError):
                    continue
    fx = clean(fx)
    stress = clean([(r["date"], r["stress_bps"]) for r in rows if r["stress_bps"] is not None])
    auctions = {}
    mm = [(r["_date"], P._num(next((v for h, v in r.items() if h.startswith("total bids") and "without" not in h), None)), P._num(next((v for h, v in r.items() if h.startswith("amount of issue")), None)),
           P._num(next((v for h, v in r.items() if h.startswith("yield")), None))) for r in mm_recs]
    auctions["mmdrc_3m"] = sorted([{"date": d, "coverage": round(b / a, 3), "tail": float("nan"), "amount": a, "term": "3m", "yield": (y * 100) if y is not None else float("nan")} for d, b, a, y in mm if b and a], key=lambda r: r["date"])
    bd = []
    for r in bd_recs:
        b = P._num(next((v for h, v in r.items() if h.startswith("total bids") and "without" not in h), None))
        a = P._num(next((v for h, v in r.items() if h.startswith("amount of issue")), None))
        y = P._num(next((v for h, v in r.items() if h.startswith("yield")), None))
        own = P._num(next((v for h, v in r.items() if h.startswith("additional own")), None)) or 0.0
        if b and a:
            bd.append({"date": r["_date"], "coverage": round(b / a, 3), "tail": float("nan"), "amount": a, "term": str(r.get("bond", "")), "yield": (y * 100) if y is not None else float("nan"), "own_share": round(own / (a + own), 3) if (a + own) else 0.0})
    auctions["confed_bonds"] = sorted(bd, key=lambda r: r["date"])
    auctions["snb_bills_28d"] = sorted([{"date": o["date"], "coverage": round(o["bids"] / o["allocation"], 3), "tail": float("nan"), "amount": o["allocation"], "term": o["term"], "yield": o["yield"] if o["yield"] is not None else float("nan")}
                                        for o in bills if o["bids"] and 20 <= int(''.join(ch for ch in o["term"] if ch.isdigit()) or 0) <= 35], key=lambda r: r["date"])
    return {"rows": rows, "fx": fx, "fx_label": "USD/CHF (BoE IADB XUDLSFD, CHF per USD) — + = CHF weaker", "stress": stress, "auctions": auctions,
            "structural_breaks": [{"date": "2015-01-15", "note": "EUR/CHF floor abandoned; policy −0.75 %, tiered exemption (20×) — negative-rate era, no absorption"},
                                  {"date": "2022-09-22", "note": "exit from negative rates: policy 0.5 %, tiered remuneration (threshold factor 28 → 25 …), absorption via SNB Bills and repos begins — calibration era"},
                                  {"date": "2025-06-20", "note": "policy back to 0 %: rate above threshold −0.25 %, absorption anchor policy − 5 bp (sub-era)"}]}


def _cells_of(rows: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    """{row: {col: v}} (in-browser XLSX capture) → {ref: v} as providers_chf.xlsx_sheets returns."""
    return {"%s%s" % (c, r): v for r, o in rows.items() for c, v in o.items()}


def replay_nzd(cfg: dict, fx_dir: str, start: str) -> dict:
    """NZD: RBNZ whole-history workbooks captured 2026-09-09 (hd12 Standing Facilities since 1999-03, hd3 OMO sheets — old reverse repos, new weekly OMO,
    LSAP sales, repurchases, BMLS —, hd10 monthly influences since 2008, hr1/hr3 monthly, hb2 daily close and hb1 daily NZD/USD since 2018-01) and
    NZDM tender histories (T-bills since 1993, nominal bonds since 1983), all parsed with the live providers' own parsers from the cells JSON.
    Publication lags as-of: D10 +31d (last day of next month), R1/R3 +14d. FX = 1 / NZD-USD (NZD per USD, + = NZD weaker)."""
    from . import blocks_nzd as BN
    from . import providers_nzd as PN
    R = json.load(open(os.path.join(fx_dir, "rbnz_cells.json")))
    NZ = json.load(open(os.path.join(fx_dir, "nzdm_cells.json")))
    S_ = {k: {s: _cells_of(rows) for s, rows in sh.items()} for k, sh in R.items()}
    S_.update({k: {s: _cells_of(rows) for s, rows in sh.items()} for k, sh in NZ.items()})
    orig = PN.xlsx_sheets
    PN.xlsx_sheets = lambda blob: blob if isinstance(blob, dict) else orig(blob)  # type: ignore
    try:
        class _P(PN.RbnzD12Provider, PN.RbnzD3Provider, PN.RbnzD10Provider):
            def __init__(self, sheets):
                super().__init__()
                self._sheets = sheets
            def _blob(self, path, tag):
                return self._sheets
        D: Dict[str, Series] = {}
        d12, _ = _P(S_["d12"]).fetch_d12("1999-01-01")
        D.update(d12)
        d3 = _P(S_["d3"]).fetch_d3("2015-01-01")
        d10 = _P(S_["d10"]).fetch_d10("1999-01-01")
        D.update(d10)
        for tbl in ("r1", "r3", "b2", "b1"):
            D.update(PN.RbnzTableProvider.parse_data_sheet(S_[tbl]["Data"], tbl.upper(), "1990-01-01"))
        class _N(PN.NzdmProvider):
            def __init__(self, sheets):
                super().__init__()
                self._sheets = sheets
            def _get(self, path, tag, binary=False):
                return self._sheets
        tb = [dict(x, kind="tbill") for x in _N({"Sheet1": S_["tbill"]["Sheet1"]}).history("tbill", "1990-01-01", {"tbill": "x"})]
        bd = [dict(x, kind="bond") for x in _N({"Nominals": S_["bond"]["Nominals"]}).history("bond", "1980-01-01", {"bond": "x"})]
    finally:
        PN.xlsx_sheets = orig  # type: ignore
    sc = D.get("D12:settlement_cash", [])
    bdays = [d for d, _ in sc]
    D.update(PN.RbnzD3Provider.omo_series(d3, bdays))
    for kind, rows_ in (("tbill", tb), ("bond", bd)):
        for k, ser in PN.NzdmProvider.tender_series(rows_).items():
            D["NZDM:%s_%s" % (kind, k)] = ser
    # bonds on issue (current lines; only the coupon/maturity tags depend on it)
    side = {"_tender_rows": tb + bd, "_bonds_on_issue": PN.NzdmProvider(fixtures_dir=os.path.join(ROOT, "fixtures", "nzd")).bonds_on_issue(), "_upcoming_tenders": []}
    LAG = {"D10:": 31, "R1:": 14, "R3:": 14}

    def tr(d: str) -> Dict[str, Series]:
        out = trunc(D, d, lookback_days=1600)
        for k in list(out):
            lag = next((v for pre, v in LAG.items() if k.startswith(pre)), 0)
            if lag:
                cut = (date.fromisoformat(d) - timedelta(days=lag)).isoformat()
                out[k] = [(x, v) for x, v in out[k] if x <= cut]
        out.update(side)  # type: ignore
        out["_tender_rows"] = [r for r in side["_tender_rows"] if r["tender_date"] <= d]  # type: ignore
        return out

    days = [d for d in bdays if d >= start]
    weeks = [d for i, d in enumerate(days) if i % 5 == 0]
    rows = []
    prev_cb = prev_fi = prev_rt = None
    for d in weeks:
        Dd = tr(d)
        cb = BN.build_central_bank(cfg, Dd, prev_cb)
        fi = BN.build_fiscal(cfg, Dd, prev_fi, cb)
        rt = BN.build_rates(cfg, Dd, prev_rt)
        prev_cb, prev_fi, prev_rt = cb, fi, rt
        od = rt["derived"].get("bank_bill_30d_minus_ocr_bps", {})
        rows.append({"date": d, "cb_score": cb["signals"]["score"] if cb["signals"]["traffic_light"] != "NONE" else None, "cb_label": cb["signals"]["label"], "cb_comp": cb["signals"].get("components"), "fi_comp": fi["signals"].get("components"),
                     "fi_score": fi["signals"]["score"] if fi["signals"]["traffic_light"] != "NONE" else None, "fi_label": fi["signals"]["label"],
                     "reserves": cb["series"]["settlement_cash_daily"]["value"], "reserves_level": cb["series"]["settlement_cash_daily"]["level"],
                     "net_liq_wow": (cb["derived"].get("settlement_cash_wow") or {}).get("value"), "govt_account": (fi["series"].get("crown_settlement_account") or {}).get("value"),
                     "fiscal_7d": (fi["derived"].get("govt_cash_influence") or {}).get("value"), "fiscal_z": (fi["derived"].get("govt_cash_influence") or {}).get("zscore"),
                     "stress_bps": od.get("value"), "stress_level": od.get("level"),
                     "wow_level": (cb["derived"].get("settlement_cash_wow") or {}).get("level"), "wow_side": (cb["derived"].get("settlement_cash_wow") or {}).get("side"),
                     "d20": (cb["derived"].get("settlement_cash_20d_change") or {}).get("value"), "omo_share": (cb["derived"].get("omo_reliance_share") or {}).get("value"),
                     "omo_share_level": (cb["derived"].get("omo_reliance_share") or {}).get("level"), "orrf_level": (cb["derived"].get("orrf_used") or {}).get("level"),
                     "gci_level": (fi["derived"].get("govt_cash_influence") or {}).get("level"), "gci_side": (fi["derived"].get("govt_cash_influence") or {}).get("side")})
    nzdusd = D.get("B1:EXR.DS11.D06", [])
    fx = clean([(d, round(1.0 / v, 5)) for d, v in nzdusd if v])
    stress = clean([(r["date"], r["stress_bps"]) for r in rows if r["stress_bps"] is not None])
    # alternative funding truth (triangulation round 2): overnight interbank cash rate − OCR (RBNZ B2 INM.DN.NZK − INM.DP1.N), bps
    ocr = dict(D.get("B2:INM.DP1.N", []))
    ibk = [(d, round((v - ocr[d]) * 100, 1)) for d, v in D.get("B2:INM.DN.NZK", []) if d in ocr and v is not None and ocr[d] is not None]
    stress_alt = _weekly_asof(clean(ibk), [r["date"] for r in rows])
    auctions = {}
    # per tender line (T-bills: three lines per tender; bonds: per line) — coverage = bid/offered, tail = highest accepted − wavg
    def _rows(rs, term_key):
        out = []
        for x in rs:
            if x.get("offered") and x.get("bid"):
                tail = ((x["high_acc"] - x["wavg"]) * 100) if (x.get("high_acc") is not None and x.get("wavg") is not None and (x.get("accepted") or 0) > 0) else float("nan")
                out.append({"date": x["tender_date"], "coverage": round(x["bid"] / x["offered"], 3), "tail": round(tail, 2) if tail == tail else tail, "amount": x.get("accepted") or 0.0,
                            "term": str(x.get(term_key) or ""), "yield": x["wavg"] if x.get("wavg") is not None else float("nan")})
        return sorted(out, key=lambda r: r["date"])
    auctions["tbills"] = _rows(tb, "maturity")
    auctions["nzgb_nominal"] = _rows(bd, "maturity")
    return {"rows": rows, "fx": fx, "fx_label": "NZD per USD (1 / RBNZ B1 NZD/USD daily) — + = NZD weaker", "stress": stress, "auctions": auctions,
            "stress_label": "bank bill 30d − OCR (bps)", "stress_alt": stress_alt, "stress_alt_label": "overnight interbank cash rate − OCR (RBNZ B2 INM.DN.NZK − INM.DP1.N, bps; daily from 2018-01, sampled on the replay dates)",
            "structural_breaks": [{"date": "2020-03-23", "note": "LSAP starts: settlement cash from ~7 bn to > 40 bn; floor system (ODR = OCR)"},
                                  {"date": "2022-07-01", "note": "LSAP unwind: bond sales to NZDM begin (NZ$5 bn/yr), settlement cash declines toward the new steady state — calibration era"},
                                  {"date": "2026-04-02", "note": "new liquidity framework: weekly full-allotment reverse-repo OMO at OCR + 10 bp, no settlement-cash target (sub-era, 23 weeks)"}]}


def replay_usd(cfg: dict, fx_dir: str, start: str) -> dict:
    """USD: FRED keyless CSVs since 2003 (H.4.1 WALCL/WTREGEN/WRESBAL/WLCFLPCL/TREAST/WSHOMCB weekly, RRPONTTLD daily, SOFR since 2018-04, IORB since
    2021-07-29 spliced on IOER 2008-10 → 2021-07, DFF/DGS2/DGS10/DTB3, DTWEXBGS broad dollar); Fiscal Data DTS since 2005-10 (operating cash balance —
    'Federal Reserve Account' close before 2021-10, 'Treasury General Account (TGA)' to 2022-04-17, then the new Closing Balance rows —, daily totals of
    deposits/withdrawals aggregated by the API per side (pre-2022) or the catg-'null' total rows (post-2022, with MTD/FYTD), Public Debt Cash Issues/Redemp.
    rows in both table namings, debt subject to limit); TreasuryDirect auction results (securities/search by auction year). FX truth = 1 / broad dollar
    index (+ = USD weaker). Replay on H.4.1 Wednesdays."""
    from . import blocks_usd as BU
    from .providers_usd import FredProvider, FiscalDataProvider as FD
    D: Dict[str, Series] = {}
    for fn in sorted(os.listdir(fx_dir)):
        if fn.startswith("fred_") and fn.endswith(".csv"):
            sid = fn[5:-4]
            D[sid] = FredProvider._scale(sid, FredProvider.parse_csv(open(os.path.join(fx_dir, fn), encoding="utf-8").read(), sid))
    io = D.get("IORB", [])
    first = io[0][0] if io else "9999"
    D["IORB"] = clean([(d, v) for d, v in D.get("IOER", []) if d < first] + io)
    # ── DTS ──
    def rd(fn):
        with open(os.path.join(fx_dir, fn), encoding="utf-8") as f:
            return list(csv.DictReader(f))
    f = FD._f
    tga_c, tga_o, td, tw = {}, {}, {}, {}
    for r in rd("dts_cash_hist.csv"):
        d, at = r["record_date"], r["account_type"]
        if at in ("Federal Reserve Account", "Treasury General Account (TGA)"):
            if f(r["close"]) is not None:
                tga_c[d] = f(r["close"])
            if f(r["open"]) is not None:
                tga_o[d] = f(r["open"])
        elif "Closing Balance" in at and f(r["open"]) is not None:
            tga_c[d] = f(r["open"])
        elif "Opening Balance" in at and f(r["open"]) is not None:
            tga_o[d] = f(r["open"])
        elif "Total TGA Deposits" in at and f(r["open"]) is not None:
            td[d] = f(r["open"])
        elif "Total TGA Withdrawals" in at and f(r["open"]) is not None:
            tw[d] = f(r["open"])
    for r in rd("dts_tot_pre2022.csv"):
        (td if r["type"] == "D" else tw).setdefault(r["record_date"], f(r["today"]))
    D["DTS:tga_close"], D["DTS:tga_open"], D["DTS:total_deposits"], D["DTS:total_withdrawals"] = clean(sorted(tga_c.items())), clean(sorted(tga_o.items())), clean(sorted(td.items())), clean(sorted(tw.items()))
    tot = {"D": {}, "W": {}}
    for r in rd("dts_tot_post2022.csv"):
        for suf, col in (("", "today"), ("|mtd", "mtd"), ("|fytd", "fytd")):
            tot[r["type"]].setdefault(suf, {})[r["record_date"]] = f(r[col])
    for suf in ("", "|mtd", "|fytd"):
        D["DTS:tot_dep_tx" + suf] = clean(sorted((tot["D"].get(suf) or {}).items()))
        D["DTS:tot_wd_tx" + suf] = clean(sorted((tot["W"].get(suf) or {}).items()))
    dbt = {"I": {}, "R": {}}
    for r in rd("dts_debt_tx.csv"):
        for suf, col in (("", "today"), ("|mtd", "mtd"), ("|fytd", "fytd")):
            v = f(r[col])
            if v is not None:
                m = dbt[r["kind"]].setdefault(suf, {})
                m[r["record_date"]] = m.get(r["record_date"], 0.0) + v
    for suf in ("", "|mtd", "|fytd"):
        D["DTS:debt_issues" + suf] = clean(sorted(dbt["I"].get(suf, {}).items()))
        D["DTS:debt_redemptions" + suf] = clean(sorted(dbt["R"].get(suf, {}).items()))
    pub, intra = {}, {}
    for r in rd("dts_debt_hist.csv"):
        (pub if r["catg"] == "D" else intra)[r["record_date"]] = f(r["close"])
    D["DTS:debt_public"] = clean(sorted(pub.items()))
    D["DTS:debt_intragov"] = clean(sorted(intra.items()))
    D["DTS:debt_total"] = clean(sorted((d, pub[d] + intra[d]) for d in pub if d in intra))
    wa = D.get("WALCL", [])
    weeks = [d for d, _ in wa if d >= start]
    rows = []
    prev_cb = prev_fi = prev_rt = None
    for d in weeks:
        # H.4.1 is published Thursday for the Wednesday level; DTS T-1: as-of = the Wednesday date with everything dated ≤ d
        Dd = trunc(D, d, lookback_days=1500)
        cb = BU.build_central_bank(cfg, Dd, prev_cb)
        fi = BU.build_fiscal(cfg, Dd, prev_fi)
        rt = BU.build_rates(cfg, Dd, prev_rt, cb)
        prev_cb, prev_fi, prev_rt = cb, fi, rt
        od = rt["derived"].get("sofr_minus_iorb_bps", {})
        fimp = fi["derived"].get("fiscal_impulse") or {}
        rows.append({"date": d, "cb_score": cb["signals"]["score"] if cb["signals"]["traffic_light"] != "NONE" else None, "cb_label": cb["signals"]["label"], "cb_comp": cb["signals"].get("components"), "fi_comp": fi["signals"].get("components"),
                     "fi_score": fi["signals"]["score"] if fi["signals"]["traffic_light"] != "NONE" else None, "fi_label": fi["signals"]["label"],
                     "reserves": cb["series"]["reserves"]["value"], "reserves_level": (cb["derived"].get("reserves_status") or {}).get("badge"),
                     "net_liq_wow": (cb["derived"].get("net_liquidity_wow_pct") or {}).get("value"), "govt_account": cb["series"]["tga"]["value"],
                     "fiscal_7d": (fi["derived"].get("net_treasury_flow_7d") or {}).get("value"), "fiscal_z": (fi["derived"].get("net_treasury_flow") or {}).get("zscore"),
                     "stress_bps": od.get("value"), "stress_level": od.get("level"),
                     "nl_signal": (cb["derived"].get("net_liquidity_wow_pct") or {}).get("signal"), "tga_badge": (cb["derived"].get("tga_status") or {}).get("badge"),
                     "rrp_badge": (cb["derived"].get("rrp_status") or {}).get("badge"), "phase": (cb["derived"].get("balance_sheet_phase") or {}).get("phase"),
                     "structural": fimp.get("structural"), "surprise": fimp.get("surprise")})
    bd = D.get("DTWEXBGS", [])
    fx = clean([(d, round(100.0 / v, 5)) for d, v in bd if v])
    stress = clean([(r["date"], r["stress_bps"]) for r in rows if r["stress_bps"] is not None])
    auctions: Dict[str, list] = {}
    p = os.path.join(fx_dir, "treasurydirect_auctions.csv")
    if os.path.exists(p):
        for r in rd("treasurydirect_auctions.csv"):
            if r.get("cashManagementBillCMB") == "Yes" or not r.get("bidToCoverRatio"):
                continue
            kind = "bills" if r["securityType"] == "Bill" else "tips" if r.get("tips") == "Yes" else "frn" if r.get("floatingRate") == "Yes" else "notes_bonds"
            hy = f(r["highYield"]) if r.get("highYield") else f(r["highDiscountRate"]) if r.get("highDiscountRate") else None
            my = f(r["averageMedianYield"]) if r.get("averageMedianYield") else f(r["averageMedianDiscountRate"]) if r.get("averageMedianDiscountRate") else None
            tail = round((hy - my) * 100, 2) if (hy is not None and my is not None) else float("nan")
            auctions.setdefault(kind, []).append({"date": r["auctionDate"][:10], "coverage": f(r["bidToCoverRatio"]), "tail": tail, "amount": (f(r["totalAccepted"]) or 0) / 1e9, "term": r["securityTerm"],
                                                  "yield": hy if hy is not None else float("nan")})
        for k in auctions:
            auctions[k].sort(key=lambda r: r["date"])
    return {"rows": rows, "fx": fx, "fx_label": "1 / broad dollar index (FRED DTWEXBGS) — + = USD weaker", "stress": stress, "auctions": auctions,
            "structural_breaks": [{"date": "2020-03-15", "note": "COVID: emergency cuts, unlimited QE, reserves 1.7 → 4 tn; ON RRP era 2021–2023"},
                                  {"date": "2022-06-01", "note": "QT starts (caps 47.5 → 95 bn/month); TGA rebuilds; RRP drains from 2.3 tn to ~0 by 2025 — ample-reserves-under-QT era (calibration era)"},
                                  {"date": "2025-04-01", "note": "QT slowed to 5 bn/month Treasuries (Mar-2025 FOMC); RRP ≈ 0; reserves 2.9–3.4 tn — sub-era"}]}


def replay_eur(cfg: dict, fx_dir: str, start: str) -> dict:
    """EUR: ECB Data Portal full history captured 2026-09-09 (ILM daily current accounts / deposit facility / MLF since 2005, EXLIQ / MRR / NLIQ / TOMO only since
    2024-09-27 → before that EXLIQ = CA + DF − MRR (first published requirement, 162.9 bn, held constant: ±40 bn on a 1.5–4.7 tn stock) and TOMO = weekly
    MRO + LTRO carried onto the daily grid; WFS weekly items since 2005/2009; central-government deposits: the weekly L050100 breakdown exists only since
    2025-W45, so the replay uses L050000 (liabilities to euro-area residents in euro, ≈ 90 % government) throughout; EXR EUR/USD since 1999; key rates since
    1999; €STR since 2019-10; APP/PEPP files; Finanzagentur Emissionshistorie 1999–2026 (2,319 auction lines) with the live parser).
    Publication lags as-of: WFS +4 d, TGB/BSI/MIR +60 d, IRS +45 d, APP/PEPP +32 d, GFS via the block's own 90-day rule. Replay on WFS Fridays."""
    from . import blocks_eur as BE
    from .providers_eur import EcbProvider, AppPeppProvider, FinanzagenturProvider
    ids = sorted(set(sc["id"] for b in ("central_bank", "fiscal", "banking", "rates") for sc in cfg["blocks"][b]["series"].values() if sc.get("id") and "." in sc["id"]))
    ecb = EcbProvider(fixtures_dir=fx_dir)
    D: Dict[str, Series] = ecb.fetch(ids, "1999-01-01", [])
    L = D.get("ILM.W.U2.C.L050000.U2.EUR", [])
    D["ILM.W.U2.C.L050100.U2.EUR"] = list(L)   # see docstring: consistent proxy across the whole replay
    ca, df = D.get("ILM.D.U2.C.L020100.U2.EUR", []), D.get("ILM.D.U2.C.L020200.U2.EUR", [])
    ex, mrr, tomo = D.get("ILM.D.U2.C.EXLIQ.U2.EUR", []), D.get("ILM.D.U2.C.MRR.U2.EUR", []), D.get("ILM.D.U2.C.TOMO.U2.EUR", [])
    first_ex = ex[0][0] if ex else "9999"
    mrr0 = mrr[0][1] if mrr else 162940.0
    dfm = dict(df)
    proxy = [(d, round(v + dfm[d] - mrr0, 1)) for d, v in ca if d in dfm and d < first_ex]
    D["ILM.D.U2.C.EXLIQ.U2.EUR"] = clean(proxy + ex)
    D["ILM.D.U2.C.MRR.U2.EUR"] = clean([(d, mrr0) for d, _ in proxy] + mrr)
    wk = S_add(D.get("ILM.W.U2.C.A050100.U2.EUR", []), D.get("ILM.W.U2.C.A050200.U2.EUR", []))
    wkd = [x for x, _ in wk]
    import bisect as _b
    tproxy = []
    for d, _ in ca:
        if d >= first_ex:
            break
        i = _b.bisect_right(wkd, d) - 1
        if i >= 0:
            tproxy.append((d, wk[i][1]))
    D["ILM.D.U2.C.TOMO.U2.EUR"] = clean(tproxy + tomo)
    D.update(AppPeppProvider(fixtures_dir=fx_dir).fetch())

    class _FA(FinanzagenturProvider):
        def _bytes(self):
            return open(os.path.join(fx_dir, "emissionshistorie_en.xlsx"), "rb").read()
    fa = _FA()
    D.update(fa.fetch())
    de_rows = fa.rows
    LAG = {"ILM.W": 4, "TGB.": 60, "BSI.": 60, "MIR.": 60, "IRS.": 45, "APP:": 32, "PEPP:": 32, "BLS.": 30, "ICP.": 30, "FM.M": 30}

    def tr(d: str) -> Dict[str, Series]:
        out = trunc(D, d, lookback_days=1500)
        for k in list(out):
            lag = next((v for pre, v in LAG.items() if k.startswith(pre)), 0)
            if lag:
                cut = (date.fromisoformat(d) - timedelta(days=lag)).isoformat()
                out[k] = [(x, v) for x, v in out[k] if x <= cut]
        return out

    weeks = [d for d, _ in D.get("ILM.W.U2.C.A070100.U2.EUR", []) if d >= start]
    rows = []
    prev_cb = prev_fi = prev_rt = None
    for d in weeks:
        Dd = tr(d)
        cb = BE.build_central_bank(cfg, Dd, prev_cb)
        fi = BE.build_fiscal(cfg, Dd, prev_fi, aux={"de_rows": [r for r in de_rows if r["date"] <= d][-200:]})
        rt = BE.build_rates(cfg, Dd, prev_rt, cb)
        prev_cb, prev_fi, prev_rt = cb, fi, rt
        od = rt["derived"].get("estr_minus_dfr_bps", {})
        rows.append({"date": d, "cb_score": cb["signals"]["score"] if cb["signals"]["traffic_light"] != "NONE" else None, "cb_label": cb["signals"]["label"], "cb_comp": cb["signals"].get("components"), "fi_comp": fi["signals"].get("components"),
                     "fi_score": fi["signals"]["score"] if fi["signals"]["traffic_light"] != "NONE" else None, "fi_label": fi["signals"]["label"],
                     "reserves": cb["series"]["excess_liquidity"]["value"], "reserves_level": cb["series"]["excess_liquidity"]["level"],
                     "net_liq_wow": (cb["derived"].get("excess_liquidity_wow") or {}).get("value"), "govt_account": fi["series"]["govt_deposits"]["value"],
                     "fiscal_7d": (fi["derived"].get("fiscal_impulse_4w") or {}).get("value"), "fiscal_z": (fi["derived"].get("fiscal_impulse_4w") or {}).get("percentile"),
                     "stress_bps": od.get("value"), "stress_level": od.get("level"),
                     "phase": (cb["derived"].get("balance_sheet_phase") or {}).get("phase"), "t20": (cb["derived"].get("excess_liquidity_trend_20s") or {}).get("value"),
                     "tomo_lvl": cb["series"]["omo_takeup"]["level"], "fi_rule": (fi["derived"].get("fiscal_regime") or {}).get("regime"),
                     "fi_comp_regime": (fi["derived"].get("fiscal_regime") or {}).get("components"), "deficit": (fi["derived"].get("fiscal_stance_structural") or {}).get("value")})
    eurusd = D.get("EXR.D.USD.EUR.SP00.A", [])
    fx = clean([(d, round(1.0 / v, 5)) for d, v in eurusd if v])
    stress = clean([(r["date"], r["stress_bps"]) for r in rows if r["stress_bps"] is not None])
    auctions: Dict[str, list] = {}
    for r in de_rows:
        if not r.get("bid_to_cover") or r.get("process") == "Syn":
            continue
        kind = "bubills" if r["bond"] == "Bubill" else "ilb" if r["bond"] == "ILB" else "bunds" if r["bond"] in ("Bund", "Bobl", "Schatz", "Green") else None
        if not kind:
            continue
        auctions.setdefault(kind, []).append({"date": r["date"], "coverage": r["bid_to_cover"], "tail": float("nan"), "amount": (r.get("allotted") or 0) / 1e3, "term": r.get("segment") or "",
                                              "yield": r["avg_yield"] if r.get("avg_yield") is not None else float("nan"), "retention": (r.get("retention") or 0) / r["volume"] if r.get("volume") else None})
    for k in auctions:
        auctions[k].sort(key=lambda x: x["date"])
    return {"rows": rows, "fx": fx, "fx_label": "EUR per USD (1 / ECB EXR USD/EUR reference) — + = EUR weaker", "stress": stress, "auctions": auctions,
            "structural_breaks": [{"date": "2015-03-09", "note": "APP starts (PSPP): excess liquidity from 0.1 to 4.7 tn by 2022; DFR −0.20 → −0.50"},
                                  {"date": "2022-09-14", "note": "DFR positive (0.75 %) after the July exit from negative rates; TLTRO repayments and APP/PEPP run-off → excess liquidity falls from 4.7 to 2.2 tn — floor-under-QT era (calibration era)"},
                                  {"date": "2025-06-11", "note": "DFR 2.00 after the cutting cycle; first hike 2026-06-17 to 2.25 (sub-era)"}]}


def _weekly_asof(series: Series, dates: List[str]) -> Series:
    """Sample a daily series on the replay dates (last print at or before each date) — the shape analyse_v03 expects for a truth."""
    import bisect
    sd = [d for d, _ in series]
    out = []
    for d in dates:
        i = bisect.bisect_right(sd, d) - 1
        if i >= 0:
            out.append((d, series[i][1]))
    return out


def S_add(a: Series, b: Series) -> Series:
    m = dict(b)
    return [(d, v + m[d]) for d, v in a if d in m]


REPLAY = {"cad": replay_cad, "gbp": replay_gbp, "aud": replay_aud, "jpy": replay_jpy, "chf": replay_chf, "nzd": replay_nzd, "usd": replay_usd, "eur": replay_eur}


# ───────────────────────────── analysis ─────────────────────────────
def analyse(ccy: str, cfg: dict, R: dict, split: str, out_dir: str) -> dict:
    rows = R["rows"]
    dates = [r["date"] for r in rows]
    cb = [r["cb_score"] for r in rows]
    fi = [r["fi_score"] for r in rows]
    fr = fwd_returns(R["fx"], dates)
    # secondary truth: forward change of the stress spread (20 sessions)
    st = R["stress"]
    sd_ = [x for x, _ in st]
    import bisect
    fstress = []
    for d in dates:
        i = bisect.bisect_right(sd_, d)
        fstress.append((st[i + 20][1] - st[i][1]) if i + 20 < len(st) else None)
    sign = +1  # injection → currency weaker → quote (CCY per USD) rises
    res = {"currency": ccy.upper(), "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z", "weeks": len(dates), "first": dates[0], "last": dates[-1], "split": split,
           "truth": R["fx_label"], "structural_breaks": R.get("structural_breaks", []), "blocks": {}, "horizons": {}}
    for h in HORIZONS:
        res["horizons"][h] = {"cb": dict(zip(("rho", "p", "n"), spearman(cb, fr[h]))), "fi": dict(zip(("rho", "p", "n"), spearman(fi, fr[h])))}
    # main horizon for thresholds = the horizon with the strongest full-sample |rho| that also holds out of sample; default 20
    grid = np.round(np.arange(-1.5, 1.55, 0.1), 2)
    for name, sc in (("central_bank", cb), ("fiscal", fi)):
        blk = {"n": sum(1 for x in sc if x is not None), "walk_forward": {h: walk_forward_corr(sc, fr[h], dates) for h in HORIZONS}, "thresholds": {}}
        for h in HORIZONS:
            inj = threshold_search(sc, fr[h], dates, split, "ge", sign, grid)
            drn = threshold_search(sc, fr[h], dates, split, "le", -sign, grid[::-1])
            blk["thresholds"][h] = {"injection": inj["best"], "drain": drn["best"], "grid_injection": inj["grid"], "grid_drain": drn["grid"]}
        blk["stress_secondary"] = dict(zip(("rho", "p", "n"), spearman(sc, fstress)))
        res["blocks"][name] = blk
    res["dual"] = {h: ols_weights(cb, fi, fr[h], dates, split, sign) for h in HORIZONS}
    # floor-era subsample (after the last structural break)
    brk = max((b["date"] for b in R.get("structural_breaks", [])), default=None)
    if brk:
        idx = [i for i, d in enumerate(dates) if d >= brk]
        sub = {"since": brk, "weeks": len(idx), "horizons": {}}
        for h in HORIZONS:
            sub["horizons"][h] = {"cb": dict(zip(("rho", "p", "n"), spearman([cb[i] for i in idx], [fr[h][i] for i in idx]))),
                                  "fi": dict(zip(("rho", "p", "n"), spearman([fi[i] for i in idx], [fr[h][i] for i in idx])))}
        res["post_break"] = sub
    # auctions
    res["auctions"] = analyse_auctions(R.get("auctions", {}), R["fx"], split)
    analyse_ab(res, R, brk)
    # persist scores
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "scores.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "cb_score", "cb_label", "fi_score", "fi_label", "reserves", "reserves_level", "net_liq_wow", "govt_account", "fiscal_7d", "fiscal_z", "stress_bps", "stress_level"] + ["fwd_%d" % h for h in HORIZONS])
        for i, r in enumerate(rows):
            w.writerow([r[k] for k in ("date", "cb_score", "cb_label", "fi_score", "fi_label", "reserves", "reserves_level", "net_liq_wow", "govt_account", "fiscal_7d", "fiscal_z", "stress_bps", "stress_level")] + [None if fr[h][i] is None else round(fr[h][i], 4) for h in HORIZONS])
    json.dump(res, open(os.path.join(out_dir, "calibration.json"), "w"), indent=1, default=str)
    return res


def analyse_auctions(auc: dict, fx: Series, split: str) -> dict:
    out = {}
    for kind, rows in auc.items():
        if not rows:
            continue
        cov = np.array([r["coverage"] for r in rows]); tail = np.array([r["tail"] for r in rows if not math.isnan(r["tail"])])
        d = [r["date"] for r in rows]
        fr = fwd_returns(fx, d, (5, 20))
        pct = lambda a, p: round(float(np.nanpercentile(a, p)), 3)
        o = {"n": len(rows), "first": d[0], "last": d[-1],
             "coverage": {"p5": pct(cov, 5), "p10": pct(cov, 10), "p25": pct(cov, 25), "median": pct(cov, 50), "p75": pct(cov, 75), "p90": pct(cov, 90),
                          "recent_3y": {"n": sum(1 for x in d if x >= "2023-09-01"), "p10": pct(np.array([r["coverage"] for r in rows if r["date"] >= "2023-09-01"]) if any(x >= "2023-09-01" for x in d) else cov, 10),
                                        "median": pct(np.array([r["coverage"] for r in rows if r["date"] >= "2023-09-01"]) if any(x >= "2023-09-01" for x in d) else cov, 50)}},
             "tail_bps": {"p50": pct(tail, 50), "p75": pct(tail, 75), "p90": pct(tail, 90), "p95": pct(tail, 95)} if len(tail) else None}
        # validation: does a weak auction (coverage <= p10) precede a different forward FX path? (weak demand for the currency's paper → currency weaker)
        for h in (5, 20):
            o["weak_vs_rest_fwd%d" % h] = cond_test(list(cov), fr[h], o["coverage"]["p10"], "le")
            o["strong_vs_rest_fwd%d" % h] = cond_test(list(cov), fr[h], o["coverage"]["p90"], "ge")
        r, p, n = spearman(list(cov), fr[20])
        o["coverage_vs_fwd20"] = {"rho": r, "p": p, "n": n}
        out[kind] = o
    return out


# ───────────────────────────── final desk cuts (single source of truth for the config patches) ─────────────────────────────
# Triangulation 2026-09-09 (CodeWord): the automatic p80/p20 proposal in calibration.json diverged from the cuts argued in
# CALIBRACION_<CCY>.md (natural gaps of discrete scores, funding-validated cuts). The desk cuts now live HERE, are written to
# calibration.json as ab.final_cuts (with the rule that produced each one) and the automatic proposal is kept as ab.A_frequency.*.proposal_auto.
FINAL_CUTS: Dict[str, dict] = {
    "cad": {"central_bank": {"injection_enter": 0.90, "injection_exit": 0.09, "drain_enter": -1.00, "drain_exit": -0.71, "rule": "p80/p20 of the floor era (337 wk), exit p67/p33"},
            "fiscal": {"injection_enter": 0.62, "injection_exit": 0.30, "drain_enter": -0.59, "drain_exit": -0.20, "rule": "p80/p20 of the floor era, exit p67/p33"}},
    "gbp": {"central_bank": {"injection_enter": 1.17, "injection_exit": 0.83, "drain_enter": -0.50, "drain_exit": -0.17, "rule": "natural gaps of the 7-value discrete score (INJ 15 %, DRAIN 10 % of the QT era)"},
            "fiscal": {"injection_enter": 1.0, "injection_exit": 1.0, "drain_enter": -1.0, "drain_exit": -1.0, "rule": "ternary band by design (±1); funding-validated at 12 weeks"}},
    "aud": {"central_bank": {"injection_enter": 1.33, "injection_exit": 0.67, "drain_enter": 0.0, "drain_exit": 0.67, "rule": "natural gaps of the 5-value discrete score (INJ 24 %, DRAIN 26 %); era 74 wk — provisional until 150"},
            "fiscal": {"injection_enter": 0.57, "injection_exit": 0.46, "drain_enter": -1.02, "drain_exit": -0.43, "rule": "p80/p20 of the ample-reserves era, exit p67/p33"}},
    "jpy": {"central_bank": {"injection_enter": 1.0, "injection_exit": 0.5, "drain_enter": 0.0, "drain_exit": 0.5, "rule": "only two values leave the modal +0.5 (INJ 4 %, DRAIN 15 %); block to be redesigned in v0.3"},
            "fiscal": {"injection_enter": 0.30, "injection_exit": 0.17, "drain_enter": -0.33, "drain_exit": -0.12, "rule": "p80/p20 of the positive-rate era, exit p67/p33"}},
    "chf": {"central_bank": {"injection_enter": 1.0, "injection_exit": 0.5, "drain_enter": -1.0, "drain_exit": -0.5, "rule": "13-week ternary must fire (±1); absorption-share penalty alone is not a regime"},
            "fiscal": {"injection_enter": 0.5, "injection_exit": 0.5, "drain_enter": -0.5, "drain_exit": -0.5, "rule": "ternary band by design (±0.5); funding-validated at 12 weeks"}},
    "nzd": {"central_bank": {"injection_enter": 0.75, "injection_exit": 0.25, "drain_enter": -0.5, "drain_exit": -0.25, "rule": "natural gaps of the discrete score (INJ 20 %, DRAIN 35 % of the LSAP-unwind era)"},
            "fiscal": {"injection_enter": 0.5, "injection_exit": 0.5, "drain_enter": -0.5, "drain_exit": -0.5, "rule": "ternary band by design (±0.5)"}},
    "usd": {"central_bank": {"injection_enter": 0.30, "injection_exit": 0.0, "drain_enter": -0.60, "drain_exit": -0.30, "rule": "p90/p20 of the QT era (INJ 10 %, DRAIN 20 %); level anchors kept"},
            "fiscal": {"injection_enter": 1.28, "injection_exit": 1.15, "drain_enter": -0.5, "drain_exit": -0.5, "rule": "label INJECTION by construction; pace band p80 (strong) / p20 +0.54 (weak); absolute DRAIN ≤ −0.5"}},
    "eur": {"central_bank": {"injection_enter": 0.25, "injection_exit": -0.08, "drain_enter": -0.60, "drain_exit": -0.43, "rule": "p90/p20 of the floor-under-QT era; DRAIN ≤ −0.6 survives the funding test"},
            "fiscal": {"injection_enter": 0.70, "injection_exit": 0.56, "drain_enter": -0.04, "drain_exit": 0.17, "rule": "p80/p20 of the era; DRAIN impossible until the structural deficit weighs 0.25 (v0.3)"}},
}
PERCENTILE_CONVENTION = "numpy.percentile default = linear interpolation between order statistics (on a discrete score the p80 can fall between two attainable values; the nearest attainable value is reported alongside)"


def _nearest_attainable(x: np.ndarray, v: float) -> float:
    vals = np.unique(x)
    return float(vals[np.argmin(np.abs(vals - v))])


def block_bootstrap_p(x: List[Optional[float]], y: List[Optional[float]], block: int = 8, n_boot: int = 2000, seed: int = 7) -> Optional[float]:
    """Two-sided p-value of the Spearman ρ under a moving-block bootstrap of the weekly pairs (block = 8 weeks ≈ the 4/12-week horizons
    and the hysteresis memory). Triangulation 2026-09-09 (Perplexity): weekly block scores are autocorrelated, so n weeks are not n draws."""
    a, b = _clean_pairs(x, y)
    n = len(a)
    if n < 30:
        return None
    r0 = stats.spearmanr(a, b).correlation
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    cnt = 0
    for _ in range(n_boot):
        starts = rng.integers(0, n - block + 1, size=nb)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        # circular-shift the y blocks independently of x blocks: destroys the x–y link but keeps the within-block dependence
        starts_y = rng.integers(0, n - block + 1, size=nb)
        idy = np.concatenate([np.arange(s, s + block) for s in starts_y])[:n]
        r = stats.spearmanr(a[idx], b[idy]).correlation
        if abs(r) >= abs(r0):
            cnt += 1
    return round((cnt + 1) / (n_boot + 1), 4)


# ───────────────────────────── A + B: frequency of the operating era + funding truth ─────────────────────────────
def analyse_ab(res: dict, R: dict, era_start: Optional[str]) -> dict:
    """A: thresholds = percentiles of the block score within the operating era (p20 / p80 with p33 / p67 hysteresis), stability by year.
    B: funding truth = forward change of the stress spread (4 and 12 weeks): rank correlation + threshold search (drain → spread widens?)."""
    rows = R["rows"]
    dates = [r["date"] for r in rows]
    era = era_start or dates[0]
    idx = [i for i, d in enumerate(dates) if d >= era]
    st = R["stress"]
    sd_ = [x for x, _ in st]
    import bisect
    def fstress(h_weeks: int) -> List[Optional[float]]:
        out = []
        for d in dates:
            i = bisect.bisect_right(sd_, d) - 1   # last stress print at or before d
            j = i + h_weeks
            out.append((st[j][1] - st[i][1]) if (i >= 0 and j < len(st)) else None)
        return out
    fs = {4: fstress(4), 12: fstress(12)}
    ab = {"era_start": era, "weeks": len(idx), "percentile_convention": PERCENTILE_CONVENTION, "final_cuts": FINAL_CUTS.get(res["currency"].lower()), "A_frequency": {}, "B_funding": {}}
    grid = np.round(np.arange(-1.5, 1.55, 0.1), 2)
    for name, key in (("central_bank", "cb_score"), ("fiscal", "fi_score")):
        sc = [rows[i][key] for i in idx]
        x = np.array([v for v in sc if v is not None], dtype=float)
        if len(x) < 30:
            ab["A_frequency"][name] = {"status": "insufficient"}
            continue
        pct = lambda p: round(float(np.percentile(x, p)), 2)
        yrs = {}
        for y in sorted(set(dates[i][:4] for i in idx)):
            xy = np.array([rows[i][key] for i in idx if dates[i][:4] == y and rows[i][key] is not None], dtype=float)
            if len(xy) >= 20:
                yrs[y] = {"n": len(xy), "p20": round(float(np.percentile(xy, 20)), 2), "p50": round(float(np.percentile(xy, 50)), 2), "p80": round(float(np.percentile(xy, 80)), 2),
                          "share_drain_p20": round(float(np.mean(xy <= pct(20))), 2), "share_inj_p80": round(float(np.mean(xy >= pct(80))), 2)}
        ab["A_frequency"][name] = {"n": len(x), "p10": pct(10), "p20": pct(20), "p33": pct(33), "p50": pct(50), "p67": pct(67), "p80": pct(80), "p90": pct(90),
                                   "attainable_values": [float(v) for v in np.unique(x)][:20], "p80_nearest_attainable": _nearest_attainable(x, pct(80)), "p20_nearest_attainable": _nearest_attainable(x, pct(20)),
                                   "share_drain_at_minus_0_5": round(float(np.mean(x <= -0.5)), 2), "share_inj_at_plus_0_5": round(float(np.mean(x >= 0.5)), 2),
                                   "proposal_auto": {"injection_enter": pct(80), "injection_exit": pct(67), "drain_enter": pct(20), "drain_exit": pct(33), "rule": "automatic p80/p20, exit p67/p33 — NOT the desk cut"},
                                   "by_year": yrs}
        fc = (FINAL_CUTS.get(res["currency"].lower()) or {}).get(name)
        if fc:
            ab["A_frequency"][name]["final_cut"] = dict(fc, share_injection=round(float(np.mean(x >= fc["injection_enter"])), 2), share_drain=round(float(np.mean(x <= fc["drain_enter"])), 2))
        # B: stress truth on the era; hypothesis: DRAIN (low score) → spread widens (positive Δ), INJECTION → compresses → expect NEGATIVE correlation
        b = {}
        for h in (4, 12):
            y = [fs[h][i] for i in idx]
            r, p, n = spearman(sc, y)
            split = dates[idx[len(idx) * 2 // 3]] if len(idx) > 90 else dates[idx[-1]]
            inj = threshold_search(sc, y, [dates[i] for i in idx], split, "ge", -1, grid, min_cov=0.10)      # injection → spread falls
            drn = threshold_search(sc, y, [dates[i] for i in idx], split, "le", +1, grid[::-1], min_cov=0.10)  # drain → spread rises
            b[h] = {"rho": None if r is None else round(r, 3), "p": None if p is None else round(p, 4), "n": n, "split": split,
                    "p_block_bootstrap": block_bootstrap_p(sc, y), "grid_tests": 2 * len(grid),
                    "injection": inj["best"], "drain": drn["best"]}
        ab["B_funding"][name] = b
    res["ab"] = ab
    return ab


# ───────────────────────────── report ─────────────────────────────
def _f(x, nd=3):
    return "—" if x is None else ("%%.%df" % nd) % x


def report(res: dict, out_dir: str) -> str:
    L = []
    L.append("# %s — calibración empírica del régimen dual (BC / Tesoro / general)\n" % res["currency"])
    L.append("Generado %s · %d semanas (%s → %s) · corte entrenamiento/prueba %s · verdad: %s\n" % (res["generated_at"], res["weeks"], res["first"], res["last"], res["split"], res["truth"]))
    L.append("Hipótesis de la mesa (MMT/Mosler): INYECCIÓN → la divisa se debilita después (retorno forward positivo del cruce divisa-por-USD); DRENAJE → se fortalece. Un umbral sólo se propone si separa los retornos forward con |t| ≥ 2 en entrenamiento, conserva el signo en la prueba y cubre ≥ 10 % de las semanas.\n")
    for b in res.get("structural_breaks", []):
        L.append("Ruptura estructural: %s — %s\n" % (b["date"], b["note"]))
    L.append("\n## 1. ¿Explican los bloques el tipo de cambio? (Spearman, muestra completa)\n")
    L.append("| horizonte | BC ρ | p | n | Tesoro ρ | p | n |\n|---|---|---|---|---|---|---|")
    for h, v in res["horizons"].items():
        L.append("| %s sesiones | %s | %s | %s | %s | %s | %s |" % (h, _f(v["cb"]["rho"]), _f(v["cb"]["p"]), v["cb"]["n"], _f(v["fi"]["rho"]), _f(v["fi"]["p"]), v["fi"]["n"]))
    if res.get("post_break"):
        pb = res["post_break"]
        L.append("\nSubmuestra desde la ruptura (%s, %d semanas):\n" % (pb["since"], pb["weeks"]))
        L.append("| horizonte | BC ρ | p | n | Tesoro ρ | p | n |\n|---|---|---|---|---|---|---|")
        for h, v in pb["horizons"].items():
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (h, _f(v["cb"]["rho"]), _f(v["cb"]["p"]), v["cb"]["n"], _f(v["fi"]["rho"]), _f(v["fi"]["p"]), v["fi"]["n"]))
    for name, blk in res["blocks"].items():
        L.append("\n## 2. Bloque %s — walk-forward (bloques de 2 años, fuera de muestra cada uno)\n" % name)
        for h in HORIZONS:
            L.append("- %d sesiones: " % h + " · ".join("%s ρ=%s (n=%s)" % (w["years"], _f(w["rho"], 2), w["n"]) for w in blk["walk_forward"][h]))
        L.append("- verdad secundaria (Δ spread de estrés a 20 sesiones): ρ=%s p=%s n=%s" % (_f(blk["stress_secondary"]["rho"]), _f(blk["stress_secondary"]["p"]), blk["stress_secondary"]["n"]))
        L.append("\n### Umbrales que sobreviven (entrenamiento |t| ≥ 2, signo confirmado en prueba)\n")
        L.append("| horizonte | INJECTION ≥ | cobertura | t (train) | Δ retorno train | Δ retorno test | DRAIN ≤ | cobertura | t (train) | Δ train | Δ test |\n|---|---|---|---|---|---|---|---|---|---|---|")
        for h in HORIZONS:
            t = blk["thresholds"][h]
            i, d = t["injection"], t["drain"]
            L.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                h, i["cut"] if i else "ninguno", _f(i["train"]["coverage"], 2) if i else "—", _f(i["train"]["t"], 2) if i else "—", _f(i["train"]["diff"]) if i else "—", _f(i["test"]["diff"]) if i else "—",
                d["cut"] if d else "ninguno", _f(d["train"]["coverage"], 2) if d else "—", _f(d["train"]["t"], 2) if d else "—", _f(d["train"]["diff"]) if d else "—", _f(d["test"]["diff"]) if d else "—"))
    L.append("\n## 3. Pesos duales (OLS del retorno forward sobre los dos bloques estandarizados; walk-forward)\n")
    for h, dl in res["dual"].items():
        L.append("- %s sesiones: %s" % (h, json.dumps(dl, ensure_ascii=False)))
    if res.get("ab"):
        ab = res["ab"]
        L.append("\n## A. Umbrales por frecuencia de la era operativa (desde %s, %d semanas)\n" % (ab["era_start"], ab["weeks"]))
        L.append("| bloque | n | p10 | p20 | p33 | p50 | p67 | p80 | p90 | %% DRAIN a −0,5 | %% INJ a +0,5 | propuesta enter/exit |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
        for name, a in ab["A_frequency"].items():
            if a.get("status"):
                L.append("| %s | insuficiente |" % name); continue
            pr = a.get("final_cut") or a["proposal_auto"]
            L.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | INJ ≥ %s (salida %s) · DRAIN ≤ %s (salida %s) |" % (name, a["n"], a["p10"], a["p20"], a["p33"], a["p50"], a["p67"], a["p80"], a["p90"], a["share_drain_at_minus_0_5"], a["share_inj_at_plus_0_5"], pr["injection_enter"], pr["injection_exit"], pr["drain_enter"], pr["drain_exit"]))
        L.append("\nConvención de percentil: %s." % ab["percentile_convention"])
        for name, a in ab["A_frequency"].items():
            if a.get("final_cut"):
                fc, au = a["final_cut"], a["proposal_auto"]
                L.append("- %s — corte de mesa (fuente única para el config): INJ ≥ %s / DRAIN ≤ %s → %s%% / %s%% de las semanas de la era · regla: %s · propuesta automática p80/p20: %s / %s (p80 alcanzable más próximo %s, p20 %s)" % (
                    name, fc["injection_enter"], fc["drain_enter"], round(fc["share_injection"] * 100), round(fc["share_drain"] * 100), fc["rule"], au["injection_enter"], au["drain_enter"], a["p80_nearest_attainable"], a["p20_nearest_attainable"]))
        for name, a in ab["A_frequency"].items():
            if a.get("by_year"):
                L.append("\nEstabilidad año a año — %s: " % name + " · ".join("%s p20 %s / p50 %s / p80 %s" % (y, v["p20"], v["p50"], v["p80"]) for y, v in a["by_year"].items()))
        L.append("\n## B. Verdad de funding — puntuación del bloque vs Δ spread de estrés (4 y 12 semanas; hipótesis: INJECTION comprime, DRAIN ensancha → ρ negativa)\n")
        for name, b in ab["B_funding"].items():
            for h, v in b.items():
                i, d = v["injection"], v["drain"]
                L.append("- %s, %s semanas: ρ=%s p=%s (p block-bootstrap 8 s: %s; rejilla de %s cortes) n=%s · umbral INJECTION que sobrevive: %s · DRAIN: %s" % (
                    name, h, _f(v["rho"]), _f(v["p"], 4), _f(v.get("p_block_bootstrap"), 4), v.get("grid_tests"), v["n"],
                    ("≥ %s (Δ train %s, t %s; Δ test %s)" % (i["cut"], _f(i["train"]["diff"], 2), _f(i["train"]["t"], 2), _f(i["test"]["diff"], 2))) if i else "ninguno",
                    ("≤ %s (Δ train %s, t %s; Δ test %s)" % (d["cut"], _f(d["train"]["diff"], 2), _f(d["train"]["t"], 2), _f(d["test"]["diff"], 2))) if d else "ninguno"))
    if res.get("auctions"):
        L.append("\n## 4. Subastas — anclas empíricas y validación\n")
        for kind, o in res["auctions"].items():
            L.append("### %s (n=%d, %s → %s)\n" % (kind, o["n"], o["first"], o["last"]))
            c = o["coverage"]
            L.append("- bid-to-cover: p5 %s · p10 %s · p25 %s · mediana %s · p75 %s · p90 %s · últimos 3 años (n=%d): p10 %s mediana %s" % (c["p5"], c["p10"], c["p25"], c["median"], c["p75"], c["p90"], c["recent_3y"]["n"], c["recent_3y"]["p10"], c["recent_3y"]["median"]))
            if o.get("tail_bps"):
                L.append("- tail (pb): p50 %s · p75 %s · p90 %s · p95 %s" % (o["tail_bps"]["p50"], o["tail_bps"]["p75"], o["tail_bps"]["p90"], o["tail_bps"]["p95"]))
            for h in (5, 20):
                w, s = o["weak_vs_rest_fwd%d" % h], o["strong_vs_rest_fwd%d" % h]
                L.append("- subastas débiles (≤ p10) vs resto, retorno FX forward %d: Δ %s t %s · fuertes (≥ p90): Δ %s t %s" % (h, _f(w.get("diff")), _f(w.get("t"), 2), _f(s.get("diff")), _f(s.get("t"), 2)))
            L.append("- ρ bid-to-cover vs retorno forward 20: %s (p %s, n %s)" % (_f(o["coverage_vs_fwd20"]["rho"]), _f(o["coverage_vs_fwd20"]["p"]), o["coverage_vs_fwd20"]["n"]))
    txt = "\n".join(L) + "\n"
    open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8").write(txt)
    return txt


# ───────────────────────────── engine v0.3 calibration ─────────────────────────────
def _welch(a: np.ndarray, b: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    if len(a) < 5 or len(b) < 5:
        return None, None
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return float(t), float(p)


def _regime_series(scores: List[Optional[float]], dates: List[str], cuts: dict, persistence: dict) -> List[str]:
    from .engine import block_regime_step
    st, out = {}, []
    for sc, d in zip(scores, dates):
        st = block_regime_step(sc, cuts, st, d, persistence)
        out.append(st["confirmed"] if sc is not None else "NO SIGNAL")
    return out


def _spells(reg: List[str]) -> dict:
    sw, cur, lens = 0, None, []
    n = 0
    for r in reg:
        if r == cur:
            n += 1
        else:
            if cur is not None:
                lens.append(n); sw += 1
            cur, n = r, 1
    if cur is not None:
        lens.append(n)
    return {"switches": max(0, sw), "mean_spell_weeks": round(float(np.mean(lens)), 1) if lens else None, "min_spell_weeks": int(min(lens)) if lens else None}


def _era_cuts(x: np.ndarray) -> dict:
    """Pre-registered cuts on an era sample: enter = nearest attainable value to p80 / p20, strictly beyond the median (discrete
    scales: the next attainable value past the median mass); exit = nearest attainable to p67 / p33, strictly beyond the median on
    its side — otherwise no hysteresis (exit = enter), so a median mass can never be captured by a stale side."""
    pct = lambda p: float(np.percentile(x, p))
    med = pct(50)
    u = np.unique(x)
    above = [float(v) for v in u if v > med]
    below = [float(v) for v in u if v < med]
    inj = _nearest_attainable(x, pct(80))
    if inj <= med:
        inj = min(above) if above else float(u[-1])
    drn = _nearest_attainable(x, pct(20))
    if drn >= med:
        drn = max(below) if below else float(u[0])
    # mass guard (discrete scales): an enter cut may never capture more than 35 % of the era on its side — step outwards
    for _ in range(3):
        if float(np.mean(x >= inj)) > 0.35 and [v for v in above if v > inj]:
            inj = min(v for v in above if v > inj)
        else:
            break
    for _ in range(3):
        if float(np.mean(x <= drn)) > 0.35 and [v for v in below if v < drn]:
            drn = max(v for v in below if v < drn)
        else:
            break
    inj_x = _nearest_attainable(x, pct(67))
    if not (med < inj_x <= inj):
        inj_x = inj
    drn_x = _nearest_attainable(x, pct(33))
    if not (drn <= drn_x < med):
        drn_x = drn
    return {"injection_enter": inj, "injection_exit": inj_x, "drain_enter": drn, "drain_exit": drn_x}


def analyse_v03(res: dict, R: dict, era_start: str, out_dir: str) -> dict:
    """Engine v0.3 calibration on the era replay (percentile windows anchored to the era from era_start):
    (1) level-weight grid LW_GRID, re-scoring the published block components without a new replay;
    (2) pre-registered cuts = era p80/p20 of the block score (exit p67/p33), nearest attainable value — no grid search;
    (3) persistence 7/0 (two weekly prints in, one out) and the agreement rule for the general regime;
    (4) B (funding truth) evaluated ONLY at those cuts: conditional mean Δ spread (4 / 12 weeks) DRAIN − NEUTRAL and INJECTION − NEUTRAL
        with Welch t, Spearman + moving-block bootstrap p; alternative spreads (NZD / JPY) when the replay provides them;
    (5) level-weight choice, pre-registered rule: the largest weight (closest to v0.2) whose era distribution is two-sided —
        both INJECTION and DRAIN attainable in >= 10 % of the era weeks under persistence — and, among those, the one with the
        highest balance min(share INJECTION, share DRAIN); B is reported as evidence, never used to pick the weight."""
    from .scoring import Comps
    rows = R["rows"]
    dates = [r["date"] for r in rows]
    idx = [i for i, d in enumerate(dates) if d >= era_start]
    edates = [dates[i] for i in idx]
    st = R["stress"]
    sd_ = [x for x, _ in st]
    import bisect

    def fstress(series: Series, h_weeks: int) -> List[Optional[float]]:
        sd = [x for x, _ in series]
        out = []
        for d in edates:
            i = bisect.bisect_right(sd, d) - 1
            j = i + h_weeks
            out.append((series[j][1] - series[i][1]) if (i >= 0 and j < len(series)) else None)
        return out
    truths = {"stress": R["stress"]}
    if R.get("stress_alt"):
        truths["stress_alt"] = R["stress_alt"]
    fs = {k: {4: fstress(v, 4), 12: fstress(v, 12)} for k, v in truths.items() if v}
    v03 = {"era_start": era_start, "weeks": len(idx), "level_weights": LW_GRID, "persistence": PERSISTENCE, "truths": {k: R.get(k + "_label", k) for k in truths},
           "blocks": {}, "general": {}, "selected_level_weight": None}
    per_block_reg: Dict[str, Dict[float, List[str]]] = {}
    for name, key in (("central_bank", "cb_comp"), ("fiscal", "fi_comp")):
        comps = [rows[i].get(key) for i in idx]
        base = [rows[i]["cb_score" if name == "central_bank" else "fi_score"] for i in idx]
        blk = {"has_levels": any(c and c.get("level") for c in comps), "level_names": sorted({k for c in comps if c for k in c.get("level", {})}),
               "flow_names": sorted({k for c in comps if c for k in c.get("flow", {})}), "by_level_weight": {}}
        per_block_reg[name] = {}
        for lw in LW_GRID:
            sc = [None if (c is None and b is None) else (Comps.rescore(c, lw) if c else b) for c, b in zip(comps, base)]
            # effective (operating) score under the persistence rule: mean of this print and the previous one when they are <= entry_days apart
            eff: List[Optional[float]] = []
            for k, v in enumerate(sc):
                pv = sc[k - 1] if k > 0 else None
                gap = (date.fromisoformat(edates[k]) - date.fromisoformat(edates[k - 1])).days if k > 0 else 99
                eff.append(None if v is None else (round((v + pv) / 2, 3) if (PERSISTENCE.get("mode", "mean") == "mean" and pv is not None and gap <= PERSISTENCE["entry_days"]) else v))
            x = np.array([v for v in eff if v is not None], dtype=float)
            xr = np.array([v for v in sc if v is not None], dtype=float)
            if len(x) < 30:
                blk["by_level_weight"][lw] = {"status": "insufficient", "n": int(len(x))}
                continue
            cuts = _era_cuts(x)
            cuts_raw = _era_cuts(xr)
            reg = _regime_series(sc, edates, cuts, PERSISTENCE)
            per_block_reg[name][lw] = reg
            n = sum(1 for r in reg if r != "NO SIGNAL") or 1
            share = {k: round(sum(1 for r in reg if r == k) / n, 3) for k in ("INJECTION", "NEUTRAL", "DRAIN")}
            variants = {}
            for vn, vp in PERSISTENCE_VARIANTS.items():
                rv = _regime_series(sc, edates, cuts if vp.get("mode", "mean") == "mean" and vp.get("entry_days", 0) > 0 else cuts_raw, vp)
                variants[vn] = {k: round(sum(1 for r in rv if r == k) / n, 3) for k in ("INJECTION", "NEUTRAL", "DRAIN")}
                variants[vn]["switches"] = _spells(rv)["switches"]
            by_year = {}
            for y in sorted(set(d[:4] for d in edates)):
                ry = [r for r, d in zip(reg, edates) if d[:4] == y and r != "NO SIGNAL"]
                if len(ry) >= 10:
                    by_year[y] = {k: round(sum(1 for r in ry if r == k) / len(ry), 2) for k in ("INJECTION", "DRAIN")}
            # B at the pre-registered cuts, per truth, on the operating (effective) score
            B = {}
            for tk, fh in fs.items():
                B[tk] = {}
                for h in (4, 12):
                    y = fh[h]
                    r_, p_, n_ = spearman(eff, y)
                    grp = {k: np.array([yy for rr, yy in zip(reg, y) if rr == k and yy is not None], dtype=float) for k in ("INJECTION", "NEUTRAL", "DRAIN")}
                    td, pd_ = _welch(grp["DRAIN"], grp["NEUTRAL"])
                    ti, pi_ = _welch(grp["INJECTION"], grp["NEUTRAL"])
                    B[tk][h] = {"rho": None if r_ is None else round(r_, 3), "p": None if p_ is None else round(p_, 4), "n": n_,
                                "p_block_bootstrap": block_bootstrap_p(eff, y),
                                "mean_delta": {k: (round(float(g.mean()), 3) if len(g) else None) for k, g in grp.items()}, "n_by_regime": {k: int(len(g)) for k, g in grp.items()},
                                "drain_vs_neutral": {"t": None if td is None else round(td, 2), "p": None if pd_ is None else round(pd_, 4), "sign_ok": (td is not None and td > 0)},
                                "injection_vs_neutral": {"t": None if ti is None else round(ti, 2), "p": None if pi_ is None else round(pi_, 4), "sign_ok": (ti is not None and ti < 0)}}
            pct = lambda p: float(np.percentile(x, p))
            blk["by_level_weight"][lw] = {"n": int(len(x)), "p10": round(pct(10), 2), "p20": round(pct(20), 2), "p50": round(pct(50), 2), "p80": round(pct(80), 2), "p90": round(pct(90), 2),
                                          "raw_p20": round(float(np.percentile(xr, 20)), 2), "raw_p50": round(float(np.percentile(xr, 50)), 2), "raw_p80": round(float(np.percentile(xr, 80)), 2),
                                          "attainable_values": [float(v) for v in np.unique(x)][:25], "n_attainable": int(len(np.unique(x))), "n_attainable_raw": int(len(np.unique(xr))), "cuts": cuts, "cuts_raw_score": cuts_raw,
                                          "shares": share, "balance": round(min(share["INJECTION"], share["DRAIN"]), 3),
                                          "two_sided": share["INJECTION"] >= 0.10 and share["DRAIN"] >= 0.10, "spells": _spells(reg), "by_year": by_year, "B": B,
                                          "shares_by_persistence": variants}
        # level-weight choice (pre-registered rule, engine v0.3): with era-relative cuts the shares are fixed by construction, so
        # the weight can only be judged by the funding truth. Rule: keep 1.0 (v0.2 arithmetic) unless a weight has a B test that
        # survives the moving-block bootstrap (p <= 0.05) with the MMT sign on the primary truth at 12 weeks — then the weight with
        # the strongest such |rho|; ties to the larger weight. Alternative truths are reported, never used to pick.
        cands = [(lw, v) for lw, v in blk["by_level_weight"].items() if v.get("status") != "insufficient"]
        if not blk["has_levels"]:
            blk["selected_level_weight"], blk["selection_rule"] = 1.0, "no level components in this block — weight irrelevant"
        elif cands:
            def _b12(v):
                b = ((v.get("B") or {}).get("stress") or {}).get(12) or {}
                pb, r = b.get("p_block_bootstrap"), b.get("rho")
                return (r, pb) if (pb is not None and pb <= 0.05 and r is not None and r < 0) else None
            ok = [(lw, v, _b12(v)) for lw, v in cands if _b12(v)]
            if ok:
                best = max(ok, key=lambda t: (abs(t[2][0]), t[0]))
                blk["selected_level_weight"] = best[0]
                blk["selection_rule"] = "funding truth: strongest bootstrap-significant B at 12 weeks (rho %s, p %s); ties to the larger weight" % (best[2][0], best[2][1])
            else:
                blk["selected_level_weight"] = 1.0 if any(lw == 1.0 for lw, _ in cands) else cands[0][0]
                blk["selection_rule"] = "no weight has a bootstrap-significant B at 12 weeks — v0.2 arithmetic kept (1.0); shares are era-relative whatever the weight"
            blk["one_sided"] = not any(v["two_sided"] for _, v in cands)
        v03["blocks"][name] = blk
    # general regime by the agreement rule at the selected weights
    lw_cb = v03["blocks"].get("central_bank", {}).get("selected_level_weight")
    lw_fi = v03["blocks"].get("fiscal", {}).get("selected_level_weight")
    if lw_cb is not None and lw_fi is not None and per_block_reg.get("central_bank", {}).get(lw_cb) and per_block_reg.get("fiscal", {}).get(lw_fi):
        rc, rf = per_block_reg["central_bank"][lw_cb], per_block_reg["fiscal"][lw_fi]
        gen = []
        for a, b in zip(rc, rf):
            if a == "INJECTION" and b == "INJECTION":
                gen.append("LIQUIDITY_INJECTION")
            elif a == "DRAIN" and b == "DRAIN":
                gen.append("LIQUIDITY_DRAIN")
            elif "NO SIGNAL" in (a, b):
                gen.append("NO SIGNAL")
            elif "NEUTRAL" in (a, b):
                gen.append("NEUTRAL_PARTIAL")
            else:
                gen.append("NEUTRAL_CONFLICT")
        n = sum(1 for g in gen if g != "NO SIGNAL") or 1
        v03["general"] = {"level_weights": {"central_bank": lw_cb, "fiscal": lw_fi},
                          "shares": {k: round(sum(1 for g in gen if g == k) / n, 3) for k in ("LIQUIDITY_INJECTION", "NEUTRAL_PARTIAL", "NEUTRAL_CONFLICT", "LIQUIDITY_DRAIN")},
                          "spells": _spells(gen), "rule": "agreement only: both inject / both drain; partial and conflict = NEUTRAL (labelled)"}
        v03["selected_level_weight"] = lw_cb
        # persist per-week series
        with open(os.path.join(out_dir, "v03_regimes.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "cb_score_lw", "cb_regime", "fi_score_lw", "fi_regime", "general"])
            for k, i in enumerate(idx):
                cc, fc = rows[i].get("cb_comp"), rows[i].get("fi_comp")
                w.writerow([dates[i], Comps.rescore(cc, lw_cb) if cc else rows[i]["cb_score"], rc[k], Comps.rescore(fc, lw_fi) if fc else rows[i]["fi_score"], rf[k], gen[k]])
    # config patch (regime.dual, engine v0.3) — evidence labels filled after the joint FDR (fdr_all --v03)
    patch = {"version": "0.3", "status": "calibrated by replay %s (engine v0.3, era %s, %d weeks)" % (res["generated_at"][:10], era_start, len(idx)),
             "era_start": era_start, "anchor_percentiles": True, "level_weight": lw_cb, "persistence": PERSISTENCE,
             "agreement_only": True, "agreement_only_until_weeks": 150, "weights": {"central_bank": 0.6, "fiscal": 0.4}, "general_thresholds": {"injection": 0.5, "drain": -0.5},
             "block_thresholds": {}}
    for name in ("central_bank", "fiscal"):
        blk = v03["blocks"].get(name) or {}
        lw = blk.get("selected_level_weight")
        v = (blk.get("by_level_weight") or {}).get(lw) if lw is not None else None
        if not v or v.get("status") == "insufficient":
            continue
        short = len(idx) < 150
        by_design = v.get("n_attainable_raw", v.get("n_attainable", len(v["attainable_values"]))) <= 3
        ev = "provisional_era_corta" if short else ("banda_por_diseño" if by_design else "frecuencia_de_era")
        patch["block_thresholds"][name] = dict(v["cuts"], level_weight=lw, evidence={"injection": ev, "drain": ev},
                                               rule="era p80/p20 (exit p67/p33) of the %s-day mean score, nearest attainable, exit after %d days inside" % (PERSISTENCE["entry_days"], PERSISTENCE["exit_days"]))
        if blk.get("one_sided"):
            patch["block_thresholds"][name]["evidence"]["note"] = "one_sided: no level weight makes both tails attainable — the missing side needs a flow redesign"
    v03["config_patch"] = patch
    res["v03"] = v03
    return v03


def report_v03(res: dict) -> str:
    v = res.get("v03") or {}
    L = ["# %s — engine v0.3 (era %s, %d semanas; ventanas ancladas a la era; persistencia %d/%d días; regla de acuerdo)\n" % (res["currency"], v.get("era_start"), v.get("weeks", 0), PERSISTENCE["entry_days"], PERSISTENCE["exit_days"])]
    for name, blk in (v.get("blocks") or {}).items():
        L.append("\n## %s — niveles: %s · flujos: %s\n" % (name, ", ".join(blk.get("level_names") or []) or "ninguno", ", ".join(blk.get("flow_names") or [])))
        L.append("| peso nivel | p20 / p50 / p80 (puntuación operativa = media 2 s; bruta) | cortes INJ ≥ (salida) / DRAIN ≤ (salida) | INJ / NEUTRAL / DRAIN | balance | cambios · racha media | B 12s: ρ (p boot) · DRAIN−N t · INJ−N t |")
        L.append("|---|---|---|---|---|---|---|")
        for lw, r in blk["by_level_weight"].items():
            if r.get("status") == "insufficient":
                L.append("| %s | insuficiente (n %d) | | | | | |" % (lw, r["n"]))
                continue
            c, s, sp = r["cuts"], r["shares"], r["spells"]
            b = (r["B"].get("stress") or {}).get(12, {})
            L.append("| %s%s | %.2f / %.2f / %.2f (%.2f / %.2f / %.2f) | %+.2f (%+.2f) / %+.2f (%+.2f) | %d / %d / %d %% | %.2f%s | %d · %s | %s (%s) · %s · %s |" % (
                lw, " ★" if lw == blk.get("selected_level_weight") else "", r["p20"], r["p50"], r["p80"], r.get("raw_p20", 0), r.get("raw_p50", 0), r.get("raw_p80", 0), c["injection_enter"], c["injection_exit"], c["drain_enter"], c["drain_exit"],
                round(s["INJECTION"] * 100), round(s["NEUTRAL"] * 100), round(s["DRAIN"] * 100), r["balance"], "" if r["two_sided"] else " (un lado)", sp["switches"], sp["mean_spell_weeks"],
                _f(b.get("rho")), _f(b.get("p_block_bootstrap")), _f((b.get("drain_vs_neutral") or {}).get("t"), 2), _f((b.get("injection_vs_neutral") or {}).get("t"), 2)))
        L.append("\nPeso seleccionado: **%s** — %s" % (blk.get("selected_level_weight"), blk.get("selection_rule")))
        rs = blk["by_level_weight"].get(blk.get("selected_level_weight")) or {}
        if rs.get("shares_by_persistence"):
            L.append("Persistencia (peso seleccionado): " + " · ".join("%s → INJ %d %% / DRAIN %d %% / cambios %d" % (k, round(v["INJECTION"] * 100), round(v["DRAIN"] * 100), v["switches"]) for k, v in rs["shares_by_persistence"].items()))
        if "stress_alt" in (v.get("truths") or {}):
            lw = blk.get("selected_level_weight")
            r = blk["by_level_weight"].get(lw) or {}
            for tk in ("stress", "stress_alt"):
                for h in (4, 12):
                    b = (r.get("B") or {}).get(tk, {}).get(h)
                    if b:
                        L.append("- B %s %ds: ρ %s (p %s, boot %s, n %s) · Δ medio DRAIN %s / NEUTRAL %s / INJ %s · t DRAIN−N %s · t INJ−N %s" % (
                            tk, h, _f(b["rho"]), _f(b["p"]), _f(b["p_block_bootstrap"]), b["n"], _f(b["mean_delta"]["DRAIN"], 2), _f(b["mean_delta"]["NEUTRAL"], 2), _f(b["mean_delta"]["INJECTION"], 2),
                            _f(b["drain_vs_neutral"]["t"], 2), _f(b["injection_vs_neutral"]["t"], 2)))
    g = v.get("general") or {}
    if g:
        s = g["shares"]
        L.append("\n## Régimen general (regla de acuerdo, pesos %s)\n" % g["level_weights"])
        L.append("INYECCIÓN %d %% · NEUTRAL parcial %d %% · NEUTRAL conflicto %d %% · DRENAJE %d %% · cambios %s · racha media %s semanas" % (
            round(s["LIQUIDITY_INJECTION"] * 100), round(s["NEUTRAL_PARTIAL"] * 100), round(s["NEUTRAL_CONFLICT"] * 100), round(s["LIQUIDITY_DRAIN"] * 100), g["spells"]["switches"], g["spells"]["mean_spell_weeks"]))
    L.append("\n## Parche de config (regime.dual)\n\n```json\n%s\n```" % json.dumps(v.get("config_patch"), indent=1, ensure_ascii=False))
    return "\n".join(L)



def fdr_all(out_root: str) -> dict:
    """Benjamini–Hochberg FDR across every B test of every currency (2 blocks × 2 horizons × 8 currencies) on the raw and the
    block-bootstrap p-values (triangulation 2026-09-09: Perplexity, Kimi). Writes calibration/B_fdr.json and prints the table."""
    tests = []
    for ccy in sorted(os.listdir(out_root)):
        p = os.path.join(out_root, ccy, "calibration.json")
        if not os.path.exists(p) or ccy.endswith("_v03"):
            continue
        j = json.load(open(p))
        for name, b in (j.get("ab", {}).get("B_funding") or {}).items():
            for h, v in b.items():
                if v.get("p") is not None:
                    tests.append({"ccy": ccy, "block": name, "h": int(h), "rho": v["rho"], "p": v["p"], "p_bb": v.get("p_block_bootstrap"), "n": v["n"]})
    def bh(ps):
        m = len(ps)
        order = np.argsort(ps)
        q = np.empty(m)
        prev = 1.0
        for rank, i in enumerate(order[::-1], start=0):
            k = m - rank
            val = min(prev, ps[i] * m / k)
            q[i] = val
            prev = val
        return q
    if tests:
        q = bh(np.array([t["p"] for t in tests]))
        qb = bh(np.array([t["p_bb"] if t["p_bb"] is not None else 1.0 for t in tests]))
        for t, a, b in zip(tests, q, qb):
            t["q_fdr"] = round(float(a), 4)
            t["q_fdr_block_bootstrap"] = round(float(b), 4)
            t["survives_5pct"] = bool(a <= 0.05 and b <= 0.05 and (t["rho"] or 0) < 0)
    out = {"generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z", "n_tests": len(tests), "method": "Benjamini–Hochberg on Spearman p (raw and moving-block bootstrap, block 8 weeks); survives = q ≤ 0.05 on both and MMT sign (ρ < 0)", "tests": tests}
    json.dump(out, open(os.path.join(out_root, "B_fdr.json"), "w"), indent=1)
    lines = ["| divisa | bloque | h | ρ | p | p bootstrap | q FDR | q FDR bootstrap | sobrevive |", "|---|---|---|---|---|---|---|---|---|"]
    for t in sorted(tests, key=lambda t: t["p"]):
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (t["ccy"].upper(), t["block"], t["h"], t["rho"], t["p"], t["p_bb"], t.get("q_fdr"), t.get("q_fdr_block_bootstrap"), "SÍ" if t.get("survives_5pct") else "no"))
    txt = "\n".join(lines)
    open(os.path.join(out_root, "B_fdr.md"), "w").write("# B — corrección por comparaciones múltiples y autocorrelación (las ocho divisas)\n\n" + txt + "\n")
    print(txt)
    return out


def _bh(ps: np.ndarray) -> np.ndarray:
    m = len(ps)
    order = np.argsort(ps)
    q = np.empty(m)
    prev = 1.0
    for rank, i in enumerate(order[::-1], start=0):
        k = m - rank
        val = min(prev, ps[i] * m / k)
        q[i] = val
        prev = val
    return q


def fdr_v03(out_root: str) -> dict:
    """Joint Benjamini–Hochberg over the v0.3 pre-registered B tests (selected level weight, era p80/p20 cuts, persistence): one
    Spearman per block × horizon × truth (primary + alternative where the replay provides one), p from the moving-block bootstrap.
    Writes calibration/B_fdr_v03.{json,md} and stamps the evidence labels into each calibration_v03 config patch:
    funding_validado  = q ≤ 0.05 on the bootstrap p, ρ < 0 (MMT sign) and the conditional mean on that side has the expected sign;
    frecuencia_de_era / banda_por_diseño / provisional_era_corta otherwise (as set by analyse_v03)."""
    tests, files = [], {}
    for d in sorted(os.listdir(out_root)):
        p = os.path.join(out_root, d, "calibration.json")
        if not d.endswith("_v03") or not os.path.exists(p):
            continue
        j = json.load(open(p))
        files[d] = j
        v = j.get("v03") or {}
        for name, blk in (v.get("blocks") or {}).items():
            lw = blk.get("selected_level_weight")
            r = (blk.get("by_level_weight") or {}).get(str(lw)) or (blk.get("by_level_weight") or {}).get(lw)
            if not r or r.get("status") == "insufficient":
                continue
            for tk, hh in (r.get("B") or {}).items():
                for h, b in hh.items():
                    if b.get("p") is None:
                        continue
                    tests.append({"ccy": d[:3], "block": name, "truth": tk, "h": int(h), "rho": b["rho"], "p": b["p"], "p_bb": b.get("p_block_bootstrap"), "n": b["n"],
                                  "drain_sign_ok": (b.get("drain_vs_neutral") or {}).get("sign_ok"), "injection_sign_ok": (b.get("injection_vs_neutral") or {}).get("sign_ok"),
                                  "t_drain": (b.get("drain_vs_neutral") or {}).get("t"), "t_injection": (b.get("injection_vs_neutral") or {}).get("t")})
    if tests:
        q = _bh(np.array([t["p"] for t in tests]))
        qb = _bh(np.array([t["p_bb"] if t["p_bb"] is not None else 1.0 for t in tests]))
        for t, a, b in zip(tests, q, qb):
            t["q_fdr"] = round(float(a), 4)
            t["q_fdr_block_bootstrap"] = round(float(b), 4)
            t["survives_5pct"] = bool(b <= 0.05 and (t["rho"] or 0) < 0)
    # stamp evidence labels
    for d, j in files.items():
        patch = ((j.get("v03") or {}).get("config_patch") or {})
        for name, bt in (patch.get("block_thresholds") or {}).items():
            ev = bt.get("evidence") or {}
            for side, key in (("drain", "drain_sign_ok"), ("injection", "injection_sign_ok")):
                hits = [t for t in tests if t["ccy"] == d[:3] and t["block"] == name and t.get("survives_5pct") and t.get(key)]
                if hits:
                    ev[side] = "funding_validado"
                    ev[side + "_test"] = "%s %dw ρ %s q %s" % (hits[0]["truth"], hits[0]["h"], hits[0]["rho"], hits[0]["q_fdr_block_bootstrap"])
            bt["evidence"] = ev
        json.dump(j, open(os.path.join(out_root, d, "calibration.json"), "w"), indent=1, default=str)
    out = {"generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z", "n_tests": len(tests),
           "method": "pre-registered cuts (era p80/p20, persistence 7/0 mean) at the selected level weight; Benjamini–Hochberg on the moving-block bootstrap p (block 8 weeks); survives = q ≤ 0.05 and ρ < 0", "tests": tests}
    json.dump(out, open(os.path.join(out_root, "B_fdr_v03.json"), "w"), indent=1)
    lines = ["| divisa | bloque | verdad | h | ρ | p boot | q FDR boot | t DRAIN−N | t INJ−N | sobrevive |", "|---|---|---|---|---|---|---|---|---|---|"]
    for t in sorted(tests, key=lambda t: (t["p_bb"] if t["p_bb"] is not None else 1.0)):
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (t["ccy"].upper(), t["block"], t["truth"], t["h"], t["rho"], t["p_bb"], t.get("q_fdr_block_bootstrap"), t["t_drain"], t["t_injection"], "SÍ" if t.get("survives_5pct") else "no"))
    txt = "\n".join(lines)
    open(os.path.join(out_root, "B_fdr_v03.md"), "w").write("# B v0.3 — pruebas prerregistradas, corrección conjunta (las ocho divisas)\n\n%d pruebas · %s\n\n" % (len(tests), out["method"]) + txt + "\n")
    print(txt)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fdr", action="store_true", help="only: Benjamini–Hochberg across every currency's B tests (reads calibration/*/calibration.json)")
    ap.add_argument("--fdr-v03", action="store_true", help="only: joint FDR over the v0.3 pre-registered tests (reads calibration/*_v03/calibration.json) and stamps evidence labels")
    ap.add_argument("--ccy", default="cad")
    ap.add_argument("--start", default="2008-01-01")
    ap.add_argument("--era", default=None, help="operating-era start for the frequency thresholds (default: last structural break)")
    ap.add_argument("--split", default="2021-01-01", help="train < split <= test")
    ap.add_argument("--fixtures", default=None)
    ap.add_argument("--cache", default=None, help="pickle path: reuse the replay result if it exists, else save it there")
    ap.add_argument("--v03", action="store_true", help="engine v0.3 replay: era-anchored percentile windows, level-weight grid, pre-registered cuts, persistence 7/0, agreement rule")
    a = ap.parse_args(argv)
    if a.fdr:
        fdr_all(os.path.join(ROOT, "calibration"))
        return 0
    if a.fdr_v03:
        fdr_v03(os.path.join(ROOT, "calibration"))
        return 0
    ccy = a.ccy.lower()
    cfg = json.load(open(os.path.join(ROOT, "config", "%s.json" % ccy), encoding="utf-8"))
    fx_dir = a.fixtures or os.path.join(ROOT, "fixtures", ccy)
    era = a.era or ERA_DEFAULT.get(ccy)
    if a.v03:
        ERA["start"] = era
        a.era = era
    if a.cache and os.path.exists(a.cache):
        import pickle
        R = pickle.load(open(a.cache, "rb"))
    else:
        R = REPLAY[ccy](cfg, fx_dir, a.start)
        if a.cache:
            import pickle
            pickle.dump(R, open(a.cache, "wb"))
    out_dir = os.path.join(ROOT, "calibration", ccy + ("_v03" if a.v03 else ""))
    if a.era:
        R["structural_breaks"] = [b for b in R.get("structural_breaks", []) if b["date"] <= a.era] + [{"date": a.era, "note": "era start set on the command line"}]
    res = analyse(ccy, cfg, R, a.split, out_dir)
    if a.v03:
        analyse_v03(res, R, era, out_dir)
        json.dump(res, open(os.path.join(out_dir, "calibration.json"), "w"), indent=1, default=str)
        txt = report_v03(res)
        open(os.path.join(out_dir, "report.md"), "w").write(txt + "\n")
        print(txt)
    else:
        print(report(res, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
