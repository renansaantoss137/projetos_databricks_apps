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
    NOME_FORNECEDOR,
    DS_ITEM,
    CODIGO_ITEM,
    EMPRESA
FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri
WHERE NOTA_FISCAL = '52'
  AND SUBSTRING(DATA_LANCAMENTO, 1, 4) = '2026'
ORDER BY DATA_LANCAMENTO, NUMERO_OC, LINHA_OC
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
    print(f"Total rows found for NOTA_FISCAL = '52' in 2026: {len(resp.result.data_array)}")
    for row in resp.result.data_array:
        print("Row:", row)
