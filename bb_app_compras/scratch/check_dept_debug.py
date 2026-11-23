import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient()

def run_query(sql):
    resp = w.statement_execution.execute_statement(
        warehouse_id='f4a2e26b8410f1e3',
        statement=sql,
        wait_timeout='30s'
    )
    statement_id = resp.statement_id
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(3)
        resp = w.statement_execution.get_statement(statement_id=statement_id)
    if resp.status.error:
        print("Error:", resp.status.error.message)
        return []
    if resp.manifest and resp.manifest.schema:
        cols = [c.name for c in resp.manifest.schema.columns]
        rows = [dict(zip(cols, r)) for r in (resp.result.data_array or [])]
        return rows
    return []

sql = """
SELECT 
    hp.PARTY_NAME,
    u.PersonId,
    u.Username,
    a.ASSIGNMENT_TYPE,
    a.ASSIGNMENT_STATUS_TYPE,
    a.PRIMARY_FLAG,
    a.ORGANIZATION_ID,
    o.NAME AS org_name,
    a.EFFECTIVE_START_DATE,
    a.EFFECTIVE_END_DATE
FROM cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo u
JOIN cat_ocloud_r5_dv.rg5glofsn_cz.hz_parties hp
    ON u.PartyId = hp.PARTY_ID
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_per_all_assignments_f a
    ON u.PersonId = a.PERSON_ID
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.hr_organization_units o
    ON a.ORGANIZATION_ID = o.ORGANIZATION_ID
WHERE hp.PARTY_NAME IN ('FELIPE DUARTE VIEIRA', 'SIDINEI SAMPAIO', 'INTERFACE ARKER')
ORDER BY hp.PARTY_NAME, a.EFFECTIVE_END_DATE DESC
"""


rows = run_query(sql)
for r in rows:
    print(r)
