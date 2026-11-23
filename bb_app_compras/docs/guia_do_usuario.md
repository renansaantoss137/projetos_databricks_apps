# Guia do Usuário — COMPRAS 360°

> Portal de Compras da Bimbo Brasil

---

## 1. O que é o COMPRAS 360°

O COMPRAS 360° é o portal de inteligência de compras da Bimbo Brasil. Ele mostra, de forma visual e interativa, tudo sobre gastos, ordens de compra, savings, prazos de pagamento e exceções de processo — reunindo dados do Oracle Cloud em um só lugar.

---

## 2. Como Acessar

1. Abra o navegador (Chrome ou Edge recomendado)
2. Acesse o link: **https://compras-360-8674310331778219.19.azure.databricksapps.com**
3. Faça login com seu e-mail corporativo (`@grupobimbo.com`)
4. Você verá a tela inicial com os 6 módulos disponíveis

> **Dica**: Salve o link nos favoritos do navegador para acesso rápido.

---

## 3. Os 6 Módulos

| # | Módulo | Para que serve |
| --- | --- | --- |
| 01 | **Performance de Compras** | Visão geral: quanto gastamos, quanto economizamos, prazo médio de pagamento e tempo de processamento |
| 02 | **Análise de Gastos** | Entender onde o dinheiro está indo: por item, fornecedor, planta e curva ABC |
| 03 | **Gestão de Ordens** | Acompanhar ordens de compra abertas, atrasadas e comparar previsto vs. realizado |
| 04 | **Condições Comerciais** | Analisar prazos de pagamento, savings por fornecedor e oportunidades de renegociação |
| 05 | **Governança** | Identificar exceções: OCs pós-fatura, compras emergenciais, notas sem OC e compras descentralizadas acima de R$ 30 mil |
| 06 | **Relatórios** | Explorar os dados em detalhe com busca, filtros avançados e exportação para Excel |

---

## 4. Filtros — Como Usar

Todos os módulos possuem uma **barra de filtros** no topo. Os filtros são **cascateados**: ao selecionar um valor, os demais filtros mostram apenas opções compatíveis.

**Filtros disponíveis:**

* **Ano** — selecione um ou mais anos
* **Mês** — selecione um ou mais meses
* **Empresa** — BB (Bimbo Brasil) ou BQ (Bimbo QSR)
* **Grupo de Compras** — DIRETOS ou INDIRETOS
* **Fornecedor** — busque pelo nome
* **Unidade/Planta** — filtre por localidade

**Dicas:**
* Clique em "Limpar" para remover todos os filtros
* No módulo de Relatórios, use a busca textual para encontrar uma nota ou OC específica
* Para exportar dados, clique no botão de **download Excel** (ícone ↓) presente nas tabelas

---

## 5. Exemplos de Perguntas que Funcionam Bem

Copie e use como guia para encontrar a informação:

### Performance de Compras (Módulo 01)

> **"Quanto gastamos este ano comparado ao ano passado?"**
> → Abra o módulo Performance. O gráfico "Spend YoY" mostra mês a mês. Os KPIs no topo mostram o total.

> **"Qual o saving acumulado de 2026?"**
> → No módulo Performance, veja o KPI "Savings". Filtre o ano desejado.

> **"Quanto tempo leva da requisição até a nota fiscal?"**
> → No módulo Performance, veja o painel "Lead Time" com as 3 etapas.

### Análise de Gastos (Módulo 02)

> **"Quais são os 10 itens com maior gasto?"**
> → Abra o módulo Gastos. O card "Top Itens" mostra o ranking com valor e percentual.

> **"Quais fornecedores concentram 80% do gasto?"**
> → No módulo Gastos, veja a tabela "Curva ABC". A classe A representa ~80% do valor.

### Gestão de Ordens (Módulo 03)

> **"Quantas ordens de compra estão atrasadas?"**
> → No módulo Ordens, o KPI "OCs Atrasadas" mostra a quantidade e o valor total.

> **"Qual fornecedor tem mais atraso na entrega?"**
> → No módulo Ordens, veja o gráfico "Atraso por Fornecedor".

### Condições Comerciais (Módulo 04)

> **"Qual o prazo médio de pagamento atual?"**
> → No módulo Comercial, o KPI "Prazo Ponderado" mostra o valor em dias.

### Governança (Módulo 05)

> **"Quantas notas foram lançadas sem OC este ano?"**
> → No módulo Governança, selecione a exceção "Nota sem OC".

> **"Quanto temos de compra descentralizada acima de R$ 30 mil?"**
> → No módulo Governança, selecione "OC Descentralizada > 30K".

### Relatórios (Módulo 06)

> **"Preciso de todas as notas do fornecedor X em janeiro/2026."**
> → No módulo Relatórios, selecione o dataset "Notas Fiscais", filtre Fornecedor e Mês, e exporte para Excel.

---

## 6. O que o COMPRAS 360° NÃO Sabe Responder

| O que NÃO faz | O que fazer em vez disso |
| --- | --- |
| Dados em tempo real (atualiza diariamente) | Se precisar do dado do dia, solicite a execução do ETL à equipe de dados |
| Compras do grupo COMERCIAL | Essas compras são excluídas dos filtros por regra de negócio |
| Detalhes de contrato ou cláusulas | Consultar o sistema Oracle Cloud diretamente |
| Previsão / forecast de gastos | Usar ferramentas de planejamento financeiro |
| Dados de outras regionais (fora Brasil) | Escopo limitado a BB e BQ |
| Aprovações ou workflows | Usar o Oracle Cloud para fluxos de aprovação |

---

## 7. FAQ — Perguntas Frequentes

**P: Com que frequência os dados são atualizados?**
> R: Os dados são carregados a partir do Oracle Cloud. A atualização depende da execução do ETL (idealmente diária). Se os dados parecem antigos, peça à equipe de dados para executar o notebook de carga.

**P: Por que o saving aparece como zero para alguns fornecedores?**
> R: O saving é calculado comparando o preço atual da nota com o preço anterior. Se não houver preço anterior registrado, ou se o saving percentual estiver fora da faixa 0-100%, o sistema desconsidera.

**P: O que significa "Nota sem OC"?**
> R: São notas fiscais que foram lançadas no Oracle sem uma ordem de compra vinculada. Isso pode indicar uma compra emergencial ou um processo sem requisição prévia.

**P: Posso exportar os dados para Excel?**
> R: Sim! No módulo de **Relatórios**, use o botão de download. Nos demais módulos, as tabelas também possuem opção de exportação.

**P: O que é "Centralizado" vs. "Descentralizado"?**
> R: **Centralizado** = compra feita pela área de Compras (via acordo/blanket ou OC acima de R$ 30 mil). **Descentralizado** = compra feita diretamente pela unidade/planta, sem passar pelo Compras central.

---

## 8. A Quem Recorrer em Caso de Dúvida

| Assunto | Contato |
| --- | --- |
| Problemas técnicos no app (não abre, erro, lentidão) | **Renan Ferreira** — renan.ferreira@grupobimbo.com |
| Dados parecem incorretos ou desatualizados | **Renan Ferreira** — renan.ferreira@grupobimbo.com |
| Dúvidas sobre regras de negócio (savings, centralização) | Área de Compras / Gestão de Fornecedores |
| Acesso ao app (permissão negada) | **Renan Ferreira** — renan.ferreira@grupobimbo.com |
| Dados do Oracle Cloud (fonte) | Equipe Oracle Cloud / TI |
