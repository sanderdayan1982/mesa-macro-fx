# ACTA — Netlify: deploys solo cuando cambia una página (2026-10-08)

**Hallazgo.** Netlify del equipo: 1.067 deploys de producción en 10-sep→9-oct = 16.005 créditos (15 c/deploy; el plan incluye 10.000); todos los proyectos pausados.
Este repo: ~563 commits desde el 10-sep, casi todos de bots (`data/`, `history/`, `logs/`). Cada uno disparaba un deploy, porque el sitio publica la raíz y las páginas leían `../data/` primero.

**Decisión.**
1. `<ccy>/index.html` (8) y `mesa/index.html`: orden de lectura invertido → primero `raw.githubusercontent.com` (con `?v=` por minuto), copia local solo como respaldo. Mismo mecanismo que ya existía, solo el orden.
2. `netlify.toml` `[build].ignore`: solo se despliega si cambia un `*index.html` o `netlify.toml`.

**Frescura.** Comprobado 2026-10-08 20:57Z: `data/usd/regime.json` en raw tiene `generated_at` 2026-10-08T02:19Z (refresco diario de hoy). La antigüedad por bloque que muestra la mesa no cambia.

**Sin cambios.** Metodología, umbrales, fuentes, workflows, esquemas de datos.

**Riesgo conocido.** Si raw.githubusercontent falla (6 s), las páginas caen a la copia desplegada, que ya no se refresca; la «antigüedad» (`generated_at`) la delata, no se oculta.

**Pruebas.** Sintaxis JS de las 9 páginas OK. `tools/smoke.sh` no se pudo ejecutar en el Mac (falta Python 3.11 con dependencias; exit 127); el cambio no toca Python. Verificar tras el push que los commits de datos salen «Skipped» en Netlify → Deploys.

**Siguiente.** Desactivar Deploy Previews en Netlify; recarga fija de créditos.
