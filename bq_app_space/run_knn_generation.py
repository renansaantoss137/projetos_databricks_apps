import os
import re
import csv
import unicodedata
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from databricks.sdk import WorkspaceClient

print("1. Conectando ao Databricks via WorkspaceClient...")
w = WorkspaceClient()
warehouses = list(w.warehouses.list())
warehouse_id = warehouses[0].id if warehouses else None
print(f"Utilizando Warehouse ID: {warehouse_id}")

print("2. Consultando colaboradores ativos da Bimbo QSR em cat_dnabb_dv.grobbjrnl_cz.colaboradores...")
sql_colab = """
SELECT 
    ID_COLABORADOR,
    NOME_COLABORADOR,
    TRIM(LOWER(COLAB_EMAIL)) as EMAIL,
    CARGO,
    UNIDADE,
    AREA_NEGOCIO,
    CENTRO_CUSTO,
    CENTRO_CUSTO_DETALHE
FROM cat_dnabb_dv.grobbjrnl_cz.colaboradores
WHERE (SITUACAO = 'ATIVO' OR DATA_RECISAO IS NULL)
  AND COLAB_EMAIL IS NOT NULL 
  AND LENGTH(TRIM(COLAB_EMAIL)) > 0
  AND (
      LOWER(UNIDADE) LIKE '%bq%' 
      OR LOWER(UNIDADE) LIKE '%qsr%' 
      OR LOWER(CENTRO_CUSTO) LIKE '%bq%'
      OR LOWER(COLAB_EMAIL) LIKE '%renan.ferreira%'
  )
"""

stmt = w.statement_execution.execute_statement(
    statement=sql_colab,
    warehouse_id=warehouse_id,
    wait_timeout="45s"
)
cols = [c.name for c in stmt.manifest.schema.columns]
rows = stmt.result.data_array
print(f"Total de colaboradores QSR encontrados: {len(rows)}")

pdf_colab = pd.DataFrame(rows, columns=cols)

# Os 13 Dashboards oficiais da Bimbo QSR
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
        "tags": "vendas receita faturamento volume clientes canais comercial metas pedidos preco medio positivacao trade distribuidores franquias qsr"
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
        "cod": "financas_db",
        "nome": "Finanças",
        "espaco": "Finanças",
        "tags": "financas gestao financeira fluxo de caixa tesouraria receitas balanco controladoria planejamento financeiro custos contas a pagar receber"
    },
    {
        "cod": "opex_custos_operacionais",
        "nome": "OPEX (Custos Operacionais)",
        "espaco": "Finanças",
        "tags": "opex custos operacionais despesas orcamento orcado realizado gestao de custos gastos centros de custo operacao despesas administrativas"
    },
    {
        "cod": "performance_de_distribuidores",
        "nome": "Performance de Distribuidores",
        "espaco": "Marketing",
        "tags": "distribuidores performance marketing trade ponto de venda campanhas sell in sell out market share volume canal cobertura franquias"
    }
]

df_dashboards = pd.DataFrame(DASHBOARDS_QSR)

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

pdf_colab['texto_perfil'] = pdf_colab.apply(
    lambda r: f"{r['CARGO']} {r['CENTRO_CUSTO']} {r['CENTRO_CUSTO_DETALHE']} {r['UNIDADE']}", axis=1
).apply(normalizar_texto)

print("3. Executando Vetorização TF-IDF e Modelo KNN...")
vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2))
X_dash = vectorizer.fit_transform(df_dashboards['texto_busca'])
X_colab = vectorizer.transform(pdf_colab['texto_perfil'])

knn = NearestNeighbors(n_neighbors=4, metric='cosine')
knn.fit(X_dash.toarray())
distancias, indices = knn.kneighbors(X_colab.toarray())

DASHBOARDS_EXECUTIVOS = ['dna_de_vendas', 'otif_e_fill_rate', 'painel_logistico', 'estado_de_resultados']
DASH_BY_COD = {d['cod']: d for d in DASHBOARDS_QSR}

def eh_perfil_cross_ou_ti(cargo, centro_custo):
    texto = f"{cargo} {centro_custo}".upper()
    termos_cross = [
        "DADOS", "BI", "TI", "TRANSFORMA", "SISTEMAS", "GERENTE", "DIRETOR",
        "COORDENADOR", "ANALISTA DADOS", "PRODUTO", "GOVERNANCA"
    ]
    return any(t in texto for t in termos_cross)

rows_final = []

for i, row in pdf_colab.iterrows():
    c_email = row['EMAIL'].strip().lower()
    c_cargo = row['CARGO']
    c_id = row['ID_COLABORADOR']
    c_cc = str(row['CENTRO_CUSTO'])

    idx_sugeridos = indices[i]
    dist_sugeridos = distancias[i]

    if eh_perfil_cross_ou_ti(c_cargo, c_cc) and min(dist_sugeridos) > 0.85:
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
        "DISTANCIA_4": selected_dists[3]
    })

df_final = pd.DataFrame(rows_final).drop_duplicates(subset=['EMAIL'])
print(f"4. Recomendações geradas com sucesso: {len(df_final)} colaboradores!")

# Salvar arquivo CSV local para o app
csv_path = os.path.join(os.path.dirname(__file__), 'src', 'app', 'sugestao_knn.csv')
df_final.to_csv(csv_path, index=False, encoding='utf-8')
print(f"5. Arquivo local atualizado: {csv_path}")

# Inspecionar resultado para renan.ferreira
u = df_final[df_final['EMAIL'].str.contains('renan.ferreira')]
if not u.empty:
    print("\n--- TESTE DO SEU USUÁRIO (renan.ferreira@grupobimbo.com) ---")
    rec = u.to_dict('records')[0]
    print(f"Cargo: {rec['CARGO']}")
    print(f"1. {rec['RELATORIO_1']} ({rec['ESPACO_1']}) [dist: {rec['DISTANCIA_1']}]")
    print(f"2. {rec['RELATORIO_2']} ({rec['ESPACO_2']}) [dist: {rec['DISTANCIA_2']}]")
    print(f"3. {rec['RELATORIO_3']} ({rec['ESPACO_3']}) [dist: {rec['DISTANCIA_3']}]")
    print(f"4. {rec['RELATORIO_4']} ({rec['ESPACO_4']}) [dist: {rec['DISTANCIA_4']}]")

# 6. Criar tabela Delta no Databricks Unity Catalog cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr
print("\n6. Criando tabela Delta no Unity Catalog: cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr...")
create_table_sql = """
CREATE TABLE IF NOT EXISTS cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr (
    EMAIL STRING,
    CARGO STRING,
    RELATORIO_1 STRING,
    ESPACO_1 STRING,
    COD_1 STRING,
    DISTANCIA_1 DOUBLE,
    RELATORIO_2 STRING,
    ESPACO_2 STRING,
    COD_2 STRING,
    DISTANCIA_2 DOUBLE,
    RELATORIO_3 STRING,
    ESPACO_3 STRING,
    COD_3 STRING,
    DISTANCIA_3 DOUBLE,
    RELATORIO_4 STRING,
    ESPACO_4 STRING,
    COD_4 STRING,
    DISTANCIA_4 DOUBLE,
    DT_ULTIMA_ATUALIZACAO TIMESTAMP
) USING DELTA
COMMENT 'Sugestões de dashboards Bimbo QSR por colaborador geradas via KNN + Regras de Negócio';
"""

w.statement_execution.execute_statement(
    statement=create_table_sql,
    warehouse_id=warehouse_id,
    wait_timeout="30s"
)
print("Tabela criada/validada no Unity Catalog!")

# Inserir em lotes
print("Inserindo dados na tabela Delta...")
# Truncar antes de inserir a nova versão
w.statement_execution.execute_statement(
    statement="TRUNCATE TABLE cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr",
    warehouse_id=warehouse_id,
    wait_timeout="30s"
)

batch_size = 200
records = df_final.to_dict('records')
total_records = len(records)
now_iso = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

for b_start in range(0, total_records, batch_size):
    batch = records[b_start:b_start + batch_size]
    values_list = []
    for r in batch:
        def escape_sql(val):
            return str(val).replace("'", "''")
        values_list.append(
            f"('{escape_sql(r['EMAIL'])}', '{escape_sql(r['CARGO'])}', "
            f"'{escape_sql(r['RELATORIO_1'])}', '{escape_sql(r['ESPACO_1'])}', '{escape_sql(r['COD_1'])}', {r['DISTANCIA_1']}, "
            f"'{escape_sql(r['RELATORIO_2'])}', '{escape_sql(r['ESPACO_2'])}', '{escape_sql(r['COD_2'])}', {r['DISTANCIA_2']}, "
            f"'{escape_sql(r['RELATORIO_3'])}', '{escape_sql(r['ESPACO_3'])}', '{escape_sql(r['COD_3'])}', {r['DISTANCIA_3']}, "
            f"'{escape_sql(r['RELATORIO_4'])}', '{escape_sql(r['ESPACO_4'])}', '{escape_sql(r['COD_4'])}', {r['DISTANCIA_4']}, "
            f"TIMESTAMP'{now_iso}')"
        )
    insert_sql = f"""
    INSERT INTO cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr VALUES
    {', '.join(values_list)}
    """
    w.statement_execution.execute_statement(
        statement=insert_sql,
        warehouse_id=warehouse_id,
        wait_timeout="30s"
    )
    print(f"  Inseridos {min(b_start + batch_size, total_records)}/{total_records} registros...")

print("\nProcesso concluído com 100% de sucesso!")
