import io, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace

w = WorkspaceClient()

# Notebook content (Databricks notebook source format)
nb_content = """# Databricks notebook source
import psycopg2, os
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

print("=== LAKEBASE NOTAS_RI FOR BOTH OCS ===")
cur.execute(\"\"\"
SELECT numero_oc, nota_fiscal, urgente, data_lancamento, valor_liquido_brl 
FROM notas_ri 
WHERE numero_oc IN ('26089059497', '26089030052')
\"\"\")
for r in cur.fetchall():
    print(r)

print("=== LAKEBASE ORDENS_COMPRA FOR BOTH OCS ===")
cur.execute(\"\"\"
SELECT numero_oc, urgente, data_oc, valor_original_brl 
FROM ordens_compra 
WHERE numero_oc IN ('26089059497', '26089030052')
\"\"\")
for r in cur.fetchall():
    print(r)

conn.close()
"""

target = '/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/compras_360/scratch_nb_check_two_ocs'
w.workspace.upload(target, io.BytesIO(nb_content.encode('utf-8')), overwrite=True, format=workspace.ImportFormat.AUTO)

run = w.jobs.submit(
    run_name='check_two_ocs_lakebase',
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
    output = w.jobs.get_run_output(run_id=tasks[0].run_id)
    if output.logs:
        print('=== LOGS ===\n', output.logs)
    if output.error:
        print('=== ERROR ===\n', output.error)
