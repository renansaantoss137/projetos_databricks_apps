import time
import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

query = """
SELECT 
    nf.NOTA_FISCAL,
    nf.NUMERO_OC,
    nf.DATA_LANCAMENTO,
    nf.DATA_PAGAMENTO,
    nf.DT_NOTA,
    nf.URGENTE,
    nf.VALOR_LIQUIDO_BRL,
    nf.NOME_FORNECEDOR,
    nf.CHAVE_OC_LINHA,
    oc.DATA_OC,
    oc.DT_APROVACAO,
    oc.NOME_USUARIO,
    oc.COMPRADOR
FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri nf
LEFT JOIN cat_dnabb_dv.grobbcompr_cz.vw_ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
WHERE nf.URGENTE = 'SIM'
  AND SUBSTRING(nf.DATA_LANCAMENTO, 1, 7) = '2026-10'
"""

res = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=query,
    wait_timeout='45s'
)

while res.status.state.value in ('PENDING', 'RUNNING'):
    time.sleep(2)
    res = w.statement_execution.get_statement(res.statement_id)

print('Final state:', res.status.state)
if res.status.error:
    print('Error:', res.status.error.message)
if res.manifest and res.manifest.schema and res.result and res.result.data_array:
    cols = [c.name for c in res.manifest.schema.columns]
    for row in res.result.data_array:
        print(dict(zip(cols, row)))
else:
    print("No rows returned!")
