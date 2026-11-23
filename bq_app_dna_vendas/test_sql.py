from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementExecutionAPI

w = WorkspaceClient()
print("Current user:", w.current_user.me().user_name)

res = w.statement_execution.execute_statement(
    warehouse_id="f4a2e26b8410f1e3",
    statement="SELECT 'CONNECTION_SUCCESS' as status",
    wait_timeout="30s"
)
print("Status:", res.status.state)
if res.result and res.result.data_array:
    print("Result:", res.result.data_array)
