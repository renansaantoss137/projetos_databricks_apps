from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
resp = w.workspace.download("/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/prod/files/src/app/app.py")
content = resp.read()
with open("scratch/app_from_workspace.py", "wb") as f:
    f.write(content)
print("Successfully downloaded app.py from workspace, size:", len(content))
