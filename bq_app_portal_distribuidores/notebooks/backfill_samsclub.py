# Databricks notebook source
from delta.tables import DeltaTable

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
WHERE gcv.COD_GR_CLIENTE = 99
  AND vppbv.GRUPO_CLI NOT IN (108)
  AND vppbv.DT_REGISTRO >= DATE'2025-01-01'
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

keys = ['DT_SELL_IN', 'CNPJ_BIMBO', 'CNPJ_DISTRIBUIDOR', 'SKU_PROD_BQ']
assert df.count() > 0, 'Nenhum dado Sam’s Club encontrado na landing'
assert df.groupBy(*keys).count().where('count > 1').limit(1).count() == 0, 'Chaves duplicadas na origem CZ'
existing = spark.table(target_table)
assert df.alias('s').join(existing.alias('t'), keys, 'inner').where('t.ID_DISTRIBUIDOR <> 99').limit(1).count() == 0, 'Chave pertence a outro distribuidor'
DeltaTable.forName(spark, target_table).alias('destino').merge(df.alias('origem'), ' AND '.join(f'destino.{k} = origem.{k}' for k in keys)).whenMatchedUpdate(set=_cols).whenNotMatchedInsert(values=_cols).execute()
print('CZ Sams Club:', df.count())

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
WHERE ID_DISTRIBUIDOR = 99 AND CNPJ_BIMBO <> 0
GROUP BY
    DT_SELL_IN, CNPJ_BIMBO, ID_DISTRIBUIDOR, DESC_DISTRIBUIDOR, DESC_DISTRIBUIDOR_DNA,
    CNPJ_DISTRIBUIDOR, SKU_DIST, SKU_PROD_BQ, DESC_PROD_BQ, CODIGO_BARRAS,
    QT_NA_EMB_BQ, CUPO_NOR_BQ
"""

# Lê os dados da query
df = spark.sql(query)

# ---------- TABELA DESTINO ----------
target_table = "cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellin"

# ---------- UPSERT (MERGE) ou CREATE na primeira execução ----------

_cols = {c: f"origem.{c}" for c in df.columns}
keys = ['DT_SELL_IN', 'CNPJ_BIMBO', 'CNPJ_DISTRIBUIDOR', 'SKU_PROD_BQ']
assert df.count() > 0, 'Nenhum dado Sam’s Club encontrado na CZ'
assert df.groupBy(*keys).count().where('count > 1').limit(1).count() == 0, 'Chaves duplicadas na origem SZ'
existing = spark.table(target_table)
assert df.alias('s').join(existing.alias('t'), keys, 'inner').where('t.ID_DISTRIBUIDOR <> 99').limit(1).count() == 0, 'Chave pertence a outro distribuidor'
DeltaTable.forName(spark, target_table).alias('destino').merge(df.alias('origem'), ' AND '.join(f'destino.{k} = origem.{k}' for k in keys)).whenMatchedUpdate(set=_cols).whenNotMatchedInsert(values=_cols).execute()
print('SZ Sams Club:', df.count())
