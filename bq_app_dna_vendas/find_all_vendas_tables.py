import subprocess
import json

cmd = ["databricks", "schemas", "list", "cat_dnabb_dv", "-o", "json"]
res = subprocess.run(cmd, capture_output=True, text=True)
schemas = json.loads(res.stdout)

all_vendas_tables = []

for s in schemas:
    s_name = s.get("name")
    cmd_t = ["databricks", "tables", "list", "cat_dnabb_dv", s_name, "-o", "json"]
    r_t = subprocess.run(cmd_t, capture_output=True)
    if r_t.returncode == 0:
        try:
            tbls = json.loads(r_t.stdout.decode('utf-8', errors='replace'))
            for t in tbls:
                t_name = t.get("name", "")
                if any(k in t_name.lower() for k in ["venda", "ppto", "pedido", "budget", "forecast", "open_order"]):
                    all_vendas_tables.append(f"{s_name}.{t_name}")
        except Exception:
            pass

print("=== ALL MATCHING TABLES IN cat_dnabb_dv ===")
for t in sorted(all_vendas_tables):
    print(" ", t)
