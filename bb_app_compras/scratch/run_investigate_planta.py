import io
import time
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

# 1. Conferir totais de Spend por Planta para 2026 e INDIRETOS (como no app)
spend_check_sql = \"\"\"
SELECT
    COALESCE(NULLIF(TRIM(planta), ''), 'Não identificada') AS unidade,
    ROUND(SUM(valor_liquido_brl)::numeric / 1e6, 1) AS net_spend_mi,
    ROUND((SUM(valor_liquido_brl) * 100.0 / SUM(SUM(valor_liquido_brl)) OVER())::numeric, 0) AS pct
FROM notas_ri
WHERE SUBSTRING(data_lancamento, 1, 4) = '2026'
  AND UPPER(TRIM(COALESCE(grupo_compras, ''))) = 'INDIRETOS'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%RGB%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE 'ADV%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%FOPAG%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%ARKER%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%FISCAL%'
GROUP BY COALESCE(NULLIF(TRIM(planta), ''), 'Não identificada')
HAVING SUM(valor_liquido_brl) > 0
ORDER BY SUM(valor_liquido_brl) DESC
LIMIT 10;
\"\"\"
cur.execute(spend_check_sql)
print("=== SPEND CHECK (COMPARE WITH SCREENSHOT) ===")
for row in cur.fetchall():
    print(row)

# 2. Obter as maiores notas fiscais (agrupadas por NF ou por RI/linha) sem planta identificada
top_nfs_sql = \"\"\"
SELECT 
    numero_ri,
    nota_fiscal,
    empresa,
    cnpj_bimbo,
    nome_fornecedor,
    numero_oc,
    ds_item,
    categoria_item,
    unidade,
    planta,
    centro_custo,
    conta_contabil,
    data_lancamento,
    dt_nota,
    ROUND(SUM(valor_liquido_brl)::numeric, 2) AS total_liquido_brl,
    ROUND(SUM(valor_nota_brl)::numeric, 2) AS total_nota_brl,
    COUNT(*) as qtd_linhas
FROM notas_ri
WHERE SUBSTRING(data_lancamento, 1, 4) = '2026'
  AND UPPER(TRIM(COALESCE(grupo_compras, ''))) = 'INDIRETOS'
  AND (planta IS NULL OR TRIM(planta) = '' OR TRIM(planta) = 'Não identificada')
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%RGB%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE 'ADV%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%FOPAG%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%ARKER%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%FISCAL%'
GROUP BY 
    numero_ri,
    nota_fiscal,
    empresa,
    cnpj_bimbo,
    nome_fornecedor,
    numero_oc,
    ds_item,
    categoria_item,
    unidade,
    planta,
    centro_custo,
    conta_contabil,
    data_lancamento,
    dt_nota
ORDER BY total_liquido_brl DESC
LIMIT 25;
\"\"\"
cur.execute(top_nfs_sql)
cols = [desc[0] for desc in cur.description]
top_nfs = [dict(zip(cols, row)) for row in cur.fetchall()]
print("=== TOP NOTAS SEM PLANTA ===")
print(json.dumps(top_nfs, indent=2, default=str))

# 3. Analisar o campo UNIDADE e CENTRO_CUSTO nas notas sem planta
unidade_dist_sql = \"\"\"
SELECT 
    COALESCE(NULLIF(TRIM(unidade), ''), '[UNIDADE VAZIA]') AS unidade_val,
    COUNT(*) AS total_linhas,
    COUNT(DISTINCT nota_fiscal) AS total_nfs,
    ROUND(SUM(valor_liquido_brl)::numeric / 1e6, 2) AS spend_mi
FROM notas_ri
WHERE SUBSTRING(data_lancamento, 1, 4) = '2026'
  AND UPPER(TRIM(COALESCE(grupo_compras, ''))) = 'INDIRETOS'
  AND (planta IS NULL OR TRIM(planta) = '' OR TRIM(planta) = 'Não identificada')
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%RGB%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE 'ADV%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%FOPAG%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%ARKER%'
  AND UPPER(COALESCE(nota_fiscal, '')) NOT LIKE '%FISCAL%'
GROUP BY COALESCE(NULLIF(TRIM(unidade), ''), '[UNIDADE VAZIA]')
ORDER BY spend_mi DESC
LIMIT 20;
\"\"\"
cur.execute(unidade_dist_sql)
cols = [desc[0] for desc in cur.description]
print("=== DISTRIBUICAO DE UNIDADE NAS NOTAS SEM PLANTA ===")
for row in cur.fetchall():
    print(dict(zip(cols, row)))

conn.close()
"""

target = '/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/compras_360/scratch_investigate_planta.py'
w.workspace.upload(target, io.BytesIO(script_content.encode('utf-8')), overwrite=True, format=workspace.ImportFormat.AUTO)

run = w.jobs.submit(
    run_name='investigate_planta',
    tasks=[
        jobs.SubmitTask(
            task_key='investigate',
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
