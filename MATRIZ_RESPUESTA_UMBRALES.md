# MATRIZ DE RESPUESTA — triangulación de umbrales (rellenar una por AI)

AI revisora: ______________ · fecha: __________

Versión del paquete recibido: ______ (v2, 2026-09-09) · fichero: ______

Veredictos: **V** = VALIDADO · **VO** = VALIDADO CON OBSERVACIONES · **R** = RECHAZADO · **SD** = SIN DATOS (no cuenta en el quórum). Cada VO o R lleva razón, **comprobación concreta** (serie + rango de fechas + signo esperado) y fuente primaria (URL). Sin cifras de umbral.

## 1. Método (común)

| pregunta | veredicto | razón | fuente primaria |
|---|---|---|---|
| Frecuencia de la era como criterio (A) | | | |
| Verdad alternativa al cruce (cuál y por qué) | | | |
| Spread de estrés correcto por divisa (señala las divisas en que no) | | | |
| Retardos de publicación del replay | | | |
| Histéresis p80/p20 → p67/p33 y persistencia mínima | | | |
| Cambio v0.3: niveles 0,25, flujos dicen la inyección | | | |
| Régimen general = regla de acuerdo, conflicto = NEUTRAL etiquetado, sin pesos duales | | | |
| Persistencia mínima para cambiar de régimen | | | |
| Multiplicidad / autocorrelación: qué validaciones B aceptas tras FDR + bootstrap | | | |
| Transición de era (qué opera en vivo hasta 150 semanas) | | | |
| Etiquetado de evidencia por umbral en el config | | | |

## 2. Eras (una fila por divisa)

| divisa | corte propuesto | veredicto | corte alternativo y fuente |
|---|---|---|---|
| CAD | suelo desde 2020-03-23 | | |
| GBP | QT/ventas APF desde 2022-11 | | |
| AUD | reservas amplias desde 2025-04-09 (74 sem.) | | |
| JPY | tipos positivos desde 2024-07-31 | | |
| CHF | absorción escalonada desde 2022-09-22 (0 % desde 2025-06-20) | | |
| NZD | LSAP unwind desde 2022-07-01 (marco nuevo 2026-04-02) | | |
| USD | QT desde 2022-06-01 (sub-era 2025-04) | | |
| EUR | DFR positivo desde 2022-09-14 | | |

## 3. Verdad de funding y flujos (una fila por divisa)

| divisa | spread usado | veredicto | mejor precio de funding público | flujos que deberían decir la inyección |
|---|---|---|---|---|
| CAD | CORRA − depósito | | | |
| GBP | SONIA − Bank Rate | | | |
| AUD | AONIA − target | | | |
| JPY | TONA − IOER | | | |
| CHF | SARON − (política − 5 pb) | | | |
| NZD | bank bill 30 d − OCR | | | |
| USD | SOFR − IORB | | | |
| EUR | €STR − DFR | | | |

## 4. Subastas (una fila por instrumento que conozcas)

| divisa / instrumento | percentiles de era como ancla | veredicto | ancla institucional publicada (fuente) | fuente pública del tail vs WI / secundario |
|---|---|---|---|---|
| | | | | |

## 5. Casos especiales

| caso | veredicto | razón | fuente |
|---|---|---|---|
| USD: Tesoro INJECTION permanente → leer el ritmo (p20/p80) | | | |
| EUR: caja fiscal del área — medida semanal pública | | | |
| JPY: flujos del BoJ que definen la inyección | | | |
| CHF: ventana del Δ13 s anclada a la era | | | |
| AUD / NZD: eras cortas — ¿esperar a 150 semanas? | | | |

## 6. Fuentes nuevas (sólo con URL)

| divisa | serie | frecuencia | mejora (funding / fiscal / subastas) | URL |
|---|---|---|---|---|
| | | | | |

## Cierre

Las tres cosas que cambiarías del método antes de llevar cualquier umbral a producción:

1.
2.
3.
