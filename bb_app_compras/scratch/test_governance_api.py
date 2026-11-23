import requests
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
token = w.config.token or w.config.authenticate()
headers = {}
if isinstance(token, str):
    headers["Authorization"] = f"Bearer {token}"
elif hasattr(token, "token"):
    headers["Authorization"] = f"Bearer {token.token}"
elif callable(token):
    headers.update(token())

app_url = "https://compras-360-8674310331778219.19.azure.databricksapps.com"

print("--- Testing /api/governance/deviation-impact ---")
# 1. Base query (no filters)
r_base = requests.get(f"{app_url}/api/governance/deviation-impact", headers=headers).json()
oc90_base = next((x for x in r_base if '90 dias' in x['label']), None)
print("Base (no filters):", oc90_base)

# 2. Date query (ano=2026 vs ano=2025)
r_2026 = requests.get(f"{app_url}/api/governance/deviation-impact?ano=2026", headers=headers).json()
oc90_2026 = next((x for x in r_2026 if '90 dias' in x['label']), None)
print("With ano=2026:", oc90_2026)

r_2025 = requests.get(f"{app_url}/api/governance/deviation-impact?ano=2025", headers=headers).json()
oc90_2025 = next((x for x in r_2025 if '90 dias' in x['label']), None)
print("With ano=2025:", oc90_2025)

# 3. Entity query (empresa=BB vs empresa=BQ)
r_bb = requests.get(f"{app_url}/api/governance/deviation-impact?empresa=BB", headers=headers).json()
oc90_bb = next((x for x in r_bb if '90 dias' in x['label']), None)
print("With empresa=BB:", oc90_bb)

r_bq = requests.get(f"{app_url}/api/governance/deviation-impact?empresa=BQ", headers=headers).json()
oc90_bq = next((x for x in r_bq if '90 dias' in x['label']), None)
print("With empresa=BQ:", oc90_bq)

# 4. Entity query (grupo_compras=INDIRETOS vs DIRETOS)
r_ind = requests.get(f"{app_url}/api/governance/deviation-impact?grupo_compras=INDIRETOS", headers=headers).json()
oc90_ind = next((x for x in r_ind if '90 dias' in x['label']), None)
print("With grupo_compras=INDIRETOS:", oc90_ind)

r_dir = requests.get(f"{app_url}/api/governance/deviation-impact?grupo_compras=DIRETOS", headers=headers).json()
oc90_dir = next((x for x in r_dir if '90 dias' in x['label']), None)
print("With grupo_compras=DIRETOS:", oc90_dir)

print("\n--- Testing /api/governance/kpis ---")
r_kpi = requests.get(f"{app_url}/api/governance/kpis?empresa=BB", headers=headers).json()
print("KPI oc90_qty:", r_kpi.get('oc90_qty'))
print("KPI oc90_val:", r_kpi.get('oc90_val'))
print("KPI total_oc_abertas:", r_kpi.get('total_oc_abertas'))
