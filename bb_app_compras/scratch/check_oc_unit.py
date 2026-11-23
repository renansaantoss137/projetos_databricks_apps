from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "f4a2e26b8410f1e3"

stmt = """
SELECT numero_oc, unidade, area, categoria_oc 
FROM cat_dnabb_dv.grobbcompr_cz.vw_ordens_compra 
WHERE numero_oc IN ('26089059281', '26089029901', '26089057035')
LIMIT 10
"""
res = w.statement_execution.execute_statement(
    warehouse_id=wh_id,
    statement=stmt,
    wait_timeout="30s"
)
if res.result and res.result.data_array:
    cols = [c.name for c in res.manifest.schema.columns]
    for r in res.result.data_array:
        print(dict(zip(cols, r)))
else:
    print(res.status)
