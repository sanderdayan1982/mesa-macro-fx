"""ICL — prerregistro definitivo T1–T3 (adjudicación ronda 3, 2026-09-09, §3). Una mirada.

Familia BH de tres tests sobre el retorno residual (betas as-of de Δdiferencial de política y canasta), bootstrap por bloques
móviles con longitud por la ACF de cada serie de IC, signo MMT (más inyección relativa → divisa relativamente más débil → IC > 0):

    T1  Tesoro: Φ⁻¹(percentil as-of de era de la media de 13 semanas del flujo fiscal del bloque)   h = 13 s
    T2  la misma señal                                                                              h = 26 s
    T3  Tesoro fontanería: −Δ13 s de la cuenta del gobierno en el BC como % de las reservas (13 s antes), historia completa
        del replay (sin puerta de era), demeaning transversal y escala agrupada como el brazo BC Δ13 s   h = 13 s

Aceptación por test: q_BH ≤ 0,05, IC 95 % bootstrap sin cero (y media > 0, hipótesis direccional), mitades del panel con el mismo signo.
Todo se reutiliza de ingest/conviction.py (panel, percentil as-of, sección cruzada, residualización, bootstrap, BH). El único
código copiado literalmente de run() es el bucle de retornos/Δpolítica/canasta (no está expuesto como función) y pairs().

    python -m ingest.conviction_t123 --cache-dir <dir con v03_<ccy>.pkl> [--out calibration/conviction]
"""
from __future__ import annotations
import argparse
import json
import os
from typing import Dict, List, Optional
import numpy as np

from .conviction import (CCYS, MIN_XS, ROOT, _asof, _f, acf, asof_percentile, bh, block_bootstrap_mean, block_len, cross_section,
                         forward_logret, fx_on_grid, ic_series, kendall_between, load_panel, residualise, tercile_spread)

DESIGN = "ICL T1–T3 (prerregistro definitivo, adjudicación ronda 3, 2026-09-09 §3; una mirada)"
WIN = 13                # semanas de la media del flujo fiscal (T1/T2) y del Δ de la cuenta del gobierno (T3)
GAP_MONTHLY = 45        # días de tolerancia as-of para la cuenta del gobierno (CHF y NZD son mensuales); reservas: 10 como en conviction.py
GAP_WEEKLY = 10
TESTS = (("T1", "fi_mean13", 13), ("T2", "fi_mean13", 26), ("T3", "govt_d13_pct", 13))
PERSIST_LAGS = (4, 8, 13, 26)


def _pairs(Zb: Dict[str, Dict[str, float]], grid: List[str]) -> Dict[str, Dict[str, float]]:
    """S_i = Z_i − Z_USD (copia de run()'s pairs)."""
    S = {c: {} for c in Zb if c != "usd"}
    for g in grid:
        zu = Zb["usd"].get(g)
        if zu is None:
            continue
        for c in S:
            if Zb[c].get(g) is not None:
                S[c][g] = Zb[c][g] - zu
    return S


def returns(D: dict, grid: List[str], horizons) -> tuple:
    """Retorno log adelantado por USD, Δ(diferencial de política), canasta equiponderada y residual — copia del bucle de run()."""
    era = {c: D["ccy"][c]["era"] for c in CCYS}
    fxg = {c: fx_on_grid(D["ccy"][c]["fx"], grid) for c in CCYS}
    polg = {c: {g: _asof(D["ccy"][c]["policy"], g, 40) for g in grid} for c in CCYS}
    ret, resid = {}, {}
    for h in horizons:
        ret[h] = {c: forward_logret(fxg[c], grid, h) for c in CCYS if c != "usd"}
        dpol = {}
        for c in ret[h]:
            dpol[c] = {}
            for i, g in enumerate(grid):
                if i + h < len(grid) and None not in (polg[c].get(g), polg[c].get(grid[i + h]), polg["usd"].get(g), polg["usd"].get(grid[i + h])):
                    dpol[c][g] = (polg[c][grid[i + h]] - polg[c][g]) - (polg["usd"][grid[i + h]] - polg["usd"][g])
                else:
                    dpol[c][g] = None
        basket = {}
        for g in grid:
            v = [ret[h][c].get(g) for c in ret[h] if ret[h][c].get(g) is not None]
            basket[g] = float(np.mean(v)) if len(v) >= 5 else None
        resid[h], _ = residualise(ret[h], dpol, basket, grid, h, era)
    return ret, resid


# ───────────────────────────── señales ─────────────────────────────
def signal_fi_mean13(D: dict, grid: List[str]) -> Dict[str, Dict[str, Optional[float]]]:
    """Mismo camino que el brazo exploratorio de run(): media de las últimas 13 impresiones del score de flujos del bloque fiscal,
    percentil as-of de era → Φ⁻¹ (clip ±2,5)."""
    n = {}
    for c in CCYS:
        ser = D["ccy"][c]["fi"]
        vals = [v for _, v in ser]
        sm = [(ser[i][0], float(np.mean(vals[max(0, i - WIN + 1): i + 1]))) for i in range(len(ser))]
        n[c] = asof_percentile(sm, D["ccy"][c]["era"], grid)
    return n


def signal_govt_d13(D: dict, grid: List[str]) -> tuple:
    """−Δ13 s de la cuenta del gobierno / |reservas 13 s antes| × 100, historia completa del replay (sin puerta de era).
    Mismo cálculo que el brazo absoluto govt_d13_pct de run(), salvo: sin `g >= era` y tolerancia as-of de 45 días para la cuenta."""
    A: Dict[str, Dict[str, float]] = {}
    excluded = []
    for c in CCYS:
        gov = D["ccy"][c]["govt"]
        if not gov:
            excluded.append(c)
            continue
        vals = {g: _asof(gov, g, GAP_MONTHLY) for g in grid}
        resv = {g: _asof(D["ccy"][c]["reserves"], g, GAP_WEEKLY) for g in grid}
        A[c] = {}
        for i, g in enumerate(grid):
            if i >= WIN and vals.get(g) is not None and vals.get(grid[i - WIN]) is not None and resv.get(grid[i - WIN]):
                A[c][g] = -(vals[g] - vals[grid[i - WIN]]) / abs(resv[grid[i - WIN]]) * 100
    return A, excluded


# ───────────────────────────── descriptivos ─────────────────────────────
def _acf13_by_ccy(sig: Dict[str, Dict[str, Optional[float]]], grid: List[str]) -> Dict[str, Optional[float]]:
    out = {}
    for c, s in sig.items():
        x = np.array([s[g] for g in grid if s.get(g) is not None])
        out[c] = round(acf(x, 13)[13], 2) if len(x) > 40 else None
    return out


def _persistence(Z: Dict[str, Dict[str, float]], grid: List[str]) -> Dict[int, Optional[float]]:
    """Mediana de τ de Kendall entre el ranking transversal en t y en t+k."""
    out = {}
    for k in PERSIST_LAGS:
        taus = []
        for i in range(len(grid) - k):
            a = {c: Z[c].get(grid[i]) for c in Z if Z[c].get(grid[i]) is not None}
            b = {c: Z[c].get(grid[i + k]) for c in Z if Z[c].get(grid[i + k]) is not None}
            t = kendall_between(a, b)
            if t is not None:
                taus.append(t)
        out[k] = round(float(np.median(taus)), 3) if taus else None
    return out


def _resid_share(S: Dict[str, Dict[str, float]], ret_h: dict, resid_h: dict, ds: List[str]) -> float:
    """Fracción de observaciones divisa-semana del test cuyo retorno ya está residualizado (antes de MIN_BETA es el retorno bruto)."""
    tot = res = 0
    for c in S:
        for g in ds:
            if S[c].get(g) is None or resid_h[c].get(g) is None:
                continue
            tot += 1
            res += int(resid_h[c][g] != ret_h[c][g])
    return round(res / tot, 3) if tot else 0.0


# ───────────────────────────── análisis ─────────────────────────────
def run(cache_dir: str, fx_root: str, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    D = load_panel(cache_dir, fx_root)
    # rejilla acotada al último viernes cubierto por el FX de todas las divisas (evita un retorno adelantado con precio stale)
    fx_end = min(D["ccy"][c]["fx"][-1][0] for c in CCYS)
    grid = [g for g in D["grid"] if g <= fx_end]
    ret, resid = returns(D, grid, (13, 26))

    n12 = signal_fi_mean13(D, grid)
    Z12, _ = cross_section(n12, grid)
    S12 = _pairs(Z12, grid)
    A3, excluded = signal_govt_d13(D, grid)
    Z3, _ = cross_section(A3, grid)
    S3 = _pairs(Z3, grid)
    sig = {"fi_mean13": (n12, Z12, S12), "govt_d13_pct": (A3, Z3, S3)}

    res = {"design": DESIGN, "grid": [grid[0], grid[-1]], "n_boot_seed": "N_BOOT/SEED de conviction.py", "tests": [], "descriptives": {}, "deviations": [
        "T3 sin puerta de era (historia completa del replay); las señales T1/T2 mantienen la puerta de era del percentil as-of.",
        "T3: tolerancia as-of de %d días para la cuenta del gobierno (CHF y NZD son mensuales; el replay ya arrastra el último valor publicado a cada semana, así que la tolerancia sólo actúa en los extremos)." % GAP_MONTHLY,
        "T3: GBP excluida (el replay no tiene cuenta del gobierno). Ninguna sustitución.",
        "Rejilla acotada al último viernes cubierto por el FX de todas las divisas (%s); conviction.py la extiende hasta hoy." % fx_end,
        "Retorno residual = camino de conviction.py: antes de %d retornos completados en la era, el retorno es bruto. Se informa la fracción residualizada por test." % 52,
    ]}
    for name, key, h in TESTS:
        n_or_A, Zb, S = sig[key]
        ds, ic = ic_series(S, resid[h], grid)
        t = {"test": name, "signal": key, "h": h, "n_weeks": len(ic), "ccys": sorted(c for c in S if S[c]), "excluded": excluded if key == "govt_d13_pct" else [],
             "entry_week_by_ccy": {c: next((g for g in grid if n_or_A[c].get(g) is not None), None) for c in n_or_A}}
        if len(ic) < 30:
            t["status"] = "insufficient"; res["tests"].append(t); continue
        L = block_len(ic)
        bb = block_bootstrap_mean(ic, L)
        half = len(ic) // 2
        _, raw_ic = ic_series(S, ret[h], grid)
        ts = tercile_spread(S, resid[h], grid)
        t.update({"first": ds[0], "last": ds[-1], "ic": bb, "acf_ic": [round(x, 2) for x in acf(ic, 8)[1:]],
                  "ic_first_half": round(float(ic[:half].mean()), 4), "ic_second_half": round(float(ic[half:].mean()), 4),
                  "hit_rate": round(float(np.mean(ic > 0)), 3), "ic_raw_return": round(float(raw_ic.mean()), 4) if len(raw_ic) else None,
                  "resid_share": _resid_share(S, ret[h], resid[h], ds),
                  "tercile_spread_pct": block_bootstrap_mean(ts * 100, block_len(ts)) if len(ts) >= 30 else None})
        res["tests"].append(t)
    ps = [t["ic"]["p"] for t in res["tests"] if "ic" in t]
    qs = bh(ps) if ps else []
    k = 0
    for t in res["tests"]:
        if "ic" in t:
            t["q_bh"] = round(qs[k], 4); k += 1
            t["survives"] = bool(t["q_bh"] <= 0.05 and t["ic"]["mean"] > 0 and t["ic"]["ci95"][0] > 0 and t["ic_first_half"] > 0 and t["ic_second_half"] > 0)
    for key, (n_or_A, Zb, S) in sig.items():
        res["descriptives"][key] = {"signal_acf_lag13_by_ccy": _acf13_by_ccy(n_or_A, grid), "ranking_persistence_tau": _persistence(Zb, grid)}

    # consistencia con el brazo exploratorio de results.json (misma serie, mismo camino → debería coincidir)
    prev_path = os.path.join(out_dir, "results.json")
    if os.path.exists(prev_path):
        prev = json.load(open(prev_path)).get("secondary", {}).get("exploratory_smoothed_position", {})
        chk = {}
        for t in res["tests"]:
            e = prev.get("fi_mean13w_%d" % t["h"])
            if t["signal"] == "fi_mean13" and e and "ic" in t:
                chk[t["test"]] = {"ic_exploratory": e["mean"], "ic_here": t["ic"]["mean"], "n_exploratory": e["n"], "n_here": t["ic"]["n"], "match": abs(e["mean"] - t["ic"]["mean"]) < 5e-4 and e["n"] == t["ic"]["n"]}
        res["consistency_vs_exploratory"] = chk
    json.dump(res, open(os.path.join(out_dir, "T123.json"), "w"), indent=1, default=str)
    return res


def report(res: dict) -> str:
    L = ["# ICL — T1–T3, prerregistro definitivo (%s)\n" % res["design"],
         "Prerregistro (ronda 3 §3, escrito antes de mirar): familia BH de tres tests sobre el retorno residual (betas as-of de carry y canasta), "
         "bootstrap por bloques con longitud por la ACF de cada serie de IC, signo MMT (IC > 0). Aceptación: q ≤ 0,05, IC 95 %% sin cero, mitades del mismo signo. "
         "**Una sola mirada**: se corrió una vez, sin variantes ni segunda pasada. Rejilla %s → %s.\n" % (res["grid"][0], res["grid"][1]),
         "## Veredicto\n",
         "| test | medida | h (s) | semanas | IC medio | IC 95 % bootstrap | bloque | p boot | q BH | 1ª / 2ª mitad | sobrevive |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    lab = {"fi_mean13": "Tesoro: Φ⁻¹(pct as-of de la media 13 s del flujo fiscal)", "govt_d13_pct": "Tesoro fontanería: −Δ13 s cuenta del gobierno, % reservas"}
    for t in res["tests"]:
        if "ic" not in t:
            L.append("| %s | %s | %d | %d | insuficiente | | | | | | |" % (t["test"], lab[t["signal"]], t["h"], t["n_weeks"])); continue
        b = t["ic"]
        L.append("| %s | %s | %d | %d | %+.3f | [%+.3f, %+.3f] | %d | %.4f | %.4f | %+.3f / %+.3f | %s |" % (
            t["test"], lab[t["signal"]], t["h"], t["n_weeks"], b["mean"], b["ci95"][0], b["ci95"][1], b["block"], b["p"], t["q_bh"], t["ic_first_half"], t["ic_second_half"], "SÍ" if t["survives"] else "no"))
    L += ["\n## Descriptivos (no forman parte de la aceptación)\n",
          "| test | primera / última semana | hit | IC sin residualizar | fracción residualizada | tercil alto − bajo (% del cruce) | ACF de la serie de IC (1–4) | divisas |",
          "|---|---|---|---|---|---|---|---|"]
    for t in res["tests"]:
        if "ic" not in t:
            continue
        ts = t["tercile_spread_pct"]
        L.append("| %s | %s / %s | %.2f | %+.3f | %.2f | %s | %s | %s |" % (
            t["test"], t["first"], t["last"], t["hit_rate"], t["ic_raw_return"], t["resid_share"],
            "%+.2f [%+.2f, %+.2f]" % (ts["mean"], ts["ci95"][0], ts["ci95"][1]) if ts else "—", ", ".join("%+.2f" % x for x in t["acf_ic"][:4]), ", ".join(c.upper() for c in t["ccys"])))
    for key, d in res["descriptives"].items():
        L.append("\n- %s · ACF lag 13 de la señal por divisa: %s" % (key, " · ".join("%s %s" % (c.upper(), _f(v, 2)) for c, v in d["signal_acf_lag13_by_ccy"].items())))
        L.append("- %s · persistencia del ranking transversal (τ mediana t→t+k): %s" % (key, " · ".join("k %s: %s" % (k, _f(v)) for k, v in d["ranking_persistence_tau"].items())))
    for t in res["tests"]:
        L.append("- %s · entrada por divisa: %s%s" % (t["test"], ", ".join("%s %s" % (c.upper(), d) for c, d in t["entry_week_by_ccy"].items()), (" · excluidas: " + ", ".join(c.upper() for c in t["excluded"])) if t["excluded"] else ""))
    chk = res.get("consistency_vs_exploratory")
    if chk:
        L.append("\n## Consistencia con el brazo exploratorio de la ronda 1–2\n")
        for k, v in chk.items():
            L.append("- %s: exploratorio IC %+.3f (n %d) vs aquí %+.3f (n %d) → %s" % (k, v["ic_exploratory"], v["n_exploratory"], v["ic_here"], v["n_here"], "coincide" if v["match"] else "NO coincide"))
    L.append("\n## Desviaciones respecto al texto prerregistrado y supuestos\n")
    L += ["- " + d for d in res["deviations"]]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--fixtures-root", default=os.path.join(ROOT, "fixtures"))
    ap.add_argument("--out", default=os.path.join(ROOT, "calibration", "conviction"))
    a = ap.parse_args(argv)
    res = run(a.cache_dir, a.fixtures_root, a.out)
    txt = report(res)
    open(os.path.join(a.out, "T123.md"), "w").write(txt + "\n")
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
