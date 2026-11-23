import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
from databricks.sdk.service.apps import AppDeployment

w = WorkspaceClient()

base_remote = "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/compras_360/dev/files/src/app"

print("1. Uploading app.py...")
for attempt in range(1, 4):
    try:
        with open("src/app/app.py", "rb") as f:
            w.workspace.upload(f"{base_remote}/app.py", f, overwrite=True, format=workspace.ImportFormat.AUTO)
        print("Uploaded app.py successfully!")
        break
    except Exception as e:
        print(f"Attempt {attempt} failed: {e}. Retrying in 2s...")
        time.sleep(2)
else:
    raise RuntimeError("Failed to upload app.py after 3 attempts")

print("2. Starting deployment to compras-360-dev...")
waiter = w.apps.deploy(
    app_name="compras-360-dev",
    app_deployment=AppDeployment(source_code_path=base_remote)
)
print("Deployment triggered. Waiting for completion...")

max_wait = 240
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
        print("Deployment FAILED!")
        break
    time.sleep(10)
