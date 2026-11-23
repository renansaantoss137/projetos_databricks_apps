from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    collect_set(distinct year(v.DT_REGISTRO)) as anos,
    collect_set(distinct coalesce(c.NM_CANAL, 'OUTROS')) as canais,
    collect_set(distinct coalesce(c.CLUSTER, 'OUTROS')) as clusters,
    collect_set(distinct coalesce(c.CLUSTER_1, 'OUTROS')) as clusters_detalhe,
    collect_set(distinct coalesce(c.NM_NV1, 'OUTROS')) as gerentes,
    collect_set(distinct coalesce(p.CATEGORIA_MKT, 'OUTROS')) as categorias,
    collect_set(distinct coalesce(p.TIPO_CESTO, 'OUTROS')) as tipos_produto
FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2 v
LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view p ON cast(p.INVENTORY_ITEM_ID as string) = cast(v.ID_PRODUTO as string)
LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view c ON cast(c.COD_GR_CLIENTE as string) = cast(v.GRUPO_CLI as string)
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
        print(f"=== {c} ===")
        print(val[:300] if val else "None")
