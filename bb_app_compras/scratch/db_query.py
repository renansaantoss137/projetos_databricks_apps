import sys, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient()

def execute(sql):
    resp = w.statement_execution.execute_statement(
        warehouse_id='f4a2e26b8410f1e3',
        statement=sql,
        wait_timeout='30s'
    )
    stmt_id = resp.statement_id
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(3)
        resp = w.statement_execution.get_statement(statement_id=stmt_id)
    if resp.status.error:
        print("SQL ERROR:", resp.status.error.message)
        return []
    if resp.result and resp.result.data_array is not None:
        cols = [c.name for c in resp.manifest.schema.columns]
        return [dict(zip(cols, r)) for r in resp.result.data_array]
    try:
        chunk = w.statement_execution.get_statement_result_chunk_n(statement_id=stmt_id, chunk_index=0)
        cols = [c.name for c in resp.manifest.schema.columns]
        return [dict(zip(cols, r)) for r in (chunk.data_array or [])]
    except Exception as e:
        print("Fetch chunk error:", e)
        return []

if __name__ == "__main__":
    sql = sys.argv[1] if len(sys.argv) > 1 else "SELECT 1"
    rows = execute(sql)
    for r in rows:
        print(r)
