import subprocess
import json

tables = [
    "cat_dnabb_dv.grobbbqb_sz.vendas_pedidos_bq",
    "cat_dnabb_dv.grobbbqb_sz.budget_forecast_bq",
    "cat_dnabb_dv.bracatlg_lz.produtos_view",
    "cat_dnabb_dv.bracatlg_lz.grupo_clientes_view",
    "cat_dnabb_dv.bracatlg_cz.clientes_mc1_oracle",
    "cat_dnabb_dv.bracatlg_lz.calendario_bimbo"
]

for t in tables:
    res = subprocess.run(['databricks', 'tables', 'get', t, '-o', 'json'], capture_output=True)
    if res.returncode == 0:
        data = json.loads(res.stdout.decode('utf-8', errors='replace'))
        print("="*60)
        print(f"TABLE: {data.get('full_name')}")
        cols = [f"{c.get('name')} ({c.get('type_name')})" for c in data.get('columns', [])]
        print("Columns (" + str(len(cols)) + "):", ", ".join(cols[:15]))
        if len(cols) > 15:
            print("  ...", ", ".join(cols[15:30]))
    else:
        print(f"Error fetching {t}:", res.stderr.decode('utf-8', errors='replace')[:100])
