# Medição de páginas

Condições: largura 1440px · rede nenhuma · CPU 1x · 3 repetições com cache vazio · 2026-10-29 09:32

Valores em ms (mediana das repetições). 'Dados na tela' = tempo até o seletor --pronto ficar visível.

| URL | 1º byte | DOM pronto | LCP | Dados na tela | Requisições | KB | Tarefas longas (qtd / maior ms) | Observação |
|---|---|---|---|---|---|---|---|---|
| http://127.0.0.1:8002/performance.html | 16 | 1.061 | 1.080 | 1.539 | 24 | 746.3 | 5 / 203 | tarefa longa de 203 ms |

## Requisições mais lentas (última repetição)

**http://127.0.0.1:8002/performance.html**
- 844 ms · 47.7 KB · font · https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2
- 593 ms · 1.3 KB · stylesheet · https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap
- 126 ms · 138.3 KB · script · https://cdn.jsdelivr.net/npm/xlsx-js-style@1.2.0/dist/xlsx.bundle.min.js
- 115 ms · 69.9 KB · script · https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js
- 75 ms · 4.3 KB · script · http://127.0.0.1:8002/analytics-ui.js
- 73 ms · 30.0 KB · stylesheet · http://127.0.0.1:8002/visual-system.css

## Erros e falhas

Nenhum.
