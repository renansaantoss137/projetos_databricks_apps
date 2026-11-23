import os
import psycopg2
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
user = w.current_user.me().user_name
print(f"User: {user}")

cred = w.api_client.do("POST", "/api/2.0/postgres/credentials", body={
    "endpoint": "projects/compras-360/branches/production/endpoints/primary"
})
token = cred.get("token", "")
print(f"Token length: {len(token)}")

conn = psycopg2.connect(
    host="ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net",
    database="databricks_postgres",
    user=user,
    password=token,
    port=5432,
    sslmode="require",
    options="-c search_path=compras"
)
print("Connected successfully!")
cur = conn.cursor()
cur.execute("SELECT count(*) FROM notas_ri")
print(f"Total rows in notas_ri: {cur.fetchone()[0]}")
conn.close()
