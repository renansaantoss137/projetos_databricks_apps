# Decisões de Projeto (ADR)

**Projeto:** Cockpit Logístico OTIF & Fill Rate — Bimbo QSR Brasil  
**Última atualização:** 2026-07-16

Este documento registra as decisões arquiteturais e de negócio tomadas ao longo do projeto. Cada decisão é imutável após registrada — novas decisões que substituam anteriores devem ser adicionadas como "Supercedência".

---

## ADR-001: Tolerância de 30 minutos no On Time FOB

**Data:** 2026-06-15  
**Status:** Aceita  
**Contexto:** Veículos de clientes FOB (que fazem coleta na planta) frequentemente chegam com pequenos atrasos operacionais (trânsito, fila de portaria). Penalizar esses atrasos mínimos distorceria o indicador.  
**Decisão:** Aplicar tolerância de +30 minutos sobre a `DATA_GRADE` para classificação de On Time FOB.  
**Consequência:** Pedidos FOB que chegam até 30 min após a grade são considerados "on time". Tolerância não se aplica a CIF.

---

## ADR-002: Regra BOB/KFC com Data Grade Ajustada

**Data:** 2026-06-15 (implementada em 2026-07-08)  
**Status:** Aceita  
**Contexto:** Para os clientes BOB e KFC, a `DATA_GRADE` informada pelo OTM não reflete a janela real de coleta/entrega. O sistema Mercanet (`DB_PED_DT_PREVENT`) possui a data correta.  
**Decisão:** Para BOB e KFC com `DATA_GRADE > 2026-05-31`, substituir `DATA_GRADE` por `DB_PED_DT_PREVENT`.  
**Consequência:** O On Time desses clientes é avaliado contra a data planejada real, não contra a grade OTM incorreta. A regra tem data de corte para não afetar histórico anterior.

---

## ADR-003: OTIF Geral como total ponderado (não média)

**Data:** 2026-06-15  
**Status:** Aceita  
**Contexto:** Se OTIF Geral fosse a média simples de CIF e FOB, plantas com poucos pedidos FOB teriam peso desproporcional.  
**Decisão:** OTIF Geral = (Total OTIF OK CIF + Total OTIF OK FOB) / (Total Remessas CIF + Total Remessas FOB).  
**Consequência:** O indicador reflete o volume real. Uma planta 100% CIF com 1000 remessas pesa mais que uma planta 100% FOB com 10 remessas.

---

## ADR-004: Cancelados excluídos do denominador do Fill Rate

**Data:** 2026-06-15  
**Status:** Aceita  
**Contexto:** Itens cancelados pelo cliente não representam falha de atendimento da Bimbo. Incluí-los no denominador penalizaria injustamente.  
**Decisão:** Denominador = Qtde Pedida − Qtde Cancelada.  
**Consequência:** Fill Rate mede efetivamente a capacidade de entrega sobre o que foi prometido e mantido.

---

## ADR-005: Pedidos futuros excluídos do cálculo

**Data:** 2026-06-15  
**Status:** Aceita  
**Contexto:** Pedidos cuja data planejada ainda não venceu não podem ser avaliados — seria injusto medir algo que ainda não teve oportunidade de ser cumprido.  
**Decisão:** Somente pedidos com `DT_PLANEJADA < HOJE` entram nos KPIs do Painel Executivo e Fill Rate.  
**Consequência:** O indicador reflete performance real, não projeção.

---

## ADR-006: Pareto por impacto no gap (não por menor %)

**Data:** 2026-07-01  
**Status:** Aceita  
**Contexto:** Um ranking por "menor % de Fill Rate" poderia destacar um cliente pequeno com 50% mas 10 caixas, enquanto um cliente grande com 90% e 10.000 caixas representa uma perda muito maior.  
**Decisão:** O Pareto rankeia por `loss_value` (quantidade de unidades/remessas que faltam para atingir a meta 96%) e `impact_pp` (impacto em pontos percentuais no indicador global).  
**Consequência:** Prioriza ação onde o retorno real é maior.

---

## ADR-007: Arquitetura Flask + Azure SQL (sem Spark)

**Data:** 2026-07-03  
**Status:** Aceita  
**Contexto:** Os dados já residem em Azure SQL Server (Mercanet + OTM). Usar Spark/Delta adicionaria complexidade de ETL sem benefício, dado o volume de dados (milhares de pedidos/dia, não milhões).  
**Decisão:** Conexão direta Flask → Azure SQL via pyodbc/pymssql. Sem camada de ETL intermediária.  
**Consequência:** Dados em tempo real, sem delay de pipeline. Trade-off: dependência da disponibilidade do Azure SQL.

---

## ADR-008: Databricks Apps como plataforma de hosting

**Data:** 2026-07-03  
**Status:** Aceita  
**Contexto:** Precisava de hospedagem segura, com autenticação SSO, acesso a secrets, sem infra adicional para gerenciar.  
**Decisão:** Usar Databricks Apps (Flask nativo) com secrets via `dbutils.secrets`.  
**Consequência:** Deploy simples, autenticação herdada do workspace, secrets protegidos. Compute MEDIUM provisionado.

---

## ADR-009: Fallback pymssql para ambientes sem ODBC Driver

**Data:** 2026-07-10  
**Status:** Aceita  
**Contexto:** O container Databricks Apps nem sempre tem o ODBC Driver 17 instalado. Depender exclusivamente do pyodbc causava falhas de deploy.  
**Decisão:** Implementar fallback automático: tenta pyodbc primeiro; se falhar, usa pymssql (pure Python, FreeTDS).  
**Consequência:** Deploy resiliente. Wrapper `_MssqlCursor` converte placeholders `?` para `%s` automaticamente.

---

## ADR-010: Connection pooling com TTL de 5 minutos

**Data:** 2026-07-12  
**Status:** Aceita  
**Contexto:** Conexões Azure SQL ficam idle e são cortadas pelo firewall após inatividade. Health-check com `SELECT 1` detecta conexões mortas, mas não previne stale connections.  
**Decisão:** Forçar reconexão a cada 5 minutos (TTL), independente de uso.  
**Consequência:** Conexões sempre frescas, sem erros de timeout em picos de uso após inatividade.

---

## ADR-011: Insights determinísticos (sem IA generativa)

**Data:** 2026-07-14  
**Status:** Aceita  
**Contexto:** A seção "Leitura Executiva" deve gerar texto resumido, mas não pode inventar dados ou extrapolar.  
**Decisão:** Gerar insights via lógica condicional no backend (template-based), usando apenas valores já calculados pelo Pareto, prioridades e métricas.  
**Consequência:** Zero risco de "alucinação". Texto é fact-based e auditável.
