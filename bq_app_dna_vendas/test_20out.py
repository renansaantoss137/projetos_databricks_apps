from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    sum(case when month(v.DT_REGISTRO) = 10 and year(v.DT_REGISTRO) = 2026 and v.DT_REGISTRO <= '2026-10-20' then v.VL_CYW_LIQ_VENDIDO else 0 end) as invoiced_ate_20out,
    sum(case when year(v.DT_REGISTRO) = 2026 and v.DT_REGISTRO <= '2026-10-20' then v.VL_CYW_LIQ_VENDIDO else 0 end) as invoiced_ytd_ate_20out
FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2 v
LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view p 
    ON cast(p.INVENTORY_ITEM_ID as string) = cast(v.ID_PRODUTO as string)
WHERE 
    v.GRUPO_CLI <> 108
    AND (p.COD_PRODUTO IS NULL OR p.COD_PRODUTO NOT IN ('100234', '100235'))
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
        num = float(val)
        print(f"  {c}: {num:,.2f} -> {num/1e6:,.2f} Mi")
