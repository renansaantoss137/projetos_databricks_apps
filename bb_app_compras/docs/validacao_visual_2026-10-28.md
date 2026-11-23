# Validação da consolidação visual — 28/10/2026

## Escopo
Home, Performance, Ordens, Comercial, Governança, Relatórios e Guia em execução demo local; CSS compartilhado carregado também por Spend/Cadastros. Cálculos, endpoints, permissões e configuração de deploy preservados.

## Matriz de requisitos
| Requisito | Implementação | Evidência | Status |
|---|---|---|---|
| R1 Cor com significado consistente | visual-system.css e tokens dos gráficos em Comercial/Ordens | Cores computadas do ranking: 3 azuis + 2 de contexto; KPIs neutros | Atendido |
| R2 Hierarquia e densidade | KPIs sem glow/hover, tipografia maior, grade compacta mobile | Capturas desktop e celular | Atendido |
| R3 Gramática de gráficos | barras planas, foco/contexto, legendas e tooltip tokens | Capturas Performance/Comercial; revisão independente | Atendido |
| R4 Nomes completos e texto legível | rankings Comercial/Ordens, tabelas13px, metadados12px | DOM mostra Fornecedor Exemplo A–E completos; sintaxe JS válida | Atendido |
| R5 Contexto e toque mobile | chips em linha própria, controles44px e nav12px | Sete rotas sem overflow global; gaveta e Mais operantes | Atendido |
| R6 Títulos corretos e recuperação | Performance título por vista; analytics-ui.js mensagem acessível+recarga | Alternância tabela/gráfico exercitada; falha de rede não simulada | Implementado; recuperação pendente de teste induzido |
| R7 Ajuda e Home completas | Guia cinco módulos, descrições sem clamp, tabs quebram linha | Guia renderizado em390px | Atendido |
| R8 Temas | tokens claro/escuro e números fora de preenchimentos variáveis | Sete rotas medidas no escuro; capturas Performance/Governança | Atendido nos estados observados |
| R9 Validação e reavaliação | testes abaixo e crítica independente | Relatório e snapshots Impeccable | Atendido |

## Execução
- Sete rotas em390px claro: sem overflow global; chips têm337px de largura e dados visíveis.
- Sete rotas em320,768,1440px escuro: sem overflow global, sem banner de erro de carregamento.
- Fumaça final em abas novas1280px: sete rotas com zero erros de console observados.
- Performance: tema alterna; Spend/Centralização alteram título; Tabela/Gráfico alteram conteúdo e título financeiro correspondente.
- Gaveta de filtros abre com seleções existentes. Mobile Mais abre links Governança/Relatórios.
- Ranking Comercial renderiza nomes completos e foco/contexto correspondentes à legenda.
- Exportação XLSX Comercial: arquivo renegociacao_pedidos.xlsx baixado, ZIP/XML válido, seis linhas (cabeçalho+cinco registros).
- Sintaxe: oito scripts inline e analytics-ui.js/i18n.js passaram node --check.
- Erro preexistente encontrado em Comercial: Chart tentava usar canvas chartDiscount removido; função agora retorna quando canvas ausente. Aba nova confirmou console sem erro.

## Limitações
pytest não executou: módulo pytest ausente no ambiente local. A validação funcional usou app rodando e endpoints/controles. Conferência tela×API×SQL real não executada: Lakebase local indisponível; demo não comprova integridade de números produtivos. Não se alterou regra de negócio para fazer números baterem.
Sem aparelho físico, Safari, gesto sintetizado, zoom200%, teste completo de teclado ou todos os filtros/exportações. Cadastros dependem de permissão; revisão por fonte. Mensagem de erro possui retry real por recarga, sem teste de falha induzida nesta sessão.
Pontuação heurística é julgamento de design, não certificação de acessibilidade. Avisos do detector não equivalem a problemas distintos; exemplos do Guia e estilos antigos sobrepostos podem ser falsos positivos.

## Ajuste do padrão de gráficos após referência de Performance
Aplicado em ordens.html, governanca.html, comercial.html e visual-system.css. Rankings medidos com barras24px; maior linha em foco e restantes contexto, quantidades fora das barras. Colunas de Ordens preservam realizado/restante, destacam mês filtrado e exibem percentuais neutros abaixo do eixo; tabela alternativa com12meses abriu corretamente.
Browser: três rotas em390px sem overflow global (scrollWidth383); gráfico mensal600px rola dentro de337px, sem comprimir12rótulos. Tema escuro desktop inspecionado; console de Ordens sem erros; scripts alterados passaram node --check. Detector111avisos candidatos no app, não equivalentes a111defeitos visíveis. Sem alteração de backend ou deploy.

## Cabeçalho, escala e rótulos de Ordens
Filtros movidos para o cabeçalho compartilhado, entre título e menu em desktop; segunda linha em telas menores. Escala em select dentro do menu, testada85%→100%. Gaveta de filtros abriu após mudança. Performance, Comercial, Governança e Relatórios verificados em390px: filtros no cabeçalho, sem overflow global e sem erros de console observados.
Ordens: texto de período simplificado; cabeçalhos redundantes removidos; quantidades com OCs e atraso com dias; legenda de realizado mostra contexto+foco e restante cinza. Sintaxe de Ordens/view-scale/analytics-ui passou Node.
