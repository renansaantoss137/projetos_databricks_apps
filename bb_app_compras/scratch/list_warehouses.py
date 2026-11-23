from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
warehouses = list(w.warehouses.list())
for wh in warehouses:
    print(f"Warehouse: id={wh.id}, name={wh.name}, state={wh.state}")
