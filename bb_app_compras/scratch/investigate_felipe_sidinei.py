from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState
import time

w = WorkspaceClient()

# 1. Investigate Felipe and Sidinei in CRM users, Person, and Assignments
sql = """
SELECT 
    u.Username,
    u.PersonId,
    u.PersonNamePEOFullName,
    TRIM(CONCAT_WS(' ', u.PersonNamePEOFirstName, u.PersonNamePEOLastName)) AS PersonFirstLastName,
    u.EmailAddress,
    u.ActiveFlag,
    u.UserAccountStatus,
    u.StartDate,
    u.EndDate
FROM cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo u
WHERE UPPER(u.PersonNamePEOFullName) LIKE '%FELIPE%DUARTE%'
   OR UPPER(u.PersonNamePEOFullName) LIKE '%SIDINEI%SAMPAIO%'
   OR UPPER(u.Username) LIKE '%FELIPE%DUARTE%'
   OR UPPER(u.Username) LIKE '%SIDINEI%SAMPAIO%'
"""

resp = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=sql,
    wait_timeout='30s'
)
stmt_id = resp.statement_id
while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
    time.sleep(3)
    resp = w.statement_execution.get_statement(statement_id=stmt_id)

cols = [c.name for c in resp.manifest.schema.columns]
data = resp.result.data_array if (resp.result and resp.result.data_array) else []
print("=== CRM USERS ===")
for r in data:
    print(dict(zip(cols, r)))
