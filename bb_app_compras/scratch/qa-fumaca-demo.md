# Teste de fumaça

Base: http://127.0.0.1:8002 · 2026-10-29 09:33

| Rota | Largura | Resultado | Tempo (ms) | Problemas |
|---|---|---|---|---|
| /index.html | 390 | OK | 2751 | — |
| /performance.html | 390 | OK | 1771 | — |
| /ordens.html | 390 | OK | 1724 | — |
| /comercial.html | 390 | OK | 1795 | — |
| /governanca.html | 390 | OK | 1661 | — |
| /relatorios.html | 390 | OK | 1604 | — |
| /cadastros.html | 390 | FALHA | 1731 | 2 erro(s) de console/JS; 2 requisição(ões) com erro |
| /guia.html | 390 | OK | 1706 | — |
| /index.html | 1440 | OK | 2640 | — |
| /performance.html | 1440 | OK | 1880 | — |
| /ordens.html | 1440 | OK | 1927 | — |
| /comercial.html | 1440 | OK | 1795 | — |
| /governanca.html | 1440 | OK | 1706 | — |
| /relatorios.html | 1440 | OK | 1589 | — |
| /cadastros.html | 1440 | FALHA | 1573 | 2 erro(s) de console/JS; 2 requisição(ões) com erro |
| /guia.html | 1440 | OK | 1447 | — |

## Detalhes

### /cadastros.html · 390px
- console: Failed to load resource: the server responded with a status of 501 (NOT IMPLEMENTED)
- console: Failed to load resource: the server responded with a status of 501 (NOT IMPLEMENTED)
- requisição: GET http://127.0.0.1:8002/api/lookups/summary -> 501
- requisição: GET http://127.0.0.1:8002/api/lookups/fornecedores_especiais -> 501

### /cadastros.html · 1440px
- console: Failed to load resource: the server responded with a status of 501 (NOT IMPLEMENTED)
- console: Failed to load resource: the server responded with a status of 501 (NOT IMPLEMENTED)
- requisição: GET http://127.0.0.1:8002/api/lookups/summary -> 501
- requisição: GET http://127.0.0.1:8002/api/lookups/fornecedores_especiais -> 501

