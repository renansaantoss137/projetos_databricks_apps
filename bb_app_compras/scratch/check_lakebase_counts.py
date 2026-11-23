import sys, io, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace

w = WorkspaceClient()

# Get credentials
cred = w.api_client.do('POST', '/api/2.0/postgres/credentials', body={
    'endpoint': 'projects/compras-360/branches/production/endpoints/primary'
})
pg_token = cred.get('token', '')
pg_user = w.current_user.me().user_name

script_content = """import sys, psycopg2, json

pg_user = sys.argv[1]
pg_token = sys.argv[2]

conn = psycopg2.connect(
    host='ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net',
    database='databricks_postgres',
    user=pg_user,
    password=pg_token,
    port=5432,
    sslmode='require',
    options='-c search_path=compras'
)
cur = conn.cursor()

# Query counts for 2026-10
q = \"\"\"
SELECT 
    COUNT(DISTINCT nf.nota_fiscal) as tot_nfs_sem_filtro,
    COUNT(DISTINCT CASE WHEN nf.is_fornecedor_nao_negociavel = 'NEGOCIAVEL' THEN nf.nota_fiscal END) as tot_nfs_negociavel,
    COUNT(DISTINCT CASE WHEN nf.is_fornecedor_especial = 'ESPECIAL' THEN nf.nota_fiscal END) as tot_nfs_especial,
    COUNT(DISTINCT CASE WHEN nf.is_fornecedor_especial != 'ESPECIAL' THEN nf.nota_fiscal END) as tot_nfs_nao_especial,
    COUNT(DISTINCT CASE WHEN nf.is_fornecedor_especial != 'ESPECIAL' AND nf.is_fornecedor_nao_negociavel = 'NEGOCIAVEL' THEN nf.nota_fiscal END) as tot_nfs_nao_esp_negoc,
    
    -- Numerador (pos_fatura):
    COUNT(DISTINCT CASE
        WHEN nf.numero_oc != 'Nota sem OC'
         AND nf.numero_oc IS NOT NULL
         AND nf.numero_oc != ''
         AND oc.dt_aprovacao ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
         AND COALESCE(nf.dt_nota, nf.data_lancamento) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
         AND SUBSTRING(COALESCE(nf.dt_nota, nf.data_lancamento), 1, 10)::date < SUBSTRING(oc.dt_aprovacao, 1, 10)::date
        THEN nf.nota_fiscal
    END) as pf_todas,
    
    COUNT(DISTINCT CASE
        WHEN nf.numero_oc != 'Nota sem OC'
         AND nf.numero_oc IS NOT NULL
         AND nf.numero_oc != ''
         AND oc.dt_aprovacao ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
         AND COALESCE(nf.dt_nota, nf.data_lancamento) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
         AND SUBSTRING(COALESCE(nf.dt_nota, nf.data_lancamento), 1, 10)::date < SUBSTRING(oc.dt_aprovacao, 1, 10)::date
         AND COALESCE(nf.is_fornecedor_especial, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'
        THEN nf.nota_fiscal
    END) as pf_sem_especial,

    COUNT(DISTINCT CASE
        WHEN nf.numero_oc != 'Nota sem OC'
         AND nf.numero_oc IS NOT NULL
         AND nf.numero_oc != ''
         AND oc.dt_aprovacao ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
         AND COALESCE(nf.dt_nota, nf.data_lancamento) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
         AND SUBSTRING(COALESCE(nf.dt_nota, nf.data_lancamento), 1, 10)::date < SUBSTRING(oc.dt_aprovacao, 1, 10)::date
         AND COALESCE(nf.is_fornecedor_especial, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'
         AND COALESCE(nf.is_fornecedor_nao_negociavel, 'NEGOCIAVEL') = 'NEGOCIAVEL'
        THEN nf.nota_fiscal
    END) as pf_sem_esp_e_negoc

FROM notas_ri nf
LEFT JOIN ordens_compra oc ON nf.chave_oc_linha = oc.chave_oc_linha
WHERE SUBSTRING(nf.data_pagamento, 1, 4) = '2026'
  AND SUBSTRING(nf.data_pagamento, 6, 2) = '10'
\"\"\"
cur.execute(q)
cols = [desc[0] for desc in cur.description]
row = cur.fetchone()
print(dict(zip(cols, row)))
conn.close()
"""

target = '/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/compras_360/scratch_test_pf.py'
w.workspace.upload(target, io.BytesIO(script_content.encode('utf-8')), overwrite=True, format=workspace.ImportFormat.AUTO)

run = w.jobs.submit(
    run_name='check_pf_counts',
    tasks=[
        jobs.SubmitTask(
            task_key='counts',
            spark_python_task=jobs.SparkPythonTask(
                python_file=target,
                parameters=[pg_user, pg_token]
            ),
            existing_cluster_id='0711-194930-gejtkmmb'
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
