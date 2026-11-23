# Inventário de controles (largura 390px)

## http://127.0.0.1:8002/performance.html

35 controles visíveis (100 ocultos) · 11 com problema

| # | Tipo | Nome | Seletor | Estado | Tamanho | Problemas |
|---|---|---|---|---|---|---|
| 1 | button | Filtros: 4 ativos | `#fpAbrirGaveta` | — | 84×44 | — |
| 2 | button | Remover filtro Ano | `#fpChips > span:nth-of-type(1) > button` | — | 32×32 | alvo 32x32 < 44px |
| 3 | button | Remover filtro Mês | `#fpChips > span:nth-of-type(2) > button` | — | 32×32 | alvo 32x32 < 44px |
| 4 | button | Remover filtro Negociável | `#fpChips > span:nth-of-type(3) > button` | — | 32×32 | alvo 32x32 < 44px |
| 5 | button | Remover filtro Forn. sem OC | `#fpChips > span:nth-of-type(4) > button` | — | 32×32 | alvo 32x32 < 44px |
| 6 | button | Limpar tudo | `#fpLimparTudo` | — | 115×44 | — |
| 7 | button | Recolher filtros aplicados | `div > header > div:nth-of-type(3) > button` | expandido=true | 44×44 | — |
| 8 | button | Menu do usuário | `#daAppMenuTrigger` | expandido=false | 64×44 | — |
| 9 | a | Início | `div:nth-of-type(2) > div > nav > a:nth-of-type(1)` | → index.html | 76×48 | — |
| 10 | a | Performance | `div:nth-of-type(2) > div > nav > a:nth-of-type(2)` | → performance.html | 76×48 | — |
| 11 | a | Ordens | `div:nth-of-type(2) > div > nav > a:nth-of-type(3)` | → ordens.html | 76×48 | — |
| 12 | a | Comercial | `div:nth-of-type(2) > div > nav > a:nth-of-type(4)` | → comercial.html | 76×48 | — |
| 13 | button | Mais | `#dnaMoreBtn` | expandido=false | 76×48 | — |
| 14 | button[role=tab] | Spend Líquido | `#btnYoYSpend` | — | 105×36 | alvo 105x36 < 44px |
| 15 | button[role=tab] | % Centralização | `#btnYoYCentral` | — | 117×36 | alvo 117x36 < 44px |
| 16 | summary | Ver dados em tabela | `#cardSpendYoY > details > summary` | — | 344×28 | alvo 344x28 < 44px |
| 17 | button | Diretos | `#funnelScopePills > button:nth-of-type(1)` | — | 63×36 | alvo 63x36 < 44px |
| 18 | button | Indiretos | `#funnelScopePills > button:nth-of-type(2)` | — | 73×36 | alvo 73x36 < 44px |
| 19 | tr | Requisições aguardando OC há mais de 5 dias 18 2.0% R$ 1,2 Mi <0.1% | `#attentionList > table > tbody > tr:nth-of-type(1)` | — | 336×173 | — |
| 20 | tr | OCs aprovadas após fatura 34 3.8% R$ 8,5 Mi 0.3% | `#attentionList > table > tbody > tr:nth-of-type(2)` | — | 336×173 | — |
| 21 | tr | OCs descentralizadas acima de R$30.000 15 1.7% R$ 1,9 Mi <0.1% | `#attentionList > table > tbody > tr:nth-of-type(3)` | — | 336×173 | — |
| 22 | tr | OCs abertas há mais de 90 dias 11 1.2% R$ 950,0 mil <0.1% | `#attentionList > table > tbody > tr:nth-of-type(4)` | — | 336×173 | — |
| 23 | tr | Acordos de Compra abertos há mais de 180 dias 7 0.8% R$ 700,0 mil <0.1% | `#attentionList > table > tbody > tr:nth-of-type(5)` | — | 336×191 | — |
| 24 | tr | Notas sem OCs 22 2.4% R$ 2,7 Mi <0.1% | `#attentionList > table > tbody > tr:nth-of-type(6)` | — | 336×173 | — |
| 25 | button | Tabela | `#btnViewTable` | — | 77×36 | alvo 77x36 < 44px |
| 26 | button | Gráfico | `#btnViewChart` | — | 81×36 | alvo 81x36 < 44px |
| 27 | button | XLSX | `#btnExportAlerts` | — | 73×44 | — |
| 28 | button | Ver mais (5) | `#paBody > tr:nth-of-type(1) > td:nth-of-type(12) > button` | — | 102×44 | — |
| 29 | button | Ver mais (5) | `#paBody > tr:nth-of-type(2) > td:nth-of-type(12) > button` | — | 102×44 | — |
| 30 | button | Ver mais (5) | `#paBody > tr:nth-of-type(3) > td:nth-of-type(12) > button` | — | 102×44 | — |
| 31 | button | Ver mais (5) | `#paBody > tr:nth-of-type(4) > td:nth-of-type(12) > button` | — | 102×44 | — |
| 32 | button | Ver mais (5) | `#paBody > tr:nth-of-type(5) > td:nth-of-type(12) > button` | — | 102×44 | — |
| 33 | button | Ver mais (5) | `#paBody > tr:nth-of-type(6) > td:nth-of-type(12) > button` | — | 102×44 | — |
| 34 | button | Ver mais (5) | `#paBody > tr:nth-of-type(7) > td:nth-of-type(12) > button` | — | 102×44 | — |
| 35 | button | Ver mais (5) | `#paBody > tr:nth-of-type(8) > td:nth-of-type(12) > button` | — | 102×44 | — |

## http://127.0.0.1:8002/ordens.html

17 controles visíveis (70 ocultos) · 4 com problema

| # | Tipo | Nome | Seletor | Estado | Tamanho | Problemas |
|---|---|---|---|---|---|---|
| 1 | button | Filtros: 4 ativos | `#fpAbrirGaveta` | — | 84×44 | — |
| 2 | button | Remover filtro Ano | `#fpChips > span:nth-of-type(1) > button` | — | 32×32 | alvo 32x32 < 44px |
| 3 | button | Remover filtro Mês | `#fpChips > span:nth-of-type(2) > button` | — | 32×32 | alvo 32x32 < 44px |
| 4 | button | Remover filtro Negociável | `#fpChips > span:nth-of-type(3) > button` | — | 32×32 | alvo 32x32 < 44px |
| 5 | button | Remover filtro Forn. sem OC | `#fpChips > span:nth-of-type(4) > button` | — | 32×32 | alvo 32x32 < 44px |
| 6 | button | Limpar tudo | `#fpLimparTudo` | — | 115×44 | — |
| 7 | button | Recolher filtros aplicados | `div > header > div:nth-of-type(3) > button` | expandido=true | 44×44 | — |
| 8 | button | Menu do usuário | `#daAppMenuTrigger` | expandido=false | 64×44 | — |
| 9 | a | Início | `div:nth-of-type(2) > div > nav > a:nth-of-type(1)` | → index.html | 76×48 | — |
| 10 | a | Performance | `div:nth-of-type(2) > div > nav > a:nth-of-type(2)` | → performance.html | 76×48 | — |
| 11 | a | Ordens | `div:nth-of-type(2) > div > nav > a:nth-of-type(3)` | → ordens.html | 76×48 | — |
| 12 | a | Comercial | `div:nth-of-type(2) > div > nav > a:nth-of-type(4)` | → comercial.html | 76×48 | — |
| 13 | button | Mais | `#dnaMoreBtn` | expandido=false | 76×48 | — |
| 14 | summary | Ver dados em tabela | `div:nth-of-type(3) > div:nth-of-type(1) > details > summary` | — | 344×44 | — |
| 15 | button | XLSX | `div:nth-of-type(4) > div:nth-of-type(2) > div:nth-of-type(1) > button` | — | 78×44 | — |
| 16 | button | ← Anterior | `#btnPrev` | desabilitado | 87×44 | — |
| 17 | button | Próxima → | `#btnNext` | — | 86×44 | — |

## http://127.0.0.1:8002/comercial.html

16 controles visíveis (58 ocultos) · 4 com problema

| # | Tipo | Nome | Seletor | Estado | Tamanho | Problemas |
|---|---|---|---|---|---|---|
| 1 | button | Filtros: 4 ativos | `#fpAbrirGaveta` | — | 84×44 | — |
| 2 | button | Remover filtro Ano | `#fpChips > span:nth-of-type(1) > button` | — | 32×32 | alvo 32x32 < 44px |
| 3 | button | Remover filtro Mês | `#fpChips > span:nth-of-type(2) > button` | — | 32×32 | alvo 32x32 < 44px |
| 4 | button | Remover filtro Negociável | `#fpChips > span:nth-of-type(3) > button` | — | 32×32 | alvo 32x32 < 44px |
| 5 | button | Remover filtro Forn. sem OC | `#fpChips > span:nth-of-type(4) > button` | — | 32×32 | alvo 32x32 < 44px |
| 6 | button | Limpar tudo | `#fpLimparTudo` | — | 115×44 | — |
| 7 | button | Recolher filtros aplicados | `div > header > div:nth-of-type(3) > button` | expandido=true | 44×44 | — |
| 8 | button | Menu do usuário | `#daAppMenuTrigger` | expandido=false | 64×44 | — |
| 9 | a | Início | `div:nth-of-type(2) > div > nav > a:nth-of-type(1)` | → index.html | 76×48 | — |
| 10 | a | Performance | `div:nth-of-type(2) > div > nav > a:nth-of-type(2)` | → performance.html | 76×48 | — |
| 11 | a | Ordens | `div:nth-of-type(2) > div > nav > a:nth-of-type(3)` | → ordens.html | 76×48 | — |
| 12 | a | Comercial | `div:nth-of-type(2) > div > nav > a:nth-of-type(4)` | → comercial.html | 76×48 | — |
| 13 | button | Mais | `#dnaMoreBtn` | expandido=false | 76×48 | — |
| 14 | button | XLSX | `div:nth-of-type(3) > div:nth-of-type(2) > div:nth-of-type(1) > button` | — | 78×44 | — |
| 15 | button | ← Anterior | `#renPrev` | desabilitado | 87×44 | — |
| 16 | button | Próxima → | `#renNext` | desabilitado | 86×44 | — |

## http://127.0.0.1:8002/governanca.html

37 controles visíveis (89 ocultos) · 12 com problema

| # | Tipo | Nome | Seletor | Estado | Tamanho | Problemas |
|---|---|---|---|---|---|---|
| 1 | button | Filtros: 4 ativos | `#fpAbrirGaveta` | — | 84×44 | — |
| 2 | button | Remover filtro Ano | `#fpChips > span:nth-of-type(1) > button` | — | 32×32 | alvo 32x32 < 44px |
| 3 | button | Remover filtro Mês | `#fpChips > span:nth-of-type(2) > button` | — | 32×32 | alvo 32x32 < 44px |
| 4 | button | Remover filtro Negociável | `#fpChips > span:nth-of-type(3) > button` | — | 32×32 | alvo 32x32 < 44px |
| 5 | button | Remover filtro Forn. sem OC | `#fpChips > span:nth-of-type(4) > button` | — | 32×32 | alvo 32x32 < 44px |
| 6 | button | Limpar tudo | `#fpLimparTudo` | — | 115×44 | — |
| 7 | button | Recolher filtros aplicados | `div > header > div:nth-of-type(3) > button` | expandido=true | 44×44 | — |
| 8 | button | Menu do usuário | `#daAppMenuTrigger` | expandido=false | 64×44 | — |
| 9 | a | Início | `div:nth-of-type(2) > div > nav > a:nth-of-type(1)` | → index.html | 76×48 | — |
| 10 | a | Performance | `div:nth-of-type(2) > div > nav > a:nth-of-type(2)` | → performance.html | 76×48 | — |
| 11 | a | Ordens | `div:nth-of-type(2) > div > nav > a:nth-of-type(3)` | → ordens.html | 76×48 | — |
| 12 | a | Comercial | `div:nth-of-type(2) > div > nav > a:nth-of-type(4)` | → comercial.html | 76×48 | — |
| 13 | button | Mais | `#dnaMoreBtn` | expandido=false | 76×48 | — |
| 14 | button | XLSX | `div:nth-of-type(3) > div:nth-of-type(2) > div:nth-of-type(1) > button` | — | 78×44 | — |
| 15 | button | ← Anterior | `#buyerPrev` | desabilitado | 87×44 | — |
| 16 | button | Próxima → | `#buyerNext` | — | 86×44 | — |
| 17 | button | XLSX | `div:nth-of-type(4) > div:nth-of-type(1) > div:nth-of-type(2) > button` | — | 78×44 | — |
| 18 | button | OCs Pós-Fatura | `#excSelector > button:nth-of-type(1)` | — | 59×36 | alvo 59x36 < 44px |
| 19 | button | Notas sem OCs | `#excSelector > button:nth-of-type(2)` | — | 56×36 | alvo 56x36 < 44px |
| 20 | button | OC Descentr. >30k | `#excSelector > button:nth-of-type(3)` | — | 78×36 | alvo 78x36 < 44px |
| 21 | button | OCs Sucessivas | `#excSelector > button:nth-of-type(4)` | — | 88×36 | alvo 88x36 < 44px |
| 22 | button | OC >90 dias | `#excSelector > button:nth-of-type(5)` | — | 46×36 | alvo 46x36 < 44px |
| 23 | button | Acordos de Compra >180 dias | `#excSelector > button:nth-of-type(6)` | — | 71×36 | alvo 71x36 < 44px |
| 24 | button | Emergencial | `#excSelector > button:nth-of-type(7)` | — | 94×36 | alvo 94x36 < 44px |
| 25 | button | Ver mais (8) | `#excBody > tr:nth-of-type(1) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 26 | button | Ver mais (8) | `#excBody > tr:nth-of-type(2) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 27 | button | Ver mais (8) | `#excBody > tr:nth-of-type(3) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 28 | button | Ver mais (8) | `#excBody > tr:nth-of-type(4) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 29 | button | Ver mais (8) | `#excBody > tr:nth-of-type(5) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 30 | button | Ver mais (8) | `#excBody > tr:nth-of-type(6) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 31 | button | Ver mais (8) | `#excBody > tr:nth-of-type(7) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 32 | button | Ver mais (8) | `#excBody > tr:nth-of-type(8) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 33 | button | Ver mais (8) | `#excBody > tr:nth-of-type(9) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 34 | button | Ver mais (8) | `#excBody > tr:nth-of-type(10) > td:nth-of-type(15) > button` | — | 102×44 | — |
| 35 | button | ← Anterior | `#excPrev` | desabilitado | 87×44 | — |
| 36 | span | Página 1 de 3 | `#excPageInfo` | — | 79×19 | elemento não semântico clicável; alvo 79x19 < 44px |
| 37 | button | Próxima → | `#excNext` | — | 86×44 | — |

## http://127.0.0.1:8002/relatorios.html

47 controles visíveis (133 ocultos) · 37 com problema

| # | Tipo | Nome | Seletor | Estado | Tamanho | Problemas |
|---|---|---|---|---|---|---|
| 1 | button | Filtros: 4 ativos | `#fpAbrirGaveta` | — | 84×44 | — |
| 2 | button | Remover filtro Ano | `#fpChips > span:nth-of-type(1) > button` | — | 32×32 | alvo 32x32 < 44px |
| 3 | button | Remover filtro Mês | `#fpChips > span:nth-of-type(2) > button` | — | 32×32 | alvo 32x32 < 44px |
| 4 | button | Remover filtro Negociável | `#fpChips > span:nth-of-type(3) > button` | — | 32×32 | alvo 32x32 < 44px |
| 5 | button | Remover filtro Forn. sem OC | `#fpChips > span:nth-of-type(4) > button` | — | 32×32 | alvo 32x32 < 44px |
| 6 | button | Limpar tudo | `#fpLimparTudo` | — | 115×44 | — |
| 7 | button | Recolher filtros aplicados | `div > header > div:nth-of-type(3) > button` | expandido=true | 44×44 | — |
| 8 | button | Menu do usuário | `#daAppMenuTrigger` | expandido=false | 64×44 | — |
| 9 | a | Início | `div:nth-of-type(2) > div > nav > a:nth-of-type(1)` | → index.html | 76×48 | — |
| 10 | a | Performance | `div:nth-of-type(2) > div > nav > a:nth-of-type(2)` | → performance.html | 76×48 | — |
| 11 | a | Ordens | `div:nth-of-type(2) > div > nav > a:nth-of-type(3)` | → ordens.html | 76×48 | — |
| 12 | a | Comercial | `div:nth-of-type(2) > div > nav > a:nth-of-type(4)` | → comercial.html | 76×48 | — |
| 13 | button | Mais | `#dnaMoreBtn` | expandido=false | 76×48 | — |
| 14 | button | NFs & OCs | `main > div:nth-of-type(1) > div > button:nth-of-type(1)` | — | 83×36 | alvo 83x36 < 44px |
| 15 | button | Requisições | `main > div:nth-of-type(1) > div > button:nth-of-type(2)` | — | 92×36 | alvo 92x36 < 44px |
| 16 | button | Minimizar painel | `#btnCollapsePanel` | — | 44×36 | alvo 44x36 < 44px |
| 17 | svg | Buscar | `div:nth-of-type(1) > div:nth-of-type(2) > div > svg` | — | 11×12 | elemento não semântico clicável; alvo 11x12 < 44px |
| 18 | input[text] | Busca rápida... | `#tblQuickSearch` | — | 223×18 | alvo 223x18 < 44px |
| 19 | button | CSV | `#btnExportCsv` | — | 72×44 | — |
| 20 | div | Dados do relatório; role horizontalmente para ver as demais colunas | `div:nth-of-type(2) > div > div > div:nth-of-type(3)` | — | 368×558 | elemento não semântico clicável |
| 21 | span | NOTA FISCAL | `tr > th:nth-of-type(1) > div:nth-of-type(1) > span` | — | 78×19 | elemento não semântico clicável; alvo 78x19 < 44px |
| 22 | button | Filtrar coluna Nota Fiscal | `tr > th:nth-of-type(1) > div:nth-of-type(1) > button` | — | 17×44 | alvo 17x44 < 44px |
| 23 | div | **(sem nome)** | `#reportHead > tr > th:nth-of-type(1) > div:nth-of-type(2)` | — | 8×62 | sem nome acessível; elemento não semântico clicável; alvo 8x62 < 44px |
| 24 | span | Nº OC | `tr > th:nth-of-type(2) > div:nth-of-type(1) > span` | — | 55×19 | elemento não semântico clicável; alvo 55x19 < 44px |
| 25 | button | Filtrar coluna Nº OC | `tr > th:nth-of-type(2) > div:nth-of-type(1) > button` | — | 17×44 | alvo 17x44 < 44px |
| 26 | div | **(sem nome)** | `#reportHead > tr > th:nth-of-type(2) > div:nth-of-type(2)` | — | 8×62 | sem nome acessível; elemento não semântico clicável; alvo 8x62 < 44px |
| 27 | span | FORNECEDOR | `tr > th:nth-of-type(3) > div:nth-of-type(1) > span` | — | 108×19 | elemento não semântico clicável; alvo 108x19 < 44px |
| 28 | button | Filtrar coluna Fornecedor | `tr > th:nth-of-type(3) > div:nth-of-type(1) > button` | — | 17×44 | alvo 17x44 < 44px |
| 29 | div | **(sem nome)** | `#reportHead > tr > th:nth-of-type(3) > div:nth-of-type(2)` | — | 8×62 | sem nome acessível; elemento não semântico clicável; alvo 8x62 < 44px |
| 30 | span | DS ITEM | `tr > th:nth-of-type(4) > div:nth-of-type(1) > span` | — | 88×19 | elemento não semântico clicável; alvo 88x19 < 44px |
| 31 | button | Filtrar coluna Ds Item | `tr > th:nth-of-type(4) > div:nth-of-type(1) > button` | — | 17×44 | alvo 17x44 < 44px |
| 32 | div | **(sem nome)** | `#reportHead > tr > th:nth-of-type(4) > div:nth-of-type(2)` | — | 8×62 | sem nome acessível; elemento não semântico clicável; alvo 8x62 < 44px |
| 33 | span | CATEGORIA | `tr > th:nth-of-type(5) > div:nth-of-type(1) > span` | — | 89×19 | elemento não semântico clicável; alvo 89x19 < 44px |
| 34 | button | Filtrar coluna Categoria | `tr > th:nth-of-type(5) > div:nth-of-type(1) > button` | — | 17×44 | alvo 17x44 < 44px |
| 35 | div | **(sem nome)** | `#reportHead > tr > th:nth-of-type(5) > div:nth-of-type(2)` | — | 8×62 | sem nome acessível; elemento não semântico clicável; alvo 8x62 < 44px |
| 36 | span | EMPRESA | `tr > th:nth-of-type(6) > div:nth-of-type(1) > span` | — | 85×19 | elemento não semântico clicável; alvo 85x19 < 44px |
| 37 | button | Filtrar coluna Empresa | `tr > th:nth-of-type(6) > div:nth-of-type(1) > button` | — | 17×44 | alvo 17x44 < 44px |
| 38 | div | **(sem nome)** | `#reportHead > tr > th:nth-of-type(6) > div:nth-of-type(2)` | — | 8×62 | sem nome acessível; elemento não semântico clicável; alvo 8x62 < 44px |
| 39 | span | DATA LANÇAMENTO | `tr > th:nth-of-type(7) > div:nth-of-type(1) > span` | — | 143×19 | elemento não semântico clicável; alvo 143x19 < 44px |
| 40 | button | Filtrar coluna Data Lançamento | `tr > th:nth-of-type(7) > div:nth-of-type(1) > button` | — | 17×44 | alvo 17x44 < 44px |
| 41 | div | **(sem nome)** | `#reportHead > tr > th:nth-of-type(7) > div:nth-of-type(2)` | — | 8×62 | sem nome acessível; elemento não semântico clicável; alvo 8x62 < 44px |
| 42 | span | VALOR LÍQUIDO BRL | `tr > th:nth-of-type(8) > div:nth-of-type(1) > span` | — | 140×19 | elemento não semântico clicável; alvo 140x19 < 44px |
| 43 | button | Filtrar coluna Valor Líquido BRL | `tr > th:nth-of-type(8) > div:nth-of-type(1) > button` | — | 17×44 | alvo 17x44 < 44px |
| 44 | div | **(sem nome)** | `#reportHead > tr > th:nth-of-type(8) > div:nth-of-type(2)` | — | 8×62 | sem nome acessível; elemento não semântico clicável; alvo 8x62 < 44px |
| 45 | span | STATUS FECHAMENTO OC | `tr > th:nth-of-type(9) > div:nth-of-type(1) > span` | — | 179×19 | elemento não semântico clicável; alvo 179x19 < 44px |
| 46 | button | Filtrar coluna Status Fechamento OC | `tr > th:nth-of-type(9) > div:nth-of-type(1) > button` | — | 17×44 | alvo 17x44 < 44px |
| 47 | div | **(sem nome)** | `#reportHead > tr > th:nth-of-type(9) > div:nth-of-type(2)` | — | 8×62 | sem nome acessível; elemento não semântico clicável; alvo 8x62 < 44px |

## Próximo passo

Para cada controle, escreva o resultado esperado (o que muda na tela ou qual requisição sai) e cubra com um teste. Corrija os 68 problema(s) apontados ou justifique.
