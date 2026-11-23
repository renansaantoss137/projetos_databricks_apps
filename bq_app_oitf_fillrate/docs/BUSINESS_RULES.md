# Regras de Negócio — OTIF & Fill Rate

**Projeto:** Cockpit Logístico Bimbo QSR Brasil  
**Última validação:** 2026-07-08  
**Responsável pela validação:** Equipe de Planejamento Logístico

---

## 1. Fill Rate (Quantidade)

### Fórmula

```
Fill Rate (%) = Qtde Atendida / (Qtde Pedida − Qtde Cancelada) × 100
```

### Regras

| # | Regra | Detalhe |
|---|-------|--------|
| FR-01 | Cancelados excluídos do denominador | `PEDIDO_QTDE_CANCELADO` é subtraído do denominador, não penaliza o indicador |
| FR-02 | Pedidos futuros excluídos | Somente pedidos com `DT_PLANEJADA_FATURAMENTO < HOJE` entram no cálculo |
| FR-03 | Cap em 100% | Overdelivery (atendido > pedido) não faz o % ultrapassar 100% na exibição |
| FR-04 | Produto excluído | Produto `999999917` é removido de toda a base |
| FR-05 | Canal excluído | Registros com canal = "NÃO DEFINIDO" são excluídos |
| FR-06 | Status elegíveis | Todos os status (0, 1, 2, 9) entram na base; cancelados (9) só afetam a subtração no denominador |
| FR-07 | Registro ativo | Apenas registros com `status_registro = 'ATIVO'` |

### Meta

**≥ 96%**

---

## 2. On Time

### On Time CIF (frete por conta da Bimbo)

```
On Time CIF = 1 quando DATA_CHEGADA_DESTINO ≤ DATA_AGENDA_ENTREGA
```

- Comparação: data/hora de chegada no destino final vs data agendada de entrega ao cliente.

### On Time FOB (frete por conta do cliente)

```
On Time FOB = 1 quando DATA_CHEGADA_PLANTA ≤ DATA_GRADE + 30 minutos
```

- Comparação: data/hora de chegada na planta Bimbo vs data/hora da grade + tolerância de 30 minutos.
- A tolerância de 30 minutos é uma regra validada pelo negócio (veículos do cliente que chegam com pequeno atraso operacional aceitável).

### Regras Comuns

| # | Regra | Detalhe |
|---|-------|--------|
| OT-01 | Status elegíveis | Apenas pedidos com status 1 (Faturado Parcial) e 2 (Faturado) |
| OT-02 | Status excluídos | Status 0 (Aberto) e 9 (Cancelado) NÃO entram no cálculo de On Time |
| OT-03 | Tempo de atraso | Calculado em minutos (DATEDIFF MINUTE) para fins de diagnóstico |
| OT-04 | Grupo excluído | Clientes do grupo "ARMAZÉM EXTERNO" são excluídos do cálculo OTIF |

---

## 3. In Full

### Fórmula

```
In Full = 1 quando QTDE_ATENDIDA ≥ (QTDE_PEDIDA − QTDE_CANCELADA)
         E (QTDE_PEDIDA − QTDE_CANCELADA) > 0
```

### Regras

| # | Regra | Detalhe |
|---|-------|--------|
| IF-01 | Threshold 100% | Só conta como In Full se entregou TUDO o que foi prometido (ou mais) |
| IF-02 | Overdelivery = OK | Se atendeu mais do que o pedido, conta como In Full |
| IF-03 | Denominador > 0 | Se (Pedido - Cancelado) = 0, o registro não é avaliado |
| IF-04 | Status elegíveis | Apenas status 1 e 2 (mesma regra do On Time) |
| IF-05 | Faturado Parcial | Status 1 naturalmente falha no In Full (foi faturado parcialmente) |

---

## 4. OTIF (On Time In Full)

### Fórmula

```
OTIF = On Time × In Full  (ambos devem ser 1 para contar como OTIF OK)
```

### Variantes

| Variante | Cálculo |
|----------|--------|
| OTIF FOB | `OT_FOB × In Full` |
| OTIF CIF | `OT_CIF × In Full` |
| OTIF Geral | `Total OTIF OK (FOB + CIF) / Total Remessas Elegíveis (FOB + CIF)` |

### Regra Crítica — OTIF Geral

**OTIF Geral NÃO é a média aritmética de OTIF CIF e OTIF FOB.**

É calculado como:
```
OTIF Geral (%) = (ΣOTIF_FOB_OK + ΣOTIF_CIF_OK) / (ΣRemessas_FOB + ΣRemessas_CIF) × 100
```

Isso garante que o peso relativo de cada tipo de frete seja proporcional ao volume real.

### Meta

**≥ 85%**

---

## 5. Regra BOB e KFC (Unificada)

### Histórico

Até v1.0.0, BOB e KFC tinham uma regra especial que usava `DB_PED_DT_PREVENT` (Mercanet) no lugar de `DATA_GRADE` (OTM) para datas > 2026-05-31.

### Regra Atual (a partir de v1.1.0)

**Removida.** BOB e KFC agora seguem a mesma regra de todos os demais clientes:
- On Time FOB: `DATA_CHEGADA_PLANTA <= DATA_GRADE + 30 minutos`
- On Time CIF: `DATA_CHEGADA_DESTINO <= DATA_AGENDA_ENTREGA`

### Justificativa

Decisão de simplificação aprovada pela gestão. Centralizar todas as regras de cálculo em um único padrão para todos os clientes.

---

## 6. Exclusões Globais

| Exclusão | Razão |
|----------|------|
| Produto `999999917` | Produto de teste/sistema |
| Canal "NÃO DEFINIDO" | Cadastro incompleto |
| Grupo "ARMAZÉM EXTERNO" | Movimentação interna, não é entrega a cliente |
| `status_registro ≠ 'ATIVO'` | Registros inativos/deletados |
| Pedidos futuros (DT_PLAN >= HOJE) | Ainda não venceram, não podem ser avaliados |

---

## 7. Painel Executivo — Regras Adicionais

| # | Regra | Detalhe |
|---|-------|--------|
| PE-01 | Separação vencido/futuro | KPIs calculados apenas sobre pedidos vencidos |
| PE-02 | Pareto por impacto | Ranking por contribuição ao gap vs meta 96%, não por menor % |
| PE-03 | Linha 80% | Referência visual para concentração de perdas |
| PE-04 | Ação Prioritária | Maior perda concentrada entre todas as combinações KPI × dimensão |
| PE-05 | Insights determinísticos | IA não calcula KPIs; apenas resume métricas já calculadas pelo backend |

---

## 8. Regra de Elegibilidade Temporal (C5)

**Partial Pass:** Fill Rate e OTIF compartilham o mesmo boundary temporal (DT_PLANEJADA < HOJE), mas possuem denominadores diferentes por definição de cada KPI:
- Fill Rate: denominador = Qtde Pedida − Cancelada (nível item)
- OTIF: denominador = Remessas elegíveis com status 1 ou 2 (nível pedido/remessa)

---

## Histórico de Validações

| Data | Evento |
|------|-------|
| 2026-06-15 | Sessão de planejamento — definição inicial das regras |
| 2026-07-08 | Validação completa com equipe logística |
| 2026-07-16 | Documentação formal gerada |
