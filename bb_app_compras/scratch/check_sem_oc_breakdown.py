import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "f4a2e26b8410f1e3"

query_breakdown = """
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
      AND (planta IS NULL OR TRIM(planta) = '' OR TRIM(planta) = 'Não identificada')
)
SELECT 
    CASE WHEN NUMERO_OC = 'Nota sem OC' OR NUMERO_OC IS NULL OR TRIM(NUMERO_OC) = '' THEN 'Nota sem OC' ELSE 'Com OC' END AS tipo_oc,
    COUNT(DISTINCT NUMERO_RI) AS total_ris,
    COUNT(DISTINCT NOTA_FISCAL) AS total_nfs,
    ROUND(SUM(VALOR_LIQUIDO_BRL) / 1e6, 2) AS spend_mi,
    ROUND(SUM(VALOR_LIQUIDO_BRL) * 100.0 / (SELECT SUM(VALOR_LIQUIDO_BRL) FROM base), 1) AS pct_do_nao_identificado
FROM base
GROUP BY CASE WHEN NUMERO_OC = 'Nota sem OC' OR NUMERO_OC IS NULL OR TRIM(NUMERO_OC) = '' THEN 'Nota sem OC' ELSE 'Com OC' END
"""

res = w.statement_execution.execute_statement(
    warehouse_id=wh_id,
    statement=query_breakdown,
    wait_timeout="50s"
)

if res.result and res.result.data_array:
    cols = [c.name for c in res.manifest.schema.columns]
    for r in res.result.data_array:
        print(dict(zip(cols, r)))
