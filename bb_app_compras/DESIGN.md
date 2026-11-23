# Sistema visual analítico

Modo: Operate nas páginas analíticas; Read no Guia. Identidade D&A existente preservada.

- Fonte Inter; texto de tabela 13px, metadados/legendas 12px, títulos de visual 14–16px.
- Azul principal `--chart-focus` para série em foco; `--chart-context` para contexto; `--chart-compare` para comparação.
- Azul de ação `--analytics-control` com texto branco. Semáforo reservado a resultado/meta explicitamente definidos, nunca a um tipo de exceção.
- Valores de KPI neutros, metadados secundários, ícones neutros; sem brilho ou hover de cartão não interativo.
- Barras planas, títulos conclusivos preservados e tooltip legível. Contorno no traço de comparação sobre colunas.
- Tabelas preservam precisão e exportação; rolagem localizada em celular, primeira coluna fixa onde apropriado.
- Filtros ativos em faixa própria no celular; controles principais com 44px de altura; rankings com nome completo acima da barra.
- Erros de APIs analíticas ganham mensagem acessível e botão de recarga, sem mudar o contrato de dados.
- Arquivos compartilhados: src/app/visual-system.css e src/app/analytics-ui.js, carregados por todas as páginas.
- Claro/escuro usam os tokens de superfície existentes. Home preserva marca e conteúdo; não cria uma identidade nova.

## Gramática de gráficos adotada a partir de Performance
- Colunas mensais: contexto azul suave, mês filtrado em azul de foco, eixo Y e grade omitidos, linha de base discreta, percentual neutro sob cada mês; só o total do mês em foco recebe rótulo superior.
- Ordens mantém empilhamento realizado/restante; restante usa token próprio e todos os valores ficam disponíveis em tooltip e tabela expansível.
- Rankings de Ordens/Governança/Comercial: barras24px, cantos2px, linhas36px no desktop, espaçamento10px, nomes13px, valores13px e quantidades12px fora da barra. Maior linha em foco; demais no token de contexto. Larguras continuam representando a métrica original de cada visual.
- No celular: nome acima da barra, valor à direita, quantidade/dias em linha auxiliar; rolagem global evitada, sem esconder números.
