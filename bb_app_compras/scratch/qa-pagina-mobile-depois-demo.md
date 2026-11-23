# Medição de páginas

Condições: largura 390px · rede 4g · CPU 4x · 3 repetições com cache vazio · 2026-10-29 09:36

Valores em ms (mediana das repetições). 'Dados na tela' = tempo até o seletor --pronto ficar visível.

| URL | 1º byte | DOM pronto | LCP | Dados na tela | Requisições | KB | Tarefas longas (qtd / maior ms) | Observação |
|---|---|---|---|---|---|---|---|---|
| http://127.0.0.1:8002/performance.html | 12 | 3.030 | 2.780 | 5.926 | 23 | 608.8 | 15 / 617 | dados acima de 4000 ms; tarefa longa de 617 ms |

## Requisições mais lentas (última repetição)

**http://127.0.0.1:8002/performance.html**
- 1244 ms · 47.7 KB · font · https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2
- 603 ms · 1.3 KB · stylesheet · https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap
- 576 ms · 4.3 KB · script · http://127.0.0.1:8002/analytics-ui.js
- 561 ms · 122.3 KB · script · http://127.0.0.1:8002/i18n.js
- 547 ms · 109.9 KB · stylesheet · http://127.0.0.1:8002/styles.css
- 515 ms · 11.8 KB · script · http://127.0.0.1:8002/mobile-nav.js

## Erros e falhas

Nenhum.

Com rede simulada, a coluna '1º byte' do navegador não inclui a latência simulada; compare 'DOM pronto' e 'Dados na tela'.
