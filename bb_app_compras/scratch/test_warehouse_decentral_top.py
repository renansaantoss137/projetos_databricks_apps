from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

sql = """
SELECT 
    NUMERO_OC,
    NOME_USUARIO,
    COUNT(*) as qtd_linhas,
    SUM(VALOR_ORIGINAL) as sum_val,
    MAX(VALOR_ORIGINAL) as max_val,
    MIN(VALOR_ORIGINAL) as min_val,
    MAX(DATA_OC) as data_oc,
    MAX(FORNECEDOR) as fornecedor,
    MAX(USUARIO) as usuario
FROM cat_dnabb_dv.grobbcompr_cz.vw_ordens_compra
WHERE SUBSTRING(DATA_OC, 1, 4) IN ('2026')
  AND CAST(SUBSTRING(DATA_OC, 6, 2) AS INT) IN (10)
  AND CENTRALIZADO = 'DESCENTRALIZADO'
  AND (NUMERO_ACORDO IS NULL OR TRIM(NUMERO_ACORDO) = '')
  AND UPPER(COALESCE(NOME_USUARIO, '')) NOT IN (
      SELECT UPPER(comprador_funcional) FROM cat_dnabb_dv.grobbcompr_cz.compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%'
  )
GROUP BY NUMERO_OC, NOME_USUARIO
HAVING SUM(VALOR_ORIGINAL) > 30000
ORDER BY sum_val DESC
LIMIT 15
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
    print(f"Top OCs in vw_ordens_compra (found {len(resp.result.data_array)}):")
    total = 0
    for r in resp.result.data_array:
        print(f"OC: {r[0]} | User: {r[1]} | Linhas: {r[2]} | Sum: R$ {float(r[3]):,.2f} | Max: R$ {float(r[4]):,.2f} | Forn: {r[7]}")
        total += float(r[3])
    print(f"Top sum: R$ {total:,.2f}")

# Total query
sql_tot = """
SELECT COUNT(*), SUM(sum_val) FROM (
    SELECT 
        NUMERO_OC,
        SUM(VALOR_ORIGINAL) as sum_val
    FROM cat_dnabb_dv.grobbcompr_cz.vw_ordens_compra
    WHERE SUBSTRING(DATA_OC, 1, 4) IN ('2026')
      AND CAST(SUBSTRING(DATA_OC, 6, 2) AS INT) IN (10)
      AND CENTRALIZADO = 'DESCENTRALIZADO'
      AND (NUMERO_ACORDO IS NULL OR TRIM(NUMERO_ACORDO) = '')
      AND UPPER(COALESCE(NOME_USUARIO, '')) NOT IN (
          SELECT UPPER(comprador_funcional) FROM cat_dnabb_dv.grobbcompr_cz.compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%'
      )
    GROUP BY NUMERO_OC
    HAVING SUM(VALOR_ORIGINAL) > 30000
) sub
"""
resp_tot = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=sql_tot,
    wait_timeout='45s'
)
if resp_tot.result and resp_tot.result.data_array:
    print("TOTAL in vw_ordens_compra:", resp_tot.result.data_array)
