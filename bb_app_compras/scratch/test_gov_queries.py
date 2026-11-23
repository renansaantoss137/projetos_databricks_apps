import os, time, psycopg2, psycopg2.extras
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
cred = w.api_client.do("POST", "/api/2.0/postgres/credentials", body={
    "endpoint": "projects/compras-360/branches/production/endpoints/primary"
})
token = cred.get("token", "")
user = w.current_user.me().user_name

conn = psycopg2.connect(
    host="ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net",
    database="databricks_postgres",
    user=user,
    password=token,
    port=5432,
    sslmode="require",
    options="-c search_path=compras"
)

def run(name, sql):
    t0 = time.time()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        dt = time.time() - t0
        print(f"[{name}] SUCCESS in {dt:.2f}s - {len(rows)} rows returned")
        if rows and len(rows) <= 5:
            print("  Sample:", rows[:2])
        elif rows:
            print("  Sample (first 2):", rows[:2])
    except Exception as e:
        dt = time.time() - t0
        print(f"[{name}] ERROR in {dt:.2f}s: {e}")
        conn.rollback()

# Test 1: Count OCs with buyer in Compras vs outside Compras
run("Test 1: Compras buyer count", """
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN UPPER(COALESCE(departamento_comprador, '')) LIKE '%COMPRAS%' THEN 1 END) as dept_compras,
        COUNT(CASE WHEN CENTRALIZADO = 'DESCENTRALIZADO' THEN 1 END) as descentral,
        COUNT(CASE WHEN CENTRALIZADO = 'DESCENTRALIZADO' AND UPPER(COALESCE(departamento_comprador, '')) LIKE '%COMPRAS%' THEN 1 END) as false_positive_desc
    FROM ordens_compra
    WHERE SUBSTRING(data_oc, 1, 4) = '2026'
""")

# Test 2: Decentral query for Out/2026
run("Test 2: Decentral KPI query", """
    SELECT COUNT(*) AS qty, SUM(valor_oc) AS valor
    FROM (
        SELECT NUMERO_OC, SUM(valor_original_brl) AS valor_oc
        FROM ordens_compra
        WHERE SUBSTRING(data_oc, 1, 4) = '2026'
          AND CAST(SUBSTRING(data_oc, 6, 2) AS INT) = 10
          AND CENTRALIZADO = 'DESCENTRALIZADO'
          AND (numero_acordo IS NULL OR numero_acordo = '')
          AND UPPER(COALESCE(departamento_comprador, '')) NOT LIKE '%COMPRAS%'
        GROUP BY NUMERO_OC
        HAVING SUM(valor_original_brl) > 30000
    ) sub
""")

# Test 3: Total 2026 Decentral >30k
run("Test 3: Decentral KPI query FULL 2026", """
    SELECT COUNT(*) AS qty, SUM(valor_oc) AS valor
    FROM (
        SELECT NUMERO_OC, SUM(valor_original_brl) AS valor_oc
        FROM ordens_compra
        WHERE SUBSTRING(data_oc, 1, 4) = '2026'
          AND CENTRALIZADO = 'DESCENTRALIZADO'
          AND (numero_acordo IS NULL OR numero_acordo = '')
          AND UPPER(COALESCE(departamento_comprador, '')) NOT LIKE '%COMPRAS%'
        GROUP BY NUMERO_OC
        HAVING SUM(valor_original_brl) > 30000
    ) sub
""")

conn.close()
