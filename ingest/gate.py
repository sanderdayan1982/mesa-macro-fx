"""Anti-invention gate (deployment condition, round 3 — Kimi/Qwen). Five binary assertions on a built agent.json:
 1. every numeric token in the text is a recorded number (with its field), a date present in the day's JSON, or a structural label;
 2. every directional verb matches the sign of the field it describes (word ↔ sign, and recomputed from the blocks when given);
 3. the F5 label belongs to the engine enum and equals regime.json; block regimes belong to their enum; streaks equal the ledger;
 4. every acronym of the currency glossary that appears is expanded at its first occurrence;
 5. determinism: the hash equals the hash of the narrative; a stale/proxy/unavailable block is announced in the header.
Plus the blacklist on the model's closing lines (operator_takeaway), when present.  `fuzz()` re-runs the build with inverted
signs and checks the verbs flip (CLI: python -m ingest.gate --ccy usd --fuzz)."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Dict, List, Optional

NUM = re.compile(r"[−\-+]?\d[\d.]*(?:,\d+)?")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
STRUCTURAL = [r"\bF[1-7]\.", r"T1–T3", r"Δ13", r"p20", r"(?<=\d)\.ª", r"\bH\.4\.1\b"]
POS_VERBS = {"subieron", "creció", "subió", "alimenta", "por encima"}
NEG_VERBS = {"cayeron", "cayó", "bajó", "drena", "por debajo"}
ZERO_VERBS = {"no variaron", "no varió", "no mueve", "al nivel"}
BLACKLIST_CLOSING = ["busca", "pretende", "quiere", "intenta", "inflación", "empleo", "pib", "señal", "recomendación", "recomend", "comprar", "vender", "compra", "venta", "objetivo", "probabilidad", "seguirá", "continuará", "masivo", "fuerte", "enorme"]


def _dates_in(obj, acc: set) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _dates_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _dates_in(v, acc)
    elif isinstance(obj, str):
        for m in DATE.findall(obj):
            acc.add(m)


def check(out: dict, blocks: Optional[dict] = None, regime: Optional[dict] = None) -> dict:
    fails: List[str] = []
    text = out.get("narrative", "")
    # 1 — numeric traceability
    allowed = {n["token"] for n in out.get("numbers", [])}
    dates = set()
    _dates_in(out, dates)
    if blocks:
        _dates_in(blocks, dates)
    if regime:
        _dates_in(regime, dates)
    body = text
    for d in DATE.findall(body):
        if d not in dates:
            fails.append("A1 date not in JSON: %s" % d)
    body = DATE.sub(" ", body)
    for lit in out.get("structural") or []:
        body = body.replace(lit, " ")
    for pat in STRUCTURAL:
        body = re.sub(pat, " ", body)
    for m in NUM.finditer(body):
        tok = m.group(0).lstrip("+")
        if tok in allowed or tok.lstrip("−-") in allowed or tok.replace("-", "−") in allowed:
            continue
        if re.fullmatch(r"\d", tok) and ("F%s" % tok) in out.get("daily_log", {}):
            continue
        fails.append("A1 untraced number: %r" % tok)
    # 2 — verbs vs sign
    for v in out.get("verbs", []):
        w, s = v["verb"], v["sign"]
        ok = (w in POS_VERBS and s > 0) or (w in NEG_VERBS and s < 0) or (w in ZERO_VERBS and s == 0)
        if not ok:
            fails.append("A2 verb/sign mismatch: %s %s (%s)" % (w, s, v["field"]))
        if w not in text:
            fails.append("A2 verb not in text: %s" % w)
    if blocks:
        from .narrative import _get, _delta, WINDOWS, _freq
        for v in out.get("verbs", []):
            f = v["field"]
            m = re.match(r"^(\w+)\.(\w+)\.(\w+)\.delta(?:_(\d+))?$", f)
            if not m:
                continue
            e = _get(blocks, (m.group(1), m.group(2), m.group(3)))
            n = int(m.group(4)) if m.group(4) else WINDOWS[_freq(e)][2]
            d = _delta(e, n) if e else None
            if d is not None and ((d > 0) - (d < 0)) != v["sign"]:
                fails.append("A2 recomputed sign differs: %s" % f)
    # 3 — enum + regime + streaks
    from .narrative import GEN_ENUM, BLOCK_ENUM, GEN_ES
    lab = out.get("regime")
    if lab not in GEN_ENUM:
        fails.append("A3 F5 label outside enum: %s" % lab)
    if GEN_ES.get(lab, lab) not in out.get("daily_log", {}).get("F5", ""):
        fails.append("A3 F5 text does not carry the engine label")
    if regime is not None:
        rg = (regime.get("regimes", {}).get("general") or {}).get("regime") or regime.get("regime")
        if rg != lab:
            fails.append("A3 F5 label ≠ regime.json (%s vs %s)" % (lab, rg))
        for b in ("central_bank", "fiscal"):
            br = (regime.get("regimes", {}).get(b) or {}).get("regime")
            if br is not None and br not in BLOCK_ENUM:
                fails.append("A3 block regime outside enum: %s=%s" % (b, br))
    for k, n in (out.get("streaks") or {}).items():
        seq = (out.get("ledger") or {}).get(k) or []
        cnt = 0
        for x in reversed(seq):
            if seq and x[1] == seq[-1][1]:
                cnt += 1
            else:
                break
        if max(cnt, 1) != n:
            fails.append("A3 streak ≠ ledger: %s %s vs %s" % (k, n, cnt))
        if ("%d.ª" % n) not in text:
            fails.append("A3 streak not in text: %s" % k)
    # 4 — glossary first-use expansion
    for ac, exp in (out.get("glossary") or {}).items():
        m = re.search(r"(?<![\w€])" + re.escape(ac) + r"(?![\w])", text)
        if m:
            after = text[m.end(): m.end() + len(exp) + 4]
            if not after.startswith(" ("):
                fails.append("A4 acronym not expanded at first use: %s" % ac)
    # 5 — determinism + degraded notice
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    if h != out.get("hash"):
        fails.append("A5 hash mismatch")
    for b, m in (out.get("blocks_meta") or {}).items():
        st = m.get("status")
        if st and st != "fresh":
            word = {"stale": "stale", "proxy": "proxy", "unavailable": "no disponible", "degraded": "degradado"}.get(st, st)
            if word not in out.get("header", ""):
                fails.append("A5 degraded block not announced: %s=%s" % (b, st))
    # closing lines (model) — blacklist and digits
    close = out.get("operator_takeaway")
    if close:
        low = close.lower()
        for w in BLACKLIST_CLOSING:
            if re.search(r"\b" + re.escape(w), low):
                fails.append("CLOSE blacklisted word: %s" % w)
        stripped = DATE.sub("", close)
        if re.search(r"\d", stripped):
            fails.append("CLOSE contains digits outside calendar dates")
    return {"pass": not fails, "failures": fails, "checked": ["A1 numbers", "A2 verbs", "A3 enum/streak", "A4 glossary", "A5 hash/degraded", "CLOSE blacklist"]}


def fuzz(ccy: str, root: Optional[str] = None) -> dict:
    """Same JSON → same hash; inverted sparklines → the directional verbs flip; stale block → header says so."""
    from . import narrative as N
    root = root or N.ROOT
    blocks, regime, prev, cal, al = N.load(ccy, root)
    jefe = N.J.compute(None, root)
    a = N.build(ccy, blocks, regime, prev, jefe, cal, al)
    b = N.build(ccy, blocks, regime, prev, jefe, cal, al)
    res = {"same_hash": a["hash"] == b["hash"]}
    inv = copy.deepcopy(blocks)
    for blk in inv.values():
        for sec in ("series", "derived"):
            for e in blk.get(sec, {}).values():
                if isinstance(e, dict) and isinstance(e.get("sparkline"), list) and e["sparkline"]:
                    last = e["sparkline"][-1]
                    e["sparkline"] = [(2 * last - x) if (x is not None and last is not None) else x for x in e["sparkline"]]
    c = N.build(ccy, inv, regime, prev, jefe, cal, al)
    flips = sum(1 for x, y in zip(a["verbs"], c["verbs"]) if x["field"] == y["field"] and x["sign"] != 0 and y["sign"] == -x["sign"])
    nonzero = sum(1 for x in a["verbs"] if x["sign"] != 0 and (x["field"].split(".")[-1].startswith("delta") or x["field"].endswith("reserve_effect")))
    res["verbs_flipped"] = flips
    res["verbs_nonzero_delta"] = nonzero
    res["flip_ok"] = flips == nonzero
    st = copy.deepcopy(blocks)
    st["central_bank"]["source_health"]["status"] = "stale"
    d = N.build(ccy, st, regime, prev, jefe, cal, al)
    res["stale_announced"] = "stale" in d["header"] and check(d)["pass"]
    res["pass"] = bool(res["same_hash"] and res["flip_ok"] and res["stale_announced"])
    return res


def main(argv=None) -> int:
    import argparse, os
    from . import narrative as N
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccy", default="usd")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fuzz", action="store_true")
    a = ap.parse_args(argv)
    rc = 0
    for c in (list(N.SPEC) if a.all else [a.ccy.lower()]):
        p = os.path.join(N.ROOT, "data", c, "agent.json")
        out = json.load(open(p, encoding="utf-8"))
        blocks, regime, _, _, _ = N.load(c)
        g = check(out, blocks, regime)
        line = "%s gate=%s %s" % (c.upper(), "PASS" if g["pass"] else "FAIL", g["failures"] or "")
        if a.fuzz:
            fz = fuzz(c)
            line += " | fuzz=%s %s" % ("PASS" if fz["pass"] else "FAIL", fz)
            rc |= 0 if fz["pass"] else 1
        print(line)
        rc |= 0 if g["pass"] else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
