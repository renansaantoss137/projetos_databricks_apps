import sys
sys.path.insert(0, 'src/app')
import app

print("Checking colaboradores for Rafael Cordeiro:")
res = app.query("""
    SELECT matricula, id_colaborador, nome_completo, email, area, diretoria, nm_unidade 
    FROM colaboradores 
    WHERE UPPER(nome_completo) LIKE '%CORDEIRO%' 
       OR UPPER(nome_completo) LIKE '%RAFAEL%'
    LIMIT 10
""")
for r in res:
    print(r)

print("\nChecking ordens_compra for OC 26089064670 (from screenshot):")
oc_res = app.query("""
    SELECT numero_oc, nome_requisitante, departamento_requisitante, email_requisitante, requisicao, usuario, comprador
    FROM ordens_compra
    WHERE numero_oc = '26089064670'
    LIMIT 5
""")
for r in oc_res:
    print(r)
