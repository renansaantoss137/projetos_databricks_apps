# Changelog

Todas as alterações relevantes deste projeto são documentadas neste arquivo.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [1.0.0] — 2026-07-16

### Adicionado
- Painel Executivo com KPI cards (Fill Rate, OTIF Geral, Volume, Ação Prioritária)
- Evolução Mensal (Fill Rate vs OTIF, 12+ meses, linha de meta 96%)
- Pareto de Perdas com toggles (FR/OTIF, Planta/Grupo, Geral/CIF/FOB)
- Tabela de Prioridades de Ação (top 5-10)
- Leitura Executiva determinística
- Módulo Fill Rate (visão mensal e semanal)
- Módulo Fill Rate Detalhe (drill-down por pedido)
- Módulo OTIF v2 com base OTM (CIF/FOB separados)
- Módulo OTIF Detalhe (visão por remessa)
- Módulo Gestão de Pedidos (tabela paginada com filtros)
- Regra BOB/KFC com Data Grade Ajustada
- Tolerância 30 min para On Time FOB
- Dark mode / Light mode com toggle
- Filtros dinâmicos (data, planta, grupo, canal, status, busca)
- Health check endpoint `/api/diag`
- Fallback pymssql para ambientes sem ODBC
- Connection pooling com TTL 5 min
- Documentação completa (docs/)

### Infraestrutura
- Deploy via Databricks Apps (compute MEDIUM)
- Secrets via Azure Key Vault / Databricks Secrets
- Conexão direta Azure SQL (sem ETL intermediário)

---

## [0.9.0] — 2026-07-08

### Adicionado
- Validação completa das regras de negócio com equipe logística
- Regra OTIF Geral como total ponderado (não média)
- Exclusão de pedidos futuros no Painel Executivo
- Cap 100% no Fill Rate exibido

### Corrigido
- Cálculo OTIF FOB com tolerância validada
- Filtros de canal excluindo "NÃO DEFINIDO"

---

## [0.8.0] — 2026-07-03

### Adicionado
- Criação inicial do App no Databricks
- Estrutura Flask com endpoints básicos
- Conexão Azure SQL via pyodbc
- Páginas HTML iniciais

---

## [0.1.0] — 2026-06-15

### Adicionado
- Sessão de planejamento e definição de regras de negócio
- Escopo do projeto definido
- Metas 96% acordadas
