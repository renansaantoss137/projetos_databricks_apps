# Databricks notebook source
# MAGIC %md
# MAGIC # Sugestão de Dashboards Bimbo QSR via KNN + Regras de Negócio
# MAGIC 
# MAGIC Este notebook gera as recomendações personalizadas de dashboards para os colaboradores da **Bimbo QSR**,
# MAGIC utilizando uma abordagem híbrida de **Machine Learning (K-Nearest Neighbors / NLP)** combinada com
# MAGIC **regras de negócio por família de cargos**.
# MAGIC 
# MAGIC - **Tabela Origem**: `cat_dnabb_dv.grobbjrnl_cz.colaboradores`
# MAGIC - **Tabela Destino**: `cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr`

# COMMAND ----------

import re
import unicodedata
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from pyspark.sql import functions as F

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Catálogo dos 13 Dashboards Oficiais Bimbo QSR com Enriquecimento Semântico

# COMMAND ----------

DASHBOARDS_QSR = [
    {
        "cod": "painel_logistico",
        "nome": "Painel Logístico",
        "espaco": "Logística",
        "tags": "logistica transporte entregas rotas rastreamento frota custos frete distribuicao viagens motorista expedicao veiculos cdva"
    },
    {
        "cod": "rentabilidade",
        "nome": "Rentabilidade",
        "espaco": "Logística",
        "tags": "rentabilidade custos financeiros margem transporte frete rota eficiencia operacional custo unitario analise financeira logistica"
    },
    {
        "cod": "painel_de_projetos",
        "nome": "Painel de Projetos",
        "espaco": "Logística",
        "tags": "projetos gestao cronograma entregas melhoria continua kpi plano de acao capex expansao transformacao engenharia"
    },
    {
        "cod": "painel_de_precos_equipes",
        "nome": "Painel de Preços Equipes",
        "espaco": "Logística",
        "tags": "precos equipes negociacao tabelas frete prestadores contratos fornecedores valores custo logistico transportadoras"
    },
    {
        "cod": "painel_de_performance",
        "nome": "Painel de Performance",
        "espaco": "Logística",
        "tags": "performance operacional produtividade kpi tempo nivel de servico sla eficiencia operacao cd fabril expedicao"
    },
    {
        "cod": "painel_de_precos",
        "nome": "Painel de Preços",
        "espaco": "Logística",
        "tags": "precos frete tabela tarifaria variacao combustivel custo por km rota custo frete cotacao"
    },
    {
        "cod": "painel_de_price_protocol",
        "nome": "Painel de Price Protocol",
        "espaco": "Logística",
        "tags": "price protocol protocolo precos contratos regras tarifarias acordos comerciais compliance fiscal reajuste"
    },
    {
        "cod": "logistica_ct_e",
        "nome": "Logística CT-e",
        "espaco": "Logística",
        "tags": "cte conhecimento transporte eletronico fiscal tributario auditoria notas frete manifesto sefaz faturamento dacte"
    },
    {
        "cod": "otif_e_fill_rate",
        "nome": "OTIF e Fill Rate",
        "espaco": "Logística",
        "tags": "otif fill rate on time in full atendimento pedidos cortes faturamento nivel de servico pontualidade ruptura cliente pedidos entregas"
    },
    {
        "cod": "dna_de_vendas",
        "nome": "DNA de Vendas",
        "espaco": "Comercial",
        "tags": "vendas receita faturamento volume clientes canais comercial metas pedidos preco medio positivação trade distribuidores franquias qsr"
    },
    {
        "cod": "supply_chain",
        "nome": "Supply Chain",
        "espaco": "Supply Chain",
        "tags": "supply chain cadeia suprimentos demanda planejamento forecast sop estoque giro materias primas compras fornecedores producao abastecimento"
    },
    {
        "cod": "estado_de_resultados",
        "nome": "Estado de Resultados",
        "espaco": "Finanças",
        "tags": "estado de resultados dre pl resultado contabil financeiro despesas receita liquida ebitda margem orcamento forecast tesouraria controladoria"
    },
    {
        "cod": "performance_de_distribuidores",
        "nome": "Performance de Distribuidores",
        "espaco": "Marketing",
        "tags": "distribuidores performance marketing trade ponto de venda campanhas sell in sell out market share volume canal cobertura franquias"
    }
]

df_dashboards = pd.DataFrame(DASHBOARDS_QSR)
display(df_dashboards[['cod', 'nome', 'espaco']])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Leitura da Base de Colaboradores (Bimbo QSR e Corporativo)

# COMMAND ----------

# Leitura da tabela gerenciada de colaboradores
df_colab_spark = spark.table("cat_dnabb_dv.grobbjrnl_cz.colaboradores")

# Filtrar colaboradores ativos ou com data de rescisão nula
# Focar em colaboradores da Bimbo QSR (unidades BQB/QSR) e posições corporativas
df_colab_filtered = df_colab_spark.filter(
    (F.col("SITUACAO") == "ATIVO") | (F.col("DATA_RECISAO").isNull())
).select(
    F.col("ID_COLABORADOR"),
    F.col("NOME_COLABORADOR"),
    F.col("COLAB_EMAIL").alias("EMAIL"),
    F.col("CARGO"),
    F.col("UNIDADE"),
    F.col("AREA_NEGOCIO"),
    F.col("CENTRO_CUSTO"),
    F.col("CENTRO_CUSTO_DETALHE")
).filter(
    F.col("EMAIL").isNotNull() & (F.length(F.trim(F.col("EMAIL"))) > 0)
)

pdf_colab = df_colab_filtered.toPandas()
print(f"Total de colaboradores lidos: {len(pdf_colab)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Preparação do Modelo KNN com Vetorização Semântica (TF-IDF)

# COMMAND ----------

def normalizar_texto(texto):
    if not texto or pd.isna(texto):
        return ""
    texto = str(texto).lower()
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    texto = re.sub(r'[^a-z0-9\s]', ' ', texto)
    return ' '.join(texto.split())

# Montar corpus de dashboards
df_dashboards['texto_busca'] = df_dashboards.apply(
    lambda r: f"{r['nome']} {r['espaco']} {r['tags']}", axis=1
).apply(normalizar_texto)

# Montar corpus de colaboradores
pdf_colab['texto_perfil'] = pdf_colab.apply(
    lambda r: f"{r['CARGO']} {r['CENTRO_CUSTO']} {r['CENTRO_CUSTO_DETALHE']} {r['UNIDADE']}", axis=1
).apply(normalizar_texto)

# Vetorização TF-IDF combinando termos do negócio
vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2))
X_dash = vectorizer.fit_transform(df_dashboards['texto_busca'])
X_colab = vectorizer.transform(pdf_colab['texto_perfil'])

# Modelo KNN (k=4 com métrica de cosseno)
knn = NearestNeighbors(n_neighbors=4, metric='cosine')
knn.fit(X_dash.toarray())

# Obter distâncias e índices dos 4 dashboards mais próximos para cada colaborador
distancias, indices = knn.kneighbors(X_colab.toarray())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Aplicação de Regras de Negócio e Refinamento para Perfis Estratégicos

# COMMAND ----------

# Regras de Negócio de Fallback / Âncora para cargos executivos ou transversais
DASHBOARDS_EXECUTIVOS = ["dna_de_vendas", "otif_e_fill_rate", "painel_logistico", "estado_de_resultados"]
DASH_BY_COD = {d['cod']: d for d in DASHBOARDS_QSR}

def eh_perfil_cross_ou_ti(cargo, centro_custo):
    texto = f"{cargo} {centro_custo}".upper()
    termos_cross = [
        "DADOS", "BI", "TI", "TRANSFORMA", "SISTEMAS", "GERENTE", "DIRETOR",
        "COORDENADOR", "ANALISTA DADOS", "PRODUTO", "GOVERNANCA"
    ]
    return any(t in texto for t in termos_cross)

rows_final = []
now_ts = datetime.utcnow()

for i, row in pdf_colab.iterrows():
    c_email = row['EMAIL'].strip().lower()
    c_cargo = row['CARGO']
    c_id = row['ID_COLABORADOR']
    c_cc = str(row['CENTRO_CUSTO'])

    idx_sugeridos = indices[i]
    dist_sugeridos = distancias[i]

    # Se for perfil corporativo / dados / liderança com baixa especificidade
    if eh_perfil_cross_ou_ti(c_cargo, c_cc) and min(dist_sugeridos) > 0.85:
        # Atribuir os 4 dashboards executivos prioritários da BQ
        selected_cods = DASHBOARDS_EXECUTIVOS
        selected_dists = [0.0, 0.05, 0.10, 0.15]
    else:
        selected_cods = [df_dashboards.iloc[idx]['cod'] for idx in idx_sugeridos]
        selected_dists = [round(float(d), 4) for d in dist_sugeridos]

    d1 = DASH_BY_COD[selected_cods[0]]
    d2 = DASH_BY_COD[selected_cods[1]]
    d3 = DASH_BY_COD[selected_cods[2]]
    d4 = DASH_BY_COD[selected_cods[3]]

    rows_final.append({
        "ID_COLABORADOR": int(c_id) if str(c_id).isdigit() else 0,
        "EMAIL": c_email,
        "CARGO": c_cargo,
        "RELATORIO_1": d1['nome'],
        "ESPACO_1": d1['espaco'],
        "COD_1": d1['cod'],
        "DISTANCIA_1": selected_dists[0],
        "RELATORIO_2": d2['nome'],
        "ESPACO_2": d2['espaco'],
        "COD_2": d2['cod'],
        "DISTANCIA_2": selected_dists[1],
        "RELATORIO_3": d3['nome'],
        "ESPACO_3": d3['espaco'],
        "COD_3": d3['cod'],
        "DISTANCIA_3": selected_dists[2],
        "RELATORIO_4": d4['nome'],
        "ESPACO_4": d4['espaco'],
        "COD_4": d4['cod'],
        "DISTANCIA_4": selected_dists[3],
        "DT_ULTIMA_ATUALIZACAO": now_ts
    })

df_final_pandas = pd.DataFrame(rows_final)
# Remover eventuais duplicatas de email mantendo a primeira ocorrencia
df_final_pandas = df_final_pandas.drop_duplicates(subset=['EMAIL'])
print(f"Total de recomendações geradas: {len(df_final_pandas)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Gravação da Tabela Delta no Unity Catalog (`cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr`)

# COMMAND ----------

# Converter para Spark DataFrame
spark_df_final = spark.createDataFrame(df_final_pandas)

# Criar ou substituir a tabela Delta gerenciada
table_target = "cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr"

spark_df_final.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(table_target)

# Adicionar comentário/descrição na tabela
spark.sql(f"COMMENT ON TABLE {table_target} IS 'Sugestões de dashboards Bimbo QSR por colaborador geradas via KNN + Regras de Negócio'")

print(f"Tabela {table_target} gravada com sucesso com {spark_df_final.count()} registros!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Validação das Sugestões Geradas

# COMMAND ----------

display(
    spark.table(table_target)
    .filter(F.col("EMAIL").like("%renan.ferreira%") | F.col("CARGO").like("%LOGISTICA%") | F.col("CARGO").like("%VENDAS%"))
    .limit(10)
)
