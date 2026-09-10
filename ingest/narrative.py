"""daily_log — the seven deterministic sentences (template 1.0, adjudicated 2026-09-09, round 3) built from the day's JSON.

Every number in the text is produced by fmt() and recorded in `numbers` (token, field path, raw value, precision), every
directional verb is chosen by the sign of the field it describes and recorded in `verbs`, every acronym is expanded on
first use from the currency glossary, and the regime label + streak come from regime.json and the agent ledger.
No HTTP, no interpolation, no invented values: a missing field produces the degraded variant of the sentence, never a guess.

Output: data/<ccy>/agent.json  {header, daily_log[F1..F7], numbers, verbs, glossary_used, degraded, ledger, jefe, gate}
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from . import jefe as J

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCKS = ("central_bank", "fiscal", "rates", "banking")
WINDOWS = {"daily": ("cinco sesiones", "veinte sesiones", 5, 20), "weekly": ("la semana", "cuatro semanas", 1, 4), "ten_day": ("la decena", "tres decenas", 1, 3), "monthly": ("el mes", "tres meses", 1, 3)}
REG_ES = {"INJECTION": "INYECCIÓN", "DRAIN": "DRENAJE", "NEUTRAL": "NEUTRAL", "NO DATA": "SIN DATO"}
GEN_ES = {"LIQUIDITY_INJECTION": "INYECCIÓN DE LIQUIDEZ", "LIQUIDITY_DRAIN": "DRENAJE DE LIQUIDEZ", "NEUTRAL": "NEUTRAL", "FLOOR_FRICTION": "FRICCIÓN DE SUELO", "LIQUIDITY_SCARCITY": "ESCASEZ DE LIQUIDEZ", "NO SIGNAL": "SIN SEÑAL"}
GEN_ENUM = set(GEN_ES)
BLOCK_ENUM = set(REG_ES)
FRESH_ES = {"fresh": "fresco", "stale": "stale", "proxy": "proxy", "unavailable": "no disponible", "degraded": "degradado"}

# ───────────────────────────── per-currency vocabulary (what each slot reads) ─────────────────────────────
# unit: divisor and display label for money amounts; bps/percent/ratio have their own formats.
SPEC: Dict[str, dict] = {
    "usd": {
        "cb": "Fed (Reserva Federal)", "tsy": "Tesoro de EE. UU.",
        "unit": (1000.0, "mm USD", 1), "glossary": {"WRESBAL": "Reserve Balances, saldos de reservas H.4.1", "TGA": "Treasury General Account, cuenta del Tesoro en la Reserva Federal", "MBS": "Mortgage-Backed Securities", "SOFR": "Secured Overnight Financing Rate", "IORB": "Interest on Reserve Balances", "NTF": "Net Treasury Flow, flujo neto del Tesoro con signo MMT", "DTS": "Daily Treasury Statement", "RRP": "Reverse Repo Facility a un día", "MMT": "Modern Monetary Theory", "BC": "banco central"},
        "reserves": ("central_bank", "series", "reserves", "las reservas bancarias (WRESBAL)", True),
        "portfolio": [("central_bank", "series", "treasury_securities", "Treasuries en cartera"), ("central_bank", "series", "mbs", "MBS")],
        "ops": [("central_bank", "series", "on_rrp", "RRP a un día", "stock"), ("central_bank", "series", "primary_credit", "crédito primario de la ventanilla", "stock")],
        "govt": ("central_bank", "series", "tga", "la TGA"),
        "fiscal": {"week": ("fiscal", "derived", "net_treasury_flow_7d", "7 sesiones"), "month": ("fiscal", "derived", "net_treasury_flow_mtd", "mes en curso"), "q13": ("fiscal", "derived", "ntf_60d", "60 sesiones"), "label": "flujo fiscal neto NTF"},
        "issuance": {"gross": ("fiscal", "series", "debt_issues"), "redemptions": ("fiscal", "series", "debt_redemptions"), "freq": "daily"},
        "auctions": [],
        "spread": ("rates", "derived", "sofr_minus_iorb_bps", "SOFR − IORB"), "friction": ("rates", "derived", "friction_confirmed"),
    },
    "eur": {
        "cb": "BCE (Banco Central Europeo)", "tsy": "Tesoros del área euro",
        "unit": (1000.0, "mm EUR", 1), "glossary": {"BCE": "Banco Central Europeo", "APP": "Asset Purchase Programme", "PEPP": "Pandemic Emergency Purchase Programme", "€STR": "Euro Short-Term Rate", "DFR": "Deposit Facility Rate, tipo de la facilidad de depósito", "MRO": "Main Refinancing Operations", "LTRO": "Longer-Term Refinancing Operations", "MMT": "Modern Monetary Theory", "BC": "banco central"},
        "reserves": ("central_bank", "series", "excess_liquidity", "el exceso de liquidez del Eurosistema", False),
        "portfolio": [("central_bank", "series", "monpol_securities", "valores de política monetaria en cartera")],
        "portfolio_monthly": [("central_bank", "derived", "app_pepp_total", "APP + PEPP"), ("central_bank", "series", "app_pepp_redemptions", "vencimientos APP + PEPP del mes", "flow")],
        "ops": [("central_bank", "series", "mro_weekly", "MRO", "stock"), ("central_bank", "series", "ltro_weekly", "LTRO", "stock")],
        "govt": ("fiscal", "series", "govt_deposits", "los depósitos de las administraciones en el Eurosistema"),
        "fiscal": {"week": ("fiscal", "derived", "govt_deposits_wow", "−Δ depósitos"), "month": ("fiscal", "derived", "fiscal_impulse_4w", "4 semanas"), "q13": ("fiscal", "derived", "fiscal_impulse_13w", "13 semanas"), "label": "impulso fiscal (−Δ depósitos públicos)", "week_sign": -1},
        "issuance": {"gross": ("fiscal", "derived", "de_supply_4w"), "redemptions": None, "freq": "event", "gross_label": "oferta alemana en subastas de 4 semanas"},
        "auctions": [("fiscal", "series", "de_auction_bid_to_cover", "Bund/Schatz: cobertura"), ("fiscal", "series", "de_auction_avg_yield", "rendimiento medio"), ("fiscal", "series", "de_auction_retention", "retención")],
        "spread": ("rates", "derived", "estr_minus_dfr_bps", "€STR − DFR"), "friction": ("rates", "derived", "friction_confirmed"),
    },
    "gbp": {
        "cb": "BoE (Bank of England)", "tsy": "HM Treasury / DMO (Debt Management Office)",
        "unit": (1000.0, "mm GBP", 1), "glossary": {"BoE": "Bank of England", "APF": "Asset Purchase Facility", "STR": "Short-Term Repo", "ILTR": "Indexed Long-Term Repo", "SONIA": "Sterling Overnight Index Average", "CGNCR": "Central Government Net Cash Requirement", "DMO": "Debt Management Office", "MMT": "Modern Monetary Theory", "BC": "banco central"},
        "reserves": ("central_bank", "series", "reserves", "las reservas bancarias en el BoE", True),
        "portfolio": [("central_bank", "series", "apf_loan", "préstamo al APF (cartera de gilts)")],
        "ops": [("central_bank", "series", "str_lending", "STR", "stock"), ("central_bank", "series", "ltr_lending", "ILTR", "stock")],
        "govt": None,
        "fiscal": {"week": None, "month": ("fiscal", "derived", "net_spending", "mes"), "q13": ("fiscal", "derived", "fiscal_flow_3m_cum", "3 meses"), "label": "gasto neto del gobierno central (CGNCR)", "monthly_only": True},
        "issuance": {"gross": ("fiscal", "derived", "tbill_issued"), "redemptions": ("fiscal", "derived", "tbill_matured"), "freq": "daily"},
        "auctions": [("fiscal", "derived", "tbill_cover", "tender de letras: cobertura"), ("central_bank", "derived", "iltr_cover", "ILTR: cobertura")],
        "spread": ("rates", "derived", "overnight_minus_policy_bps", "SONIA − Bank Rate"), "friction": ("rates", "derived", "overnight_minus_policy_bps", "friction_confirmed"),
    },
    "jpy": {
        "cb": "BoJ (Banco de Japón)", "tsy": "MoF (Ministerio de Finanzas)",
        "unit": (10000.0, "tn JPY", 2), "unit_small": "×100 mn JPY", "glossary": {"BoJ": "Banco de Japón", "MoF": "Ministerio de Finanzas", "CAB": "Current Account Balances, saldos en cuenta corriente en el Banco de Japón", "JGB": "Japanese Government Bond", "TONA": "Tokyo Overnight Average Rate", "IOER": "Interest on Excess Reserves", "MMT": "Modern Monetary Theory", "BC": "banco central"},
        "reserves": ("central_bank", "series", "cab_daily", "los saldos CAB en el BoJ", True),
        "portfolio": [("central_bank", "series", "jgb_holdings", "cartera de JGB")],
        "ops": [("central_bank", "series", "jgb_purchases_daily", "compras de JGB del día", "flow"), ("central_bank", "series", "slf_daily", "facilidad de préstamo de valores (SLF) del día", "flow")],
        "govt": ("fiscal", "series", "government_account", "los depósitos del gobierno en el BoJ"),
        "fiscal": {"week": ("fiscal", "derived", "fiscal_flow_5d_cum", "5 sesiones"), "month": ("fiscal", "derived", "fiscal_flow_20d_cum", "20 sesiones"), "q13": None, "label": "flujo de fondos del Tesoro (treasury funds, signo MMT)"},
        "issuance": {"gross": ("fiscal", "series", "jgb_issued_monthly"), "redemptions": ("fiscal", "series", "jgb_redeemed_monthly"), "freq": "monthly", "gross_sign": -1},
        "auctions": [("fiscal", "derived", "bid_to_cover_superlong", "superlargo: cobertura"), ("fiscal", "derived", "auction_tail_superlong_bp", "tail")],
        "spread": ("rates", "derived", "tona_minus_ioer_bps", "TONA − IOER"), "friction": ("rates", "derived", "friction_confirmed"),
    },
    "chf": {
        "cb": "SNB (Banco Nacional Suizo)", "tsy": "Confederación (Tesorería federal)",
        "unit": (1000.0, "mm CHF", 1), "glossary": {"SNB": "Banco Nacional Suizo", "SARON": "Swiss Average Rate Overnight", "MMDRC": "Money Market Debt Register Claims, letras de la Confederación", "MMT": "Modern Monetary Theory", "BC": "banco central"},
        "reserves": ("central_bank", "series", "sight_deposits_domestic_weekly", "los depósitos a la vista de bancos domésticos en el SNB", True),
        "portfolio": [],
        "portfolio_monthly": [("central_bank", "series", "fx_investments", "inversiones en divisas"), ("central_bank", "series", "snb_bills", "SNB Bills"), ("central_bank", "series", "absorbing_repos", "repos de absorción")],
        "ops": [("central_bank", "derived", "bills_maturing_week", "SNB Bills que vencen en la semana", "flow")],
        "govt": ("fiscal", "series", "amounts_due_to_confederation", "los saldos de la Confederación en el SNB"),
        "fiscal": {"week": None, "month": ("fiscal", "derived", "confed_cash_mom", "−Δ saldo"), "q13": None, "label": "flujo fiscal (−Δ saldos de la Confederación)", "monthly_only": True, "month_sign": -1},
        "issuance": {"gross": None, "redemptions": None, "freq": "monthly", "net": ("fiscal", "derived", "net_issuance_month")},
        "auctions": [("fiscal", "derived", "mmdrc_bid_to_cover", "MMDRC: cobertura"), ("fiscal", "derived", "mmdrc_yield_minus_saron_bps", "rendimiento − SARON"), ("fiscal", "derived", "bond_bid_to_cover", "bono: cobertura")],
        "spread": ("rates", "derived", "saron_minus_policy_bps", "SARON − tipo SNB"), "friction": ("rates", "derived", "friction_confirmed"),
    },
    "cad": {
        "cb": "BoC (Banco de Canadá)", "tsy": "Gobierno de Canadá (Receptor General)",
        "unit": (1000.0, "mm CAD", 1), "glossary": {"BoC": "Banco de Canadá", "CORRA": "Canadian Overnight Repo Rate Average", "MMT": "Modern Monetary Theory", "BC": "banco central"},
        "reserves": ("central_bank", "series", "reserves", "los saldos de liquidación en el BoC", True),
        "portfolio": [("central_bank", "series", "sovereign_bonds", "bonos del Gobierno de Canadá en cartera"), ("central_bank", "series", "bills", "letras en cartera")],
        "ops": [("central_bank", "series", "liquidity_repos", "repos de liquidez a plazo", "stock")],
        "govt": ("central_bank", "series", "government_account", "la cuenta del Receptor General en el BoC"),
        "fiscal": {"week": ("fiscal", "derived", "fiscal_flow_7d_cum", "7 días"), "month": None, "q13": None, "label": "flujo fiscal proxy (−Δ cuenta del gobierno)"},
        "issuance": {"gross": ("fiscal", "derived", "issued_private"), "redemptions": ("fiscal", "derived", "matured_private"), "freq": "daily"},
        "auctions": [("fiscal", "derived", "rg_am_coverage", "subasta matinal del Receptor General: cobertura")],
        "spread": ("rates", "derived", "overnight_minus_policy_bps", "CORRA − tipo objetivo"), "friction": None,
    },
    "aud": {
        "cb": "RBA (Reserve Bank of Australia)", "tsy": "Tesoro australiano / AOFM (Australian Office of Financial Management)",
        "unit": (1000.0, "mm AUD", 1), "glossary": {"RBA": "Reserve Bank of Australia", "ES": "Exchange Settlement, saldos de liquidación", "OMO": "operaciones de mercado abierto", "AOFM": "Australian Office of Financial Management", "MMT": "Modern Monetary Theory", "BC": "banco central"},
        "reserves": ("central_bank", "series", "es_balances_daily", "los saldos ES en el RBA", True),
        "portfolio": [("central_bank", "series", "aud_investments", "inversiones en AUD en cartera")],
        "ops": [("central_bank", "derived", "omo_outstanding", "OMO vivas", "stock")],
        "govt": ("central_bank", "series", "government_account", "la cuenta del gobierno en el RBA"),
        "fiscal": {"week": ("fiscal", "derived", "fiscal_flow_weekly", "semana"), "month": ("fiscal", "derived", "fiscal_flow_4w_cum", "4 semanas"), "q13": None, "label": "flujo fiscal (−Δ cuenta del gobierno)"},
        "issuance": {"gross": None, "redemptions": None, "freq": "none"},
        "auctions": [],
        "spread": ("rates", "derived", "overnight_minus_target_bps", "cash rate − objetivo"), "friction": ("rates", "derived", "overnight_minus_target_bps", "friction_confirmed"),
    },
    "nzd": {
        "cb": "RBNZ (Reserve Bank of New Zealand)", "tsy": "Tesoro neozelandés / NZDM (New Zealand Debt Management)",
        "unit": (1000.0, "mm NZD", 1), "glossary": {"RBNZ": "Reserve Bank of New Zealand", "OCR": "Official Cash Rate", "OMO": "operaciones de mercado abierto", "LSAP": "Large Scale Asset Purchases", "NZDM": "New Zealand Debt Management", "MMT": "Modern Monetary Theory", "BC": "banco central"},
        "reserves": ("central_bank", "series", "settlement_cash_daily", "el settlement cash en el RBNZ", False),
        "portfolio": [],
        "portfolio_monthly": [("central_bank", "series", "lsap_holdings", "cartera LSAP"), ("central_bank", "series", "lsap_sales_month", "ventas LSAP del mes", "flow")],
        "ops": [("central_bank", "series", "omo_outstanding", "OMO vivas", "stock")],
        "govt": ("fiscal", "series", "crown_settlement_account", "la cuenta de la Corona en el RBNZ"),
        "fiscal": {"week": ("central_bank", "derived", "residual_flow_5d_cum", "5 sesiones, proxy residual"), "month": ("central_bank", "derived", "residual_flow_20d_cum", "20 sesiones, proxy residual"), "q13": ("fiscal", "derived", "govt_cash_influence", "mes, influencia de caja del gobierno"), "label": "flujo fiscal (proxy residual del settlement cash)"},
        "issuance": {"gross": ("fiscal", "derived", "tender_settled"), "redemptions": ("fiscal", "derived", "bill_matured"), "freq": "daily"},
        "auctions": [("fiscal", "derived", "bond_bid_to_cover", "bono: cobertura"), ("fiscal", "derived", "bond_tail_bp", "tail"), ("fiscal", "derived", "tbill_bid_to_cover", "letra: cobertura"), ("fiscal", "derived", "tbill_yield_minus_ocr_bps", "rendimiento − OCR")],
        "spread": ("rates", "derived", "overnight_interbank_minus_ocr_bps", "interbancario a un día − OCR"), "friction": ("rates", "derived", "friction_confirmed"),
    },
}


# ───────────────────────────── formatting (every number goes through here) ─────────────────────────────
class Ledger:
    """Records every numeric token and every directional verb emitted, for the anti-invention gate."""

    def __init__(self):
        self.numbers: List[dict] = []
        self.verbs: List[dict] = []
        self.glossary: List[str] = []
        self.degraded: List[str] = []

    def num(self, value: float, field: str, kind: str, unit: str = "", decimals: Optional[int] = None) -> str:
        tok = _fmt(value, kind, decimals)
        self.numbers.append({"token": tok, "field": field, "value": value, "kind": kind, "unit": unit})
        return tok

    def verb(self, sign: float, pos: str, neg: str, zero: str, field: str) -> str:
        w = pos if sign > 0 else neg if sign < 0 else zero
        self.verbs.append({"verb": w, "sign": 1 if sign > 0 else -1 if sign < 0 else 0, "field": field})
        return w


def _es(s: str) -> str:
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _fmt(v: float, kind: str, decimals: Optional[int] = None) -> str:
    """Spanish number format; the decimals grow until a non-zero value does not round to zero (no rounding across zero)."""
    d = decimals if decimals is not None else {"money": 1, "bps": 1, "pct": 2, "ratio": 2, "rate": 3, "int": 0}.get(kind, 2)
    while d < 4 and v != 0 and round(v, d) == 0:
        d += 1
    s = ("{:,.%df}" % d).format(v)
    s = _es(s)
    if v < 0:
        s = "−" + s.lstrip("-")
    return s


def _get(blocks: dict, path: Optional[tuple]) -> Optional[dict]:
    if not path:
        return None
    b, sec, key = path[0], path[1], path[2]
    e = (blocks.get(b) or {}).get(sec, {}).get(key)
    return e if isinstance(e, dict) else None


def _delta(e: dict, n: int) -> Optional[float]:
    sp = e.get("sparkline") or []
    if len(sp) > n and sp[-1] is not None and sp[-1 - n] is not None:
        return float(sp[-1]) - float(sp[-1 - n])
    return None


def _money(L: Ledger, v: float, spec: dict, field: str, signed: bool = True) -> str:
    div, unit, dec = spec["unit"]
    if v != 0 and abs(v / div) < 0.05:  # below the display resolution: print the source unit instead of adding decimals
        unit = spec.get("unit_small", "mn " + unit.split(" ")[-1])
        tok = L.num(v, field, "money", unit, 0)
        if signed and v > 0:
            tok = "+" + tok
        return "%s %s" % (tok, unit)
    tok = L.num(v / div, field, "money", unit, dec)
    if signed and v > 0:
        tok = "+" + tok
    return "%s %s" % (tok, unit)


def _freq(e: dict) -> str:
    f = (e or {}).get("frequency") or "weekly"
    return f if f in WINDOWS else "weekly"


def _ordinal(n: int, L: Optional["Ledger"] = None, field: str = "streak") -> str:
    if L is not None:
        return L.num(n, field, "int") + ".ª"
    return "%d.ª" % n


# ───────────────────────────── the seven sentences ─────────────────────────────
def header(blocks: dict) -> Tuple[str, dict]:
    parts, meta = [], {}
    names = {"central_bank": "BC", "fiscal": "Tesoro", "rates": "tipos", "banking": "banca"}
    for b in BLOCKS:
        blk = blocks.get(b)
        if not blk:
            continue
        st = (blk.get("source_health") or {}).get("status", "unavailable")
        meta[b] = {"as_of": blk.get("as_of"), "status": st}
        parts.append("%s: as-of %s, %s" % (names[b], blk.get("as_of"), FRESH_ES.get(st, st)))
    latest = max([m["as_of"] for m in meta.values() if m.get("as_of")] or ["—"])
    return "Datos hasta %s (%s)." % (latest, "; ".join(parts)), meta


def f1_reserves(ccy: str, blocks: dict, regime: dict, streak: int, L: Ledger, spec: dict) -> str:
    e = _get(blocks, spec["reserves"])
    label = spec["reserves"][3]
    fld = ".".join(spec["reserves"][:3])
    reg = (regime.get("regimes", {}).get("central_bank") or {}).get("regime", "NO DATA")
    if not e or e.get("value") is None:
        L.degraded.append("F1: reserves unavailable")
        return "F1. %s: sin dato publicado en el JSON de hoy; régimen del BC %s (%s lectura consecutiva)." % (label.capitalize(), REG_ES.get(reg, reg), _ordinal(streak, L, "streaks.central_bank"))
    fq = _freq(e)
    w1, w2, n1, n2 = WINDOWS[fq]
    d1, d2 = _delta(e, n1), _delta(e, n2)
    div, unit, dec = spec["unit"]
    lvl = L.num(e["value"] / div, fld + ".value", "money", unit, dec)
    s = "F1. %s" % label[0].upper() + label[1:]
    if d1 is None:
        L.degraded.append("F1: short history (%s)" % fq)
        s += " están en %s %s (%s); variación no calculable con la historia publicada" % (lvl, unit, e.get("date"))
    else:
        plural = spec["reserves"][4]
        v = L.verb(d1, "subieron" if plural else "subió", "cayeron" if plural else "cayó", "no variaron" if plural else "no varió", fld + ".delta_%d" % n1)
        s += " %s %s en %s" % (v, _money(L, d1, spec, fld + ".delta_%d" % n1), w1)
        if d2 is not None:
            s += " y %s en %s" % (_money(L, d2, spec, fld + ".delta_%d" % n2), w2)
        s += ", hasta %s %s (%s)" % (lvl, unit, e.get("date"))
    st = (regime.get("regimes", {}).get("central_bank") or {}).get("state") or {}
    s += "; régimen del BC: %s, %s lectura consecutiva" % (REG_ES.get(reg, reg), _ordinal(streak, L, "streaks.central_bank"))
    if st.get("candidate") and st.get("candidate") != reg:
        s += " (candidato %s desde %s, pendiente %s días)" % (REG_ES.get(st["candidate"], st["candidate"]), st.get("candidate_since"), L.num(st.get("pending_days") or 0, "regime.central_bank.state.pending_days", "int"))
    return s + "."


def f2_portfolio(ccy: str, blocks: dict, L: Ledger, spec: dict) -> str:
    parts = []
    for b, sec, key, label in spec.get("portfolio", []):
        e = _get(blocks, (b, sec, key))
        if not e or e.get("value") is None:
            continue
        fq = _freq(e)
        d = _delta(e, WINDOWS[fq][2])
        fld = "%s.%s.%s" % (b, sec, key)
        if d is None:
            parts.append("%s: stock %s (%s), variación no calculable" % (label, _money(L, e["value"], spec, fld + ".value", signed=False), e.get("date")))
            continue
        v = L.verb(d, "creció", "cayó", "no varió", fld + ".delta")
        parts.append("%s %s %s en %s (%s)" % (label, v, _money(L, d, spec, fld + ".delta"), WINDOWS[fq][0], e.get("date")))
    for item in spec.get("portfolio_monthly", []):
        b, sec, key, label = item[:4]
        e = _get(blocks, (b, sec, key))
        if not e or e.get("value") is None:
            continue
        fld = "%s.%s.%s" % (b, sec, key)
        if len(item) > 4 and item[4] == "flow":
            parts.append("%s: %s (%s); atribución semanal no publicada por la fuente" % (label, _money(L, e["value"], spec, fld + ".value", signed=False), e.get("date")))
            L.degraded.append("F2: monthly flow only (%s)" % key)
            continue
        d = _delta(e, 1)
        txt = "%s: stock de %s %s" % (label, e.get("date"), _money(L, e["value"], spec, fld + ".value", signed=False))
        if d is not None:
            txt += ", %s en el mes" % _money(L, d, spec, fld + ".delta_1")
        parts.append(txt + "; atribución semanal no publicada por la fuente")
        L.degraded.append("F2: monthly stock only (%s)" % key)
    for b, sec, key, label, kind in spec.get("ops", []):
        e = _get(blocks, (b, sec, key))
        if not e or e.get("value") is None:
            continue
        fld = "%s.%s.%s" % (b, sec, key)
        if kind == "flow":
            parts.append("%s: %s (%s)" % (label, _money(L, e["value"], spec, fld + ".value"), e.get("date")))
        else:
            d = _delta(e, WINDOWS[_freq(e)][2])
            txt = "%s: %s vivos" % (label, _money(L, e["value"], spec, fld + ".value", signed=False))
            if d is not None:
                txt += " (%s en %s)" % (_money(L, d, spec, fld + ".delta"), WINDOWS[_freq(e)][0])
            parts.append(txt)
    if not parts:
        L.degraded.append("F2: no portfolio/operations fields")
        return "F2. Cartera y operaciones del BC: la fuente no publica flujo ni stock en el JSON de hoy."
    return "F2. Cartera y operaciones del %s — %s." % (spec["cb"], "; ".join(parts))


def f3_treasury(ccy: str, blocks: dict, regime: dict, streak: int, L: Ledger, spec: dict) -> str:
    fi = spec["fiscal"]
    reg = (regime.get("regimes", {}).get("fiscal") or {}).get("regime", "NO DATA")
    parts = []
    g = _get(blocks, spec["govt"]) if spec.get("govt") else None
    if g and g.get("value") is not None:
        fld = ".".join(spec["govt"][:3])
        fq = _freq(g)
        d = _delta(g, WINDOWS[fq][2])
        if d is not None:
            v = L.verb(d, "subió", "bajó", "no varió", fld + ".delta")
            eff = L.verb(-d, "alimenta", "drena", "no mueve", fld + ".reserve_effect")
            parts.append("%s %s %s en %s, hasta %s (%s): este flujo %s las reservas del sistema" % (spec["govt"][3][0].upper() + spec["govt"][3][1:], v, _money(L, d, spec, fld + ".delta"), WINDOWS[fq][0], _money(L, g["value"], spec, fld + ".value", signed=False), g.get("date"), eff))
        else:
            parts.append("%s: %s (%s), variación no calculable" % (spec["govt"][3], _money(L, g["value"], spec, fld + ".value", signed=False), g.get("date")))
    else:
        L.degraded.append("F3: government account not in JSON")
        parts.append("cuenta del gobierno en el BC: no publicada en el JSON de hoy")
    fl = []
    for k, name in (("week", "semana"), ("month", "mes"), ("q13", "trimestre móvil")):
        path = fi.get(k)
        e = _get(blocks, path) if path else None
        if e and e.get("value") is not None:
            sign = fi.get(k + "_sign", 1)
            fld = ".".join(path[:3])
            win = "" if path[3] in (name, "mes en curso") and name != "trimestre móvil" else " (%s)" % path[3]
            fl.append("%s%s %s" % (name, win, _money(L, sign * e["value"], spec, fld + ".value" + (".neg" if sign < 0 else ""))))
        elif path is None:
            fl.append("%s: no publicado por la fuente" % name)
    if fi.get("monthly_only"):
        L.degraded.append("F3: monthly fiscal series only")
    parts.append("%s: %s" % (fi["label"], ", ".join(fl)))
    parts.append("régimen del Tesoro: %s, %s lectura consecutiva" % (REG_ES.get(reg, reg), _ordinal(streak, L, "streaks.fiscal")))
    return "F3. %s — %s." % (spec["tsy"], "; ".join(parts))


def f4_issuance(ccy: str, blocks: dict, L: Ledger, spec: dict) -> str:
    iss = spec["issuance"]
    parts = []
    gross = _get(blocks, iss.get("gross")) if iss.get("gross") else None
    red = _get(blocks, iss.get("redemptions")) if iss.get("redemptions") else None
    if iss.get("net"):
        n = _get(blocks, iss["net"])
        if n and n.get("value") is not None:
            parts.append("emisión neta del mes %s (%s)" % (_money(L, n["value"], spec, ".".join(iss["net"][:3]) + ".value"), n.get("date")))
    if gross and gross.get("value") is not None:
        gs = iss.get("gross_sign", 1)
        fq = iss.get("freq", "daily")
        gf = ".".join(iss["gross"][:3])
        if fq == "daily":
            sp_g, sp_r = gross.get("sparkline") or [], (red or {}).get("sparkline") or []
            if len(sp_g) >= 5 and red and len(sp_r) >= 5 and None not in sp_g[-5:] + sp_r[-5:]:
                g5, r5 = sum(sp_g[-5:]), sum(sp_r[-5:])
                parts.append("emisión bruta de cinco sesiones %s, vencimientos %s, neta %s (%s)" % (_money(L, g5, spec, gf + ".sum5", signed=False), _money(L, r5, spec, ".".join(iss["redemptions"][:3]) + ".sum5", signed=False), _money(L, g5 - r5, spec, gf + ".net5"), gross.get("date")))
            else:
                parts.append("emisión bruta del día %s (%s)" % (_money(L, gross["value"], spec, gf + ".value", signed=False), gross.get("date")))
        elif red and red.get("value") is not None:
            gv, rv = gs * gross["value"], abs(red["value"])
            parts.append("emisión bruta %s %s, vencimientos %s, neta %s" % (iss.get("gross_label", "del mes"), _money(L, gv, spec, gf + ".value", signed=False), _money(L, rv, spec, ".".join(iss["redemptions"][:3]) + ".value", signed=False), _money(L, gv - rv, spec, gf + ".net")))
        else:
            parts.append("%s %s (%s); vencimientos no publicados por la fuente; emisión neta no calculable" % (iss.get("gross_label", "emisión bruta"), _money(L, gs * gross["value"], spec, gf + ".value", signed=False), gross.get("date")))
            L.degraded.append("F4: no redemptions")
    elif not iss.get("net"):
        parts.append("emisión y vencimientos: no publicados en el JSON de hoy; emisión neta no calculable")
        L.degraded.append("F4: no issuance fields")
    au = []
    for b, sec, key, label in spec.get("auctions", []):
        e = _get(blocks, (b, sec, key))
        if not e or e.get("value") is None:
            continue
        fld = "%s.%s.%s" % (b, sec, key)
        u = (e.get("unit") or "").lower()
        kind = ("ratio" if any(t in key for t in ("bid_to_cover", "coverage", "btc")) else "bps" if ("bp" in key or "bp" in u) else "pct" if "retention" in key else
                "rate" if "yield" in key else "ratio" if u in ("x", "ratio") else "pct" if "%" in u else "rate")
        tok = L.num(e["value"], fld + ".value", kind, u)
        suffix = {"bps": " pb", "ratio": "×", "pct": " %", "rate": " %"}[kind]
        lvl = e.get("level")
        au.append("%s %s%s (%s%s)" % (label, tok, suffix, e.get("date"), ", %s" % lvl if lvl in ("WATCH", "STRESS", "CRISIS") else ", sin señal"))
    if au:
        parts.append("subastas: " + ", ".join(au))
    else:
        parts.append("subastas: sin resultado en el JSON de hoy")
    return "F4. Emisión y subastas — %s." % "; ".join(parts)


MECHANISM = {
    ("DRAIN", "INJECTION"): "el Tesoro inyecta y el BC drena: el BC compensa el impulso fiscal",
    ("INJECTION", "DRAIN"): "el Tesoro drena y el BC no compensa hacia abajo: el BC inyecta contra el drenaje fiscal",
    ("DRAIN", "DRAIN"): "el Tesoro drena y el BC drena: los dos brazos retiran reservas",
    ("INJECTION", "INJECTION"): "el Tesoro inyecta y el BC inyecta: los dos brazos añaden reservas",
    ("DRAIN", "NEUTRAL"): "el Tesoro está neutro y el BC drena: el drenaje viene del BC",
    ("INJECTION", "NEUTRAL"): "el Tesoro está neutro y el BC inyecta: la inyección viene del BC",
    ("NEUTRAL", "DRAIN"): "el Tesoro drena y el BC no compensa: el drenaje viene del Tesoro",
    ("NEUTRAL", "INJECTION"): "el Tesoro inyecta y el BC no compensa: la inyección viene del Tesoro",
    ("NEUTRAL", "NEUTRAL"): "ni el Tesoro ni el BC mueven las reservas fuera de su banda de era",
}


def f5_regime(ccy: str, regime: dict, streak: int, L: Ledger, spec: dict) -> Tuple[str, str]:
    R = regime.get("regimes", {})
    g = R.get("general") or {}
    label = g.get("regime") or regime.get("regime") or "NO SIGNAL"
    cb = (R.get("central_bank") or {}).get("regime", "NO DATA")
    fi = (R.get("fiscal") or {}).get("regime", "NO DATA")
    mech = MECHANISM.get((cb, fi), "sin lectura de mecanismo: falta el régimen de un bloque")
    s = "F5. Régimen general del motor: %s (%s lectura consecutiva); %s" % (GEN_ES.get(label, label), _ordinal(streak, L, "streaks.general"), mech)
    gate = g.get("price_gate")
    if gate:
        s += "; puerta de precio activa (reservas amplias y fricción confirmada)"
    else:
        s += "; puerta de precio no activa"
    era = g.get("era_weeks")
    if era is not None:
        s += "; cortes de era de %s semanas" % L.num(era, "regime.general.era_weeks", "int")
    return s + ".", label


def f6_price(ccy: str, blocks: dict, L: Ledger, spec: dict) -> str:
    e = _get(blocks, spec["spread"])
    if not e or e.get("value") is None:
        L.degraded.append("F6: spread unavailable")
        return "F6. Precio del dinero: el spread %s no está publicado en el JSON de hoy." % spec["spread"][3]
    fld = ".".join(spec["spread"][:3])
    tok = L.num(e["value"], fld + ".value", "bps", "bps")
    lvl = e.get("level") or "—"
    fr = None
    if spec.get("friction"):
        p = spec["friction"]
        fe = _get(blocks, p[:3])
        if fe is not None:
            fr = fe.get(p[3]) if len(p) > 3 else fe.get("value")
    fr_txt = "fricción confirmada" if fr is True else "fricción no confirmada" if fr is False else "fricción: sin cálculo publicado"
    if fr is None:
        L.degraded.append("F6: friction flag missing")
    v = L.verb(e["value"], "por encima", "por debajo", "al nivel", fld + ".sign")
    return "F6. Precio del dinero: %s %s pb (%s), el mercado paga %s del tipo del BC; %s. Confirma, no determina." % (spec["spread"][3], tok, lvl, v, fr_txt)


def f7_jefe(ccy: str, jefe: dict, L: Ledger, spec: dict) -> str:
    if not jefe or jefe.get("status") != "ok":
        L.degraded.append("F7: jefe unavailable")
        return "F7. Jefe de mesa: ranking transversal no calculable hoy (%s)." % (jefe or {}).get("reason", "sin panel")
    me = ccy.upper()
    items = []
    for r in jefe["ranking"]:
        items.append("%s %s %s %% (Z %s)" % (L.num(r["rank"], "jefe.ranking.%s.rank" % r["ccy"], "int"), r["ccy"], L.num(r["d13_pct"], "jefe.ranking.%s.d13_pct" % r["ccy"], "pct", "%", 1), L.num(r["z"], "jefe.ranking.%s.z" % r["ccy"], "pct", "Z", 2)))
    mine = next((r for r in jefe["ranking"] if r["ccy"] == me), None)
    s = "F7. Jefe de mesa (viernes %s; Δ13 semanas de reservas del BC en %% del stock, Z transversal; %s): %s" % (jefe["as_of_friday"], jefe["label"], "; ".join(items))
    if mine:
        pos = L.num(mine["rank"], "jefe.ranking.%s.rank" % me, "int")
        s += ". %s ocupa la posición %s de %s" % (me, pos, L.num(jefe["n"], "jefe.n", "int"))
        if mine.get("rank_prev_week"):
            s += " (semana anterior %s)" % L.num(mine["rank_prev_week"], "jefe.ranking.%s.rank_prev_week" % me, "int")
    else:
        s += ". %s no entra en el ranking de hoy (sin dato de reservas en la rejilla)" % me
        L.degraded.append("F7: own currency missing")
    pm = jefe.get("pair_max_conviction")
    if pm:
        s += "; par con más convicción relativa por la pata BC: %s (más reservas) frente a %s (más drenaje), brecha Z %s" % (pm["reserves_growth"], pm["reserves_drain"], L.num(pm["z_gap"], "jefe.pair_max_conviction.z_gap", "pct", "Z", 2))
    if jefe.get("low_dispersion"):
        s += "; dispersión transversal baja (σ semanal %s < p20 de la era %s)" % (L.num(jefe["sigma_week"], "jefe.sigma_week", "pct", "σ", 3), L.num(jefe["sigma_week_p20_era"], "jefe.sigma_week_p20_era", "pct", "σ", 3))
    if jefe.get("missing"):
        s += "; fuera del ranking: %s" % ", ".join(jefe["missing"])
    return s + "; sin par neto hasta T1–T3."


# ───────────────────────────── glossary expansion (first use per text) ─────────────────────────────
def expand_acronyms(text: str, glossary: Dict[str, str], L: Ledger) -> str:
    seen = set()
    for ac in sorted(glossary, key=len, reverse=True):
        pat = re.compile(r"(?<![\w€])" + re.escape(ac) + r"(?![\w])")
        m = pat.search(text)
        if m and ac not in seen:
            # skip if already followed by a parenthesis (the spec's own expansions, e.g. "Fed (Reserva Federal)")
            after = text[m.end(): m.end() + 2]
            if after.startswith(" ("):
                seen.add(ac)
                L.glossary.append(ac)
                continue
            text = text[: m.end()] + " (%s)" % glossary[ac] + text[m.end():]
            seen.add(ac)
            L.glossary.append(ac)
    return text


# ───────────────────────────── streak ledger ─────────────────────────────
def update_ledger(prev: Optional[dict], regime: dict, blocks: dict) -> Tuple[dict, Dict[str, int]]:
    led = dict((prev or {}).get("ledger") or {})
    R = regime.get("regimes", {})
    entries = {"central_bank": ((R.get("central_bank") or {}).get("as_of") or blocks.get("central_bank", {}).get("as_of"), (R.get("central_bank") or {}).get("regime")),
               "fiscal": ((R.get("fiscal") or {}).get("as_of") or blocks.get("fiscal", {}).get("as_of"), (R.get("fiscal") or {}).get("regime")),
               "general": (regime.get("as_of"), (R.get("general") or {}).get("regime") or regime.get("regime"))}
    streaks = {}
    for k, (d, reg) in entries.items():
        seq = [tuple(x) for x in led.get(k, [])]
        if d and reg:
            if seq and seq[-1][0] == d:
                seq[-1] = (d, reg)
            elif not seq or seq[-1][0] < d:
                seq.append((d, reg))
        seq = seq[-260:]
        led[k] = [list(x) for x in seq]
        n = 0
        for x in reversed(seq):
            if x[1] == reg:
                n += 1
            else:
                break
        streaks[k] = max(n, 1)
    return led, streaks


# ───────────────────────────── build ─────────────────────────────
def build(ccy: str, blocks: dict, regime: dict, prev_agent: Optional[dict], jefe: Optional[dict], calendar: Optional[dict] = None, alerts: Optional[dict] = None) -> dict:
    spec = SPEC[ccy]
    L = Ledger()
    led, streaks = update_ledger(prev_agent, regime, blocks)
    head, meta = header(blocks)
    F = [f1_reserves(ccy, blocks, regime, streaks["central_bank"], L, spec),
         f2_portfolio(ccy, blocks, L, spec),
         f3_treasury(ccy, blocks, regime, streaks["fiscal"], L, spec),
         f4_issuance(ccy, blocks, L, spec)]
    f5, glabel = f5_regime(ccy, regime, streaks["general"], L, spec)
    F += [f5, f6_price(ccy, blocks, L, spec), f7_jefe(ccy, jefe, L, spec)]
    text = expand_acronyms("\n".join([head] + F), spec["glossary"], L)
    lines = text.split("\n")
    upcoming = [{"date": x.get("date"), "type": x.get("type"), "title": x.get("title")} for x in (calendar or {}).get("upcoming", [])[:5]]
    active = [{"rule_id": a.get("rule_id"), "severity": a.get("severity"), "metric": a.get("metric")} for a in (alerts or {}).get("alerts", []) if a.get("status") == "active"][:10]
    out = {"currency": ccy.upper(), "template": "1.0 (ronda 3, 2026-09-09)", "generated_at": regime.get("generated_at"), "as_of": regime.get("as_of"),
           "regime": glabel, "regime_enum": sorted(GEN_ENUM), "block_regime_enum": sorted(BLOCK_ENUM),
           "header": lines[0], "daily_log": {"F%d" % (i + 1): lines[i + 1] for i in range(7)}, "narrative": "\n".join(lines),
           "streaks": streaks, "ledger": led, "numbers": L.numbers, "verbs": L.verbs, "glossary_used": L.glossary, "glossary": spec["glossary"],
           "degraded": L.degraded, "blocks_meta": meta, "calendar_next": upcoming, "alerts_active": active,
           "jefe": {k: v for k, v in (jefe or {}).items() if k != "ranking"} | {"ranking": (jefe or {}).get("ranking")} if jefe else None,
           "structural": sorted({p[3] for p in [spec["fiscal"].get(k) for k in ("week", "month", "q13")] if p} | {spec["issuance"].get("gross_label", "")} - {""}),
           "prohibitions": PROHIBITIONS, "closing_rules": CLOSING_RULES}
    out["hash"] = hashlib.sha256(out["narrative"].encode("utf-8")).hexdigest()[:16]
    out["operator_takeaway"] = None  # the model's 2–3 closing lines go here (no digits except the calendar); the engine never writes them
    return out


PROHIBITIONS = ["compra/venta o posición", "objetivo de precio", "probabilidad o confianza numérica", "número, fecha, entidad o nombre propio fuera del JSON del día",
                "mecanismo que contradiga el signo del dato", "causalidad de eventos que no estén en el JSON", "predicción de decisiones de política", "proyección de valores futuros",
                "intencionalidad del banco central (busca, pretende)", "adjetivos de magnitud sin percentil o Z (masivo, fuerte)", "vínculos con inflación, empleo o PIB",
                "comparaciones entre divisas fuera de F7", "redondeo que cruce cero o un ancla", "las palabras «señal» y «recomendación» en el cierre"]
CLOSING_RULES = "Cierre del modelo, 2–3 líneas, sin cifras salvo fechas del calendario: qué cambió respecto a ayer (ledger/streaks), qué vigilar mañana (calendar_next), aviso stale/proxy/degradado (blocks_meta, degraded)."


def load(ccy: str, root: str = ROOT) -> Tuple[dict, dict, Optional[dict], Optional[dict], Optional[dict]]:
    d = os.path.join(root, "data", ccy)

    def rj(name):
        p = os.path.join(d, name + ".json")
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None

    blocks = {b: rj(b) for b in BLOCKS if rj(b)}
    return blocks, rj("regime") or {}, rj("agent"), rj("calendar"), rj("alerts")


def run(ccy: str, root: str = ROOT, jefe: Optional[dict] = None, write: bool = True, as_of: Optional[str] = None) -> dict:
    blocks, regime, prev, cal, al = load(ccy, root)
    if jefe is None:
        try:
            jefe = J.compute(as_of, root)
        except Exception as e:  # never break ingestion because of the ranking
            jefe = {"status": "unavailable", "reason": "jefe error: %s" % e}
    out = build(ccy, blocks, regime, prev, jefe, cal, al)
    from .gate import check
    out["gate"] = check(out, blocks, regime)
    out["published"] = bool(out["gate"]["pass"])
    if not out["published"]:  # deployment condition: a failed gate withholds the text, the failures stay visible
        out["narrative_withheld"] = out["narrative"]
        out["narrative"] = "daily_log retenido por la puerta anti-invención: " + "; ".join(out["gate"]["failures"])
    if write:
        p = os.path.join(root, "data", ccy, "agent.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
        if jefe and jefe.get("status") == "ok":
            mp = os.path.join(root, "data", "mesa", "jefe.json")
            os.makedirs(os.path.dirname(mp), exist_ok=True)
            with open(mp, "w", encoding="utf-8") as f:
                json.dump(jefe, f, indent=1, ensure_ascii=False)
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccy", default="usd")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    ccys = list(SPEC) if a.all else [a.ccy.lower()]
    jefe = J.compute(a.as_of)
    rc = 0
    for c in ccys:
        out = run(c, jefe=jefe, write=not a.no_write, as_of=a.as_of)
        g = out["gate"]
        print("== %s  gate=%s  degraded=%s  hash=%s" % (c.upper(), "PASS" if g["pass"] else "FAIL", len(out["degraded"]), out["hash"]))
        print(out["narrative"])
        if not g["pass"]:
            rc = 1
            print("GATE FAILURES:", json.dumps(g["failures"], ensure_ascii=False))
        print()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
