"""t332u: the GoC deposits-at-banks card shows the official next publication date.

Presentation only. The date 2026-12-26 is already in fiscal.json
(government_deposits_banks.next_publication). New tests; no existing
tests, thresholds or formulas are edited.
  python -m ingest.tests_cad_deposits_government_next_pub
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "cad" / "index.html").read_text(encoding="utf-8")
FISCAL = ROOT / "data" / "cad" / "fiscal.json"
BANKING = ROOT / "data" / "cad" / "banking.json"


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def test_json_has_official_next_publication(fails):
    fiscal = json.loads(FISCAL.read_text(encoding="utf-8"))
    banking = json.loads(BANKING.read_text(encoding="utf-8"))
    gov = fiscal["series"]["government_deposits_banks"]
    check(gov.get("next_publication") == "2026-12-26",
          "fiscal government_deposits_banks.next_publication is 2026-12-26", fails)
    check(gov.get("date") == "2026-09-01",
          "fiscal government_deposits_banks date stays 2026-09-01", fails)
    dep = banking["series"]["deposits_government"]
    check(dep.get("date") == "2026-09-01" and dep.get("value") == 3407.0,
          "banking deposits_government keeps official 1-sep value 3407", fails)


def test_card_wires_fiscal_next_publication(fails):
    check("ent.next_publication||opts.next_publication" in HTML,
          "card() falls back to opts.next_publication for the on-screen date", fails)
    needle = "card('banking','deposits_government','GoC deposits at banks',fB,{next_publication:(e('fiscal','government_deposits_banks')||{}).next_publication})"
    check(needle in HTML,
          "GoC deposits at banks card reads next_publication from fiscal government_deposits_banks", fails)


def test_rendered_card_src_contains_26_dic(fails):
    # Mirror of the card() nextPub line, with the same fallback the page uses.
    fiscal = json.loads(FISCAL.read_text(encoding="utf-8"))
    banking = json.loads(BANKING.read_text(encoding="utf-8"))
    ent = banking["series"]["deposits_government"]
    opts_next = fiscal["series"]["government_deposits_banks"].get("next_publication")
    nxt = ent.get("next_publication") or opts_next
    src = "%s%s" % (ent.get("date") or "", (" · próxima publicación esperada %s" % nxt) if nxt else "")
    check("2026-09-01" in src and "próxima publicación esperada 2026-12-26" in src,
          "card source line paints 2026-09-01 and next publication 2026-12-26", fails)


def main():
    fails = []
    test_json_has_official_next_publication(fails)
    test_card_wires_fiscal_next_publication(fails)
    test_rendered_card_src_contains_26_dic(fails)
    print("fails=%d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
