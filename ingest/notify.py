"""Telegram delivery for the desk (config/notify.json). Two modes, both deterministic and built only from published JSON:

  event mode   (python -m ingest.notify --ccy usd)   — after a refresh: compares the current state of one currency with the
               last notified state (data/<ccy>/notify_state.json) and sends one message per transition (regime change,
               gate withheld/recovered, block degraded/recovered, refresh error, jefe ranking change). Silent when nothing changed.
  digest mode  (python -m ingest.notify --digest)    — once a day, ONE message (blotter de las 08:00): eight rows CCY · label ·
               BC · Tesoro · price gate · marks (⧗ / LAG / cobertura parcial), the BC and Treasury ranking lines of the live
               jefe.json (stamp = single truth), the real exceptions in one line each, and the anti-invention inventory.
               F1–F7 stay in agent.json and on the currency page: the digest is the map, not the book.

Noise rules (2026-09-12 audit): the first run of a currency writes its state silently (no "estado inicial" message); block
freshness (stale/proxy) never fires an event — it goes to the digest; only unavailable/degraded transitions fire; source errors
fire once per source name (24 h), a recovery only when the error was sent and the same lane later runs clean; error text is one
sanitized line (no HTML, no Cloudflare dumps).

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


def clean_err(e, limit: int = 160) -> str:
    """One line per source error: name + HTTP status/reason, never an HTML body (Cloudflare 403 pages ran 686 chars into the chat)."""
    t = str(e)
    for marker in ("<!DOCTYPE", "<!doctype", "<html", "<HTML"):
        i = t.find(marker)
        if i >= 0:
            t = t[:i] + " [HTML omitido]"
    t = " ".join(t.split())
    return t if len(t) <= limit else t[:limit - 1] + "…"


def err_name(e) -> str:
    return str(e).split(":")[0].strip()


LAG_DAYS = {"daily": 3, "weekly": 10, "ten_day": 14, "monthly": 25, "quarterly": 100}  # same UI thresholds as ESTADO (pack de las 08:00)


def lag_days(asof: Optional[str], cadence: Optional[str]) -> Optional[int]:
    """Days since the block's as-of when it exceeds its cadence threshold, else None. No cadence → weekly threshold."""
    if not asof:
        return None
    try:
        n = (datetime.now(timezone.utc).date() - datetime.fromisoformat(asof[:10]).date()).days
    except Exception:
        return None
    thr = LAG_DAYS.get(cadence, 10) if cadence != "event" else None
    return n if (thr is not None and n > thr) else None


# ───────────────────────────── state snapshot of one currency ─────────────────────────────
def snapshot(ccy: str, root: str = ROOT) -> dict:
    d = os.path.join(root, "data", ccy)
    r = _rj(os.path.join(d, "regime.json")) or {}
    a = _rj(os.path.join(d, "agent.json")) or {}
    R = r.get("regimes", {})
    return {"as_of": r.get("as_of"), "generated_at": r.get("generated_at"),
            "general": (R.get("general") or {}).get("regime") or r.get("regime"),
            "central_bank": (R.get("central_bank") or {}).get("confirmed") or (R.get("central_bank") or {}).get("regime"),
            "fiscal": (R.get("fiscal") or {}).get("confirmed") or (R.get("fiscal") or {}).get("regime"),
            "fiscal_engine": (R.get("fiscal") or {}).get("engine"), "price_gate": (R.get("general") or {}).get("price_gate"),
            "lane": (r.get("heartbeat") or {}).get("lane"), "flags": r.get("flags") or [],
            "gate": (a.get("gate") or {}).get("pass") if a.get("gate") else None, "gate_failures": (a.get("gate") or {}).get("failures", []),
            "hash": a.get("hash"), "streaks": a.get("streaks") or {},
            "blocks": {b: (m or {}).get("status") for b, m in (a.get("blocks_meta") or {}).items()},
            "blocks_asof": {b: (m or {}).get("as_of") for b, m in (a.get("blocks_meta") or {}).items()},
            "blocks_cadence": {b: (m or {}).get("cadence") for b, m in (a.get("blocks_meta") or {}).items()},
            "errors": (r.get("heartbeat") or {}).get("errors") or [], "F1": (a.get("daily_log") or {}).get("F1"), "F5": (a.get("daily_log") or {}).get("F5"),
            "degraded": a.get("degraded") or []}


def jefe_snapshot(root: str = ROOT) -> dict:
    j = _rj(os.path.join(root, "data", "mesa", "jefe.json")) or {}
    t = j.get("treasury") or {}
    return {"friday": j.get("as_of_friday"), "order": [x["ccy"] for x in j.get("ranking", [])], "ranking": j.get("ranking", []),
            "low_dispersion": j.get("low_dispersion"), "pair": j.get("pair_max_z_gap"),
            "treasury": {"friday": t.get("as_of_friday"), "ranking": t.get("ranking", [])} if t.get("status") == "ok" else None, "labels": j.get("labels") or {},
            "stamp": j.get("stamp"), "generated_at": j.get("generated_at"), "completeness": j.get("completeness") or {}, "numeraire": j.get("numeraire")}


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
    if prev is None:
        return []  # first run (or lost state): the state is written silently; the digest carries the picture
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
            out.append("<b>%s · INVENTARIO A1–A5</b>: PASA de nuevo, el daily_log vuelve a publicarse." % C)
        else:
            out.append("<b>%s · INVENTARIO A1–A5 RETIENE</b> el daily_log: %s" % (C, esc("; ".join(cur["gate_failures"]))))
    if on("block_degraded"):
        for b, st in cur["blocks"].items():
            ps = (prev.get("blocks") or {}).get(b)
            if ps is None or st == ps:
                continue
            # stale/proxy flap between lanes (JPY 9× in a day): they are digest material, not events; only a block that vanishes fires
            if st in ("unavailable", "degraded"):
                out.append("<b>%s · %s %s</b> (as-of %s): el bloque no se ha podido reconstruir en esta lane." % (C, BN.get(b, b), esc(ST_ES.get(st, st)), esc(cur["blocks_asof"].get(b))))
            elif ps in ("unavailable", "degraded"):
                out.append("<b>%s · %s</b> vuelve (%s, as-of %s)." % (C, BN.get(b, b), esc(ST_ES.get(st, st)), esc(cur["blocks_asof"].get(b))))
    # a note tagged *_last_good_copy means the source is blocked but the data is current (served from the committed copy):
    # it is an AVISO, separate from real source errors, and each class notifies on its own transition
    # source errors by NAME, once per 24 h per source, grouped in one line; a recovery only when the error was sent and the same
    # lane later runs without it (heartbeat.errors carries only the current lane, so another lane running clean proves nothing)
    hard, copies = _split_errors(cur["errors"])
    sent = dict(prev.get("errors_sent") or {})  # name -> {"ts", "lane"}
    now = _now()
    def fresh24(ts):
        try:
            return (datetime.fromisoformat(now.replace("Z", "+00:00")) - datetime.fromisoformat(str(ts).replace("Z", "+00:00"))).total_seconds() < 86400
        except Exception:
            return False
    if on("refresh_error"):
        new_hard = [e for e in hard if not (sent.get(err_name(e)) and fresh24(sent[err_name(e)]["ts"]))]
        if new_hard:
            out.append("<b>%s · FUENTE</b> (lane %s): %s · reintento en la próxima lane" % (C, esc(cur.get("lane") or "—"), esc(" · ".join(clean_err(e) for e in new_hard))))
        new_copies = [e for e in copies if not (sent.get(err_name(e)) and fresh24(sent[err_name(e)]["ts"]))]
        if new_copies:
            out.append("<b>%s · AVISO</b> fuente bloqueada, dato vigente desde la copia buena: %s" % (C, esc(" · ".join(clean_err(e) for e in new_copies))))
        for e in hard + copies:
            sent[err_name(e)] = {"ts": now, "lane": cur.get("lane")}
        cur_names = {err_name(e) for e in hard + copies}
        recovered = [n for n, v in sent.items() if n not in cur_names and v.get("lane") == cur.get("lane")]
        if recovered:
            out.append("<b>%s</b> · vuelve a responder: %s (lane %s)" % (C, esc(", ".join(sorted(recovered))), esc(cur.get("lane") or "—")))
            for n in recovered:
                sent.pop(n, None)
    cur["errors_sent"] = sent
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
LAB_S = {"abundante": "abundante", "escasa": "escasa", "vulnerable": "vulnerable", "sin señal": "sin señal", "sin señal (compresión)": "sin señal (compr.)"}
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
REG_S = {"INJECTION": "INYEC", "DRAIN": "DREN", "NEUTRAL": "NEUT", "NO SIGNAL": "S/SEÑ", "NO DATA": "S/DATO", None: "—"}


def _clock() -> str:
    try:
        from zoneinfo import ZoneInfo
        n = datetime.now(timezone.utc)
        f = lambda z: n.astimezone(ZoneInfo(z)).strftime("%H:%M")
        w = n.astimezone(ZoneInfo("Africa/Lagos"))
        return "%s %s · LDN %s · NY %s · WAT %s" % (DIAS[w.weekday()], w.strftime("%d-%m"), f("Europe/London"), f("America/New_York"), f("Africa/Lagos"))
    except Exception:
        return _now()


def _signed(v, d=2) -> str:
    return "—" if v is None else (("+" if v > 0 else "") + _num(v, d))


def digest(root: str = ROOT) -> List[str]:
    """One message: header (clock, Friday map + stamp, tape as-of) · eight rows · BC line · Tesoro line · exceptions · inventory."""
    snaps = {c: snapshot(c, root) for c in CCYS}
    j = jefe_snapshot(root)
    cp = j.get("completeness") or {}
    rows, exc, gates_ok = [], [], 0
    for c in CCYS:
        s, C = snaps[c], c.upper()
        st = s["streaks"]
        trk = next((x for x in (j.get("treasury") or {}).get("ranking", []) if x["ccy"] == C), None)
        marks = []
        if trk and s.get("fiscal_engine") == "0.4" and ((s["fiscal"] == "DRAIN" and (trk.get("z") or 0) > 0) or (s["fiscal"] == "INJECTION" and (trk.get("z") or 0) < 0)):
            marks.append("⧗")
        t_cp = (cp.get(C) or {}).get("treasury") or {}
        if str(t_cp.get("equivalence_quality") or "") in ("medium-low", "low"):
            marks.append("cob.parcial")
        if trk and trk.get("proxy"):
            marks.append("proxy")
        for b in ("central_bank", "fiscal"):
            n = lag_days(s["blocks_asof"].get(b), s["blocks_cadence"].get(b))
            if n:
                marks.append("LAG %s %dd" % (BN[b], n))
        lab = LAB_S.get((j.get("labels") or {}).get(C), (j.get("labels") or {}).get(C) or "—")
        gate = "FRIC" if s.get("price_gate") == "FLOOR_FRICTION" else "ESCAS" if s.get("price_gate") == "LIQUIDITY_SCARCITY" else "—"
        rows.append("%-3s %-9s %-5s %-3s %-5s %-3s %-5s %s" % (C, lab[:9], REG_S.get(s["central_bank"], s["central_bank"] or "—"), "%sª" % st.get("central_bank", "—"),
                                                            REG_S.get(s["fiscal"], s["fiscal"] or "—"), "%sª" % st.get("fiscal", "—"), gate, " ".join(marks)))
        # exceptions: the real ones, one line each, no HTML
        for b, bst in s["blocks"].items():
            if bst and bst != "fresh":
                exc.append("%s %s %s (as-of %s)" % (C, BN.get(b, b), ST_ES.get(bst, bst), (s["blocks_asof"].get(b) or "—")[5:]))
        if s["gate"] is False:
            exc.append("%s inventario RETIENE: %s" % (C, "; ".join(s["gate_failures"])[:120]))
        else:
            gates_ok += 1 if s["gate"] else 0
        hard, copies = _split_errors(s["errors"])
        if hard:
            exc.append("%s fuente (lane %s): %s" % (C, s.get("lane") or "—", " · ".join(sorted({err_name(e) for e in hard}))))
        if copies:
            exc.append("%s copia last-good: %s" % (C, " · ".join(sorted({err_name(e).replace("_last_good_copy", "") for e in copies}))))
        if s["generated_at"]:
            try:
                h = (datetime.now(timezone.utc) - datetime.fromisoformat(s["generated_at"].replace("Z", "+00:00"))).total_seconds() / 3600
                if h > 30:
                    exc.append("%s último refresco hace %.0f h" % (C, h))
            except Exception:
                pass
    tape = max([s["generated_at"] or "" for s in snaps.values()] or [""])
    head = "<b>MESA MACRO FX · %s</b>\n" % esc(_clock())
    head += "mapa del viernes %s · sello %s · cinta al %s\n" % (esc(j.get("friday")), esc(j.get("stamp")), esc((tape or "—").replace("T", " ")[5:16] + "Z" if tape else "—"))
    head += "mapa, no libro · sin dirección · BC y Tesoro sin netear\n"
    table = "<pre>CCY etiqueta  BC    r  TES   r  precio marcas\n" + "\n".join(esc(r).rstrip() for r in rows) + "</pre>"
    body = ""
    if j.get("order"):
        body += "<b>BC</b> (Δ13 s reservas %% stock, Z): %s\n" % esc(" · ".join("%d %s %s%%/Z %s" % (x["rank"], x["ccy"], _signed(x["d13_pct"], 1), _signed(x["z"])) for x in j["ranking"]))
        if j.get("treasury"):
            body += "<b>Tesoro</b> (13 s, Z): %s\n" % esc(" · ".join("%d %s %s%s" % (x["rank"], x["ccy"], _signed(x["z"]), "*" if x.get("proxy") else "") for x in j["treasury"]["ranking"]) + " (* proxy)")
        if j.get("pair"):
            body += "par mayor brecha Z BC: %s / %s (%s) · %s\n" % (esc(j["pair"]["reserves_growth"]), esc(j["pair"]["reserves_drain"]), _num(j["pair"].get("z_gap"), 2), "dispersión baja: etiquetas retenidas" if j.get("low_dispersion") else "dispersión normal")
    else:
        body += "jefe de mesa: sin ranking publicado\n"
    body += ("<b>Excepciones (%d)</b>\n%s\n" % (len(exc), "\n".join("• " + esc(x) for x in exc))) if exc else "<b>Sin excepciones</b>: 32 bloques frescos, sin errores de fuente.\n"
    body += "inventario anti-invención A1–A5: %d/8 PASA · ⧗ otro reloj (Tesoro v0.3 vs fiscal v0.4) · LAG por cadencia · cob.parcial = equivalencia media-baja" % gates_ok
    return [head + table + "\n" + body]


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
    state["errors_sent"] = cur.get("errors_sent") or {}
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
