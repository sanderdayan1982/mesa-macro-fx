"""FAMILIAS-01 M2 — weekly Japan flows (D3 FLOWS), synthetic fixtures.

  python -m ingest.tests_flows_jpy

Does not edit older tests. Does not write data/jpy/fiscal.json.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ingest import flows_jpy as F  # noqa: E402
from ingest.providers_jpy import MofItsProvider  # noqa: E402

NAMES = (
    "its_resident_foreign_equity_weekly",
    "its_resident_foreign_bonds_weekly",
    "its_nonres_jp_equity_weekly",
    "its_foreign_jgb_weekly",
)


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def _csv(rows):
    """rows: (period, {col: number|None}). Header puts Net at 3, 6, 14, 17."""
    head = [""] * 23
    head[1] = "Acquisition"
    head[2] = "Disposition"
    head[3] = "Net"
    head[6] = "Net"
    head[14] = "Net"
    head[17] = "Net"
    lines = [",".join(head)]
    for period, cols in rows:
        row = [""] * 23
        row[0] = period
        for idx, val in cols.items():
            row[idx] = "" if val is None else str(val)
        lines.append(",".join(row))
    return "\n".join(lines) + "\n"


def _saturdays(n, end):
    end_d = date.fromisoformat(end) if isinstance(end, str) else end
    if end_d.weekday() != 5:
        raise AssertionError("%s is not a Saturday" % end_d)
    start = end_d - timedelta(days=7 * (n - 1))
    return [start + timedelta(days=7 * i) for i in range(n)]


def _const_weeks(n, end, equity=1.0, bonds=1.0, nonres=1.0, jgb=1.0, blank=None):
    """blank is {index: series name} whose value is missing."""
    blank = blank or {}
    signed_default = {
        NAMES[0]: equity, NAMES[1]: bonds, NAMES[2]: nonres, NAMES[3]: jgb,
    }
    out = []
    for i, we in enumerate(_saturdays(n, end)):
        signed = dict(signed_default)
        if i in blank:
            signed[blank[i]] = None
        out.append({"week_end": we, "signed": signed})
    return out


def test_tf1(fails):
    """Parser reads cols 3/6/14/17 and the year-change week ending, and refuses a moved layout."""
    text = _csv([
        ("2025．12．21～12．27", {3: 1, 6: 2, 14: 3, 17: 4}),
        ("2025．12．28～2026．1．3", {3: 10, 6: 20, 14: 30, 17: 40}),
        ("2026．11．1～11．7", {3: -6439, 6: -5376, 14: -1052, 17: 13711}),
    ])
    rows = F.parse_its_week(text)
    by = {r["week_end"].isoformat(): r for r in rows}
    check(list(by) == ["2025-12-27", "2026-01-03", "2026-11-07"],
          "T-F1 week-end dates, including 2025．12．28～2026．1．3 → 2026-01-03", fails)
    check(all(date.fromisoformat(k).weekday() == 5 for k in by),
          "T-F1 every week-end is a Saturday", fails)
    y = by["2026-01-03"]
    check(y["raw"][3] == 10 and y["raw"][6] == 20 and y["raw"][14] == 30 and y["raw"][17] == 40,
          "T-F1 columns 3, 6, 14 and 17 on the year-change row", fails)
    check(by["2026-11-07"]["raw"][17] == 13711 and by["2026-11-07"]["raw"][3] == -6439,
          "T-F1 a same-year row keeps the Net cells", fails)
    bad = text.replace("Acquisition", "Bought", 1)
    raised = False
    try:
        F.parse_its_week(bad)
    except F.FlowsDataDegraded:
        raised = True
    check(raised, "T-F1 a header whose Net columns moved is DATA_DEGRADED and is not remapped", fails)
    short = _csv([]).rstrip("\n") + "\n2026．11．1～11．7,1,2,3\n"
    raised = False
    try:
        F.parse_its_week(short)
    except F.FlowsDataDegraded:
        raised = True
    check(raised, "T-F1 a short week row is DATA_DEGRADED, not a silent skip", fails)
    snap = os.path.join(ROOT, "logs", "jpy", "raw", "its_week.csv")
    if os.path.exists(snap):
        parsed = F.parse_its_week(F._decode_its(open(snap, "rb").read()))
        check(len(parsed) >= 52 and all(r["week_end"].weekday() == 5 for r in parsed),
              "T-F1 the downloaded week.csv parses and every week-end is a Saturday", fails)
        last = parsed[-1]
        check(last["signed"]["its_foreign_jgb_weekly"] == last["raw"][17]
              and last["signed"]["its_resident_foreign_equity_weekly"] == -last["raw"][3],
              "T-F1 the snapshot's signs are +1 on col 17 and −1 on col 3", fails)


def test_tf2(fails):
    """R11 sign is inverted once: flow = col14 + col17 − col3 − col6."""
    text = _csv([("2026．11．1～11．7", {3: 100, 6: 40, 14: 10, 17: 7})])
    row = F.parse_its_week(text)[0]
    check(row["signed"]["its_resident_foreign_equity_weekly"] == -100
          and row["signed"]["its_resident_foreign_bonds_weekly"] == -40
          and row["signed"]["its_nonres_jp_equity_weekly"] == 10
          and row["signed"]["its_foreign_jgb_weekly"] == 7,
          "T-F2 resident nets are minus the raw cell, non-resident nets keep the raw cell", fails)
    flow = F.flow_from_signed(row["signed"])
    check(flow == 10 + 7 - 100 - 40 == -123, "T-F2 flow_jpy = col14 + col17 − col3 − col6 = −123", fails)
    check(flow == sum(row["signed"][n] for n in NAMES),
          "T-F2 the signed series sum to the same flow (the sign is not applied a second time)", fails)
    check(flow != 100 + 40 + 10 + 7 and flow != 123,
          "T-F2 the unsigned sum and the twice-inverted result are not the flow", fails)


def test_tf3(fails):
    """Borders: ENTRADA ≥ 80 / exit < 70, SALIDA ≤ 20 / exit > 30. Two prints required."""
    check(F.fold_states([80, 80]) == ["NEUTRO", "ENTRADA"],
          "T-F3 80 then 80 enters ENTRADA; a single 80 does not", fails)
    check(F.fold_states([79.99, 79.99]) == ["NEUTRO", "NEUTRO"],
          "T-F3 79.99 does not enter ENTRADA", fails)
    check(F.fold_states([20, 20]) == ["NEUTRO", "SALIDA"],
          "T-F3 20 then 20 enters SALIDA", fails)
    check(F.fold_states([20.01, 20.01]) == ["NEUTRO", "NEUTRO"],
          "T-F3 20.01 does not enter SALIDA", fails)
    stay = F.fold_states([80, 80, 70, 70])
    check(stay == ["NEUTRO", "ENTRADA", "ENTRADA", "ENTRADA"],
          "T-F3 70 does not exit ENTRADA (exit is < 70)", fails)
    leave = F.fold_states([80, 80, 69.99, 69.99])
    check(leave == ["NEUTRO", "ENTRADA", "ENTRADA", "NEUTRO"],
          "T-F3 two prints below 70 exit ENTRADA to NEUTRO", fails)
    hold = F.fold_states([20, 20, 30, 30])
    check(hold == ["NEUTRO", "SALIDA", "SALIDA", "SALIDA"],
          "T-F3 30 does not exit SALIDA (exit is > 30)", fails)
    out = F.fold_states([20, 20, 30.01, 30.01])
    check(out == ["NEUTRO", "SALIDA", "SALIDA", "NEUTRO"],
          "T-F3 two prints above 30 exit SALIDA to NEUTRO", fails)


def test_tf4(fails):
    """Two publications each way: NEUTRO → ENTRADA → NEUTRO → SALIDA."""
    pcts = [50, 85, 85, 60, 60, 15, 15]
    states = F.fold_states(pcts)
    check(states == ["NEUTRO", "NEUTRO", "ENTRADA", "ENTRADA", "NEUTRO", "NEUTRO", "SALIDA"],
          "T-F4 the publication path is NEUTRO, NEUTRO, ENTRADA, ENTRADA, NEUTRO, NEUTRO, SALIDA", fails)
    confirmed = []
    for s in states:
        if not confirmed or confirmed[-1] != s:
            confirmed.append(s)
    check(confirmed == ["NEUTRO", "ENTRADA", "NEUTRO", "SALIDA"],
          "T-F4 confirmed sequence NEUTRO → ENTRADA → NEUTRO → SALIDA", fails)
    check(F.fold_states([90]) == ["NEUTRO"] and F.fold_states([90, 50, 90]) == ["NEUTRO", "NEUTRO", "NEUTRO"],
          "T-F4 one high print, or two highs that are not consecutive, does not enter", fails)


def test_tf5(fails):
    """[PROV] at n = 25 / 26 / 51 / 52 valid publications."""
    end = "2026-11-07"
    expect = {25: (True, False), 26: (False, True), 51: (False, True), 52: (False, False)}
    for n, (unavail, prov) in expect.items():
        hist = F.replay(_const_weeks(n, end))
        flow = hist[-1]["flow_jpy"]
        check(flow["n"] == n, "T-F5 n=%d counts the valid publications in the window" % n, fails)
        check((flow["state"] == "UNAVAILABLE") is unavail and flow["flows_prov"] is prov,
              "T-F5 n=%d → unavailable=%s flows_prov=%s (got %s / %s)"
              % (n, unavail, prov, flow["state"], flow["flows_prov"]), fails)
        if prov:
            check(flow["flows_reason"] and "[PROV]" in flow["flows_reason"],
                  "T-F5 n=%d carries the [PROV] label" % n, fails)
        if unavail:
            check(flow["flows_prov"] is False and "n=25<26" in (flow["flows_reason"] or ""),
                  "T-F5 n=25 is UNAVAILABLE and not [PROV]", fails)


def test_tf6(fails):
    """A missing series is UNAVAILABLE, does not carry value or state, and resets hysteresis."""
    blank = {27: NAMES[2]}
    hist = F.replay(_const_weeks(33, "2026-11-07", blank=blank))
    pre, gap = hist[26]["flow_jpy"], hist[27]["flow_jpy"]
    check(pre["state"] == "ENTRADA" and pre["value"] not in (None, 0),
          "T-F6 the week before the hole is ENTRADA with a real value", fails)
    check(gap["value"] is None and gap["state"] == "UNAVAILABLE"
          and NAMES[2] in (gap["flows_reason"] or "") and "or 0" not in (gap["flows_reason"] or ""),
          "T-F6 the hole is UNAVAILABLE, names the missing series, and has no value", fails)
    check(gap["value"] != pre["value"] and gap["state"] != pre["state"],
          "T-F6 the hole does not carry the previous value or the previous state", fails)
    check(hist[28]["flow_jpy"]["sum4"] is None and hist[30]["flow_jpy"]["state"] == "UNAVAILABLE",
          "T-F6 the next weeks that still touch the hole stay UNAVAILABLE", fails)
    check(hist[31]["flow_jpy"]["state"] == "NEUTRO" and hist[32]["flow_jpy"]["state"] == "ENTRADA",
          "T-F6 after the reset, one high print is NEUTRO and the second is ENTRADA", fails)
    check(F.fold_states([90, 90, None, 90, 90]) == ["NEUTRO", "ENTRADA", "UNAVAILABLE", "NEUTRO", "ENTRADA"],
          "T-F6 a null percentile resets: the next single 90 does not restore ENTRADA", fails)


def test_tf7(fails):
    """sum4 needs four present weeks. A gap makes it null, including the next three weeks."""
    hist = F.replay(_const_weeks(9, "2026-11-07", blank={4: NAMES[0]}))
    sums = [h["flow_jpy"]["sum4"] for h in hist]
    check(sums[3] == 16 and sums[4] is None and sums[5] is None and sums[6] is None and sums[7] is None,
          "T-F7 sum4 is null on the gap and for the three weeks that still include it", fails)
    check(sums[8] == 16, "T-F7 sum4 returns on the fourth present week after the gap", fails)
    # a missing Saturday in the file is the same hole: dates jump 14 days
    dates = _saturdays(6, "2026-11-07")
    kept = [dates[i] for i in (0, 1, 2, 4, 5)]
    weeks = []
    for we in kept:
        weeks.append({"week_end": we, "signed": {n: 1.0 for n in NAMES}})
    jumped = F.replay(weeks)
    check(jumped[3]["flow_jpy"]["sum4"] is None,
          "T-F7 a 14-day jump (omitted week) makes sum4 null; the gap is not filled", fails)


def test_tf8(fails):
    """STALE is the signed MoF calendar date + 1 day, with no new row. Do not classify."""
    official = {
        2025: {
            date(2025, 1, 1), date(2025, 1, 13), date(2025, 2, 11), date(2025, 2, 23), date(2025, 2, 24),
            date(2025, 3, 20), date(2025, 4, 29), date(2025, 5, 3), date(2025, 5, 4), date(2025, 5, 5),
            date(2025, 5, 6), date(2025, 7, 21), date(2025, 8, 11), date(2025, 9, 15), date(2025, 9, 23),
            date(2025, 10, 13), date(2025, 11, 3), date(2025, 11, 23), date(2025, 11, 24),
        },
        2026: {
            date(2026, 1, 1), date(2026, 1, 12), date(2026, 2, 11), date(2026, 2, 23), date(2026, 3, 20),
            date(2026, 4, 29), date(2026, 5, 3), date(2026, 5, 4), date(2026, 5, 5), date(2026, 5, 6),
            date(2026, 7, 20), date(2026, 8, 11), date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23),
            date(2026, 10, 12), date(2026, 11, 3), date(2026, 11, 23),
        },
        2027: {
            date(2027, 1, 1), date(2027, 1, 11), date(2027, 2, 11), date(2027, 2, 23), date(2027, 3, 21),
            date(2027, 3, 22), date(2027, 4, 29), date(2027, 5, 3), date(2027, 5, 4), date(2027, 5, 5),
            date(2027, 7, 19), date(2027, 8, 11), date(2027, 9, 20), date(2027, 9, 23), date(2027, 10, 11),
            date(2027, 11, 3), date(2027, 11, 23),
        },
    }
    for year, expect in official.items():
        got = F.holidays_in_year(year)
        check(got == expect, "T-F8 %d holidays match the Cabinet Office list (%s)" % (
            year, "extra %s missing %s" % (sorted(got - expect), sorted(expect - got))), fails)
    check(F.release_date(date(2026, 11, 7)) == date(2026, 11, 12),
          "T-F8 week ending 2026-11-07 is released Thursday 2026-11-12", fails)
    check(F.release_date(date(2025, 12, 27)) == date(2026, 1, 2),
          "T-F8 Thursday 2026-01-01 is a holiday, so the release is Friday 2026-01-02", fails)
    # Signed rule only. The published schedule lists 2026-11-27 because Monday 11-23 is a holiday;
    # Thursday 11-26 is not, so the signed rule stays on Thursday. That gap is not papered over.
    check(F.release_date(date(2026, 11, 21)) == date(2026, 11, 26) and not F.is_jp_holiday(date(2026, 11, 26)),
          "T-F8 week ending 2026-11-21 releases on Thursday 2026-11-26 under the signed rule", fails)

    fresh = F.replay(_const_weeks(40, "2026-11-07"))
    base = fresh[-1]["flow_jpy"]
    check(base["state"] in ("ENTRADA", "SALIDA", "NEUTRO"),
          "T-F8 a current file still classifies on the release day of the next week", fails)
    on_time = F._apply_stale(dict(base), date(2026, 11, 19))
    late = F._apply_stale(dict(base), date(2026, 11, 20))
    check(on_time["state"] == base["state"] and on_time["state"] != "STALE",
          "T-F8 2026-11-19 (the Thursday release) is not STALE", fails)
    check(late["state"] == "STALE" and late["state"] not in ("ENTRADA", "SALIDA", "NEUTRO")
          and late["value"] == base["value"] and late["week_end"] == "2026-11-07",
          "T-F8 2026-11-20 is STALE: no new state, the last week_end and value stay", fails)

    held = F.replay(_const_weeks(40, "2025-12-20"))[-1]["flow_jpy"]
    friday = F._apply_stale(dict(held), date(2026, 1, 2))
    saturday = F._apply_stale(dict(held), date(2026, 1, 3))
    check(friday["state"] != "STALE" and saturday["state"] == "STALE"
          and "2026-01-02" in (saturday["flows_reason"] or ""),
          "T-F8 the holiday release is Friday 2026-01-02; STALE starts 2026-01-03, not on the Friday", fails)


def test_tf13(fails):
    """Real release dates are not STALE. Signed Thursday/Friday dates are not replaced by a table."""
    check(F.release_date(date(2026, 11, 21)) == date(2026, 11, 26),
          "T-F13 week 15–21 Nov 2026 still has signed release Thursday 26 Nov (real release is 27 Nov)", fails)
    check(F.release_date(date(2026, 12, 26)) == date(2026, 12, 31),
          "T-F13 week 20–26 Dec 2026 still has signed release Thursday 31 Dec", fails)
    check(F.release_date(date(2027, 1, 2)) == date(2027, 1, 7),
          "T-F13 week 27 Dec–2 Jan still has signed release Thursday 7 Jan 2027", fails)
    nov = F.replay(_const_weeks(40, "2026-11-14"))[-1]["flow_jpy"]
    on_nov = F._apply_stale(dict(nov), date(2026, 11, 27))
    check(on_nov["state"] != "STALE" and on_nov["week_end"] == "2026-11-14",
          "T-F13 week 15–21 Nov 2026 is not STALE on its real release date 27 Nov 2026", fails)
    dec = F.replay(_const_weeks(40, "2026-12-19"))[-1]["flow_jpy"]
    on_jan = F._apply_stale(dict(dec), date(2027, 1, 7))
    check(on_jan["state"] != "STALE" and on_jan["week_end"] == "2026-12-19",
          "T-F13 the 7 Jan 2027 combined release (20–26 Dec and 27 Dec–2 Jan) is not STALE on 7 Jan", fails)


def test_tf9(fails):
    """A MoF revision appends rev=1. Previous states, and the values they used, stay equal."""
    weeks = []
    for i, we in enumerate(_saturdays(40, "2026-11-07")):
        weeks.append({"week_end": we, "signed": {NAMES[0]: 0.0, NAMES[1]: 0.0, NAMES[2]: 0.0, NAMES[3]: float(i)}})
    tmp = tempfile.mkdtemp(prefix="flows-tf9-")
    try:
        path = os.path.join(tmp, "its_vintage.csv")
        F.update_vintage(path, weeks, "2026-01-01T00:00:00Z")
        before_txt = open(path, encoding="utf-8").read()
        first = F._first_map(F._read_vintage(path))
        hist1 = F.replay(F._weeks_from_first(weeks, first))
        revised = []
        for i, w in enumerate(weeks):
            signed = dict(w["signed"])
            if i == 10:
                signed[NAMES[3]] = signed[NAMES[3]] + 1000.0
            revised.append({"week_end": w["week_end"], "signed": signed})
        added = F.update_vintage(path, revised, "2026-02-01T00:00:00Z")
        after_txt = open(path, encoding="utf-8").read()
        check(after_txt.startswith(before_txt) and len(after_txt) > len(before_txt),
              "T-F9 the vintage file only grows; the earlier rows are untouched", fails)
        rev_rows = [r for r in added if r["week"] == weeks[10]["week_end"].isoformat() and r["rev"] == 1]
        check(any(r["series"] == NAMES[3] and r["value"] == 1010.0 for r in rev_rows)
              and any(r["series"] == "flow_jpy" for r in rev_rows),
              "T-F9 the changed week appends rev=1 for the series and for flow_jpy", fails)
        first2 = F._first_map(F._read_vintage(path))
        hist2 = F.replay(F._weeks_from_first(revised, first2))
        check([h["flow_jpy"]["state"] for h in hist1] == [h["flow_jpy"]["state"] for h in hist2],
              "T-F9 every previous state is unchanged (no repaint)", fails)
        check([h["flow_jpy"]["value"] for h in hist1] == [h["flow_jpy"]["value"] for h in hist2],
              "T-F9 the values the states used are the first vintage values", fails)
        used = hist2[10]["series"][NAMES[3]]["value"]
        check(used == 10.0 and revised[10]["signed"][NAMES[3]] == 1010.0 and used != 1010.0,
              "T-F9 week 10 still feeds the state with 10, not the revised 1010", fails)
    finally:
        shutil.rmtree(tmp)


def test_tf10(fails):
    """Additive: fiscal.json and foreign_jgb_flow_weekly stay byte-identical, vote stays 0."""
    fiscal_path = os.path.join(ROOT, "data", "jpy", "fiscal.json")
    before = open(fiscal_path, "rb").read()
    import json
    foreign_before = json.loads(before.decode("utf-8"))["series"]["foreign_jgb_flow_weekly"]
    tmp = tempfile.mkdtemp(prefix="flows-tf10-")
    try:
        text = _csv([("2026．11．1～11．7", {3: 5, 6: 6, 14: 7, 17: 8})])
        csv_path = os.path.join(tmp, "week.csv")
        open(csv_path, "w", encoding="utf-8").write(text)
        doc = F.publish(
            tmp, today=date(2026, 11, 16), now="2026-11-16T00:00:00Z",
            csv_path=csv_path,
            vintage_path=os.path.join(tmp, "its_vintage.csv"),
            out_path=os.path.join(tmp, "FLOWS_weekly.json"),
            chf_dir=os.path.join(tmp, "no-chf"),
            usd_dir=os.path.join(tmp, "no-usd"),
        )
        after = open(fiscal_path, "rb").read()
        foreign_after = json.loads(after.decode("utf-8"))["series"]["foreign_jgb_flow_weekly"]
        check(before == after and foreign_before == foreign_after,
              "T-F10 fiscal.json and foreign_jgb_flow_weekly are byte-identical after publish", fails)
        check(doc["vote"] == 0 and doc["blocked_entry"] is False and doc["shadow"] is True,
              "T-F10 the flows document is vote 0 and not blocked_entry", fails)
        tiny = _csv([("2026．11．1～11．7", {3: 1, 6: 2, 14: 3, 17: 13711, 21: 9})])
        legacy = MofItsProvider.parse(tiny, since=None)
        check(set(legacy) == {"its_foreign_jgb_weekly", "its_foreign_tbill_weekly", "its_resident_foreign_bonds_weekly"}
              and legacy["its_foreign_jgb_weekly"][-1][1] == 13711
              and legacy["its_resident_foreign_bonds_weekly"][-1][1] == 2,
              "T-F10 MofItsProvider.parse still returns the raw col 17 and col 6 series, not the signed flow", fails)
    finally:
        shutil.rmtree(tmp)


def test_tf11(fails):
    """Currencies without a weekly capture are NA. A monthly file is never copied in. CHF has no state."""
    tmp = tempfile.mkdtemp(prefix="flows-tf11-")
    try:
        os.makedirs(os.path.join(tmp, "history", "eur"))
        os.makedirs(os.path.join(tmp, "history", "usd"))
        os.makedirs(os.path.join(tmp, "history", "chf"))
        open(os.path.join(tmp, "history", "eur", "monthly.csv"), "w", encoding="utf-8").write(
            "date,monthly\n2026-09-30,10\n2026-10-31,11\n")
        open(os.path.join(tmp, "history", "usd", "WRESBAL.csv"), "w", encoding="utf-8").write(
            "date,WRESBAL\n2026-10-28,1\n2026-11-04,2\n")
        # eight Fridays so sum4 and z52 exist
        lines = ["date,snbgwdchfsgw:TG"]
        start = date(2026, 9, 18)
        for i in range(8):
            lines.append("%s,%d" % ((start + timedelta(days=7 * i)).isoformat(), 100 + i))
        open(os.path.join(tmp, "history", "chf", "snbgwdchfsgw:TG.csv"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
        text = _csv([("2026．11．1～11．7", {3: 1, 6: 1, 14: 1, 17: 1})])
        csv_path = os.path.join(tmp, "week.csv")
        open(csv_path, "w", encoding="utf-8").write(text)
        doc = F.publish(
            tmp, today=date(2026, 11, 16), now="2026-11-16T00:00:00Z",
            csv_path=csv_path,
            vintage_path=os.path.join(tmp, "its_vintage.csv"),
            out_path=os.path.join(tmp, "FLOWS_weekly.json"),
            chf_dir=os.path.join(tmp, "history", "chf"),
            usd_dir=os.path.join(tmp, "history", "usd"),
        )
        cur = doc["currencies"]
        for ccy in ("EUR", "GBP", "AUD", "NZD", "CAD", "USD"):
            check(cur[ccy] is None, "T-F11 %s is NA" % ccy, fails)
        chf = cur["CHF"]["sight_deposits_total_weekly"]
        check(set(chf) == {"value", "sum4", "z52"} and chf["value"] == 107
              and chf["sum4"] == 104 + 105 + 106 + 107 and "state" not in chf,
              "T-F11 CHF sight deposits are value/sum4/z52 only, with no state", fails)
        check(cur["JPY"]["flow_jpy"]["value"] == 0 and cur["JPY"]["flow_jpy"]["value"] not in (10, 11),
              "T-F11 JPY is the week-file flow (1+1−1−1), not the EUR monthly 10/11", fails)
    finally:
        shutil.rmtree(tmp)


def test_tf14(fails):
    """WMTSECL1 is the seventh H.4.1 series, same FRED scale, informative only."""
    src = open(os.path.join(ROOT, "ingest", "run.py"), encoding="utf-8").read()
    check('H41 = ["WALCL", "TREAST", "WSHOMCB", "WLCFLPCL", "WTREGEN", "WRESBAL", "WMTSECL1"]' in src,
          "T-F14 WMTSECL1 is the seventh id on the existing H.4.1 fredgraph list", fails)
    from ingest.providers_usd import FredProvider, UNITS_TO_M
    six = ("WALCL", "TREAST", "WSHOMCB", "WLCFLPCL", "WTREGEN", "WRESBAL")
    check(all(UNITS_TO_M[s] == 1 for s in six) and UNITS_TO_M["WMTSECL1"] == 1,
          "T-F14 WMTSECL1 uses the same $ millions scale (factor 1) as the six", fails)
    check(FredProvider._scale("WMTSECL1", [("2026-11-11", 2524189.0)]) == [("2026-11-11", 2524189.0)],
          "T-F14 the FRED scale does not rescale WMTSECL1", fails)
    tmp = tempfile.mkdtemp(prefix="flows-tf14-")
    try:
        os.makedirs(os.path.join(tmp, "history", "usd"))
        lines = ["date,WMTSECL1"]
        start = date(2026, 9, 16)
        for i in range(8):
            lines.append("%s,%d" % ((start + timedelta(days=7 * i)).isoformat(), 1000 + i))
        open(os.path.join(tmp, "history", "usd", "WMTSECL1.csv"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
        # the six series sitting beside it must not be read as custody
        open(os.path.join(tmp, "history", "usd", "WRESBAL.csv"), "w", encoding="utf-8").write(
            "date,WRESBAL\n2026-11-04,9\n")
        text = _csv([("2026．11．1～11．7", {3: 1, 6: 1, 14: 1, 17: 1})])
        csv_path = os.path.join(tmp, "week.csv")
        open(csv_path, "w", encoding="utf-8").write(text)
        doc = F.publish(
            tmp, today=date(2026, 11, 16), now="2026-11-16T00:00:00Z",
            csv_path=csv_path,
            vintage_path=os.path.join(tmp, "its_vintage.csv"),
            out_path=os.path.join(tmp, "FLOWS_weekly.json"),
            chf_dir=os.path.join(tmp, "no-chf"),
            usd_dir=os.path.join(tmp, "history", "usd"),
        )
        usd = doc["currencies"]["USD"]["WMTSECL1"]
        check(set(usd) == {"value", "sum4", "z52"} and "state" not in usd,
              "T-F14 USD custody is value/sum4/z52 only, with no state", fails)
        check(usd["value"] == 1007 and usd["sum4"] == 1004 + 1005 + 1006 + 1007,
              "T-F14 sum4 is the last four weekly custody prints", fails)
        check(doc["currencies"]["USD"].get("WRESBAL") is None and doc.get("reason") is None,
              "T-F14 reserves are not substituted for custody, and the absent-series reason is cleared", fails)
    finally:
        shutil.rmtree(tmp)


def test_tf12(fails):
    """The thresholds in the module are the signed table, not a searched parameter."""
    check((F.ENTRADA_ENTRY, F.ENTRADA_EXIT, F.SALIDA_ENTRY, F.SALIDA_EXIT) == (80, 70, 20, 30),
          "T-F12 entry/exit borders are 80/70 and 20/30", fails)
    check(F.WINDOW == 52 and F.HYSTERESIS_PUBS == 2 and F.PROV_MIN == 26,
          "T-F12 window 52, hysteresis 2 publications, [PROV] from n=26", fails)
    check(F.VOTE == 0 and F.BLOCKED_ENTRY is False, "T-F12 VOTE is 0 and blocked_entry is false", fails)
    src = open(F.__file__, encoding="utf-8").read()
    for line in ("ENTRADA_ENTRY = 80", "ENTRADA_EXIT = 70", "SALIDA_ENTRY = 20", "SALIDA_EXIT = 30",
                 "WINDOW = 52", "HYSTERESIS_PUBS = 2", "PROV_MIN = 26"):
        check(line in src, "T-F12 source contains %s" % line, fails)
    check("or 0" not in src, "T-F12 the flows module does not fill a missing leg with 0", fails)


def main() -> int:
    fails = []
    test_tf1(fails)
    test_tf2(fails)
    test_tf3(fails)
    test_tf4(fails)
    test_tf5(fails)
    test_tf6(fails)
    test_tf7(fails)
    test_tf8(fails)
    test_tf13(fails)
    test_tf9(fails)
    test_tf10(fails)
    test_tf11(fails)
    test_tf14(fails)
    test_tf12(fails)
    print("%d failures" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
