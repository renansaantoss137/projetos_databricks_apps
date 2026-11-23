from databricks.sdk import WorkspaceClient
import pandas as pd

w = WorkspaceClient()

# Check total NFs in notas_ri for 2026-10 with and without special/nao_negociavel
stmt = """
SELECT 
    COUNT(DISTINCT NOTA_FISCAL) AS total_nfs_todas,
    COUNT(DISTINCT CASE WHEN COALESCE(IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL' THEN NOTA_FISCAL END) AS nfs_sem_especial,
    COUNT(DISTINCT CASE WHEN COALESCE(IS_FORNECEDOR_NAO_NEGOCIAVEL, 'NEGOCIAVEL') = 'NEGOCIAVEL' THEN NOTA_FISCAL END) AS nfs_negociaveis,
    COUNT(DISTINCT CASE WHEN COALESCE(IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL' 
                         AND COALESCE(IS_FORNECEDOR_NAO_NEGOCIAVEL, 'NEGOCIAVEL') = 'NEGOCIAVEL' THEN NOTA_FISCAL END) AS nfs_sem_esp_e_negoc,
    COUNT(DISTINCT CASE WHEN NUMERO_OC != 'Nota sem OC' AND NUMERO_OC IS NOT NULL AND NUMERO_OC != ''
                         AND COALESCE(OC_POS_FATURA, 'NÃO') = 'SIM'
                         AND COALESCE(IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'
                        THEN NOTA_FISCAL END) AS pf_sem_especial,
    COUNT(DISTINCT CASE WHEN NUMERO_OC != 'Nota sem OC' AND NUMERO_OC IS NOT NULL AND NUMERO_OC != ''
                         AND COALESCE(OC_POS_FATURA, 'NÃO') = 'SIM'
                         AND COALESCE(IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'
                         AND COALESCE(IS_FORNECEDOR_NAO_NEGOCIAVEL, 'NEGOCIAVEL') = 'NEGOCIAVEL'
                        THEN NOTA_FISCAL END) AS pf_sem_esp_e_negoc
FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri
WHERE SUBSTRING(DATA_PAGAMENTO, 1, 7) = '2026-10'
"""

res = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=stmt,
    wait_timeout='30s'
)

cols = [c.name for c in res.manifest.schema.columns]
row = res.result.data_array[0]
for c, v in zip(cols, row):
    print(f"{c}: {v}")
