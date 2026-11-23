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

cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print("--- Query 1: Total & Count in Lakebase with October 2026 filters ---")
sql_tot = """
SELECT COUNT(*) AS qty, SUM(valor_oc) AS total_val
FROM (
    SELECT oc.NUMERO_OC, SUM(oc.valor_original_brl) AS valor_oc
    FROM ordens_compra oc
    WHERE SUBSTRING(oc.DATA_OC, 1, 4) IN ('2026')
      AND CASE WHEN LENGTH(COALESCE(oc.DATA_OC, '')) >= 7 THEN CAST(SUBSTRING(oc.DATA_OC, 6, 2) AS INT) ELSE NULL END IN (10)
      AND oc.CENTRALIZADO = 'DESCENTRALIZADO'
      AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
      AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
      AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
    GROUP BY oc.NUMERO_OC
    HAVING SUM(oc.valor_original_brl) > 30000
) sub
"""
cur.execute(sql_tot)
print("Total result:", cur.fetchall())

print("\n--- Query 2: Top 15 OCs by SUM(oc.valor_original_brl) ---")
sql_top = """
SELECT oc.NUMERO_OC, 
       COUNT(*) as num_linhas, 
       SUM(oc.valor_original_brl) as valor_oc_sum, 
       MAX(oc.valor_original_brl) as valor_oc_max,
       MIN(oc.valor_original_brl) as valor_oc_min,
       MIN(oc.data_oc) as data_oc,
       MAX(oc.fornecedor) as fornecedor,
       MAX(oc.nome_usuario) as comprador,
       MAX(oc.usuario) as usuario
FROM ordens_compra oc
WHERE SUBSTRING(oc.DATA_OC, 1, 4) IN ('2026')
  AND CASE WHEN LENGTH(COALESCE(oc.DATA_OC, '')) >= 7 THEN CAST(SUBSTRING(oc.DATA_OC, 6, 2) AS INT) ELSE NULL END IN (10)
  AND oc.CENTRALIZADO = 'DESCENTRALIZADO'
  AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
  AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
  AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
GROUP BY oc.NUMERO_OC
HAVING SUM(oc.valor_original_brl) > 30000
ORDER BY valor_oc_sum DESC
LIMIT 15
"""
cur.execute(sql_top)
rows = cur.fetchall()
for r in rows:
    print(f"OC: {r['numero_oc']} | Linhas: {r['num_linhas']} | Sum: R$ {r['valor_oc_sum']:,.2f} | Max: R$ {r['valor_oc_max']:,.2f} | Min: {r['valor_oc_min']} | Forn: {r['fornecedor']} | Comp: {r['comprador']}")

print("\n--- Query 3: What about default filter without month/ano? Or what filters are sent from frontend? ---")
cur.close()
conn.close()
