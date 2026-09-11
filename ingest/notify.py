"""Telegram delivery for the desk (config/notify.json). Two modes, both deterministic and built only from published JSON:

  event mode   (python -m ingest.notify --ccy usd)   — after a refresh: compares the current state of one currency with the
               last notified state (data/<ccy>/notify_state.json) and sends one message per transition (regime change,
               gate withheld/recovered, block degraded/recovered, refresh error, jefe ranking change). Silent when nothing changed.
  digest mode  (python -m ingest.notify --digest)    — once a day: quality incidents, the eight currencies (regimes, streaks,
               F1 + F5 of the daily_log) and the jefe de mesa ranking.

Secrets come from the environment (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID). Without them the notifier runs in dry mode:
it writes what it would have sent to data/mesa/outbox.json and never fails the workflow."""
from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone
from typing import Tuple, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CCYS = ["usd", "eur", "gbp", "jpy", "chf", "cad", "aud", "nzd"]
BN = {"central_bank": "BC", "fiscal": "Tesoro", "rates": "tipos", "banking": "banca"}
REG_ES = {"INJECTION": "INYECCIÓN", "DRAIN": "DRENAJE", "NEUTRAL": "NEUTRAL", "NO DATA": "SIN DATO", "LIQUIDITY_INJECTION": "INYECCIÓN DE LIQUIDEZ",
          "LIQUIDITY_DRAIN": "DRENAJE DE LIQUIDEZ", "FLOOR_FRICTION": "FRICCIÓN DE SUELO", "LIQUIDITY_SCARCITY": "ESCASEZ DE LIQUIDEZ", "NO SIGNAL": "SIN SEÑAL"}
ST_ES = {"fresh": "fresco", "stale": "stale", "proxy": "proxy", "unavailable": "no disponible", "degraded": "degradado"}
TG_API = "https://api.telegram.org/bot%s/sendMessage"


def _rj(path: str) -> Optional[dict]:
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return None
    return None


def _wj(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def _cfg() -> dict:
    return _rj(os.path.join(ROOT, "config", "notify.json")) or {"events": {}, "format": {"max_chars": 3900}}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wat() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Africa/Lagos")).strftime("%Y-%m-%d %H:%M WAT")
    except Exception:
        return _now()


def esc(s) -> str:
    return html.escape(str(s if s is not None else "—"), quote=False)


# ───────────────────────────── state snapshot of one currency ─────────────────────────────
def snapshot(ccy: str, root: str = ROOT) -> dict:
    d = os.path.join(root, "data", ccy)
    r = _rj(os.path.join(d, "regime.json")) or {}
    a = _rj(os.path.join(d, "agent.json")) or {}
    R = r.get("regimes", {})
    return {"as_of": r.get("as_of"), "generated_at": r.get("generated_at"),
            "general": (R.get("general") or {}).get("regime") or r.get("regime"),
            "central_bank": (R.get("central_bank") or {}).get("regime"), "fiscal": (R.get("fiscal") or {}).get("regime"),
            "gate": (a.get("gate") or {}).get("pass") if a.get("gate") else None, "gate_failures": (a.get("gate") or {}).get("failures", []),
            "hash": a.get("hash"), "streaks": a.get("streaks") or {},
            "blocks": {b: (m or {}).get("status") for b, m in (a.get("blocks_meta") or {}).items()},
            "blocks_asof": {b: (m or {}).get("as_of") for b, m in (a.get("blocks_meta") or {}).items()},
            "errors": (r.get("heartbeat") or {}).get("errors") or [], "F1": (a.get("daily_log") or {}).get("F1"), "F5": (a.get("daily_log") or {}).get("F5"),
            "degraded": a.get("degraded") or []}


def jefe_snapshot(root: str = ROOT) -> dict:
    j = _rj(os.path.join(root, "data", "mesa", "jefe.json")) or {}
    t = j.get("treasury") or {}
    return {"friday": j.get("as_of_friday"), "order": [x["ccy"] for x in j.get("ranking", [])], "ranking": j.get("ranking", []),
            "low_dispersion": j.get("low_dispersion"), "pair": j.get("pair_max_conviction"),
            "treasury": {"friday": t.get("as_of_friday"), "ranking": t.get("ranking", [])} if t.get("status") == "ok" else None, "labels": j.get("labels") or {}}


# ───────────────────────────── event detection ─────────────────────────────
def _split_errors(errs: list) -> Tuple[List[str], List[str]]:
    """(hard errors, last-good-copy notes)"""
    e = [str(x) for x in errs or []]
    return [x for x in e if "last_good_copy" not in x], [x for x in e if "last_good_copy" in x]


def events_for(ccy: str, cur: dict, prev: Optional[dict], jefe: dict, jefe_prev: Optional[dict], cfg: dict) -> List[str]:
    ev = cfg.get("events", {})
    on = lambda k: ev.get(k, {}).get("enabled", True)
    C = ccy.upper()
    out: List[str] = []
    first = prev is None
    if first:
        return ["<b>%s</b> · notificaciones activadas. Estado inicial: general %s · BC %s · Tesoro %s · puerta %s." % (
            C, esc(REG_ES.get(cur["general"], cur["general"])), esc(REG_ES.get(cur["central_bank"], cur["central_bank"])), esc(REG_ES.get(cur["fiscal"], cur["fiscal"])), "PASA" if cur["gate"] else ("RETIENE" if cur["gate"] is False else "—"))]
    if on("regime_change_general") and cur["general"] != prev.get("general"):
        miss = [BN.get(b, b) for b in ("central_bank", "fiscal") if cur.get(b) in ("NO SIGNAL", "NO DATA", None)]
        warn = ("⚠ %s sin dato en esta pasada → sin acuerdo posible entre bloques; el cambio refleja la ausencia de un bloque, no un flujo.\n" % " y ".join(miss)) if miss else ""
        out.append("<b>%s · RÉGIMEN GENERAL</b>: %s → <b>%s</b> (as-of %s)\n%s%s" % (C, esc(REG_ES.get(prev.get("general"), prev.get("general"))), esc(REG_ES.get(cur["general"], cur["general"])), esc(cur["as_of"]), warn, esc(cur.get("F5") or "")))
    if on("regime_change_block"):
        for b in ("central_bank", "fiscal"):
            if cur[b] != prev.get(b):
                out.append("<b>%s · %s</b>: %s → <b>%s</b> (as-of %s)\n%s" % (C, BN[b], esc(REG_ES.get(prev.get(b), prev.get(b))), esc(REG_ES.get(cur[b], cur[b])), esc(cur["blocks_asof"].get(b) or cur["as_of"]), esc(cur.get("F1") if b == "central_bank" else "")))
    if on("gate_withheld") and cur["gate"] is not None and cur["gate"] != prev.get("gate"):
        if cur["gate"]:
            out.append("<b>%s · PUERTA</b>: daily_log vuelve a publicarse (puerta PASA)." % C)
        else:
            out.append("<b>%s · PUERTA RETIENE</b> el daily_log: %s" % (C, esc("; ".join(cur["gate_failures"]))))
    if on("block_degraded"):
        for b, st in cur["blocks"].items():
            ps = (prev.get("blocks") or {}).get(b)
            if ps is None or st == ps:
                continue
            if st != "fresh":
                out.append("<b>%s · %s %s</b> (as-of %s): el bloque deja de estar fresco." % (C, BN.get(b, b), esc(ST_ES.get(st, st)), esc(cur["blocks_asof"].get(b))))
            elif ps != "fresh":
                out.append("<b>%s · %s fresco</b> de nuevo (as-of %s)." % (C, BN.get(b, b), esc(cur["blocks_asof"].get(b))))
    # a note tagged *_last_good_copy means the source is blocked but the data is current (served from the committed copy):
    # it is an AVISO, separate from real source errors, and each class notifies on its own transition
    hard, copies = _split_errors(cur["errors"])
    phard, pcopies = _split_errors(prev.get("errors") or [])
    if on("refresh_error") and bool(hard) != bool(phard):
        if hard:
            out.append("<b>%s · ERRORES DE FUENTE</b> en el refresco: %s" % (C, esc("; ".join(hard)[:600])))
        else:
            out.append("<b>%s</b> · el refresco vuelve a completarse sin errores de fuente." % C)
    if on("refresh_error") and bool(copies) != bool(pcopies):
        if copies:
            out.append("<b>%s · AVISO · fuente bloqueada</b>, dato vigente servido desde la copia buena: %s" % (C, esc("; ".join(copies)[:600])))
        else:
            out.append("<b>%s</b> · la fuente bloqueada vuelve a responder." % C)
    if on("jefe_ranking_change") and jefe.get("friday") and jefe_prev is not None and jefe.get("friday") != jefe_prev.get("friday"):
        order, porder = jefe.get("order", []), jefe_prev.get("order", [])
        mine = order.index(C) + 1 if C in order else None
        pmine = porder.index(C) + 1 if C in porder else None
        changed = (mine != pmine) or (order[:1] != porder[:1]) or (order[-1:] != porder[-1:])
        if changed:
            out.append("<b>%s · JEFE DE MESA</b> (viernes %s): posición %s (antes %s) de %d · 1.º %s · último %s · %s" % (
                C, esc(jefe["friday"]), mine, pmine, len(order), esc(order[0] if order else "—"), esc(order[-1] if order else "—"), esc(jefe_rank_line(jefe))))
    return out


def jefe_rank_line(j: dict) -> str:
    return " · ".join("%d %s %s%% (Z %s)" % (x["rank"], x["ccy"], _num(x["d13_pct"], 1), _num(x["z"], 2)) for x in j.get("ranking", []))


def jefe_treasury_line(j: dict) -> str:
    """Treasury order (jefe de mesa v2) + plumbing labels; empty when the Treasury column is not computable."""
    t = j.get("treasury")
    if not t or not t.get("ranking"):
        return ""
    lab = j.get("labels") or {}
    line = "Tesoro (viernes %s; impulso fiscal a un trimestre, 13–26 s): " % t["friday"] + " · ".join(
        "%d %s%s (Z %s)" % (x["rank"], x["ccy"], " (proxy)" if x.get("proxy") else "", _num(x["z"], 2)) for x in t["ranking"])
    if lab:
        line += "\netiquetas: " + " · ".join("%s %s" % (c, lab[c]) for c in lab)
    return line


def _num(v, d) -> str:
    if v is None:
        return "—"
    s = ("{:,.%df}" % d).format(v).replace(",", "§").replace(".", ",").replace("§", ".")
    return ("−" + s.lstrip("-")) if v < 0 else s


# ───────────────────────────── digest ─────────────────────────────
def digest(root: str = ROOT) -> List[str]:
    snaps = {c: snapshot(c, root) for c in CCYS}
    j = jefe_snapshot(root)
    inc = []
    for c, s in snaps.items():
        for b, st in s["blocks"].items():
            if st and st != "fresh":
                inc.append("%s · %s: %s (as-of %s)" % (c.upper(), BN.get(b, b), ST_ES.get(st, st), s["blocks_asof"].get(b)))
        if s["gate"] is False:
            inc.append("%s · puerta RETIENE: %s" % (c.upper(), "; ".join(s["gate_failures"])))
        hard, copies = _split_errors(s["errors"])
        if hard:
            inc.append("%s · errores de fuente en el último refresco" % c.upper())
        if copies:
            inc.append("%s · fuente bloqueada, dato servido desde la copia buena" % c.upper())
        if s["generated_at"]:
            try:
                h = (datetime.now(timezone.utc) - datetime.fromisoformat(s["generated_at"].replace("Z", "+00:00"))).total_seconds() / 3600
                if h > 30:
                    inc.append("%s · último refresco hace %.0f h" % (c.upper(), h))
            except Exception:
                pass
    head = "<b>MESA MACRO FX · resumen diario</b> · %s\n" % esc(_wat())
    head += ("<b>Incidencias (%d)</b>\n" % len(inc) + "\n".join("• " + esc(x) for x in inc)) if inc else "<b>Sin incidencias</b>: 32 bloques frescos, ocho puertas pasan."
    msgs = [head]
    for c in CCYS:
        s = snaps[c]
        st = s["streaks"]
        line = "<b>%s</b> · general <b>%s</b> (%s.ª) · BC %s (%s.ª) · Tesoro %s (%s.ª) · puerta %s · as-of %s\n" % (
            c.upper(), esc(REG_ES.get(s["general"], s["general"])), st.get("general", "—"), esc(REG_ES.get(s["central_bank"], s["central_bank"])), st.get("central_bank", "—"),
            esc(REG_ES.get(s["fiscal"], s["fiscal"])), st.get("fiscal", "—"), "PASA" if s["gate"] else ("RETIENE" if s["gate"] is False else "—"), esc(s["as_of"]))
        line += esc(s.get("F1") or "F1: sin daily_log") + "\n" + esc(s.get("F5") or "")
        msgs.append(line)
    if j.get("order"):
        msgs.append("<b>Jefe de mesa</b> · viernes %s · BC: Δ13 semanas de reservas del BC en %% del stock, Z transversal · Tesoro en paralelo (sin par neto)\n%s\n%s%s%s" % (
            esc(j["friday"]), esc(jefe_rank_line(j)), ("par con más convicción relativa por la pata BC: %s (más reservas) frente a %s (más drenaje)" % (j["pair"]["reserves_growth"], j["pair"]["reserves_drain"])) if j.get("pair") else "",
            "\n⚠ dispersión transversal baja" if j.get("low_dispersion") else "", ("\n" + esc(jefe_treasury_line(j))) if jefe_treasury_line(j) else ""))
    return msgs


# ───────────────────────────── transport ─────────────────────────────
def send(messages: List[str], root: str = ROOT, tag: str = "event") -> dict:
    cfg = _cfg()
    maxc = int((cfg.get("format") or {}).get("max_chars", 3900))
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    # pack consecutive messages into ≤ max_chars chunks
    chunks: List[str] = []
    for m in messages:
        while len(m) > maxc:
            cut = m.rfind("\n", 0, maxc)
            cut = cut if cut > 200 else maxc
            chunks.append(m[:cut])
            m = m[cut:].lstrip("\n")
        if chunks and len(chunks[-1]) + 2 + len(m) <= maxc:
            chunks[-1] += "\n\n" + m
        else:
            chunks.append(m)
    ob_path = os.path.join(root, "data", "mesa", "outbox.json")
    ob = _rj(ob_path) or {"sent": []}
    result = {"mode": "telegram" if (token and chat) else "dry", "chunks": len(chunks), "ok": 0, "errors": []}
    for ch in chunks:
        entry = {"ts": _now(), "tag": tag, "text": ch, "delivered": None}
        if token and chat:
            try:
                import requests
                r = requests.post(TG_API % token, json={"chat_id": chat, "text": ch, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=30)
                entry["delivered"] = bool(r.ok and r.json().get("ok"))
                if entry["delivered"]:
                    result["ok"] += 1
                else:
                    result["errors"].append(r.text[:200])
            except Exception as e:
                entry["delivered"] = False
                result["errors"].append(str(e)[:200])
        else:
            entry["delivered"] = False
            entry["note"] = "dry run: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"
        ob["sent"].append(entry)
    ob["sent"] = ob["sent"][-100:]
    ob["last"] = _now()
    _wj(ob_path, ob)
    return result


# ───────────────────────────── entry points ─────────────────────────────
def run_events(ccy: str, root: str = ROOT) -> dict:
    cfg = _cfg()
    sp = os.path.join(root, "data", ccy, "notify_state.json")
    prev = _rj(sp)
    cur = snapshot(ccy, root)
    jefe = jefe_snapshot(root)
    jp = os.path.join(root, "data", "mesa", "notify_jefe.json")
    jefe_prev = _rj(jp)
    msgs = events_for(ccy, cur, prev, jefe, jefe_prev, cfg)
    res = send(msgs, root, tag="event:%s" % ccy) if msgs else {"mode": "none", "chunks": 0, "ok": 0, "errors": []}
    state = {k: cur[k] for k in ("as_of", "generated_at", "general", "central_bank", "fiscal", "gate", "hash", "blocks", "errors")}
    state["notified_at"] = _now()
    _wj(sp, state)
    if jefe.get("friday") and (jefe_prev is None or jefe_prev.get("friday") != jefe.get("friday")):
        _wj(jp, {"friday": jefe["friday"], "order": jefe["order"], "notified_at": _now()})
    res["messages"] = len(msgs)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccy", default=None)
    ap.add_argument("--digest", action="store_true")
    ap.add_argument("--preview", action="store_true", help="print the messages, do not send, do not touch state")
    a = ap.parse_args(argv)
    if a.digest:
        msgs = digest()
        if a.preview:
            print("\n\n".join(msgs))
            return 0
        print(json.dumps(send(msgs, tag="digest"), ensure_ascii=False))
        return 0
    if not a.ccy:
        ap.error("--ccy or --digest")
    if a.preview:
        cfg = _cfg()
        cur = snapshot(a.ccy)
        print("\n\n".join(events_for(a.ccy, cur, _rj(os.path.join(ROOT, "data", a.ccy, "notify_state.json")), jefe_snapshot(), _rj(os.path.join(ROOT, "data", "mesa", "notify_jefe.json")), cfg)) or "(sin eventos)")
        return 0
    print(json.dumps(run_events(a.ccy), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
