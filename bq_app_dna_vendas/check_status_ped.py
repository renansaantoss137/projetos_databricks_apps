from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    sum(PEDIDO_VLR) as total_pedido_vlr_outubro,
    sum(case when STATUS_PEDIDO in ('ABERTO', 'EM PROCESSAMENTO', 'LIBERADO', 'PENDENTE') then PEDIDO_VLR else 0 end) as ped_aberto_outubro,
    sum(case when coalesce(VENDA_LIQUIDA_VLR, 0) = 0 then PEDIDO_VLR else 0 end) as ped_sem_fat_outubro
FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2
WHERE month(DT_ENTREGA) = 10 and year(DT_ENTREGA) = 2026
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
