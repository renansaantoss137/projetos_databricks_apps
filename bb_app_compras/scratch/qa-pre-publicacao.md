# QA e performance antes da publicação — 29/10/2026

## Ambiente e limite
- Porta 8002: demonstração com dados fictícios. Os resultados desse ambiente não validam dados ou desempenho do Lakebase.
- Porta 8003: app real iniciado temporariamente; /api/health retornou 500. Lakebase recusou a conexão por política de rede do workspace. Sem acesso ao banco, conferência tela × API × SQL, testes dos filtros sobre SQL e medição com dados reais não foram executados.
- Sem alteração de regras de negócio, dados ou deploy.

## Matriz de verificações
| Verificação | Resultado | Evidência / limite |
|---|---|---|
| Fumaça de oito telas, 390 e 1440 px | 14 de 16 passaram | qa-fumaca-demo.md e qa-capturas/; cadastros recebe 501 de duas APIs não implementadas no servidor de demonstração, sem concluir sobre produção |
| Menu do usuário e seleção de tema do sistema, cinco páginas em 390 e 1440 px | Passou | qa-controles-local.py, execução Playwright: menu aberto e aria-pressed=true |
| Inventário de controles no celular | Alertas | qa-inventario-mobile.md: alvos pequenos e controles de cabeçalho sem semântica; verificar cada ocorrência manualmente |
| Filtros sincronizados e valores, busca, ordenação, paginação e exportações | Não executado integralmente | exige testes funcionais adicionais e banco real; download não conferido |
| Tela × API × banco, cenários filtrados e totais | Não executado | Lakebase inacessível por política de rede |
| pytest | Não concluído | coleta genérica percorreu scripts scratch de diagnóstico; interrompida para evitar execução indiscriminada; falta suíte isolada documentada |

## Performance
- API demonstrativa, cinco chamadas quentes por rota: p95 3 a 15 ms, respostas 0,1 a 16,2 KB. Dados não representam consultas reais. Ver qa-performance-demo.md.
- Performance desktop demonstrativo, três execuções: dados 1539 ms (meta 2000 ms), transferência 746,3 KB, maior tarefa 203 ms. Ver qa-pagina-desktop-demo.md. Dados transferidos incluem fontes e bibliotecas; a meta de 300 KB exclui aquelas em cache, portanto não é diretamente comparável.
- Performance mobile, 4G e CPU 4x, três execuções isoladas: 10988 ms até dados (meta 4000 ms), maior tarefa 1285 ms. Ver qa-pagina-mobile-isolado-demo.md. A medição concorrente anterior foi 13646 ms e não é comparável.
- Não houve otimização: gargalo de produção e tempos antes/depois não podem ser demonstrados sem acesso ao Lakebase e medição comparável. Identificar custos de i18n.js, Chart.js, biblioteca XLSX e carregamento das fontes nas medições isoladas; validar ganhos e números antes/depois.

## Pendências antes da publicação
1. Executar health, smoke, performance e conferência de valores em ambiente autorizado com Lakebase real, preservando usuários/permissões e sem modificar dados.
2. Exercitar filtros compartilhados, exportações, paginação, busca, ordenação, idiomas, menu e cadastro autorizado nas duas larguras.
3. Investigar lentidão em celular isoladamente; corrigir gargalos medidos e repetir medições e conferência de valores.
4. Revisar alertas de acessibilidade do inventário e disponibilizar uma suíte de testes segura e isolada.


## Ajuste aplicado após a revisão
- Performance: biblioteca XLSX carregada somente ao exportar; falha de rede informa o usuário e permite tentar novamente.
- Mesmo cenário isolado (demo, 390 px, 4G, CPU 4x, três repetições): dados na tela 10.988 → 5.926 ms; transferência total 746,3 → 608,8 KB; maior tarefa 1.285 → 617 ms. Ainda acima da meta de 4 s e de 200 ms. Ver qa-pagina-mobile-isolado-demo.md e qa-pagina-mobile-depois-demo.md.
- Playwright em 390 e 1440 px verificou ausência de carga XLSX inicial e download sob demanda; arquivo abre com 8 linhas e 11 colunas, KPI exibido R$ 2,9 Bi. Ver qa-export-performance.py. É validação demonstrativa, não conferência de dados reais.
