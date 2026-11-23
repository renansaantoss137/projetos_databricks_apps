from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Note: In PBIX, the filter on products is: cp.COD_PRODUTO NOT IN ('100234', '100235') and vbq.GRUPO_CLI <> 108
sql = """
SELECT 
    -- Outubro 2026 (DT_REGISTRO or DT_ENTREGA)
    sum(case when month(v.DT_REGISTRO) = 10 and year(v.DT_REGISTRO) = 2026 then v.VL_CYW_LIQ_VENDIDO else 0 end) as invoiced_reg_out26,
    sum(case when month(v.DT_ENTREGA) = 10 and year(v.DT_ENTREGA) = 2026 then v.VL_CYW_LIQ_VENDIDO else 0 end) as invoiced_ent_out26,
    sum(case when month(v.DT_REGISTRO) = 10 and year(v.DT_REGISTRO) = 2026 then v.VL_LIQ_OPEN_ORDERS else 0 end) as open_orders_out26,
    sum(case when month(v.DT_REGISTRO) = 10 and year(v.DT_REGISTRO) = 2026 then v.BUDGET_VALOR else 0 end) as budget_out26,
    sum(case when month(v.DT_REGISTRO) = 10 and year(v.DT_REGISTRO) = 2026 then v.FORECAST_VALOR else 0 end) as forecast_out26,
    
    -- Acumulado 2026 ate 20/10
    sum(case when year(v.DT_REGISTRO) = 2026 and v.DT_REGISTRO <= '2026-10-20' then v.VL_CYW_LIQ_VENDIDO else 0 end) as invoiced_ytd_reg
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
    print("=== KPI VALIDATION (OCTOBER 2026) ===")
    for c, val in zip(cols, row):
        try:
            num = float(val)
            print(f"  {c}: {num:,.2f} (em Mi: {num/1e6:,.2f} Mi)")
        except:
            print(f"  {c}: {val}")
else:
    print("State:", res.status.state, "Error:", res.status.error)
