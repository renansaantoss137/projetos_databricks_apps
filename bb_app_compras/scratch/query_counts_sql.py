import time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

res = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement="""
    SELECT 
        COUNT(DISTINCT NOTA_FISCAL) AS total_nfs,
        COUNT(DISTINCT CASE WHEN NUMERO_OC != 'Nota sem OC' AND NUMERO_OC IS NOT NULL AND NUMERO_OC != '' THEN NOTA_FISCAL END) AS nfs_com_oc,
        COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' OR NUMERO_OC IS NULL OR NUMERO_OC = '' THEN NOTA_FISCAL END) AS nfs_sem_oc
    FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri
    WHERE SUBSTRING(DATA_PAGAMENTO, 1, 7) = '2026-10'
    """,
    wait_timeout='45s'
)

while res.status.state.value in ('PENDING', 'RUNNING'):
    time.sleep(3)
    res = w.statement_execution.get_statement(res.statement_id)

print('Final state:', res.status.state)
if res.status.error:
    print('Error:', res.status.error.message)
if res.manifest and res.manifest.schema:
    cols = [c.name for c in res.manifest.schema.columns]
    print(dict(zip(cols, res.result.data_array[0])))

