# Mesa Macro FX — Fase 1 GBP: auditoría del dashboard anterior + mapa de fuentes verificado

Versión 0.1 · 2026-09-08 · Estado: BORRADOR PARA TRIANGULACIÓN (no hay código todavía) · hereda el Desk Standard v0.3 (ver `FASE1_Desk_Standard_CAD.md`, secciones 1.2–1.6)

Siglas: BoE (Bank of England), MPC (Monetary Policy Committee), SONIA (Sterling Overnight Index Average), APF (Asset Purchase Facility), STR (Short-Term Repo), ILTR/ILTRO (Indexed Long-Term Repo Operations), CTRF (Contingent Term Repo Facility), TFSME (Term Funding Scheme with additional incentives for SMEs), PMRR (Preferred Minimum Range of Reserves), IADB (Interactive Database del BoE), ONS (Office for National Statistics), DMO (Debt Management Office), CGNCR (Central Government Net Cash Requirement), PSNB (Public Sector Net Borrowing), HMT (HM Treasury), NLF (National Loans Fund), CRD (Cash Ratio Deposits), QT/QE (Quantitative Tightening/Easing), MMT (Modern Monetary Theory), NFA (Net Financial Assets), API (Application Programming Interface), CSV (Comma-Separated Values), pb (puntos básicos), WAT (West Africa Time).

---

## 1. Auditoría del dashboard GBP anterior (UK Command Center v2.0 + GBP-ICC v4.3, abril 2026)

Dos artefactos: un HTML estático con cifras del 1–9 de abril de 2026 escritas a mano, y un backend v4.3 en Netlify Functions + Blobs con seis endpoints, registro de series, motor de régimen v2.1 y alertas con ciclo ACTIVE → ACK → RESOLVED.

### 1.1 Lo que se rescata

- **Mapa de equivalencias UK ↔ USA** (H.4.1 → Weekly Report B1.1.2; TGA → Exchequer/CGNCR; SOFR−IORB → SONIA−Bank Rate; SOMA → Loan to APF; Repo Fed → STR+ILTRO). Es correcto y pasa al config.
- **Net Liquidity UK = STR + ILTRO + TFSME + APF + Bonds** (activos de política monetaria). Buena idea de partida; en v0.1 se reformula con la fórmula del Desk (activos − cuenta del gobierno − reverse repo) más este agregado como métrica propia "Policy assets".
- **Umbrales absolutos v2.1**: reservas verde > 700B / ámbar 600–700B / rojo < 600B; SONIA spread |x| ≤ 5 verde, ≤ 15 ámbar, > 15 rojo; repo offset STR+ILTRO > 150B verde, 80–150B ámbar, < 80B rojo; APF QT pace > 10B/semana rojo. Se conservan como `secondary_absolute`, pero el ancla primaria de reservas pasa a ser el PMRR del BoE (ver 2.1).
- **Signal QA** (null / NaN / fuera de rango → BLOCKED, nunca "amber") y **penalizaciones de confianza por frescura y disponibilidad**: la misma filosofía que el Desk Standard; el motor CAD ya lo implementa (`null is never SAFE`).
- **Tabla "señales por tipo de día fiscal"** (día de recaudación PAYE/VAT, día de prestaciones DWP, subasta de gilts, operación STR): buena narrativa MMT para el bloque fiscal y el futuro agente; pasa como texto de metodología, no como métrica.
- **Registro por serie con tier / freshness / confidence / lastAttempt / lastSuccess / error / isFallback**: ya cubierto por el esquema de bloque (status + confidence + age_days).

### 1.2 Lo que no pasa al nuevo (y por qué)

1. **Balance del BoE por ingesta manual** (`/admin.html` + `BOOTSTRAP_TOKEN`). El v4.3 declaraba "No public CORS API" y dependía de que tú tecleases seis cifras cada jueves. El IADB del BoE tiene una API CSV pública y programática; verificada hoy (sección 2). Es el mayor salto de calidad de la moneda.
2. **Gilts mensuales de la OCDE vía FRED** (`IRLTLT01GBM156N`) y un **3M interbancario como "2Y"** (`IR3TIB01GBM156N`), ambos con ~30 días de retraso. El IADB publica la curva par de gilts a diario (10Y verificado hoy con dato del 3 de septiembre).
3. **Fiscal "estático"**: NFR, CGNCR y gilt sales cargados como constantes anuales del Remit del DMO (£257.1B, £149.2B, £252.1B) y "DMO cash" como semilla. El ONS publica CGNCR, gasto y recaudación del gobierno central **mensuales por API**, verificado hoy.
4. **Precios en el régimen**: GBP/USD (peso 1) y FTSE entraban en la confluencia. Igual que en CAD, salen del tab de liquidez y van al Desk.
5. **Fuentes frágiles**: Stooq (FTSE, oro), Frankfurter (FX), scraping HTML de `Bank-Rate.asp`. Bank Rate tiene serie IADB (`IUDBEDR`, verificada); FX oficial del BoE existe en el IADB (pendiente de verificar códigos XUDL*).
6. **Netlify Blobs + refresh cada 4 h**: sustituido por GitHub Actions + JSON en git, como en CAD.
7. **Régimen por recuento de verdes con hard rules** (DRAIN si ≥2R o reservas < 600B o SONIA > +15): sustituido por el motor ponderado del Desk con `LIQUIDITY_SCARCITY` / `FLOOR_FRICTION`.

---

## 2. Mapa de fuentes GBP — verificado el 2026-09-08

### 2.0 El endpoint del IADB (Bank of England Interactive Database)

`https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp?csv.x=yes&Datefrom=DD/Mon/YYYY&Dateto=DD/Mon/YYYY&SeriesCodes=A,B,C&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N`

Devuelve `application/csv` con cabecera `DATE,CODE1,CODE2…` y fechas `03 Sep 2026`. Sin clave. Verificado desde tu navegador. **Regla operativa aprendida hoy**: el sitio está detrás de Akamai y bloquea la IP tras una ráfaga de peticiones paralelas (me pasó al probar 75 códigos a la vez). La ingesta debe hacer **una sola petición por carril con todos los códigos juntos**, User-Agent identificable, y esperar ≥ 2 s entre peticiones si hay más de una. Un código inexistente en la lista hace fallar toda la petición: el config sólo lleva códigos verificados.

### 2.1 Capa A — Liquidez del banco central (Weekly Report, Tabla B1.1.2, miércoles → publicado jueves; IADB actualizado el lunes)

| Métrica canónica | Código IADB | Verificación | Último dato |
|---|---|---|---|
| Reserves (≈ WRESBAL) | **RPWB56A** | código + etiqueta ("Reserve Balances", fuente secundaria) + valor coherente con abril | 2026-09-02 · 643 685 £mn |
| Notes in circulation | **RPWB55A** | código + etiqueta ("Notes in circulation") | 2026-09-02 · 98 978 |
| Ways and Means advances to HMG | **RPWB72A** | etiqueta en el árbol del IADB | 2026-09-02 · 370 |
| Short-term OMO lending (STR) — ≈ repos de liquidez | RPWB67A (probable) | valor 124 825 coherente con STR 97 441 en abril y con "STR+ILTR £152bn" (Saporta, nov 2025); **etiqueta pendiente** | 2026-09-02 · 124 825 |
| Long-term operations (ILTR + CTRF) | RPWB69A (probable) | valor 83 874 coherente con ILTRO 72 774 en abril; **etiqueta pendiente** | 2026-09-02 · 83 874 |
| Foreign currency public securities / CRD (a identificar) | RPWB59A | **etiqueta pendiente** | 2026-09-02 · 20 533 |
| Loans to APF (≈ SOMA / TREAST) | pendiente | no está en el rango RPWB50A–99A con datos; buscar en el árbol "Assets" | abril: 553 158 |
| TFSME | pendiente | idem | abril: 41 894 |
| Sterling bond holdings | pendiente | idem | abril: 12 845 |
| Government deposits at BoE (≈ TGA) | **no existe como línea separada** en el Weekly Report; HMG/NLF queda en "other liabilities". | — | — |

Códigos que existen pero devolvieron vacío en la ventana de dos semanas (posibles series discontinuadas o de valor cero: CTRF, bills, fine-tuning): RPWB54A, 57A, 58A, 62A, 63A, 65A, 66A, 68A, 73A, 74A. Se resuelven con una consulta secuencial al árbol "Bank of England Weekly Report → Assets / Liabilities" del IADB cuando el bloqueo de Akamai expire (normalmente minutos u horas).

**Ancla institucional (verificada)**: el BoE estima el **PMRR en £375–540bn** (encuesta a contrapartes, discurso de Victoria Saporta, noviembre 2025) y esperaba alcanzar el techo del rango "hacia finales del próximo año" (2026). Reservas hoy 643.7bn → todavía por encima del PMRR; STR+ILTR suministraban £152bn en noviembre 2025 (hoy ≈ 209bn si 67A/69A son STR/ILTR). Sistema **repo-led demand-driven**: el BoE deja que la demanda de las contrapartes determine las reservas vía STR semanal e ILTR. Esto cambia la lectura: en UK un STR creciente no es "inyección discrecional" sino la propia mecánica del marco; el estrés se lee en el precio (SONIA y repo GC vs Bank Rate), no en la cantidad.

Fórmulas v0.1:
- **Net Liquidity GBP** = Policy assets − Reverse repo/ sterling bills drenantes (si existen) donde Policy assets = STR + ILTR + TFSME + APF + Bonds. Como no hay línea de depósitos del gobierno, el Net Liquidity UK no resta TGA; la cuenta fiscal se lee en la capa B.
- **Reserves** = RPWB56A. Ancla absoluta primaria = PMRR 375–540bn: por encima = ample; dentro = zona de transición (WATCH informativo); por debajo del suelo = STRESS. Percentiles secundarios.
- **Currency drain** = −Δ RPWB55A (igual que CAD).
- **QT pace** = Δ APF semanal; **Repo offset** = STR + ILTR (umbral secundario v2.1: 150/80bn).

### 2.2 Capa B — Tesoro / equivalente fiscal (ONS Public Sector Finances, mensual, API abierta — verificada)

`https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/{code}/pusf/data` → JSON con `months[]`. Sin clave. Publicación mensual hacia el día 20–22 (última 2026-08-20, próxima 22-09-2026). Datos hasta julio 2026.

| Campo Desk | Código ONS | Título verificado | Último dato |
|---|---|---|---|
| CGNCR (≈ Net Treasury Flow mensual, signo invertido) | **RUUW** | CG: Net cash requirement £m CPNSA | jul-2026 · 2 723 |
| Gasto del gobierno central | **MF6U** | CG: Total expenditure £m CPNSA | jul-2026 · 115 570 |
| Recaudación del gobierno central | **ANBV** | CG: Total current receipts £m CPNSA | jul-2026 · 104 343 |
| PSNB ex banks (déficit) | **J5II** | PS: Net Borrowing (excl. PS banks) £m CPNSA | jul-2026 · −1 800 (superávit) |
| Intereses pagados al sector privado | **JW2P** | PS: Interest & dividends paid to private sector & RoW | jul-2026 · 10 268 |

Fórmulas MMT: **Net spending** = MF6U − ANBV (gasto neto = creación neta de NFA antes de emisión); **CGNCR** = necesidad de caja = lo que absorbe emisión de gilts/letras + cambios de caja (drena reservas sin cambiar NFA); Z-score sobre 24 meses; estacionalidad fuerte (enero/julio recaudan, abril gasta): se muestra el dato interanual (mismo mes año anterior) junto al mensual.
Equivalencia: **medium** (mensual, ~3 semanas de retraso, sin desglose diario). Complementos por evento: subastas de gilts y tenders semanales de letras del DMO (pendiente verificar formato de descarga en dmo.gov.uk/data). El DMO no publica el saldo diario del Exchequer en formato máquina; el "Daily Cash Flow" del v4.3 era PDF.

### 2.3 Capa C-1 — Transmisión bancaria (BoE Money & Credit / Bankstats, mensual)

Fuente: IADB, tablas A (Money and lending). Códigos candidatos habituales — **pendientes de verificar en la misma sesión que los RPWB** (una sola petición): M4 amounts outstanding (LPMAUYN), M4 lending (LPMVWYL / LPMB3TR), net lending to individuals total (LPMBI2O), lending secured on dwellings (LPMVTVX), consumer credit (LPMBI2P), deposits from households (LPMVWYS), sterling lending to PNFCs (LPMB4VH). Publicación mensual ~día 1 del mes siguiente (retraso ~1 mes: mejor que los ~75 días de Canadá).

### 2.4 Capa C-2 — Tipos y mercado monetario (IADB, diario) — verificados

| Métrica | Código | Último dato |
|---|---|---|
| SONIA (≈ SOFR) | **IUDSOIA** | 2026-09-03 · 3.7301 % |
| Bank Rate (≈ IORB: es el tipo pagado sobre reservas, el suelo) | **IUDBEDR** | 2026-09-04 · 3.75 % |
| 10Y gilt nominal par yield | **IUDMNPY** | 2026-09-03 · 5.0843 % |
| 5Y / 20Y par yields | IUDSNPY / IUDLNPY | pendiente (misma petición) |
| 2Y | pendiente: buscar código de 2Y en la curva par; si no existe, usar 5Y como front-end y etiquetar `proxy` | — |

Spread de estrés primario: **SONIA − Bank Rate** (hoy −2 pb). En el marco del BoE el Bank Rate se paga sobre todas las reservas: SONIA cotiza normalmente unos pb por debajo; **estrés = el spread se cierra hacia 0 o lo cruza**, y el repo GC se aleja por encima de Bank Rate + 5 pb (Saporta). No hay techo tipo Bank Rate canadiense; la Discount Window Facility y el CTRF son el techo de facto. Umbrales v2.1 (|x| ≤ 5 / ≤ 15 / > 15) se mantienen como secundarios; primario = percentil rodante con signo: WATCH si SONIA − Bank Rate ≥ −1 pb, STRESS ≥ +3, CRISIS ≥ +10.

### 2.5 Calendario
MPC 8 fechas/año, jueves 12:00 Londres (13:00 WAT); Weekly Report jueves (IADB lunes); ONS PSF ~día 20–22 a las 07:00 Londres; Money & Credit ~día 1 a las 09:30 Londres; subastas DMO según calendario trimestral.

---

## 3. Diferencias estructurales UK vs CAD que el motor debe absorber

1. **Sin cuenta fiscal diaria ni semanal**: la capa B es mensual. Peso de régimen propuesto: banco central 0.50 · tipos 0.30 · fiscal 0.10 · transmisión 0.10 (se sube tipos porque SONIA y la curva son diarios y el marco repo-led hace del precio la señal principal).
2. **Marco demand-driven**: STR/ILTR crecientes = normal, no inyección. El score de la capa A no debe premiar ni penalizar el nivel de repos; sí vigila su cambio brusco.
3. **PMRR como ancla**: dentro del rango no es escasez; escasez = reservas por debajo de 375bn **y** SONIA ≥ Bank Rate.
4. **QT activo**: APF cae por ventas + vencimientos; `balance_sheet_phase` = QT mientras ΔAPF < 0.
5. **Sin deposit rate distinto del policy rate**: `deposit_rate = policy_rate` (no hay −5 pb como en Canadá).

## 4. Pendientes antes de construir (Fase 2 GBP)
- Etiquetas de RPWB59A/67A/69A y códigos de APF, TFSME, Bonds (árbol IADB, petición secuencial).
- Códigos Money & Credit y 2Y/5Y/20Y verificados con una petición.
- FX oficial BoE (XUDLUSS, XUDLERS) para el Desk.
- Formato de descarga de subastas DMO.
- Triangulación con las otras AI (prompt adjunto).
