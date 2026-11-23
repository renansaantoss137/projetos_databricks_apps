import time
import urllib.request
import json
import ssl
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
from databricks.sdk.service.apps import AppDeployment

w = WorkspaceClient()

base_remote = "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/compras_360/dev/files/src/app"

print("1. Uploading app.py...")
with open("src/app/app.py", "rb") as f:
    w.workspace.upload(f"{base_remote}/app.py", f, overwrite=True, format=workspace.ImportFormat.AUTO)
print("Uploaded app.py successfully!")

print("2. Uploading i18n.js...")
with open("src/app/i18n.js", "rb") as f:
    w.workspace.upload(f"{base_remote}/i18n.js", f, overwrite=True, format=workspace.ImportFormat.AUTO)
print("Uploaded i18n.js successfully!")

print("3. Starting deployment to compras-360-dev...")
waiter = w.apps.deploy(
    app_name="compras-360-dev",
    app_deployment=AppDeployment(source_code_path=base_remote)
)
print("Deployment triggered. Waiting for completion...")

# Poll deployment status
max_wait = 180
start = time.time()
while time.time() - start < max_wait:
    app_info = w.apps.get(name="compras-360-dev")
    active_dep = getattr(app_info, "active_deployment", None)
    status = getattr(active_dep, "status", None)
    state = getattr(status, "state", None) if status else None
    state_str = getattr(state, "value", str(state))
    msg = getattr(status, "message", "") if status else ""
    app_status = getattr(app_info, "app_status", None)
    app_state = getattr(app_status, "state", None) if app_status else None
    app_state_str = getattr(app_state, "value", str(app_state))
    
    print(f"[{int(time.time() - start)}s] App state: {app_state_str} | Deployment state: {state_str} | Msg: {msg}")
    
    if state_str == "SUCCEEDED":
        print("Deployment SUCCEEDED!")
        break
    elif state_str == "FAILED":
        print("Deployment FAILED:", msg)
        break
    time.sleep(10)

# Verify app URL and API response
app_info = w.apps.get(name="compras-360-dev")
app_url = getattr(app_info, "url", None)
print("App URL:", app_url)

if app_url:
    test_url = f"{app_url}/api/governance/deviation-impact?ano=2026&mes=10"
    print("Testing API:", test_url)
    req = urllib.request.Request(test_url, headers={
        "Authorization": f"Bearer {w.config.token}"
    })
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print("=== LIVE API RESPONSE (deviation-impact Out/2026) ===")
            print(json.dumps(data, indent=2))
    except Exception as e:
        print("API test failed:", e)

    test_url2 = f"{app_url}/api/governance/kpis?ano=2026&mes=10"
    print("Testing KPIs API:", test_url2)
    req2 = urllib.request.Request(test_url2, headers={
        "Authorization": f"Bearer {w.config.token}"
    })
    try:
        with urllib.request.urlopen(req2, context=ctx, timeout=30) as resp:
            data2 = json.loads(resp.read().decode('utf-8'))
            print("=== LIVE API RESPONSE (governance/kpis Out/2026) ===")
            print(json.dumps(data2, indent=2))
    except Exception as e:
        print("KPIs test failed:", e)
