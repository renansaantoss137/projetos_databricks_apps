import os
import sys
import json
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.compute import Language

w = WorkspaceClient()
cluster_id = '0711-194930-gejtkmmb'

# Get Lakebase token
cred = w.api_client.do('POST', '/api/2.0/postgres/credentials', body={
    'endpoint': 'projects/compras-360/branches/production/endpoints/primary'
})
token = cred.get('token', '')
user = w.current_user.me().user_name

def run_in_cluster(python_code):
    ctx = w.command_execution.create(cluster_id=cluster_id, language=Language.PYTHON).result()
    try:
        cmd = w.command_execution.execute(cluster_id=cluster_id, context_id=ctx.id, language=Language.PYTHON, command=python_code).result()
        if cmd.results:
            if hasattr(cmd.results, 'data') and cmd.results.data:
                print(cmd.results.data)
            if hasattr(cmd.results, 'cause') and cmd.results.cause:
                print("ERROR:", cmd.results.cause)
    finally:
        w.command_execution.destroy(cluster_id=cluster_id, context_id=ctx.id)

test_code = f"""
import psycopg2
for h in ['ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net']:
    try:
        conn = psycopg2.connect(
            host=h,
            port=5432,
            dbname='databricks_postgres',
            user='{user}',
            password='{token}',
            sslmode='require',
            options='-c search_path=compras,public'
        )
        cur = conn.cursor()
        cur.execute('''
            SELECT numero_acordo, status, dt_criacao, valor_total, valor_liberado
            FROM compras.acordos_compra
            WHERE numero_acordo IN ('24089000208', '26089000025', '26089000024', '24089001454')
        ''')
        rows = cur.fetchall()
        for r in rows:
            print('ROW:', r)
        cur.close()
        conn.close()
    except Exception as e:
        print('Error:', e)
"""

if __name__ == '__main__':
    run_in_cluster(test_code)
