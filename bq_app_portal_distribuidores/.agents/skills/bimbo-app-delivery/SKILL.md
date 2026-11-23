---
name: bimbo-app-delivery
description: Use at the start of any non-trivial change to a Grupo Bimbo D&A Flask/HTML/JS Databricks App (new app, new module, multi-file feature, bug that touches data, pre-release validation, DEV->PROD promotion). Routes the task to the right corporate and external skills, enforces the lifecycle (discovery, implementation, UX refinement, verification, DEV validation, PROD approval, monitoring) and captures reusable improvements as approval-gated skill proposals. Do NOT use for a one-line CSS/text fix, pure ETL, or Lakebase/Jobs administration with no app change.
metadata:
  version: "0.1.0"
  owner: "renan.ferreira@grupobimbo.com"
  team: "D&A Brasil"
  status: "beta"
---

# Bimbo App Delivery (orquestrador)

Coordena o trabalho. Não repete o conteúdo das skills especializadas: escolhe quais carregar e quando parar.

## 1. Classifique o pedido (decide o que carregar)

| Tamanho | Exemplo | Carregar | Verificação mínima |
|---|---|---|---|
| XS | texto, cor, espaçamento num componente | nada além do arquivo | inspeção do diff + render se possível |
| S | ajuste visual/responsivo localizado | `frontend-apps` (`databricks_frontend_produtos`) | checklist-responsivo do componente; viewports 390/1440 |
| M | filtro, tabela, KPI, gráfico, exportação, estado de carga | `bimbo-dashboard-components` + `bimbo-app-qa` (só a seção do controle) | testes do controle + conferência tela x API |
| L | módulo/app novo, mudança de cálculo, release | todas as acima + `databricks-apps`/`databricks-dabs`/`databricks-lakebase` conforme stack | suíte de release (`bimbo-app-qa` seção Release) |

Nunca carregue todas as skills do catálogo. Liste as skills do schema (`list_skills`) e carregue só as da tabela acima.

## 2. Fontes de verdade e conflitos

- Regras de negócio: o backend aprovado (`app.py`, módulos, SQL/notebooks aprovados). Nunca reimplemente cálculo no front.
- Visual D&A: `frontend-apps` (identidade-da.md, dashboards-swd.md). Onde `bimbo-ux-ui` divergir (navbar no topo com emojis, glass em tudo, máx. 3 filtros, Z-pattern universal), **prevalece `frontend-apps` + o padrão aprovado do app** e a divergência é registrada como proposta (references/skill-improvement.md). Não resolva conflito em silêncio.
- Contexto do projeto: `AGENTS.md`, `PRODUCT.md`, `DESIGN.md`, `DATA_CONTRACT.md` na raiz do projeto. Se faltar `DATA_CONTRACT.md` em tarefa M/L, crie um rascunho com o que foi verificado no código e marque lacunas como `NÃO VERIFICADO`.
- Impeccable (externo, oficial `pbakaus/impeccable`): dono de direção visual, critique/audit/polish. Não é fonte de cálculo, autorização ou integridade de dados.

## 3. Ciclo de vida

1. **Descoberta** — leia contexto do projeto; para app/módulo novo use `/impeccable init` e `/impeccable shape` (Codex: `$impeccable ...`) onde o Impeccable oficial estiver instalado. Registre usuários, decisões suportadas, fontes, filtros, permissões e critérios de aceite. Não invente regra de negócio: pergunte ou marque como pendente.
2. **Implementação** — reutilize componentes do app e os contratos de `bimbo-dashboard-components`. Mudanças mínimas; preserve rotas, contratos e `app.yaml`.
3. **Refinamento UX** — escolha 1-2 comandos Impeccable pelo escopo (`critique`/`audit` para revisão, `adapt` para responsivo, `harden` para estados de erro/vazio, `polish` no fim). Não rode todos.
4. **Verificação** — `bimbo-app-qa`. Teste falhou = defeito; não altere teste/tolerância para passar. Máximo 3 ciclos de correção por defeito; depois disso reporte com evidência.
5. **DEV** — deploy só pelo fluxo existente (DAB / `apps deploy` no app DEV) e só se o pedido autorizar. Antes: `databricks apps get <app> --output json` e confira `app_status`/`compute_status`. Valide no DEV com dados reais.
6. **PROD** — exige aprovação explícita do usuário na conversa. Bloqueado com qualquer BLOCKER/CRITICAL aberto (ver `bimbo-app-qa` gates). Porte patches; nunca copie DEV inteiro sobre PROD (ETLs e apps podem ter divergido).
7. **Monitoramento** — especificação em `bimbo-app-qa/references/severity-gates-monitoring.md`. Incidente em PROD volta pelo fluxo DEV.

## 4. Proibições

- Não alterar dados de negócio (Lakebase/UC) durante QA; consultas só de leitura.
- Não mudar permissões, schedules de Jobs nem publicar em PROD sem autorização explícita.
- Não mascarar falha de carga com zero, valor antigo ou mock. Erro aparece como erro ("—" + aviso).
- Não declarar "testado" sem execução; separe Executado / Estático / Não executado.
- Não instalar ferramentas externas sem aprovação.

## 5. Relatório de entrega (sempre)

1. O que mudou (arquivos) e por quê.
2. Verificações: executadas (com evidência), estáticas, não executadas (motivo).
3. Defeitos abertos com severidade.
4. Estado de deploy (DEV/PROD, deployment_id) ou "não publicado".
5. **Propostas de melhoria de skill** (agrupadas, formato em references/skill-improvement.md) — nunca aplicadas sem aprovação.

## Referências

- `references/skill-improvement.md` — detectar, propor, aprovar e publicar melhorias de skills.
- `references/agent-integration.md` — Codex, Antigravity (Gemini/Claude) e Genie Code.
