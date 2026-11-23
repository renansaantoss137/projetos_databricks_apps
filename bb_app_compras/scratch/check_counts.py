from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    COUNT(*) as total_2026,
    COUNT(CASE WHEN DATA_LANCAMENTO >= '2026-09-26' THEN 1 END) as count_since_sep26,
    COUNT(CASE WHEN DATA_LANCAMENTO = '2026-09-26' THEN 1 END) as count_sep26
FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri
WHERE SUBSTRING(DATA_LANCAMENTO, 1, 4) = '2026'
  AND (NOTA_FISCAL IS NULL OR (
      UPPER(NOTA_FISCAL) NOT LIKE '%RGB%'
      AND UPPER(NOTA_FISCAL) NOT LIKE 'ADV%'
      AND UPPER(NOTA_FISCAL) NOT LIKE '%FOPAG%'
  ))
"""

resp = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=sql,
    wait_timeout='45s'
)
print("Status:", resp.status.state)
if resp.result and resp.result.data_array:
    for row in resp.result.data_array:
        print("Row:", row)
