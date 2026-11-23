import base64, time, json
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace

w = WorkspaceClient()

nb_code = """# Databricks notebook source
import psycopg2, os, json
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

cur.execute(\"\"\"
SELECT numero_oc, nota_fiscal, urgente, data_lancamento, valor_liquido_brl 
FROM notas_ri 
WHERE numero_oc IN ('26089059497', '26089030052')
\"\"\")
notas_rows = cur.fetchall()

cur.execute(\"\"\"
SELECT numero_oc, urgente, data_oc, valor_original_brl 
FROM ordens_compra 
WHERE numero_oc IN ('26089059497', '26089030052')
\"\"\")
oc_rows = cur.fetchall()

conn.close()

dbutils.notebook.exit(json.dumps({
    'notas_ri': notas_rows,
    'ordens_compra': oc_rows
}, default=str))
"""

target = '/Users/renan.ferreira@grupobimbo.com/Drafts/check_oc_lakebase'
w.workspace.import_(
    path=target,
    content=base64.b64encode(nb_code.encode('utf-8')).decode('utf-8'),
    format=workspace.ExportFormat.SOURCE,
    language=workspace.Language.PYTHON,
    overwrite=True
)

run = w.jobs.submit(
    run_name='check_lakebase_ocs',
    tasks=[
        jobs.SubmitTask(
            task_key='check',
            notebook_task=jobs.NotebookTask(
                notebook_path=target
            )
        )
    ]
)
print('Submitted run ID:', run.run_id)

while True:
    st = w.jobs.get_run(run_id=run.run_id)
    state = st.state.life_cycle_state
    if state in (jobs.RunLifeCycleState.TERMINATED, jobs.RunLifeCycleState.SKIPPED, jobs.RunLifeCycleState.INTERNAL_ERROR):
        break
    time.sleep(3)

tasks = st.tasks or []
if tasks:
    out = w.jobs.get_run_output(run_id=tasks[0].run_id)
    if out.notebook_output and out.notebook_output.result:
        print('=== NOTEBOOK RESULT ===\n', out.notebook_output.result)
    elif out.error:
        print('=== ERROR ===\n', out.error)
