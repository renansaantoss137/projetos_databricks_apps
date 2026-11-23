# Medição de páginas

Condições: largura 390px · rede 4g · CPU 4x · 3 repetições com cache vazio · 2026-10-29 09:32

Valores em ms (mediana das repetições). 'Dados na tela' = tempo até o seletor --pronto ficar visível.

| URL | 1º byte | DOM pronto | LCP | Dados na tela | Requisições | KB | Tarefas longas (qtd / maior ms) | Observação |
|---|---|---|---|---|---|---|---|---|
| http://127.0.0.1:8002/performance.html | 15 | 6.773 | 4.364 | 13.646 | 24 | 746.3 | 22 / 1.484 | dados acima de 4000 ms; tarefa longa de 1484 ms |

## Requisições mais lentas (última repetição)

**http://127.0.0.1:8002/performance.html**
- 1819 ms · 47.7 KB · font · https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2
- 689 ms · 138.3 KB · script · https://cdn.jsdelivr.net/npm/xlsx-js-style@1.2.0/dist/xlsx.bundle.min.js
- 653 ms · 122.3 KB · script · http://127.0.0.1:8002/i18n.js
- 635 ms · 109.9 KB · stylesheet · http://127.0.0.1:8002/styles.css
- 584 ms · 1.3 KB · stylesheet · https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap
- 561 ms · 4.3 KB · script · http://127.0.0.1:8002/analytics-ui.js

## Erros e falhas

Nenhum.

Com rede simulada, a coluna '1º byte' do navegador não inclui a latência simulada; compare 'DOM pronto' e 'Dados na tela'.
