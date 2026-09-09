"""Block score components — engine v0.3 (desk rule 2026-09-09, triangulation round 2).

Every central-bank / treasury block score is a combination of *flow* components (what changed: Δ reserves, net liquidity band,
fiscal impulse, take-up) and *level* components (where the stock sits: reserves vs range, phase, absorption share, OMO reliance,
structural deficit). The eight calibrations showed that level components pin a block in one state for a whole era, so v0.3
weights them separately: score = f(flows + level_weight × levels). level_weight comes from config `regime.dual.level_weight`
(default 1.0 = v0.2 arithmetic, bit-for-bit) and is calibrated by replay, never fixed by hand.

Three arithmetic modes reproduce the existing block formulas at level_weight 1.0:
  mean2    — CAD/GBP/AUD/JPY/USD/EUR style: clamp(sum(comps) / n × 2)
  sum      — CHF/NZD style: clamp(sum(comps))
  weighted — USD/EUR fiscal style: clamp(sum(w_i × comp_i))
The components are published in signals.components so the calibration can re-score any level_weight without a new replay."""
from __future__ import annotations
from typing import Dict, Optional

_CTX: Dict[str, Optional[float]] = {"level_weight": None}


def set_level_weight(lw: Optional[float]) -> None:
    """Session default (run.py / calibrate.py set it from config regime.dual.level_weight)."""
    _CTX["level_weight"] = lw


def level_weight(cfg: Optional[dict] = None) -> float:
    if cfg:
        lw = ((cfg.get("regime") or {}).get("dual") or {}).get("level_weight")
        if lw is not None:
            return float(lw)
    return 1.0 if _CTX["level_weight"] is None else float(_CTX["level_weight"])


class Comps:
    def __init__(self, cfg: Optional[dict], mode: str = "mean2", lo: float = -2.0, hi: float = 2.0, round_to: int = 2):
        self.mode, self.lo, self.hi, self.nd = mode, lo, hi, round_to
        self.lw = level_weight(cfg)
        self.flows: Dict[str, float] = {}
        self.levels: Dict[str, float] = {}
        self.weights: Dict[str, float] = {}

    def flow(self, name: str, v: float, w: float = 1.0) -> "Comps":
        self.flows[name] = float(v)
        self.weights[name] = w
        return self

    def level(self, name: str, v: float, w: float = 1.0) -> "Comps":
        self.levels[name] = float(v)
        self.weights[name] = w
        return self

    # events (emergency lending, CTRF, CLF, primary-credit panic) are flows: they describe a use of a facility in the window
    event = flow

    @staticmethod
    def _score(mode: str, flows: Dict[str, float], levels: Dict[str, float], weights: Dict[str, float], lw: float, lo: float, hi: float, nd: int) -> float:
        n = len(flows) + len(levels)
        if n == 0:
            return 0.0
        tot = sum(weights.get(k, 1.0) * v for k, v in flows.items()) + lw * sum(weights.get(k, 1.0) * v for k, v in levels.items())
        if mode == "mean2":
            s = tot / n * 2
        else:  # sum, weighted
            s = tot
        return round(max(lo, min(hi, s)), nd)

    def score(self, lw: Optional[float] = None) -> float:
        return self._score(self.mode, self.flows, self.levels, self.weights, self.lw if lw is None else lw, self.lo, self.hi, self.nd)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "level_weight": self.lw, "flow": dict(self.flows), "level": dict(self.levels),
                "weights": {k: w for k, w in self.weights.items() if w != 1.0}, "range": [self.lo, self.hi],
                "score_v02": self.score(1.0), "score_flows_only": self.score(0.0)}

    @staticmethod
    def rescore(d: dict, lw: float) -> float:
        """Re-score a published components dict at another level weight (calibration)."""
        lo, hi = d.get("range", [-2.0, 2.0])
        return Comps._score(d.get("mode", "mean2"), d.get("flow", {}), d.get("level", {}), d.get("weights", {}), lw, lo, hi, 2)
