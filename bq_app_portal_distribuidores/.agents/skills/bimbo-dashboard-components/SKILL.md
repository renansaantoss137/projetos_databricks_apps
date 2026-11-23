---
name: bimbo-dashboard-components
description: Use when creating, modifying or debugging the functional behavior of dashboard components in Grupo Bimbo D&A Flask + vanilla JS Databricks Apps - global and page filters (searchable multi-select, select all, clear, chips, persistence, cross-page sync), Excel-like table column filters, sorting, resizing, pagination, exports (CSV/XLSX), KPI cards, Chart.js narrative charts, and loading/empty/error/stale states, including filters that do not update KPIs, stale data after filter changes and out-of-order (race) responses. Gives interface contracts, verified Compras 360 reference implementations with known defects, and acceptance criteria. Visual identity stays in frontend-apps; tests in bimbo-app-qa.
metadata:
  version: "0.1.0"
  owner: "renan.ferreira@grupobimbo.com"
  team: "D&A Brasil"
  status: "beta"
  reference_app: "compras-360-dev deployment 01f1d4684b7b11549f96c0b18e077e4c"
---

# Componentes funcionais de dashboard

Contratos de comportamento. Aparência: `frontend-apps` (identidade-da.md, dashboards-swd.md, filtros-referencia.html). Testes: `bimbo-app-qa`.
Antes de criar um componente, procure o equivalente no app atual e na referência (`references/compras360-audit.md`). Reutilize; não duplique.

## 1. Filtros

Contrato mínimo de um filtro (referência: `MultiSelect` em `filters-shared.js`):

| Membro | Significado |
|---|---|
| `key` | nome do parâmetro enviado ao backend (fonte de verdade da semântica) |
| `options` | valores válidos vindos da API de lookups |
| `selected: Set` | seleção atual |
| `getSelected()` | valores enviados; "todos" pode ser omitido só se o backend tratar ausência = todos (documente) |
| `renderOptions()`, `updateLabel()` | redesenho e rótulo/chip |

Regras:
- **Semântica antes de sincronizar.** Sincronize entre páginas só filtros com o mesmo `key` *e* o mesmo significado/granularidade. Dimensões parecidas com significados diferentes (ex.: data de emissão x data de aprovação) recebem `key` distintos.
- **Persistência** em `localStorage` por `key`; preserve chaves de outras páginas ao salvar; descarte valores que não existem mais em `options`; `__ALL__` para "todos" (referência `FilterStateStore`).
- **Defaults documentados** (ex.: ano corrente, mês corrente, flags de negócio) em um único lugar e usados por "Limpar" e pelo prewarm do backend.
- **Controle pelo tipo de dado**: multi-seleção para categorias; período/intervalo para datas e números; ano/mês ordenados cronologicamente, não alfabeticamente.
- **Busca** dentro do dropdown, "Selecionar todos" respeitando o resultado da busca, "Limpar", contador "(n)" e chips removíveis.
- **Aplicar** dispara a carga via guard de requisição (seção 4). Sem guard = defeito CRITICAL potencial.
- **Sem resultado**: mensagem "Nenhum registro para os filtros" + ação "Limpar filtros"; nunca KPI 0 sem explicação.
- **Acessibilidade**: botão com `aria-expanded`, lista com `role=listbox`/`option` ou checkboxes nativos, Esc fecha e devolve foco, alvo ≥ 44px no toque.

## 2. Tabelas

- Filtro de coluna por tipo (referência `TableColumnFilter`): texto (contém, igual, diferente, começa, termina, não contém), número/data (>, <, ≥, ≤, entre). Mostre só operadores do tipo da coluna (a referência mostra todos: melhoria pendente).
- Ordenação tipada (número como número, data como data, `localeCompare('pt-BR')` para texto); indicador `aria-sort`.
- Redimensionar coluna: coordenadas divididas pela escala ativa quando houver zoom (`window.dnaScale()`), largura mínima, persistência opcional.
- Altura de linha uniforme; texto longo com `text-overflow: ellipsis` + `title`/tooltip acessível; padrão de referência: tabela "Exceções que Requerem Ação" (Governança).
- Paginação: total vindo do servidor; para > ~10 mil linhas ou payload > ~2 MB medido, use paginação e exportação no servidor.
- Rolagem horizontal localizada no wrapper da tabela; nunca `overflow-x:hidden` na página.

## 3. Exportação

- Escopo = filtros globais + filtros de coluna + colunas selecionadas, na ordem exibida.
- Grande volume: endpoint servidor (referência `/api/reports/export`) em vez de montar no navegador.
- CSV para Excel pt-BR: UTF-8 com BOM, separador `;`, decimal `,`; XLSX com números como número e datas como data. Biblioteca por CDN com versão fixa.
- Mostrar progresso e erro; nunca baixar arquivo vazio silenciosamente.

## 4. Carga, erro e dado obsoleto

- Um guard por bloco: `references/request-guard.js` (AbortController + sequência + HttpError).
- Estados por bloco: `loading` (esmaecido, sem apagar o valor anterior **com** indicação de atualização), `ready`, `empty`, `error` ("—" + mensagem + Tentar novamente), `stale` (se exibir dado antigo, rotule "desatualizado").
- Retry só para GET idempotente e 502/503/504 (referência `analytics-ui.js`); 500 é erro real.
- Backend: falha de consulta deve virar HTTP 5xx ou `{error: ...}`, nunca `[]`/0 com 200.
- Failsafe de UI (ex.: remover esmaecimento após N s) não substitui o estado de erro.

## 5. KPI cards

- Estrutura: rótulo + ícone (cabeçalho), valor, comparação com base explícita (vs ano anterior / mês anterior / meta), botão de ajuda acessível (`aria-label="Como é calculado: ..."`) com a definição.
- `%` para variação relativa e `p.p.` para diferença de percentuais; sinal + seta + texto, nunca só cor.
- Formatação com `Intl.NumberFormat('pt-BR')` (referência `fmtNum`/`fmtPct` em `i18n.js`); ausência ou denominador 0 = "—".
- Período parcial: rotule "parcial" ou compare com o mesmo período (referência: "vs mesmo período ano anterior").

## 6. Gráficos narrativos (Chart.js 4)

- Título-conclusão calculado dos mesmos dados do gráfico, com a mesma regra do KPI. Referências verificadas em `performance.html`:
  - `Em ${ano}, Spend Líquido em ${fmt(total)} (${sinal}${pct}% ${direção} vs ano anterior)`
  - `Em ${ano}, Centralização em ${pct} (${sinal}${pp} pp ${direção} vs ano anterior)` (meta de referência 80%)
  - `O maior tempo do processo está entre {leg}.` com `leg` vindo da API (`longest_leg`)
- O texto inicial no HTML é placeholder e precisa ser substituído ou ocultado se a API falhar (não deixar conclusão fixa).
- Ano atual em cor de destaque, ano anterior em neutro, meta como linha/traço; barras com base zero; `maintainAspectRatio:false` com altura no container; alternativa em tabela; recriar gráfico ao trocar tema.

## 7. Navegação e escala

- Menu lateral recolhível com estado persistido (referência `navigation.js`, chave `compras_nav_expanded`); navegação interna na mesma aba.
- Celular: barra inferior com até 4 destinos + "Mais" construída a partir do menu lateral (referência `mobile-nav.js`).
- Popovers e menus: posicione pelo espaço disponível no viewport (acima/abaixo, esquerda/direita) e limite altura com rolagem interna.
- Zoom de corpo (`view-scale.js`) é **opcional** e só em desktop com ponteiro fino; o padrão é layout responsivo nativo. Se usar zoom: corrija coordenadas de popover/resize, desative dentro de iframes e ofereça seletor manual.

## Critérios de aceite

- Filtro: parâmetro chega ao SQL; troca rápida exibe a última seleção; persistência volta igual; Limpar = defaults documentados.
- Tabela/exportação: contagem e totais iguais entre tela, API e arquivo.
- KPI/gráfico: valor = API dentro da tolerância de exibição; título coerente com os dados; erro mostra "—".
- Todos verificados com `bimbo-app-qa` em 390 e 1440 px.
