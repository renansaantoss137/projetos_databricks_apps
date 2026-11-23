import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient()

query = """
SELECT 
    COUNT(*) as total_open_180,
    COUNT(CASE WHEN COALESCE(VALOR_LIBERADO, 0) = 0 THEN 1 END) as liberado_zero,
    COUNT(CASE WHEN COALESCE(VALOR_LIBERADO, 0) > 0 THEN 1 END) as liberado_maior_zero,
    MIN(VALOR_LIBERADO) as min_liberado,
    MAX(VALOR_LIBERADO) as max_liberado
FROM cat_dnabb_dv.grobbcompr_cz.vw_acordos_bpa
WHERE STATUS = 'OPEN'
  AND DATEDIFF(CURRENT_DATE, CAST(SUBSTRING(DT_CRIACAO, 1, 10) AS DATE)) > 180
"""

res = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=query,
    wait_timeout='45s'
)

while res.status.state in (StatementState.PENDING, StatementState.RUNNING):
    time.sleep(2)
    res = w.statement_execution.get_statement(res.statement_id)

print("Final state:", res.status.state)
if res.status.error:
    print("Error:", res.status.error)
if res.manifest and res.manifest.schema and res.result and res.result.data_array:
    cols = [c.name for c in res.manifest.schema.columns]
    for row in res.result.data_array:
        print(dict(zip(cols, row)))
