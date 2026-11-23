from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "f4a2e26b8410f1e3"

resp = w.statement_execution.execute_statement(
    warehouse_id=wh_id,
    statement="SELECT current_catalog(), current_schema()",
    wait_timeout="30s"
)
print("Status:", resp.status.state)
if resp.result and resp.result.data_array:
    print("Result:", resp.result.data_array)
