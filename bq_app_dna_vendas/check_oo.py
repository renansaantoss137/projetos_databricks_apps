from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    sum(VL_LIQ_OPEN_ORDERS) as total_open_orders_all,
    sum(case when month(DT_ENTREGA) = 10 and year(DT_ENTREGA) = 2026 then VL_LIQ_OPEN_ORDERS else 0 end) as oo_entrega_out,
    sum(case when month(DT_REGISTRO) = 10 and year(DT_REGISTRO) = 2026 then VL_LIQ_OPEN_ORDERS else 0 end) as oo_reg_out,
    sum(case when month(DT_PEDIDO) = 10 and year(DT_PEDIDO) = 2026 then VL_LIQ_OPEN_ORDERS else 0 end) as oo_ped_out
FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2
"""

res = w.statement_execution.execute_statement(
    warehouse_id="f4a2e26b8410f1e3",
    statement=sql,
    wait_timeout="45s"
)
if res.result and res.result.data_array:
    cols = [col.name for col in res.manifest.schema.columns]
    row = res.result.data_array[0]
    for c, val in zip(cols, row):
        print(f"  {c}: {float(val):,.2f}")
