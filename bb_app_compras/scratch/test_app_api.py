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
else:
    # try header auth directly
    h = w.config.as_dict()
    print("Config keys:", h.keys())

# Let's test calling the app API
app_url = "https://compras-360-8674310331778219.19.azure.databricksapps.com"
r = requests.get(f"{app_url}/api/spend/by-plant?ano=2026&macro_categoria=Indiretos", headers=headers)
print("Status:", r.status_code)
print("Response:", r.text[:500])
