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

print("Full KPI response:", r_kpi)

print("\n--- Testing /api/governance/exceptions?ano=2026&mes=10&tipo=urgente ---")
r_exc = requests.get(f"{app_url}/api/governance/exceptions?ano=2026&mes=10&tipo=urgente", headers=headers).json()
print("Exceptions response keys:", r_exc.keys() if isinstance(r_exc, dict) else type(r_exc))
print("Exceptions content:", r_exc)
