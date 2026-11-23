# Medição de API (5 chamadas a quente por rota)

Base: http://127.0.0.1:8002 · metas: p95 ≤ 800 ms, ≤ 300 KB · 2026-10-29 09:31

| Rota | Status | Frio (ms) | p50 (ms) | p95 (ms) | Máx (ms) | 1º byte p50 (ms) | Tamanho (KB) | Simultâneas | Observação |
|---|---|---|---|---|---|---|---|---|---|
| `/api/performance/kpis` | 200 | 101 | 3 | 3 | 3 | 2 | 0.1 (nenhuma) | — | OK |
| `/api/orders/kpis` | 200 | 2 | 2 | 13 | 13 | 2 | 0.1 (nenhuma) | — | OK |
| `/api/commercial/kpis` | 200 | 2 | 3 | 6 | 7 | 2 | 0.1 (nenhuma) | — | OK |
| `/api/governance/kpis` | 200 | 25 | 2 | 15 | 15 | 2 | 0.5 (nenhuma) | — | OK |
| `/api/reports/data` | 200 | 2 | 2 | 3 | 3 | 2 | 16.2 (nenhuma) | — | sem compressão |

Sem cabeçalho Server-Timing: instale o middleware de resources/server_timing_fastapi.py para ver o tempo de cada consulta.

## Alertas

- `/api/reports/data`: sem compressão
