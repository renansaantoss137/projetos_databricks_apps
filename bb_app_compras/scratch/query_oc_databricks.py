from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    NOTA_FISCAL,
    NUMERO_RI,
    NUMERO_OC,
    DATA_LANCAMENTO,
    DT_NOTA,
    VALOR_LIQUIDO_BRL,
    CHAVE_OC_LINHA,
    LINHA_OC,
    DS_ITEM,
    CODIGO_ITEM,
    EMPRESA
FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri
WHERE NUMERO_OC = '26089060703'
ORDER BY NOTA_FISCAL, LINHA_OC
"""

resp = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=sql,
    wait_timeout='45s'
)
print("Status:", resp.status.state)
if resp.status.error:
    print("Error:", resp.status.error.message)
if resp.result and resp.result.data_array:
    print(f"Total rows found: {len(resp.result.data_array)}")
    for row in resp.result.data_array:
        print("Row:", row)
