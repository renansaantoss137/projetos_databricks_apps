import sys
sys.path.insert(0, 'src/app')
import app

sql = """
SELECT numero_oc, usuario, nome_usuario, comprador, comprador_funcional, usuario_comprador, email_comprador, departamento_comprador, nome_requisitante, departamento_requisitante, requisicao
FROM ordens_compra
WHERE numero_oc = '26089017779'
LIMIT 5
"""
try:
    rows = app.query(sql)
    print(f"Total rows: {len(rows)}")
    for r in rows:
        print(r)
except Exception as e:
    print(f"Error: {e}")
