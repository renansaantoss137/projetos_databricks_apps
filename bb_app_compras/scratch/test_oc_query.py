from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Check OC 26089064913 completely
sql = """
WITH asg_dept AS (
    SELECT 
        a.person_id,
        a.organization_id,
        org.NAME AS DEPARTAMENTO,
        ROW_NUMBER() OVER (
            PARTITION BY a.person_id 
            ORDER BY 
                CASE WHEN a.assignment_type = 'E' THEN 1 ELSE 2 END,
                CASE WHEN a.primary_flag = 'Y' THEN 1 ELSE 2 END,
                CASE WHEN a.assignment_status_type = 'ACTIVE' THEN 1 ELSE 2 END,
                a.effective_end_date DESC,
                a.effective_start_date DESC
        ) AS rn
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_per_all_assignments_f a
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.hr_organization_units org 
        ON a.organization_id = org.ORGANIZATION_ID
)
SELECT 
    PHA.SEGMENT1 AS NUMERO_OC,
    PHA.AGENT_ID,
    buyer.Username AS USERNAME_COMPRADOR,
    buyer.PersonNamePEOFullName AS NOME_COMPRADOR_FULL,
    TRIM(CONCAT(NVL(buyer.PersonNamePEOFirstName, ''), ' ', NVL(buyer.PersonNamePEOLastName, ''))) AS NOME_COMPRADOR,
    buyer.EmailAddress AS EMAIL_COMPRADOR,
    dept_buyer.DEPARTAMENTO AS DEPARTAMENTO_COMPRADOR,
    req.REQUISICAO,
    req.SOLICITANTE_REQUISICAO,
    req.EMAIL_REQUISITANTE,
    dept_req.DEPARTAMENTO AS DEPARTAMENTO_REQUISITANTE
FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all PHA
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo buyer 
    ON CAST(PHA.AGENT_ID AS BIGINT) = buyer.PersonId
LEFT JOIN (SELECT person_id, DEPARTAMENTO FROM asg_dept WHERE rn = 1) dept_buyer 
    ON CAST(PHA.AGENT_ID AS BIGINT) = dept_buyer.person_id
LEFT JOIN (
    SELECT 
        a.PoHeaderId, 
        user1.PersonId AS RequesterPersonId,
        user1.PersonNamePEOFullName AS SOLICITANTE_REQUISICAO, 
        user1.EmailAddress AS EMAIL_REQUISITANTE, 
        b.RequisitionNumber AS REQUISICAO
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_por_requisitionlineextractpvo a 
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_por_requisitionheaderextractpvo b 
        ON a.RequisitionHeaderId = b.RequisitionHeaderId 
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo user1 
        ON COALESCE(a.RequesterId, b.PreparerId) = user1.PersonId
) req ON req.PoHeaderId = PHA.PO_HEADER_ID
LEFT JOIN (SELECT person_id, DEPARTAMENTO FROM asg_dept WHERE rn = 1) dept_req 
    ON req.RequesterPersonId = dept_req.person_id
WHERE PHA.SEGMENT1 = '26089064913'
LIMIT 5
"""

resp = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement=sql,
    wait_timeout='45s'
)
print("=== OC 26089064913 TEST ===")
if resp.manifest and resp.manifest.schema:
    cols = [c.name for c in resp.manifest.schema.columns]
    if resp.result and resp.result.data_array:
        for r in resp.result.data_array:
            d = dict(zip(cols, r))
            for k, v in d.items():
                print(f"  {k}: {v}")
