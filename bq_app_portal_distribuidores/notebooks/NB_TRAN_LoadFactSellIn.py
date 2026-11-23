# Databricks notebook source
# DBTITLE 1,Variaveis
import datetime as md_date
from delta.tables import DeltaTable
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
    # MODO INCREMENTAL: última atualização na CZ sell-in - 5 dias
    _max_row = spark.sql("""
        SELECT MAX(CAST(storeday AS DATE)) AS max_dt
        FROM cat_dnabb_dv.opebrapodis_cz.sellin
    """).first()
    _max_dt = _max_row["max_dt"] if _max_row and _max_row["max_dt"] else date.today()
    v_data_ini = (_max_dt - timedelta(days=5)).strftime("%Y-%m-%d")
    v_data_fim = date.today().strftime("%Y-%m-%d")
    print(f"🔄 Modo incremental: última atualização CZ={_max_dt} → janela [{v_data_ini} → {v_data_fim}]")

# COMMAND ----------

# DBTITLE 1,Leitura e Carga dos dados CZ -> SZ
from delta.tables import DeltaTable
from datetime import date, timedelta

# ---------- QUERY DE ORIGEM COM FILTRO DE PERÍODO ----------
# Alterações v2 (2026-08-03):
#   1. Adicionado CNPJ_BIMBO
#   2. Adicionado SKU_DIST
#   3. Renomeado CNPJ_CLIENTE → CNPJ_DISTRIBUIDOR
# Alterações v3 (2026-08-04):
#   4. Filtro CNPJ_BIMBO <> 0 (linhas sem planta não têm dados)
#   5. Linhas zeradas são mantidas para atualizar registros previamente não zerados.
#   6. MERGE key inclui CNPJ_BIMBO (evita conflito de múltiplas linhas)
# Alterações v4 (2026-10-21):
#   7. WHERE inclui datas futuras (>= current_date) para capturar budget
#      de semanas/meses futuros cujo storeday ficou fora da janela CDC

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
WHERE (
    DT_SELL_IN IN (
        SELECT DISTINCT DT_SELL_IN
        FROM cat_dnabb_dv.opebrapodis_cz.sellin
        WHERE CAST(storeday AS DATE) BETWEEN '{v_data_ini}' AND '{v_data_fim}'
    )
    OR DT_SELL_IN >= current_date()
  )
  AND CNPJ_BIMBO <> 0
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
print(f"✅ {target_table} - MERGE concluído [{v_data_ini} → {v_data_fim}]")

# COMMAND ----------

# DBTITLE 1,Validação Anti-Duplicata
# ============================================================
# VALIDAÇÃO PÓS-MERGE: Detecta e corrige duplicatas automaticamente
# Mantém apenas o registro com storeday mais recente por MERGE key
# ============================================================
from pyspark.sql.window import Window
from pyspark.sql import functions as F

_table = target_table
_keys = ["DT_SELL_IN", "CNPJ_BIMBO", "CNPJ_DISTRIBUIDOR", "SKU_PROD_BQ"]

_df = spark.read.table(_table)
_total = _df.count()
_distinct = _df.select(_keys).distinct().count()
_dups = _total - _distinct

if _dups > 0:
    print(f"⚠️ {_dups:,} duplicatas detectadas em {_table}. Corrigindo...")
    _w = Window.partitionBy(*_keys).orderBy(F.col("storeday").desc())
    _to_del = _df.withColumn("_rn", F.row_number().over(_w)).filter("_rn > 1").select(*_keys, "storeday")
    _cond = " AND ".join([f"t.`{k}` = s.`{k}`" for k in _keys]) + " AND t.storeday = s.storeday"
    DeltaTable.forName(spark, _table).alias("t").merge(_to_del.alias("s"), _cond).whenMatchedDelete().execute()
    _after = spark.read.table(_table).count()
    print(f"✅ Dedup concluído: {_total:,} → {_after:,} (removidas: {_total - _after:,})")
else:
    print(f"✅ {_table} — sem duplicatas ({_total:,} registros, {_distinct:,} chaves)")
