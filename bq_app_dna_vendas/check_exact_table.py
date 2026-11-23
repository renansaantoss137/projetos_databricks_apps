from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    count(*) as total_rows,
    min(DT_ENTREGA) as min_dt_entrega,
    max(DT_ENTREGA) as max_dt_entrega,
    min(DT_REGISTRO) as min_dt_reg,
    max(DT_REGISTRO) as max_dt_reg
FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2
"""

res = w.statement_execution.execute_statement(
    warehouse_id="f4a2e26b8410f1e3",
    statement=sql,
    wait_timeout="45s"
)
if res.result and res.result.data_array:
    print("Columns:", [col.name for col in res.manifest.schema.columns])
    for row in res.result.data_array:
        print("Row:", row)
else:
    print("State:", res.status.state, "Error:", res.status.error)
