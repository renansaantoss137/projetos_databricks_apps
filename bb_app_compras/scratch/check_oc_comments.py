import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "f4a2e26b8410f1e3"

query_oc_details = """
SELECT 
    h.SEGMENT1 AS NUMERO_OC,
    h.COMMENTS,
    h.NOTE_TO_VENDOR,
    dff.TIPO_ORDEN_,
    req.REQUISICAO,
    req.EmergencyReqFlag
FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all h
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_draftpurchasingdocumentheaderdffextractpvo dff
    ON CAST(h.PO_HEADER_ID AS BIGINT) = CAST(dff.s_k_5000 AS BIGINT)
LEFT JOIN (
    SELECT 
        a.PoHeaderId, 
        MAX(b.RequisitionNumber) AS REQUISICAO, 
        MAX(b.EmergencyReqFlag) AS EmergencyReqFlag
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_por_requisitionlineextractpvo a 
    JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_por_requisitionheaderextractpvo b 
        ON a.RequisitionHeaderId = b.RequisitionHeaderId 
    GROUP BY a.PoHeaderId
) req ON h.PO_HEADER_ID = req.PoHeaderId
WHERE h.SEGMENT1 IN ('26089059497', '26089030052')
"""

resp = w.statement_execution.execute_statement(
    warehouse_id=wh_id,
    statement=query_oc_details,
    wait_timeout="40s"
)

if resp.result and resp.result.data_array:
    cols = [c.name for c in resp.manifest.schema.columns]
    for r in resp.result.data_array:
        print(dict(zip(cols, r)), flush=True)
else:
    print(resp.status, flush=True)
