# OBO (on-behalf-of-user) no Databricks Apps

Leia quando o pedido envolver OBO, "autorização de usuário", "permissão por usuário" ou "cada um vê só os seus dados".

**Isto é mudança de backend e de segurança.** Só faça com pedido explícito. Nunca mexa nisso por motivo visual.

## O que é

- **Autorização do app (padrão):** o app consulta os dados com a identidade do próprio service principal, e todos os usuários enxergam a mesma coisa.
- **Autorização de usuário (OBO):** o Databricks repassa ao app o token do usuário logado. Cada consulta roda com as permissões do Unity Catalog desse usuário, inclusive row filters e column masks.

O OBO está disponível de forma geral (GA) desde outubro de 2026.

## O que fica fora do código (dono do app e admin)

1. **Admin do workspace:** em Settings > Development > Apps fica a lista de escopos permitidos para apps. O padrão é todos; "None" desliga a autorização de usuário.
2. **Configuração do app:** declare só os escopos necessários, na UI (User authorization) ou em `user_api_scopes` no bundle/CLI.
   - App de análise somente leitura: `sql:restricted-query`.
   - Se precisar escrever via SQL: `sql`.
3. **Permissões dos usuários (de preferência por grupo):**
   - `CAN USE` no SQL warehouse;
   - `USE CATALOG`, `USE SCHEMA` e `SELECT` no Unity Catalog, nas tabelas e views que o app consulta.
   - O escopo é um teto e não concede acesso a nada.
4. **Consentimento:** na primeira visita, cada usuário aprova os escopos. Essa tela é do Databricks.
5. **Mesmo workspace:** o token só vale no workspace do app, então o warehouse precisa estar nele.

## Regras de implementação

- **Token:** leia o token do cabeçalho `x-forwarded-access-token` a cada requisição. Crie a conexão do usuário dentro do handler da requisição, nunca na inicialização, e não guarde o token.
- **Sigilo:** nunca imprima, logue ou grave o token, inclusive em tratadores de erro.
- **Falhe fechado:** sem token, responda 401/403 com mensagem clara. Nunca use o service principal como alternativa nas consultas de dados do usuário.
- **Dois clientes separados:** o do app (service principal: configuração compartilhada, métricas, jobs) e o do usuário, separados no código e nos testes.
- **Cache:** todo cache de resultado passa a ter o usuário na chave (ex.: o e-mail de `X-Forwarded-Email`). Cache compartilhado entre usuários vaza dados.
- **Regras de acesso já existentes no app** (perfis de acesso, filtros por gerente etc.): não remova nem altere sem confirmação do dono. Descreva no diagnóstico como elas vão conviver com o Unity Catalog.
- **Auditoria:** registre usuário, ação, recurso e status de cada operação feita em nome do usuário.
- **Desenvolvimento local:** os cabeçalhos só existem dentro do Databricks Apps. Em dev, use uma variável de ambiente com token pessoal, e mantenha o caminho de produção falhando fechado.

## Frontend

- A identidade do usuário (cabeçalhos `X-Forwarded-Preferred-Username` e `X-Forwarded-Email`) serve para auditoria e chave de cache. O menu padrão do app não mostra o nome.
- Estado **sem permissão** quando o Unity Catalog negar acesso, distinto de **sem dados**: explique o que aconteceu e como pedir acesso.

## Critérios de aceite

| # | Critério |
|---|---|
| O1 | Os escopos declarados são o mínimo necessário e estão documentados no projeto. |
| O2 | Toda consulta de dados do usuário usa o token do cabeçalho; nenhuma usa o service principal. |
| O3 | Sem token, a resposta é 401/403, sem alternativa silenciosa. |
| O4 | O token nunca aparece em log, mensagem de erro, arquivo ou resposta. |
| O5 | Cache com o usuário na chave, ou desligado para dados do usuário. |
| O6 | Testado com dois usuários de permissões diferentes: os resultados mudam conforme o Unity Catalog. |
| O7 | Tela "sem permissão" distinta de "sem dados". |
| O8 | Pendências fora do código (lista de escopos do admin, permissões no warehouse e no Unity Catalog) listadas na entrega. |
