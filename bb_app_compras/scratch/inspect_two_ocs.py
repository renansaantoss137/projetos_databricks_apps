import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "f4a2e26b8410f1e3"

def run_query(stmt):
    resp = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=stmt,
        wait_timeout="50s"
    )
    if resp.result and resp.result.data_array:
        cols = [c.name for c in resp.manifest.schema.columns]
        return [dict(zip(cols, r)) for r in resp.result.data_array]
    return str(resp.status)

# 1. Inspect both OCs in vw_po_headers_all and DFF
print("=== 1. PO HEADERS AND DFF ===")
stmt1 = """
SELECT 
    h.PO_HEADER_ID,
    h.SEGMENT1 AS NUMERO_OC,
    h.DOCUMENT_STATUS,
    h.CREATION_DATE,
    dff.s_k_5000,
    dff.TIPO_ORDEN_
FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all h
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_draftpurchasingdocumentheaderdffextractpvo dff
    ON CAST(h.PO_HEADER_ID AS BIGINT) = CAST(dff.s_k_5000 AS BIGINT)
WHERE h.SEGMENT1 IN ('26089059497', '26089030052')
"""
print(json.dumps(run_query(stmt1), indent=2))

# 2. Inspect both in vw_ordens_compra
print("=== 2. VW_ORDENS_COMPRA ===")
stmt2 = """
SELECT 
    NUMERO_OC,
    URGENTE,
    REQUISICAO,
    DATA_OC,
    STATUS_APROVACAO
FROM cat_dnabb_dv.grobbcompr_cz.vw_ordens_compra
WHERE NUMERO_OC IN ('26089059497', '26089030052')
"""
print(json.dumps(run_query(stmt2), indent=2))

# 3. Inspect both in vw_notas_ri
print("=== 3. VW_NOTAS_RI ===")
stmt3 = """
SELECT 
    NUMERO_OC,
    NOTA_FISCAL,
    URGENTE,
    DATA_LANCAMENTO
FROM cat_dnabb_dv.grobbcompr_cz.vw_notas_ri
WHERE NUMERO_OC IN ('26089059497', '26089030052')
"""
print(json.dumps(run_query(stmt3), indent=2))
