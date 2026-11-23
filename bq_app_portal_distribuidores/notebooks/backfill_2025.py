# Databricks notebook source
# MAGIC %run /Shared/CONSULTAS_AUTOMATIZADAS/ProjetoPortalDistribuidores/Control/NB_CNTR_Config

# COMMAND ----------
from delta.tables import DeltaTable
from pyspark.sql.functions import current_timestamp, from_utc_timestamp
from pyspark.sql.utils import AnalysisException
v_data_ini='2025-01-01'
v_data_fim='2025-12-31'

# COMMAND ----------
v_query = f"""select * from bqb.vendas_pedidos_ppto_bq_v2 where DT_REGISTRO >= '2025-01-01' AND DT_REGISTRO < '2026-01-01'"""

df = read_sql_azure(query=v_query)

df = df.withColumn("storeday", from_utc_timestamp(current_timestamp(), "America/Sao_Paulo"))

# COMMAND ----------

# DBTITLE 1,Cell 5
_cols = {c: f"origem.{c}" for c in df.columns}

assert df.groupBy('CNPJ_BIMBO', 'CNPJ_CLIENTE', 'ID_PRODUTO', 'DT_REGISTRO').count().where('count > 1').limit(1).count() == 0, 'Duplicate source keys: CNPJ_BIMBO,CNPJ_CLIENTE,ID_PRODUTO,DT_REGISTRO'
DeltaTable.forName(spark, "cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2") \
    .alias("destino") \
    .merge(df.alias("origem"),
           "destino.CNPJ_BIMBO = origem.CNPJ_BIMBO AND "
           "destino.CNPJ_CLIENTE = origem.CNPJ_CLIENTE AND "
           "destino.ID_PRODUTO = origem.ID_PRODUTO AND "
           "destino.DT_REGISTRO = origem.DT_REGISTRO") \
    .whenNotMatchedInsert(values=_cols) \
    .execute()


# COMMAND ----------
v_query = "select * from comercial.vendas_neogrid_distribuidores_bqb where DATA >= '2025-01-01' AND DATA < '2026-01-01'"
df = read_sql_azure(query=v_query)
df = df.withColumn("storeday", from_utc_timestamp(current_timestamp(), "America/Sao_Paulo"))

_cols = {c: f"origem.{c}" for c in df.columns}

assert df.groupBy('ID').count().where('count > 1').limit(1).count() == 0, 'Duplicate source keys: ID'
DeltaTable.forName(spark, "cat_dnabb_dv.opebrapodis_lz.vendas_neogrid_distribuidores_bqb") \
    .alias("destino") \
    .merge(df.alias("origem"),
           "destino.ID = origem.ID") \
    .whenNotMatchedInsert(values=_cols) \
    .execute()



# COMMAND ----------
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
WHERE gcv.NM_CANAL = 'DISTRIBUIDORES'
  AND vppbv.GRUPO_CLI NOT IN (108)
  AND vppbv.DT_REGISTRO >= DATE'2025-01-01' AND vppbv.DT_REGISTRO < DATE'2026-01-01'
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

assert df.groupBy('DT_SELL_IN', 'CNPJ_BIMBO', 'CNPJ_DISTRIBUIDOR', 'SKU_PROD_BQ').count().where('count > 1').limit(1).count() == 0, 'Duplicate source keys: DT_SELL_IN,CNPJ_BIMBO,CNPJ_DISTRIBUIDOR,SKU_PROD_BQ'
DeltaTable.forName(spark, target_table) \
    .alias("destino") \
    .merge(df.alias("origem"),
           "destino.DT_SELL_IN = origem.DT_SELL_IN AND "
           "destino.CNPJ_BIMBO = origem.CNPJ_BIMBO AND "
           "destino.CNPJ_DISTRIBUIDOR = origem.CNPJ_DISTRIBUIDOR AND "
           "destino.SKU_PROD_BQ = origem.SKU_PROD_BQ") \
    .whenNotMatchedInsert(values=_cols) \
    .execute()
print(f"✅ {target_table} - MERGE concluído (CDC storeday [{v_data_ini} → {v_data_fim}])")


# COMMAND ----------
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

WHERE vndb.DATA >= DATE'2025-01-01' AND vndb.DATA < DATE'2026-01-01'
"""

# Lê os dados da query
df = spark.sql(query)

# ---------- TABELA DESTINO ----------
target_table = "cat_dnabb_dv.opebrapodis_cz.sellout"

# ---------- UPSERT (MERGE) via CDC storeday ----------
_cols = {c: f"origem.{c}" for c in df.columns}

assert df.groupBy('ID_NEOGRID').count().where('count > 1').limit(1).count() == 0, 'Duplicate source keys: ID_NEOGRID'
DeltaTable.forName(spark, target_table) \
    .alias("destino") \
    .merge(df.alias("origem"),
           "destino.ID_NEOGRID = origem.ID_NEOGRID") \
    .whenNotMatchedInsert(values=_cols) \
    .execute()
print(f"✅ {target_table} - MERGE concluído (CDC storeday [{v_data_ini} → {v_data_fim}])")


# COMMAND ----------
query = f"""
SELECT
    DT_SELL_IN,
    CNPJ_BIMBO,
    ID_DISTRIBUIDOR,
    DESC_DISTRIBUIDOR,
    DESC_DISTRIBUIDOR_DNA,
    CNPJ_DISTRIBUIDOR,
    SKU_DIST AS SKU_PROD_DIST,
    SKU_PROD_BQ,
    DESC_PROD_BQ,
    CODIGO_BARRAS,
    CAST(ROUND(COALESCE(SUM(BUDGET_QTDE), 0) * 1.05, 0) AS INT)  AS QTDE_FORECAST,
    CAST(ROUND(COALESCE(SUM(BUDGET_VALOR), 0) * 1.05, 0) AS BIGINT) AS VL_FORECAST,
    CAST(ROUND(COALESCE(
        SUM(COALESCE(QT_CYW_LIQ_VENDIDO, 0)) * COALESCE(QT_NA_EMB_BQ, 0)
        / NULLIF(COALESCE(CUPO_NOR_BQ, 1), 0), 0), 0) AS INT)  AS QTDE_SELL_IN,
    CAST(ROUND(COALESCE(SUM(VL_CYW_LIQ_VENDIDO), 0), 0) AS BIGINT) AS VL_SELL_IN,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')                                        AS storeday
FROM cat_dnabb_dv.opebrapodis_cz.sellin
WHERE DT_SELL_IN >= DATE'2025-01-01' AND DT_SELL_IN < DATE'2026-01-01'
  AND CNPJ_BIMBO <> 0
GROUP BY
    DT_SELL_IN, CNPJ_BIMBO, ID_DISTRIBUIDOR, DESC_DISTRIBUIDOR, DESC_DISTRIBUIDOR_DNA,
    CNPJ_DISTRIBUIDOR, SKU_DIST, SKU_PROD_BQ, DESC_PROD_BQ, CODIGO_BARRAS,
    QT_NA_EMB_BQ, CUPO_NOR_BQ
HAVING SUM(COALESCE(BUDGET_QTDE, 0)) <> 0
    OR SUM(COALESCE(BUDGET_VALOR, 0)) <> 0
    OR SUM(COALESCE(QT_CYW_LIQ_VENDIDO, 0)) <> 0
    OR SUM(COALESCE(VL_CYW_LIQ_VENDIDO, 0)) <> 0
"""

# Lê os dados da query
df = spark.sql(query)

# ---------- TABELA DESTINO ----------
target_table = "cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellin"

# ---------- UPSERT (MERGE) ou CREATE na primeira execução ----------

_cols = {c: f"origem.{c}" for c in df.columns}
assert df.groupBy('DT_SELL_IN', 'CNPJ_BIMBO', 'CNPJ_DISTRIBUIDOR', 'SKU_PROD_BQ').count().where('count > 1').limit(1).count() == 0, 'Duplicate source keys: DT_SELL_IN,CNPJ_BIMBO,CNPJ_DISTRIBUIDOR,SKU_PROD_BQ'
DeltaTable.forName(spark, target_table) \
    .alias("destino") \
    .merge(df.alias("origem"),
           "destino.DT_SELL_IN = origem.DT_SELL_IN AND "
           "destino.CNPJ_BIMBO = origem.CNPJ_BIMBO AND "
           "destino.CNPJ_DISTRIBUIDOR = origem.CNPJ_DISTRIBUIDOR AND "
           "destino.SKU_PROD_BQ = origem.SKU_PROD_BQ") \
    .whenNotMatchedInsert(values=_cols) \
    .execute()
print(f"✅ {target_table} - MERGE concluído [{v_data_ini} → {v_data_fim}]")


# COMMAND ----------
query_sm = f"""
SELECT
    DATA_SELL_OUT,
    CNPJ_DISTRIBUIDOR,
    ID_DISTRIBUIDOR,
    DESC_DISTRIBUIDOR,
    DESC_DISTRIBUIDOR_DNA,
    CNPJ_CLIENTE,
    DESC_CLIENTE,
    SKU_PROD_DIST,
    DESC_PROD_ARQUIVO_DIST,
    CODIGO_BARRAS,
    SKU_PROD_BQ,
    DESC_PROD_BQ,
    CHAVE_DISTRIB_SKU,
    CHAVE_DISTRIB_CLIENTE,
        -- Quantidade pacote sell-out
        COALESCE(SUM(CASE WHEN NATUREZA_OPER = 'Venda' THEN QUANTIDADE ELSE -QUANTIDADE END), 0)
            AS QTDE_PCT_SELL_OUT,
        -- Quantidade unitário sell-out (condicional: EAN usa QTD_PAES_PACOTE, DUN usa QT_NA_EMB_BQ)
        COALESCE(SUM(CASE WHEN NATUREZA_OPER = 'Venda' THEN QUANTIDADE ELSE -QUANTIDADE END), 0)
            * CASE WHEN TIPO_CODIGO_DIST = 'DUN' THEN QT_NA_EMB_BQ ELSE QTD_PAES_PACOTE END
            AS QTDE_UNITARIO_SELL_OUT,
        -- Quantidade dúzia sell-out (calculada na CZ via vw_produtos_distribuidores_bqb)
        SUM(QTDE_DUZIA_SELL_OUT)
            AS QTDE_DUZIA_SELL_OUT,
    -- Valor sell-out
    ROUND(COALESCE(SUM(CASE WHEN NATUREZA_OPER = 'Venda' THEN VALOR_LIQUIDO ELSE -VALOR_LIQUIDO END), 0), 2)
        AS VL_SELL_OUT,
    -- Linhas de venda: VL_META = 0 (meta fica nas linhas dedicadas 'META')
    CAST(0 AS BIGINT) AS VL_META,
    CAST(0 AS INT) AS POSITIVACAO_META,
    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo') AS storeday
FROM cat_dnabb_dv.opebrapodis_cz.sellout
WHERE DATA_SELL_OUT >= DATE'2025-01-01' AND DATA_SELL_OUT < DATE'2026-01-01'
GROUP BY
    DATA_SELL_OUT,
    CNPJ_DISTRIBUIDOR,
    ID_DISTRIBUIDOR,
    DESC_DISTRIBUIDOR,
    DESC_DISTRIBUIDOR_DNA,
    CNPJ_CLIENTE,
    DESC_CLIENTE,
    SKU_PROD_DIST,
    DESC_PROD_ARQUIVO_DIST,
    CODIGO_BARRAS,
    SKU_PROD_BQ,
    DESC_PROD_BQ,
    CHAVE_DISTRIB_SKU,
    CHAVE_DISTRIB_CLIENTE,
    QTD_PAES_PACOTE,
    QT_NA_EMB_BQ,
    CUPO_NOR_BQ,
    TIPO_CODIGO_DIST
"""


df_sm = spark.sql(query_sm)
target_table_sm = "cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellout"

# ---------- UPSERT (MERGE) ----------
# MERGE key inclui CNPJ_CLIENTE e SKU_PROD_DIST:
# linhas META têm CNPJ_CLIENTE='META' + SKU_PROD_DIST='META' → não conflitam com vendas reais
_cols_sm = {c: f"origem.{c}" for c in df_sm.columns}
assert df_sm.groupBy('DATA_SELL_OUT', 'CNPJ_DISTRIBUIDOR', 'CNPJ_CLIENTE', 'SKU_PROD_DIST').count().where('count > 1').limit(1).count() == 0, 'Duplicate source keys: DATA_SELL_OUT,CNPJ_DISTRIBUIDOR,CNPJ_CLIENTE,SKU_PROD_DIST'
DeltaTable.forName(spark, target_table_sm) \
    .alias("destino") \
    .merge(df_sm.alias("origem"),
           "destino.DATA_SELL_OUT = origem.DATA_SELL_OUT AND "
           "destino.CNPJ_DISTRIBUIDOR = origem.CNPJ_DISTRIBUIDOR AND "
           "destino.CNPJ_CLIENTE = origem.CNPJ_CLIENTE AND "
           "destino.SKU_PROD_DIST = origem.SKU_PROD_DIST") \
    .whenNotMatchedInsert(values=_cols_sm) \
    .execute()
print(f"✅ {target_table_sm} - MERGE concluído [{v_data_ini} → {v_data_fim}]")

