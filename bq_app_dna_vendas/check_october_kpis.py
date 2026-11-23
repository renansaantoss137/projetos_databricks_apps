from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    sum(case when month(DT_ENTREGA) = 10 then VL_FAT_LIQUIDO else 0 end) as invoiced_outubro,
    sum(case when month(DT_ENTREGA) = 10 then VL_LIQ_OPEN_ORDERS else 0 end) as open_orders_outubro,
    sum(case when month(DT_ENTREGA) = 10 then VL_PPTO_FAT_LIQ else 0 end) as budget_outubro,
    sum(case when month(DT_ENTREGA) = 10 then VL_FCST_FAT_LIQ else 0 end) as forecast_outubro,
    sum(case when year(DT_ENTREGA) = 2026 and DT_ENTREGA <= '2026-10-20' then VL_FAT_LIQUIDO else 0 end) as invoiced_ytd
FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2
WHERE year(DT_ENTREGA) = 2026
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
