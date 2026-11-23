# Documentação Técnica

> **Última atualização**: Agosto 2026  
> **Responsável**: renan.ferreira@grupobimbo.com  
> **App URL**: https://compras-360-8674310331778219.19.azure.databricksapps.com

---

## 1. Visão Geral

O app **compras** é o portal de inteligência de compras do Grupo Bimbo Brasil. Consolida dados de notas fiscais, ordens de compra e requisições do Oracle Cloud em um painel interativo com KPIs, gráficos e tabelas exportáveis. O objetivo é dar visibilidade rápida ao gasto, savings, prazos e exceções de processo — tudo em um único lugar.

---

## 2. Manual Detalhado de Métricas, Fórmulas e Segmentações por Aba

Este manual técnico fornece o detalhamento exaustivo de **cada indicador, gráfico e tabela analítica** do Portal de Compras. Para cada elemento, são documentadas a fórmula matemática, a coluna de data filtrada pelos seletores de período (segmentação temporal), as tabelas e colunas de origem e as regras de negócio ou exclusões corporativas aplicadas.

### 2.1 Lógica das Âncoras Temporais de Segmentação

Os filtros do cabeçalho superior (**Ano**, **Mês**, **Dia** e **Período Personalizado De/Até**) incidem sobre campos de data distintos conforme o módulo e a natureza da análise:

| Módulo | Âncora Temporal (Campo Filtrado) | Descrição do Campo |
| --- | --- | --- |
| **01. Performance** | `notas_ri.DATA_LANCAMENTO` | Data contábil da nota fiscal de recebimento (visuais contábeis: spend, prazos, centralização) |
| **01. Performance (Funil)** | `ordens_compra.DATA_OC` (Diretos/Todos)<br>`requisicoes.dt_aprovacao` (Indiretos) | Coorte de emissão de pedidos (Diretos/Todos) ou geração de requisições (Indiretos) com acompanhamento downstream das etapas de aprovação e faturamento |
| **02. Gastos (Spend)** | `notas_ri.DATA_LANCAMENTO` | Data contábil da nota fiscal de recebimento |
| **03. Gestão de Ordens** | `ordens_compra.DATA_OC` | Data oficial de criação/emissão da ordem de compra |
| **04. Comercial** | `notas_ri.DATA_LANCAMENTO` | Data contábil da nota fiscal de recebimento |
| **05. Governança** | `notas_ri.DATA_LANCAMENTO` | Data contábil da nota fiscal de recebimento |
| **06. Relatórios** | Dinâmica por Fonte | `notas_ri` → `data_lancamento`; `ordens_compra` → `data_oc`; `requisicoes` → `COALESCE(dt_aprovacao, dt_criacao)` |

---

### 2.2 Módulo 01 — Performance de Compras (`performance.html`)

* **Tabela Base Principal**: `notas_ri` (com cruzamento em `ordens_compra` e `requisicoes` para lead time e alertas).
* **Âncora de Data Padrão**: `notas_ri.DATA_LANCAMENTO`.

| Visual / Componente | Tipo | Métrica & Fórmula de Cálculo | Tabelas & Colunas | Âncora de Data | Regras de Negócio & Filtros |
| --- | --- | --- | --- | --- | --- |
| **Spend Líquido** | KPI Card | `SUM(valor_liquido_brl)`<br>**YoY/MoM**: Se Ano+Mês: vs mês anterior até mesmo dia. Se só Ano: YTD vs YTD ano anterior.<br>`((Spend_Atual - Spend_Ant) / Spend_Ant) * 100` | `notas_ri.valor_liquido_brl` | `notas_ri.data_lancamento` | Exclusão de `grupo_compras = 'COMERCIAL'`. Moedas estrangeiras convertidas para BRL pela taxa PTAX oficial do Oracle. |
| **Prazo Médio** | KPI Card | `SUM(pgto_x_valor) / SUM(valor_liquido_brl)`<br>Prazo médio ponderado pelo valor da NF em dias corridos. | `notas_ri.pgto_x_valor`, `notas_ri.valor_liquido_brl` | `notas_ri.data_lancamento` | Coluna `pgto_x_valor = prazo_pgto * valor_liquido_brl` pré-calculada no ETL para agregação aditiva instantânea. |
| **Centralização (%)** | KPI Card | `(SUM(CASE WHEN centralizado = 'CENTRALIZADO' THEN valor_liquido_brl ELSE 0 END) / SUM(valor_liquido_brl)) * 100` | `notas_ri.centralizado`, `notas_ri.valor_liquido_brl` | `notas_ri.data_lancamento` | Centralizado se: OC Blanket; OC Standard ≥ R$ 30K de comprador Compras; OC com Acordo BPA; ou comprador da área Compras. |
| **Spend YoY Mensal** | Gráfico | `SUM(valor_liquido_brl)` agrupado por mês `SUBSTRING(data_lancamento, 6, 2)` comparando ano $Y$ vs ano $Y-1$. | `notas_ri.valor_liquido_brl` | `notas_ri.data_lancamento` | Revela sazonalidade e taxa de expansão orçamentária mês a mês. |
| **Aumento de Preço / Descontos** | Tabela / Gráfico | `Impacto = SUM(saving_total)`<br>`Δ Preço = preco_unit_atual - preco_unit_ant`<br>Toggle executivo: alternância entre Tabela e Gráfico. | `notas_ri.saving_total`, `notas_ri.preco_unitario_brl` | `notas_ri.data_lancamento` | Filtro de sanidade: somente percentuais de aumento/desconto entre 0% e 100% são aceitos. |
| **Funil de Lead Time (Process Funnel)** | Funil | **1. Req → Pedido**: `AVG(data_oc - dt_aprov_req)`<br>**2. Pedido → Aprovação**: `AVG(dt_aprov_oc - data_oc)`<br>**3. Pedido Aprovado → 1ª NF**: `AVG(min_data_nf - dt_aprov_oc)`<br>**4. 1ª NF → Conclusão**: `AVG(max_data_nf - min_data_nf)`<br>**Volumes**:<br>• Reqs: `COUNT(DISTINCT requisicao)` (Indiretos)<br>• Pedidos Emitidos: `COUNT(DISTINCT numero_oc)` (coorte de emissão, excluindo canceladas/incompletas)<br>• Pedidos Aprovados: `COUNT(DISTINCT numero_oc)` (APPROVED / com aprovação)<br>• Faturamento Iniciado / Concluído | `requisicoes`, `ordens_compra`, `notas_ri` | `ordens_compra.DATA_OC` (Diretos/Todos)<br>`requisicoes.dt_aprovacao` (Indiretos) | Para Diretos e Todos, a coorte é ancorada na emissão dos pedidos (`DATA_OC`), acompanhando a taxa real de aprovação e faturamento posterior sem clamping artificial. Para Indiretos, é ancorada na aprovação/criação das requisições. |
| **Desvios de Processo** | Gráfico | `SUM(valor_liquido_brl)` quebrado por: *OC Pós-Fatura* (`data_oc > data_lancamento`), *Descentralizadas* (`centralizado = 'DESCENTRALIZADO'`) e *Notas sem OC* (`numero_oc = 'Nota sem OC'`). | `notas_ri.data_lancamento`, `notas_ri.data_oc`, `notas_ri.centralizado` | `notas_ri.data_lancamento` | Mensura o montante de vazamento de valor e não conformidade operacional. |
| **O que exige atenção agora** | Alerta Operacional | Exibe Qtd, % Qtd, Valor R$ e % Valor:<br>1. *OCs após fatura*: `oc_pos_fatura = 'SIM'` (âncora em data_pagamento)<br>2. *Descentralizadas > R$ 30K*: `centralizado = 'DESCENTRALIZADO' AND valor >= 30000` (exclui compradores de compras)<br>3. *Reqs pendentes aprovação*: `status` pendente (`dt_aprovacao IS NULL`)<br>4. *OCs aprovadas sem NF > 90d*: `status_aprovacao = 'APPROVED'` sem NF após 90d | `notas_ri`, `requisicoes`, `ordens_compra`, `compradores_funcionais` | • Linha 1: `notas_ri.data_pagamento`<br>• Linha 2: `notas_ri.data_lancamento`<br>• Linha 3: `requisicoes.dt_criacao`<br>• Linha 4: `ordens_compra.dt_aprovacao` | Cruza com `compradores_funcionais` para expurgar compradores funcionais de compras da regra de descentralizadas > 30K. |

---

### 2.3 Módulo 02 — Análise de Gastos / Spend (`spend.html`)

* **Tabela Base Principal**: `notas_ri`.
* **Âncora de Data Padrão**: `notas_ri.DATA_LANCAMENTO`.

| Visual / Componente | Tipo | Métrica & Fórmula de Cálculo | Tabelas & Colunas | Âncora de Data | Regras de Negócio & Filtros |
| --- | --- | --- | --- | --- | --- |
| **Spend por Empresa** | Gráfico | `SUM(valor_liquido_brl)` agrupado por `empresa` ('BB' vs 'BQ'). | `notas_ri.empresa`, `notas_ri.valor_liquido_brl` | `notas_ri.data_lancamento` | BU Oracle `300000002033035` = BB; BU `300000002033048` = BQ. |
| **Top Fornecedores & Itens** | Gráfico / Ranking | `SUM(valor_liquido_brl) ORDER BY 1 DESC LIMIT N` | `notas_ri.nome_fornecedor`, `notas_ri.descricao_item` | `notas_ri.data_lancamento` | Suporta cross-filtering ao clicar nas barras para refinar todos os demais visuais. |
| **Spend por Macro Categoria** | Gráfico | `SUM(valor_liquido_brl) GROUP BY COALESCE(macro_categoria, 'Indiretos')` | `notas_ri.macro_categoria` | `notas_ri.data_lancamento` | Valores nulos são classificados automaticamente como 'Indiretos'. |
| **Spend por Planta Fabril** | Gráfico / Mapa | `SUM(valor_liquido_brl) GROUP BY planta` | `notas_ri.planta` | `notas_ri.data_lancamento` | Desagrega os gastos pelas fábricas industriais do grupo. |
| **Curva ABC Dinâmica** | Curva ABC | Percentual cumulativo ordenado decrescente:<br>• **Classe A**: 0% a 80% do spend (itens críticos)<br>• **Classe B**: 80% a 95% do spend (intermediários)<br>• **Classe C**: 95% a 100% do spend (cauda longa) | `notas_ri.valor_liquido_brl`, `notas_ri.nome_fornecedor`, `notas_ri.codigo_item` | `notas_ri.data_lancamento` | Calculada dinamicamente via Window Function `SUM(...) OVER (ORDER BY ...)`. |
| **Matriz de Centralização** | Tabela | `% Centralizado = Spend_Centralizado / Spend_Total * 100` por macro categoria ou fornecedor. | `notas_ri.macro_categoria`, `notas_ri.centralizado` | `notas_ri.data_lancamento` | Revela categorias com alto índice de desvio descentralizado. |

---

### 2.4 Módulo 03 — Gestão de Ordens (`ordens.html`)

* **Tabela Base Principal**: `ordens_compra`.
* **Âncora de Data Padrão**: `ordens_compra.DATA_OC` (data de emissão da ordem de compra).

| Visual / Componente | Tipo | Métrica & Fórmula de Cálculo | Tabelas & Colunas | Âncora de Data | Regras de Negócio & Filtros |
| --- | --- | --- | --- | --- | --- |
| **Total de Ordens** | KPI Card | `COUNT(DISTINCT numero_oc)` | `ordens_compra.numero_oc` | `ordens_compra.data_oc` | Conta pedidos únicos emitidos no período selecionado. |
| **Valor Total Emitido** | KPI Card | `SUM(valor_original_brl)` | `ordens_compra.valor_original_brl` | `ordens_compra.data_oc` | Montante financeiro contratado nas linhas de pedido. |
| **Saldo em Aberto** | KPI Card | `SUM(valor_original_brl - COALESCE(valor_utilizado_brl, 0))` onde `status_fechamento = 'ABERTA'`. | `ordens_compra.valor_original_brl`, `ordens_compra.status_fechamento` | `ordens_compra.data_oc` | Passivo financeiro pendente de entrega física e faturamento. |
| **OCs em Atraso** | KPI Card | `COUNT(DISTINCT numero_oc)` e `SUM(saldo_aberto)` onde `status_fechamento = 'ABERTA' AND CURRENT_DATE > COALESCE(dt_prometida, dt_necessidade)`. | `ordens_compra.dt_prometida`, `ordens_compra.dt_necessidade` | `ordens_compra.data_oc` | Ordens que já deveriam ter sido entregues na fábrica e seguem abertas. |
| **Previsto vs. Realizado** | Gráfico | Previsto: `SUM(valor_original_brl)`<br>Realizado: `SUM(valor_utilizado_brl)`<br>Agrupado por mês de emissão `SUBSTRING(data_oc, 1, 7)`. | `ordens_compra.valor_original_brl`, `ordens_compra.valor_utilizado_brl` | `ordens_compra.data_oc` | Compara o volume contratado versus o consumo efetivamente liquidado. |
| **Faixas de Atraso (Buckets)** | Gráfico | `CURRENT_DATE - dt_prometida::date` agrupado em: *< 15 dias*, *15-30 dias*, *31-60 dias*, *> 60 dias*. | `ordens_compra.dt_prometida` | `ordens_compra.data_oc` | Aging de inadimplência de entrega para cancelamento ou cobrança. |
| **Tabela de Ordens em Aberto** | Tabela | Grid analítico com paginação, busca e ordenação por dias de atraso, fornecedor, comprador e valor em aberto. | `ordens_compra` | `ordens_compra.data_oc` | Permite aos compradores acompanharem sua carteira individual de pedidos. |

---

### 2.5 Módulo 04 — Condições Comerciais (`comercial.html`)

* **Tabela Base Principal**: `notas_ri`.
* **Âncora de Data Padrão**: `notas_ri.DATA_LANCAMENTO`.

| Visual / Componente | Tipo | Métrica & Fórmula de Cálculo | Tabelas & Colunas | Âncora de Data | Regras de Negócio & Filtros |
| --- | --- | --- | --- | --- | --- |
| **Prazo Médio Geral** | KPI Card | `SUM(pgto_x_valor) / SUM(valor_liquido_brl)` | `notas_ri.pgto_x_valor`, `notas_ri.valor_liquido_brl` | `notas_ri.data_lancamento` | Média ponderada pela liquidez financeira em dias corridos. |
| **% Spend Prazo Longo** | KPI Card | `(SUM(CASE WHEN prazo_pgto >= 60 THEN valor_liquido_brl ELSE 0 END) / SUM(valor_liquido_brl)) * 100` | `notas_ri.prazo_pgto`, `notas_ri.valor_liquido_brl` | `notas_ri.data_lancamento` | Percentual do spend que atende à meta de prazo longo (DPO ≥ 60 dias). |
| **Fornecedores Críticos** | KPI Card | `COUNT(DISTINCT nome_fornecedor) WHERE prazo_medio_forn < 60` | `notas_ri.nome_fornecedor`, `notas_ri.prazo_pgto` | `notas_ri.data_lancamento` | Fornecedores que operam abaixo da meta corporativa. |
| **Evolução Mensal do Prazo** | Gráfico | Média ponderada calculada mês a mês por `data_lancamento`. | `notas_ri` | `notas_ri.data_lancamento` | Mostra se os prazos de pagamento estão se expandindo ou encolhendo. |
| **Distribuição de Prazos** | Gráfico | Spend agrupado nas faixas: *À Vista (0d)*, *1-30d*, *31-60d*, *61-90d*, *> 90d*. | `notas_ri.prazo_pgto` | `notas_ri.data_lancamento` | Identifica concentração de pagamentos que pressionam o fluxo de caixa. |
| **Matriz de Renegociação (Working Capital)** | Tabela | `Potencial = (60 - Prazo_Atual) * (Spend_Anual / 360)` | `notas_ri.nome_fornecedor`, `notas_ri.prazo_pgto`, `notas_ri.valor_liquido_brl` | `notas_ri.data_lancamento` | Estima o valor de capital de giro liberado ao elevar o prazo do fornecedor para 60 dias. |

---

### 2.6 Módulo 05 — Governança (`governanca.html`)

* **Tabela Base Principal**: `notas_ri` + tabelas de lookup (`compradores_funcionais`).
* **Âncora de Data Padrão**: `notas_ri.DATA_LANCAMENTO`.

| Visual / Componente | Tipo | Métrica & Fórmula de Cálculo | Tabelas & Colunas | Âncora de Data | Regras de Negócio & Filtros |
| --- | --- | --- | --- | --- | --- |
| **Índice de Conformidade** | KPI Card | `(1 - (SUM(valor_desvios) / SUM(valor_liquido_brl))) * 100` | `notas_ri` | `notas_ri.data_lancamento` | Mede o percentual do spend 100% aderente a todas as políticas de compras. |
| **OC Pós-Fatura** | Card Exceção | `COUNT(DISTINCT numero_oc)` e `SUM(valor_liquido_brl)` onde `oc_pos_fatura = 'SIM'` (`dt_nota < ApprovedDate`). | `notas_ri.numero_oc`, `notas_ri.oc_pos_fatura`, `notas_ri.data_pagamento` | `notas_ri.data_pagamento` | Fato consumado: a mercadoria/nota chegou antes da emissão/aprovação formal do pedido. A âncora de data de referência para o filtro é a data de pagamento da fatura. |
| **Notas sem OC** | Card Exceção | `COUNT(DISTINCT nota_fiscal)` e `SUM(valor_liquido_brl)` onde `numero_oc = 'Nota sem OC'`. | `notas_ri.numero_oc` | `notas_ri.data_lancamento` | NFs recebidas e lançadas sem vínculo a nenhum pedido de compra. |
| **Descentralizadas > R$ 30K** | Card Exceção | `COUNT(DISTINCT numero_oc)` e `SUM(valor_liquido_brl)` onde `centralizado = 'DESCENTRALIZADO' AND valor >= 30000`. | `notas_ri.centralizado`, `compradores_funcionais` | `notas_ri.data_lancamento` | **Exclusão:** Compradores da área 'Compras' são excluídos desta contagem. |
| **Impacto & Tendência** | Gráfico | `SUM(valor_liquido_brl)` de exceções agrupado mês a mês. | `notas_ri` | `notas_ri.data_lancamento` | Avalia se as ações corretivas estão reduzindo o volume de desvios. |
| **Desvios por Comprador / Unidade** | Tabela | Ranking de reincidência de exceções por usuário comprador e por planta fabril. | `notas_ri.planta`, `ordens_compra.nome_usuario` | `notas_ri.data_lancamento` | Subsidia auditorias internas e direcionamento de treinamentos. |

---

### 2.7 Módulo 06 — Relatórios (`relatorios.html`)

* **Tabela Base**: Selecionada dinamicamente pelo usuário no menu **Fonte**.
* **Âncora de Data**: Varia estritamente de acordo com a fonte escolhida.

| Fonte Selecionada | Tabela Principal | Âncora Temporal Filtrada | Principais Colunas Disponíveis & Recursos |
| --- | --- | --- | --- |
| **Notas Fiscais (RI)** | `notas_ri` | `notas_ri.DATA_LANCAMENTO` | Número RI, Nota Fiscal, Série, Data Lançamento, CNPJ Bimbo, Fornecedor, CNPJ Fornecedor, Item, Descrição, Valor Líquido, Saving Total, Prazo Pagamento, Status Pagamento, Centralizado, Planta. |
| **Ordens de Compra** | `ordens_compra` | `ordens_compra.DATA_OC` | Número OC, Linha, Acordo, Data OC, Data Prometida, Fornecedor, Comprador, Unidade, Valor Original BRL, Valor Utilizado BRL, Status Aprovação, Status Fechamento, Centralizado. |
| **Requisições** | `requisicoes` | `COALESCE(dt_aprovacao, dt_criacao)` | Número Requisição, Data Criação, Data Aprovação, Requisitante, Descrição, Valor Requisição, Status Requisição, Status Ordem, Número OC Gerada. |

* **Recursos do Motor de Relatórios**: Paginação server-side (10 a 100 linhas/pág), ordenação dinâmica por qualquer coluna, busca textual multi-campo e exportação integral sem limites de visualização para planilha Excel (.xlsx / .csv).

---

### 2.8 Módulo 07 — Cadastros de Apoio (`cadastros.html`)

* **Tabelas Gerenciadas**: Bases dimensionais sincronizadas em tempo real (dual-write no Volume do Unity Catalog e tabelas Lakebase).

| Tabela de Apoio | Arquivo no Volume | Chave Primária | Impacto nas Regras de Negócio |
| --- | --- | --- | --- |
| `fornecedores_especiais` | `fornecedores_especiais.csv` | `cod_fornecedor_oracle` | Isola fornecedores com regime especial de contratação (utilities, impostos, aluguéis, intercompany). |
| `fornecedores_nao_negociaveis` | `fornecedores_nao_negociaiveis.csv` | `cod_fornecedor_oracle` | Fornecedores regulados e cartoriais que não entram no cálculo de metas de saving. |
| `compradores_funcionais` | `COMPRADORES_FUNCIONAIS(BASE_COMPRAS).csv` | `usuario_oracle` | **Crítica**: Alimenta a regra de Centralização (`area = 'Compras'`) e expurga compras desses usuários da exceção 'Descentralizadas > R$ 30K'. |

---

### 2.9 Exemplos de Perguntas que o App Responde

| Pergunta | Módulo | Onde encontrar |
| --- | --- | --- |
| "Quanto gastamos em 2026 vs. 2025?" | Performance | KPI Net Spend + gráfico YoY |
| "Quais os top 10 fornecedores por gasto?" | Gastos | Card "Top Fornecedores" |
| "Quantas OCs estão atrasadas hoje?" | Ordens | KPI "OCs Atrasadas" + tabela |
| "Qual o prazo médio de pagamento de DIRETOS?" | Comercial | KPI prazo ponderado (filtrar Grupo = DIRETOS) |
| "Quanto temos de OC pós-fatura este ano?" | Governança | Exceção "OC Pós-Fatura" |

---

## 3. Arquitetura

O fluxo de dados segue **3 camadas**:

| Etapa | Origem | Destino | Mecanismo |
| --- | --- | --- | --- |
| **Extração** | Oracle Cloud (`cat_ocloud_r5_dv.rg5glofsn_cz`) | Spark temp views | SQL via notebook ETL |
| **Lookups** | CSVs no workspace (`compras_360/`) | Spark temp views + Lakebase staging | Pandas + psycopg2 COPY |
| **Carga** | Spark temp views | Lakebase PostgreSQL (schema `compras`) | COPY via psycopg2, blue-green swap |
| **Consumo** | Lakebase PostgreSQL | Flask API → Frontend HTML/JS | psycopg2 + REST endpoints |

**Diagrama simplificado:**

```
Oracle Cloud (cat_ocloud_r5_dv)
        │
        ▼
   SQL Views (vw_notas_ri, vw_ordens_compra, vw_requisicoes)
   + CSVs de lookup (fornecedores, compradores)
        │
        ▼
   Lakebase PostgreSQL ──► schema "compras_staging" (blue-green)
        │                            │
        │                   validação + swap atômico
        ▼                            │
   schema "compras" ◄────────────────┘
        │
        ▼
   Flask API (app.py) ──► Frontend HTML/JS (6 módulos)
```

**Componentes-chave:**
* **Lakebase PostgreSQL**: Host `ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net`, database `databricks_postgres`
* **Projeto Lakebase**: `compras-360`, branch `production`
* **ETL Notebook**: `/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/compras_360_lakebase_etl`
* **Job de atualização**: `ETL Compras 360 - Lakebase Daily` (Job ID `357960921780603`) — roda **diariamente às 06:00** (America/Sao_Paulo), duração média ∼6 min, notificação em falha para renan.ferreira@grupobimbo.com
* **App source**: `/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/app/`
* **SQL views**: `/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/sql/`

---

## 4. Modelo de Dados

Todas as tabelas residem no schema `compras` do Lakebase PostgreSQL.

### 4.1 Tabelas Principais

| Tabela | Registros (aprox.) | Descrição | Colunas-chave |
| --- | --- | --- | --- |
| `notas_ri` | ~400.000 | Notas fiscais de recebimento (RI) | `numero_ri`, `nota_fiscal`, `numero_oc`, `empresa`, `valor_liquido_brl`, `saving_total`, `data_lancamento`, `data_vencimento`, `data_pagamento`, `grupo_compras`, `centralizado`, `nome_fornecedor`, `planta` |
| `ordens_compra` | ~260.000 | Ordens de compra (linhas) | `numero_oc`, `numero_acordo`, `chave_oc_linha`, `data_oc`, `status_aprovacao`, `status_fechamento`, `valor_original_brl`, `nome_fornecedor`, `grupo_compras_oc`, `centralizado` |
| `requisicoes` | ~90.000 | Requisições de compra | `requisicao`, `numero_oc`, `dt_criacao`, `dt_aprovacao`, `valor_requisicao`, `status`, `status_ordem`, `requisitante` |

### 4.2 Tabelas de Lookup

| Tabela | Registros (aprox.) | Descrição | Fonte |
| --- | --- | --- | --- |
| `fornecedores_especiais` | ~54 | Fornecedores marcados como especiais | CSV no workspace |
| `fornecedores_nao_negociaveis` | ~349 | Fornecedores não negociáveis | CSV no workspace |
| `compradores_funcionais` | ~690 | Mapeamento comprador → área/unidade | CSV no workspace |

### 4.3 Joins Principais

* `notas_ri` ↔ `ordens_compra` via `CHAVE_OC_LINHA` (composta: `NUMERO_OC_LINHA_OC`)
* `requisicoes` ↔ `ordens_compra` via `NUMERO_OC` ou `REQUISICAO`
* `ordens_compra` ↔ `compradores_funcionais` via `usuario` = `usuario_oracle`

---

## 5. Regras de Negócio

### 5.1 Classificação de Centralização

Determina se a compra foi centralizada (via área de Compras) ou descentralizada (pelas unidades).

| Condição | Resultado |
| --- | --- |
| OC tipo BLANKET | CENTRALIZADO |
| OC tipo STANDARD com valor de linha >= R$ 30.000 | CENTRALIZADO |
| OC com acordo (BPA) referenciado | CENTRALIZADO |
| Comprador pertence à área "Compras" (`compradores_funcionais.area = 'Compras'` — match exato) | CENTRALIZADO |
| Nenhuma das anteriores | DESCENTRALIZADO |

> **Exemplo**: Uma OC STANDARD de R$ 12.000 criada por um comprador da área "Compras" é classificada como CENTRALIZADO, mesmo estando abaixo de R$ 30K — porque o comprador pertence à área funcional.
>
> ⚠️ **Atenção**: o código atual usa igualdade exata (`= 'Compras'`), não `LIKE '%Compras%'`. Hoje só existe o valor `'Compras'` (93 compradores), então o resultado é o mesmo. Mas se novos valores contendo "Compras" forem cadastrados (ex: "Compras Indiretos"), não serão capturados. Avaliar se convém alterar para `LIKE` no `app.py` (subquery `_EXCL_COMPRAS_OCS`, linha ~331).

### 5.2 Grupo de Compras

Classificação baseada no código do item:

| Condição | Grupo |
| --- | --- |
| Item começa com "A" ou "B" | DIRETOS |
| Sem item + criado por BBAPPA0001 | COMERCIAL |
| Sem item (demais) | INDIRETOS |

> **Exemplo**: Item "A907386 - SAL SEM IODO" → DIRETOS.

### 5.3 Empresa

| Código BU Oracle | Empresa |
| --- | --- |
| 300000002033035 | BB (Bimbo Brasil) |
| 300000002033048 | BQ (Bimbo QSR) |

### 5.4 Cálculo de Savings

* **Saving unitário** = preço anterior − preço atual da NF
* **Saving %** = (saving unitário / preço anterior) × 100
* Filtro de sanidade: só considera `SAVING_PCT BETWEEN 0 AND 100`
* **Saving total** = `VALOR_LIQUIDO_BRL × SAVING_PCT / 100`

> **Exemplo**: Preço anterior R$ 10,00, preço NF R$ 8,50 → Saving % = 15%.

### 5.5 Prazo de Pagamento Ponderado

```
Prazo médio = SUM(PGTO_X_VALOR) / SUM(VALOR_LIQUIDO_BRL)
```

Onde `PGTO_X_VALOR` = prazo × valor líquido BRL (já pré-calculado no ETL).

### 5.6 Governança — Exclusão de Compradores Funcionais

OCs criadas por compradores da área "Compras" (tabela `compradores_funcionais`) são **excluídas** da contagem de "OC Descentralizada > R$ 30K". Motivo: mesmo que a flag CENTRALIZADO esteja incorreta no ETL, esses compradores pertencem à área funcional de Compras.

### 5.7 Comparação YoY nos KPIs

* **Ano + Mês selecionado**: compara com o mês anterior, limitado ao mesmo dia do mês (se mês corrente)
* **Só ano selecionado**: compara o ano atual até hoje vs. ano anterior até a mesma data

> **Exemplo**: Se hoje é 21/ago/2026, o KPI de 2026 mostra jan-ago (até dia 21) vs. jan-ago 2025 (até dia 21).

### 5.8 Lead Time (3 etapas)

| Etapa | De → Para |
| --- | --- |
| 1. Requisição → Pedido | `requisicoes.DT_APROVACAO` → `ordens_compra.DATA_OC` |
| 2. Pedido → Aprovação | `ordens_compra.DATA_OC` → `ordens_compra.DT_APROVACAO` |
| 3. Aprovação → NF | `ordens_compra.DT_APROVACAO` → `notas_ri.DATA_LANCAMENTO` |

### 5.9 Exclusão de Despesas/Reembolsos/Adiantamentos de Colaboradores (Oracle Expenses) e Folha (FOPAG)

Faturas de despesas, reembolsos e adiantamentos de viagens de funcionários geradas automaticamente pelo módulo **Oracle Expenses (EXM / RDV)** e faturas de folha de pagamento são **excluídas na raiz** da base de compras (`vw_notas_ri.sql`, ETL Databricks `compras_360_lakebase_etl.py` e backend `app.py`).

* **Padrões de Nomenclatura Identificados**:
  * **`RGB...`** (ex: `RGBRBBR0007...`, `RGBRQSR...`): Relatórios de Despesas de Viagem (RDV / Expense Reports diretos).
  * **`ADVRGB...` / `ADV...`** (ex: `ADVRGBRBBR0008...`, `ADVRGBRQSR0006...`): Adiantamentos de Viagem a Colaboradores (Cash Advances).
* **Critério de Exclusão Unificado**:
  * `UPPER(NOTA_FISCAL) NOT LIKE '%RGB%'` (cobre `RGB%`, `ADVRGB%`, `RGBRQSR%`, etc.).
  * `UPPER(NOTA_FISCAL) NOT LIKE 'ADV%'` (cobre qualquer adiantamento de colaboradores).
  * `UPPER(NOTA_FISCAL) NOT LIKE '%FOPAG%'` (faturas de folha de pagamento).
* **Motivo**: Adiantamentos de viagens e reembolsos operacionais (refeições, diárias, milhagem/combustível, pedágios, custos de viagens internacionais/nacionais) são desembolsos a pessoas físicas/colaboradores sem fornecedor comercial e sem Ordem de Compra. Mantê-las na base distorce o Spend Líquido, inflaciona "Notas sem OC" e gera falso volume "Descentralizado".

---

## 6. Limitações Conhecidas

* **Sem dados em tempo real**: o ETL roda sob demanda (executar como Job diário); dados refletem a última execução.
* **Grupo COMERCIAL excluído dos filtros**: o dropdown de grupo de compras não mostra "COMERCIAL" — essas notas são sempre excluídas das análises.
* **Datas armazenadas como TEXT**: por virem do Oracle Cloud, as datas são strings `'YYYY-MM-DD'`. Funções de data usam cast explícito.
* **Savings negativos ignorados**: savings com percentual fora de 0-100% são descartados (possíveis erros de cadastro).
* **Fornecedores especiais/não negociáveis**: mantidos manualmente em CSVs — não vêm do Oracle.
* **Notas "sem OC"**: identificadas por `numero_oc = 'Nota sem OC'` — não possuem dados de OC associados.
* **Sem controle de acesso por perfil**: qualquer usuário com acesso ao app vê todos os dados (BB e BQ).

---

## 7. Governança e Segurança

### 7.1 Acesso ao App

| Componente | Quem tem acesso | Tipo |
| --- | --- | --- |
| App compras-360 (URL) | Configurado via permissões do Databricks Apps | OAuth via Databricks |
| Lakebase PostgreSQL | Service Principal `872976ee-3cee-44ca-b379-b95ca3c728e0` | Token OAuth renovado a cada 45 min |
| ETL Notebook | Usuários com acesso a `/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/` | Workspace permissions |
| Oracle Cloud (fonte) | Catálogo `cat_ocloud_r5_dv` | Unity Catalog ACL |

### 7.2 Service Principal

* **Nome**: `app-4q6vld compras-360`
* **Client ID**: `872976ee-3cee-44ca-b379-b95ca3c728e0`
* **SP ID**: `141828335256181`
* Grants re-aplicados automaticamente no ETL (após swap blue-green)

---

## 8. Runbook

### 8.1 Dados desatualizados

O job **ETL Compras 360 - Lakebase Daily** (ID `357960921780603`) roda automaticamente às 06:00 (Brasília). Se os dados parecem antigos:

1. Verificar no Jobs se a última execução foi bem-sucedida
2. Se falhou: abrir o notebook `compras_360_lakebase_etl` e executar manualmente
3. Verificar no output: "ETL COMPLETO — App compras-360 atualizado!"
4. Se falhar na validação (tabela vazia): verificar acesso ao catálogo `cat_ocloud_r5_dv`

### 8.2 App não abre / erro 5xx

1. No workspace, ir em Apps → compras-360 → verificar status
2. Se STOPPED: clicar Start (ou CLI: `databricks apps start compras-360`)
3. Se RUNNING mas com erro: verificar logs do app (`Apps > Logs`)
4. Erro comum: "Token refresh failed" → Service Principal sem grant no Lakebase; re-executar célula 6 do ETL

### 8.3 Dados parecem errados

1. Conectar no Lakebase e validar contagens:
   ```sql
   SELECT COUNT(*) FROM compras.notas_ri;
   SELECT COUNT(*) FROM compras.ordens_compra;
   SELECT COUNT(*) FROM compras.requisicoes;
   ```
2. Comparar com output da última execução do ETL (~400K, ~260K, ~90K)
3. Se discrepante: re-executar o ETL

### 8.4 Novo fornecedor especial / não negociável

1. Editar o CSV correspondente em `/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/`:
   * `fornecedores_especiais.csv`
   * `fornecedores_nao_negociaiveis.csv`
2. Re-executar o ETL para propagar ao Lakebase

### 8.5 Novo comprador funcional

1. Editar `COMPRADORES_FUNCIONAIS(BASE_COMPRAS).csv` na mesma pasta
2. Re-executar o ETL

### 8.6 Deploy de nova versão do app

1. Editar os arquivos em `/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/app/`
2. No CLI: `databricks apps deploy compras-360 --source-code-path /Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/app`
3. Acompanhar status: `databricks apps get compras-360`
