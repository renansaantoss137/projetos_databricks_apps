# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Distribuidores Bimbo QSR e equipe comercial interna acompanhando metas, faturamento (sell-in/sell-out), carteira de pedidos (open orders) e cobertura de budget diariamente.

## Product Purpose
Migrar e modernizar o modelo analítico e operacional de vendas da Bimbo Brasil (anteriormente hospedado em Power BI) para uma experiência web corporativa nativa, performática e centralizada, oferecendo visibilidade em tempo real de faturamento realizado, pedidos em carteira, cobertura de metas (Budget e Forecast) e relatórios dinâmicos.

## Positioning
Databricks App corporativo nativo com governança no Unity Catalog, execução acelerada via SQL Warehouse Photon e autenticação On-Behalf-Of (OBO), unificando Vendômetro diário e Report Dinâmico com exportação estruturada, eliminando barreiras de licenças desktop e garantindo integridade e governança de dados corporativos.

## Operating Context
- Utilizado diariamente no início do dia e ao longo dos turnos comerciais para acompanhamento de atingimento de metas e pedidos em carteira.
- Acesso tanto via desktop corporativo quanto via dispositivos móveis (tablets e smartphones) por equipes de campo e distribuidores.
- Ambientes de deploy integrados via Databricks Asset Bundles (DAB) com targets dev e prod.

## Capabilities and Constraints
- **Módulos Centrais:**
  - *Home / Portal:* Apresentação institucional, autenticação corporativa e roteamento seguro.
  - *Vendômetro:* Visão analítica executiva de KPIs (Invoiced, Open Orders, Budget até a data, Cobertura % e YTD).
  - *Report Dinâmico:* Construtor e visualizador de relatórios com filtros multidimensionais (Regional, Gerência, Canal, Distribuidor, Categoria, SKU) e exportação para Excel.
  - *Guia do Usuário & Arquitetura:* Dicionário oficial de KPIs, fórmulas SQL e documentação de engenharia.
- **Restrições Técnicas:**
  - Backend FastAPI (Python) com execução assíncrona e consultas ao Databricks SQL Warehouse (`cat_dnabb_dv`).
  - Cache em memória com TTL por usuário (`user_email:sql`).
  - Frontend em Vanilla HTML5, CSS3 moderno e JavaScript modular (sem dependência de frameworks pesados).
  - Preservação estrita de regras de negócio corporativas (fórmulas oficiais e catálogo de dados).

## Brand Commitments
- Identidade visual corporativa Grupo Bimbo Brasil e Bimbo QSR (Quick Service Restaurants).
- Paleta profissional com suporte a temas Dark / Light, tipografia refinada (`Inter`, `Segoe UI`, `system-ui`) e estética D&A.
- Assets oficiais mantidos: `logo_bimbo.png`, `logo-bimbo-qsr.png`, `logo-dna.png`.

## Evidence on Hand
- Código e páginas funcionais em `src/app/` (`index.html`, `vendometro.html`, `relatorios.html`, `guia.html`, `styles.css`, `home.css`, `app.py`).
- Metadados e modelos históricos em `dna_vendas_metadata.json`, `export_model.json`, `databricks.yml`.
- Assets de identidade visual em `src/app/` e na raiz do repositório.

## Product Principles
1. **Verdade Única dos Dados:** Toda métrica deriva diretamente das tabelas governadas no Unity Catalog e reflete as fórmulas oficiais do negócio.
2. **Clareza e Agilidade Operacional:** Foco em scanability rápido das métricas críticas (Invoiced vs Budget) em menos de 5 segundos de leitura.
3. **Resiliência Multi-dispositivo:** Design plenamente funcional e fluido do mobile ao desktop widescreen corporativo.
4. **Precisão e Restrição:** Modo Operacional onde consistência, precisão numérica e tempos de resposta rápidos têm prioridade sobre ornamentos desnecessários.

## Accessibility & Inclusion
- Alto contraste legível em ambos os temas (Dark/Light).
- Semântica de cabeçalhos e tabelas para leitores de tela e navegação por teclado.
- Failsafes visuais e quebras garantidas para nomes longos de clientes e produtos sem corte de dados críticos.
