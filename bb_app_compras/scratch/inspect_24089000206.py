from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

query = """
SELECT 
    NUMERO_ACORDO,
    STATUS,
    DT_CRIACAO,
    VALOR_TOTAL,
    VALOR_LIBERADO,
    FORNECEDOR,
    COMPRADOR
FROM cat_dnabb_dv.grobbcompr_cz.vw_acordos_bpa
WHERE NUMERO_ACORDO = '24089000206'
"""

res = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=query,
    wait_timeout='45s'
)

if res.manifest and res.manifest.schema and res.result and res.result.data_array:
    cols = [c.name for c in res.manifest.schema.columns]
    for row in res.result.data_array:
        print(dict(zip(cols, row)))
