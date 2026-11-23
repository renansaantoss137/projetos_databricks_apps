# Medição de páginas

Condições: largura 390px · rede 4g · CPU 4x · 3 repetições com cache vazio · 2026-10-29 09:34

Valores em ms (mediana das repetições). 'Dados na tela' = tempo até o seletor --pronto ficar visível.

| URL | 1º byte | DOM pronto | LCP | Dados na tela | Requisições | KB | Tarefas longas (qtd / maior ms) | Observação |
|---|---|---|---|---|---|---|---|---|
| http://127.0.0.1:8002/performance.html | 14 | 6.055 | 3.884 | 10.988 | 24 | 746.3 | 19 / 1.285 | dados acima de 4000 ms; tarefa longa de 1285 ms |

## Requisições mais lentas (última repetição)

**http://127.0.0.1:8002/performance.html**
- 783 ms · 47.7 KB · font · https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2
- 706 ms · 138.3 KB · script · https://cdn.jsdelivr.net/npm/xlsx-js-style@1.2.0/dist/xlsx.bundle.min.js
- 684 ms · 122.3 KB · script · http://127.0.0.1:8002/i18n.js
- 666 ms · 4.3 KB · script · http://127.0.0.1:8002/analytics-ui.js
- 655 ms · 109.9 KB · stylesheet · http://127.0.0.1:8002/styles.css
- 580 ms · 11.8 KB · script · http://127.0.0.1:8002/mobile-nav.js

## Erros e falhas

Nenhum.

Com rede simulada, a coluna '1º byte' do navegador não inclui a latência simulada; compare 'DOM pronto' e 'Dados na tela'.
