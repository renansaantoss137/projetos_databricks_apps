import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "f4a2e26b8410f1e3"

query_oc_top = """
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
    NUMERO_OC AS numero_oc,
    NOME_FORNECEDOR AS nome_fornecedor,
    UNIDADE AS unidade_flex,
    LOCAL AS local_raw,
    CENTRO_CUSTO AS centro_custo,
    DS_ITEM AS ds_item,
    ROUND(VALOR_LIQUIDO_BRL, 2) AS valor_liquido_brl
FROM base
WHERE (planta IS NULL OR TRIM(planta) = '' OR TRIM(planta) = 'Não identificada')
  AND NUMERO_OC != 'Nota sem OC'
ORDER BY VALOR_LIQUIDO_BRL DESC
LIMIT 5;
"""

res = w.statement_execution.execute_statement(
    warehouse_id=wh_id,
    statement=query_oc_top,
    wait_timeout="50s"
)

if res.result and res.result.data_array:
    cols = [c.name for c in res.manifest.schema.columns]
    for r in res.result.data_array:
        print(dict(zip(cols, r)), flush=True)
