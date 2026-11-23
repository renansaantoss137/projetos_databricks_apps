from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = 'f4a2e26b8410f1e3'

def run_sql(query):
    res = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=query,
        wait_timeout='60s'
    )
    if res.status.state.value != 'SUCCEEDED':
        raise RuntimeError(f"Query failed: {res.status.error}")
    return res.result.data_array or []

# 1. Total de notas e notas sem OC em 09/2026 com fornecedor NEGOCIAVEL vs NÃO NEGOCIAVEL
sql1 = """
WITH base AS (
    SELECT 
        v.NOTA_FISCAL,
        v.NUMERO_OC,
        v.VALOR_LIQUIDO_BRL,
        v.NOME_FORNECEDOR,
        CASE 
            WHEN fnn.COD_FORNECEDOR_ORACLE IS NOT NULL THEN 'NÃO NEGOCIAVEL'
            ELSE 'NEGOCIAVEL'
        END AS is_fornecedor_nao_negociavel
    FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri v
    LEFT JOIN (SELECT DISTINCT COD_FORNECEDOR_ORACLE FROM cat_dnabb_dv.grobbcompr_cz.fornecedores_nao_negociaveis) fnn
           ON v.CNPJ_FORNECEDOR = fnn.COD_FORNECEDOR_ORACLE -- or supplier number
    WHERE YEAR(v.DATA_NOTA) = 2026 AND MONTH(v.DATA_NOTA) = 9
)
SELECT 
    is_fornecedor_nao_negociavel,
    COUNT(DISTINCT NOTA_FISCAL) as total_notas,
    COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' THEN NOTA_FISCAL END) as sem_oc_qty,
    SUM(VALOR_LIQUIDO_BRL) as total_spend,
    SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) as sem_oc_val
FROM base
GROUP BY is_fornecedor_nao_negociavel
"""
