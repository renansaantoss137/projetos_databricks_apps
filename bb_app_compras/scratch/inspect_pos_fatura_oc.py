from databricks.sdk import WorkspaceClient
import json

w = WorkspaceClient()

stmt = """
SELECT 
    ApInvoicesInvoiceNum,
    ApInvoicesInvoiceDate,
    ApInvoicesCreationDate,
    ApInvoicesApprovedDate,
    ApInvoiceLinesAllPoHeaderId,
    PurchasingDocumentHeaderSegment1,
    PurchasingDocumentHeaderApprovedDate,
    PurchasingDocumentHeaderCreationDate
FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_notas_ri
WHERE PurchasingDocumentHeaderSegment1 IN ('24089089761', '24089101410', '26089004906')
LIMIT 10
"""

try:
    res = w.statement_execution.execute_statement(
        warehouse_id='f4a2e26b8410f1e3',
        statement=stmt,
        wait_timeout='45s'
    )
    if res.result and res.result.data_array:
        for row in res.result.data_array:
            print(row)
    else:
        print("Status:", res.status)
except Exception as e:
    print("Warehouse error:", e)
