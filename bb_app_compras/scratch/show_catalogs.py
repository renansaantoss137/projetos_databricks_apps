from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "f4a2e26b8410f1e3"

def run_query(stmt):
    resp = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=stmt,
        wait_timeout="30s"
    )
    if resp.result and resp.result.data_array:
        return resp.result.data_array
    return resp.status

print("Catalogs:", run_query("SHOW CATALOGS"))
