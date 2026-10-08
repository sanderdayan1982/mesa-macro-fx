# ACTA — CAD banking: crédito StatCan conectado y fin del «stale» por series informativas (2026-10-08)

**Hallazgo.** `data/cad/banking.json`: estado `stale`, 6/8 series. Causas: (1) `business_loans` y `household_credit` nunca conectadas
(«pending: StatCan candidates»); (2) `bank_assets` `degraded` a propósito (display_only). El dato NO estaba atrasado: Valet C1/C2 y
StatCan terminan en 2026-07 (publicado 2026-09-18), comprobado hoy en ambas fuentes.

**Verificación en la fuente primaria (Statistics Canada WDS, 2026-10-08).**
- Hogares: tabla 36-10-0639-01, «Total credit liabilities of households», Canadá, raw → v1231415582; 2026-07 = 3.290.492 M CAD.
- Empresas: tabla 36-10-0640-01, «Total credit liabilities of private non-financial corporations», Canadá, raw → v1304432223; 2026-07 = 2.410.115 M CAD.
- Descartadas: 33-10-0006-01 (archivada, fin 2019-01), 36-10-0619-01 (fin 2019-10). 10-10-0109-01 «Canadian dollar assets, total» = v36852,
  la misma serie errática que Valet V36852 → `bank_assets` sigue display_only.
- Raw (sin desestacionalizar), igual que las series Valet C1/C2 del bloque.

**Decisión (OK del propietario en el chat, 2026-10-08).**
1. `config/cad.json`: ids StatCan en `business_loans` / `household_credit`; `sources.statcan` verificado.
2. `ingest/providers.py` `StatCanProvider` (WDS POST, latestN 60 / 300 en backfill); `ingest/run.py` CAD banking: Valet solo recibe ids Valet,
   StatCan aparte, fusión con history/ igual que Valet.
3. `ingest/blocks.py` banking: `source_health` cuenta las series que puntúan; las display_only se listan y conservan su propia marca.

**Sin cambios.** Fórmulas, umbrales, regla de transmisión (ya incluía ambas series en `applies_to`), régimen.

**Efecto (corrida en vivo en copia temporal).** Bloque `fresh` 6/6. Señal de transmisión YELLOW (4/6 válidas) → **RED** (6/6):
depósitos −0,26 %, reservas −2,22 %, crédito empresas −0,13 % m/m bajan (3 rojas). Flag `TRANSMISSION_FAILURE`; régimen sigue FLOOR_FRICTION.

**Pruebas.** `ingest/tests_cad_statcan.py` (S1–S5) y `tools/smoke.sh`: 17 comprobaciones en verde.

**Siguiente.** Refresco CAD lane monthly lanzado a mano tras el push.
