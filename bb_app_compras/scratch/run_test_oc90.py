import psycopg2, json, base64, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace

w = WorkspaceClient()

nb_code = """# Databricks notebook source
import psycopg2, json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
cred = w.api_client.do('POST', '/api/2.0/postgres/credentials', body={'endpoint': 'projects/compras-360/branches/production/endpoints/primary'})
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

def test_q(where_clause):
    sql = f'''
    SELECT COUNT(DISTINCT numero_oc)::int AS qty, COALESCE(SUM(valor_original_brl), 0)::float AS val
    FROM ordens_compra
    WHERE status_fechamento = 'ABERTA' AND dias_aberto > 90 {where_clause}
    '''
    cur.execute(sql)
    return cur.fetchone()

# 1. Base (all open >90d)
base_qty, base_val = test_q('')
# 2. Filter Empresa = BB
bb_qty, bb_val = test_q("AND org_desc IN ('BB')")
# 3. Filter Empresa = BQ
bq_qty, bq_val = test_q("AND org_desc IN ('BQ')")
# 4. Filter Grupo = INDIRETOS
ind_qty, ind_val = test_q("AND grupo_compras_oc IN ('INDIRETOS')")
# 5. Filter Grupo = DIRETOS
dir_qty, dir_val = test_q("AND grupo_compras_oc IN ('DIRETOS')")

cur.execute("SELECT COUNT(DISTINCT numero_oc) FROM ordens_compra WHERE status_fechamento = 'ABERTA' AND org_desc IN ('BB')")
tot_open_bb = cur.fetchone()[0]

cur.close()
conn.close()

res = {
    'base': {'qty': base_qty, 'val': base_val},
    'bb': {'qty': bb_qty, 'val': bb_val, 'tot_open': tot_open_bb, 'pct': round(bb_qty/tot_open_bb*100, 1) if tot_open_bb else 0},
    'bq': {'qty': bq_qty, 'val': bq_val},
    'indiretos': {'qty': ind_qty, 'val': ind_val},
    'diretos': {'qty': dir_qty, 'val': dir_val}
}
dbutils.notebook.exit(json.dumps(res))
"""

target = '/Users/renan.ferreira@grupobimbo.com/Drafts/test_oc90_queries'
w.workspace.import_(
    path=target,
    content=base64.b64encode(nb_code.encode('utf-8')).decode('utf-8'),
    format=workspace.ExportFormat.SOURCE,
    language=workspace.Language.PYTHON,
    overwrite=True
)

run = w.jobs.submit(
    run_name='test_oc90_queries',
    tasks=[
        jobs.SubmitTask(
            task_key='test',
            notebook_task=jobs.NotebookTask(notebook_path=target)
        )
    ]
)

while True:
    st = w.jobs.get_run(run_id=run.run_id)
    if st.state.life_cycle_state.value in ['TERMINATED', 'INTERNAL_ERROR', 'SKIPPED']:
        break
    time.sleep(2)

out = w.jobs.get_run_output(run_id=st.tasks[0].run_id)
if out.notebook_output and out.notebook_output.result:
    print('RESULT:\n', out.notebook_output.result)
elif out.error:
    print('ERROR:\n', out.error)
