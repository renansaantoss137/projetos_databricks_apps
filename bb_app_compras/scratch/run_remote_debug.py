import io, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace

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

# Query: Top 20 OCs by SUM(valor_original_brl)
q = \"\"\"
SELECT 
    oc.numero_oc,
    oc.nome_usuario,
    COUNT(*) as qtd_linhas,
    SUM(oc.valor_original_brl) as sum_val,
    MAX(oc.valor_original_brl) as max_val,
    MIN(oc.valor_original_brl) as min_val,
    MAX(oc.data_oc) as data_oc,
    MAX(oc.fornecedor) as fornecedor,
    MAX(oc.usuario) as usuario
FROM ordens_compra oc
WHERE SUBSTRING(oc.data_oc, 1, 4) = '2026'
  AND CAST(SUBSTRING(oc.data_oc, 6, 2) AS INT) = 10
  AND oc.centralizado = 'DESCENTRALIZADO'
  AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
  AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
  AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
GROUP BY oc.numero_oc, oc.nome_usuario
HAVING SUM(oc.valor_original_brl) > 30000
ORDER BY sum_val DESC
LIMIT 20
\"\"\"

cur.execute(q)
rows = cur.fetchall()
print('=== TOP 20 DESCENTRALIZADAS OUT/2026 ===')
for r in rows:
    print(r)

# Total sum and count
cur.execute(\"\"\"
SELECT COUNT(*), SUM(sum_val) FROM (
    SELECT oc.numero_oc, SUM(oc.valor_original_brl) as sum_val
    FROM ordens_compra oc
    WHERE SUBSTRING(oc.data_oc, 1, 4) = '2026'
      AND CAST(SUBSTRING(oc.data_oc, 6, 2) AS INT) = 10
      AND oc.centralizado = 'DESCENTRALIZADO'
      AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
      AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
      AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
    GROUP BY oc.numero_oc
    HAVING SUM(oc.valor_original_brl) > 30000
) sub
\"\"\")
print('=== TOTAL DESCENTRAL OUT/2026 ===', cur.fetchall())

# What about with empresa / org_desc IN ('BB', 'BQ')?
cur.execute(\"\"\"
SELECT COUNT(*), SUM(sum_val) FROM (
    SELECT oc.numero_oc, SUM(oc.valor_original_brl) as sum_val
    FROM ordens_compra oc
    WHERE SUBSTRING(oc.data_oc, 1, 4) = '2026'
      AND CAST(SUBSTRING(oc.data_oc, 6, 2) AS INT) = 10
      AND oc.org_desc IN ('BB', 'BQ')
      AND oc.centralizado = 'DESCENTRALIZADO'
      AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
      AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
      AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
    GROUP BY oc.numero_oc
    HAVING SUM(oc.valor_original_brl) > 30000
) sub
\"\"\")
print('=== TOTAL DESCENTRAL OUT/2026 (WITH BB/BQ) ===', cur.fetchall())

conn.close()
"""

target = '/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/compras_360/scratch_debug_lakebase.py'
w.workspace.upload(target, io.BytesIO(script_content.encode('utf-8')), overwrite=True, format=workspace.ImportFormat.AUTO)
print('Uploaded script to workspace.')

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

# Wait for completion
while True:
    st = w.jobs.get_run(run_id=run.run_id)
    state = st.state.life_cycle_state
    print('Run state:', state)
    if state in (jobs.RunLifeCycleState.TERMINATED, jobs.RunLifeCycleState.SKIPPED, jobs.RunLifeCycleState.INTERNAL_ERROR):
        break
    time.sleep(5)

# Print output
tasks = st.tasks or []
if tasks:
    task_run_id = tasks[0].run_id
    output = w.jobs.get_run_output(run_id=task_run_id)
    if output.logs:
        print('=== LOGS ===\n', output.logs)
    if output.error:
        print('=== ERROR ===\n', output.error)
