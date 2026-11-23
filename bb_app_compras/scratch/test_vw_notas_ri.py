import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient()

with open("docs/sql/vw_notas_ri.sql", "r", encoding="utf-8") as f:
    sql_notas = f.read()

sql_test = f"""
WITH 
tv_fornecedores_especiais AS (SELECT '' AS COD_FORNECEDOR_ORACLE),
tv_fornecedores_nao_negociaveis AS (SELECT '' AS COD_FORNECEDOR_ORACLE),
tv_compradores_funcionais AS (SELECT '' AS USUARIO_ORACLE, '' AS AREA),
vw_nf AS (
{sql_notas}
)
SELECT 
    NOTA_FISCAL,
    NUMERO_OC,
    COMPRADOR,
    DEPARTAMENTO_COMPRADOR,
    VALOR_LIQUIDO_BRL
FROM vw_nf
WHERE YEAR(DATA_NOTA) >= 2025
LIMIT 5
"""

print("Testando vw_notas_ri no Databricks...")
resp = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=sql_test,
    wait_timeout='30s'
)
stmt_id = resp.statement_id
while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
    time.sleep(3)
    resp = w.statement_execution.get_statement(statement_id=stmt_id)

print("State:", resp.status.state)
if resp.status.error:
    print("Error:", resp.status.error.message)
elif resp.manifest and resp.manifest.schema:
    cols = [c.name for c in resp.manifest.schema.columns]
    data = resp.result.data_array if (resp.result and resp.result.data_array) else []
    for r in data:
        print(dict(zip(cols, r)))
