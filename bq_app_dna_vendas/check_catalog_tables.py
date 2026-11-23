import subprocess
import json

cmd = ["databricks", "tables", "list", "cat_dnabb_dv", "bracatlg_lz", "-o", "json"]
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode != 0:
    print("Error:", res.stderr)
else:
    tables = json.loads(res.stdout)
    table_names = sorted([t.get("name") for t in tables if "name" in t])
    print(f"Total tables found in cat_dnabb_dv.bracatlg_lz: {len(table_names)}")
    
    # Check our target keywords: vendas, pedidos, ppto, produto, cliente, grupo, calendario, fabrica
    keywords = ["venda", "pedido", "ppto", "produt", "client", "grupo", "calenda", "fabrica", "bqb"]
    print("\n--- Matching Target Tables ---")
    matched = set()
    for name in table_names:
        for kw in keywords:
            if kw in name.lower():
                matched.add(name)
                break
    for m in sorted(matched):
        print(f"  - {m}")
        
    print("\n--- All Table Names (First 50) ---")
    for name in table_names[:50]:
        print(f"  {name}")
