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

# Let's inspect DATA_PAGAMENTO in vw_notas_ri
sql = """
SELECT 
    COUNT(DISTINCT NOTA_FISCAL) as total_nfs_lancamento_2026,
    COUNT(DISTINCT CASE WHEN OC_POS_FATURA = 'SIM' THEN NOTA_FISCAL END) as pos_fatura_nfs,
    COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' THEN NOTA_FISCAL END) as sem_oc_nfs,
    COUNT(DISTINCT CASE WHEN URGENTE = 'SIM' THEN NUMERO_OC END) as urgente_ocs,
    SUM(VALOR_LIQUIDO_BRL) as total_spend,
    SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) as sem_oc_spend,
    SUM(CASE WHEN URGENTE = 'SIM' THEN VALOR_LIQUIDO_BRL ELSE 0 END) as urgente_spend
FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri
WHERE YEAR(DATA_LANCAMENTO) = 2026
"""

cols, rows = run_sql(sql)
print("vw_notas_ri 2026 Metrics:")
for r in rows:
    print(dict(zip(cols, r)))
