from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

stmt = """
SELECT SEGMENT1, DOCUMENT_STATUS, CREATED_BY
FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all
WHERE SEGMENT1 = '26089040407'
"""
res = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=stmt,
    wait_timeout='30s'
)
print("PO Header 26089040407:", res.result.data_array if res.result else res.status)
