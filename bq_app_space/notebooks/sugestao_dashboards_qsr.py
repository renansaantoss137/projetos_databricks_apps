# Databricks notebook source
# MAGIC %md
# MAGIC # 🎯 Sugestão Inteligente de Dashboards — Bimbo QSR (BQ)
# MAGIC 
# MAGIC **Objetivo:** Gerar diariamente uma base preditiva de recomendações personalizadas de dashboards para cada colaborador ativo da **Bimbo QSR**, combinando:
# MAGIC 1. **Inteligência Semântica:** Mapeamento via Foundation Model Databricks (`ai_query` com Llama 3.3 70B) e similaridade vetorial (TF-IDF + KNN).
# MAGIC 2. **Regras de Negócio Determinísticas:** Visão executiva/financeira obrigatória para lideranças e dashboards prioritários.
# MAGIC 3. **Catálogo Oficial BQ:** 15 dashboards e aplicações corporativas da Bimbo QSR.
# MAGIC 
# MAGIC **Origem:** `cat_dnabb_dv.grobbjrnl_cz.colaboradores`  
# MAGIC **Destino:** `cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr`

# COMMAND ----------
# MAGIC %md
# MAGIC ### 1. Parâmetros e Configurações

# COMMAND ----------
from datetime import datetime
import json
import re
import unicodedata
import pandas as pd
import numpy as np

# Tabelas e Recursos do Unity Catalog
TABELA_COLABORADORES = "cat_dnabb_dv.grobbjrnl_cz.colaboradores"
TABELA_DESTINO = "cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr"
LLM_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"

# Limite de sugestões por colaborador
MAX_SLOTS = 4

print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando pipeline de sugestões BQ...")
print(f"Origem Colaboradores : {TABELA_COLABORADORES}")
print(f"Destino Delta Table  : {TABELA_DESTINO}")
print(f"Foundation Model LLM : {LLM_ENDPOINT}")

# COMMAND ----------
# MAGIC %md
# MAGIC ### 2. Catálogo Oficial dos 15 Dashboards da Bimbo QSR

# COMMAND ----------
DASHBOARDS_QSR = [
    {
        "cod": "painel_logistico",
        "nome": "Painel Logístico",
        "espaco": "Logística",
        "tags": "logistica transporte entregas rotas rastreamento frota frete distribuicao viagens expedicao veiculos cdva cd fabril abastecimento",
        "link": "https://app.powerbi.com/reportEmbed?reportId=67e43992-3924-46c6-9528-464b40eda398"
    },
    {
        "cod": "rentabilidade",
        "nome": "Rentabilidade",
        "espaco": "Logística",
        "tags": "rentabilidade custos financeiros margem transporte frete rota eficiencia operacional custo unitario analise financeira logistica margem operacional",
        "link": "https://app.powerbi.com/reportEmbed?reportId=c25fd9f2-8516-4a41-9a04-439d84853d61"
    },
    {
        "cod": "painel_de_projetos",
        "nome": "Painel de Projetos",
        "espaco": "Logística",
        "tags": "projetos gestao cronograma entregas melhoria continua kpi plano de acao capex expansao transformacao engenharia pmo metas",
        "link": "https://app.powerbi.com/reportEmbed?reportId=dde8af11-8886-4dd4-8483-34ee3252b993"
    },
    {
        "cod": "painel_de_precos_equipes",
        "nome": "Painel de Preços Equipes",
        "espaco": "Logística",
        "tags": "precos equipes negociacao tabelas frete prestadores contratos fornecedores valores custo logistico transportadoras parceiros",
        "link": "https://app.powerbi.com/reportEmbed?reportId=99e45b11-0968-4203-a7d9-afb8dbb0a3a5"
    },
    {
        "cod": "painel_de_performance",
        "nome": "Painel de Performance",
        "espaco": "Logística",
        "tags": "performance operacional produtividade kpi tempo nivel de servico sla eficiencia operacao cd fabril expedicao carregamento",
        "link": "https://app.powerbi.com/reportEmbed?reportId=3535a0a8-4f9c-4229-ab20-5b23651ed3a8"
    },
    {
        "cod": "painel_de_precos",
        "nome": "Painel de Preços",
        "espaco": "Logística",
        "tags": "precos frete tabela tarifaria variacao combustivel custo por km rota custo frete cotacao diesel custos rodoviarios",
        "link": "https://app.powerbi.com/reportEmbed?reportId=b1073f44-78b7-4b89-b72e-e72669ac8633"
    },
    {
        "cod": "painel_de_price_protocol",
        "nome": "Painel de Price Protocol",
        "espaco": "Logística",
        "tags": "price protocol protocolo precos contratos regras tarifarias acordos comerciais compliance fiscal reajuste clausulas",
        "link": "https://app.powerbi.com/reportEmbed?reportId=e5d9ae3c-3ab4-479a-a2e1-70d091b4f3f6"
    },
    {
        "cod": "logistica_ct_e",
        "nome": "Logística CT-e",
        "espaco": "Logística",
        "tags": "cte conhecimento transporte eletronico fiscal tributario auditoria notas frete manifesto sefaz faturamento dacte auditoria",
        "link": "https://app.powerbi.com/reportEmbed?reportId=48248c1c-5d96-40c6-a0b2-f52153ebc77d"
    },
    {
        "cod": "otif_e_fill_rate",
        "nome": "OTIF e Fill Rate",
        "espaco": "Logística",
        "tags": "otif fill rate on time in full atendimento pedidos cortes faturamento nivel de servico pontualidade ruptura cliente pedidos entregas",
        "link": "https://bq-oitf-fillrate-8674310331778219.19.azure.databricksapps.com/"
    },
    {
        "cod": "dna_de_vendas",
        "nome": "DNA de Vendas",
        "espaco": "Comercial",
        "tags": "vendas receita faturamento volume clientes canais comercial metas pedidos preco medio positivacao trade distribuidores franquias qsr ticket medio",
        "link": "https://app.powerbi.com/reportEmbed?reportId=681a24a6-519d-4930-b780-0c2d81c4429c"
    },
    {
        "cod": "supply_chain_db",
        "nome": "Supply Chain",
        "espaco": "Supply Chain",
        "tags": "supply chain cadeia suprimentos demanda planejamento forecast sop estoque giro materias primas compras fornecedores producao abastecimento",
        "link": "https://app.powerbi.com/reportEmbed?reportId=5de75719-aa8f-4d15-9697-061d073d780c"
    },
    {
        "cod": "estado_de_resultados",
        "nome": "Estado de Resultados",
        "espaco": "Finanças",
        "tags": "estado de resultados dre pl resultado contabil financeiro despesas receita liquida ebitda margem orcamento forecast controladoria resultado financeiro",
        "link": "https://app.powerbi.com/reportEmbed?reportId=568b9571-8aac-4377-83a6-7fc35b605735"
    },
    {
        "cod": "financas_db",
        "nome": "Finanças",
        "espaco": "Finanças",
        "tags": "financas gestao financeira fluxo de caixa tesouraria receitas balanco controladoria planejamento financeiro custos contas a pagar receber",
        "link": "https://app.powerbi.com/reportEmbed?reportId=6849e6ec-2888-4e2b-9d2f-03eee775b206"
    },
    {
        "cod": "opex_custos_operacionais",
        "nome": "OPEX",
        "espaco": "Finanças",
        "tags": "opex custos operacionais despesas orcamento orcado realizado gestao de custos gastos centros de custo operacao despesas administrativas",
        "link": "https://app.powerbi.com/reportEmbed?reportId=e95ebdff-9082-4119-879e-428b331abd05"
    },
    {
        "cod": "performance_de_distribuidores",
        "nome": "Performance de Distribuidores",
        "espaco": "Marketing",
        "tags": "distribuidores performance marketing trade ponto de venda campanhas sell in sell out market share volume canal cobertura franquias",
        "link": "https://app.powerbi.com/reportEmbed?reportId=93686707-57e1-4d67-9448-116f67f36d65"
    }
]

df_dashboards = pd.DataFrame(DASHBOARDS_QSR)
DASH_BY_COD = {d['cod']: d for d in DASHBOARDS_QSR}
DASH_BY_NOME_UPPER = {d['nome'].strip().upper(): d for d in DASHBOARDS_QSR}

# Prepara prompt com lista estruturada de dashboards
dash_por_area = df_dashboards.groupby('espaco')['nome'].apply(list).to_dict()
LISTA_DASHBOARDS_PROMPT = ""
for area, dashs in sorted(dash_por_area.items()):
    LISTA_DASHBOARDS_PROMPT += f"{area.upper()}: {', '.join(dashs)} | "
LISTA_DASHBOARDS_PROMPT = LISTA_DASHBOARDS_PROMPT.rstrip(" | ")

print(f"Total de Dashboards BQ carregados: {len(df_dashboards)}")
print(f"Categorias: {list(dash_por_area.keys())}")

# COMMAND ----------
# MAGIC %md
# MAGIC ### 3. Extração e Filtragem de Colaboradores Ativos da Bimbo QSR
# MAGIC 
# MAGIC - Filtra colaboradores da Bimbo QSR por:
# MAGIC   - `UNIDADE` contendo 'BQ' ou 'QSR'
# MAGIC   - `CENTRO_CUSTO` contendo 'BQ'
# MAGIC   - Usuários estratégicos/administradores (ex.: `renan.ferreira`)
# MAGIC - Exclui colaboradores com rescisão e grupos puramente operativos sem acesso a computadores/portais de BI.

# COMMAND ----------
sql_colab = f"""
CREATE OR REPLACE TEMP VIEW vw_colaboradores_qsr AS
SELECT 
    ID_COLABORADOR,
    TRIM(LOWER(COLAB_EMAIL)) AS EMAIL,
    NOME_COLABORADOR,
    CARGO,
    GRUPO_CARGO,
    NIVEL_CARGO,
    UNIDADE,
    AREA_NEGOCIO,
    CENTRO_CUSTO,
    CENTRO_CUSTO_DETALHE,
    DATA_ATUALIZACAO
FROM {TABELA_COLABORADORES}
WHERE DATA_RECISAO IS NULL
  AND COLAB_EMAIL IS NOT NULL
  AND LENGTH(TRIM(COLAB_EMAIL)) > 0
  AND COLAB_EMAIL LIKE '%@%'
  AND GRUPO_CARGO != 'OPERATIVO'
  AND (
      UPPER(UNIDADE) LIKE '%BQ%' 
      OR UPPER(UNIDADE) LIKE '%QSR%' 
      OR UPPER(CENTRO_CUSTO) LIKE '%BQ%'
  )
"""
spark.sql(sql_colab)

# Cria view de cargos distintos da BQ para inferência semântica
spark.sql("""
CREATE OR REPLACE TEMP VIEW vw_cargos_distintos_qsr AS
SELECT 
    CARGO,
    GRUPO_CARGO,
    CENTRO_CUSTO_DETALHE,
    FIRST(UNIDADE) AS UNIDADE,
    FIRST(CENTRO_CUSTO) AS CENTRO_CUSTO,
    MAX(NIVEL_CARGO) AS NIVEL_CARGO,
    COUNT(DISTINCT EMAIL) AS TOTAL_COLABS
FROM vw_colaboradores_qsr
GROUP BY CARGO, GRUPO_CARGO, CENTRO_CUSTO_DETALHE
""")

total_colabs = spark.table("vw_colaboradores_qsr").count()
total_cargos = spark.table("vw_cargos_distintos_qsr").count()
print(f"Colaboradores ativos da Bimbo QSR: {total_colabs}")
print(f"Cargos distintos mapeados: {total_cargos}")

# COMMAND ----------
# MAGIC %md
# MAGIC ### 4. Recomendação Semântica por Cargo (Databricks Foundation Model + Fallback TF-IDF)
# MAGIC 
# MAGIC Utilizamos o Foundation Model da Databricks (`ai_query` com Llama 3.3 70B) para interpretar o contexto funcional de cada cargo contra a lista dos 15 dashboards.  
# MAGIC Caso a função `ai_query` não esteja disponível no cluster, o pipeline ativa um fallback matemático instantâneo via **TF-IDF + Cosine Distance (KNN)**.

# COMMAND ----------
# MAGIC %md
# MAGIC ### 4. Enriquecimento Semântico dos Cargos via Databricks LLM (`ai_query`)
# MAGIC 
# MAGIC **O Papel do LLM nesta Arquitetura:**
# MAGIC O LLM (Llama 3.3 70B) atua como um especialista de RH e Operações da Bimbo QSR. Ele expande cada cargo com uma descrição técnica rica (50 a 80 palavras-chave sobre atribuições, rotinas operacionais, KPIs e decisões diárias).
# MAGIC Essa descrição enriquecida alimenta o modelo KNN com um vocabulário semântico muito mais profundo do que apenas o título do cargo.
# MAGIC *(Se o `ai_query` estiver indisponível no cluster, o pipeline ativa um fallback automático para o perfil textual do RH).*

# COMMAND ----------
def normalizar_texto(texto):
    if not texto or pd.isna(texto):
        return ""
    texto = str(texto).lower()
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    texto = re.sub(r'[^a-z0-9\s]', ' ', texto)
    return ' '.join(texto.split())

df_dashboards['texto_busca'] = df_dashboards.apply(
    lambda r: f"{r['nome']} {r['espaco']} {r['tags']}", axis=1
).apply(normalizar_texto)

pdf_cargos = spark.table("vw_cargos_distintos_qsr").toPandas()

# 1. Tenta enriquecer com ai_query (Databricks Foundation Model)
descricoes_llm = {}
try:
    print(f"Executando enriquecimento semântico via ai_query({LLM_ENDPOINT})...")
    sql_llm = f"""
    SELECT
        CARGO,
        GRUPO_CARGO,
        CENTRO_CUSTO_DETALHE,
        ai_query(
            '{LLM_ENDPOINT}',
            CONCAT(
                'Voce e um especialista em RH e Operacoes da Bimbo QSR (divisao de Fast Food e Restaurantes da Bimbo no Brasil).\n',
                'Gere uma descricao objetiva de 50 a 70 palavras-chave sobre o cargo de "', CARGO, '" que atua na area de "', CENTRO_CUSTO_DETALHE, '".\n',
                'Inclua termos tecnicos sobre as rotinas, metas, indicadores (KPIs), dados e decisoes que essa funcao toma (ex: entregas, rotas, faturamento, despesas, margem, tributos, nivel de servico, estoques, custos operacionais, vendas, abastecimento).\n',
                'Responda APENAS com o texto descritivo corrido, sem titulos e sem marcadores.'
            )
        ) AS DESCRICAO_EXPANDIDA
    FROM vw_cargos_distintos_qsr
    """
    df_desc_llm = spark.sql(sql_llm).toPandas()
    for _, r in df_desc_llm.iterrows():
        descricoes_llm[r['CARGO']] = str(r['DESCRICAO_EXPANDIDA'] or '')
    print(f"✅ Enriquecimento LLM concluído para {len(descricoes_llm)} cargos!")
except Exception as e:
    print(f"[AVISO] ai_query indisponível ({e}). Usando perfil nativo de RH como fallback semântico...")

# Monta o texto de perfil para cada cargo (LLM Enriquecido + Metadados de RH)
def montar_perfil_cargo(row):
    cargo = row['CARGO']
    desc_ia = descricoes_llm.get(cargo, '')
    texto_base = f"{row['CARGO']} {row['GRUPO_CARGO']} {row['CENTRO_CUSTO_DETALHE']} {row['CENTRO_CUSTO']}"
    return normalizar_texto(f"{texto_base} {desc_ia}")

pdf_cargos['texto_perfil'] = pdf_cargos.apply(montar_perfil_cargo, axis=1)
print(f"Perfis semânticos gerados para {len(pdf_cargos)} cargos distintos!")

# COMMAND ----------
# MAGIC %md
# MAGIC ### 5. Motor de Decisão: Vetorização TF-IDF e Modelo KNN (`NearestNeighbors`)
# MAGIC 
# MAGIC **O Papel do KNN nesta Arquitetura:**
# MAGIC O **KNN é o tomador de decisão oficial**. Ele projeta as descrições enriquecidas dos cargos e as tags dos 15 dashboards no mesmo espaço vetorial contínuo e calcula a **distância de cosseno exata** para cada dashboard.
# MAGIC O algoritmo rankeia os dashboards por proximidade geométrica matemática, preenchendo as distâncias reais (`DISTANCIA_1` a `DISTANCIA_4`).

# COMMAND ----------
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

# Vetorização TF-IDF com unigramas e bigramas
vectorizer = TfidfVectorizer(max_features=1000, ngram_range=(1, 2))
X_dash = vectorizer.fit_transform(df_dashboards['texto_busca'])
X_cargos = vectorizer.transform(pdf_cargos['texto_perfil'])

# O KNN avalia todos os 15 dashboards e calcula o ranking matemático completo
num_dashboards = len(df_dashboards)
knn = NearestNeighbors(n_neighbors=num_dashboards, metric='cosine')
knn.fit(X_dash.toarray())
distancias_knn, indices_knn = knn.kneighbors(X_cargos.toarray())

print(f"✅ KNN treinado e executado com sucesso!")
print(f"Matriz de distâncias gerada: {len(pdf_cargos)} cargos x {num_dashboards} dashboards calculados.")

# COMMAND ----------
# MAGIC %md
# MAGIC ### 6. Aplicação das Regras de Negócio sobre o Ranking do KNN
# MAGIC 
# MAGIC 1. **Ranking Base:** O KNN fornece a ordem decrescente de relevância (menor distância de cosseno).
# MAGIC 2. **Regra de Liderança / Gestão:** Diretores, Gerentes, Supervisores e Coordenadores precisam ter visão financeira (`Estado de Resultados`, `Finanças` ou `OPEX`). Se o KNN não tiver colocado um dashboard financeiro nos primeiros lugares, o melhor dash financeiro é promovido para a vaga de liderança.
# MAGIC 3. **Sem Duplicatas:** Cada slot recebe um relatório exclusivo com sua distância matemática real.

# COMMAND ----------
FALLBACK_DEFAULTS = ['dna_de_vendas', 'otif_e_fill_rate', 'painel_logistico', 'estado_de_resultados']
GRUPOS_LIDERANCA = {'DIRETIVO', 'PRIMER EJECUTIVO', 'SEGUNDO EJECUTIVO', 'SUPERVISORIO', '1º SUPERVISÓRIO'}
DASHBOARDS_FINANCEIROS = {'estado_de_resultados', 'financas_db', 'opex_custos_operacionais'}

def eh_lideranca(cargo, grupo):
    texto = f"{str(cargo).upper()} {str(grupo).upper()}"
    termos = ['GERENTE', 'DIRETOR', 'SUPERVISOR', 'COORDENADOR', 'HEAD', 'LEADER']
    return any(t in texto for t in termos) or grupo in GRUPOS_LIDERANCA

cargos_resultado = []

for i, row in pdf_cargos.iterrows():
    c_cargo = row['CARGO']
    c_grupo = row['GRUPO_CARGO']
    
    # Ranking completo calculado pelo KNN para este cargo
    indices_ranking = indices_knn[i]
    dists_ranking = distancias_knn[i]
    
    slots_cods = []
    slots_dists = []
    
    # 1. Se for Liderança, garante presença do melhor dashboard financeiro segundo o KNN
    if eh_lideranca(c_cargo, c_grupo):
        for idx_k, dist_k in zip(indices_ranking, dists_ranking):
            cod_cand = df_dashboards.iloc[idx_k]['cod']
            if cod_cand in DASHBOARDS_FINANCEIROS:
                slots_cods.append(cod_cand)
                slots_dists.append(round(float(dist_k), 4))
                break
    
    # 2. Preenche os slots restantes com o ranking natural do KNN
    for idx_k, dist_k in zip(indices_ranking, dists_ranking):
        cod_cand = df_dashboards.iloc[idx_k]['cod']
        if cod_cand not in slots_cods:
            slots_cods.append(cod_cand)
            slots_dists.append(round(float(dist_k), 4))
        if len(slots_cods) >= MAX_SLOTS:
            break
            
    # 3. Fallback defensivo de segurança caso faltem slots
    for fb_cod in FALLBACK_DEFAULTS:
        if len(slots_cods) >= MAX_SLOTS:
            break
        if fb_cod not in slots_cods:
            slots_cods.append(fb_cod)
            slots_dists.append(0.50)
            
    # Seleção dos 4 dashboards finais
    d1 = DASH_BY_COD[slots_cods[0]]
    d2 = DASH_BY_COD[slots_cods[1]]
    d3 = DASH_BY_COD[slots_cods[2]]
    d4 = DASH_BY_COD[slots_cods[3]]
    
    cargos_resultado.append({
        "CARGO": c_cargo,
        "RELATORIO_1": d1['nome'],
        "ESPACO_1": d1['espaco'],
        "COD_1": d1['cod'],
        "DISTANCIA_1": slots_dists[0],
        "RELATORIO_2": d2['nome'],
        "ESPACO_2": d2['espaco'],
        "COD_2": d2['cod'],
        "DISTANCIA_2": slots_dists[1],
        "RELATORIO_3": d3['nome'],
        "ESPACO_3": d3['espaco'],
        "COD_3": d3['cod'],
        "DISTANCIA_3": slots_dists[2],
        "RELATORIO_4": d4['nome'],
        "ESPACO_4": d4['espaco'],
        "COD_4": d4['cod'],
        "DISTANCIA_4": slots_dists[3]
    })

df_sugestoes_por_cargo = pd.DataFrame(cargos_resultado)
print(f"✅ Sugestões geradas pelo KNN para {len(df_sugestoes_por_cargo)} cargos!")

# COMMAND ----------
# MAGIC %md
# MAGIC ### 7. Cruzamento com Colaboradores e Deduplicação Final

# COMMAND ----------
pdf_todos_colabs = spark.table("vw_colaboradores_qsr").toPandas()

# Ordena por data de atualização para priorizar registro mais recente
if 'DATA_ATUALIZACAO' in pdf_todos_colabs.columns:
    pdf_todos_colabs = pdf_todos_colabs.sort_values('DATA_ATUALIZACAO', ascending=False)

# Deduplica por ID_COLABORADOR e EMAIL
pdf_todos_colabs = pdf_todos_colabs.drop_duplicates(subset=['ID_COLABORADOR'], keep='first')
pdf_todos_colabs = pdf_todos_colabs.drop_duplicates(subset=['EMAIL'], keep='first')

# Merge com tabela de sugestões pelo CARGO
df_final = pdf_todos_colabs.merge(df_sugestoes_por_cargo, on='CARGO', how='left')

# Se algum colaborador não teve match de cargo, aplica fallback padrão
mask_sem_match = df_final['RELATORIO_1'].isna()
if mask_sem_match.sum() > 0:
    print(f"Colaboradores sem cargo mapeado (recebendo fallback): {mask_sem_match.sum()}")
    fb1 = DASH_BY_COD[FALLBACK_DEFAULTS[0]]
    fb2 = DASH_BY_COD[FALLBACK_DEFAULTS[1]]
    fb3 = DASH_BY_COD[FALLBACK_DEFAULTS[2]]
    fb4 = DASH_BY_COD[FALLBACK_DEFAULTS[3]]
    df_final.loc[mask_sem_match, 'RELATORIO_1'] = fb1['nome']
    df_final.loc[mask_sem_match, 'ESPACO_1'] = fb1['espaco']
    df_final.loc[mask_sem_match, 'COD_1'] = fb1['cod']
    df_final.loc[mask_sem_match, 'DISTANCIA_1'] = 0.50
    df_final.loc[mask_sem_match, 'RELATORIO_2'] = fb2['nome']
    df_final.loc[mask_sem_match, 'ESPACO_2'] = fb2['espaco']
    df_final.loc[mask_sem_match, 'COD_2'] = fb2['cod']
    df_final.loc[mask_sem_match, 'DISTANCIA_2'] = 0.50
    df_final.loc[mask_sem_match, 'RELATORIO_3'] = fb3['nome']
    df_final.loc[mask_sem_match, 'ESPACO_3'] = fb3['espaco']
    df_final.loc[mask_sem_match, 'COD_3'] = fb3['cod']
    df_final.loc[mask_sem_match, 'DISTANCIA_3'] = 0.50
    df_final.loc[mask_sem_match, 'RELATORIO_4'] = fb4['nome']
    df_final.loc[mask_sem_match, 'ESPACO_4'] = fb4['espaco']
    df_final.loc[mask_sem_match, 'COD_4'] = fb4['cod']
    df_final.loc[mask_sem_match, 'DISTANCIA_4'] = 0.50

# Metadados de auditoria
df_final['DT_ULTIMA_ATUALIZACAO'] = datetime.utcnow()

# Seleção e ordenação das colunas finais
cols_finais = [
    'ID_COLABORADOR', 'EMAIL', 'NOME_COLABORADOR', 'CARGO',
    'RELATORIO_1', 'ESPACO_1', 'COD_1', 'DISTANCIA_1',
    'RELATORIO_2', 'ESPACO_2', 'COD_2', 'DISTANCIA_2',
    'RELATORIO_3', 'ESPACO_3', 'COD_3', 'DISTANCIA_3',
    'RELATORIO_4', 'ESPACO_4', 'COD_4', 'DISTANCIA_4',
    'DT_ULTIMA_ATUALIZACAO'
]
df_final = df_final[cols_finais].drop_duplicates(subset=['EMAIL'])

print(f"Total de colaboradores BQ processados e enriquecidos: {len(df_final)}")

# COMMAND ----------
# MAGIC %md
# MAGIC ### 8. Gravação na Tabela Delta do Unity Catalog
# MAGIC 
# MAGIC Destino: `cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr`

# COMMAND ----------
sdf_final = spark.createDataFrame(df_final)

(
    sdf_final.write
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(TABELA_DESTINO)
)

print(f"✅ Tabela Delta '{TABELA_DESTINO}' atualizada com sucesso!")
print(f"Registros gravados: {len(df_final)}")

# COMMAND ----------
# MAGIC %md
# MAGIC ### 9. Otimização e Auditoria dos Resultados

# COMMAND ----------
spark.sql(f"OPTIMIZE {TABELA_DESTINO}")

print("\n--- AMOSTRA DAS SUGESTÕES GERADAS ---")
display(spark.table(TABELA_DESTINO).select("EMAIL", "CARGO", "RELATORIO_1", "RELATORIO_2", "RELATORIO_3", "RELATORIO_4").limit(10))

print("\n--- TOP DASHBOARDS RECOMENDADOS (SLOT 1) ---")
display(spark.table(TABELA_DESTINO).groupBy("RELATORIO_1").count().orderBy("count", ascending=False))

# COMMAND ----------
# MAGIC %md
# MAGIC ### 10. 🗺️ Visualização Gráfica do Hiperespaço (Redução PCA de 1.000 Dimensões para 2D)
# MAGIC 
# MAGIC O gráfico abaixo projeta a matemática do modelo:
# MAGIC - Cada ponto representa um **Dashboard** posicionado conforme suas palavras-chave.
# MAGIC - Os **Cargos** são plotados no mesmo mapa com base na descrição semântica gerada.
# MAGIC - É possível ver claramente a formação dos *clusters* (Logística, Finanças, Comercial, Supply Chain, Marketing) e por que o KNN escolhe os vizinhos mais próximos de cada colaborador.

# COMMAND ----------
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt

# Reduz as 1.000 dimensões do TF-IDF para 2 dimensões (X e Y)
pca = PCA(n_components=2, random_state=42)
coords_dash_2d = pca.fit_transform(X_dash.toarray())
coords_cargos_2d = pca.transform(X_cargos.toarray())

plt.figure(figsize=(12, 8))
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')

# Plota os 15 Dashboards
cores_areas = {
    'Logística': '#1f77b4',
    'Comercial': '#2ca02c',
    'Supply Chain': '#9467bd',
    'Finanças': '#ff7f0e',
    'Marketing': '#e377c2'
}

for i, row in df_dashboards.iterrows():
    c_x, c_y = coords_dash_2d[i]
    cor = cores_areas.get(row['espaco'], '#7f7f7f')
    plt.scatter(c_x, c_y, color=cor, s=150, alpha=0.9, edgecolors='black', linewidth=1.5, zorder=3)
    plt.annotate(
        row['nome'],
        (c_x, c_y),
        textcoords="offset points",
        xytext=(0, 10),
        ha='center',
        fontsize=9,
        fontweight='bold',
        color='#1e293b'
    )

# Plota uma amostra dos Cargos da BQ
amostra_indices = range(min(15, len(pdf_cargos)))
for idx in amostra_indices:
    u_x, u_y = coords_cargos_2d[idx]
    plt.scatter(u_x, u_y, color='#d62728', marker='*', s=180, alpha=0.8, zorder=2)
    plt.annotate(
        f"★ {pdf_cargos.iloc[idx]['CARGO']}",
        (u_x, u_y),
        textcoords="offset points",
        xytext=(0, -12),
        ha='center',
        fontsize=8,
        color='#842029'
    )

plt.title("Mapa Geométrico do Modelo KNN — Projeção PCA 2D (Bimbo QSR)", fontsize=14, fontweight='bold', pad=15)
plt.xlabel(f"Componente Principal 1 ({pca.explained_variance_ratio_[0]*100:.1f}% da variância)", fontsize=11)
plt.ylabel(f"Componente Principal 2 ({pca.explained_variance_ratio_[1]*100:.1f}% da variância)", fontsize=11)
plt.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()
plt.show()

