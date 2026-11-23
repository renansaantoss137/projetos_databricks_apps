# Portal financeiro — diagnóstico e decisões pendentes

Estado: rascunho para discussão; desenvolvimento do aplicativo ainda não aprovado.

## Objetivo e navegação

Analisar OPEX, custo de produção e receita, com detalhamento progressivo de empresa/planta até SKU quando a fonte e o negócio permitirem. O relatório dinâmico deverá preservar filtros, medidas selecionadas, paginação e exportação. Os filtros compartilhados só serão sincronizados quando tiverem o mesmo significado e granularidade.

## OPEX: modelo atual

O PBIX local contém páginas Início, Filtro, Visão Geral, Onde está o desvio? e Relatório Dinâmico. A fonte fOPEX é a aba BD_I da planilha BASE_OPEX_PBI.xlsx no SharePoint; outra planilha, base_perfil_acesso_bq.xlsx, fornece regras de acesso. O modelo constrói uma data no primeiro dia de cada mês e relaciona fOPEX[Data] a dCalendario[Data].

Medidas extraídas: Realizado = soma de LIQUIDO onde ACTUAL_FLAG = REALIZADO; orçamento = soma de LIQUIDO onde ACTUAL_FLAG = PPTO; desvio = realizado menos orçamento; percentual de desvio = desvio dividido pelo orçamento; aderência = realizado dividido pelo orçamento; anterior usa SAMEPERIODLASTYEAR; variação anterior = realizado menos anterior; percentual anterior = variação dividida pelo anterior; desvio acumulado usa DATESYTD; desvio absoluto usa ABS. Divisão por zero e valores vazios devem seguir o comportamento aprovado, sem transformá-los automaticamente em zero.

O perfil de segurança existente usa email, área de negócio, centro de custo, conta e grupo; há exceções específicas para TODAS e carga social. Precisa ser analisado e reproduzido com o responsável de segurança antes de qualquer publicação; o filtro visual não é controle de acesso.

Tabela candidata: `cat_dnabb_dv.mgtbbpdgbb_sz.planiha_de_gastos`. Há correspondência de muitos campos, mas não equivalência comprovada. Na consulta de 2026, linhas PPTO somaram zero em LIQUIDO enquanto PPTO_OFICIAL e PPTO_ORACLE apresentaram valores. O PBIX calcula orçamento a partir de LIQUIDO nas linhas PPTO. Verificar transformação, escopo, versão, segurança e origem antes de substituir a planilha; não assumir que PPTO_OFICIAL seja a resposta.

## Custos de produção

O Excel de referência possui as abas Simulate (Costos), Simulate (MFG) e XDO_METADATA. As duas primeiras apresentam hierarquia de produto, submontagem, operação, componente e recurso; a primeira inclui custo unitário e custo estendido. Os cabeçalhos estão na linha 12 e a organização informada é HAB. Existem níveis pai e filho: somar todos os níveis pode duplicar custos. A regra de custeio, período de referência, planta, moeda, tipo de custo e critério de consolidação precisam ser confirmados.

Sugestão de exploração: custo total e unitário por período/planta, composição por material, mão de obra e outros recursos, evolução e detalhamento até SKU e componentes. Disponibilidade e classificação dependem de fontes reais e validação financeira. O relatório parece ser uma simulação de manufatura; não tratar automaticamente seus custos como custo contábil real de vendas.

## Receita e margem

Sugestão: receita bruta, deduções, receita líquida, volume, preço médio ponderado e detalhamento por período, planta e SKU, desde que as dimensões existam e tenham definição aprovada. Quando houver custo dos produtos vendidos compatível em período, unidade, produto e escopo, calcular lucro bruto = receita líquida − CPV e margem bruta = lucro bruto ÷ receita líquida. Receita líquida geralmente representa receita bruta menos deduções, não receita menos custo. Definições fiscais, devoluções, tributos, frete e tratamento de receitas negativas dependem da controladoria.

`cat_dnabb_dv.grobbbqb_sz.budget_forecast_bq` contém produto, filial, período, quantidade e valor de forecast; é candidata para orçamento de receita, não comprovação de receita realizada nem de vínculo com planta. `cat_dnabb_dv.bracatlg_lz.produtos_view` e outras tabelas de itens podem apoiar identificação de SKU; equivalência e chaves ainda não foram testadas. Não foi localizada correspondência direta dos campos de custo da simulação na busca inicial pelo nome das colunas.

## Critérios de dados e QA

- Documentar fonte, responsável, frequência, chaves, moeda, período, granularidade, segurança e regras aprovadas por métrica.
- Confrontar OPEX com o PBIX para o mesmo usuário, filtros e atualização; verificar valores exatos antes da formatação, tabelas, gráficos e exportação.
- Testar filtro, navegação, telas vazias, erros, autorização e ordenação; validar divergências em percentual versus pontos percentuais.
- Nenhuma execução parcial ou SQL ausente pode ser declarada aprovação completa; testes sintéticos não substituem dados reais.
- Publicação DEV e testes reais devem ocorrer após aprovação do projeto; PROD exige aprovação explícita e gates efetivos.

## Decisões pendentes

1. Público, permissões e responsáveis por cada métrica; política de acesso entre plantas.
2. Fontes oficiais de receita realizada, CPV e custos de produção; definir se custeio simulado ou real.
3. Correspondência de planta, SKU e período entre fontes; atualidade e reconciliação.
4. Definições de receita, deduções, CPV, margem, budget e períodos comparativos.
5. Indicadores iniciais e hierarquias de detalhamento com os clientes.
6. Escolha da arquitetura de consulta e requisitos de latência antes da implementação.
