"""t331u B5 — APP/PEPP semanal (WFS 7.1 por cartera), ILTR semanal, patas diarias."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from ingest import wfs_71 as W  # noqa: E402

FIX = ROOT / "ingest" / "fixtures" / "t331u_b5" / "ecb_fs261117.html"


class Wfs71(unittest.TestCase):
    def test_tabla_1_del_17_nov_por_cartera_sin_rellenar(self):
        html = FIX.read_text(encoding="utf-8", errors="replace")
        p = W.parse_table(html)
        self.assertEqual(p["position_date"], "2026-11-13")
        self.assertAlmostEqual(p["portfolios_mn"]["PSPP"], 1_623_500.0)
        self.assertAlmostEqual(p["portfolios_mn"]["PEPP"], 1_258_300.0)
        self.assertAlmostEqual(p["portfolios_mn"]["SMP"], 0.0)
        # APP = 182.2+1.2+1623.5+208.0 = 2014.9 bn = 2_014_900 mn
        self.assertAlmostEqual(p["app_mn"], 2_014_900.0)
        self.assertAlmostEqual(p["pepp_mn"], 1_258_300.0)
        self.assertAlmostEqual(p["app_pepp_smp_mn"], 3_273_200.0)

    def test_reconciliacion_con_ilm_a070100_de_la_misma_semana(self):
        # live ILM W46 last obs 3,273,235 mn vs table 3,273.2 bn
        rec = W.reconcile_weekly_vs_ilm(3_273_200.0, 3_273_235.0)
        self.assertEqual(rec["status"], "OK")
        self.assertAlmostEqual(rec["diff_mn"], -35.0)
        blank = W.reconcile_weekly_vs_ilm(None, 3_273_235.0)
        self.assertEqual(blank["status"], "BLANK")
        self.assertIsNone(blank["diff_mn"])

    def test_reconcilia_fin_de_mes_solo_si_hay_ambas_patas(self):
        weekly = [("2026-10-30", 2_050_000.0), ("2026-11-13", 2_014_900.0)]
        monthly = [("2026-10-31", 2_030_699.0)]  # October official
        rows = W.reconcile_month_end(weekly, monthly)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["month"], "2026-10")
        self.assertEqual(rows[0]["weekly_date"], "2026-10-30")
        # noviembre sin mensual → no se rellena
        self.assertEqual([r["month"] for r in rows], ["2026-10"])


class IltrLabel(unittest.TestCase):
    def test_iltr_auction_result_es_semanal(self):
        cfg = json.loads((ROOT / "config" / "gbp.json").read_text(encoding="utf-8"))
        ev = cfg["blocks"]["central_bank"]["series"]["iltr_auction_result"]
        self.assertEqual(ev["freq"], "weekly")
        self.assertEqual(cfg["blocks"]["central_bank"]["series"]["iltr"]["freq"], "weekly")


class DailyLegs(unittest.TestCase):
    def test_series_diarias_marcadas_como_pata_diaria_sin_cambiar_id(self):
        specs = [
            ("jpy.json", "central_bank", "cab_daily", "label:Current account balances (amount outstanding)"),
            ("aud.json", "central_bank", "es_balances_daily", "AESAT"),
            ("nzd.json", "central_bank", "settlement_cash_daily", "D12:settlement_cash"),
            ("usd.json", "fiscal", "tga_closing", "DTS:tga_close"),
        ]
        for fname, block, key, expected_id in specs:
            cfg = json.loads((ROOT / "config" / fname).read_text(encoding="utf-8"))
            ser = cfg["blocks"][block]["series"][key]
            self.assertEqual(ser["id"], expected_id, fname)
            self.assertEqual(ser["freq"], "daily", fname)
            self.assertEqual(ser.get("display_role"), "daily_leg", fname)
            self.assertTrue(ser.get("pair_series"), fname)


if __name__ == "__main__":
    unittest.main()
