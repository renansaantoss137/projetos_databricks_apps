# Referência de API

**Projeto:** Cockpit Logístico OTIF & Fill Rate — Bimbo QSR Brasil  
**Base URL:** `https://bq-oitf-fillrate-dev-8674310331778219.19.azure.databricksapps.com`  
**Última atualização:** 2026-07-16

---

## Filtros Comuns

A maioria dos endpoints aceita os seguintes parâmetros de query string:

| Parâmetro | Tipo | Descrição | Exemplo |
|-----------|------|----------|--------|
| `dt_ini` | string (YYYY-MM-DD) | Data inicial | `2026-06-01` |
| `dt_fim` | string (YYYY-MM-DD) | Data final | `2026-06-30` |
| `ano` | multi-value | Ano(s) | `ano=2026` |
| `mes` | multi-value | Mês(es) | `mes=6&mes=7` |
| `dia` | multi-value | Dia(s) do mês | `dia=15` |
| `semana` | multi-value | Semana (seg\|dom) | `semana=2026-07-07\|2026-07-13` |
| `planta` | multi-value | Planta(s) | `planta=JAG&planta=OSA` |
| `grupo_cliente` | multi-value | Grupo(s) cliente | `grupo_cliente=123-BOB` |
| `canal` | multi-value | Canal | `canal=QSR` |
| `responsavel` | multi-value | Responsável N1 | `responsavel=João` |
| `status` | multi-value | Status pedido | `status=1&status=2` |
| `busca` | string | Busca livre | `busca=12345` |

**Regra de data padrão:** Se nenhum filtro de data for informado, assume últimos 90 dias.

---

## Endpoints

### Diagnóstico

#### `GET /api/diag`

Health check e diagnóstico de conexão.

**Resposta:** Drivers disponíveis, fonte de credenciais, status da conexão, versão do SQL Server.

---

### Gestão de Pedidos

#### `GET /api/pedidos`

Lista paginada de pedidos com filtros.

| Parâmetro Extra | Tipo | Descrição |
|----------------|------|----------|
| `page` | int | Página (default: 1) |
| `page_size` | int | Itens por página (1-500, default: 50) |
| `sort_field` | string | Coluna para ordenação |
| `sort_dir` | string | `asc` ou `desc` |
| `cf_EMPRESA[]` | multi-value | Filtro por coluna (tipo Excel) |
| `cf_STATUS_PEDIDO[]` | multi-value | Filtro por coluna |

**Resposta:** `{ rows, total, page, page_size, total_pages }`

#### `GET /api/pedidos/distinct`

Valores distintos de uma coluna (para filtros tipo Excel).

| Parâmetro | Descrição |
|-----------|----------|
| `column` | Coluna: `EMPRESA`, `STATUS_PEDIDO`, `GRUPO_CLI`, `CNPJ_CLIENTE` |

#### `GET /api/pedidos/resumo`

Totais agregados para KPI cards (pedidos vencidos vs dentro do prazo).

**Resposta:** Total pedidos, cancelados, quantidades, valores, fill rate, corte.

---

### Fill Rate

#### `GET /api/fillrate/mensal`

Quantidades agregadas por mês (apenas pedidos vencidos).

**Resposta:** Array de `{ ANO, MES, QTDE_PEDIDA, QTDE_ATENDIDA, QTDE_CANCELADA }`

#### `GET /api/fillrate/semanal`

Quantidades agregadas por semana (segunda a domingo).

**Resposta:** Array de `{ DT_SEGUNDA, SEMANA_NUM, QTDE_PEDIDA, QTDE_ATENDIDA, QTDE_CANCELADA }`

---

### OTIF (Módulo Legado — base Mercanet)

#### `GET /api/otif/resumo`

Resumo OTIF baseado na lógica Mercanet (status 1/2).

**Resposta:** `{ QTDE_PEDIDA, QTDE_ATENDIDA, QTDE_CANCELADA, TOTAL_PEDIDOS, OTIF_AVALIADOS, ON_TIME, IN_FULL, OTIF }`

---

### OTIF v2 (Módulo OTM — base `base_otm_otif_bq`)

#### `GET /api/otif2/resumo`

Resumo geral OTIF com separação CIF/FOB.

**Parâmetros adicionais:**

| Parâmetro | Descrição |
|-----------|----------|
| `tipo_frete` | Filtrar por CIF ou FOB |
| `cliente` | Nome do cliente |
| `pedido` | Nº do pedido |
| `remessa` | Nº da remessa |
| `transportadora` | Nome da transportadora |

**Resposta:** `{ TOTAL_LINHAS, FOB_LINHAS, CIF_LINHAS, OTIF_FOB, OT_FOB, OT_CIF, OTIF_CIF, INFULL_FOB, INFULL_CIF, AVG_ATRASO_FOB, AVG_ATRASO_CIF }`

#### `GET /api/otif2/por-planta`

OTIF desagregado por planta.

#### `GET /api/otif2/por-cliente`

OTIF desagregado por grupo de cliente ou cliente individual.

| Parâmetro | Descrição |
|-----------|----------|
| `mode` | `grupo` (default) ou `cliente` |

#### `GET /api/otif2/por-semana`

Evolução semanal do OTIF.

#### `GET /api/otif2/detalhe`

Tabela detalhada (paginada) de cada remessa avaliada.

| Parâmetro | Descrição |
|-----------|----------|
| `page` | Página (default: 1) |
| `page_size` | Itens (default: 50, max: 200) |

#### `GET /api/otif2/plantas`

Lista de plantas disponíveis para filtro.

#### `GET /api/otif2/clientes`

Lista de clientes disponíveis (aceita `grupo_cliente` para filtrar).

#### `GET /api/otif2/grupos-cliente`

Lista de grupos de cliente disponíveis.

#### `GET /api/otif2/canais`

Lista de canais disponíveis.

#### `GET /api/otif2/pedidos`

Lista de números de pedido disponíveis.

#### `GET /api/otif2/remessas`

Lista de remessas disponíveis.

---

### Painel Executivo

#### `GET /api/executivo/resumo`

KPIs consolidados do período (Fill Rate + OTIF).

**Resposta:** `{ QTDE_PEDIDA, QTDE_ATENDIDA, QTDE_CANCELADA, TOTAL_PEDIDOS, OTIF_AVALIADOS, ON_TIME, IN_FULL, OTIF }`

#### `GET /api/executivo/scorecard`

Fill Rate + OTIF desagregado por planta para o período selecionado.

#### `GET /api/executivo/evolucao`

Evolução mensal de Fill Rate e OTIF (janela de 12+ meses).

**Resposta:** Array de `{ ANO, MES, QTDE_PED, QTDE_ATD, QTDE_CAN, AVALIADOS, ON_TIME, IN_FULL, OTIF_OK }`

#### `GET /api/executivo/diagnostico/pareto`

Pareto de perdas por dimensão.

| Parâmetro | Valores | Descrição |
|-----------|---------|----------|
| `kpi` | `fillrate`, `otif` | KPI a analisar |
| `dimension` | `planta`, `grupo_cliente` | Dimensão do Pareto |
| `otif_view` | `geral`, `cif`, `fob` | Visão (só para kpi=otif) |

**Resposta:** Array rankeado com `{ dimension_name, kpi_value, target, gap_vs_target, loss_value, impact_pp, loss_share_pct, cumulative_loss_pct, rank }`

#### `GET /api/executivo/diagnostico/acao-prioritaria`

Maior ofensor entre todas as combinações de KPI × dimensão × visão.

**Resposta:** Objeto com o ofensor de maior impacto.

#### `GET /api/executivo/diagnostico/prioridades`

Tabela de prioridades de ação consolidada (top N).

| Parâmetro | Descrição |
|-----------|----------|
| `limit` | Máximo de linhas (5-10, default: 8) |

**Resposta:** Array de `{ planta, grupo_cliente, indicador, valor_atual, impact_pp, loss_value, acao_sugerida }`

#### `GET /api/executivo/insights`

Leitura executiva textual (determinística, baseada nos dados).

**Resposta:** `{ text, cached }`

---

### Páginas Estáticas (Frontend)

| Rota | Arquivo |
|------|--------|
| `/` | `index.html` |
| `/painel-executivo.html` | Painel Executivo |
| `/fillrate.html` | Fill Rate |
| `/fillrate-detalhe.html` | Fill Rate Detalhe |
| `/otif.html` | OTIF |
| `/otif-detalhe.html` | OTIF Detalhe |
| `/gestao-pedidos.html` | Gestão de Pedidos |

---

## Códigos de Erro

| Código | Descrição |
|--------|----------|
| 200 | Sucesso |
| 400 | Parâmetro inválido (ex: kpi ou dimension inválido) |
| 500 | Erro de conexão ou SQL (retorna `{ error: "mensagem" }`) |
