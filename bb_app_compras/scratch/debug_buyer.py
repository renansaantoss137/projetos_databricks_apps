from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState
import time

w = WorkspaceClient()

sql = """
WITH users_dedup AS (
    SELECT 
      PersonId,
      Username,
      PersonNamePEOFullName,
      PersonFirstLastName,
      ROW_NUMBER() OVER (PARTITION BY PersonId ORDER BY StartDate DESC) AS rn
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo
    WHERE PersonId IS NOT NULL
)
SELECT 
    poh.AGENT_ID,
    u.PersonId,
    u.Username,
    u.PersonFirstLastName,
    asg.ASSIGNMENT_TYPE,
    asg.ASSIGNMENT_STATUS_TYPE,
    asg.PRIMARY_FLAG,
    asg.ORGANIZATION_ID,
    o.NAME AS DEPT_NAME
FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all poh
JOIN users_dedup u ON CAST(poh.AGENT_ID AS BIGINT) = u.PersonId AND u.rn = 1
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_per_all_assignments_f asg ON u.PersonId = asg.PERSON_ID
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.hr_organization_units o ON asg.ORGANIZATION_ID = o.ORGANIZATION_ID
WHERE u.PersonFirstLastName = 'FELIPE DUARTE VIEIRA'
LIMIT 5
"""

resp = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=sql,
    wait_timeout='50s'
)
while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
    time.sleep(3)
    resp = w.statement_execution.get_statement(statement_id=resp.statement_id)

if resp.result and resp.result.data_array:
    data = resp.result.data_array
else:
    chunk = w.statement_execution.get_statement_result_chunk_n(statement_id=resp.statement_id, chunk_index=0)
    data = chunk.data_array

cols = [c.name for c in resp.manifest.schema.columns]
for r in data or []:
    print(dict(zip(cols, r)))
