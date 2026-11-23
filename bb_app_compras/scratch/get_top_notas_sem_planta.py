import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "f4a2e26b8410f1e3"

query_top_nfs = """
WITH base AS (
    SELECT 
        *,
        REGEXP_REPLACE(LOCAL, '^[0-9]+_(BBR_|BQB_)?', '') AS planta
    FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri
    WHERE YEAR(DATA_LANCAMENTO) = 2026
      AND UPPER(TRIM(COALESCE(GRUPO_COMPRAS, ''))) = 'INDIRETOS'
      AND (NOTA_FISCAL IS NULL OR (
          UPPER(NOTA_FISCAL) NOT LIKE '%ARKER%'
          AND UPPER(NOTA_FISCAL) NOT LIKE '%RGB%'
          AND UPPER(NOTA_FISCAL) NOT LIKE 'ADV%'
          AND UPPER(NOTA_FISCAL) NOT LIKE '%FOPAG%'
          AND UPPER(NOTA_FISCAL) NOT LIKE '%FISCAL%'
      ))
)
SELECT 
    CAST(NUMERO_RI AS BIGINT) AS numero_ri,
    NOTA_FISCAL AS nota_fiscal,
    SERIE AS serie,
    EMPRESA AS empresa,
    CNPJ_BIMBO AS cnpj_bimbo,
    NOME_FORNECEDOR AS nome_fornecedor,
    CNPJ_FORNECEDOR AS cnpj_fornecedor,
    NUMERO_OC AS numero_oc,
    UNIDADE AS unidade_flex,
    LOCAL AS local_raw,
    LOCAL_FORNECEDOR AS local_fornecedor,
    CENTRO_CUSTO AS centro_custo,
    CONTA_CONTABIL AS conta_contabil,
    COMPRADOR AS comprador,
    DEPARTAMENTO_COMPRADOR AS departamento_comprador,
    DATA_LANCAMENTO AS data_lancamento,
    DT_NOTA AS dt_nota,
    CATEGORIA_ITEM AS categoria_item,
    COUNT(*) AS total_linhas,
    ROUND(SUM(VALOR_LIQUIDO_BRL), 2) AS total_liquido_brl,
    ROUND(SUM(VALOR_NOTA_BRL), 2) AS total_nota_brl,
    COLLECT_SET(DS_ITEM)[0] AS exemplo_descricao_item
FROM base
WHERE (planta IS NULL OR TRIM(planta) = '' OR TRIM(planta) = 'Não identificada')
GROUP BY 
    CAST(NUMERO_RI AS BIGINT),
    NOTA_FISCAL,
    SERIE,
    EMPRESA,
    CNPJ_BIMBO,
    NOME_FORNECEDOR,
    CNPJ_FORNECEDOR,
    NUMERO_OC,
    UNIDADE,
    LOCAL,
    LOCAL_FORNECEDOR,
    CENTRO_CUSTO,
    CONTA_CONTABIL,
    COMPRADOR,
    DEPARTAMENTO_COMPRADOR,
    DATA_LANCAMENTO,
    DT_NOTA,
    CATEGORIA_ITEM
ORDER BY total_liquido_brl DESC
LIMIT 15;
"""

res = w.statement_execution.execute_statement(
    warehouse_id=wh_id,
    statement=query_top_nfs,
    wait_timeout="50s"
)

if res.result and res.result.data_array:
    cols = [c.name for c in res.manifest.schema.columns]
    rows = [dict(zip(cols, r)) for r in res.result.data_array]
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    with open("scratch/top_15_notas_sem_planta.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
else:
    print("Status/Error:", res.status)
