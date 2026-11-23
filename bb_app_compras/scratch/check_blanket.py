import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient()

def run_sql(sql):
    resp = w.statement_execution.execute_statement(
        warehouse_id='f4a2e26b8410f1e3',
        statement=sql,
        wait_timeout='50s'
    )
    stmt_id = resp.statement_id
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(2)
        resp = w.statement_execution.get_statement(stmt_id)
    if resp.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"Query failed: {resp.status.error}")
    cols = [c.name for c in resp.manifest.schema.columns]
    data = resp.result.data_array if resp.result else []
    return cols, data

# Check Blanket purchase agreements in vw_ordens_compra
sql = """
SELECT 
    COUNT(DISTINCT NUMERO_ACORDO) as total_acordos_distintos,
    COUNT(DISTINCT CASE WHEN ACORDO_COMPRA = 'SIM' THEN NUMERO_ACORDO END) as acordos_sim,
    COUNT(DISTINCT CASE WHEN NUMERO_ACORDO IS NOT NULL AND NUMERO_ACORDO != '' THEN NUMERO_ACORDO END) as com_numero_acordo
FROM cat_dnabb_dv.grobbcompr_cz.vw_ordens_compra
"""

cols, rows = run_sql(sql)
print("Blanket check 1:")
for r in rows:
    print(dict(zip(cols, r)))
