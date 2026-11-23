import sys, os
sys.path.insert(0, os.path.abspath('src/app'))

try:
    from app import _get_conn, _PG_SCHEMA, query
    conn = _get_conn()
    print("Database connection:", conn)
    cur = conn.cursor()
    cur.execute(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{_PG_SCHEMA}'")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables in schema '{_PG_SCHEMA}':", tables)
    conn.close()
except Exception as e:
    print("Database check failed:", e)
