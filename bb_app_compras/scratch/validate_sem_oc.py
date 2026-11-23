from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
cluster_id = '0711-194930-gejtkmmb'

host_val = w.config.host
token_val = w.config.token

remote_script = """
import psycopg2
from databricks.sdk import WorkspaceClient

w2 = WorkspaceClient(host='__HOST__', token='__TOKEN__')
cred = w2.api_client.do('POST', '/api/2.0/postgres/credentials', body={
    'endpoint': 'projects/compras-360/branches/production/endpoints/primary'
})
token = cred.get('token', '')
me = w2.current_user.me()
pg_user = me.user_name""".replace('__HOST__', host_val).replace('__TOKEN__', token_val) + """

conn = psycopg2.connect(
    host='ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net',
    database='databricks_postgres',
    user=pg_user,
    password=token,
    port=5432,
    sslmode='require'
)
cur = conn.cursor()

# 1. Com filtro NEGOCIAVEL
cur.execute('''
SELECT 
    COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' THEN NOTA_FISCAL END) AS sem_oc_qty,
    SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS sem_oc_val,
    SUM(VALOR_LIQUIDO_BRL) AS total_spend,
    COUNT(DISTINCT NOTA_FISCAL) AS total_notas
FROM compras.notas_ri
WHERE ano = '2026' AND mes = '9' AND is_fornecedor_nao_negociavel = 'NEGOCIAVEL'
''')
r_neg = cur.fetchone()
print('=== 1. NEGOCIAVEL (Mes 09/2026) ===')
print('sem_oc_qty:', r_neg[0])
print(f'sem_oc_val: R$ {r_neg[1]:,.2f}')
print(f'total_spend: R$ {r_neg[2]:,.2f}')
print('total_notas:', r_neg[3])
pct_spend = (r_neg[1] / r_neg[2] * 100) if r_neg[2] else 0
print(f'pct_spend: {pct_spend:.2f}%')

# 2. Sem filtro de fornecedor (TODOS)
cur.execute('''
SELECT 
    COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' THEN NOTA_FISCAL END) AS sem_oc_qty,
    SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS sem_oc_val,
    SUM(VALOR_LIQUIDO_BRL) AS total_spend,
    COUNT(DISTINCT NOTA_FISCAL) AS total_notas
FROM compras.notas_ri
WHERE ano = '2026' AND mes = '9'
''')
r_all = cur.fetchone()
print('\\n=== 2. TODOS OS FORNECEDORES (Sem filtro de fornecedor, Mes 09/2026) ===')
print('sem_oc_qty:', r_all[0])
print(f'sem_oc_val: R$ {r_all[1]:,.2f}')
print(f'total_spend: R$ {r_all[2]:,.2f}')
print('total_notas:', r_all[3])
pct_spend_all = (r_all[1] / r_all[2] * 100) if r_all[2] else 0
print(f'pct_spend: {pct_spend_all:.2f}%')

# 3. Fornecedores NAO NEGOCIAVEIS isolados
cur.execute('''
SELECT 
    COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' THEN NOTA_FISCAL END) AS sem_oc_qty,
    SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS sem_oc_val,
    SUM(VALOR_LIQUIDO_BRL) AS total_spend,
    COUNT(DISTINCT NOTA_FISCAL) AS total_notas
FROM compras.notas_ri
WHERE ano = '2026' AND mes = '9' AND is_fornecedor_nao_negociavel = 'NÃO NEGOCIAVEL'
''')
r_nao = cur.fetchone()
print('\\n=== 3. APENAS NAO NEGOCIAVEIS (Mes 09/2026) ===')
print('sem_oc_qty:', r_nao[0])
print(f'sem_oc_val: R$ {r_nao[1]:,.2f}')
print(f'total_spend: R$ {r_nao[2]:,.2f}')
print('total_notas:', r_nao[3])
pct_spend_nao = (r_nao[1] / r_nao[2] * 100) if r_nao[2] else 0
print(f'pct_spend: {pct_spend_nao:.2f}%')

# 4. Top Fornecedores NAO NEGOCIAVEIS que geram Nota sem OC
cur.execute('''
SELECT 
    nome_fornecedor,
    COUNT(DISTINCT NOTA_FISCAL) AS qtd_nfs,
    SUM(VALOR_LIQUIDO_BRL) AS val
FROM compras.notas_ri
WHERE ano = '2026' AND mes = '9' AND NUMERO_OC = 'Nota sem OC' AND is_fornecedor_nao_negociavel = 'NÃO NEGOCIAVEL'
GROUP BY nome_fornecedor
ORDER BY qtd_nfs DESC
LIMIT 10
''')
rows_nao = cur.fetchall()
print('\\n=== Top Fornecedores NAO NEGOCIAVEIS com Nota sem OC em 09/2026 ===')
for row in rows_nao:
    print(f'  {row[0]}: {row[1]} notas, R$ {row[2]:,.2f}')

# 5. Top Fornecedores NEGOCIAVEIS com Nota sem OC
cur.execute('''
SELECT 
    nome_fornecedor,
    COUNT(DISTINCT NOTA_FISCAL) AS qtd_nfs,
    SUM(VALOR_LIQUIDO_BRL) AS val
FROM compras.notas_ri
WHERE ano = '2026' AND mes = '9' AND NUMERO_OC = 'Nota sem OC' AND is_fornecedor_nao_negociavel = 'NEGOCIAVEL'
GROUP BY nome_fornecedor
ORDER BY qtd_nfs DESC
LIMIT 10
''')
rows_neg = cur.fetchall()
print('\\n=== Top Fornecedores NEGOCIAVEIS com Nota sem OC em 09/2026 ===')
for row in rows_neg:
    print(f'  {row[0]}: {row[1]} notas, R$ {row[2]:,.2f}')

conn.close()
"""

from databricks.sdk.service.compute import Language

ctx = w.command_execution.create(cluster_id=cluster_id, language=Language.PYTHON).result()
print('Context ID:', ctx.id)
res = w.command_execution.execute(cluster_id=cluster_id, context_id=ctx.id, language=Language.PYTHON, command=remote_script).result()
w.command_execution.destroy(cluster_id=cluster_id, context_id=ctx.id)
print(res.as_dict())
