from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace
import io

w = WorkspaceClient()

script_content = """import psycopg2, os
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
cred = w.api_client.do('POST', '/api/2.0/postgres/credentials', body={
    'endpoint': 'projects/compras-360/branches/production/endpoints/primary'
})
token = cred.get('token', '')

conn = psycopg2.connect(
    host='ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net',
    database='databricks_postgres',
    user=w.current_user.me().user_name,
    password=token,
    port=5432,
    sslmode='require',
    options='-c search_path=compras'
)

cur = conn.cursor()

query_inner = \"\"\"SELECT 
    oc.numero_oc,
    oc.nome_usuario,
    COUNT(*) as qtd_linhas,
    SUM(oc.valor_original_brl) as sum_val,
    MAX(oc.valor_original_brl) as max_line_val
FROM ordens_compra oc
WHERE SUBSTRING(oc.data_oc, 1, 4) = '2026'
  AND CAST(SUBSTRING(oc.data_oc, 6, 2) AS INT) = 10
  AND oc.centralizado = 'DESCENTRALIZADO'
  AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
  AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
  AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
GROUP BY oc.numero_oc, oc.nome_usuario
HAVING SUM(oc.valor_original_brl) > 30000\"\"\"

cur.execute(query_inner + ' ORDER BY sum_val DESC LIMIT 15')
rows = cur.fetchall()
print('=== TOP 15 DESCENTRAL OCS OUT/2026 IN POSTGRESQL ===')
for r in rows:
    print(r)

cur.execute('SELECT COUNT(*), SUM(sum_val) FROM (' + query_inner + ') sub')
print('=== TOTAL DESCENTRAL OUT/2026 ===', cur.fetchall())

conn.close()
"""

target = '/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/compras_360/scratch_debug_lakebase.py'
w.workspace.upload(target, io.BytesIO(script_content.encode('utf-8')), overwrite=True, format=workspace.ImportFormat.AUTO)
print('Uploaded script to workspace successfully!')

run = w.jobs.submit(
    run_name='debug_lakebase_postgres',
    tasks=[
        jobs.SubmitTask(
            task_key='debug',
            spark_python_task=jobs.SparkPythonTask(
                python_file=target
            ),
            existing_cluster_id='0711-194930-gejtkmmb'
        )
    ]
)
print('Submitted run ID:', run.run_id)
