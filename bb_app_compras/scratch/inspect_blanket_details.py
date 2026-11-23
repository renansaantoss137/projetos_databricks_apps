import time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

query = """
SELECT 
    NUMERO_ACORDO,
    STATUS,
    DT_CRIACAO,
    VALOR_TOTAL,
    VALOR_LIBERADO,
    FORNECEDOR,
    COMPRADOR
FROM cat_dnabb_dv.grobbcompr_cz.vw_acordos_bpa
WHERE NUMERO_ACORDO IN ('24089000208', '26089000025', '26089000024', '24089001454')
"""

res = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=query,
    wait_timeout='45s'
)

while res.status.state.value in ('PENDING', 'RUNNING'):
    time.sleep(2)
    res = w.statement_execution.get_statement(res.statement_id)

print('Final state:', res.status.state)
if res.status.error:
    print('Error:', res.status.error.message)
if res.manifest and res.manifest.schema and res.result and res.result.data_array:
    cols = [c.name for c in res.manifest.schema.columns]
    for row in res.result.data_array:
        print(dict(zip(cols, row)))
