---
name: project-business-rules
description: Regras de negócio confirmadas para o projeto OTIF/Fill Rate — Bimbo Brasil
metadata:
  type: project
---

## Métricas e fórmulas

**Fill Rate (Qtde)**
- Fórmula: `PEDIDO_QTDE_ATENDIDO / (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO)`
- Cancelados excluídos do denominador (regra confirmada)
- Meta mínima: **≥ 96%**

**In Full (OTIF)**
- Threshold: **100%** — só conta como In Full quando entregou exatamente o que foi prometido
- Pedido Faturado Parcial (status 1) entra no cálculo e naturalmente falha no IF

**On Time (OTIF)**
- Condição: `DT_REAL_FATURAMENTO <= DT_PLANEJADA_ENTREGA`
- Calculado apenas para status 1 (Faturado Parcial) e 2 (Faturado)
- Status Cancelado (9) e Aberto (0) não entram no cálculo de On Time

**OTIF**
- Definição: pedido que é simultaneamente On Time AND In Full
- Meta mínima: **≥ 85%**

**Regra BOB/KFC (REMOVIDA em v1.1.0)**
- A regra especial de Data Grade Ajustada foi REMOVIDA
- BOB e KFC agora seguem a mesma regra de todos os clientes: DATA_GRADE (OTM)
- Simplificação aprovada pela gestão em 2026-07-16

**Why:** Regras definidas em sessão de planejamento (2026-06-15) e validadas em 2026-07-08.
**How to apply:** Usar estas fórmulas em todos os módulos (Gestão de Pedidos, Fill Rate, OTIF, Painel Executivo). Não alterar sem confirmação do usuário.
