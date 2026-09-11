"""ICL — prerregistro T4 (adjudicación «jefe de mesa: fontanería nacional», 2026-09-11, pregunta 2). Una mirada.

¿Aporta la aceleración del impulso fiscal algo sobre la velocidad? Velocidad V = señal de T1/T2 (Φ⁻¹ del percentil as-of de era de la
media 13 s del flujo fiscal, Z transversal, par vs USD). Aceleración A = V_t − V_{t−13} (dos trimestres disjuntos).

    Elección declarada: A se define sobre la Z transversal por divisa que alimenta los pares, A_i,t = Z_i,t − Z_i,t−13, y después se
    empareja vs USD exactamente como V (S^A_i = A_i − A_USD). Como el emparejamiento es lineal, S^A_i,t = S_i,t − S_i,t−13: es
    idénticamente la Δ13 s de la señal de pares de T1/T2.

Medida: IC transversal (Spearman) semanal del residuo de A sobre V — dentro de cada viernes, regresión por rangos de A sobre V entre las
divisas disponibles (con constante), residuo — contra el retorno residual adelantado (mismo camino que T1/T2). Horizontes 13 y 26 s,
bootstrap por bloques móviles con longitud por la ACF de la serie de IC, BH sobre los 2 tests. Aceptación: q ≤ 0,05, IC 95 % sin cero
(media > 0, lado MMT), mitades del mismo signo. Descriptivos: IC plano de A (sin parcializar) e IC de V en las mismas semanas.

    python -m ingest.conviction_t4 --cache-dir <dir con v03_<ccy>.pkl> [--out calibration/conviction]
"""
from __future__ import annotations
import argparse
import os
import json
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy import stats

from .conviction import CCYS, MIN_XS, ROOT, acf, bh, block_bootstrap_mean, block_len, cross_section, load_panel, ic_series, spearman_xs
from .conviction_t123 import WIN, _pairs, returns, signal_fi_mean13

DESIGN = "ICL T4 (prerregistro adjudicación fontanería 2026-09-11 §2; una mirada)"
LAG = 13                # semanas entre V_t y V_{t−13}
TESTS = (("T4-13", 13), ("T4-26", 26))


def accel(Z: Dict[str, Dict[str, float]], grid: List[str], lag: int = LAG) -> Dict[str, Dict[str, float]]:
    """A_i,t = Z_i,t − Z_i,t−lag por divisa; sólo donde ambas Z existen."""
    A = {c: {} for c in Z}
    for c in Z:
        for i in range(lag, len(grid)):
            a, b = Z[c].get(grid[i]), Z[c].get(grid[i - lag])
            if a is not None and b is not None:
                A[c][grid[i]] = a - b
    return A


def partial_ic_series(SA: Dict[str, Dict[str, float]], SV: Dict[str, Dict[str, float]], Y: Dict[str, Dict[str, Optional[float]]], grid: List[str]) -> Tuple[List[str], np.ndarray]:
    """Por viernes: residuo de rango(A) sobre rango(V) (OLS con constante) entre las divisas con A, V y retorno; Spearman del residuo vs Y."""
    ds, vals = [], []
    for g in grid:
        ks = [c for c in SA if SA[c].get(g) is not None and SV[c].get(g) is not None and Y[c].get(g) is not None]
        if len(ks) < MIN_XS:
            continue
        ra = stats.rankdata([SA[c][g] for c in ks]); rv = stats.rankdata([SV[c][g] for c in ks])
        X = np.column_stack([np.ones(len(ks)), rv])
        e = ra - X @ np.linalg.lstsq(X, ra, rcond=None)[0]
        r = spearman_xs(dict(zip(ks, e)), {c: Y[c][g] for c in ks})
        if r is not None:
            ds.append(g); vals.append(r)
    return ds, np.array(vals)


def run(cache_dir: str, fx_root: str, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    D = load_panel(cache_dir, fx_root)
    fx_end = min(D["ccy"][c]["fx"][-1][0] for c in CCYS)
    grid = [g for g in D["grid"] if g <= fx_end]
    ret, resid = returns(D, grid, (13, 26))

    n12 = signal_fi_mean13(D, grid)
    Z, _ = cross_section(n12, grid)
    SV = _pairs(Z, grid)
    A = accel(Z, grid)
    SA = _pairs(A, grid)

    res = {"design": DESIGN, "grid": [grid[0], grid[-1]], "lag": LAG, "n_boot_seed": "N_BOOT/SEED de conviction.py", "tests": [],
           "entry_week_by_ccy": {c: next((g for g in grid if A[c].get(g) is not None), None) for c in A},
           "deviations": [
               "A definida sobre la Z transversal por divisa (la misma que alimenta los pares de T1/T2), A_i,t = Z_i,t − Z_i,t−13, y emparejada vs USD como V; equivale exactamente a Δ13 s de la señal de pares S.",
               "IC parcial = Spearman del residuo semanal de rango(A) sobre rango(V) (OLS con constante entre las divisas con A, V y retorno; mínimo %d) contra el retorno residual. No es la fórmula cerrada de correlación parcial." % MIN_XS,
               "El IC plano de A y el IC de V de referencia se calculan sobre exactamente las semanas de la serie parcial de cada horizonte (mismo n).",
               "Retorno residual, rejilla (acotada al último viernes con FX de todas las divisas, %s) y señal V: mismo código que T1/T2 (conviction_t123)." % fx_end,
               "Sin variantes: un rezago (13 s), dos horizontes, una pasada.",
           ]}
    for name, h in TESTS:
        ds, ic = partial_ic_series(SA, SV, resid[h], grid)
        t = {"test": name, "h": h, "n_weeks": len(ic), "ccys": sorted(c for c in SA if SA[c])}
        if len(ic) < 30:
            t["status"] = "insufficient"; res["tests"].append(t); continue
        excl = set(grid) - set(ds)
        half = len(ic) // 2
        _, ic_a = ic_series(SA, resid[h], grid, exclude=excl)
        _, ic_v = ic_series(SV, resid[h], grid, exclude=excl)
        n_xs = [sum(1 for c in SA if SA[c].get(g) is not None and SV[c].get(g) is not None and resid[h][c].get(g) is not None) for g in ds]
        t.update({"first": ds[0], "last": ds[-1], "ic_partial": block_bootstrap_mean(ic, block_len(ic)),
                  "acf_ic": [round(x, 2) for x in acf(ic, 8)[1:]],
                  "ic_first_half": round(float(ic[:half].mean()), 4), "ic_second_half": round(float(ic[half:].mean()), 4),
                  "hit_rate": round(float(np.mean(ic > 0)), 3), "n_xs_mean": round(float(np.mean(n_xs)), 2),
                  "ic_plain_A": block_bootstrap_mean(ic_a, block_len(ic_a)),
                  "ic_V_same_weeks": block_bootstrap_mean(ic_v, block_len(ic_v))})
        res["tests"].append(t)
    ps = [t["ic_partial"]["p"] for t in res["tests"] if "ic_partial" in t]
    qs = bh(ps) if ps else []
    k = 0
    for t in res["tests"]:
        if "ic_partial" in t:
            b = t["ic_partial"]
            t["q_bh"] = round(qs[k], 4); k += 1
            t["survives"] = bool(t["q_bh"] <= 0.05 and b["mean"] > 0 and b["ci95"][0] > 0 and t["ic_first_half"] > 0 and t["ic_second_half"] > 0)
    json.dump(res, open(os.path.join(out_dir, "T4.json"), "w"), indent=1, default=str)
    return res


def report(res: dict) -> str:
    L = ["# ICL — T4, aceleración del impulso fiscal (%s)\n" % res["design"],
         "Prerregistro (adjudicación fontanería 2026-09-11, pregunta 2, escrito antes de mirar): A = V_t − V_{t−13} sobre la señal T1/T2; "
         "medida = IC transversal (Spearman) del residuo de A sobre V contra el retorno residual, horizontes 13 y 26 s, bootstrap por bloques "
         "(longitud por la ACF de la serie de IC), BH sobre 2. Aceptación: q ≤ 0,05, IC 95 %% sin cero (media > 0), mitades del mismo signo. "
         "**Una sola mirada**: una pasada, sin variantes. Prior adjudicado: probablemente **no** aporta. Rejilla %s → %s.\n" % (res["grid"][0], res["grid"][1]),
         "## Veredicto\n",
         "| test | h (s) | semanas | IC parcial medio | IC 95 % bootstrap | bloque | p boot | q BH | 1ª / 2ª mitad | sobrevive |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for t in res["tests"]:
        if "ic_partial" not in t:
            L.append("| %s | %d | %d | insuficiente | | | | | | |" % (t["test"], t["h"], t["n_weeks"])); continue
        b = t["ic_partial"]
        L.append("| %s | %d | %d | %+.3f | [%+.3f, %+.3f] | %d | %.4f | %.4f | %+.3f / %+.3f | %s |" % (
            t["test"], t["h"], t["n_weeks"], b["mean"], b["ci95"][0], b["ci95"][1], b["block"], b["p"], t["q_bh"], t["ic_first_half"], t["ic_second_half"], "SÍ" if t["survives"] else "no"))
    L += ["\n## Descriptivos (no forman parte de la aceptación)\n",
          "| test | primera / última semana | hit | IC plano de A (sin parcializar) | IC de V en las mismas semanas | divisas/semana | ACF de la serie de IC parcial (1–4) | divisas |",
          "|---|---|---|---|---|---|---|---|"]
    for t in res["tests"]:
        if "ic_partial" not in t:
            continue
        a, v = t["ic_plain_A"], t["ic_V_same_weeks"]
        L.append("| %s | %s / %s | %.2f | %+.3f [%+.3f, %+.3f] | %+.3f [%+.3f, %+.3f] | %.1f | %s | %s |" % (
            t["test"], t["first"], t["last"], t["hit_rate"], a["mean"], a["ci95"][0], a["ci95"][1], v["mean"], v["ci95"][0], v["ci95"][1],
            t["n_xs_mean"], ", ".join("%+.2f" % x for x in t["acf_ic"][:4]), ", ".join(c.upper() for c in t["ccys"])))
    L.append("\n- Entrada de A por divisa: " + ", ".join("%s %s" % (c.upper(), d) for c, d in res["entry_week_by_ccy"].items()))
    surv = [t for t in res["tests"] if t.get("survives")]
    L.append("\n## Consecuencia para el jefe de mesa v2\n")
    L.append("- " + ("La aceleración aporta sobre la velocidad en %s: la columna Tesoro puede llevar flecha de aceleración en ese horizonte." % ", ".join(t["test"] for t in surv)
                     if surv else "La aceleración **no** aporta información incremental sobre la velocidad en ningún horizonte: queda como detector binario de cambio de régimen (cruce por cero del flujo), no como regresor ni como flecha en la columna Tesoro."))
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
    open(os.path.join(a.out, "T4.md"), "w").write(txt + "\n")
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
