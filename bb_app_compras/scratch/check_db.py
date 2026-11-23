import os
from databricks.sdk import WorkspaceClient
import psycopg2

w = WorkspaceClient()
cred = w.api_client.do('POST', '/api/2.0/postgres/credentials', body={
    'endpoint': 'projects/compras-360/branches/production/endpoints/primary'
})
token = cred.get('token', '')

host = 'ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net'
conn = psycopg2.connect(
    host=host,
    dbname='databricks_postgres',
    user=w.current_user.me().user_name,
    password=token,
    port=5432,
    sslmode='require'
)
cur = conn.cursor()
cur.execute('SELECT current_schema(), version()')
print('DB connected:', cur.fetchone())

cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'compras'
""")
tables = cur.fetchall()
print('Tables in compras schema:', [t[0] for t in tables])

# Check distinct years and months in the primary tables
for tbl in ['fato_notas', 'compras_fato_notas', 'fato_compras_centralizada']:
    try:
        cur.execute(f"SELECT DISTINCT ano FROM compras.{tbl} ORDER BY ano DESC LIMIT 10")
        print(f"Years in compras.{tbl}:", cur.fetchall())
        cur.execute(f"SELECT ano, COUNT(*) FROM compras.{tbl} GROUP BY ano ORDER BY ano DESC")
        print(f"Row count by year in compras.{tbl}:", cur.fetchall())
    except Exception as e:
        conn.rollback()
        # table might not exist
        pass

# Check distinct is_fornecedor_nao_negociavel
for tbl in ['fato_notas', 'compras_fato_notas']:
    try:
        cur.execute(f"SELECT DISTINCT is_fornecedor_nao_negociavel FROM compras.{tbl}")
        print(f"Distinct is_fornecedor_nao_negociavel in {tbl}:", cur.fetchall())
    except Exception as e:
        conn.rollback()
        pass

cur.close()
conn.close()
