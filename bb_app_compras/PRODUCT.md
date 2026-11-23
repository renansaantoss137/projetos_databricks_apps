# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Equipe interna de Compras/Suprimentos, analistas e lideranças do Grupo Bimbo Brasil (DNA Analytics e Procurement Leaders), atuando em rotinas de negociação, fechamento mensal, homologação de fornecedores e auditoria de compras corporativas.

## Product Purpose

Portal unificado de inteligência e governança de compras (Compras 360°). Centraliza métricas operacionais, táticas e estratégicas da Bimbo Brasil, permitindo monitoramento de spend, savings acumulados, cumprimento de prazos de pagamento, desempenho de ordens e mitigação de riscos de conformidade em compras. O sucesso significa visibilidade fidedigna dos dados transacionais, tomada de decisão rápida e controle estrito de exceções.

## Positioning

Portal analítico corporativo de compras 360° integrado nativamente ao ecossistema Databricks Apps e Lakebase PostgreSQL da Bimbo Brasil, combinando filtros corporativos compartilhados, detecção automática de não conformidades (OCs pós-fatura, compras descentralizadas, notas sem OC) e consolidação automatizada das fontes corporativas (Oracle Cloud / SAP).

## Operating Context

- Aplicação web corporativa executada via Databricks Apps (Azure Databricks) sob autenticação corporativa `@grupobimbo.com` com controle de acesso (`CAN_MANAGE` para DNA Leaders).
- Consultada em computadores corporativos (desktop) e dispositivos móveis/tablets (responsive web).
- Integrada ao banco Lakebase PostgreSQL gerenciado via Databricks Asset Bundles (DAB).
- Utilizada em reuniões de resultados de suprimentos, auditorias de governança e monitoramento diário de entregas e pagamentos.

## Capabilities and Constraints

- Módulos analíticos: Performance de Compras, Gestão de Ordens, Condições Comerciais, Governança & Exceções e Relatórios & Exportações (com módulo de Spend preservado no código para ativação futura).
- Painel unificado de filtros cascateados com recolhimento lateral rápido (Ano, Mês, Empresa BB/BQ, Categoria/Grupo de Compras DIRETOS/INDIRETOS, Fornecedor, Planta/Unidade).
- Backend Flask em Python estruturado em REST APIs (/api/performance, /api/comercial, /api/ordens, /api/governanca, /api/relatorios, /api/filters).
- Frontend Vanilla estruturado em HTML5, CSS corporativo e Vanilla JS, otimizado para carregamento veloz sem dependências pesadas de frameworks externos.
- **Restrição de deploy inegociável**: O assistente nunca deve executar comandos de deploy no Databricks (`databricks apps deploy` ou `databricks bundle deploy`); o deploy é realizado e controlado exclusivamente pelo usuário.
- Resolução e paridade contínua com a base corporativa de produção.

## Brand Commitments

- Padrão visual estrito de identidade corporativa D&A Bimbo Brasil (DNA Analytics / DNA de Vendas):
  - Fundo neutro e sobriedade analítica corporativa (telas internas claras `#F0F4F8`, home institucional profunda).
  - Azul corporativo como cor primordial de ação, foco e seleção (`--primary: #2563EB`, `--focus-ring: #2563EB`).
  - Vermelho corporativo Bimbo (`--brand-red: #C02830`) estritamente reservado ao logotipo Bimbo (alertas e erros utilizam `--danger: #B91C1C`).
  - Semáforos funcionais: verde para metas/sucesso, âmbar para atenção/alerta, vermelho para desvios/perigo.
  - Logos em destaque no cabeçalho e na tela inicial: Data & Analytics e Grupo Bimbo.

## Evidence on Hand

- Código-fonte completo em `src/app/` com todas as páginas HTML, CSS corporativo (`styles.css`), componentes de menu (`app-menu.js`) e filtros (`filters-component.js`, `filters-shared.js`).
- Scripts e notebooks de ETL em `src/dados/` e tabelas de suporte CSV/XLSX de compradores e fornecedores.
- Views analíticas em `docs/sql/` e documentação técnica em `docs/documentacao_tecnica.md` e `docs/guia_do_usuario.md`.
- App de Produção em execução no Databricks Apps (`https://compras-360-8674310331778219.19.azure.databricksapps.com`).

## Product Principles

1. **Sobriedade Analítica e Densidade de Informação**: Foco absoluto na clareza dos dados e facilidade de leitura; superfícies limpas, tipografia com números tabulares e ausência de ruídos visuais decorativos.
2. **Consistência 360° em Toda a Jornada**: Filtros globais sincronizados e métricas calculadas sob a mesma regra de negócio entre todas as telas.
3. **Ação Orientada por Dados**: Destaque visual claro para desvios de processo e exceções operacionais, direcionando o comprador ou gestor imediatamente à causa raiz e oportunidade de negociação.
4. **Resiliência e Desempenho Local/Nuvem**: Inicialização imediata de interface sem travas de rede, com carregamento assíncrono e tratamento gracioso de falhas ou ausência de dados.

## Accessibility & Inclusion

- Contraste mínimo de 4.5:1 para textos corporativos e 3:1 para controles/bordas de inputs (`--border-input: #7D8CA1`).
- Suporte a navegação por teclado nos componentes de navegação e filtros, com anéis de foco visíveis (`--focus-ring`).
- Status e indicadores nunca dependem exclusivamente da cor (acompanhados de texto descritivo, ícone ou sinalização).
