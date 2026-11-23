import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient()

def run_sql(sql):
    resp = w.statement_execution.execute_statement(
        warehouse_id='f4a2e26b8410f1e3',
        statement=sql,
        wait_timeout='50s'
    )
    stmt_id = resp.statement_id
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(3)
        resp = w.statement_execution.get_statement(stmt_id)
        print(f"Waiting query {stmt_id}... state: {resp.status.state}")
    
    if resp.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"Query failed: {resp.status.error}")
        
    cols = [c.name for c in resp.manifest.schema.columns]
    data = resp.result.data_array if resp.result else []
    return cols, data

sql = """
WITH base AS (
    SELECT 
        v.*,
        inv_h.ApInvoicesApprovalStatus
    FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri v
    INNER JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoiceheaderextractpvo inv_h
        ON CAST(v.NUMERO_RI AS BIGINT) = inv_h.ApInvoicesInvoiceId
        AND inv_h.ApInvoicesApprovalStatus IN ('APPROVED', 'FULL')
    WHERE YEAR(COALESCE(v.DATA_LANCAMENTO, v.DT_NOTA)) = 2026
      AND (v.NOTA_FISCAL IS NULL OR (
          UPPER(v.NOTA_FISCAL) NOT LIKE '%ARKER%'
          AND UPPER(v.NOTA_FISCAL) NOT LIKE '%RGB%'
          AND UPPER(v.NOTA_FISCAL) NOT LIKE 'ADV%'
          AND UPPER(v.NOTA_FISCAL) NOT LIKE '%FOPAG%'
          AND UPPER(v.NOTA_FISCAL) NOT LIKE '%JURIDICO%'
          AND UPPER(v.NOTA_FISCAL) NOT LIKE '%FISCAL%'
          AND UPPER(v.NOTA_FISCAL) NOT LIKE '%TESSP%'
      ))
)
SELECT 
    COUNT(DISTINCT NOTA_FISCAL) as total_notas,
    COUNT(DISTINCT CASE WHEN NUMERO_OC != 'Nota sem OC' AND NUMERO_OC IS NOT NULL THEN NUMERO_OC END) as total_oc_faturadas,
    SUM(VALOR_LIQUIDO_BRL) as total_spend,
    COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' THEN NOTA_FISCAL END) as sem_oc_qty,
    SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) as sem_oc_val,
    COUNT(DISTINCT CASE WHEN URGENTE = 'SIM' THEN NUMERO_OC END) as urgente_qty,
    SUM(CASE WHEN URGENTE = 'SIM' THEN VALOR_LIQUIDO_BRL ELSE 0 END) as urgente_val
FROM base
"""

cols, rows = run_sql(sql)
print("ETL Base Filtered Metrics for 2026:")
for r in rows:
    print(dict(zip(cols, r)))
