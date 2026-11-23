# Databricks notebook source
from delta.tables import DeltaTable

# COMMAND ----------
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
    AND GCV.COD_GR_CLIENTE = 99
    AND I.DB_PEDI_PRODUTO <> '999999917'
    AND I.DB_PEDI_SITUACAO IN (0, 1, 2, 4, 9)
    AND COALESCE(I.STATUS_REGISTRO, 'ATIVO') = 'ATIVO'
    -- Alteração (2026-10-26): CDC também pelo cabeçalho (P.storeday) — captura mudanças só no cabeçalho (ex.: previsão de entrega)

"""

# Lê os dados da query
df = spark.sql(query)

# ---------- TABELA DESTINO ----------
target_table = "cat_dnabb_dv.opebrapodis_cz.pedidos"

# ---------- UPSERT (MERGE) via CDC storeday ----------
_cols = {c: f"origem.{c}" for c in df.columns}

keys = ['DB_PEDI_PEDIDO', 'DB_PEDI_SEQUENCIA', 'DB_PED_DT_EMISSAO']
assert df.count() > 0, 'Sem pedidos de Sam’s Club'
assert df.groupBy(*keys).count().where('count > 1').limit(1).count() == 0, 'Chaves duplicadas CZ pedidos'
existing = spark.table(target_table)
assert df.alias('s').join(existing.alias('t'), keys, 'inner').where("CAST(t.DB_TBATV_CODIGO AS STRING) <> '99'").limit(1).count() == 0, 'Chave pertence a outro distribuidor'
DeltaTable.forName(spark, target_table).alias('destino').merge(df.alias('origem'), ' AND '.join(f'destino.{k} = origem.{k}' for k in keys)).whenMatchedUpdate(set=_cols).whenNotMatchedInsert(values=_cols).execute()
print('CZ pedidos:',df.count())

# COMMAND ----------
query = f"""
-- ========== VALOR REAL DA NOTA (mesma regra do Power BI: SUM(VL_CYW_LIQ_VENDIDO)) ==========
-- Origem: LZ vendas_pedidos_ppto_bq_v2, por pedido + produto + CNPJ do cliente.
-- Notas que atendem mais de um pedido (NUMERO_PEDIDO = 'a|b') são divididas igualmente entre os pedidos.
WITH nf_raw AS (
    SELECT
        NUMERO_PEDIDO,
        CAST(ID_PRODUTO AS STRING)      AS NF_PRODUTO,
        CAST(CNPJ_CLIENTE AS BIGINT)    AS NF_CNPJ_CLI,
        VL_CYW_LIQ_VENDIDO              AS NF_VL_LIQ,
        VL_CYW_BRUTO_VENDIDO            AS NF_VL_BRUTO,
        SIZE(SPLIT(NUMERO_PEDIDO, '[|]')) AS NF_N_PED
    FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2
    WHERE NUMERO_PEDIDO IS NOT NULL
      AND VL_CYW_LIQ_VENDIDO IS NOT NULL AND VL_CYW_LIQ_VENDIDO <> 0
),
nf AS (
    SELECT
        TRY_CAST(TRIM(pe) AS BIGINT)    AS NF_PEDIDO,
        NF_PRODUTO,
        NF_CNPJ_CLI,
        SUM(NF_VL_LIQ / NF_N_PED)       AS NF_VL_LIQ,
        SUM(NF_VL_BRUTO / NF_N_PED)     AS NF_VL_BRUTO
    FROM nf_raw LATERAL VIEW EXPLODE(SPLIT(NUMERO_PEDIDO, '[|]')) t AS pe
    GROUP BY 1, 2, 3
)
SELECT
    -- ========== CNPJS E IDENTIFICAÇÃO ==========
    CASE
        WHEN DB_PED_EMPRESA = 'QRA' THEN '35402759011110'
        WHEN DB_PED_EMPRESA = 'QRC' THEN '35402759011209'
        WHEN DB_PED_EMPRESA = 'QRB' THEN '35402759011381'
        WHEN DB_PED_EMPRESA = 'QRE' THEN '35402759011462'
        WHEN DB_PED_EMPRESA = 'QRD' THEN '35402759011543'
        WHEN DB_PED_EMPRESA = 'QRF' THEN '35402759011624'
        WHEN DB_PED_EMPRESA = 'QRJ' THEN '35402759011977'
        ELSE ''
    END AS CNPJ_BIMBO,
    CASE
        WHEN DB_CLI_CGCMF = '099999999999999' THEN '0'
        WHEN DB_CLI_CGCMF = '99999999999999' THEN '0'
        ELSE DB_CLI_CGCMF
    END AS CNPJ_DISTRIBUIDOR,
    DB_TBATV_CODIGO AS ID_DISTRIBUIDOR,
    DESC_DISTRIBUIDOR,
    GRUPO_CLIENTE_DESC AS DESC_DISTRIBUIDOR_DNA,

    -- ========== DATAS ==========
    CAST(DB_PED_DT_EMISSAO AS DATE) AS DATA_EMISSAO_PEDIDO,
    CAST(DB_PED_DT_PREVENT AS DATE) AS DATA_PREVISAO_ENTREGA,
    CAST(DB_PEDI_ATD_DATA AS DATE) AS DATA_ENTREGA,

    -- ========== PEDIDO E PRODUTO ==========
    DB_PEDI_PEDIDO AS NUMERO_PEDIDO,
    DB_PEDI_SEQUENCIA,
    DB_PEDI_PRODUTO AS SKU_PROD_BQ,
    SKU_DISTRIB AS SKU_PROD_DIST,
    DESC_PRODUTO_ARQUIVO_DIST AS DESC_SKU_DIST,
    DESCRICAO_PRODUTO AS DESC_PROD_BQ,
    DB_PEDI_SITUACAO AS ID_STATUS_PEDIDO,
    CASE
        WHEN DB_PEDI_SITUACAO = 0 THEN 'ABERTO'
        WHEN DB_PEDI_SITUACAO = 1 THEN 'FATURADO PARCIAL'
        WHEN DB_PEDI_SITUACAO = 2 THEN 'FATURADO'
        WHEN DB_PEDI_SITUACAO = 9 THEN 'CANCELADO'
        ELSE 'VERIFICAR'
    END AS DESC_STATUS_PEDIDO,

    -- ========== NOTA FISCAL ==========
    LEFT(NULLIF(DB_PEDI_ATD_DCTO, ''), NULLIF(INSTR(DB_PEDI_ATD_DCTO, '-') - 1, -1)) AS NOTA_FISCAL,
    SUBSTRING(DB_PEDI_ATD_DCTO, INSTR(DB_PEDI_ATD_DCTO, '-') + 1, LENGTH(DB_PEDI_ATD_DCTO)) AS SERIE,

    -- ========== QUANTIDADES EM CAIXA ==========
    CAST(DB_PEDI_QTDE_SOLIC AS INT) AS QTDE_PEDIDO_CX,
    CAST(DB_PEDI_QTDE_ATEND AS INT) AS QTDE_PEDIDO_ATENDIDO_CX,
    CAST(DB_PEDI_QTDE_CANC AS INT) AS QTDE_PEDIDO_CANCELADO_CX,

    -- ========== QUANTIDADE EM ABERTO CAIXA (ZERA SOMENTE CANCELADO - STATUS 9) ==========
    CAST(CASE
        WHEN DB_PEDI_SITUACAO = 9 THEN 0
        ELSE (DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC)
    END AS INT) AS QTDE_PEDIDO_ABERTO_CX,

    -- ========== COLUNAS DE CONVERSÃO ==========
    QT_NA_EMB_BQ,
    CAST(CUPO_NOR_BQ AS INT) AS CUPO_NOR_BQ,

    -- ========== QUANTIDADES EM DÚZIA ==========
    ROUND(COALESCE(
        (COALESCE(DB_PEDI_QTDE_SOLIC, 0) * COALESCE(QT_NA_EMB_BQ, 0)) / NULLIF(COALESCE(CUPO_NOR_BQ, 1), 0),
        0
    ), 0) AS QTDE_PEDIDO_DZ,
    ROUND(COALESCE(
        (COALESCE(DB_PEDI_QTDE_ATEND, 0) * COALESCE(QT_NA_EMB_BQ, 0)) / NULLIF(COALESCE(CUPO_NOR_BQ, 1), 0),
        0
    ), 0) AS QTDE_PEDIDO_ATENDIDO_DZ,
    ROUND(COALESCE(
        (COALESCE(DB_PEDI_QTDE_CANC, 0) * COALESCE(QT_NA_EMB_BQ, 0)) / NULLIF(COALESCE(CUPO_NOR_BQ, 1), 0),
        0
    ), 0) AS QTDE_PEDIDO_CANCELADO_DZ,

    -- ========== QUANTIDADE EM ABERTO DÚZIA (ZERA SOMENTE CANCELADO - STATUS 9) ==========
    ROUND(CASE
        WHEN DB_PEDI_SITUACAO = 9 THEN 0
        ELSE COALESCE(
            ((DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC) * COALESCE(QT_NA_EMB_BQ, 0)) / NULLIF(COALESCE(CUPO_NOR_BQ, 1), 0),
            0
        )
    END, 0) AS QTDE_PEDIDO_ABERTO_DZ,

    -- ========== QUANTIDADES EM UNIDADE ==========
    ROUND(COALESCE(DB_PEDI_QTDE_SOLIC, 0) * COALESCE(QT_NA_EMB_BQ, 0), 0) AS QTDE_PEDIDO_UN,
    ROUND(COALESCE(DB_PEDI_QTDE_ATEND, 0) * COALESCE(QT_NA_EMB_BQ, 0), 0) AS QTDE_PEDIDO_ATENDIDO_UN,
    ROUND(COALESCE(DB_PEDI_QTDE_CANC, 0) * COALESCE(QT_NA_EMB_BQ, 0), 0) AS QTDE_PEDIDO_CANCELADO_UN,
    ROUND(CASE
        WHEN DB_PEDI_SITUACAO = 9 THEN 0
        ELSE (COALESCE(DB_PEDI_QTDE_SOLIC, 0) - COALESCE(DB_PEDI_QTDE_ATEND, 0) - COALESCE(DB_PEDI_QTDE_CANC, 0)) * COALESCE(QT_NA_EMB_BQ, 0)
    END, 0) AS QTDE_PEDIDO_ABERTO_UN,

    -- ========== PREÇO ==========
    ROUND(DB_PEDI_PRECO_LIQ, 0) AS PRECO_UNIT_BRUTO,

    -- ========== VALORES BRUTOS ==========
    ROUND(DB_PEDI_QTDE_SOLIC * DB_PEDI_PRECO_LIQ, 0) AS VL_PEDIDO_BRUTO,
    ROUND(DB_PEDI_PRECO_UNIT * DB_PEDI_QTDE_ATEND, 0) AS VL_PEDIDO_ATENDIDO_BRUTO,
    ROUND(DB_PEDI_PRECO_UNIT * DB_PEDI_QTDE_CANC, 0) AS VL_PEDIDO_CANCELADO_BRUTO,
    ROUND(CASE
        WHEN DB_PEDI_SITUACAO = 9 THEN 0
        ELSE ((DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC) * DB_PEDI_PRECO_LIQ)
    END, 0) AS VL_PEDIDO_ABERTO_BRUTO,

    -- ========== ICMS ==========
    ROUND(COALESCE(DB_PEDI_VU_ICMS, 0), 0) AS VL_ICMS_BRUTO,
    ROUND(COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_ATEND / NULLIF(DB_PEDI_QTDE_SOLIC, 0)), 0) AS VL_ICMS_ATENDIDO,
    ROUND(COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_CANC / NULLIF(DB_PEDI_QTDE_SOLIC, 0)), 0) AS VL_ICMS_CANCELADO,
    ROUND(CASE
        WHEN DB_PEDI_SITUACAO = 9 THEN 0
        ELSE (COALESCE(DB_PEDI_VU_ICMS, 0) * ((DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC) / NULLIF(DB_PEDI_QTDE_SOLIC, 0)))
    END, 0) AS VL_ICMS_ABERTO,

    -- ========== PIS/COFINS ==========
    ROUND((
        (DB_PEDI_QTDE_SOLIC * DB_PEDI_PRECO_LIQ)
        - COALESCE(DB_PEDI_VU_ICMS, 0)
    ) * 0.0925, 0) AS VL_PIS_COFINS_PEDIDO,
    ROUND(CASE
        WHEN DB_PEDI_QTDE_SOLIC = 0 THEN 0
        ELSE (
            ((DB_PEDI_QTDE_ATEND * DB_PEDI_PRECO_LIQ)
            - (COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_ATEND / DB_PEDI_QTDE_SOLIC))
            ) * 0.0925
        )
    END, 0) AS VL_PIS_COFINS_ATENDIDO,
    ROUND(CASE
        WHEN DB_PEDI_QTDE_SOLIC = 0 THEN 0
        ELSE (
            ((DB_PEDI_QTDE_CANC * DB_PEDI_PRECO_LIQ)
            - (COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_CANC / DB_PEDI_QTDE_SOLIC))
            ) * 0.0925
        )
    END, 0) AS VL_PIS_COFINS_CANCELADO,
    ROUND(CASE
        WHEN DB_PEDI_SITUACAO = 9 THEN 0
        WHEN DB_PEDI_QTDE_SOLIC = 0 THEN 0
        ELSE (
            (((DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC) * DB_PEDI_PRECO_LIQ)
            - (COALESCE(DB_PEDI_VU_ICMS, 0) * ((DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC) / DB_PEDI_QTDE_SOLIC))
            ) * 0.0925
        )
    END, 0) AS VL_PIS_COFINS_ABERTO,

    -- ========== VALORES LÍQUIDOS ==========
    ROUND((
        (DB_PEDI_QTDE_SOLIC * DB_PEDI_PRECO_LIQ)
        - COALESCE(DB_PEDI_VU_ICMS, 0)
        - (
            (DB_PEDI_QTDE_SOLIC * DB_PEDI_PRECO_LIQ)
            - COALESCE(DB_PEDI_VU_ICMS, 0)
        ) * 0.0925
    ), 0) AS VL_PEDIDO_LIQUIDO,
    ROUND(CASE
        WHEN DB_PEDI_QTDE_SOLIC = 0 THEN 0
        ELSE (
            (DB_PEDI_QTDE_ATEND * DB_PEDI_PRECO_LIQ)
            - (COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_ATEND / DB_PEDI_QTDE_SOLIC))
            - (
                ((DB_PEDI_QTDE_ATEND * DB_PEDI_PRECO_LIQ)
                - (COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_ATEND / DB_PEDI_QTDE_SOLIC))
                ) * 0.0925
            )
        )
    END, 0) AS VL_PEDIDO_ATENDIDO_LIQUIDO,
    ROUND(CASE
        WHEN DB_PEDI_QTDE_SOLIC = 0 THEN 0
        ELSE (
            (DB_PEDI_QTDE_CANC * DB_PEDI_PRECO_LIQ)
            - (COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_CANC / DB_PEDI_QTDE_SOLIC))
            - (
                ((DB_PEDI_QTDE_CANC * DB_PEDI_PRECO_LIQ)
                - (COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_CANC / DB_PEDI_QTDE_SOLIC))
                ) * 0.0925
            )
        )
    END, 0) AS VL_PEDIDO_CANCELADO_LIQUIDO,
    ROUND(CASE
        WHEN DB_PEDI_SITUACAO = 9 THEN 0
        WHEN DB_PEDI_QTDE_SOLIC = 0 THEN 0
        ELSE (
            ((DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC) * DB_PEDI_PRECO_LIQ)
            - (COALESCE(DB_PEDI_VU_ICMS, 0) * ((DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC) / DB_PEDI_QTDE_SOLIC))
            - (
                (((DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC) * DB_PEDI_PRECO_LIQ)
                - (COALESCE(DB_PEDI_VU_ICMS, 0) * ((DB_PEDI_QTDE_SOLIC - DB_PEDI_QTDE_ATEND - DB_PEDI_QTDE_CANC) / DB_PEDI_QTDE_SOLIC))
                ) * 0.0925
            )
        )
    END, 0) AS VL_PEDIDO_ABERTO_LIQUIDO,

    -- ========== VALOR TOTAL LÍQUIDO (REGRA PORTAL) ==========
    -- FATURADO PARCIAL (1): somente o que foi faturado (atendido líquido)
    -- ABERTO (0), FATURADO (2), CANCELADO (9): valor total do pedido (líquido)
    ROUND(CASE
        WHEN DB_PEDI_SITUACAO = 1 THEN
            CASE
                WHEN DB_PEDI_QTDE_SOLIC = 0 THEN 0
                ELSE (
                    (DB_PEDI_QTDE_ATEND * DB_PEDI_PRECO_LIQ)
                    - (COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_ATEND / DB_PEDI_QTDE_SOLIC))
                    - (
                        ((DB_PEDI_QTDE_ATEND * DB_PEDI_PRECO_LIQ)
                        - (COALESCE(DB_PEDI_VU_ICMS, 0) * (DB_PEDI_QTDE_ATEND / DB_PEDI_QTDE_SOLIC))
                        ) * 0.0925
                    )
                )
            END
        ELSE (
            (DB_PEDI_QTDE_SOLIC * DB_PEDI_PRECO_LIQ)
            - COALESCE(DB_PEDI_VU_ICMS, 0)
            - (
                (DB_PEDI_QTDE_SOLIC * DB_PEDI_PRECO_LIQ)
                - COALESCE(DB_PEDI_VU_ICMS, 0)
            ) * 0.0925
        )
    END, 0) AS VL_PEDIDO_TOTAL_LIQUIDO,

    -- ========== VALOR REAL DA NOTA FISCAL (igual ao Power BI) ==========
    -- Preenchido só para linhas faturadas (1, 2) que já têm nota; NULL caso contrário
    CASE WHEN DB_PEDI_SITUACAO IN (1, 2) THEN ROUND(nf.NF_VL_LIQ, 2)   END AS VL_FATURADO_LIQUIDO_NF,
    CASE WHEN DB_PEDI_SITUACAO IN (1, 2) THEN ROUND(nf.NF_VL_BRUTO, 2) END AS VL_FATURADO_BRUTO_NF,

    from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo') AS storeday

FROM cat_dnabb_dv.opebrapodis_cz.pedidos p
LEFT JOIN nf
    ON  nf.NF_PEDIDO   = TRY_CAST(p.DB_PEDI_PEDIDO AS BIGINT)
    AND nf.NF_PRODUTO  = CAST(p.DB_PEDI_PRODUTO AS STRING)
    AND nf.NF_CNPJ_CLI = TRY_CAST(p.DB_CLI_CGCMF AS BIGINT)
WHERE CAST(p.DB_TBATV_CODIGO AS STRING) = '99'
"""

# Lê os dados da query
df = spark.sql(query)

# ---------- TABELA DESTINO ----------
target_table = "cat_dnabb_dv.opebrapodis_sz.tbl_factdy_order"

# ---------- UPSERT (MERGE) ou CREATE na primeira execução ----------

_cols = {c: f"origem.{c}" for c in df.columns}
keys = ['NUMERO_PEDIDO', 'DB_PEDI_SEQUENCIA', 'DATA_EMISSAO_PEDIDO']
assert df.count() > 0, 'Sem pedidos na CZ'
assert df.groupBy(*keys).count().where('count > 1').limit(1).count() == 0, 'Chaves duplicadas SZ pedidos'
existing = spark.table(target_table)
assert df.alias('s').join(existing.alias('t'), keys, 'inner').where("CAST(t.ID_DISTRIBUIDOR AS STRING) <> '99'").limit(1).count() == 0, 'Chave pertence a outro distribuidor'
DeltaTable.forName(spark, target_table).alias('destino').merge(df.alias('origem'), ' AND '.join(f'destino.{k} = origem.{k}' for k in keys)).whenMatchedUpdate(set=_cols).whenNotMatchedInsert(values=_cols).execute()
print('SZ pedidos:',df.count())
