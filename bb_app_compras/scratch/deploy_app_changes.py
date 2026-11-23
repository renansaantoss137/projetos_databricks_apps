import os
import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
from databricks.sdk.service.apps import AppDeployment

w = WorkspaceClient()

files_to_sync = [
    "app.py",
    "governanca.html",
    "i18n.js",
    "guia.html"
]

destinations = [
    "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/prod/files/src/app",
    "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/compras_360/dev/files/src/app"
]

print("1. Uploading modified files...")
for fname in files_to_sync:
    local_path = os.path.join("src", "app", fname)
    with open(local_path, "rb") as f:
        content = f.read()
    for dest_dir in destinations:
        dest_path = f"{dest_dir}/{fname}"
        try:
            w.workspace.upload(dest_path, content, overwrite=True, format=workspace.ImportFormat.AUTO)
            print(f"[OK] Uploaded {fname} -> {dest_path}")
        except Exception as e:
            print(f"[WARN] Failed to upload {fname} to {dest_path}: {e}")

print("\n2. Deploying to Databricks App compras-360...")
try:
    dep = w.apps.deploy(
        app_name="compras-360",
        app_deployment=AppDeployment(source_code_path="/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/prod/files/src/app")
    )
    print("Deployment initiated. Waiting for status...")
    max_wait = 180
    start = time.time()
    while time.time() - start < max_wait:
        app_info = w.apps.get(name="compras-360")
        active_dep = getattr(app_info, "active_deployment", None)
        status = getattr(active_dep, "status", None)
        state_str = getattr(getattr(status, "state", None), "value", str(getattr(status, "state", None)))
        msg = getattr(status, "message", "") if status else ""
        print(f"[{int(time.time() - start)}s] Deploy State: {state_str} | {msg}")
        if state_str == "SUCCEEDED":
            print("[SUCCESS] App compras-360 deployed successfully!")
            break
        elif state_str in ("FAILED", "INTERNAL_ERROR"):
            print(f"[ERROR] Deployment failed: {msg}")
            break
        time.sleep(5)
except Exception as e:
    print("[ERROR] Deploy error:", e)
