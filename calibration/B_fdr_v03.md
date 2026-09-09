# B v0.3 — pruebas prerregistradas, corrección conjunta (las ocho divisas)

40 pruebas · pre-registered cuts (era p80/p20, persistence 7/0 mean) at the selected level weight; Benjamini–Hochberg on the moving-block bootstrap p (block 8 weeks); survives = q ≤ 0.05 and ρ < 0

| divisa | bloque | verdad | h | ρ | p boot | q FDR boot | t DRAIN−N | t INJ−N | sobrevive |
|---|---|---|---|---|---|---|---|---|---|
| EUR | central_bank | stress | 4 | -0.311 | 0.0005 | 0.02 | 1.87 | -2.07 | SÍ |
| JPY | central_bank | stress_alt | 4 | -0.332 | 0.0315 | 0.61 | 2.66 | -0.22 | no |
| GBP | fiscal | stress | 12 | -0.258 | 0.0565 | 0.61 | 4.35 | -0.38 | no |
| EUR | central_bank | stress | 12 | -0.158 | 0.061 | 0.61 | -0.4 | -2.7 | no |
| CAD | central_bank | stress | 4 | -0.095 | 0.1 | 0.687 | 2.2 | 0.21 | no |
| CHF | fiscal | stress | 12 | -0.164 | 0.1359 | 0.687 | 0.09 | -2.54 | no |
| CAD | fiscal | stress | 4 | 0.092 | 0.1369 | 0.687 | 1.23 | 3.81 | no |
| GBP | fiscal | stress | 4 | -0.166 | 0.1374 | 0.687 | 2.24 | -0.1 | no |
| CAD | fiscal | stress | 12 | 0.107 | 0.1649 | 0.7329 | 0.46 | 3.44 | no |
| GBP | central_bank | stress | 4 | 0.127 | 0.2029 | 0.8116 | -2.05 | -0.68 | no |
| USD | fiscal | stress | 4 | -0.086 | 0.2739 | 0.8663 | 0.42 | -0.1 | no |
| USD | fiscal | stress | 12 | -0.093 | 0.2874 | 0.8663 | 0.51 | -0.21 | no |
| AUD | central_bank | stress | 12 | 0.129 | 0.3308 | 0.8663 | -0.51 | 1.01 | no |
| USD | central_bank | stress | 12 | 0.088 | 0.3443 | 0.8663 | -0.74 | 2.53 | no |
| NZD | fiscal | stress | 4 | 0.073 | 0.3878 | 0.8663 | -1.29 | -0.17 | no |
| NZD | central_bank | stress_alt | 4 | 0.073 | 0.3903 | 0.8663 | -0.66 | -0.92 | no |
| AUD | fiscal | stress | 4 | -0.097 | 0.4203 | 0.8663 | 1.11 | 0.57 | no |
| CHF | central_bank | stress | 12 | 0.093 | 0.4393 | 0.8663 | -2.3 | -2.54 | no |
| NZD | central_bank | stress | 12 | -0.06 | 0.4803 | 0.8663 | -1.73 | -1.77 | no |
| JPY | fiscal | stress_alt | 12 | 0.115 | 0.4858 | 0.8663 | -1.44 | -0.37 | no |
| NZD | fiscal | stress | 12 | -0.069 | 0.5102 | 0.8663 | -2.04 | -1.42 | no |
| USD | central_bank | stress | 4 | 0.046 | 0.5482 | 0.8663 | -0.78 | 1.69 | no |
| EUR | fiscal | stress | 4 | -0.048 | 0.5492 | 0.8663 | -0.25 | -0.25 | no |
| JPY | central_bank | stress | 12 | 0.068 | 0.5587 | 0.8663 | -1.49 | -0.36 | no |
| AUD | fiscal | stress | 12 | -0.075 | 0.5732 | 0.8663 | 0.77 | 0.58 | no |
| JPY | central_bank | stress_alt | 12 | -0.097 | 0.5787 | 0.8663 | 1.11 | 0.49 | no |
| CHF | fiscal | stress | 4 | -0.045 | 0.6092 | 0.8663 | -0.24 | -1.65 | no |
| AUD | central_bank | stress | 4 | 0.047 | 0.6122 | 0.8663 | -1.44 | 0.42 | no |
| NZD | central_bank | stress_alt | 12 | 0.04 | 0.6342 | 0.8663 | -0.59 | -0.46 | no |
| JPY | fiscal | stress_alt | 4 | 0.073 | 0.6497 | 0.8663 | -2.06 | -0.53 | no |
| JPY | fiscal | stress | 4 | -0.04 | 0.7136 | 0.9208 | 2.11 | 1.39 | no |
| CAD | central_bank | stress | 12 | -0.019 | 0.7836 | 0.9429 | -0.67 | -1.8 | no |
| NZD | fiscal | stress_alt | 4 | 0.021 | 0.8201 | 0.9429 | 0.79 | 0.85 | no |
| CHF | central_bank | stress | 4 | 0.018 | 0.8351 | 0.9429 | 0.56 | 0.07 | no |
| GBP | central_bank | stress | 12 | -0.028 | 0.8386 | 0.9429 | -1.3 | -2.59 | no |
| NZD | central_bank | stress | 4 | 0.017 | 0.8486 | 0.9429 | -2.32 | -1.2 | no |
| NZD | fiscal | stress_alt | 12 | 0.011 | 0.9125 | 0.9508 | 0.82 | 0.56 | no |
| JPY | central_bank | stress | 4 | 0.012 | 0.914 | 0.9508 | -0.25 | -0.23 | no |
| JPY | fiscal | stress | 12 | -0.009 | 0.927 | 0.9508 | 2.44 | 2.28 | no |
| EUR | fiscal | stress | 12 | 0.003 | 0.9695 | 0.9695 | -1.38 | -0.9 | no |
