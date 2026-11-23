from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = "DESCRIBE cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2"
res = w.statement_execution.execute_statement(
    warehouse_id="f4a2e26b8410f1e3",
    statement=sql,
    wait_timeout="45s"
)
if res.result and res.result.data_array:
    for row in res.result.data_array:
        print(f"  {row[0]}: {row[1]}")
