import sys
import os
sys.path.insert(0, os.path.abspath('src/app'))
import psycopg2
from app import _PG_HOST, _PG_PORT, _PG_DATABASE, _PG_USER, _PG_PASSWORD, _PG_SCHEMA

conn = psycopg2.connect(
    host=_PG_HOST, port=_PG_PORT, dbname=_PG_DATABASE, user=_PG_USER, password=_PG_PASSWORD
)
cur = conn.cursor()

print("--- NOTAS_RI: is_fornecedor_sem_oc ---")
try:
    cur.execute(f'SELECT is_fornecedor_sem_oc, count(*) FROM "{_PG_SCHEMA}"."notas_ri" GROUP BY is_fornecedor_sem_oc')
    print(cur.fetchall())
except Exception as e:
    print('err:', e)
    conn.rollback()

print("--- NOTAS_RI: is_fornecedor_nao_negociavel ---")
try:
    cur.execute(f'SELECT is_fornecedor_nao_negociavel, count(*) FROM "{_PG_SCHEMA}"."notas_ri" GROUP BY is_fornecedor_nao_negociavel')
    print(cur.fetchall())
except Exception as e:
    print('err:', e)
    conn.rollback()

print("--- NOTAS_RI: ANOS ---")
try:
    cur.execute(f'SELECT ano, count(*) FROM "{_PG_SCHEMA}"."notas_ri" GROUP BY ano ORDER BY ano')
    print(cur.fetchall())
except Exception as e:
    print('err:', e)
    conn.rollback()

print("--- ORDENS_COMPRA: is_fornecedor_sem_oc ---")
try:
    cur.execute(f'SELECT is_fornecedor_sem_oc, count(*) FROM "{_PG_SCHEMA}"."ordens_compra" GROUP BY is_fornecedor_sem_oc')
    print(cur.fetchall())
except Exception as e:
    print('err:', e)
    conn.rollback()

cur.close()
conn.close()
