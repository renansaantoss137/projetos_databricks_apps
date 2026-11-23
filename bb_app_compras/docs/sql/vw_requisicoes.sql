WITH asg_dept AS (
    SELECT * FROM (
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
        WHERE a.person_id IS NOT NULL
    ) WHERE rn = 1
)
SELECT
    CASE WHEN SUBSTR(b.RequisitionNumber, 1, 2) = 'BQ' THEN 'BQ' ELSE 'BB' END AS EMPRESA,
    b.RequisitionHeaderId AS REQ_ID,
    b.RequisitionNumber AS REQUISICAO,
    b.Description AS DESCRICAO_REQ,
    CASE WHEN a.NUMEROS_OC IS NULL OR TRIM(a.NUMEROS_OC) = '' 
         THEN 'Requisicao sem OC' ELSE a.NUMEROS_OC END AS NUMERO_OC,
    b.CreatedBy AS USER_REQUISICAO,
    CONCAT(NVL(user1.PersonNamePEOFirstName,''), ' ', NVL(user1.PersonNamePEOMiddleNames,''), ' ', NVL(user1.PersonNamePEOLastName,'')) AS REQUISITANTE,
    user1.EmailAddress AS EMAIL_REQUISITANTE,
    dept_req.DEPARTAMENTO AS DEPARTAMENTO_REQUISITANTE,
    b.LastUpdatedBy AS USER_APROVADOR,
    apr.APROVADOR AS NOME_APROVADOR,
    a.COMPRADOR_SUGERIDO,
    dept_buyer.DEPARTAMENTO AS DEPARTAMENTO_COMPRADOR,
    DATE_FORMAT((TO_TIMESTAMP(b.CreationDate, "yyyy-MM-dd'T'HH:mm:ss.SSS") - INTERVAL '3' HOUR), 'yyyy-MM-dd') AS DT_CRIACAO,
    DATE_FORMAT(a.LastApprovalDate, 'yyyy-MM-dd') AS DT_APROVACAO,
    NVL(a.QTD_LINHAS, 0) AS QTD_LINHAS,
    a.VALOR_CONVERTIDO AS VALOR_REQUISICAO,
    CASE 
        WHEN b.DocumentStatus = 'APPROVED' THEN 'Aprovado'
        WHEN b.DocumentStatus = 'CANCELED' THEN 'Cancelada'
        WHEN b.DocumentStatus = 'PENDING APPROVAL' THEN 'Aprovação pendente'
        WHEN b.DocumentStatus = 'REJECTED' THEN 'Rejeitada'
        WHEN b.DocumentStatus = 'RETURNED' THEN 'Devolvida'
        WHEN b.DocumentStatus = 'INCOMPLETE' THEN 'Incompleta'
        WHEN b.DocumentStatus = 'WITHDRAWN' THEN 'Retirada'
        WHEN b.DocumentStatus = 'CLOSED FOR RECEIVING' THEN 'Fechada para Recebimento'
        WHEN b.DocumentStatus = 'CLOSED' THEN 'Fechada'
        WHEN b.DocumentStatus = 'OPEN' THEN 'Aberta'
        WHEN b.DocumentStatus = 'CLOSED FOR INVOICING' THEN 'Fechada para Faturamento'
        ELSE '' END AS STATUS,
    NVL(a.STATUS_ORDEM, '') AS STATUS_ORDEM
FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_por_requisitionheaderextractpvo b
LEFT JOIN (
    SELECT 
        a.RequisitionHeaderId, 
        COUNT(1) AS QTD_LINHAS,
        MAX(a.ListName) AS ListName, 
        SUM(a.AssessableValue) AS AssessableValue,
        ROUND(SUM(
            NVL(a.Quantity, 0) * NVL(a.CurrencyUnitPrice, 0) * 
            CASE 
                WHEN NVL(a.CurrencyCode, 'BRL') = 'BRL' THEN 1.0
                WHEN NVL(a.Rate, 0) > 0 THEN a.Rate
                WHEN NVL(po_rate.Rate, 0) > 0 THEN po_rate.Rate
                ELSE 1.0
            END
        ), 2) AS VALOR_CONVERTIDO,
        MAX(a.LastApprovalDate) AS LastApprovalDate, 
        MAX(a.PoHeaderId) AS PoHeaderId,
        MAX(a.SuggestedBuyerId) AS SuggestedBuyerId,
        CONCAT_WS(', ', COLLECT_SET(
            CASE 
                WHEN po.Segment1 IS NOT NULL AND TRIM(po.Segment1) <> '' AND po.Segment1 <> '0' 
                THEN po.Segment1 
            END
        )) AS NUMEROS_OC,
        CONCAT_WS(', ', COLLECT_SET(
            CASE 
                WHEN po.DocumentStatus = 'APPROVED' THEN 'Aprovado'
                WHEN po.DocumentStatus = 'CANCELED' THEN 'Cancelada'
                WHEN po.DocumentStatus = 'PENDING APPROVAL' THEN 'Aprovação pendente'
                WHEN po.DocumentStatus = 'REJECTED' THEN 'Rejeitada'
                WHEN po.DocumentStatus = 'RETURNED' THEN 'Devolvida'
                WHEN po.DocumentStatus = 'INCOMPLETE' THEN 'Incompleta'
                WHEN po.DocumentStatus = 'WITHDRAWN' THEN 'Retirada'
                WHEN po.DocumentStatus = 'CLOSED FOR RECEIVING' THEN 'Fechada para Recebimento'
                WHEN po.DocumentStatus = 'CLOSED' THEN 'Fechada'
                WHEN po.DocumentStatus = 'OPEN' THEN 'Aberta'
                WHEN po.DocumentStatus = 'CLOSED FOR INVOICING' THEN 'Fechada para Faturamento'
                ELSE NULL 
            END
        )) AS STATUS_ORDEM,
        MAX(CONCAT(NVL(user2.PersonNamePEOFirstName,''), ' ', NVL(user2.PersonNamePEOMiddleNames,''), ' ', NVL(user2.PersonNamePEOLastName,''))) AS COMPRADOR_SUGERIDO
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_por_requisitionlineextractpvo a
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo user2 ON a.SuggestedBuyerId = user2.PersonId
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentheaderextractpvo po ON a.PoHeaderId = po.PoHeaderId
    LEFT JOIN (
        SELECT PoHeaderId, MAX(Rate) AS Rate
        FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentdistributionextractpvo
        WHERE Rate IS NOT NULL AND Rate > 0
        GROUP BY PoHeaderId
    ) po_rate ON a.PoHeaderId = po_rate.PoHeaderId
    WHERE a.FundsStatus IN ('LIQUIDATED', 'RESERVED')
      AND NVL(a.LineStatus, '') NOT IN ('CANCELED', 'CANCELLED', 'CANCELADA', 'REJECTED', 'INCOMPLETE', 'WITHDRAWN')
    GROUP BY a.RequisitionHeaderId
) a ON a.RequisitionHeaderId = b.RequisitionHeaderId
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo user1 ON b.CreatedBy = user1.Username
LEFT JOIN asg_dept dept_req ON user1.PersonId = dept_req.person_id
LEFT JOIN asg_dept dept_buyer ON a.SuggestedBuyerId = dept_buyer.person_id
LEFT JOIN (
    SELECT A.* FROM (
        SELECT RequisitionHeaderRequisitionHeaderId, DisplayName AS APROVADOR,
            ROW_NUMBER() OVER (PARTITION BY RequisitionHeaderRequisitionHeaderId ORDER BY EffectiveStartDate DESC) AS RowNum
        FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prcpo_requisitionactionhistorypvo
        WHERE PurchasingActionHistoryActionCode = 'APPROVE'
    ) A WHERE RowNum = 1
) apr ON b.RequisitionHeaderId = apr.RequisitionHeaderRequisitionHeaderId
WHERE b.DocumentStatus NOT IN ('CANCELED', 'REJECTED', 'RETURNED', 'INCOMPLETE', 'WITHDRAWN')