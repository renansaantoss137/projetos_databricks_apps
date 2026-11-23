import time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

query = """
WITH urg_raw AS (
    SELECT
        'OC emergencial' AS tipo_excecao,
        nf.NUMERO_OC AS "NUMERO_OC",
        MAX(COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não informado')) AS comprador,
        MAX(COALESCE(NULLIF(oc.usuario_comprador, ''), oc.usuario)) AS usuario,
        MAX(oc.DEPARTAMENTO_COMPRADOR) AS dept_oc,
        MAX(COALESCE(oc.NOME_REQUISITANTE, 'Não informado')) AS solicitante,
        REGEXP_REPLACE(
            COALESCE(MAX(NULLIF(oc.DEPARTAMENTO_REQUISITANTE, '')), MAX(NULLIF(oc.area, '')), '--'),
            '^[0-9]+\\\\s*-\\\\s*',
            ''
        ) AS depart_solicitante,
        MAX(nf.NOME_FORNECEDOR) AS fornecedor,
        SUM(nf.VALOR_LIQUIDO_BRL) AS net_spend,
        MAX(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO)) AS data_fatura,
        MAX(oc.DATA_OC) AS data_emissao_oc,
        MAX(oc.DT_APROVACAO) AS data_oc
    FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri nf
    LEFT JOIN cat_dnabb_dv.grobbcompr_cz.vw_ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
    WHERE nf.URGENTE = 'SIM' 
      AND nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != '' AND nf.NUMERO_OC != 'Nota sem OC'
      AND SUBSTRING(nf.DATA_LANCAMENTO, 1, 4) IN ('2026')
      AND CAST(SUBSTRING(nf.DATA_LANCAMENTO, 6, 2) AS INT) IN (10)
    GROUP BY nf.NUMERO_OC
)
SELECT * FROM urg_raw ORDER BY net_spend DESC
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
    print(f"Total rows: {len(res.result.data_array)}")
    for row in res.result.data_array:
        print(dict(zip(cols, row)))
