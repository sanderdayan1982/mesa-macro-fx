#!/usr/bin/env python3
"""Agente Doctor Autónomo MMT (G8 Mesa Macro FX) — Diagnóstico, Auto-Reparación,
Auto-Descubrimiento de URLs/Columnas y Sustitución Multi-Fuente de Feeds.

Regla de prioridad de frescura institucional MMT:
  1.º Diaria (prioridad máxima: reservas, TGA/depósitos del Tesoro, OMO/STR/ON RRP, tipos overnight y curva)
  2.º Semanal (balance del Banco Central y subastas cuando no exista serie diaria)
  3.º Mensual (ÚNICAMENTE cuando no queda más remedio: agregados M2/M3/crédito o cierres fiscales mensuales)

Capacidades autónomas de curación y sustitución (--auto-repair):
  - Etapa 1 (Re-ingesta): Re-ejecuta `python3 -m ingest.run --ccy <ccy> --lane all` para divisas con atraso o fallo.
  - Etapa 2 (Auto-descubrimiento de enlaces oficiales): Si una URL rotó (AOFM Data Hub, NZDM, Finanzagentur,
    AFT Francia, BoJ mei/juqp, EFV Suiza), rastrea la página índice oficial con escalera anti-bloqueo
    (curl_cffi -> curl -> requests -> urllib) y descarga el nuevo archivo en `logs/<ccy>/raw/` e `history/<ccy>/`.
  - Etapa 3 (Sustitución Multi-Fuente / Espejos Institucionales): Si un feed primario sigue caído o atrasado,
    consulta espejos oficiales alternativos (FRED CSV sin API key, BCE SDMX, BoC Valet, SNB Data Portal) o
    promociona la serie operativa diaria/semanal v0.4 (`derived.*`) siguiendo `1.º Diaria -> 2.º Semanal -> 3.º Mensual`,
    actualiza `history/<ccy>/<id>.csv`, y reconstruye los bloques JSON.
  - Etapa 4 (Boletín Operativo MMT): Genera el reporte institucional de inyecciones/drenajes de Bancos Centrales
    y Tesoros (`data/mesa/liquidity_report.json` y `.agent/report.md`).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ingest.liquidity_reporter import generate_all_reports

CCYS = ("usd", "eur", "gbp", "jpy", "chf", "cad", "aud", "nzd")
BLOCKS = ("central_bank", "fiscal", "rates", "banking")

MAX_AGE_BY_FREQ = {
    "daily": 7,
    "weekly": 16,
    "ten_day": 21,
    "monthly": 65,
    "quarterly": 135,
    "event": 365,
}

# Registro institucional de espejos alternativos (FRED CSV sin API key / endpoints secundarios / series v0.4)
# Ordenado estrictamente: 1.º Diaria -> 2.º Semanal -> 3.º Mensual (solo último recurso)
CROSS_SOURCE_MIRRORS: Dict[str, Dict[str, dict]] = {
    "usd": {
        "central_bank.reserves": {"fred": "WRESBAL", "freq": "weekly"},
        "central_bank.total_assets": {"fred": "WALCL", "freq": "weekly"},
        "central_bank.on_rrp": {"fred": "RRPONTSYD", "freq": "daily"},
        "fiscal.tga_balance": {"fred": "WTREGEN", "freq": "weekly"},
        "rates.sofr": {"fred": "SOFR", "freq": "daily"},
        "rates.effr": {"fred": "DFF", "freq": "daily"},
        "rates.iorb": {"fred": "IORB", "freq": "daily"},
        "rates.ust_2y": {"fred": "DGS2", "freq": "daily"},
        "rates.ust_10y": {"fred": "DGS10", "freq": "daily"},
        "rates.tbill_3m": {"fred": "DTB3", "freq": "daily"},
    },
    "eur": {
        "rates.estr": {"fred": "ECBESTRVOLWGTTRMDMNRT", "freq": "daily"},
        "rates.deposit_facility": {"fred": "ECBDFR", "freq": "daily"},
        "rates.mro_rate": {"fred": "ECBMRRFR", "freq": "daily"},
        "rates.mlf_rate": {"fred": "ECBMLFR", "freq": "daily"},
        "fiscal.fr_it_es_eu_issuance": {"promote_derived": "settled_all", "freq": "daily"},
    },
    "gbp": {
        "rates.sonia": {"fred": "IUDSOIA", "freq": "daily"},
        "rates.bank_rate": {"fred": "BOERUKM", "freq": "daily"},
        "central_bank.str_auction_result": {"promote_derived": "str_allotted_weekly", "freq": "weekly"},
        "central_bank.iltr_auction_result": {"promote_derived": "iltr_allotted_weekly", "freq": "weekly"},
        "central_bank.government_account": {"promote_derived": "exchequer_flow_weekly_proxy", "freq": "weekly"},
        "fiscal.dmo_gilt_auction": {"promote_derived": "gilt_settled_daily", "freq": "daily"},
        "fiscal.dmo_tbill_tender": {"promote_derived": "tbill_net_daily", "freq": "daily"},
    },
    "jpy": {
        "rates.tona": {"fred": "IRSTCI01JPM156N", "freq": "monthly"},
        "rates.jgb_10y": {"fred": "IRLTLT01JPM156N", "freq": "monthly"},
        "fiscal.net_issuance_private_daily": {"promote_derived": "net_issuance_private_daily", "freq": "daily"},
        "central_bank.ops_net_daily": {"promote_derived": "ops_net_daily", "freq": "daily"},
    },
    "chf": {
        "central_bank.bills_maturity_ladder": {"promote_derived": "bills_maturing_4w", "freq": "weekly"},
        "fiscal.auction_calendar": {"promote_derived": "mmdrc_settled", "freq": "daily"},
        "fiscal.bonds_outstanding": {"promote_derived": "bonds_outstanding_asof", "freq": "monthly"},
    },
    "cad": {
        "rates.corra": {"boc_valet": "AVG.INTWO", "freq": "daily"},
        "rates.policy_rate": {"boc_valet": "V39079", "freq": "daily"},
        "rates.goc_2y": {"boc_valet": "BD.CDN.2YR.DQ.YLD", "freq": "daily"},
        "rates.goc_5y": {"boc_valet": "BD.CDN.5YR.DQ.YLD", "freq": "daily"},
        "rates.goc_10y": {"boc_valet": "BD.CDN.10YR.DQ.YLD", "freq": "daily"},
        "central_bank.settlement_balances": {"boc_valet": "V36612", "freq": "weekly"},
    },
    "aud": {
        "central_bank.omo_takeup_weekly": {"promote_derived": "omo_takeup_weekly", "freq": "weekly"},
        "fiscal.aofm_bond_tenders": {"promote_derived": "tb_settled_daily", "freq": "daily"},
        "fiscal.aofm_note_tenders": {"promote_derived": "tn_settled_daily", "freq": "daily"},
        "fiscal.tnotes_on_issue": {"promote_derived": "tn_stock_daily", "freq": "daily"},
        "rates.tnote_3m": {"promote_derived": "tn_wa_yield", "freq": "weekly"},
    },
    "nzd": {
        "fiscal.treasury_residual_cash": {"promote_derived": "residual_flow_daily", "freq": "daily"},
        "fiscal.nzdm_ecp_on_issue": {"promote_derived": "ecp_on_issue", "freq": "monthly"},
        "rates.ocr": {"step_ffill_from": "D12:settlement_cash", "history_csv": "B2:INM.DP1.N.csv", "freq": "daily"},
        "rates.odr": {"step_ffill_from": "D12:settlement_cash", "history_csv": "B2:INM.DD1.N.csv", "freq": "daily"},
        "rates.orrf_rate": {"step_ffill_from": "D12:settlement_cash", "history_csv": "B2:INM.DD2.N.csv", "freq": "daily"},
    },
}

DISCOVERY_ENDPOINTS: Dict[str, List[dict]] = {
    "aud": [
        {
            "name": "aofm_data_hub",
            "index_url": "https://www.aofm.gov.au/data-hub",
            "patterns": {
                "aofm_tb_issuance.xlsx": r'href="([^"]*treasury[-_]bonds?[-_]issuance[^"]*\.xlsx)"',
                "aofm_tn_issuance.xlsx": r'href="([^"]*treasury[-_]notes?[-_]issuance[^"]*\.xlsx)"',
                "aofm_tib_issuance.xlsx": r'href="([^"]*treasury[-_]indexed[-_]bonds?[-_]issuance[^"]*\.xlsx)"',
            },
            "base": "https://www.aofm.gov.au",
        }
    ],
    "eur": [
        {
            "name": "aft_france_xlsx",
            "index_url": "https://www.aft.gouv.fr/en/oat-auctions-history",
            "patterns": {
                "aft_hist_mlt.xlsx": r'href="([^"]*_hist_mlt\.xlsx)"',
            },
            "base": "https://www.aft.gouv.fr",
        }
    ],
    "jpy": [
        {
            "name": "boj_mei_holdings",
            "index_url": "https://www.boj.or.jp/en/statistics/boj/other/mei/index.htm",
            "patterns": {
                "mei_latest.xlsx": r'href="([^"]*mei\d{6}\.xlsx)"',
            },
            "base": "https://www.boj.or.jp",
        }
    ],
}


def _load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _http_fetch(url: str, binary: bool = False, timeout: int = 8) -> Optional[bytes | str]:
    """Escalera resiliente de descarga HTTP: curl -> urllib con User-Agent de navegador."""
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    try:
        r = subprocess.run(
            ["curl", "-sSL", "--connect-timeout", "3", "--max-time", str(min(timeout, 8)), "-A", ua, url],
            capture_output=True,
            timeout=min(timeout, 8) + 2,
        )
        if r.returncode == 0 and r.stdout and not r.stdout[:25].lower().startswith(b"<!doctype html><html"):
            return r.stdout if binary else r.stdout.decode("utf-8", errors="replace")
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=min(timeout, 5)) as resp:
            blob = resp.read()
            return blob if binary else blob.decode("utf-8", errors="replace")
    except Exception:
        return None


def _append_csv_points(csv_path: str, col_name: str, points: List[Tuple[str, float]]) -> int:
    """Fusiona nuevos puntos (date, value) en history/<ccy>/<file>.csv sin perder histórico."""
    if not points:
        return 0
    existing: Dict[str, float] = {}
    if os.path.exists(csv_path):
        try:
            with open(csv_path, encoding="utf-8") as f:
                for row in csv.reader(f):
                    if len(row) >= 2 and row[0] != "date" and row[1] not in ("", "None"):
                        try:
                            existing[row[0]] = float(row[1])
                        except ValueError:
                            pass
        except Exception:
            pass
    before = len(existing)
    for d, v in points:
        if d and v is not None:
            existing[d] = v
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", col_name])
        for d in sorted(existing):
            w.writerow([d, existing[d]])
    return max(0, len(existing) - before)


def _fetch_fred_series(fred_id: str, min_date: str = "2024-01-01") -> List[Tuple[str, float]]:
    """Descarga serie alternativa desde FRED (CSV público sin API key)."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
    txt = _http_fetch(url, binary=False, timeout=25)
    if not txt or not isinstance(txt, str) or "DATE" not in txt.upper():
        return []
    out: List[Tuple[str, float]] = []
    for row in csv.reader(io.StringIO(txt)):
        if len(row) >= 2 and re.match(r"^\d{4}-\d{2}-\d{2}$", row[0]) and row[0] >= min_date:
            try:
                out.append((row[0], float(row[1])))
            except ValueError:
                continue
    return out


def _fetch_boc_valet_series(series_id: str, recent: int = 60) -> List[Tuple[str, float]]:
    """Descarga serie alternativa desde Bank of Canada Valet JSON API."""
    url = f"https://www.bankofcanada.ca/valet/observations/{series_id}/json?recent={recent}"
    txt = _http_fetch(url, binary=False, timeout=25)
    if not txt or not isinstance(txt, str):
        return []
    try:
        obj = json.loads(txt)
        out: List[Tuple[str, float]] = []
        for obs in obj.get("observations", []):
            d = obs.get("d")
            val_obj = obs.get(series_id)
            v = val_obj.get("v") if isinstance(val_obj, dict) else None
            if d and v not in (None, ""):
                out.append((d, float(v)))
        return sorted(out)
    except Exception:
        return []


def discover_and_heal_endpoints(ccy: str) -> List[str]:
    """Rastrea páginas índice oficiales cuando un enlace directo (.xlsx/.csv) ha cambiado."""
    actions: List[str] = []
    specs = DISCOVERY_ENDPOINTS.get(ccy, [])
    if not specs:
        return actions
    hist_dir = os.path.join(ROOT, "history", ccy)
    raw_dir = os.path.join(ROOT, "logs", ccy, "raw")
    for sp in specs:
        html = _http_fetch(sp["index_url"], binary=False, timeout=25)
        if not html or not isinstance(html, str):
            continue
        for target_fn, pat in sp["patterns"].items():
            m = re.search(pat, html, flags=re.IGNORECASE)
            if not m:
                continue
            href = m.group(1)
            full_url = href if href.startswith("http") else (sp["base"].rstrip("/") + "/" + href.lstrip("/"))
            blob = _http_fetch(full_url, binary=True, timeout=45)
            if blob and isinstance(blob, (bytes, bytearray)) and len(blob) > 500:
                for dest_dir in (hist_dir, raw_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                    with open(os.path.join(dest_dir, target_fn), "wb") as f:
                        f.write(blob)
                actions.append(f"{ccy.upper()}: URL auto-descubierta en {sp['name']} -> {target_fn} ({len(blob)} bytes)")
    return actions


def substitute_or_heal_series(ccy: str, bad_series_keys: List[str]) -> Tuple[List[str], bool]:
    """Aplica sustitución multi-fuente o promoción de serie operativa diaria/semanal v0.4."""
    actions: List[str] = []
    rebuilt_needed = False
    mirrors = CROSS_SOURCE_MIRRORS.get(ccy, {})
    hist_dir = os.path.join(ROOT, "history", ccy)
    data_dir = os.path.join(ROOT, "data", ccy)

    for full_key in bad_series_keys:
        if "." not in full_key:
            continue
        bname, skey = full_key.split(".", 1)
        blk_path = os.path.join(data_dir, f"{bname}.json")
        blk = _load_json(blk_path)
        ser_entry = (blk.get("series") or {}).get(skey) or {}
        src_id = ser_entry.get("source_id")
        mspec = mirrors.get(full_key) or {}

        # 1. Espejo FRED (prioridad diaria/semanal)
        if mspec.get("fred") and src_id:
            pts = _fetch_fred_series(mspec["fred"])
            if pts:
                csv_name = src_id.replace("/", "_").replace("|", "_").replace(" ", "_") + ".csv"
                added = _append_csv_points(os.path.join(hist_dir, csv_name), src_id, pts)
                actions.append(f"{ccy.upper()} {full_key}: sustituido/actualizado vía espejo FRED ({mspec['fred']}, +{added} obs, freq={mspec['freq']})")
                rebuilt_needed = True
                continue

        # 2. Espejo Bank of Canada Valet API
        if mspec.get("boc_valet") and src_id:
            pts = _fetch_boc_valet_series(mspec["boc_valet"])
            if pts:
                csv_name = src_id.replace("/", "_").replace("|", "_").replace(" ", "_") + ".csv"
                added = _append_csv_points(os.path.join(hist_dir, csv_name), src_id, pts)
                actions.append(f"{ccy.upper()} {full_key}: sustituido/actualizado vía BoC Valet ({mspec['boc_valet']}, +{added} obs)")
                rebuilt_needed = True
                continue

        # 3. Forward-fill de tipos escalón del corredor sobre rejilla diaria fresca
        if mspec.get("step_ffill_from") and mspec.get("history_csv"):
            anchor_csv = os.path.join(hist_dir, mspec["step_ffill_from"] + ".csv")
            target_csv = os.path.join(hist_dir, mspec["history_csv"])
            if os.path.exists(anchor_csv) and os.path.exists(target_csv):
                try:
                    anchor_dates = [r[0] for r in csv.reader(open(anchor_csv, encoding="utf-8")) if len(r) >= 2 and r[0] != "date"]
                    target_rows = [(r[0], float(r[1])) for r in csv.reader(open(target_csv, encoding="utf-8")) if len(r) >= 2 and r[0] != "date" and r[1] not in ("", "None")]
                    if anchor_dates and target_rows and anchor_dates[-1] > target_rows[-1][0]:
                        last_val = target_rows[-1][1]
                        new_pts = [(d, last_val) for d in anchor_dates if d > target_rows[-1][0]]
                        _append_csv_points(target_csv, mspec["history_csv"][:-4], new_pts)
                        actions.append(f"{ccy.upper()} {full_key}: extendido en rejilla diaria ({anchor_dates[-1]})")
                        rebuilt_needed = True
                        continue
                except Exception:
                    pass

        # 4. Promoción directa desde derived.* (v0.4 diario/semanal) hacia series.*
        deriv_key = mspec.get("promote_derived") or skey
        deriv_entry = (blk.get("derived") or {}).get(deriv_key)
        if isinstance(deriv_entry, dict) and deriv_entry.get("status") == "fresh" and deriv_entry.get("value") is not None:
            blk.setdefault("series", {})[skey] = dict(
                deriv_entry,
                substituted_by=f"derived.{deriv_key}",
                equivalence_note=f"Auto-sustituido por Agente Doctor desde derived.{deriv_key} (prioridad {mspec.get('freq', 'diaria/semanal')})",
            )
            wired = {k: e for k, e in blk["series"].items() if isinstance(e, dict) and e.get("source_id")}
            if "source_health" in blk and wired:
                blk["source_health"]["series_loaded"] = sum(1 for e in wired.values() if e.get("status") != "unavailable")
                blk["source_health"]["series_expected"] = len(wired)
                if blk["source_health"]["series_loaded"] == blk["source_health"]["series_expected"]:
                    blk["source_health"]["status"] = "fresh"
            with open(blk_path, "w", encoding="utf-8") as f:
                json.dump(blk, f, indent=2, ensure_ascii=False)
            actions.append(f"{ccy.upper()} {full_key}: promocionado desde derived.{deriv_key} (status=fresh)")

    return actions, rebuilt_needed


def check_ccy_health(ccy: str) -> dict:
    """Evalúa frescura de bloques y series para una divisa."""
    d_dir = os.path.join(ROOT, "data", ccy)
    regime = _load_json(os.path.join(d_dir, "regime.json"))
    quality = _load_json(os.path.join(d_dir, "quality.json"))
    agent = _load_json(os.path.join(d_dir, "agent.json"))

    block_status = {}
    stale_series = []
    unavailable_series = []
    freq_counts = {"daily": 0, "weekly": 0, "monthly": 0, "other": 0}

    for b in BLOCKS:
        bdata = _load_json(os.path.join(d_dir, f"{b}.json"))
        sh = bdata.get("source_health") or {}
        st = sh.get("status", "unknown")
        loaded = sh.get("series_loaded", 0)
        expected = sh.get("series_expected", 0)
        disp_only_set = set(sh.get("display_only") or [])
        block_status[b] = {
            "status": st,
            "loaded": loaded,
            "expected": expected,
            "as_of": bdata.get("as_of"),
        }
        for sname, sdict in (bdata.get("series") or {}).items():
            if not isinstance(sdict, dict):
                continue
            fq = str(sdict.get("frequency") or "other").lower()
            if fq in freq_counts:
                freq_counts[fq] += 1
            else:
                freq_counts["other"] += 1
            sst = sdict.get("status")
            age = sdict.get("age_days")
            src_id = sdict.get("source_id")
            is_disp = bool(sdict.get("display_only") or (sname in disp_only_set))
            if sst == "unavailable":
                # Series pendientes por diseño (source_id=None) se excluyen igual que en ingest/run.py
                if src_id is not None and not is_disp:
                    unavailable_series.append(f"{b}.{sname}")
            elif sst in ("stale", "degraded") and not is_disp and st not in ("fresh", "ok"):
                max_age = MAX_AGE_BY_FREQ.get(fq, 30)
                if age is not None and age > max_age:
                    stale_series.append(f"{b}.{sname} ({age}d, {fq})")

    hb = regime.get("heartbeat") or {}
    hb_errors = hb.get("errors") or []
    degraded_blocks = [b for b, info in block_status.items() if info["status"] not in ("fresh", "ok")]

    needs_repair = bool(degraded_blocks or unavailable_series or stale_series or hb_errors)
    return {
        "currency": ccy.upper(),
        "as_of": regime.get("as_of"),
        "overall_regime": regime.get("regime") or (regime.get("overall") or {}).get("label"),
        "overall_score": regime.get("weighted_score") if regime.get("weighted_score") is not None else (regime.get("overall") or {}).get("score"),
        "confidence": ((quality.get("system") or {}).get("confidence") or {}).get("score"),
        "blocks": block_status,
        "degraded_blocks": degraded_blocks,
        "unavailable_series": unavailable_series,
        "stale_series": stale_series,
        "heartbeat_errors": hb_errors[:5],
        "freq_mix": freq_counts,
        "needs_repair": needs_repair,
        "headline": agent.get("headline"),
        "liquidity_bulletin": agent.get("liquidity_bulletin") or {},
    }


def run_gate() -> Tuple[bool, str]:
    """Ejecuta `python3 -m ingest.gate --all --fuzz` y devuelve (passed, output)."""
    r = subprocess.run(
        [sys.executable, "-m", "ingest.gate", "--all", "--fuzz"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    out = (r.stdout or "") + (r.stderr or "")
    return (r.returncode == 0), out.strip()


def auto_repair_currency(ccy: str, initial_health: Optional[dict] = None) -> Tuple[bool, str, List[str]]:
    """Ejecuta el ciclo completo de auto-curación y sustitución multi-fuente para una divisa."""
    actions: List[str] = []

    # Etapa 1: Auto-descubrimiento de enlaces si hay endpoints dinámicos
    disc_actions = discover_and_heal_endpoints(ccy)
    actions.extend(disc_actions)

    # Etapa 2: Re-ejecución del pipeline oficial (`ingest.run --lane all`)
    r = subprocess.run(
        [sys.executable, "-m", "ingest.run", "--ccy", ccy, "--lane", "all", "--no-rss"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    actions.append(f"{ccy.upper()}: re-ingesta ejecutada (`ingest.run --ccy {ccy} --lane all`)")

    # Etapa 3: Verificar si persisten series caídas o atrasadas y aplicar sustitución multi-fuente
    post_h = check_ccy_health(ccy)
    bad_keys = list(post_h["unavailable_series"]) + [s.split(" ")[0] for s in post_h["stale_series"]]
    for b in post_h["degraded_blocks"]:
        bdata = _load_json(os.path.join(ROOT, "data", ccy, f"{b}.json"))
        for k, v in (bdata.get("series") or {}).items():
            if isinstance(v, dict) and v.get("source_id") and v.get("status") in ("unavailable", "stale", "degraded"):
                fk = f"{b}.{k}"
                if fk not in bad_keys:
                    bad_keys.append(fk)

    if bad_keys:
        sub_actions, rebuild = substitute_or_heal_series(ccy, bad_keys)
        actions.extend(sub_actions)
        if rebuild:
            subprocess.run(
                [sys.executable, "-m", "ingest.run", "--ccy", ccy, "--lane", "all", "--no-rss"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=300,
            )
            post_h = check_ccy_health(ccy)

    return (not post_h["needs_repair"]), out[-400:], actions


def build_markdown_report(
    health_by_ccy: Dict[str, dict],
    liq_report: dict,
    gate_ok: bool,
    gate_out: str,
    repaired: Dict[str, Tuple[bool, str, List[str]]],
) -> Tuple[str, bool]:
    """Construye el reporte Markdown institucional (con primera línea ESTADO: OK o ESTADO: REQUIERE OK)."""
    any_issue = (not gate_ok) or any(h["needs_repair"] for h in health_by_ccy.values())
    header = "ESTADO: REQUIERE OK" if any_issue else "ESTADO: OK"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        header,
        "",
        f"**Fecha UTC:** `{now_str}`",
        "**Prioridad de Frescura MMT:** `1.º Diaria (prioridad máxima) → 2.º Semanal → 3.º Mensual (solo último recurso)`",
        "",
        "### 1. Estado de Salud y Frescura por Divisa (32 Bloques)",
        "",
        "| Divisa | As-Of | Régimen General | BC | Tesoro | Tipos | Banca | Gate A1–A5 | Series (D/W/M) | Estado |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for ccy in CCYS:
        h = health_by_ccy[ccy]
        b = h["blocks"]
        fm = h["freq_mix"]
        gate_str = "PASS" if gate_ok else "CHECK"
        st_str = "OK" if not h["needs_repair"] else ("Incidencia (" + ", ".join(h["degraded_blocks"] or h["unavailable_series"] or h["stale_series"])[:48] + ")")
        lines.append(
            f"| **{h['currency']}** | `{h['as_of']}` | `{h['overall_regime']}` | "
            f"`{b['central_bank']['status']}` ({b['central_bank']['loaded']}/{b['central_bank']['expected']}) | "
            f"`{b['fiscal']['status']}` ({b['fiscal']['loaded']}/{b['fiscal']['expected']}) | "
            f"`{b['rates']['status']}` ({b['rates']['loaded']}/{b['rates']['expected']}) | "
            f"`{b['banking']['status']}` ({b['banking']['loaded']}/{b['banking']['expected']}) | "
            f"`{gate_str}` | `{fm['daily']}D / {fm['weekly']}W / {fm['monthly']}M` | {st_str} |"
        )

    lines.extend([
        "",
        "### 2. Boletín Operativo de Liquidez MMT (Bancos Centrales y Tesoros G8)",
        "",
    ])
    for msg in liq_report.get("messages", []):
        lines.append(f"- **{msg['actor']} ({msg['currency']}):** {msg['text']}")

    if repaired:
        lines.extend([
            "",
            "### 3. Acciones de Auto-Reparación y Sustitución de Feeds Ejecutadas",
            "",
        ])
        for ccy, (ok, out, acts) in repaired.items():
            lines.append(f"- **{ccy.upper()}**: `{'REPARADO' if ok else 'REQUIERE REVISIÓN'}` — `{out[-160:]}`")
            for act in acts:
                lines.append(f"  - {act}")

    if any_issue:
        lines.extend([
            "",
            "### 4. Detalle de Incidencias Detectadas",
            "",
        ])
        for ccy, h in health_by_ccy.items():
            if h["needs_repair"]:
                lines.append(
                    f"- **{h['currency']}**: bloques degradados={h['degraded_blocks']}, "
                    f"no disponibles={h['unavailable_series']}, atrasadas={h['stale_series']}, "
                    f"errores={h['heartbeat_errors']}"
                )

    return "\n".join(lines) + "\n", any_issue


def build_telegram_messages(
    health_by_ccy: Dict[str, dict],
    liq_report: dict,
    gate_ok: bool,
    repaired: Dict[str, Tuple[bool, str, List[str]]],
) -> List[str]:
    """Construye los mensajes HTML para Telegram con el estado del Agente Doctor, sustituciones de feeds y flujos MMT."""
    from ingest.notify import esc
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    any_issue = (not gate_ok) or any(h["needs_repair"] for h in health_by_ccy.values())
    badge = "🟢 ESTADO: OK (32/32 bloques frescos)" if not any_issue else "🟡 ESTADO: INCIDENCIAS EN REVISIÓN"

    hdr = [
        f"<b>MESA MACRO FX · AGENTE DOCTOR MMT ({esc(now_str)})</b>",
        f"{badge} · Gate A1–A5: <b>{'PASS' if gate_ok else 'CHECK'}</b>",
        "Prioridad MMT: 1.º Diaria → 2.º Semanal → 3.º Mensual (último recurso)",
        "",
    ]
    for ccy in CCYS:
        h = health_by_ccy[ccy]
        b = h["blocks"]
        fm = h["freq_mix"]
        st_icon = "✓" if not h["needs_repair"] else "⚠"
        hdr.append(
            f"{st_icon} <b>{h['currency']}</b> ({esc(h['as_of'] or '—')}) · {esc(h['overall_regime'] or '—')} · "
            f"BC:{b['central_bank']['status']} TES:{b['fiscal']['status']} TIP:{b['rates']['status']} BAN:{b['banking']['status']} "
            f"[{fm['daily']}D/{fm['weekly']}W/{fm['monthly']}M]"
        )

    if repaired:
        hdr.append("")
        hdr.append("<b>AUTO-REPARACIÓN Y SUSTITUCIÓN DE FEEDS EJECUTADAS</b>")
        for ccy, (ok, _out, acts) in repaired.items():
            for act in acts:
                hdr.append(f"• {esc(act)}")

    msgs = ["\n".join(hdr)]

    liq_lines = ["<b>BOLETÍN OPERATIVO DE LIQUIDEZ MMT (BANCOS CENTRALES Y TESOROS G8)</b>"]
    for msg in liq_report.get("messages", []):
        liq_lines.append(f"• <b>{esc(msg['actor'])} ({esc(msg['currency'])}):</b> {esc(msg['text'])}")
    if len(liq_lines) > 1:
        msgs.append("\n".join(liq_lines))

    return msgs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Agente Doctor MMT — Mesa Macro FX")
    ap.add_argument("--auto-repair", action="store_true", help="Re-ejecuta y sustituye feeds automáticamente para divisas con atraso o fallo")
    ap.add_argument("--send-telegram", action="store_true", help="Envía el boletín del Agente Doctor + Liquidez MMT a Telegram y outbox.json")
    ap.add_argument("--report-out", default=os.path.join(ROOT, ".agent", "report.md"), help="Ruta del reporte Markdown")
    ap.add_argument("--json-out", default=os.path.join(ROOT, "data", "mesa", "liquidity_report.json"), help="Ruta del boletín JSON")
    args = ap.parse_args(argv)

    health_by_ccy = {ccy: check_ccy_health(ccy) for ccy in CCYS}
    repaired: Dict[str, Tuple[bool, str, List[str]]] = {}

    if args.auto_repair:
        for ccy, h in list(health_by_ccy.items()):
            if h["needs_repair"]:
                ok, out, acts = auto_repair_currency(ccy, h)
                repaired[ccy] = (ok, out, acts)
                health_by_ccy[ccy] = check_ccy_health(ccy)

    gate_ok, gate_out = run_gate()
    liq_report = generate_all_reports(ROOT, write_out=args.json_out)

    # Asegurar que cada data/<ccy>/agent.json tenga su liquidity_bulletin y auto_repair_actions actualizados
    for ccy in CCYS:
        ap_path = os.path.join(ROOT, "data", ccy, "agent.json")
        adata = _load_json(ap_path)
        if adata:
            if ccy.upper() in liq_report.get("currencies", {}):
                adata["liquidity_bulletin"] = liq_report["currencies"][ccy.upper()]
            if ccy in repaired:
                adata["auto_repair_actions"] = repaired[ccy][2]
            with open(ap_path, "w", encoding="utf-8") as f:
                json.dump(adata, f, indent=2, ensure_ascii=False)

    md, any_issue = build_markdown_report(health_by_ccy, liq_report, gate_ok, gate_out, repaired)
    os.makedirs(os.path.dirname(args.report_out), exist_ok=True)
    with open(args.report_out, "w", encoding="utf-8") as f:
        f.write(md)

    if args.send_telegram or args.auto_repair or os.environ.get("TELEGRAM_BOT_TOKEN"):
        from ingest import notify as N
        tg_msgs = build_telegram_messages(health_by_ccy, liq_report, gate_ok, repaired)
        N.send(tg_msgs, ROOT, tag="agent_doctor")

    print(f"agent_doctor status={'ISSUE' if any_issue else 'OK'} gate={'PASS' if gate_ok else 'FAIL'} report={args.report_out}")
    return 2 if any_issue else 0


if __name__ == "__main__":
    sys.exit(main())
