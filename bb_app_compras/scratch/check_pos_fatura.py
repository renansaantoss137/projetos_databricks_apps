from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

def run_sql(sql):
    resp = w.statement_execution.execute_statement(
        warehouse_id='f4a2e26b8410f1e3',
        statement=sql,
        wait_timeout='50s'
    )
    cols = [c.name for c in resp.manifest.schema.columns]
    data = resp.result.data_array if resp.result else []
    return cols, data

sql = """
SELECT 
    OC_POS_FATURA,
    COUNT(DISTINCT NOTA_FISCAL) as qtd_nfs,
    COUNT(DISTINCT NUMERO_OC) as qtd_ocs,
    SUM(VALOR_LIQUIDO_BRL) as total_val
FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri
WHERE YEAR(DATA_LANCAMENTO) = 2026
GROUP BY OC_POS_FATURA
"""

cols, rows = run_sql(sql)
print("vw_notas_ri by OC_POS_FATURA (filter YEAR(DATA_LANCAMENTO)=2026):")
for r in rows:
    print(dict(zip(cols, r)))
