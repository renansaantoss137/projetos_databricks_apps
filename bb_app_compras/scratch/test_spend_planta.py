import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "f4a2e26b8410f1e3"

query_spend = """
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
    COALESCE(NULLIF(TRIM(planta), ''), 'Não identificada') AS planta_calc,
    ROUND(SUM(VALOR_LIQUIDO_BRL) / 1e6, 1) AS spend_mi,
    ROUND(SUM(VALOR_LIQUIDO_BRL) * 100.0 / SUM(SUM(VALOR_LIQUIDO_BRL)) OVER(), 0) AS pct
FROM base
GROUP BY COALESCE(NULLIF(TRIM(planta), ''), 'Não identificada')
HAVING SUM(VALOR_LIQUIDO_BRL) > 0
ORDER BY spend_mi DESC
LIMIT 12;
"""

res = w.statement_execution.execute_statement(
    warehouse_id=wh_id,
    statement=query_spend,
    wait_timeout="50s"
)
print("=== SPEND BY PLANTA 2026 INDIRETOS ===")
if res.result and res.result.data_array:
    for row in res.result.data_array:
        print(row)
else:
    print(res.status)
