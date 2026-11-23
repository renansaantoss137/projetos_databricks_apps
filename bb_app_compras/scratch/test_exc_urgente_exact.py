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

print("1. KPI /api/governance/kpis?ano=2026&mes=10:")
r_kpi = requests.get(f"{app_url}/api/governance/kpis?ano=2026&mes=10", headers=headers).json()
print("   urgente_qty:", r_kpi.get('urgente_qty'), "urgente_val:", r_kpi.get('urgente_val'))

print("\n2. Table /api/governance/exceptions-table?type=urgente&per_page=0&ano=2026&mes=10:")
r_exc = requests.get(f"{app_url}/api/governance/exceptions-table?type=urgente&per_page=0&ano=2026&mes=10", headers=headers)
print("   Status:", r_exc.status_code)
try:
    data = r_exc.json()
    print("   Total rows returned:", len(data))
    if data:
        print("   First row:", data[0])
except Exception as e:
    print("   Failed to parse JSON:", e, r_exc.text[:500])
