---
name: performance-apps
description: Medir e melhorar a velocidade de apps web de dados (backend FastAPI/Flask com Databricks SQL ou outro banco, frontend HTML/JS com gráficos). Use quando o app estiver lento, antes de publicar, ou ao pedir otimização de carregamento, filtros, consultas ou payload.
---

# Velocidade de apps de dados

O objetivo é deixar o app mais rápido **sem mudar nenhum número**: medir antes, achar o gargalo de verdade, corrigir na ordem de maior ganho e provar o resultado medindo depois, nas mesmas condições.

## Regras

- **Sem medição, sem otimização.** Nada de mudar código "porque costuma ajudar". Primeiro a linha de base; depois cada mudança com o seu ganho medido.
- **Os números não mudam.** Velocidade nunca justifica alterar regra de negócio, filtro, cálculo ou fonte de dados. Depois de otimizar, rode a conferência de valores da skill `qa-apps` (se existir) ou compare os KPIs de cada tela antes e depois.
- **Mesmas condições:** compare frio com frio e quente com quente, com o mesmo warehouse, a mesma rede e o mesmo volume de dados. O resultado de um warehouse que acabou de "acordar" não se compara com o de um já aquecido.
- **Cache nunca mistura usuários.** Se o app usa permissão por usuário (OBO, RLS, perfis), a chave do cache inclui o usuário. O cache também precisa respeitar a atualização dos dados (TTL coerente com o "Atualizado em").
- **Não declare ganho que não mediu.** Separe o que foi medido do que é estimativa.

## Passo 1. Linha de base

Rode com o app local no ar. Os scripts aceitam `--help`; rode com `--help` antes, em vez de ler o código.

```bash
# API: cada rota medida a frio (1ª chamada) e a quente (N chamadas), com p50/p95, tamanho e Server-Timing
python scripts/medir_api.py --base http://localhost:8000 --rota "/api/kpis?mes=10&ano=2026" --rota "/api/vendas?mes=10" -n 10 --saida medicao-api-antes.md

# Página: tempo até os dados aparecerem, LCP, requisições, KB, tarefas longas e erros de console
python scripts/medir_pagina.py --url http://localhost:8000/vendometro --pronto "#grafico-mensal canvas" --repeticoes 3 --saida medicao-pagina-antes.md

# Simulando celular: rede 4G e CPU 4x mais lenta
python scripts/medir_pagina.py --url http://localhost:8000/vendometro --pronto "#grafico-mensal canvas" --rede 4g --cpu 4 --largura 390 --saida medicao-celular-antes.md
```

- `--pronto` é o seletor do elemento que recebe os dados (o primeiro KPI, o rótulo do gráfico principal). O script espera o texto real, ignorando "—", "--", vazio e "Carregando". Sem `--pronto`, mede só o carregamento da página, não a espera pelos dados.
- Requisitos: `medir_api.py` usa só a biblioteca padrão do Python. `medir_pagina.py` precisa de `pip install playwright` e `python -m playwright install chromium`.

**Metas iniciais** (ajuste ao app e registre as que valerem):

| Métrica | Meta |
|---|---|
| API, p95 a quente | ≤ 800 ms por rota |
| Dados na tela (desktop, warehouse aquecido) | ≤ 2 s |
| Dados na tela (celular simulado: 4G + CPU 4x) | ≤ 4 s |
| Transferido por tela | ≤ 300 KB comprimidos, sem contar fontes e bibliotecas em cache |
| Tarefas longas no navegador | nenhuma acima de 200 ms |
| Erros de console | zero |

## Passo 2. Achar o gargalo

Divida o tempo de cada tela em quatro partes antes de mexer em qualquer coisa:

1. **Banco / warehouse:** tempo de cada consulta SQL.
2. **Backend:** tempo do servidor fora do SQL (conexão, transformação, serialização).
3. **Rede:** tamanho das respostas, compressão, quantidade de requisições e requisições em sequência ("cascata").
4. **Navegador:** JavaScript, montagem de gráficos e tabelas, tarefas longas.

Para separar 1 e 2, instale o middleware de `resources/server_timing_fastapi.py`. Ele devolve o cabeçalho `Server-Timing` com o tempo de cada consulta, e o `medir_api.py` já mostra esses tempos. Se o app não for FastAPI, adapte a mesma ideia: cronometrar cada consulta e devolver no cabeçalho.

## Passo 3. Corrigir na ordem de ganho

Ataque primeiro a parte que mais pesa. Os problemas mais comuns em apps de dados, do maior para o menor ganho típico:

**Banco / Databricks SQL**
- **Warehouse frio:** a primeira consulta depois de parado pode levar vários segundos. Isso não se resolve no código: ajuste o auto stop do warehouse ou faça um aquecimento no início do horário de uso. Meça e registre separado.
- **Agregar na hora:** se a tela soma milhões de linhas a cada filtro, crie tabelas ou views materializadas já agregadas no nível que as telas usam (ex.: mês × canal × cliente) e consulte essas.
- **Colunas de filtro:** use liquid clustering (ou Z-order e particionamento) nas colunas mais filtradas (data, canal, cliente). Confira o perfil da consulta (query profile) para ver se os arquivos estão sendo pulados.
- **Consultas enxutas:** nada de `SELECT *`. Traga só as colunas usadas, com `LIMIT` e paginação no servidor para tabelas grandes.
- **Cache de resultado do Databricks SQL:** consultas com o texto idêntico e tabelas sem mudança voltam do cache. Mantenha o SQL estável e passe filtros como parâmetros, sem concatenar valores que mudam à toa (como o horário atual).

**Backend (FastAPI)**
- **Endpoint `async def` com chamada bloqueante.** O `databricks-sql-connector`, o `pyodbc`, o `requests` e o `pandas.read_sql` bloqueiam. Dentro de `async def`, travam o servidor inteiro, e as requisições passam a ser atendidas uma de cada vez. Use `def` (o FastAPI roda em thread) ou `await run_in_threadpool(...)`. É um dos ganhos mais fáceis e mais comuns.
- **Consultas em sequência que não dependem uma da outra:** rode em paralelo (`ThreadPoolExecutor` ou `asyncio.gather` com `run_in_threadpool`).
- **Conexão aberta a cada consulta:** abrir sessão no warehouse custa caro. Reaproveite a conexão dentro da mesma requisição. Entre requisições, só reaproveite se a identidade for a mesma; com OBO, nunca compartilhe a conexão de um usuário com outro.
- **N+1:** uma consulta por item de lista (ex.: uma por cliente). Troque por uma consulta com `IN` ou `GROUP BY`.
- **Cache com TTL** (ex.: `cachetools.TTLCache`) para combinações de filtros repetidas, com chave = (usuário, rota, filtros) e TTL coerente com a atualização dos dados.
- **Serialização:** para resultados grandes, `cursor.fetchall_arrow()` é mais rápido que `fetchall()`. Para JSON grande, `ORJSONResponse`.
- **Compressão:** `app.add_middleware(GZipMiddleware, minimum_size=1000)`.

**Rede / payload**
- **Mande só o que a tela mostra.** Agregados para os gráficos; detalhe sob demanda (ao abrir, paginar ou expandir).
- **Cascata:** se o front faz `await` em uma chamada e só depois dispara a próxima, sem depender dela, use `Promise.all`.
- **Muitas requisições pequenas para a mesma tela:** junte num endpoint por tela, se isso não duplicar lógica.
- **Bibliotecas por CDN com versão fixa** (cache longo), `preconnect` para o CDN e `defer` nos scripts que não são críticos.

**Navegador**
- **Filtros:** cancele a requisição anterior quando o usuário muda o filtro (`AbortController`) e use debounce de 250–300 ms na busca por texto.
- **Gráficos:** para dados novos, use `chart.data = ...; chart.update()`. Destruir e recriar fica só para troca de tema.
- **Tabelas grandes:** pagine ou virtualize. Não renderize milhares de linhas de uma vez.
- **Primeira impressão:** mostre o esqueleto (skeleton) imediatamente e carregue os gráficos abaixo da dobra depois.

## Passo 4. Medir depois e comparar

Rode os mesmos comandos do passo 1, nas mesmas condições, salvando com sufixo `-depois`. Confira os valores das telas: devem ser os mesmos de antes.

## Entrega

1. **Tabela antes × depois** por rota e por tela (frio e quente; desktop e celular simulado), em ms e KB.
2. **Gargalos encontrados**, cada um com a correção aplicada e o ganho medido.
3. **O que não dá para resolver no código** (ex.: warehouse frio), com a recomendação.
4. **Conferência de valores:** números iguais antes e depois, ou as divergências encontradas.
5. **Metas atingidas e não atingidas.**

Não altere configuração de warehouse, permissões ou deploy sem pedido explícito; recomende.
