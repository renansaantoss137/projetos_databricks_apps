# Databricks notebook source
# DBTITLE 1,Variáveis
import datetime as md_date
from delta.tables import DeltaTable
from pyspark.sql.utils import AnalysisException
from datetime import date, timedelta

# ---------- PARÂMETROS ----------
# Prioridade: widgets do job > modo incremental automático
try:
    _data_ini = dbutils.widgets.get("data_ini").strip()
    _data_fim = dbutils.widgets.get("data_fim").strip()
except Exception:
    _data_ini = ""
    _data_fim = ""

if _data_ini and _data_fim:
    # MODO MANUAL: datas fornecidas pelo job ou widget
    v_data_ini = _data_ini
    v_data_fim = _data_fim
    print(f"📅 Modo manual: {v_data_ini} → {v_data_fim}")
else:
    # MODO INCREMENTAL: última atualização na fonte - 5 dias
    _max_row = spark.sql("""
        SELECT MAX(CAST(ULTIMA_ATUALIZACAO AS DATE)) AS max_dt
        FROM cat_dnabb_dv.opebrapodis_lz.vendas_neogrid_distribuidores_bqb
    """).first()
    _max_dt = _max_row["max_dt"] if _max_row and _max_row["max_dt"] else date.today()
    v_data_ini = (_max_dt - timedelta(days=5)).strftime("%Y-%m-%d")
    v_data_fim = date.today().strftime("%Y-%m-%d")
    print(f"🔄 Modo incremental: última atualização={_max_dt} → janela [{v_data_ini} → {v_data_fim}]")

# COMMAND ----------

print(f'Processando dados do periodo {v_data_ini} até {v_data_fim}')

# COMMAND ----------

# DBTITLE 1,Carga Delta Table - Sell In Distribuidores

# ---------- QUERY DE ORIGEM COM FILTRO DE PERÍODO ----------
# Alterações v2 (2026-08-03):
#   1. Adicionado CNPJ_BIMBO
#   2. Adicionado SKU_DIST via LEFT JOIN com MAX() para evitar multiplicação
#   3. Renomeado CNPJ_CLIENTE → CNPJ_DISTRIBUIDOR (semântica correta no contexto sell-in)
#   4. COALESCE(CODIGO_BARRAS, CODIGO_DUN) como fallback defensivo

query = f"""
WITH pd_dedup AS (
    -- Deduplica SKU_DISTRIB: pega MAX por (CNPJ_DISTRIBUIDOR, COD_PRODUTO)
    SELECT
        LPAD(CNPJ_DISTRIBUIDOR, 14, '0') AS CNPJ_DIST_NORM,
        COD_PRODUTO,
        MAX(SKU_DISTRIB) AS SKU_DIST
    FROM cat_dnabb_dv.bracatlg_lz.vw_produtos_distribuidores
    WHERE COD_PRODUTO IS NOT NULL
    GROUP BY LPAD(CNPJ_DISTRIBUIDOR, 14, '0'), COD_PRODUTO
)
SELECT
    vppbv.DT_REGISTRO                                           AS DT_SELL_IN,
    vppbv.CNPJ_BIMBO,
    vppbv.GRUPO_CLI                                             AS ID_DISTRIBUIDOR,
    COALESCE(NULLIF(gcv.DESC_DISTRIBUIDOR, '0'),
             'CADASTRAR DESCRICAO')                             AS DESC_DISTRIBUIDOR,
    gcv.GRUPO_CLIENTE_DESC                                      AS DESC_DISTRIBUIDOR_DNA,
    LPAD(CAST(vppbv.CNPJ_CLIENTE AS STRING), 14, '0')           AS CNPJ_DISTRIBUIDOR,
    pd.SKU_DIST,
    CAST(vppbv.ID_PRODUTO AS STRING)                            AS SKU_PROD_BQ,
    pv.DESCRICAO_PRODUTO                                        AS DESC_PROD_BQ,
    COALESCE(NULLIF(pv.CODIGO_BARRAS, '0'), NULLIF(pv.CODIGO_DUN, '0'))  AS CODIGO_BARRAS,
    vppbv.BUDGET_QTDE,
    vppbv.BUDGET_VALOR,
    vppbv.QT_CYW_LIQ_VENDIDO,
    vppbv.VL_CYW_LIQ_VENDIDO,
    pv.QT_NA_EMB_BQ,
    pv.CUPO_NOR_BQ,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')                                         AS storeday
FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2 vppbv
LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view gcv
    ON gcv.COD_GR_CLIENTE = vppbv.GRUPO_CLI
LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view pv
    ON pv.INVENTORY_ITEM_ID = vppbv.ID_PRODUTO
LEFT JOIN pd_dedup pd
    ON pd.CNPJ_DIST_NORM = LPAD(CAST(vppbv.CNPJ_CLIENTE AS STRING), 14, '0')
    AND pd.COD_PRODUTO = CAST(vppbv.ID_PRODUTO AS STRING)
WHERE (gcv.NM_CANAL = 'DISTRIBUIDORES' OR gcv.COD_GR_CLIENTE = 99)
  AND vppbv.GRUPO_CLI NOT IN (108)
  AND CAST(vppbv.storeday AS DATE) BETWEEN '{v_data_ini}' AND '{v_data_fim}'
  AND vppbv.ID_PRODUTO NOT IN (
      26522, 29672, 29675, 29881, 19059850, 19059851, 19059884, 19060224,
      19060271, 19060272, 220, 26693, 290428, 4160062, 44163, 44219,
      48555165, 50935, 8, 82213, 82521, 82820, 83931, 83948, 8551913, 90334,
      90365, 9059374, 90595, 9059877, 9059878, 9059883, 9060135, 907662,
      907663, 907699, 907719, 907720, 907754, 907765, 907779, 907783,
      907802, 907809, 907815, 907819, 908007, 91881, 946185, 100234, 100235,
      149997, 907660, 907726)
"""

# Lê os dados da query
df = spark.sql(query)

# ---------- TABELA DESTINO ----------
target_table = "cat_dnabb_dv.opebrapodis_cz.sellin"

# ---------- UPSERT (MERGE) via CDC storeday ----------
_cols = {c: f"origem.{c}" for c in df.columns}

try:
    DeltaTable.forName(spark, target_table) \
        .alias("destino") \
        .merge(df.alias("origem"),
               "destino.DT_SELL_IN = origem.DT_SELL_IN AND "
               "destino.CNPJ_BIMBO = origem.CNPJ_BIMBO AND "
               "destino.CNPJ_DISTRIBUIDOR = origem.CNPJ_DISTRIBUIDOR AND "
               "destino.SKU_PROD_BQ = origem.SKU_PROD_BQ") \
        .whenMatchedUpdate(set=_cols) \
        .whenNotMatchedInsert(values=_cols) \
        .execute()
    print(f"✅ {target_table} - MERGE concluído (CDC storeday [{v_data_ini} → {v_data_fim}])")
except AnalysisException:
    # Tabela não existe — primeira execução
    df.write.format("delta") \
        .mode("overwrite") \
        .saveAsTable(target_table)
    print(f"✅ {target_table} - Tabela criada (primeira execução)")

# COMMAND ----------

# DBTITLE 1,Carga Delta Table - Sell-Out Distribuidores
query = f"""
SELECT 
  vndb.ID                                               AS ID_NEOGRID,
  vndb.DATA                                             AS DATA_SELL_OUT,
  LPAD(vndb.CNPJ_DISTRIBUIDOR, 14, '0')                AS CNPJ_DISTRIBUIDOR,
  COALESCE(gcv.COD_GR_CLIENTE, 0)                       AS ID_DISTRIBUIDOR,
  vndb.DISTRIBUIDOR                                     AS DESC_DISTRIBUIDOR,
  gcv.GRUPO_CLIENTE_DESC                                AS DESC_DISTRIBUIDOR_DNA,
  CAST(vndb.CNPJ_CLIENTE AS STRING)                     AS CNPJ_CLIENTE,
  cd.RAZAO_SOCIAL                                       AS DESC_CLIENTE,
  vndb.CODIGO_PRODUTO                                   AS SKU_PROD_DIST,
  vpd.DESC_PRODUTO_ARQUIVO_DIST                         AS DESC_PROD_ARQUIVO_DIST,
  vpd.CODIGO_BARRAS,
  vpd.COD_PRODUTO                                        AS SKU_PROD_BQ,
  vpd.DESC_PRODUTO                                       AS DESC_PROD_BQ,
  LPAD(vndb.CNPJ_DISTRIBUIDOR, 14, '0') || '-' || vndb.CODIGO_PRODUTO  AS CHAVE_DISTRIB_SKU,
  LPAD(vndb.CNPJ_DISTRIBUIDOR, 14, '0') || '-' || vndb.CNPJ_CLIENTE    AS CHAVE_DISTRIB_CLIENTE,
  vndb.NATUREZA_OPER,
  vndb.QUANTIDADE,
  CAST(vndb.VALOR_LIQUIDO AS DECIMAL(18,4))             AS VALOR_LIQUIDO,
  COALESCE(vpd.QTD_FATOR, 0)                            AS QTD_PAES_PACOTE,
  COALESCE(vpd.QTD_FATOR, 0)                            AS QT_NA_EMB_BQ,
  CAST(COALESCE(pv.CUPO_NOR_BQ, 0) AS INT)              AS CUPO_NOR_BQ,
  COALESCE(vpd.TIPO_CODIGO_BARRAS, 'EAN')                AS TIPO_CODIGO_DIST,
  -- ========== DUZIA (via vw_produtos_distribuidores_bqb) ==========
  -- Replica DAX Duzias_2: sinal por NATUREZA_OPER × QTD_FATOR / divisor
  -- Divisor = 1 p/ MINI CROISSANT, CROISSANT, DONUTS, BAGUETE GRANDE,
  --           BIMBO - MINI HB BRIOCHE, BOLO AM; 12 p/ demais.
  CAST(
    CASE 
      WHEN vndb.NATUREZA_OPER = 'Venda'                         THEN vndb.QUANTIDADE
      WHEN vndb.NATUREZA_OPER IN ('Devolução', 'Cancelado')     THEN -vndb.QUANTIDADE
      ELSE NULL
    END 
    * vpd.QTD_FATOR
    / CASE
        WHEN UPPER(vpd.DESC_PRODUTO) LIKE 'MINI CROISSANT%' 
          OR UPPER(vpd.DESC_PRODUTO) LIKE 'CROISSANT%'
          OR UPPER(vpd.DESC_PRODUTO) LIKE 'DONUTS%'
          OR UPPER(vpd.DESC_PRODUTO) LIKE 'BAGUETE GRANDE%'
          OR UPPER(vpd.DESC_PRODUTO) LIKE 'BIMBO - MINI HB BRIOCHE%'
          OR UPPER(vpd.DESC_PRODUTO) LIKE 'BOLO AM%'
        THEN 1
        ELSE 12
      END 
  AS DOUBLE)                                              AS QTDE_DUZIA_SELL_OUT,
  from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')                                   AS storeday

FROM cat_dnabb_dv.opebrapodis_lz.vendas_neogrid_distribuidores_bqb vndb 

LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view gcv 
  ON gcv.CNPJ_CLIENTE = vndb.CNPJ_DISTRIBUIDOR

LEFT JOIN cat_dnabb_dv.bracatlg_lz.vw_produtos_distribuidores vpd
  ON  vpd.SKU_DISTRIB       = vndb.CODIGO_PRODUTO
  AND vpd.CNPJ_DISTRIBUIDOR = vndb.CNPJ_DISTRIBUIDOR

LEFT JOIN cat_dnabb_dv.bracatlg_lz.clientes_distribuidores cd 
  ON  cd.CNPJ              = vndb.CNPJ_CLIENTE 
  AND cd.CNPJ_DISTRIBUIDOR = vndb.CNPJ_DISTRIBUIDOR 

LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view pv 
  ON pv.INVENTORY_ITEM_ID  = vpd.COD_PRODUTO

WHERE CAST(vndb.storeday AS DATE) BETWEEN '{v_data_ini}' AND '{v_data_fim}'
"""

# Lê os dados da query
df = spark.sql(query)

# ---------- TABELA DESTINO ----------
target_table = "cat_dnabb_dv.opebrapodis_cz.sellout"

# ---------- SCHEMA EVOLUTION (Table ACLs não permitem mergeSchema) ----------
try:
    _existing = {c.name for c in spark.table(target_table).schema}
    _new_cols = set(df.schema.names) - _existing
    if _new_cols:
        for _cn in _new_cols:
            _ct = df.schema[_cn].dataType.simpleString()
            spark.sql(f"ALTER TABLE {target_table} ADD COLUMNS (`{_cn}` {_ct})")
        print(f"📐 Schema evolução: adicionada(s) {_new_cols}")
except AnalysisException:
    pass  # Tabela ainda não existe — será criada abaixo

# ---------- UPSERT (MERGE) via CDC storeday ----------
_cols = {c: f"origem.{c}" for c in df.columns}

try:
    DeltaTable.forName(spark, target_table) \
        .alias("destino") \
        .merge(df.alias("origem"),
               "destino.ID_NEOGRID = origem.ID_NEOGRID") \
        .whenMatchedUpdate(set=_cols) \
        .whenNotMatchedInsert(values=_cols) \
        .execute()
    print(f"✅ {target_table} - MERGE concluído (CDC storeday [{v_data_ini} → {v_data_fim}])")
except AnalysisException:
    # Tabela não existe — primeira execução
    df.write.format("delta") \
        .mode("overwrite") \
        .saveAsTable(target_table)
    print(f"✅ {target_table} - Tabela criada (primeira execução)")

# COMMAND ----------

# DBTITLE 1,Carga Delta Table - Estoque Distribuidores
query = f"""
    SELECT 
    ed.DT_ESTOQUE AS DATA_ESTOQUE,
    ed.CNPJ_DIST AS CNPJ_DISTRIBUIDOR,
    COALESCE(gcv.COD_GR_CLIENTE, 0) AS ID_DISTRIBUIDOR,
    gcv.DESC_DISTRIBUIDOR,
    gcv.GRUPO_CLIENTE_DESC DESC_DISTRIBUIDOR_DNA,
    ed.COD_PRODUTO AS SKU_PROD_DIST,
    vpd.DESC_PRODUTO_ARQUIVO_DIST AS DESC_PROD_ARQUIVO_DIST,
    vpd.CODIGO_BARRAS,
    pv.COD_PRODUTO AS SKU_PROD_BQ,
    pv.DESCRICAO_PRODUTO AS DESC_PROD_BQ,
    ed.QT_ESTOQUE AS QTDE_ESTOQUE,
    ed.MEDIA_VENDA,
    ed.GIRO_ESTOQUE,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')                                         AS storeday
    FROM cat_dnabb_dv.opebrapodis_lz.estoque_distribuidores ed 
    LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view gcv 
        ON gcv.CNPJ_CLIENTE = ed.CNPJ_DIST
    LEFT JOIN cat_dnabb_dv.bracatlg_lz.vw_produtos_distribuidores vpd 
        ON vpd.SKU_DISTRIB = ed.COD_PRODUTO 
        AND vpd.CNPJ_DISTRIBUIDOR = ed.CNPJ_DIST
    LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view pv 
        ON pv.INVENTORY_ITEM_ID = vpd.COD_PRODUTO
    WHERE CAST(ed.storeday AS DATE) BETWEEN '{v_data_ini}' AND '{v_data_fim}'
"""

# Lê os dados da query
df = spark.sql(query)

# ---------- TABELA DESTINO ----------
target_table = "cat_dnabb_dv.opebrapodis_cz.estoque"

# ---------- UPSERT (MERGE) via CDC storeday ----------
_cols = {c: f"origem.{c}" for c in df.columns}

try:
    DeltaTable.forName(spark, target_table) \
        .alias("destino") \
        .merge(df.alias("origem"),
               "destino.DATA_ESTOQUE = origem.DATA_ESTOQUE AND "
               "destino.CNPJ_DISTRIBUIDOR = origem.CNPJ_DISTRIBUIDOR AND "
               "destino.SKU_PROD_DIST = origem.SKU_PROD_DIST") \
        .whenMatchedUpdate(set=_cols) \
        .whenNotMatchedInsert(values=_cols) \
        .execute()
    print(f"✅ {target_table} - MERGE concluído (CDC storeday [{v_data_ini} → {v_data_fim}])")
except AnalysisException:
    # Tabela não existe — primeira execução
    df.write.format("delta") \
        .mode("overwrite") \
        .saveAsTable(target_table)
    print(f"✅ {target_table} - Tabela criada (primeira execução)")

# COMMAND ----------

# DBTITLE 1,Carga Delta Table - Pedidos Distribuidores
query = f"""
    SELECT
    -- ========== IDENTIFICAÇÃO ==========
    P.DB_PED_EMPRESA,
    I.DB_PEDI_PEDIDO,
    I.DB_PEDI_SEQUENCIA,
    I.DB_PEDI_PRODUTO,
    I.DB_PEDI_SITUACAO,
    I.DB_PEDI_ATD_DCTO,
    I.STATUS_REGISTRO,

    -- ========== DATAS ==========
    P.DB_PED_DT_EMISSAO,
    P.DB_PED_DT_PREVENT,
    I.DB_PEDI_ATD_DATA,

    -- ========== CLIENTE / DISTRIBUIDOR ==========
    P.DB_PED_CLIENTE,
    DC.DB_CLI_CGCMF,
    DC.DB_CLI_RAMATIV,
    R.DB_TBATV_CODIGO,
    GCV.DESC_DISTRIBUIDOR,
    GCV.GRUPO_CLIENTE_DESC,
    GCV.NM_CANAL,

    -- ========== PRODUTO ==========
    CPV.DESCRICAO_PRODUTO,
    CPV.QT_NA_EMB_BQ,
    CAST(CPV.CUPO_NOR_BQ AS DECIMAL(18, 4)) AS CUPO_NOR_BQ,
    CPD.SKU_DISTRIB,
    CPD.DESC_PRODUTO_ARQUIVO_DIST,

    -- ========== QUANTIDADES (RAW) ==========
    I.DB_PEDI_QTDE_SOLIC,
    I.DB_PEDI_QTDE_ATEND,
    I.DB_PEDI_QTDE_CANC,

    -- ========== PREÇOS (RAW) ==========
    I.DB_PEDI_PRECO_UNIT,
    I.DB_PEDI_PRECO_LIQ,
    I.DB_PEDI_VU_ICMS,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo') AS storeday

FROM
    cat_dnabb_dv.opebrapodis_lz.mcanet_db_pedido_prod I
    INNER JOIN cat_dnabb_dv.opebrapodis_lz.mcanet_db_pedido P
        ON I.DB_PEDI_PEDIDO = P.DB_PED_NRO
        AND I.DB_PED_DT_EMISSAO = P.DB_PED_DT_EMISSAO
    LEFT JOIN cat_dnabb_dv.opebrapodis_lz.mcanet_db_cliente DC
        ON P.DB_PED_CLIENTE = DC.DB_CLI_CODIGO
    LEFT JOIN cat_dnabb_dv.opebrapodis_lz.mcanet_db_tb_ramo_ativ R
        ON DC.DB_CLI_RAMATIV = R.DB_TBATV_CODIGO
    LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view GCV
        ON CAST(GCV.COD_GR_CLIENTE AS STRING) = R.DB_TBATV_CODIGO
    LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view CPV
        ON CAST(I.DB_PEDI_PRODUTO AS INT) = CPV.INVENTORY_ITEM_ID
    LEFT JOIN (
        SELECT
            CNPJ_DISTRIBUIDOR,
            COD_PRODUTO,
            SKU_DISTRIB,
            DESC_PRODUTO_ARQUIVO_DIST,
            ROW_NUMBER() OVER (
                PARTITION BY CNPJ_DISTRIBUIDOR, COD_PRODUTO
                ORDER BY SKU_DISTRIB DESC
            ) AS RN
        FROM cat_dnabb_dv.bracatlg_lz.vw_produtos_distribuidores
    ) CPD
        ON CAST(CPD.CNPJ_DISTRIBUIDOR AS STRING) = CAST(DC.DB_CLI_CGCMF AS STRING)
        AND CAST(CPD.COD_PRODUTO AS STRING) = CAST(I.DB_PEDI_PRODUTO AS STRING)
        AND CPD.RN = 1

WHERE 1=1 
    AND (GCV.NM_CANAL = 'DISTRIBUIDORES' OR GCV.COD_GR_CLIENTE = 99)
    AND I.DB_PEDI_PRODUTO <> '999999917'
    AND I.DB_PEDI_SITUACAO IN (0, 1, 2, 4, 9)
    AND COALESCE(I.STATUS_REGISTRO, 'ATIVO') = 'ATIVO'
    -- Alteração (2026-10-26): CDC também pelo cabeçalho (P.storeday) — captura mudanças só no cabeçalho (ex.: previsão de entrega)
    AND (CAST(I.storeday AS DATE) BETWEEN '{v_data_ini}' AND '{v_data_fim}'
         OR CAST(P.storeday AS DATE) BETWEEN '{v_data_ini}' AND '{v_data_fim}')
"""

# Lê os dados da query
df = spark.sql(query)

# ---------- TABELA DESTINO ----------
target_table = "cat_dnabb_dv.opebrapodis_cz.pedidos"

# ---------- UPSERT (MERGE) via CDC storeday ----------
_cols = {c: f"origem.{c}" for c in df.columns}

try:
    DeltaTable.forName(spark, target_table) \
        .alias("destino") \
        .merge(df.alias("origem"),
               "destino.DB_PEDI_PEDIDO = origem.DB_PEDI_PEDIDO AND "
               "destino.DB_PEDI_SEQUENCIA = origem.DB_PEDI_SEQUENCIA AND "
               "destino.DB_PED_DT_EMISSAO = origem.DB_PED_DT_EMISSAO") \
        .whenMatchedUpdate(set=_cols) \
        .whenNotMatchedInsert(values=_cols) \
        .withSchemaEvolution() \
        .execute()
    print(f"✅ {target_table} - MERGE concluído (CDC storeday [{v_data_ini} → {v_data_fim}])")
except AnalysisException:
    # Tabela não existe — primeira execução
    df.write.format("delta") \
        .mode("overwrite") \
        .saveAsTable(target_table)
    print(f"✅ {target_table} - Tabela criada (primeira execução)")

# COMMAND ----------

# DBTITLE 1,Dimensão Curated - Produtos Distribuidores
# ========== dim_produtos_distribuidores ==========
# Enriquecido com DESC_DISTRIBUIDOR + DESC_DISTRIBUIDOR_DNA de grupo_clientes_view
# Sem filtro de PASTA_FONTE — compartilhada entre BQB e BB

query_dim_prod = """
SELECT
    pd.SKU_DISTRIB,
    pd.EAN AS CODIGO_BARRAS,
    LPAD(pd.CNPJ_DISTRIBUIDOR, 14, '0') AS CNPJ_DISTRIBUIDOR,
    pd.PASTA_FONTE,
    pd.DESC_PRODUTO,
    pd.DESC_PRODUTO_ARQUIVO_DIST,
    pd.COD_PRODUTO          AS SKU_PROD_BQ,
    pv.DESCRICAO_PRODUTO    AS DESC_PROD_BQ,
    pd.TIPO_CESTO,
    pd.CUPO,
    pd.CUPO_NOR,
    pd.CUPO_BQ,
    COALESCE(NULLIF(gcv.DESC_DISTRIBUIDOR, '0'), 'CADASTRAR DESCRICAO') AS DESC_DISTRIBUIDOR,
    gcv.GRUPO_CLIENTE_DESC  AS DESC_DISTRIBUIDOR_DNA,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')     AS storeday
FROM cat_dnabb_dv.bracatlg_lz.produtos_distribuidores pd
LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view gcv
    ON gcv.CNPJ_CLIENTE = pd.CNPJ_DISTRIBUIDOR
LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view pv
    ON pv.INVENTORY_ITEM_ID = pd.COD_PRODUTO
-- Sem filtro PASTA_FONTE: BQB e BB compartilham a mesma dimensão enriquecida
-- Filtrar PASTA_FONTE no nível da aplicação/query
"""

df_dim_prod = spark.sql(query_dim_prod)

# Full overwrite — dimensão sem filtro de período
df_dim_prod.write.format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable("cat_dnabb_dv.opebrapodis_cz.dim_produtos_distribuidores")

# COMMAND ----------

# DBTITLE 1,Dimensão Curated - VW Produtos Distribuidores (BQB)
# ========== dim_vw_produtos_distribuidores ==========
# Fonte: bracatlg_lz.vw_produtos_distribuidores (Azure: catalogos.vw_produtos_distribuidores_bqb)
# Maior acuracidade que produtos_distribuidores — substitui na camada CZ.
# Enriquecido com DESC_DISTRIBUIDOR_DNA (grupo_clientes_view) e DESC_PROD_BQ (produtos_view).
# Full overwrite — dimensão catálogo sem filtro de período.

target_table = "cat_dnabb_dv.opebrapodis_cz.dim_vw_produtos_distribuidores"

query_dim_vwpd = """
SELECT
    vpd.SKU_DISTRIB,
    vpd.CODIGO_BARRAS,
    LPAD(vpd.CNPJ_DISTRIBUIDOR, 14, '0')    AS CNPJ_DISTRIBUIDOR,
    vpd.NOME_DISTRIBUIDOR                    AS DESC_DISTRIBUIDOR,
    gcv.GRUPO_CLIENTE_DESC                   AS DESC_DISTRIBUIDOR_DNA,
    vpd.DESC_PRODUTO,
    vpd.DESC_PRODUTO_ARQUIVO_DIST,
    vpd.COD_PRODUTO                          AS SKU_PROD_BQ,
    pv.DESCRICAO_PRODUTO                     AS DESC_PROD_BQ,
    vpd.PASTA_FONTE,
    vpd.CUPO_BQ,
    vpd.QTD_FATOR,
    vpd.TIPO_CODIGO_BARRAS,
    vpd.PK_PRODUTO,
    vpd.FONTE,
    vpd.ULTIMA_ATUALIZACAO,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')                      AS storeday
FROM cat_dnabb_dv.bracatlg_lz.vw_produtos_distribuidores vpd
LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view gcv
    ON gcv.CNPJ_CLIENTE = vpd.CNPJ_DISTRIBUIDOR
LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view pv
    ON pv.INVENTORY_ITEM_ID = vpd.COD_PRODUTO
"""

df_dim_vwpd = spark.sql(query_dim_vwpd)

df_dim_vwpd.write.format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(target_table)

print(f"✅ {target_table} — {df_dim_vwpd.count()} registros")

# COMMAND ----------

# DBTITLE 1,Dimensão Curated - Clientes Distribuidores
# ========== dim_clientes_distribuidores ==========
# Enriquecido com DESC_DISTRIBUIDOR + DESC_DISTRIBUIDOR_DNA de grupo_clientes_view
# Sem filtros (BQB/BB, ATIVO/INATIVO) — compartilhada entre projetos.
# Todos os filtros aplicados no nível da aplicação/query.

query_dim_cli = """
SELECT
    cd.CNPJ AS CNPJ_CLIENTE,
    cd.RAZAO_SOCIAL AS DESC_CLIENTE,
    cd.CEP,
    cd.UF,
    cd.MUNICIPIO,
    cd.RUA,
    cd.BAIRRO,
    LPAD(cd.CNPJ_DISTRIBUIDOR, 14, '0') AS CNPJ_DISTRIBUIDOR,
    cd.PASTA_FONTE,
    COALESCE(NULLIF(gcv.DESC_DISTRIBUIDOR, '0'), 'CADASTRAR DESCRICAO') AS DESC_DISTRIBUIDOR,
    gcv.GRUPO_CLIENTE_DESC  AS DESC_DISTRIBUIDOR_DNA,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')     AS storeday
FROM cat_dnabb_dv.bracatlg_lz.clientes_distribuidores cd
LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view gcv
    ON gcv.CNPJ_CLIENTE = cd.CNPJ_DISTRIBUIDOR
-- Sem filtro PASTA_FONTE: BQB e BB compartilham a mesma dimensão enriquecida
"""

df_dim_cli = spark.sql(query_dim_cli)

# Full overwrite — dimensão sem filtro de período
df_dim_cli.write.format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable("cat_dnabb_dv.opebrapodis_cz.dim_clientes_distribuidores")

# COMMAND ----------

# DBTITLE 1,Dimensão Curated - Conexão FTP Distribuidores
# ========== dim_conexao_ftp_distribuidores ==========
# Enriquecido com DESC_DISTRIBUIDOR + DESC_DISTRIBUIDOR_DNA de grupo_clientes_view
# Sem filtros — compartilhada entre projetos. Filtrar no nível da aplicação/query.

query_dim_cnx = """
SELECT
    cfg.USUARIO,
    cfg.SENHA,
    cfg.SERVIDOR,
    cfg.PORTA,
    cfg.PASTA,
    cfg.CNPJ AS CNPJ_DISTRIBUIDOR,
    cfg.NOME_DISTRIBUIDOR AS DESC_DISTRIBUIDOR,
    cfg.CONEXAO,
    cfg.COMUNICADO,
    cfg.INSTALADO,
    cfg.STATUS,
    cfg.OBS AS PASTA_FONTE,
    cfg.SERVIDOR_CLIENTE,
    gcv.GRUPO_CLIENTE_DESC AS DESC_DISTRIBUIDOR_DNA,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo') AS storeday
FROM cat_dnabb_dv.bracatlg_lz.conexao_ftp_distribuidores cfg
LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view gcv
    ON gcv.CNPJ_CLIENTE = cfg.CNPJ
"""

df_dim_cnx = spark.sql(query_dim_cnx)

# Full overwrite — dimensão sem filtro de período
df_dim_cnx.write.format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable("cat_dnabb_dv.opebrapodis_cz.dim_conexao_ftp_distribuidores")

# COMMAND ----------

# DBTITLE 1,dim_grupo_clientes_bq
# ---------- dim_grupo_clientes_bq ----------
# Fonte: bracatlg_lz.grupo_clientes_view
# Chave: COD_GR_CLIENTE (= ID_DISTRIBUIDOR nas tabelas fato)
# Descrições: GRUPO_CLIENTE_DESC (DNA), DESC_DISTRIBUIDOR

target_table = "cat_dnabb_dv.opebrapodis_cz.dim_grupo_clientes_bq"

df = spark.sql("""
    SELECT 
        COD_GR_CLIENTE AS ID_DISTRIBUIDOR,
        GRUPO_CLIENTE_DESC,
        DESC_DISTRIBUIDOR,
        LPAD(CNPJ_CLIENTE, 14, '0') AS CNPJ_DISTRIBUIDOR,
        CD_CANAL, NM_CANAL,
        NM_NV1, NM_NV2, NM_NV3, NM_NV4,
        CD_SEGMENTO, NM_SEGMENTO,
        PER_LIQUIDO, PER_COMISSAO,
        CLUSTER, CLUSTER_1, CLUSTER_2,
        CANAL,
        CLUSTER_FILL_RATE_OTIF,
        from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo') AS storeday
    FROM cat_dnabb_dv.bracatlg_lz.grupo_clientes_view
""")

df.write.format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(target_table)

_cnt = spark.table(target_table).count()
print(f"✅ {target_table} — {_cnt} registros")

# COMMAND ----------

# DBTITLE 1,dim_produtos_bq
# ---------- dim_produtos ----------
# Fonte: bracatlg_lz.produtos_view
# Chave primária: INVENTORY_ITEM_ID (Oracle PK — usar para relationships)
# Chave natural: COD_PRODUTO (= SKU_PROD_BQ nas tabelas fato)

target_table = "cat_dnabb_dv.opebrapodis_cz.dim_produtos"

df = spark.sql("""
    SELECT 
        INVENTORY_ITEM_ID,
        COD_PRODUTO,
        DESCRICAO_PRODUTO,
        CODIGO_BARRAS,
        CODIGO_DUN,
        MARCA,
        CATEGORIA_MKT, LINHA_MKT, SUBLINHA_MKT,
        STATUS,
        TIPO_CESTO, TIPO_CUPO,
        CUPO, CUPO_NOR, CAST(CUPO_NOR_BQ AS INT) AS CUPO_NOR_BQ,
        QT_NA_EMB_BQ, QTD_PAES_PACOTE,
        GRAMATURA, SHELF_LIFE_DAYS, UE,
        LINHA_RVV, LINHA_PRODUTO,
        CATEGORIA_PRICING, SUBCATEGORIA,
        UNIDADE_NEGOCIO,
        GRP_PROD_COD_BQ, GRUPO_PRODUTO_DESC_BQ,
        FAMILIA_COD_BQ, FAMILIA_DESC_BQ,
        TIPO_PRODUTO_BQ, DS_TIPO_PROD_BQ, DS_CLASIF_BQ,
        PRODUTO_FOCO, PAO_COMUM,
        NCM, CEST,
        from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo') AS storeday
    FROM cat_dnabb_dv.bracatlg_lz.produtos_view
""")

df.write.format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(target_table)

_cnt = spark.table(target_table).count()
print(f"✅ {target_table} — {_cnt} registros")

# COMMAND ----------

# DBTITLE 1,CZ - jbp_metas_distribuidores
# ---------- jbp_metas_distribuidores ----------
# Fonte: opebrapodis_lz.jbp_metas_distribuidores_bqb_v2
# Chave: (ID_DISTRIBUIDOR, DATA)
# Transformações: renames, LPAD CNPJ, UPPER(EXECUTIVO/REGIONAL)
# Excluídos: CLIENTE, BI

target_table = "cat_dnabb_dv.opebrapodis_cz.jbp_metas_distribuidores"

df = spark.sql("""
    SELECT
        COD_GR_CLIENTE              AS ID_DISTRIBUIDOR,
        LPAD(CNPJ, 14, '0')        AS CNPJ_DISTRIBUIDOR,
        ANO,
        MES,
        DATA,
        GRUPO_CLIENTE_DESC          AS DESC_DISTRIBUIDOR_DNA,
        UPPER(EXECUTIVO)            AS EXECUTIVO,
        UPPER(REGIONAL)             AS REGIONAL,
        UF,
        VALOR_META,
        DT_LAST_UPDATE,
        from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')         AS storeday
    FROM cat_dnabb_dv.opebrapodis_lz.jbp_metas_distribuidores_bqb_v2
""")

# Full overwrite — tabela de referência (metas semanais)
df.write.format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(target_table)

_cnt = spark.table(target_table).count()
print(f"✅ {target_table} — {_cnt} registros")

# COMMAND ----------

# DBTITLE 1,CZ - metas_positivacao_distribuidores
# ---------- metas_positivacao_distribuidores ----------
# Fonte: opebrapodis_lz.metas_positivacao_distribuidores
# Chave: (ID_DISTRIBUIDOR, DATA)
# Transformações: renames, LPAD CNPJ, UPPER(EXECUTIVO/REGIONAL)
# Excluídos: CLIENTE, BI
# Diferença vs jbp_metas: POSITIVACAO_META (int) no lugar de VALOR_META

target_table = "cat_dnabb_dv.opebrapodis_cz.metas_positivacao_distribuidores"

df = spark.sql("""
    SELECT
        COD_GR_CLIENTE              AS ID_DISTRIBUIDOR,
        LPAD(CNPJ, 14, '0')        AS CNPJ_DISTRIBUIDOR,
        ANO,
        MES,
        DATA,
        GRUPO_CLIENTE_DESC          AS DESC_DISTRIBUIDOR_DNA,
        UPPER(EXECUTIVO)            AS EXECUTIVO,
        UPPER(REGIONAL)             AS REGIONAL,
        UF,
        CAST(POSITIVACAO_META AS INT) AS POSITIVACAO_META,
        DT_LAST_UPDATE,
        from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')         AS storeday
    FROM cat_dnabb_dv.opebrapodis_lz.metas_positivacao_distribuidores
""")

# Full overwrite — tabela de referência (metas de positivação)
df.write.format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(target_table)

_cnt = spark.table(target_table).count()
print(f"✅ {target_table} — {_cnt} registros")

# COMMAND ----------

# DBTITLE 1,CZ - distribuidores_arquivo_ftp
# ---------- distribuidores_arquivo_ftp (CZ) ----------
# Fonte: opebrapodis_lz.distribuidores_arquivo_ftp
# Enriquecido com grupo_clientes_view (ID_DISTRIBUIDOR, DESC_DISTRIBUIDOR_DNA)
# LPAD CNPJ para 14 dígitos
# replaceWhere em DT_INFO_ARQUIVO

query = f"""
SELECT
    daf.ARQUIVO,
    daf.DATE_UPDATE_ARQUIVO,
    daf.NATUREZA_ARQUIVO,
    LPAD(daf.CNPJ, 14, '0')                    AS CNPJ_DISTRIBUIDOR,
    COALESCE(gcv.COD_GR_CLIENTE, 0)             AS ID_DISTRIBUIDOR,
    daf.DISTRIBUIDOR                             AS DESC_DISTRIBUIDOR,
    gcv.GRUPO_CLIENTE_DESC                       AS DESC_DISTRIBUIDOR_DNA,
    daf.ORG_BIMBO,
    daf.DT_UPDATE_DATA_LAKE,
    daf.DT_INFO_ARQUIVO,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')                          AS storeday
FROM cat_dnabb_dv.opebrapodis_lz.distribuidores_arquivo_ftp daf
LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view gcv
    ON LPAD(gcv.CNPJ_CLIENTE, 14, '0') = LPAD(daf.CNPJ, 14, '0')
WHERE CAST(daf.storeday AS DATE) BETWEEN '{v_data_ini}' AND '{v_data_fim}'
"""

target_table = "cat_dnabb_dv.opebrapodis_cz.distribuidores_arquivo_ftp"
df = spark.sql(query)

# ---------- UPSERT (MERGE) via CDC storeday ----------
_cols = {c: f"origem.{c}" for c in df.columns}

try:
    DeltaTable.forName(spark, target_table) \
        .alias("destino") \
        .merge(df.alias("origem"),
               "destino.ARQUIVO = origem.ARQUIVO AND "
               "destino.CNPJ_DISTRIBUIDOR = origem.CNPJ_DISTRIBUIDOR") \
        .whenMatchedUpdate(set=_cols) \
        .whenNotMatchedInsert(values=_cols) \
        .execute()
    print(f"✅ {target_table} - MERGE concluído (CDC storeday [{v_data_ini} → {v_data_fim}])")
except AnalysisException:
    # First run — create Delta table
    df.write.format("delta") \
        .mode("overwrite") \
        .option("overwriteSchema", "true") \
        .saveAsTable(target_table)
    print(f"✅ {target_table} - Tabela criada (primeira execução)")