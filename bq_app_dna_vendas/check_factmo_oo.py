from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    sum(case when month(DT_ENTREGA) = 10 and year(DT_ENTREGA) = 2026 then VL_LIQ_OPEN_ORDERS else 0 end) as oo_out26,
    sum(case when month(DT_ENTREGA) = 10 and year(DT_ENTREGA) = 2026 then VL_BRUTO_OPEN_ORDERS else 0 end) as oo_bruto_out26
FROM cat_dnabb_dv.grobbcmrcl_sz.factmo_open_orders_status_bq
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
        if val is not None:
            print(f"  {c}: {float(val):,.2f}")
else:
    print("State:", res.status.state, "Error:", res.status.error)
