# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,ETL: Unity Catalog → Lakebase (compras-360)
# MAGIC %md
# MAGIC # ETL: Oracle Cloud → Lakebase PostgreSQL (Blue-Green)
# MAGIC
# MAGIC **App**: compras-360  
# MAGIC **Projeto Lakebase**: `compras-360`  
# MAGIC **Host**: `ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net`
# MAGIC
# MAGIC Este notebook lê **diretamente das tabelas Oracle Cloud** (`cat_ocloud_r5_dv.rg5glofsn_cz`) e carrega os dados
# MAGIC no Lakebase PostgreSQL para consumo direto pelo app via psycopg2.
# MAGIC
# MAGIC **Independência**: Nenhuma dependência de views intermediárias do Unity Catalog (`compras_sz` ou `grobbcompr_cz`).  
# MAGIC **Zero-downtime**: Padrão blue-green — carrega em schema staging, valida, e faz swap atômico.  
# MAGIC **Lookups**: Fornecedores e compradores lidos diretamente de CSVs no workspace.
# MAGIC
# MAGIC **Agendar**: Execute como Job diário.
# MAGIC
# MAGIC **Requisitos**: Cluster com acesso ao catálogo `cat_ocloud_r5_dv`.

# COMMAND ----------

# DBTITLE 1,1. Configuração Lakebase
import os
import uuid
import time
import psycopg2
from psycopg2 import sql
import io
from io import StringIO
import pandas as pd
from databricks.sdk import WorkspaceClient

# ── Configuração Lakebase ──
PG_HOST = "ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net"
PG_DATABASE = "databricks_postgres"
PG_PORT = 5432

# Schemas (blue-green)
SCHEMA_PROD = "compras"
SCHEMA_STAGING = "compras_staging"

# ── Resolução Dinâmica de Diretórios (Zero Hardcode) ──
def _detect_script_dir():
    """Detecta dinamicamente a pasta onde o notebook/script está sendo executado."""
    # 1. Contexto oficial do Databricks Notebook (dbutils)
    try:
        import IPython
        ipython = IPython.get_ipython()
        if ipython and "dbutils" in ipython.user_ns:
            dbutils = ipython.user_ns["dbutils"]
            nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
            if nb_path:
                ws_path = nb_path if nb_path.startswith("/Workspace") else f"/Workspace{nb_path}"
                dir_path = os.path.dirname(ws_path)
                if os.path.exists(dir_path):
                    return dir_path
    except Exception:
        pass

    # 2. Padrão Python __file__ (Databricks Repos / Files / Script CLI)
    try:
        if "__file__" in globals() and __file__:
            dir_path = os.path.dirname(os.path.abspath(__file__))
            if os.path.exists(dir_path):
                return dir_path
    except Exception:
        pass

    # 3. Fallback para diretório de trabalho atual
    return os.getcwd()

_SCRIPT_DIR = _detect_script_dir()

def _find_repo_root(start_dir):
    """Sobe na hierarquia de pastas para encontrar a raiz do repositório (marcada por databricks.yml, docs ou src)."""
    cur = os.path.abspath(start_dir)
    for _ in range(5):
        if any(os.path.exists(os.path.join(cur, marker)) for marker in ["databricks.yml", "docs", "src", "resources"]):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return start_dir

_REPO_ROOT = _find_repo_root(_SCRIPT_DIR)

def _find_sql_dir():
    """Encontra o diretório onde residem as views SQL (priorizando docs/sql do repositório)."""
    candidates = [
        os.path.join(_REPO_ROOT, "docs", "sql"),
        os.path.join(_SCRIPT_DIR, "..", "..", "docs", "sql"),
        os.path.join(_SCRIPT_DIR, "docs", "sql"),
        os.path.join(_REPO_ROOT, "sql"),
        os.path.join(_SCRIPT_DIR, "sql"),
        "/Volumes/cat_dnabb_dv/grobbcompr_cz/compras_360/sql",
        "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/prod/files/docs/sql",
        "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/prod/files/sql",
        "/Workspace/Shared/Databricks_Apps/BQ-Apps/compras_360/sql"
    ]
    for c in candidates:
        c_norm = os.path.normpath(c)
        if os.path.exists(c_norm) and os.path.exists(os.path.join(c_norm, "vw_ordens_compra.sql")):
            return c_norm
    for c in candidates:
        c_norm = os.path.normpath(c)
        if os.path.exists(c_norm):
            return c_norm
    return os.path.normpath(candidates[0])

SQL_DIR = _find_sql_dir()

def _resolve_csv(filename):
    """Resolve o caminho de um arquivo CSV buscando no Volume do Unity Catalog e nas pastas locais."""
    candidates = [
        # 1. Volume Unity Catalog (Produção Bimbo)
        os.path.join("/Volumes/cat_dnabb_dv/grobbcompr_cz/compras_360", filename),
        # 2. Mesma pasta do script (src/dados/)
        os.path.join(_SCRIPT_DIR, filename),
        # 3. src/dados relativo à raiz
        os.path.join(_REPO_ROOT, "src", "dados", filename),
        # 4. Raiz do repositório
        os.path.join(_REPO_ROOT, filename),
        # 5. Caminhos conhecidos no Workspace
        os.path.join("/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/prod/files/src/dados", filename),
        os.path.join("/Workspace/Shared/Databricks_Apps/BQ-Apps/compras_360", filename)
    ]
    for p in candidates:
        p_norm = os.path.normpath(p)
        if os.path.exists(p_norm):
            return p_norm
    return os.path.normpath(candidates[0])

CSV_FORNECEDORES_ESP = _resolve_csv("fornecedores_especiais.csv")
CSV_FORNECEDORES_NN = _resolve_csv("fornecedores_nao_negociaiveis.csv")
CSV_FORNECEDORES_SEM_OC = _resolve_csv("fornecedores_sem_oc.csv")
CSV_COMPRADORES = _resolve_csv("COMPRADORES_FUNCIONAIS(BASE_COMPRAS).csv")

def load_sql_view(view_name):
    """Carrega o conteúdo do arquivo SQL de uma view com busca resiliente de caminhos."""
    candidates = [
        os.path.join(SQL_DIR, f"{view_name}.sql"),
        os.path.join(_REPO_ROOT, "docs", "sql", f"{view_name}.sql"),
        os.path.join(_SCRIPT_DIR, "..", "..", "docs", "sql", f"{view_name}.sql"),
        os.path.join(_REPO_ROOT, "sql", f"{view_name}.sql"),
        os.path.join(_SCRIPT_DIR, "sql", f"{view_name}.sql"),
        f"/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/prod/files/docs/sql/{view_name}.sql",
        f"/Volumes/cat_dnabb_dv/grobbcompr_cz/compras_360/sql/{view_name}.sql",
        f"/Workspace/Shared/Databricks_Apps/BQ-Apps/compras_360/sql/{view_name}.sql"
    ]
    for p in candidates:
        p_norm = os.path.normpath(p)
        if os.path.exists(p_norm):
            with open(p_norm, "r", encoding="utf-8") as f:
                content = f.read()
                import re
                content = re.sub(r'^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+[^\s]+\s+AS\s*', '', content, flags=re.IGNORECASE)
                return content
    raise FileNotFoundError(
        f"Arquivo SQL '{view_name}.sql' não foi encontrado.\n"
        f"Tentativas verificadas:\n" + "\n".join(f" - {os.path.normpath(p)}" for p in candidates)
    )

# Service principal do notebook (o user que roda o job)
w = WorkspaceClient()

def get_pg_connection():
    """Gera credencial OAuth e conecta ao Lakebase."""
    cred = w.api_client.do("POST", "/api/2.0/postgres/credentials", body={
        "endpoint": "projects/compras-360/branches/production/endpoints/primary"
    })
    token = cred.get("token", "")
    
    # Pegar username do current user
    me = w.current_user.me()
    pg_user = me.user_name  # email do user
    
    conn = psycopg2.connect(
        host=PG_HOST,
        database=PG_DATABASE,
        user=pg_user,
        password=token,
        port=PG_PORT,
        sslmode="require"
    )
    conn.autocommit = True
    return conn

def bulk_load_to_pg(df_pandas, schema, table, conn):
    """Carrega DataFrame pandas no Lakebase via COPY (bulk insert)."""
    cur = conn.cursor()
    cur.execute(f"TRUNCATE TABLE {schema}.{table}")
    buffer = StringIO()
    df_pandas.to_csv(buffer, index=False, header=False, na_rep='\\N')
    buffer.seek(0)
    cur.copy_expert(f"COPY {schema}.{table} FROM STDIN WITH (FORMAT csv, NULL '\\N')", buffer)
    cur.close()
    return len(df_pandas)

print("✓ Configuração carregada com sucesso")
print(f"  Host: {PG_HOST}")
print(f"  Schema produção: {SCHEMA_PROD}")
print(f"  Schema staging: {SCHEMA_STAGING}")
print(f"  Diretório do script: {_SCRIPT_DIR}")
print(f"  Raiz do repositório: {_REPO_ROOT}")
print(f"  Diretório das SQL Views: {SQL_DIR}")
print(f"  CSV Fornecedores Especiais: {CSV_FORNECEDORES_ESP}")
print(f"  CSV Fornecedores Não Negociáveis: {CSV_FORNECEDORES_NN}")
print(f"  CSV Compradores Funcionais: {CSV_COMPRADORES}")

# COMMAND ----------

# DBTITLE 1,2. Criar schema e tabelas no Lakebase
conn = get_pg_connection()
cur = conn.cursor()

# Garantir que schema de produção existe (primeira execução)
cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_PROD}")

# Recriar schema staging limpo (blue-green: carrega aqui, depois faz swap)
cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_STAGING} CASCADE")
cur.execute(f"CREATE SCHEMA {SCHEMA_STAGING}")
print(f"✓ Schema '{SCHEMA_STAGING}' criado (limpo)")

# DDL das tabelas
DDL = {
    "notas_ri": """
    CREATE TABLE IF NOT EXISTS {schema}.notas_ri (
        invoice_id TEXT,
        invoice_line_id TEXT,
        numero_ri TEXT,
        nota_fiscal TEXT,
        serie TEXT,
        numero_oc TEXT,
        empresa TEXT,
        ds_item TEXT,
        codigo_item TEXT,
        descricao_item TEXT,
        item_type TEXT,
        categoria_item TEXT,
        categoria_codigo TEXT,
        macro_categoria TEXT,
        tipo_vendor TEXT,
        grupo_compras TEXT,
        centralizado TEXT,
        comprador TEXT,
        departamento_comprador TEXT,
        chave_oc_linha TEXT,
        linha_oc INTEGER,
        data_lancamento TEXT,
        dt_nota TEXT,
        dt_registro TEXT,
        data_vencimento TEXT,
        data_pagamento TEXT,
        ano_mes TEXT,
        dias_atraso DOUBLE PRECISION,
        oc_pos_fatura TEXT,
        urgente TEXT,
        valor_nota DOUBLE PRECISION,
        valor_nota_brl DOUBLE PRECISION,
        valor_liquido_brl DOUBLE PRECISION,
        icms DOUBLE PRECISION,
        pis DOUBLE PRECISION,
        cofins DOUBLE PRECISION,
        imposto_total DOUBLE PRECISION,
        moeda TEXT,
        taxa_cambio DOUBLE PRECISION,
        condicao_pgto TEXT,
        prazo_pgto INTEGER,
        pgto_x_valor DOUBLE PRECISION,
        saving_total DOUBLE PRECISION,
        saving_pct DOUBLE PRECISION,
        nome_fornecedor TEXT,
        numero_fornecedor TEXT,
        codigo_fornecedor_oracle TEXT,
        unidade TEXT,
        planta TEXT,
        centro_custo TEXT,
        conta_contabil TEXT,
        cond_pgto_ap DOUBLE PRECISION,
        faixa_prazo_pagamento TEXT,
        saving_total_ano DOUBLE PRECISION,
        saving_pct_ano DOUBLE PRECISION,
        preco_base_ano DOUBLE PRECISION,
        preco_anterior DOUBLE PRECISION,
        saving_unitario DOUBLE PRECISION,
        quantidade DOUBLE PRECISION,
        preco DOUBLE PRECISION,
        preco_brl DOUBLE PRECISION,
        preco_liquido DOUBLE PRECISION,
        valor_liquido DOUBLE PRECISION,
        numero_oc_original TEXT,
        status_pagamento TEXT,
        tipo_nf TEXT,
        is_fornecedor_especial TEXT,
        is_fornecedor_nao_negociavel TEXT,
        is_fornecedor_sem_oc TEXT,
        cnpj_bimbo TEXT
    )
    """,
    "ordens_compra": """
    CREATE TABLE IF NOT EXISTS {schema}.ordens_compra (
        numero_oc TEXT,
        numero_acordo TEXT,
        tipo TEXT,
        descricao TEXT,
        item_aquisicao TEXT,
        descricao_item TEXT,
        categoria_item TEXT,
        categoria_codigo TEXT,
        macro_categoria TEXT,
        grupo_compras_oc TEXT,
        descricao_linha TEXT,
        linha_oc INTEGER,
        chave_oc_linha TEXT,
        status_aprovacao TEXT,
        status_fechamento TEXT,
        empresa TEXT,
        org_desc TEXT,
        data_oc TEXT,
        dt_aprovacao TEXT,
        dt_fechamento TEXT,
        qtd_solicitada DOUBLE PRECISION,
        qtd DOUBLE PRECISION,
        qtd_faturada DOUBLE PRECISION,
        preco_unit DOUBLE PRECISION,
        taxa_cambio DOUBLE PRECISION,
        moeda TEXT,
        nome_fornecedor TEXT,
        numero_fornecedor TEXT,
        aprovador TEXT,
        usuario TEXT,
        nome_usuario TEXT,
        comprador TEXT,
        comprador_funcional TEXT,
        departamento_comprador TEXT,
        usuario_comprador TEXT,
        email_comprador TEXT,
        dt_promessa TEXT,
        dt_necessidade TEXT,
        oc_atrasada TEXT,
        dias_atraso_oc DOUBLE PRECISION,
        dias_aberto DOUBLE PRECISION,
        unidade TEXT,
        area TEXT,
        categoria_oc TEXT,
        nome_requisitante TEXT,
        departamento_requisitante TEXT,
        requisicao TEXT,
        fornecedor_especial TEXT,
        oc_sem_uso TEXT,
        centralizado TEXT,
        is_fornecedor_especial TEXT,
        is_fornecedor_nao_negociavel TEXT,
        is_fornecedor_sem_oc TEXT,
        valor_original_brl DOUBLE PRECISION,
        valor_utilizado_brl DOUBLE PRECISION,
        urgente TEXT,
        acordo_status TEXT,
        acordo_dt_criacao TEXT,
        acordo_data_inicial TEXT,
        acordo_data_final TEXT,
        acordo_valor_total DOUBLE PRECISION,
        acordo_valor_min_liberacao DOUBLE PRECISION,
        acordo_valor_liberado DOUBLE PRECISION,
        acordo_descricao TEXT,
        acordo_fob TEXT,
        acordo_condicao_frete TEXT,
        acordo_condicao_pgto TEXT
    )
    """,
    "fornecedores_especiais": """
    CREATE TABLE IF NOT EXISTS {schema}.fornecedores_especiais (
        cod_fornecedor_oracle TEXT PRIMARY KEY,
        nome_fornecedor_oracle TEXT,
        produto_servico TEXT,
        area TEXT,
        justificativa TEXT,
        data_registro TEXT
    )
    """,
    "fornecedores_nao_negociaveis": """
    CREATE TABLE IF NOT EXISTS {schema}.fornecedores_nao_negociaveis (
        cod_fornecedor_oracle TEXT PRIMARY KEY,
        nome_fornecedor_oracle TEXT,
        produto_servico TEXT,
        area TEXT,
        justificativa TEXT,
        data_registro TEXT
    )
    """,
    "fornecedores_sem_oc": """
    CREATE TABLE IF NOT EXISTS {schema}.fornecedores_sem_oc (
        cod_fornecedor_oracle TEXT PRIMARY KEY,
        nome_fornecedor_oracle TEXT,
        produto_servico TEXT,
        area TEXT,
        justificativa TEXT,
        data_registro TEXT
    )
    """,
    "compradores_funcionais": """
    CREATE TABLE IF NOT EXISTS {schema}.compradores_funcionais (
        usuario_oracle TEXT,
        id TEXT,
        comprador_funcional TEXT,
        email TEXT,
        area TEXT,
        unidade TEXT,
        operacao TEXT,
        obs TEXT
    )
    """,
    "colaboradores": """
    CREATE TABLE IF NOT EXISTS {schema}.colaboradores (
        matricula TEXT PRIMARY KEY,
        id_colaborador TEXT,
        nome_completo TEXT,
        email TEXT,
        area TEXT,
        diretoria TEXT,
        nm_unidade TEXT,
        nm_cargo TEXT
    )
    """,
    "requisicoes": """
    CREATE TABLE IF NOT EXISTS {schema}.requisicoes (
        empresa TEXT,
        req_id TEXT,
        requisicao TEXT,
        descricao_req TEXT,
        numero_oc TEXT,
        user_requisicao TEXT,
        requisitante TEXT,
        email_requisitante TEXT,
        departamento_requisitante TEXT,
        user_aprovador TEXT,
        nome_aprovador TEXT,
        comprador_sugerido TEXT,
        departamento_comprador TEXT,
        dt_criacao TEXT,
        dt_aprovacao TEXT,
        status TEXT,
        qtd_linhas INTEGER,
        valor_requisicao DOUBLE PRECISION,
        status_ordem TEXT
    )
    """,
    "acordos_compra": """
    CREATE TABLE IF NOT EXISTS {schema}.acordos_compra (
        numero_acordo TEXT,
        status TEXT,
        dt_criacao TEXT,
        dt_inicio TEXT,
        dt_fim TEXT,
        valor_total DOUBLE PRECISION,
        valor_liberado DOUBLE PRECISION,
        descricao TEXT,
        fornecedor TEXT,
        numero_fornecedor TEXT,
        comprador TEXT,
        usuario_comprador TEXT,
        departamento_comprador TEXT,
        empresa TEXT,
        dias_aberto DOUBLE PRECISION
    )
    """
}

for table_name, ddl in DDL.items():
    cur.execute(ddl.format(schema=SCHEMA_STAGING))
    print(f"✓ Tabela {SCHEMA_STAGING}.{table_name} criada")

cur.close()
conn.close()
print(f"\n✓ Estrutura staging pronta — produção ({SCHEMA_PROD}) intacta")

# COMMAND ----------

# DBTITLE 1,3. Carregar lookups (CSVs → Spark temp views + Lakebase staging)
# ══════════════════════════════════════════════════════════════════════════════
# LOOKUPS: Fornecedores Especiais, Não Negociáveis, Compradores Funcionais
# Fonte: CSVs no workspace (independente do Unity Catalog)
# Uso: temp views para JOINs nas queries principais + carga no Lakebase
# ══════════════════════════════════════════════════════════════════════════════

def load_lookup_csv(file_or_path, expected_cols, sep=";"):
    """Lê arquivos CSV de lookups com detecção resiliente de codificação (UTF-8 com BOM, latin1, etc.),
    tratamento dinâmico de cabeçalhos e limpeza de BOM/espaços."""
    encodings = ["utf-8-sig", "utf-8", "latin1", "cp1252"]
    for enc in encodings:
        try:
            if isinstance(file_or_path, bytes):
                raw = file_or_path
            else:
                with open(file_or_path, "rb") as f:
                    raw = f.read()
            df_raw = pd.read_csv(io.BytesIO(raw), sep=sep, encoding=enc, header=None, nrows=15)
            header_idx = 0
            for idx, row in df_raw.iterrows():
                row_str = " ".join([str(v).lower() for v in row.values])
                if any(k in row_str for k in ["fornecedor", "comprador", "usuario", "cód", "cod"]):
                    header_idx = idx
                    break
            df = pd.read_csv(io.BytesIO(raw), sep=sep, encoding=enc, skiprows=header_idx)
            df = df.iloc[:, :len(expected_cols)]
            df.columns = expected_cols
            df = df.dropna(subset=[expected_cols[0]])
            df = df[~df[expected_cols[0]].astype(str).str.upper().str.contains("CÓD|COD|USUÁRIO|USUARIO")]
            return df
        except Exception:
            continue
    raise ValueError(f"Não foi possível carregar o arquivo {file_or_path}")

cols_forn = ["COD_FORNECEDOR_ORACLE", "NOME_FORNECEDOR_ORACLE", "PRODUTO_SERVICO", "AREA", "JUSTIFICATIVA", "DATA_REGISTRO"]
cols_comp = ["USUARIO_ORACLE", "ID", "COMPRADOR_FUNCIONAL", "EMAIL", "AREA", "UNIDADE", "OPERACAO", "OBS"]

# --- 1. Fornecedores Especiais ---
pdf_forn_esp = load_lookup_csv(CSV_FORNECEDORES_ESP, cols_forn)
pdf_forn_esp["COD_FORNECEDOR_ORACLE"] = pdf_forn_esp["COD_FORNECEDOR_ORACLE"].astype(str).str.strip()
pdf_forn_esp = pdf_forn_esp.drop_duplicates(subset=["COD_FORNECEDOR_ORACLE"])
print(f"✓ fornecedores_especiais: {len(pdf_forn_esp)} registros")

# --- 2. Fornecedores Não Negociáveis ---
pdf_forn_nn = load_lookup_csv(CSV_FORNECEDORES_NN, cols_forn)
pdf_forn_nn["COD_FORNECEDOR_ORACLE"] = pdf_forn_nn["COD_FORNECEDOR_ORACLE"].astype(str).str.strip()
pdf_forn_nn = pdf_forn_nn.drop_duplicates(subset=["COD_FORNECEDOR_ORACLE"])
print(f"✓ fornecedores_nao_negociaveis: {len(pdf_forn_nn)} registros")

# --- 2b. Fornecedores sem OC (Permitidos faturar sem PO) ---
pdf_forn_sem_oc = load_lookup_csv(CSV_FORNECEDORES_SEM_OC, cols_forn)
pdf_forn_sem_oc["COD_FORNECEDOR_ORACLE"] = pdf_forn_sem_oc["COD_FORNECEDOR_ORACLE"].astype(str).str.strip()
pdf_forn_sem_oc = pdf_forn_sem_oc.drop_duplicates(subset=["COD_FORNECEDOR_ORACLE"])
print(f"✓ fornecedores_sem_oc: {len(pdf_forn_sem_oc)} registros")

# --- 3. Compradores Funcionais ---
pdf_compradores = load_lookup_csv(CSV_COMPRADORES, cols_comp)
pdf_compradores["USUARIO_ORACLE"] = pdf_compradores["USUARIO_ORACLE"].astype(str).str.strip()
pdf_compradores = pdf_compradores.drop_duplicates(subset=["USUARIO_ORACLE"])
print(f"✓ compradores_funcionais: {len(pdf_compradores)} registros")

# --- Registrar como Spark temp views (para uso nas queries SQL) ---
spark.createDataFrame(pdf_forn_esp).createOrReplaceTempView("tv_fornecedores_especiais")
spark.createDataFrame(pdf_forn_nn).createOrReplaceTempView("tv_fornecedores_nao_negociaveis")
spark.createDataFrame(pdf_forn_sem_oc).createOrReplaceTempView("tv_fornecedores_sem_oc")
spark.createDataFrame(pdf_compradores).createOrReplaceTempView("tv_compradores_funcionais")
print("✓ Temp views Spark registradas")

# --- Carregar no Lakebase staging ---
conn = get_pg_connection()

bulk_load_to_pg(pdf_forn_esp[["COD_FORNECEDOR_ORACLE", "NOME_FORNECEDOR_ORACLE", "PRODUTO_SERVICO", "AREA", "JUSTIFICATIVA", "DATA_REGISTRO"]], SCHEMA_STAGING, "fornecedores_especiais", conn)
print(f"✓ {SCHEMA_STAGING}.fornecedores_especiais carregada")

bulk_load_to_pg(pdf_forn_nn[["COD_FORNECEDOR_ORACLE", "NOME_FORNECEDOR_ORACLE", "PRODUTO_SERVICO", "AREA", "JUSTIFICATIVA", "DATA_REGISTRO"]], SCHEMA_STAGING, "fornecedores_nao_negociaveis", conn)
print(f"✓ {SCHEMA_STAGING}.fornecedores_nao_negociaveis carregada")

bulk_load_to_pg(pdf_forn_sem_oc[["COD_FORNECEDOR_ORACLE", "NOME_FORNECEDOR_ORACLE", "PRODUTO_SERVICO", "AREA", "JUSTIFICATIVA", "DATA_REGISTRO"]], SCHEMA_STAGING, "fornecedores_sem_oc", conn)
print(f"✓ {SCHEMA_STAGING}.fornecedores_sem_oc carregada")

bulk_load_to_pg(pdf_compradores[["USUARIO_ORACLE", "ID", "COMPRADOR_FUNCIONAL", "EMAIL", "AREA", "UNIDADE", "OPERACAO", "OBS"]], SCHEMA_STAGING, "compradores_funcionais", conn)
print(f"✓ {SCHEMA_STAGING}.compradores_funcionais carregada")

# --- 4. Colaboradores (Unity Catalog: cat_dnabb_dv.cmpbragp360_sz.vw_dim_colaborador_atual) ---
try:
    df_colab = spark.sql("""
        SELECT 
            TRIM(CAST(matricula AS STRING)) AS matricula,
            TRIM(CAST(id_colaborador AS STRING)) AS id_colaborador,
            TRIM(nome_completo) AS nome_completo,
            TRIM(email) AS email,
            TRIM(area) AS area,
            TRIM(diretoria) AS diretoria,
            TRIM(nm_unidade) AS nm_unidade,
            TRIM(nm_cargo) AS nm_cargo
        FROM cat_dnabb_dv.cmpbragp360_sz.vw_dim_colaborador_atual
        WHERE matricula IS NOT NULL
    """).dropDuplicates(["matricula"]).toPandas()
    print(f"✓ colaboradores: {len(df_colab):,} registros lidos do Unity Catalog")
    spark.createDataFrame(df_colab).createOrReplaceTempView("tv_colaboradores")
    bulk_load_to_pg(df_colab[["matricula", "id_colaborador", "nome_completo", "email", "area", "diretoria", "nm_unidade", "nm_cargo"]], SCHEMA_STAGING, "colaboradores", conn)
    print(f"✓ {SCHEMA_STAGING}.colaboradores carregada")
except Exception as e:
    print(f"⚠ Aviso ao carregar colaboradores do Unity Catalog: {e}")

conn.close()
print("\n✓ Lookups prontos (temp views + staging)")

# COMMAND ----------

# DBTITLE 1,3. Carregar vw_notas_ri
# ══════════════════════════════════════════════════════════════════════════════
# NOTAS FISCAIS RI → compras_staging.notas_ri
# Fonte: Oracle Cloud (cat_ocloud_r5_dv.rg5glofsn_cz) via temp view vw_notas_ri
# Lookups: tv_compradores_funcionais, tv_fornecedores_especiais (temp views de CSVs)
# Saving: recalculado em BRL (preço NF, não OC)
# ══════════════════════════════════════════════════════════════════════════════

# Criar temp view com SQL completo (leitura direta Oracle Cloud, sem UC views)
# Os arquivos .sql são carregados dinamicamente via load_sql_view()
_sql_dir = SQL_DIR
_vw_sql = load_sql_view("vw_notas_ri")
spark.sql(f"CREATE OR REPLACE TEMP VIEW vw_notas_ri AS {_vw_sql}")
print(f"✓ Temp view vw_notas_ri criada ({len(_vw_sql):,} chars SQL)")

# Criar temp view vw_ordens_compra (necessária para lookup de CENTRALIZADO)
_vw_oc_sql = load_sql_view("vw_ordens_compra")
spark.sql(f"CREATE OR REPLACE TEMP VIEW vw_ordens_compra AS {_vw_oc_sql}")
print(f"✓ Temp view vw_ordens_compra criada (lookup CENTRALIZADO)")

df_notas = spark.sql("""
    WITH base AS (
        SELECT 
            *,
            -- Taxa de câmbio implícita: VALOR_NOTA_BRL / VALOR_NOTA (1.0 se BRL)
            CASE WHEN CAST(VALOR_NOTA AS DOUBLE) > 0 
                 THEN CAST(VALOR_NOTA_BRL AS DOUBLE) / CAST(VALOR_NOTA AS DOUBLE)
                 ELSE 1.0 END AS _fx_rate,
            -- Preço unitário convertido para BRL
            CAST(PRECO AS DOUBLE) * 
                CASE WHEN CAST(VALOR_NOTA AS DOUBLE) > 0 
                     THEN CAST(VALOR_NOTA_BRL AS DOUBLE) / CAST(VALOR_NOTA AS DOUBLE)
                     ELSE 1.0 END AS _preco_brl,
            -- Chave de fornecedor (CNPJ é mais confiável que nome)
            COALESCE(CNPJ_FORNECEDOR, NOME_FORNECEDOR) AS _vendor_key,
            -- Chave do item (usa código se existir; se não, normaliza descrição)
            COALESCE(NULLIF(NULLIF(NULLIF(TRIM(CODIGO_ITEM), ''), '~NOVALUE~'), 'VAZIO'), UPPER(TRIM(REGEXP_REPLACE(DS_ITEM, '\\s+', ' ')))) AS _item_key,
            -- Flag: comprador está na tabela de compradores funcionais
            CASE WHEN po_h.CreatedBy IN (SELECT USUARIO_ORACLE FROM tv_compradores_funcionais) THEN 1 ELSE 0 END AS _is_comprador_funcional,
            -- Número Oracle do fornecedor (via supplier site, para match com fornecedores_especiais/nao_negociaveis)
            sups.SupplierSegment1 AS _supplier_number
        FROM vw_notas_ri
        INNER JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoiceheaderextractpvo inv_h
            ON CAST(NUMERO_RI AS BIGINT) = inv_h.ApInvoicesInvoiceId
            AND inv_h.ApInvoicesApprovalStatus IN ('APPROVED', 'FULL')
        LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentheaderextractpvo po_h
            ON ApInvoiceLinesAllPoHeaderId = po_h.PoHeaderId
        LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prcpoz_suppliersitepvo sups
            ON inv_h.ApInvoicesVendorId = sups.SupplierVendorId
            AND inv_h.ApInvoicesVendorSiteId = sups.VendorSiteId
        LEFT JOIN (
            SELECT 
                NUMERO_OC AS _lookup_oc, 
                MAX(CENTRALIZADO) AS _oc_centralizado,
                MAX(COMPRADOR) AS _oc_comprador,
                MAX(DEPARTAMENTO_COMPRADOR) AS _oc_dept_comprador
            FROM vw_ordens_compra 
            GROUP BY NUMERO_OC
        ) oc_cent
            ON NUMERO_OC = oc_cent._lookup_oc
        WHERE YEAR(COALESCE(DATA_LANCAMENTO, DT_NOTA)) >= YEAR(CURRENT_DATE) - 1
          AND (NOTA_FISCAL IS NULL OR (
              UPPER(NOTA_FISCAL) NOT LIKE '%ARKER%'
              AND UPPER(NOTA_FISCAL) NOT LIKE '%RGB%'
              AND UPPER(NOTA_FISCAL) NOT LIKE 'ADV%'
              AND UPPER(NOTA_FISCAL) NOT LIKE '%FOPAG%'
              AND UPPER(NOTA_FISCAL) NOT LIKE '%FISCAL%'
          ))
    ),
    com_saving AS (
        SELECT *,
            -- Preço anterior: LAG sobre notas fiscais do mesmo item+fornecedor (mesmo site/CNPJ), em BRL
            LAG(CASE WHEN _preco_brl > 0 THEN _preco_brl END) OVER (
                PARTITION BY _item_key, _vendor_key 
                ORDER BY DT_NOTA, NUMERO_RI
            ) AS _preco_ant_brl,
            LAG(DS_ITEM) OVER (
                PARTITION BY _item_key, _vendor_key
                ORDER BY DT_NOTA, NUMERO_RI
            ) AS _ds_item_ant,
            -- Primeiro preço do ano (base anual) em BRL
            FIRST_VALUE(CASE WHEN _preco_brl > 0 THEN _preco_brl END, true) OVER (
                PARTITION BY _item_key, _vendor_key, SUBSTRING(CAST(ANO_MES AS STRING), 1, 4)
                ORDER BY DT_NOTA, NUMERO_RI
            ) AS _base_ano_brl
        FROM base
    )
    SELECT 
        CAST(INVOICE_ID AS STRING) AS invoice_id,
        CAST(INVOICE_LINE_ID AS STRING) AS invoice_line_id,
        CAST(NUMERO_RI AS STRING) AS numero_ri,
        NOTA_FISCAL AS nota_fiscal,
        SERIE AS serie,
        NUMERO_OC AS numero_oc,
        EMPRESA AS empresa,
        DS_ITEM AS ds_item,
        CODIGO_ITEM AS codigo_item,
        DESCRICAO_ITEM AS descricao_item,
        ITEM_TYPE AS item_type,
        CATEGORIA_ITEM AS categoria_item,
        CATEGORIA_CODIGO AS categoria_codigo,
        CASE 
            WHEN CODIGO_ITEM IS NULL OR TRIM(CODIGO_ITEM) IN ('', '~NOVALUE~') THEN 'VAZIO'
            WHEN CODIGO_ITEM LIKE 'ARKER%' THEN 'Comercial'
            WHEN CATEGORIA_ITEM LIKE 'A PENDING%' THEN 'Indiretos'
            WHEN CODIGO_ITEM LIKE 'A%' THEN 'Commodities & Ingredients'
            WHEN CODIGO_ITEM LIKE 'B%' THEN 'Packaging'
            ELSE 'Indiretos'
        END AS macro_categoria,
        TIPO_VENDOR AS tipo_vendor,
        GRUPO_COMPRAS AS grupo_compras,
        -- CENTRALIZADO: lookup direto de ordens_compra (PROCV por numero_oc)
        CASE 
            WHEN NUMERO_OC = 'Nota sem OC' THEN 'DESCENTRALIZADO'
            ELSE COALESCE(_oc_centralizado, 'DESCENTRALIZADO')
        END AS centralizado,
        COALESCE(_oc_comprador, COMPRADOR) AS comprador,
        COALESCE(_oc_dept_comprador, DEPARTAMENTO_COMPRADOR) AS departamento_comprador,
        CHAVE_OC_LINHA AS chave_oc_linha,
        CAST(LINHA_OC AS INT) AS linha_oc,
        DATA_LANCAMENTO AS data_lancamento,
        DT_NOTA AS dt_nota,
        DT_REGISTRO AS dt_registro,
        DATA_VENCIMENTO AS data_vencimento,
        DATA_PAGAMENTO AS data_pagamento,
        ANO_MES AS ano_mes,
        CAST(DIAS_ATRASO AS DOUBLE) AS dias_atraso,
        CASE WHEN NUMERO_OC <> 'Nota sem OC'
              AND ApprovedDate IS NOT NULL
              AND MIN(DT_NOTA) OVER (PARTITION BY NUMERO_OC) < DATE_FORMAT(ApprovedDate, 'yyyy-MM-dd')
              AND (_supplier_number IS NULL OR _supplier_number NOT IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_especiais))
             THEN 'SIM' ELSE 'NÃO' END AS oc_pos_fatura,
        URGENTE AS urgente,
        CAST(VALOR_NOTA AS DOUBLE) AS valor_nota,
        CAST(VALOR_NOTA_BRL AS DOUBLE) AS valor_nota_brl,
        CAST(VALOR_LIQUIDO_BRL AS DOUBLE) AS valor_liquido_brl,
        CAST(ICMS AS DOUBLE) AS icms,
        CAST(PIS AS DOUBLE) AS pis,
        CAST(COFINS AS DOUBLE) AS cofins,
        CAST(NULL AS DOUBLE) AS imposto_total,
        -- Moeda derivada da taxa de câmbio
        CASE WHEN _fx_rate BETWEEN 0.99 AND 1.01 THEN 'BRL' ELSE 'ESTRANGEIRA' END AS moeda,
        ROUND(_fx_rate, 6) AS taxa_cambio,
        COND_PGTO_CADASTRO AS condicao_pgto,
        CAST(COND_PGTO_AP AS INT) AS prazo_pgto,
        CAST(PGTO_X_VALOR AS DOUBLE) AS pgto_x_valor,

        -- ═══ SAVING HISTÓRICO (nota-a-nota, em BRL, ratio <= 2, exclui F-% e qtd <= 0) ═══
        -- saving_total usa VALOR_NOTA_BRL/preco_brl como quantidade (corrige UDM milheiro/ton)
        CASE WHEN _preco_ant_brl IS NOT NULL AND _preco_brl > 0 AND _preco_ant_brl > 0
                  AND GREATEST(_preco_brl, _preco_ant_brl) / LEAST(_preco_brl, _preco_ant_brl) <= 2
                  AND (CODIGO_ITEM IS NULL OR CODIGO_ITEM NOT LIKE 'F-%')
                  AND CAST(QUANTIDADE AS DOUBLE) > 0
                  AND (
                      (CODIGO_ITEM IS NOT NULL AND TRIM(CODIGO_ITEM) NOT IN ('', '~NOVALUE~', 'VAZIO'))
                      OR (_ds_item_ant IS NOT NULL AND UPPER(TRIM(DS_ITEM)) = UPPER(TRIM(_ds_item_ant)))
                  )
             THEN ROUND((_preco_brl - _preco_ant_brl) * (CAST(VALOR_NOTA_BRL AS DOUBLE) / _preco_brl), 2)
             ELSE NULL END AS saving_total,
        CASE WHEN _preco_ant_brl IS NOT NULL AND _preco_brl > 0 AND _preco_ant_brl > 0
                  AND GREATEST(_preco_brl, _preco_ant_brl) / LEAST(_preco_brl, _preco_ant_brl) <= 2
                  AND (CODIGO_ITEM IS NULL OR CODIGO_ITEM NOT LIKE 'F-%')
                  AND CAST(QUANTIDADE AS DOUBLE) > 0
                  AND (
                      (CODIGO_ITEM IS NOT NULL AND TRIM(CODIGO_ITEM) NOT IN ('', '~NOVALUE~', 'VAZIO'))
                      OR (_ds_item_ant IS NOT NULL AND UPPER(TRIM(DS_ITEM)) = UPPER(TRIM(_ds_item_ant)))
                  )
             THEN ROUND((_preco_brl - _preco_ant_brl) / _preco_ant_brl * 100, 2)
             ELSE NULL END AS saving_pct,

        NOME_FORNECEDOR AS nome_fornecedor,
        CNPJ_FORNECEDOR AS numero_fornecedor,
        CAST(_supplier_number AS STRING) AS codigo_fornecedor_oracle,
        UNIDADE AS unidade,
        REGEXP_REPLACE(LOCAL, '^[0-9]+_(BBR_|BQB_)?', '') AS planta,
        CENTRO_CUSTO AS centro_custo,
        CONTA_CONTABIL AS conta_contabil,
        CAST(COND_PGTO_AP AS DOUBLE) AS cond_pgto_ap,
        FAIXA_PRAZO_PAGAMENTO AS faixa_prazo_pagamento,

        -- ═══ SAVING ANUAL (vs primeiro preço do ano, em BRL, ratio <= 2, exclui F-% e qtd <= 0) ═══
        CASE WHEN _base_ano_brl IS NOT NULL AND _preco_brl > 0 AND _base_ano_brl > 0
                  AND GREATEST(_preco_brl, _base_ano_brl) / LEAST(_preco_brl, _base_ano_brl) <= 2
                  AND (CODIGO_ITEM IS NULL OR CODIGO_ITEM NOT LIKE 'F-%')
                  AND CAST(QUANTIDADE AS DOUBLE) > 0
                  AND (
                      (CODIGO_ITEM IS NOT NULL AND TRIM(CODIGO_ITEM) NOT IN ('', '~NOVALUE~', 'VAZIO'))
                      OR (_ds_item_ant IS NOT NULL AND UPPER(TRIM(DS_ITEM)) = UPPER(TRIM(_ds_item_ant)))
                  )
             THEN ROUND((_preco_brl - _base_ano_brl) * (CAST(VALOR_NOTA_BRL AS DOUBLE) / _preco_brl), 2)
             ELSE NULL END AS saving_total_ano,
        CASE WHEN _base_ano_brl IS NOT NULL AND _preco_brl > 0 AND _base_ano_brl > 0
                  AND GREATEST(_preco_brl, _base_ano_brl) / LEAST(_preco_brl, _base_ano_brl) <= 2
                  AND (CODIGO_ITEM IS NULL OR CODIGO_ITEM NOT LIKE 'F-%')
                  AND CAST(QUANTIDADE AS DOUBLE) > 0
                  AND (
                      (CODIGO_ITEM IS NOT NULL AND TRIM(CODIGO_ITEM) NOT IN ('', '~NOVALUE~', 'VAZIO'))
                      OR (_ds_item_ant IS NOT NULL AND UPPER(TRIM(DS_ITEM)) = UPPER(TRIM(_ds_item_ant)))
                  )
             THEN ROUND((_preco_brl - _base_ano_brl) / _base_ano_brl * 100, 2)
             ELSE NULL END AS saving_pct_ano,
        CASE WHEN _base_ano_brl IS NOT NULL AND _base_ano_brl > 0
             THEN ROUND(_base_ano_brl, 2) ELSE NULL END AS preco_base_ano,

        -- ═══ PREÇO ANTERIOR E SAVING UNITÁRIO (em BRL, exclui F-% e qtd <= 0) ═══
        CASE WHEN _preco_ant_brl IS NOT NULL AND _preco_brl > 0 AND _preco_ant_brl > 0
                  AND GREATEST(_preco_brl, _preco_ant_brl) / LEAST(_preco_brl, _preco_ant_brl) <= 2
                  AND (CODIGO_ITEM IS NULL OR CODIGO_ITEM NOT LIKE 'F-%')
                  AND CAST(QUANTIDADE AS DOUBLE) > 0
                  AND (
                      (CODIGO_ITEM IS NOT NULL AND TRIM(CODIGO_ITEM) NOT IN ('', '~NOVALUE~', 'VAZIO'))
                      OR (_ds_item_ant IS NOT NULL AND UPPER(TRIM(DS_ITEM)) = UPPER(TRIM(_ds_item_ant)))
                  )
             THEN ROUND(_preco_ant_brl, 2)
             ELSE NULL END AS preco_anterior,
        CASE WHEN _preco_ant_brl IS NOT NULL AND _preco_brl > 0 AND _preco_ant_brl > 0
                  AND GREATEST(_preco_brl, _preco_ant_brl) / LEAST(_preco_brl, _preco_ant_brl) <= 2
                  AND (CODIGO_ITEM IS NULL OR CODIGO_ITEM NOT LIKE 'F-%')
                  AND CAST(QUANTIDADE AS DOUBLE) > 0
                  AND (
                      (CODIGO_ITEM IS NOT NULL AND TRIM(CODIGO_ITEM) NOT IN ('', '~NOVALUE~', 'VAZIO'))
                      OR (_ds_item_ant IS NOT NULL AND UPPER(TRIM(DS_ITEM)) = UPPER(TRIM(_ds_item_ant)))
                  )
             THEN ROUND(_preco_brl - _preco_ant_brl, 2)
             ELSE NULL END AS saving_unitario,

        CAST(QUANTIDADE AS DOUBLE) AS quantidade,
        CAST(PRECO AS DOUBLE) AS preco,
        ROUND(_preco_brl, 2) AS preco_brl,
        CAST(PRECO_LIQUIDO AS DOUBLE) AS preco_liquido,
        CAST(VALOR_LIQUIDO AS DOUBLE) AS valor_liquido,
        NUMERO_OC AS numero_oc_original,
        STATUS_PAGAMENTO AS status_pagamento,
        TypeLookupCode AS tipo_nf,
        -- Flags de fornecedor (desnormalizadas para filtros no app)
        CASE WHEN _supplier_number IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_especiais) THEN 'ESPECIAL' ELSE 'NÃO ESPECIAL' END AS is_fornecedor_especial,
        CASE WHEN _supplier_number IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_nao_negociaveis) THEN 'NÃO NEGOCIAVEL' ELSE 'NEGOCIAVEL' END AS is_fornecedor_nao_negociavel,
        CASE WHEN _supplier_number IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_sem_oc) THEN 'SEM OC' ELSE 'COM ATUAÇÃO' END AS is_fornecedor_sem_oc,
        -- CNPJ da unidade Bimbo compradora (filial que recebe a NF)
        CNPJ_BIMBO AS cnpj_bimbo
    FROM com_saving
""")

count_notas = df_notas.count()
print(f"→ vw_notas_ri: {count_notas:,} linhas lidas")

# Converter para pandas e carregar no Lakebase
pdf_notas = df_notas.toPandas()

# Converter colunas inteiras para Int64 (nullable) para evitar serialização como "1.0"
for col in ['linha_oc', 'prazo_pgto']:
    pdf_notas[col] = pdf_notas[col].astype('Int64')

conn = get_pg_connection()
cur = conn.cursor()
count = bulk_load_to_pg(pdf_notas, SCHEMA_STAGING, "notas_ri", conn)
conn.close()
print(f"✓ {SCHEMA_STAGING}.notas_ri: {count:,} linhas carregadas")

# COMMAND ----------

# DBTITLE 1,4. Carregar vw_ordens_compra
# Criar temp view com SQL completo (leitura direta Oracle Cloud)
_sql_dir = SQL_DIR
_vw_sql = load_sql_view("vw_ordens_compra")
spark.sql(f"CREATE OR REPLACE TEMP VIEW vw_ordens_compra AS {_vw_sql}")
print(f"✓ Temp view vw_ordens_compra criada ({len(_vw_sql):,} chars SQL)")

df_ordens = spark.sql("""
    SELECT
        NUMERO_OC AS numero_oc,
        NUMERO_ACORDO AS numero_acordo,
        TIPO AS tipo,
        DESCRICAO AS descricao,
        ITEM_AQUISICAO AS item_aquisicao,
        DESCRICAO_ITEM AS descricao_item,
        CATEGORIA_ITEM AS categoria_item,
        CATEGORIA_CODIGO AS categoria_codigo,
        CASE 
            WHEN ITEM_AQUISICAO IS NULL OR TRIM(ITEM_AQUISICAO) IN ('', '~NOVALUE~') THEN 'VAZIO'
            WHEN ITEM_AQUISICAO LIKE 'ARKER%' THEN 'Comercial'
            WHEN CATEGORIA_ITEM LIKE 'A PENDING%' THEN 'Indiretos'
            WHEN ITEM_AQUISICAO LIKE 'A%' THEN 'Commodities & Ingredients'
            WHEN ITEM_AQUISICAO LIKE 'B%' THEN 'Packaging'
            ELSE 'Indiretos'
        END AS macro_categoria,
        GRUPO_COMPRAS_OC AS grupo_compras_oc,
        CAST(NULL AS STRING) AS descricao_linha,
        CAST(LINHA_OC AS INT) AS linha_oc,
        CHAVE_OC_LINHA AS chave_oc_linha,
        STATUS_APROVACAO AS status_aprovacao,
        STATUS_FECHAMENTO AS status_fechamento,
        CAST(NULL AS STRING) AS empresa,
        org_desc AS org_desc,
        CAST(DATA_OC AS STRING) AS data_oc,
        CAST(DT_APROVACAO AS STRING) AS dt_aprovacao,
        CAST(DT_FECHAMENTO AS STRING) AS dt_fechamento,
        CAST(NULL AS DOUBLE) AS qtd_solicitada,
        CAST(NULL AS DOUBLE) AS qtd,
        CAST(QTD_FATURADA AS DOUBLE) AS qtd_faturada,
        CAST(NULL AS DOUBLE) AS preco_unit,
        CAST(TAXA_CAMBIO AS DOUBLE) AS taxa_cambio,
        CODIGO_MOEDA AS moeda,
        FORNECEDOR AS nome_fornecedor,
        NUMERO_FORNECEDOR AS numero_fornecedor,
        APROVADOR AS aprovador,
        USUARIO AS usuario,
        NOME_USUARIO AS nome_usuario,
        COMPRADOR AS comprador,
        CAST(NULL AS STRING) AS comprador_funcional,
        DEPARTAMENTO_COMPRADOR AS departamento_comprador,
        USUARIO_COMPRADOR AS usuario_comprador,
        EMAIL_COMPRADOR AS email_comprador,
        CAST(DT_PROMESSA AS STRING) AS dt_promessa,
        CAST(DT_NECESSIDADE AS STRING) AS dt_necessidade,
        OC_ATRASADA AS oc_atrasada,
        CAST(DIAS_ATRASO_OC AS DOUBLE) AS dias_atraso_oc,
        CAST(DIAS_ABERTO AS DOUBLE) AS dias_aberto,
        UNIDADE AS unidade,
        AREA AS area,
        CATEGORIA_OC AS categoria_oc,
        NOME_REQUISITANTE AS nome_requisitante,
        DEPARTAMENTO_REQUISITANTE AS departamento_requisitante,
        REQUISICAO AS requisicao,
        FORNECEDOR_ESPECIAL AS fornecedor_especial,
        OC_SEM_USO AS oc_sem_uso,
        CENTRALIZADO AS centralizado,
        -- Flags de fornecedor (desnormalizadas para filtros no app)
        CASE WHEN NUMERO_FORNECEDOR IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_especiais) THEN 'ESPECIAL' ELSE 'NÃO ESPECIAL' END AS is_fornecedor_especial,
        CASE WHEN NUMERO_FORNECEDOR IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_nao_negociaveis) THEN 'NÃO NEGOCIAVEL' ELSE 'NEGOCIAVEL' END AS is_fornecedor_nao_negociavel,
        CASE WHEN NUMERO_FORNECEDOR IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_sem_oc) THEN 'SEM OC' ELSE 'COM ATUAÇÃO' END AS is_fornecedor_sem_oc,
        -- Valor original convertido para BRL (taxa_cambio como fator multiplicador; NULL = já é BRL)
        -- Fix: VALOR_ORIGINAL e VALOR_UTILIZADO ja vem convertidos para BRL na view Oracle
        CAST(VALOR_ORIGINAL AS DOUBLE) AS valor_original_brl,
        CAST(VALOR_UTILIZADO AS DOUBLE) AS valor_utilizado_brl,
        URGENTE AS urgente,
        ACORDO_STATUS AS acordo_status,
        CAST(ACORDO_DT_CRIACAO AS STRING) AS acordo_dt_criacao,
        CAST(ACORDO_DATA_INICIAL AS STRING) AS acordo_data_inicial,
        CAST(ACORDO_DATA_FINAL AS STRING) AS acordo_data_final,
        CAST(ACORDO_VALOR_TOTAL AS DOUBLE) AS acordo_valor_total,
        CAST(ACORDO_VALOR_MIN_LIBERACAO AS DOUBLE) AS acordo_valor_min_liberacao,
        CAST(ACORDO_VALOR_LIBERADO AS DOUBLE) AS acordo_valor_liberado,
        ACORDO_DESCRICAO AS acordo_descricao,
        ACORDO_FOB AS acordo_fob,
        ACORDO_CONDICAO_FRETE AS acordo_condicao_frete,
        ACORDO_CONDICAO_PGTO AS acordo_condicao_pgto
    FROM vw_ordens_compra
    WHERE 1=1
        AND YEAR(COALESCE(DATA_OC, DT_APROVACAO)) >= YEAR(CURRENT_DATE) - 2
        AND GRUPO_COMPRAS_OC <> 'COMERCIAL'
""")

count_ordens = df_ordens.count()
print(f"→ vw_ordens_compra: {count_ordens:,} linhas lidas")

pdf_ordens = df_ordens.toPandas()

# Converter colunas inteiras para Int64 (nullable) para evitar serialização como "1.0"
pdf_ordens['linha_oc'] = pdf_ordens['linha_oc'].astype('Int64')

conn = get_pg_connection()
cur = conn.cursor()
cur.execute(f"TRUNCATE TABLE {SCHEMA_STAGING}.ordens_compra")

buffer = StringIO()
pdf_ordens.to_csv(buffer, index=False, header=False, na_rep='\\N')
buffer.seek(0)
cur.copy_expert(f"COPY {SCHEMA_STAGING}.ordens_compra FROM STDIN WITH (FORMAT csv, NULL '\\N')", buffer)

print(f"✓ {SCHEMA_STAGING}.ordens_compra: {count_ordens:,} linhas carregadas")
cur.close()
conn.close()

# COMMAND ----------

# DBTITLE 1,5. Carregar vw_requisicoes
# Criar temp view com SQL completo (leitura direta Oracle Cloud)
_sql_dir = SQL_DIR
_vw_sql = load_sql_view("vw_requisicoes")
spark.sql(f"CREATE OR REPLACE TEMP VIEW vw_requisicoes AS {_vw_sql}")
print(f"✓ Temp view vw_requisicoes criada ({len(_vw_sql):,} chars SQL)")

df_reqs = spark.sql("""
    SELECT
        EMPRESA AS empresa,
        CAST(REQ_ID AS STRING) AS req_id,
        REQUISICAO AS requisicao,
        DESCRICAO_REQ AS descricao_req,
        NUMERO_OC AS numero_oc,
        USER_REQUISICAO AS user_requisicao,
        REQUISITANTE AS requisitante,
        EMAIL_REQUISITANTE AS email_requisitante,
        DEPARTAMENTO_REQUISITANTE AS departamento_requisitante,
        USER_APROVADOR AS user_aprovador,
        NOME_APROVADOR AS nome_aprovador,
        COMPRADOR_SUGERIDO AS comprador_sugerido,
        DEPARTAMENTO_COMPRADOR AS departamento_comprador,
        CAST(DT_CRIACAO AS STRING) AS dt_criacao,
        CAST(DT_APROVACAO AS STRING) AS dt_aprovacao,
        STATUS AS status,
        CAST(QTD_LINHAS AS INT) AS qtd_linhas,
        CAST(VALOR_REQUISICAO AS DOUBLE) AS valor_requisicao,
        STATUS_ORDEM AS status_ordem
    FROM vw_requisicoes
    WHERE YEAR(COALESCE(DT_APROVACAO, DT_CRIACAO)) >= YEAR(CURRENT_DATE) - 1
""")

count_reqs = df_reqs.count()
print(f"→ vw_requisicoes: {count_reqs:,} linhas lidas")

pdf_reqs = df_reqs.toPandas()

# Converter colunas inteiras para Int64 (nullable) para evitar serialização como "1.0"
pdf_reqs['qtd_linhas'] = pdf_reqs['qtd_linhas'].astype('Int64')

conn = get_pg_connection()
cur = conn.cursor()
cur.execute(f"TRUNCATE TABLE {SCHEMA_STAGING}.requisicoes")

buffer = StringIO()
pdf_reqs.to_csv(buffer, index=False, header=False, na_rep='\\N')
buffer.seek(0)
cur.copy_expert(f"COPY {SCHEMA_STAGING}.requisicoes FROM STDIN WITH (FORMAT csv, NULL '\\N')", buffer)

print(f"✓ {SCHEMA_STAGING}.requisicoes: {count_reqs:,} linhas carregadas")
cur.close()
conn.close()

# COMMAND ----------

# DBTITLE 1,5.1. Carregar vw_acordos_bpa
# Criar temp view com SQL completo de acordos de compra BPA
_vw_sql = load_sql_view("vw_acordos_bpa")
spark.sql(f"CREATE OR REPLACE TEMP VIEW vw_acordos_bpa AS {_vw_sql}")
print(f"✓ Temp view vw_acordos_bpa criada ({len(_vw_sql):,} chars SQL)")

df_bpa = spark.sql("""
    SELECT
        numero_acordo,
        status,
        dt_criacao,
        dt_inicio,
        dt_fim,
        valor_total,
        valor_liberado,
        descricao,
        fornecedor,
        numero_fornecedor,
        comprador,
        usuario_comprador,
        departamento_comprador,
        empresa,
        dias_aberto
    FROM vw_acordos_bpa
""")

count_bpa = df_bpa.count()
print(f"→ vw_acordos_bpa: {count_bpa:,} linhas lidas")

pdf_bpa = df_bpa.toPandas()

conn = get_pg_connection()
cur = conn.cursor()
cur.execute(f"TRUNCATE TABLE {SCHEMA_STAGING}.acordos_compra")

buffer = StringIO()
pdf_bpa.to_csv(buffer, index=False, header=False, na_rep='\\N')
buffer.seek(0)
cur.copy_expert(f"COPY {SCHEMA_STAGING}.acordos_compra FROM STDIN WITH (FORMAT csv, NULL '\\N')", buffer)

print(f"✓ {SCHEMA_STAGING}.acordos_compra: {count_bpa:,} linhas carregadas")
cur.close()
conn.close()

# COMMAND ----------

# DBTITLE 1,6. Validação - Contagem final
# ══════════════════════════════════════════════════════════════════════════════
# VALIDAÇÃO + SWAP ATÔMICO (blue-green)
# 1. Verifica contagens no staging (fail-fast se vazio)
# 2. Faz swap: DROP compras → RENAME staging → compras
# 3. Re-aplica grants para o Service Principal do app
# ══════════════════════════════════════════════════════════════════════════════

conn = get_pg_connection()
cur = conn.cursor()

# --- 1. VALIDAÇÃO: Contagens no staging ---
print("Validando staging...")
tables = ['notas_ri', 'ordens_compra', 'requisicoes', 'acordos_compra', 'fornecedores_especiais', 'fornecedores_nao_negociaveis', 'fornecedores_sem_oc', 'compradores_funcionais', 'colaboradores']
counts = {}
for table in tables:
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA_STAGING}.{table}")
    c = cur.fetchone()[0]
    counts[table] = c
    print(f"  {SCHEMA_STAGING}.{table}: {c:,} registros")

# Fail-fast: tabelas principais não podem estar vazias
assert counts['notas_ri'] > 0, "ERRO: notas_ri vazia no staging!"
assert counts['ordens_compra'] > 0, "ERRO: ordens_compra vazia no staging!"
assert counts['requisicoes'] > 0, "ERRO: requisicoes vazia no staging!"
assert counts['acordos_compra'] > 0, "ERRO: acordos_compra vazia no staging!"
print("\n✓ Validação OK — todas as tabelas têm dados")

# --- 2. SWAP ATÔMICO ---
print("\nExecutando swap atômico...")

# Terminar conexões/consultas ativas que estejam segurando lock no schema compras
print("  Liberando locks e conexões ativas...")
try:
    cur.execute(f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE pid <> pg_backend_pid()
          AND (
              query ILIKE '%{SCHEMA_PROD}.%'
              OR state = 'idle in transaction'
              OR (state = 'active' AND query_start < now() - interval '20 seconds')
          )
    """)
except Exception as _e_term:
    print(f"  ⚠ Aviso ao terminar conexões ativas: {_e_term}")

# Desabilitar autocommit para transação explícita
conn.autocommit = False
try:
    cur.execute("SET LOCAL lock_timeout = '20s'")
    cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_PROD} CASCADE")
    cur.execute(f"ALTER SCHEMA {SCHEMA_STAGING} RENAME TO {SCHEMA_PROD}")
    conn.commit()
    print(f"✓ Swap completo: {SCHEMA_STAGING} → {SCHEMA_PROD}")
except Exception as e:
    conn.rollback()
    raise RuntimeError(f"ERRO no swap: {e}. Staging intacto, produção preservada.") from e
finally:
    conn.autocommit = True

# --- 3. RE-GRANT para Service Principals ---
# App compras-360 (produção)
SP_CLIENT_ID = "872976ee-3cee-44ca-b379-b95ca3c728e0"
# App compras-360-dev (desenvolvimento DAB)
SP_DEV_ID = "627e6de0-2d6a-4f18-972f-40ce487f1dc2"
# App compras-360-dev (legado)
SP_DEV_ANTIGO_ID = "a66036a6-5ef3-4c50-8bae-2b4643977da3"

for sp_id, sp_label in [
    (SP_CLIENT_ID, 'compras-360'),
    (SP_DEV_ID, 'compras-360-dev'),
    (SP_DEV_ANTIGO_ID, 'compras-360-dev-antigo'),
    ('bb20549d-b861-4b4b-bdca-6224f0449f04', 'portal-compras-prod'),
    ('1696c219-f04e-43c2-86b4-462b438143e5', 'portal-compras-dev')
]:
    cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")
    try:
        cur.execute(f"SELECT databricks_create_role('{sp_id}', 'service_principal')")
    except Exception as e:
        if 'already exists' in str(e):
            conn.rollback()
            conn.autocommit = True
        elif 'Identity not found' in str(e):
            conn.rollback()
            conn.autocommit = True
            print(f"  ⚠ SP {sp_label} ({sp_id}) não encontrado no workspace — pulando grants")
            continue
        else:
            raise
    cur.execute(f'GRANT CONNECT ON DATABASE {PG_DATABASE} TO "{sp_id}"')
    cur.execute(f'GRANT USAGE ON SCHEMA {SCHEMA_PROD} TO "{sp_id}"')
    cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA {SCHEMA_PROD} TO "{sp_id}"')
    cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA_PROD} GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO "{sp_id}"')
    print(f"✓ Grants re-aplicados para SP {sp_label} ({sp_id})")

# --- 4. ÍNDICES DE PERFORMANCE ---
print("\nCriando índices de performance...")
_indexes = [
    # notas_ri
    ("idx_nr_empresa_data",  "notas_ri",      "(empresa, data_lancamento)"),
    ("idx_nr_ano",           "notas_ri",      "(SUBSTRING(data_lancamento, 1, 4))"),
    ("idx_nr_chave_oc",      "notas_ri",      "(chave_oc_linha)"),
    ("idx_nr_numero_oc",     "notas_ri",      "(numero_oc)"),
    ("idx_nr_fornecedor",    "notas_ri",      "(nome_fornecedor)"),
    ("idx_nr_grupo",         "notas_ri",      "(grupo_compras)"),
    ("idx_nr_centralizado",  "notas_ri",      "(centralizado)"),
    ("idx_nr_planta",        "notas_ri",      "(planta)"),
    ("idx_nr_macro_cat",     "notas_ri",      "(macro_categoria)"),
    ("idx_nr_data_pgto",     "notas_ri",      "(data_pagamento)"),
    ("idx_nr_data_vencto",   "notas_ri",      "(data_vencimento)"),
    # ordens_compra
    ("idx_oc_chave",         "ordens_compra", "(chave_oc_linha)"),
    ("idx_oc_numero_oc",     "ordens_compra", "(numero_oc)"),
    ("idx_oc_acordo",        "ordens_compra", "(acordo_status, numero_acordo)"),
    ("idx_oc_status_fech",   "ordens_compra", "(status_fechamento)"),
    ("idx_oc_org",           "ordens_compra", "(org_desc)"),
    ("idx_oc_dt_criacao",    "ordens_compra", "(acordo_dt_criacao)"),
    ("idx_oc_macro_cat",     "ordens_compra", "(macro_categoria)"),
    # requisicoes
    ("idx_req_numero_oc",    "requisicoes",   "(numero_oc)"),
    ("idx_req_empresa",      "requisicoes",   "(empresa)"),
    # acordos_compra
    ("idx_acordos_status",   "acordos_compra", "(status, dt_criacao)"),
    ("idx_acordos_num",      "acordos_compra", "(numero_acordo)"),
    ("idx_acordos_empresa",  "acordos_compra", "(empresa)"),
    # fornecedores_sem_oc
    ("idx_fsemoc_cod",       "fornecedores_sem_oc", "(cod_fornecedor_oracle)"),
    # colaboradores
    ("idx_colab_matricula",  "colaboradores", "(matricula)"),
    ("idx_colab_id",         "colaboradores", "(id_colaborador)"),
    ("idx_colab_email",      "colaboradores", "(email)"),
    ("idx_colab_nome",       "colaboradores", "(nome_completo)"),
]
for idx_name, tbl, cols in _indexes:
    try:
        cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {SCHEMA_PROD}.{tbl} {cols}")
    except Exception as e:
        _log_msg = f"Índice {idx_name}: {str(e)[:80]}"
        print(f"  ⚠ {_log_msg}")
        conn.rollback()
        conn.autocommit = True
print(f"✓ {len(_indexes)} índices criados")

cur.close()
conn.close()

print("\n════════════════════════════════════════════════════")
print("✓ ETL COMPLETO — App compras-360 atualizado!")
print("  Zero-downtime: swap atômico aplicado")
print("  Grants: Service Principal com acesso")
print("  Índices: Performance otimizada")
print("════════════════════════════════════════════════════")

# COMMAND ----------

#Validar Notas
conn = get_pg_connection()

display(
    pd.read_sql(
        
        """SELECT
            sum(valor_liquido_brl) as total
        FROM compras.notas_ri
        WHERE 1=1
            AND data_lancamento between '2026-01-01' and '2026-08-31'
            AND CENTRALIZADO = 'DESCENTRALIZADO'
            AND valor_liquido_brl > 30000
            --AND URGENTE = 'SIM'
            --AND empresa = 'BB'
            AND numero_oc <> 'Nota sem OC'
            --AND grupo_compras = 'DIRETOS'
            --AND nome_fornecedor = 'WICKBOLD E NOSSO PAO INDUSTRIAS ALIMENTICIAS LTDA'
            --AND CENTRALIZADO = 'CENTRALIZADO'
            --AND UNIDADE LIKE '%BQ%'
        --LIMIT 20
        """
        
        , conn))

conn.close()

# COMMAND ----------

# DBTITLE 1,8. Consultar tabelas no Lakebase
#Validar Notas
conn = get_pg_connection()

display(
    pd.read_sql(
        
        """SELECT
            *
            
        FROM compras.notas_ri
        WHERE 1=1
            --AND data_lancamento between '2026-04-01' and '2026-04-30'
            --AND empresa = 'BB'
            --AND numero_oc <> 'Nota sem OC'
            --AND grupo_compras = 'DIRETOS'
            --AND nome_fornecedor = 'WICKBOLD E NOSSO PAO INDUSTRIAS ALIMENTICIAS LTDA'
            --AND CENTRALIZADO = 'CENTRALIZADO'
            --AND UNIDADE LIKE '%BQ%'
        LIMIT 20
        """
        
        , conn))

conn.close()

# COMMAND ----------

#Visualizar tabela de OCs
conn = get_pg_connection()

display(
    pd.read_sql(
        
        """SELECT
            *
        FROM compras.ordens_compra
    
        WHERE 1=1
            --AND numero_acordo = '26089000874'
            AND numero_oc = '26089057037'
            --AND acordo_valor_liberado = 0
            --AND acordo_status = 'OPEN'
            --AND CAST(acordo_dt_criacao AS DATE) = '2026-06-25'
            --AND acordo_valor_liberado = 0
        --LIMIT 10
        """
        , conn))

conn.close()

# COMMAND ----------

#Visualizar tabela de OCs
conn = get_pg_connection()

display(
    pd.read_sql(
        
        """SELECT
            *
        FROM compras.compradores_funcionais
        
        WHERE 1=1
        --AND numero_oc = '26089000065'
        --AND linha_oc is not null
        --AND tipo = 'BLANKET'

        --LIMIT 100
        """
        , conn))

conn.close()

# COMMAND ----------

#Visualizar tabela de Requisições
conn = get_pg_connection()

display(
    pd.read_sql(
        
        """SELECT * FROM compras.requisicoes
        WHERE 1=1
            AND dt_aprovacao between '2026-01-01' and '2026-01-02'
            AND empresa = 'BB'

        """
        
        , conn))

conn.close()
