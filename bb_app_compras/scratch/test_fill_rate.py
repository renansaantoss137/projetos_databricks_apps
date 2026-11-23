from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Query fill rate on ordens_compra
with open("docs/sql/vw_ordens_compra.sql", "r", encoding="utf-8") as f:
    sql_oc = f.read()

sql_stats = f"""
WITH 
tv_fornecedores_especiais AS (SELECT '' AS COD_FORNECEDOR_ORACLE),
tv_fornecedores_nao_negociaveis AS (SELECT '' AS COD_FORNECEDOR_ORACLE),
tv_compradores_funcionais AS (SELECT '' AS USUARIO_ORACLE, '' AS AREA),
vw_oc AS (
{sql_oc}
)
SELECT 
    COMPRADOR,
    DEPARTAMENTO_COMPRADOR,
    COUNT(*) AS total_linhas
FROM vw_oc
WHERE YEAR(DATA_OC) >= 2025
GROUP BY COMPRADOR, DEPARTAMENTO_COMPRADOR
ORDER BY total_linhas DESC
LIMIT 40
"""

import time
from databricks.sdk.service.sql import StatementState

print("Consultando taxa de preenchimento em ordens_compra...")
resp = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=sql_stats,
    wait_timeout='30s'
)
statement_id = resp.statement_id
while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
    print(f"Status: {resp.status.state}... aguardando 5s")
    time.sleep(5)
    resp = w.statement_execution.get_statement(statement_id=statement_id)

print("Final State:", resp.status.state)
if resp.status.error:
    print("Error:", resp.status.error.message)
if resp.manifest and resp.manifest.schema:
    cols = [c.name for c in resp.manifest.schema.columns]
    for r in resp.result.data_array:
        print("Stats OC:", dict(zip(cols, r)))

