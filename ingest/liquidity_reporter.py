"""Operational MMT Liquidity Flow Reporter for the G8 FX Desk.

Generates institutional Spanish MMT bulletins per currency detailing:
  1. Central Bank liquidity injections/drains by instrument and tenor (e.g. BoJ JGB purchases across 2Y/5Y/10Y/20Y/30Y buckets,
     BoE STR/ILTR repos & APF sales, Fed WRESBAL & ON RRP, BCE MRO/LTRO & APP/PEPP, RBA OMO, RBNZ OMO/Settlement Cash, BoC repos, SNB Bills).
  2. Treasury cash account deposits/withdrawals and net debt issuance to the private sector (e.g. NZ Treasury deposits/withdrawals
     and residual cash drain/injection, US TGA daily change & Net Treasury Flow, Euro govt deposits, MoF 財政等要因, UK Exchequer residual,
     CAD Receiver General account, AUD Treasury account & AOFM tenders, CHF Confederation account & MMDRC/bond auctions).

Outputs:
  - Embedded in `data/<ccy>/agent.json["liquidity_bulletin"]`
  - Consolidated across all 8 currencies in `data/mesa/liquidity_report.json`
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CCYS = ["usd", "eur", "gbp", "jpy", "chf", "cad", "aud", "nzd"]

FLAGS = {
    "usd": "🇺🇸",
    "eur": "🇪🇺",
    "gbp": "🇬🇧",
    "jpy": "🇯🇵",
    "chf": "🇨🇭",
    "cad": "🇨🇦",
    "aud": "🇦🇺",
    "nzd": "🇳🇿",
}


def _rj(path: str) -> Optional[dict]:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _wj(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def _es_num(v: Optional[float], dec: int = 1, signed: bool = False) -> str:
    if v is None:
        return "—"
    while dec < 4 and v != 0 and round(v, dec) == 0:
        dec += 1
    s = ("{:,.%df}" % dec).format(abs(v)).replace(",", "§").replace(".", ",").replace("§", ".")
    if v < 0:
        return "−" + s
    if signed and v > 0:
        return "+" + s
    return s


def _entry(blk: dict, sec: str, key: str) -> dict:
    return ((blk or {}).get(sec) or {}).get(key) or {}


def _val(blk: dict, sec: str, key: str) -> Optional[float]:
    v = _entry(blk, sec, key).get("value")
    return float(v) if isinstance(v, (int, float)) else None


def _chg(blk: dict, sec: str, key: str, n: int = 1) -> Optional[float]:
    e = _entry(blk, sec, key)
    if n == 1 and isinstance(e.get("change_abs"), (int, float)):
        return float(e["change_abs"])
    sp = e.get("sparkline") or []
    if len(sp) > n and sp[-1] is not None and sp[-1 - n] is not None:
        return float(sp[-1]) - float(sp[-1 - n])
    return None


def _dt(blk: dict, sec: str, key: str) -> str:
    return str(_entry(blk, sec, key).get("date") or (blk or {}).get("as_of") or "—")


def _last_nonzero_from_csv(ccy: str, fname: str) -> Tuple[Optional[str], Optional[float]]:
    p = os.path.join(ROOT, "history", ccy, fname)
    if not os.path.exists(p):
        return None, None
    last_d, last_v = None, None
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) == 2 and parts[0] != "date":
                    try:
                        v = float(parts[1])
                        if v != 0:
                            last_d, last_v = parts[0], v
                    except ValueError:
                        pass
    except Exception:
        pass
    return last_d, last_v


def _build_jpy(cb: dict, fi: dict, reg: dict) -> dict:
    # BoJ operations and JGB purchase tenors (unit: 100 million JPY; /10 = bn JPY; /10000 = tn JPY)
    cab_v = _val(cb, "series", "cab_daily")
    cab_d = _dt(cb, "series", "cab_daily")
    cab_chg5 = _chg(cb, "series", "cab_daily", 5)
    jgb_settled = _entry(cb, "derived", "jgb_purch_settled")
    jgb_v = _val(cb, "derived", "jgb_purch_settled")
    jgb_d = _dt(cb, "derived", "jgb_purch_settled")
    buckets = [
        ("jgb_purch_1to3y", "bonos de 2 años (tramo 1–3Y)"),
        ("jgb_purch_3to5y", "bonos de 5 años (tramo 3–5Y)"),
        ("jgb_purch_5to10y", "bonos de 10 años (tramo 5–10Y)"),
        ("jgb_purch_10to25y", "bonos de 20 años (tramo 10–25Y)"),
        ("jgb_purch_over25y", "bonos de 30–40 años (tramo >25Y)"),
        ("jgb_purch_upto1y", "bonos de ≤1 año"),
        ("jgb_purch_iib", "bonos ligados a inflación (IIB)"),
    ]
    active_buckets = []
    latest_op_date = jgb_d
    for k, label in buckets:
        v = _val(cb, "derived", k)
        d = _dt(cb, "derived", k)
        if v and v > 0:
            active_buckets.append("%s por ¥%s bn" % (label, _es_num(v / 10.0, 1)))
            latest_op_date = d
    if not active_buckets:
        # Check recent settled operations in history or derived sparkline
        for k, label in buckets:
            e = _entry(cb, "derived", k)
            sp = e.get("sparkline") or []
            nz = [x for x in sp[-10:] if x and x > 0]
            if nz:
                active_buckets.append("%s (¥%s bn en la última subasta)" % (label, _es_num(nz[-1] / 10.0, 1)))
    ops5 = _val(cb, "derived", "ops_net_5d")
    if active_buckets:
        tot_txt = (" (total liquidado ¥%s bn el %s)" % (_es_num(jgb_v / 10.0, 1), latest_op_date)) if (jgb_v and jgb_v > 0) else (" (corte de operaciones %s)" % latest_op_date)
        cb_msg = (
            "🇯🇵 El Banco Central Japonés (BoJ) inyecta liquidez mediante compras de %s%s; "
            "el flujo neto de operaciones en 5 sesiones es de ¥%s bn y los saldos en cuenta corriente (CAB) se sitúan en ¥%s tn (%s, %s ¥%s bn en 5 sesiones)."
            % (
                ", ".join(active_buckets),
                tot_txt,
                _es_num((ops5 or 0.0) / 10.0, 1, signed=True),
                _es_num((cab_v or 0.0) / 10000.0, 2),
                cab_d,
                "inyección de" if (cab_chg5 or 0) >= 0 else "drenaje de",
                _es_num(abs(cab_chg5 or 0.0) / 10.0, 1),
            )
        )
    else:
        cb_msg = (
            "🇯🇵 El Banco Central Japonés (BoJ) registra un flujo neto de operaciones de ¥%s bn en 5 sesiones, "
            "con los saldos en cuenta corriente (CAB) en ¥%s tn (%s)."
            % (_es_num((ops5 or 0.0) / 10.0, 1, signed=True), _es_num((cab_v or 0.0) / 10000.0, 2), cab_d)
        )

    # Treasury (MoF)
    tf_d_v = _val(fi, "derived", "treasury_realized_daily")
    tf_d_dt = _dt(fi, "derived", "treasury_realized_daily")
    tf_5d_v = _val(fi, "derived", "treasury_realized_5d")
    ni_5d_v = _val(fi, "derived", "net_issuance_private_5d")
    gov_v = _val(fi, "series", "government_account")
    if tf_d_v is not None:
        if tf_d_v < 0:
            action = "tuvo un depósito neto en su cuenta del BoJ de ¥%s bn (drenaje de reservas" % _es_num(abs(tf_d_v) / 10.0, 1)
        elif tf_d_v > 0:
            action = "realizó pagos netos desde su cuenta del BoJ por ¥%s bn (inyección de reservas" % _es_num(tf_d_v / 10.0, 1)
        else:
            action = "mantuvo un flujo neto nulo en su cuenta del BoJ (¥0,0 bn"
        fi_msg = (
            "🇯🇵 El Tesoro de Japón (MoF) %s el %s; acumulado de 5 sesiones: %s de ¥%s tn; emisión neta al sector privado 5 sesiones: ¥%s tn; cuenta del gobierno: ¥%s tn)."
            % (
                action,
                tf_d_dt,
                "inyección" if (tf_5d_v or 0) >= 0 else "drenaje",
                _es_num(abs(tf_5d_v or 0.0) / 10000.0, 2),
                _es_num((ni_5d_v or 0.0) / 10000.0, 2, signed=True),
                _es_num((gov_v or 0.0) / 10000.0, 2),
            )
        )
    else:
        fi_msg = "🇯🇵 El Tesoro de Japón (MoF): sin flujo diario publicado hoy."
    return {
        "cb_message": cb_msg,
        "treasury_message": fi_msg,
        "cb_date": cab_d,
        "treasury_date": tf_d_dt,
        "cb_direction": "INJECTION" if (ops5 or 0) > 0 else "DRAIN" if (ops5 or 0) < 0 else "NEUTRAL",
        "treasury_direction": "INJECTION" if (tf_d_v or 0) > 0 else "DRAIN" if (tf_d_v or 0) < 0 else "NEUTRAL",
    }


def _build_nzd(cb: dict, fi: dict, reg: dict) -> dict:
    sc_v = _val(cb, "series", "settlement_cash_daily")
    sc_d = _dt(cb, "series", "settlement_cash_daily")
    sc_chg = _chg(cb, "series", "settlement_cash_daily", 1)
    omo_v = _val(cb, "series", "omo_outstanding")
    omo_chg = _chg(cb, "series", "omo_outstanding", 1)
    lsap_v = _val(cb, "series", "lsap_sales_month")
    cb_dir = "inyecta liquidez" if (omo_chg or sc_chg or 0) > 0 else "drena liquidez" if (omo_chg or sc_chg or 0) < 0 else "mantiene neutral la liquidez"
    cb_msg = (
        "🇳🇿 El Banco de la Reserva de Nueva Zelanda (RBNZ) %s mediante operaciones de mercado abierto (OMO vivas NZ$%s mm, Δ diario NZ$%s mm; ventas LSAP del mes NZ$%s mm), "
        "situando el settlement cash en NZ$%s mm (%s, Δ NZ$%s mm)."
        % (
            cb_dir,
            _es_num((omo_v or 0.0) / 1000.0, 2),
            _es_num((omo_chg or 0.0) / 1000.0, 2, signed=True),
            _es_num((lsap_v or 0.0) / 1000.0, 2),
            _es_num((sc_v or 0.0) / 1000.0, 2),
            sc_d,
            _es_num((sc_chg or 0.0) / 1000.0, 2, signed=True),
        )
    )

    res_d_v = _val(fi, "series", "treasury_residual_cash")
    res_d_dt = _dt(fi, "series", "treasury_residual_cash")
    res_5d_v = _val(cb, "derived", "residual_flow_5d_cum")
    crown_v = _val(fi, "series", "crown_settlement_account")
    crown_chg = _chg(fi, "series", "crown_settlement_account", 1)
    ni_5d_v = _val(fi, "derived", "net_issuance_5d")
    if res_d_v is not None and res_d_v < 0:
        fi_action = "tuvo un depósito neto en su cuenta de NZ$%s mm (drenaje de reservas" % _es_num(abs(res_d_v) / 1000.0, 2)
    elif res_d_v is not None and res_d_v > 0:
        fi_action = "realizó un desembolso neto desde su cuenta de NZ$%s mm (inyección de reservas" % _es_num(res_d_v / 1000.0, 2)
    elif crown_chg is not None and crown_chg > 0:
        fi_action = "tuvo un depósito en la Cuenta de la Corona de NZ$%s mm (drenaje" % _es_num(crown_chg / 1000.0, 2)
    else:
        fi_action = "registró un flujo residual diario neutro de NZ$0,0 mm (sin drenaje neto"
    fi_msg = (
        "🇳🇿 El Tesoro de Nueva Zelanda (NZDM) %s el %s; flujo residual acumulado en 5 sesiones: NZ$%s mm; "
        "emisión neta de bonos y letras en 5 sesiones: NZ$%s mm; saldo en la Cuenta de la Corona en el RBNZ: NZ$%s mm)."
        % (
            fi_action,
            res_d_dt,
            _es_num((res_5d_v or 0.0) / 1000.0, 2, signed=True),
            _es_num((ni_5d_v or 0.0) / 1000.0, 2, signed=True),
            _es_num((crown_v or 0.0) / 1000.0, 2),
        )
    )
    return {
        "cb_message": cb_msg,
        "treasury_message": fi_msg,
        "cb_date": sc_d,
        "treasury_date": res_d_dt,
        "cb_direction": "INJECTION" if (sc_chg or 0) > 0 else "DRAIN" if (sc_chg or 0) < 0 else "NEUTRAL",
        "treasury_direction": "INJECTION" if (res_d_v or 0) > 0 else "DRAIN" if (res_d_v or 0) < 0 else "NEUTRAL",
    }


def _build_usd(cb: dict, fi: dict, reg: dict) -> dict:
    res_v = _val(cb, "series", "reserves")
    res_d = _dt(cb, "series", "reserves")
    res_chg = _chg(cb, "series", "reserves", 1)
    rrp_v = _val(cb, "series", "on_rrp")
    rrp_dod = _val(cb, "derived", "on_rrp_dod")
    rrp_imp5 = _val(cb, "derived", "on_rrp_impulse_5d")
    tsy_chg = _chg(cb, "series", "treasury_securities", 1)
    cb_dir = "inyecta liquidez" if (res_chg or 0) > 0 else "drena liquidez" if (res_chg or 0) < 0 else "mantiene estables las reservas"
    cb_msg = (
        "🇺🇸 La Reserva Federal (Fed) %s: las reservas bancarias (WRESBAL) varían %s US$%s mm en la semana hasta US$%s mm (%s), "
        "con variación de Treasuries en cartera de US$%s mm y flujo diario en ON RRP de US$%s mm (impulso a reservas −ΔON_RRP en 5 sesiones de US$%s mm; stock ON RRP US$%s mm)."
        % (
            cb_dir,
            "al alza en" if (res_chg or 0) >= 0 else "a la baja en",
            _es_num(abs(res_chg or 0.0) / 1000.0, 1),
            _es_num((res_v or 0.0) / 1000.0, 1),
            res_d,
            _es_num((tsy_chg or 0.0) / 1000.0, 1, signed=True),
            _es_num((rrp_dod or 0.0) / 1000.0, 1, signed=True),
            _es_num((rrp_imp5 or 0.0) / 1000.0, 1, signed=True),
            _es_num((rrp_v or 0.0) / 1000.0, 1),
        )
    )

    tga_v = _val(fi, "series", "tga_closing")
    tga_d = _dt(fi, "series", "tga_closing")
    tga_dod = _val(fi, "derived", "tga_dod")
    tga_imp = _val(fi, "derived", "tga_reserve_impact")
    ntf_v = _val(fi, "derived", "net_treasury_flow")
    ntf_7d = _val(fi, "derived", "net_treasury_flow_7d")
    if (tga_dod or 0) > 0:
        fi_action = "tuvo un depósito neto en su cuenta TGA de US$%s mm (drenaje de reservas −ΔTGA de US$%s mm" % (
            _es_num(abs(tga_dod or 0.0) / 1000.0, 1),
            _es_num((tga_imp or 0.0) / 1000.0, 1, signed=True),
        )
    elif (tga_dod or 0) < 0:
        fi_action = "realizó un retiro neto desde su cuenta TGA de US$%s mm (inyección de reservas −ΔTGA de US$%s mm" % (
            _es_num(abs(tga_dod or 0.0) / 1000.0, 1),
            _es_num((tga_imp or 0.0) / 1000.0, 1, signed=True),
        )
    else:
        fi_action = "mantuvo sin cambios su cuenta TGA (US$0,0 mm"
    fi_msg = (
        "🇺🇸 El Tesoro de EE. UU. (DTS) %s el %s, dejando el saldo TGA en US$%s mm; "
        "el flujo fiscal neto (NTF, creación de activos financieros netos MMT) fue de US$%s mm en el día y US$%s mm en 7 sesiones)."
        % (
            fi_action,
            tga_d,
            _es_num((tga_v or 0.0) / 1000.0, 1),
            _es_num((ntf_v or 0.0) / 1000.0, 1, signed=True),
            _es_num((ntf_7d or 0.0) / 1000.0, 1, signed=True),
        )
    )
    return {
        "cb_message": cb_msg,
        "treasury_message": fi_msg,
        "cb_date": res_d,
        "treasury_date": tga_d,
        "cb_direction": "INJECTION" if (res_chg or 0) > 0 else "DRAIN" if (res_chg or 0) < 0 else "NEUTRAL",
        "treasury_direction": "INJECTION" if (tga_imp or 0) > 0 else "DRAIN" if (tga_imp or 0) < 0 else "NEUTRAL",
    }


def _build_eur(cb: dict, fi: dict, reg: dict) -> dict:
    ex_v = _val(cb, "series", "excess_liquidity")
    ex_d = _dt(cb, "series", "excess_liquidity")
    ex_chg = _chg(cb, "series", "excess_liquidity", 1)
    mp_chg = _chg(cb, "series", "monpol_securities", 1)
    mro_v = _val(cb, "series", "mro_weekly")
    ltro_v = _val(cb, "series", "ltro_weekly")
    cb_dir = "inyecta liquidez" if (ex_chg or 0) > 0 else "drena liquidez" if (ex_chg or 0) < 0 else "mantiene estable la liquidez"
    cb_msg = (
        "🇪🇺 El Banco Central Europeo (BCE) %s: el exceso de liquidez varía €%s mm en la semana hasta €%s mm (%s), "
        "con variación en la cartera de bonos de política monetaria de €%s mm y operaciones de refinanciación MRO (€%s mm) y LTRO (€%s mm)."
        % (
            cb_dir,
            _es_num((ex_chg or 0.0) / 1000.0, 1, signed=True),
            _es_num((ex_v or 0.0) / 1000.0, 1),
            ex_d,
            _es_num((mp_chg or 0.0) / 1000.0, 1, signed=True),
            _es_num((mro_v or 0.0) / 1000.0, 2),
            _es_num((ltro_v or 0.0) / 1000.0, 2),
        )
    )

    gd_v = _val(fi, "series", "govt_deposits")
    gd_d = _dt(fi, "series", "govt_deposits")
    gd_wow = _val(fi, "derived", "govt_deposits_wow")
    ni5 = _val(fi, "derived", "net_issuance_private_5d")
    if (gd_wow or 0) > 0:
        fi_action = "tuvieron un depósito neto en el Eurosistema de €%s mm en la semana (drenaje de reservas" % _es_num(abs(gd_wow or 0.0) / 1000.0, 1)
    elif (gd_wow or 0) < 0:
        fi_action = "realizaron retiros/pagos netos desde el Eurosistema de €%s mm en la semana (inyección de reservas" % _es_num(abs(gd_wow or 0.0) / 1000.0, 1)
    else:
        fi_action = "mantuvieron sin cambios sus depósitos en el Eurosistema (€0,0 mm"
    fi_msg = (
        "🇪🇺 Los Tesoros del área euro %s al %s, situando el saldo de depósitos públicos en €%s mm; "
        "emisión soberana neta en 5 sesiones: €%s mm)."
        % (
            fi_action,
            gd_d,
            _es_num((gd_v or 0.0) / 1000.0, 1),
            _es_num((ni5 or 0.0) / 1000.0, 1, signed=True),
        )
    )
    return {
        "cb_message": cb_msg,
        "treasury_message": fi_msg,
        "cb_date": ex_d,
        "treasury_date": gd_d,
        "cb_direction": "INJECTION" if (ex_chg or 0) > 0 else "DRAIN" if (ex_chg or 0) < 0 else "NEUTRAL",
        "treasury_direction": "INJECTION" if (gd_wow or 0) < 0 else "DRAIN" if (gd_wow or 0) > 0 else "NEUTRAL",
    }


def _build_gbp(cb: dict, fi: dict, reg: dict) -> dict:
    res_v = _val(cb, "series", "reserves")
    res_d = _dt(cb, "series", "reserves")
    res_chg = _chg(cb, "series", "reserves", 1)
    str_v = _val(cb, "series", "str_lending")
    str_chg = _chg(cb, "series", "str_lending", 1)
    iltr_v = _val(cb, "series", "ltr_lending")
    iltr_chg = _chg(cb, "series", "ltr_lending", 1)
    apf_chg = _chg(cb, "series", "apf_loan", 1)
    cb_dir = "inyecta liquidez" if (res_chg or 0) > 0 else "drena liquidez" if (res_chg or 0) < 0 else "mantiene estables las reservas"
    cb_msg = (
        "🇬🇧 El Banco de Inglaterra (BoE) %s: las reservas bancarias varían £%s mm en la semana hasta £%s mm (%s), "
        "mediante facilidades de repo STR (£%s mm vivos, Δ £%s mm) e ILTR (£%s mm vivos, Δ £%s mm) frente a la variación del préstamo APF (Δ £%s mm)."
        % (
            cb_dir,
            _es_num((res_chg or 0.0) / 1000.0, 2, signed=True),
            _es_num((res_v or 0.0) / 1000.0, 1),
            res_d,
            _es_num((str_v or 0.0) / 1000.0, 2),
            _es_num((str_chg or 0.0) / 1000.0, 2, signed=True),
            _es_num((iltr_v or 0.0) / 1000.0, 2),
            _es_num((iltr_chg or 0.0) / 1000.0, 2, signed=True),
            _es_num((apf_chg or 0.0) / 1000.0, 2, signed=True),
        )
    )

    ex_v = _val(fi, "derived", "exchequer_residual_weekly")
    ex_d = _dt(fi, "derived", "exchequer_residual_weekly")
    ni5 = _val(fi, "derived", "net_issuance_private_5d")
    gilt_d = _val(fi, "series", "dmo_gilt_auction")
    tbill_d = _val(fi, "series", "dmo_tbill_tender")
    if (ex_v or 0) < 0:
        fi_action = "registró un drenaje fiscal en el residuo semanal del Exchequer de £%s mm" % _es_num(abs(ex_v or 0.0) / 1000.0, 2)
    elif (ex_v or 0) > 0:
        fi_action = "registró una inyección fiscal en el residuo semanal del Exchequer de £%s mm" % _es_num((ex_v or 0.0) / 1000.0, 2)
    else:
        fi_action = "mantuvo neutro el residuo semanal del Exchequer (£0,0 mm"
    fi_msg = (
        "🇬🇧 El Tesoro británico (HM Treasury / DMO) %s (%s), con emisión neta de gilts y letras al sector privado en 5 sesiones de £%s mm "
        "(última subasta liquidada de gilts £%s mm, letras £%s mm)."
        % (
            fi_action,
            ex_d,
            _es_num((ni5 or 0.0) / 1000.0, 2, signed=True),
            _es_num((gilt_d or 0.0) / 1000.0, 2),
            _es_num((tbill_d or 0.0) / 1000.0, 2),
        )
    )
    return {
        "cb_message": cb_msg,
        "treasury_message": fi_msg,
        "cb_date": res_d,
        "treasury_date": ex_d,
        "cb_direction": "INJECTION" if (res_chg or 0) > 0 else "DRAIN" if (res_chg or 0) < 0 else "NEUTRAL",
        "treasury_direction": "INJECTION" if (ex_v or 0) > 0 else "DRAIN" if (ex_v or 0) < 0 else "NEUTRAL",
    }


def _build_cad(cb: dict, fi: dict, reg: dict) -> dict:
    res_v = _val(cb, "series", "reserves")
    res_d = _dt(cb, "series", "reserves")
    res_chg = _chg(cb, "series", "reserves", 1)
    repo_v = _val(cb, "series", "liquidity_repos")
    repo_chg = _chg(cb, "series", "liquidity_repos", 1)
    bonds_chg = _chg(cb, "series", "sovereign_bonds", 1)
    cb_dir = "inyecta liquidez" if (res_chg or 0) > 0 else "drena liquidez" if (res_chg or 0) < 0 else "mantiene estables los saldos de liquidación"
    cb_msg = (
        "🇨🇦 El Banco de Canadá (BoC) %s: las reservas (settlement balances) varían C$%s mm hasta C$%s mm (%s), "
        "con repos de liquidez a plazo en C$%s mm (Δ C$%s mm) y variación de bonos soberanos en cartera de C$%s mm."
        % (
            cb_dir,
            _es_num((res_chg or 0.0) / 1000.0, 2, signed=True),
            _es_num((res_v or 0.0) / 1000.0, 2),
            res_d,
            _es_num((repo_v or 0.0) / 1000.0, 2),
            _es_num((repo_chg or 0.0) / 1000.0, 2, signed=True),
            _es_num((bonds_chg or 0.0) / 1000.0, 2, signed=True),
        )
    )

    ga_v = _val(cb, "series", "government_account")
    ga_d = _dt(cb, "series", "government_account")
    ga_chg = _chg(cb, "series", "government_account", 1)
    ff7 = _val(fi, "derived", "fiscal_flow_7d_cum")
    ni5 = _val(fi, "derived", "net_issuance_private_5d")
    if (ga_chg or 0) > 0:
        fi_action = "tuvo un depósito neto en su cuenta del BoC de C$%s mm (drenaje de reservas" % _es_num(abs(ga_chg or 0.0) / 1000.0, 2)
    elif (ga_chg or 0) < 0:
        fi_action = "realizó un retiro/desembolso neto desde su cuenta del BoC de C$%s mm (inyección de reservas" % _es_num(abs(ga_chg or 0.0) / 1000.0, 2)
    else:
        fi_action = "mantuvo estable su cuenta en el BoC (C$0,0 mm"
    fi_msg = (
        "🇨🇦 El Tesoro de Canadá (Receptor General) %s al %s, con saldo en cuenta de C$%s mm; "
        "impulso fiscal acumulado de 7 días: C$%s mm; emisión neta al sector privado en 5 sesiones: C$%s mm)."
        % (
            fi_action,
            ga_d,
            _es_num((ga_v or 0.0) / 1000.0, 2),
            _es_num((ff7 or 0.0) / 1000.0, 2, signed=True),
            _es_num((ni5 or 0.0) / 1000.0, 2, signed=True),
        )
    )
    return {
        "cb_message": cb_msg,
        "treasury_message": fi_msg,
        "cb_date": res_d,
        "treasury_date": ga_d,
        "cb_direction": "INJECTION" if (res_chg or 0) > 0 else "DRAIN" if (res_chg or 0) < 0 else "NEUTRAL",
        "treasury_direction": "INJECTION" if (ga_chg or 0) < 0 else "DRAIN" if (ga_chg or 0) > 0 else "NEUTRAL",
    }


def _build_aud(cb: dict, fi: dict, reg: dict) -> dict:
    es_v = _val(cb, "series", "es_balances_daily")
    es_d = _dt(cb, "series", "es_balances_daily")
    es_chg = _chg(cb, "series", "es_balances_daily", 1)
    omo_v = _val(cb, "derived", "omo_outstanding")
    inv_chg = _chg(cb, "series", "aud_investments", 1)
    cb_dir = "inyecta liquidez" if (es_chg or 0) > 0 else "drena liquidez" if (es_chg or 0) < 0 else "mantiene estables las cuentas ES"
    cb_msg = (
        "🇦🇺 El Banco de la Reserva de Australia (RBA) %s: los saldos de liquidación (ES balances) varían A$%s mm hasta A$%s mm (%s), "
        "con operaciones OMO vivas en A$%s mm y variación semanal de bonos en AUD de A$%s mm."
        % (
            cb_dir,
            _es_num((es_chg or 0.0) / 1000.0, 2, signed=True),
            _es_num((es_v or 0.0) / 1000.0, 2),
            es_d,
            _es_num((omo_v or 0.0) / 1000.0, 2),
            _es_num((inv_chg or 0.0) / 1000.0, 2, signed=True),
        )
    )

    ga_v = _val(cb, "series", "government_account")
    ga_d = _dt(cb, "series", "government_account")
    ff_w = _val(fi, "derived", "fiscal_flow_weekly")
    ni5 = _val(fi, "derived", "net_issuance_5d")
    if (ff_w or 0) < 0:
        fi_action = "tuvo un depósito neto en su cuenta del RBA de A$%s mm en la semana (drenaje de reservas" % _es_num(abs(ff_w or 0.0) / 1000.0, 2)
    elif (ff_w or 0) > 0:
        fi_action = "realizó pagos netos desde su cuenta del RBA de A$%s mm en la semana (inyección de reservas" % _es_num((ff_w or 0.0) / 1000.0, 2)
    else:
        fi_action = "mantuvo sin cambios su cuenta en el RBA (A$0,0 mm"
    fi_msg = (
        "🇦🇺 El Tesoro australiano (AOFM) %s al %s, situando el saldo oficial en A$%s mm; "
        "emisión neta de bonos AGS y Treasury Notes en 5 sesiones: A$%s mm)."
        % (
            fi_action,
            ga_d,
            _es_num((ga_v or 0.0) / 1000.0, 2),
            _es_num((ni5 or 0.0) / 1000.0, 2, signed=True),
        )
    )
    return {
        "cb_message": cb_msg,
        "treasury_message": fi_msg,
        "cb_date": es_d,
        "treasury_date": ga_d,
        "cb_direction": "INJECTION" if (es_chg or 0) > 0 else "DRAIN" if (es_chg or 0) < 0 else "NEUTRAL",
        "treasury_direction": "INJECTION" if (ff_w or 0) > 0 else "DRAIN" if (ff_w or 0) < 0 else "NEUTRAL",
    }


def _build_chf(cb: dict, fi: dict, reg: dict) -> dict:
    sd_v = _val(cb, "series", "sight_deposits_domestic_weekly")
    sd_d = _dt(cb, "series", "sight_deposits_domestic_weekly")
    sd_chg = _chg(cb, "series", "sight_deposits_domestic_weekly", 1)
    bills_w = _val(cb, "derived", "bills_maturing_week")
    bills_stock = _val(cb, "series", "snb_bills")
    repos_stock = _val(cb, "series", "absorbing_repos")
    cb_dir = "inyecta liquidez" if (sd_chg or 0) > 0 else "absorbe liquidez" if (sd_chg or 0) < 0 else "mantiene estables los depósitos a la vista"
    cb_msg = (
        "🇨🇭 El Banco Nacional Suizo (SNB) %s: los depósitos a la vista domésticos varían CHF %s mm en la semana hasta CHF %s mm (%s), "
        "con vencimientos semanales de SNB Bills por CHF %s mm (stock SNB Bills CHF %s mm, repos de absorción CHF %s mm)."
        % (
            cb_dir,
            _es_num((sd_chg or 0.0) / 1000.0, 2, signed=True),
            _es_num((sd_v or 0.0) / 1000.0, 1),
            sd_d,
            _es_num((bills_w or 0.0) / 1000.0, 2),
            _es_num((bills_stock or 0.0) / 1000.0, 1),
            _es_num((repos_stock or 0.0) / 1000.0, 1),
        )
    )

    ni5 = _val(fi, "derived", "net_issuance_private_5d")
    ni5_d = _dt(fi, "derived", "net_issuance_private_5d")
    conf_v = _val(fi, "series", "amounts_due_to_confederation")
    conf_mom = _val(fi, "derived", "confed_cash_mom")
    if (ni5 or 0) < 0:
        fi_action = "drenó liquidez mediante emisión neta de letras MMDRC y bonos al sector privado de CHF %s mm en 5 sesiones" % _es_num(abs(ni5 or 0.0) / 1000.0, 2)
    elif (ni5 or 0) > 0:
        fi_action = "inyectó liquidez por vencimientos netos de letras MMDRC y bonos de CHF %s mm en 5 sesiones" % _es_num((ni5 or 0.0) / 1000.0, 2)
    else:
        fi_action = "mantuvo un flujo neto nulo de emisión soberana en 5 sesiones (CHF 0,00 mm)"
    fi_msg = (
        "🇨🇭 La Tesorería Federal Suiza (Confederación) %s (%s; saldo en cuenta del SNB CHF %s mm, variación mensual CHF %s mm)."
        % (
            fi_action,
            ni5_d,
            _es_num((conf_v or 0.0) / 1000.0, 2),
            _es_num((conf_mom or 0.0) / 1000.0, 2, signed=True),
        )
    )
    return {
        "cb_message": cb_msg,
        "treasury_message": fi_msg,
        "cb_date": sd_d,
        "treasury_date": ni5_d,
        "cb_direction": "INJECTION" if (sd_chg or 0) > 0 else "DRAIN" if (sd_chg or 0) < 0 else "NEUTRAL",
        "treasury_direction": "INJECTION" if (ni5 or 0) > 0 else "DRAIN" if (ni5 or 0) < 0 else "NEUTRAL",
    }


BUILDERS = {
    "jpy": _build_jpy,
    "nzd": _build_nzd,
    "usd": _build_usd,
    "eur": _build_eur,
    "gbp": _build_gbp,
    "cad": _build_cad,
    "aud": _build_aud,
    "chf": _build_chf,
}


def build_for_ccy(ccy: str, root: str = ROOT, write_agent: bool = True) -> dict:
    c = ccy.lower()
    d = os.path.join(root, "data", c)
    cb = _rj(os.path.join(d, "central_bank.json")) or {}
    fi = _rj(os.path.join(d, "fiscal.json")) or {}
    reg = _rj(os.path.join(d, "regime.json")) or {}
    R = reg.get("regimes") or {}
    info = BUILDERS[c](cb, fi, reg)
    bulletin = {
        "ccy": c.upper(),
        "flag": FLAGS.get(c, ""),
        "as_of": reg.get("as_of"),
        "general_regime": (R.get("general") or {}).get("regime") or reg.get("regime"),
        "cb_regime": (R.get("central_bank") or {}).get("regime"),
        "fiscal_regime": (R.get("fiscal") or {}).get("regime"),
        **info,
    }
    if write_agent:
        ap = os.path.join(d, "agent.json")
        agent = _rj(ap)
        if isinstance(agent, dict):
            agent["liquidity_bulletin"] = bulletin
            _wj(ap, agent)
    return bulletin


def generate_report(root: str = ROOT, write: bool = True, write_out: Optional[str] = None) -> dict:
    rep_path = write_out or os.path.join(root, "data", "mesa", "liquidity_report.json")
    prev_rep = _rj(rep_path) or {}
    prev_ccys = prev_rep.get("currencies") or {}

    currencies: Dict[str, dict] = {}
    changes: List[dict] = []
    summary_lines: List[str] = []
    messages: List[dict] = []

    for c in CCYS:
        b = build_for_ccy(c, root=root, write_agent=write)
        C = c.upper()
        p = prev_ccys.get(C) or {}
        changed_reasons = []
        if p:
            if b.get("cb_date") != p.get("cb_date"):
                changed_reasons.append("nuevo dato BC (%s)" % b.get("cb_date"))
            if b.get("treasury_date") != p.get("treasury_date"):
                changed_reasons.append("nuevo dato Tesoro (%s)" % b.get("treasury_date"))
            if b.get("cb_direction") != p.get("cb_direction"):
                changed_reasons.append("giro flujo BC (%s → %s)" % (p.get("cb_direction"), b.get("cb_direction")))
            if b.get("treasury_direction") != p.get("treasury_direction"):
                changed_reasons.append("giro flujo Tesoro (%s → %s)" % (p.get("treasury_direction"), b.get("treasury_direction")))
            if b.get("general_regime") != p.get("general_regime"):
                changed_reasons.append("cambio régimen general (%s → %s)" % (p.get("general_regime"), b.get("general_regime")))
        else:
            changed_reasons.append("boletín inicial")

        b["changed"] = bool(changed_reasons)
        b["change_reasons"] = changed_reasons
        currencies[C] = b
        if changed_reasons:
            changes.append({"ccy": C, "reasons": changed_reasons, "cb_message": b["cb_message"], "treasury_message": b["treasury_message"]})
        summary_lines.append(b["cb_message"])
        summary_lines.append(b["treasury_message"])
        messages.append({"currency": C, "actor": "Banco Central", "text": b["cb_message"]})
        messages.append({"currency": C, "actor": "Tesoro", "text": b["treasury_message"]})

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": "Boletín Operativo de Liquidez MMT G8 (Bancos Centrales y Tesoros)",
        "priority_rule": "1º Diaria (prioridad máxima) → 2º Semanal → 3º Mensual (solo cuando no queda más remedio)",
        "changes_count": len(changes),
        "changes": changes,
        "currencies": currencies,
        "messages": messages,
        "bulletin_text": "\n".join(summary_lines),
    }
    if write or write_out:
        _wj(rep_path, report)
    return report


generate_all_reports = generate_report



def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccy", default=None)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if a.ccy:
        b = build_for_ccy(a.ccy, write_agent=not a.no_write)
        print(b["cb_message"])
        print(b["treasury_message"])
        return 0
    rep = generate_report(write=not a.no_write)
    print(rep["bulletin_text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
