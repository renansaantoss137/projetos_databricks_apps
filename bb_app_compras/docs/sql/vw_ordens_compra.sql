WITH users_dedup AS (
    SELECT * FROM (
        SELECT 
            PersonId,
            Username,
            EmailAddress,
            PersonNamePEOFullName,
            TRIM(CONCAT_WS(' ', PersonNamePEOFirstName, PersonNamePEOLastName)) AS PersonFirstLastName,
            ROW_NUMBER() OVER (
                PARTITION BY PersonId 
                ORDER BY 
                    CASE WHEN ActiveFlag = 'Y' THEN 1 ELSE 2 END,
                    CASE WHEN UserAccountStatus = 'ACTIVE' THEN 1 ELSE 2 END,
                    EffectiveEndDate DESC,
                    LastUpdateDate DESC
            ) AS rn
        FROM cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo
        WHERE PersonId IS NOT NULL
    ) WHERE rn = 1
),
asg_dept AS (
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
),
oc_detalhe AS (
    SELECT 
        apr.APROVADOR,
        CASE WHEN ROUND(EXTRACT(DAY FROM (TO_TIMESTAMP(c.DT_NOTA) - TO_TIMESTAMP(PHA.APPROVED_DATE)))) < 0 THEN 'SIM' ELSE 'NÃO' END AS OC_POS_FATURA,
        c.DT_NOTA, i.ACORDO_COMPRA, PHA.SEGMENT1 AS NUMERO_OC, BPA.SEGMENT1 AS NUMERO_ACORDO,
        BPA.DOCUMENT_STATUS AS ACORDO_STATUS,
        CAST(BPA.CREATION_DATE AS STRING) AS ACORDO_DT_CRIACAO,
        CAST(BPA.START_DATE AS STRING) AS ACORDO_DATA_INICIAL,
        CAST(BPA.END_DATE AS STRING) AS ACORDO_DATA_FINAL,
        BPA.BLANKET_TOTAL_AMOUNT AS ACORDO_VALOR_TOTAL,
        BPA.MIN_RELEASE_AMOUNT AS ACORDO_VALOR_MIN_LIBERACAO,
        BPA.AMOUNT_RELEASED AS ACORDO_VALOR_LIBERADO,
        BPA.COMMENTS AS ACORDO_DESCRICAO,
        BPA.FOB_LOOKUP_CODE AS ACORDO_FOB,
        BPA.FREIGHT_TERMS_LOOKUP_CODE AS ACORDO_CONDICAO_FRETE,
        TER_BPA.PaymentTermName AS ACORDO_CONDICAO_PGTO,
        PHA.TYPE_LOOKUP_CODE AS TIPO, PHA.COMMENTS AS DESCRICAO,
        ITM.ITEM_NUMBER AS ITEM_AQUISICAO,
        ITM.DESCRIPTION AS DESCRICAO_ITEM,
        CAT.CATEGORY_NAME AS CATEGORIA_ITEM,
        CAT.CATEGORY_CODE AS CATEGORIA_CODIGO,
        ITM.ITEM_TYPE,
        ITM.ITEM_CLASS_CODE,
        CASE
            WHEN TRIM(COALESCE(ITM.ITEM_NUMBER, '')) = '' AND PHA.CREATED_BY = 'BBAPPA0001' THEN 'COMERCIAL'
            WHEN TRIM(COALESCE(ITM.ITEM_NUMBER, '')) = '' THEN 'INDIRETOS'
            WHEN UPPER(SUBSTR(TRIM(ITM.ITEM_NUMBER), 1, 1)) IN ('A', 'B') THEN 'DIRETOS'
            ELSE 'INDIRETOS'
        END AS GRUPO_COMPRAS_OC,
        PDL.ItemDescription AS DESCRICAO_LINHA,
        CASE WHEN PHA.CURRENCY_CODE = 'BRL' THEN NVL(PDA.AmountBilled, 0) ELSE NVL(PDA.AmountBilled, 0) * NVL(PDA.Rate, 1) END AS VALOR_UTILIZADO,
        PDA.QuantityOrdered AS QTD_SOLICITADA, NVL(PDL.Quantity, 0) AS QTD,
        NVL(PDA.QuantityBilled, 0) AS QTD_FATURADA, NVL(PDL.UnitPrice, 0) AS PRECO_UNIT,
        PDA.Rate AS TAXA_CAMBIO, PDA.RateDate AS DT_TAXA_CAMBIO,
        CASE WHEN PHA.CURRENCY_CODE = 'BRL' THEN NVL(PDL.UnitPrice, 0) * NVL(PDL.Quantity, 0) ELSE NVL(PDL.UnitPrice, 0) * NVL(PDL.Quantity, 0) * NVL(PDA.Rate, 1) END AS VALOR_ORIGINAL,
        PDL.LineNum AS LINHA_OC,
        PHA.SEGMENT1 || '_' || CAST(COALESCE(PDL.LineNum, 0) AS INT) AS CHAVE_OC_LINHA,
        CASE WHEN PHA.APPROVED_FLAG = 'Y' THEN 'APPROVED' ELSE PHA.APPROVED_FLAG END AS STATUS_APROVACAO,
        CASE 
            WHEN PHA.DOCUMENT_STATUS = 'FINALLY CLOSED' THEN 'FINALMENTE FECHADO'
            WHEN PHA.DOCUMENT_STATUS = 'INCOMPLETE' THEN 'INCOMPLETA'
            WHEN PHA.DOCUMENT_STATUS = 'CLOSED' THEN 'FECHADO'
            WHEN PHA.DOCUMENT_STATUS = 'CANCELED' THEN 'CANCELADA'
            WHEN PHA.DOCUMENT_STATUS = 'OPEN' THEN 'ABERTA'
            WHEN PHA.DOCUMENT_STATUS = 'CLOSED FOR RECEIVING' THEN 'FECHADO P/ RECEBIMENTO'
            WHEN PHA.DOCUMENT_STATUS = 'CLOSED FOR INVOICING' THEN 'FECHADO P/ FATURAMENTO'
            WHEN PHA.DOCUMENT_STATUS = 'REJECTED' THEN 'REJEITADA'
            WHEN PHA.DOCUMENT_STATUS = 'PENDING APPROVAL' THEN 'PENDENTE APROVACAO'
            WHEN PHA.DOCUMENT_STATUS = 'WITHDRAWN' THEN 'RETIRADA'
            WHEN PHA.DOCUMENT_STATUS = 'PENDING ACKNOWLEDGMENT' THEN 'PENDENTE CONFIRMACAO'
            ELSE 'SEM STATUS' 
        END AS STATUS_FECHAMENTO,
        CASE WHEN UPPER(COALESCE(dff_po.TIPO_ORDEN_, '')) = 'URGENTE' THEN 'SIM' ELSE 'NAO' END AS URGENTE,
        CONCAT(LPAD(MONTH(PHA.CREATION_DATE), 2, '0'), '-', YEAR(PHA.CREATION_DATE)) AS ANO_MES,
        PHA.CREATION_DATE AS DATA_OC, PHA.APPROVED_DATE AS DT_APROVACAO,
        LLOC.DT_NECESSIDADE, LLOC.DT_PROMESSA,
        PHA.LAST_UPDATE_DATE AS DT_ATUALIZACAO, PHA.CLOSED_DATE AS DT_FECHAMENTO, '1900-01-01' AS DT_RELEASE,
        PHA.CREATED_BY,
        CASE WHEN user1.PersonNamePEOFullName IS NULL THEN PHA.CREATED_BY ELSE user1.PersonNamePEOFullName END AS NOME_USUARIO,
        user1.EmailAddress AS EMAIL_USUARIO,
        PHA.VENDOR_ID, PHA.VENDOR_SITE_ID,
        SUPS.SuppPartyPartyName AS FORNECEDOR, SUPS.SupplierSegment1 AS NUMERO_FORNECEDOR,
        SUP.SupplierOrganizationTypeLookupCode AS TIPO_FORNECEDOR,
        SUP.SupplierVendorTypeLookupCode AS TIPO_VENDOR,
        SUPS.PartySitePartySiteName AS ID_CNPJ,
        TER.ApTermsLinesDueDays AS PO_DIAS_PGTO, TER2.ApTermsLinesDueDays AS FORNECEDOR_DIAS_PGTO,
        PHA.CURRENCY_CODE AS CODIGO_MOEDA,
        CASE WHEN COALESCE(PHA.REQ_BU_ID, PHA.PRC_BU_ID) = 300000002033035 THEN 'BB'
             WHEN COALESCE(PHA.REQ_BU_ID, PHA.PRC_BU_ID) = 300000002033048 THEN 'BQ' ELSE '' END AS org_desc,
        CASE WHEN NVL(PDA.AmountBilled, 0) = 0 THEN 'SIM' ELSE 'NAO' END AS OC_SEM_USO,
        GCC.CodeCombinationSegment1||'-'||GCC.CodeCombinationSegment2||'-'||GCC.CodeCombinationSegment3||'-'||GCC.CodeCombinationSegment4||'-'||GCC.CodeCombinationSegment5||'-'||GCC.CodeCombinationSegment6||'-'||GCC.CodeCombinationSegment7||'-'||GCC.CodeCombinationSegment8 AS CONTA_DEBITO,
        CASE WHEN GCC.CodeCombinationSegment3 = '1130' THEN 'DIRETO' WHEN GCC.CodeCombinationSegment3 = '1137' AND GCC.CodeCombinationSegment4 = '0001' THEN 'DIRETO' ELSE 'INDIRETO' END AS TIPO_COMPRA,
        CASE WHEN UPPER(COALESCE(NULLIF(buyer.PersonFirstLastName, ''), buyer.PersonNamePEOFullName, '')) LIKE '%ABEL MOREIRA MARTINS FILHO%' THEN 'DESCENTRALIZADO'
             WHEN UPPER(COALESCE(cf.COMPRADOR_FUNCIONAL, '')) LIKE '%ABEL MOREIRA MARTINS FILHO%' THEN 'DESCENTRALIZADO'
             WHEN UPPER(COALESCE(user1.PersonNamePEOFullName, PHA.CREATED_BY, '')) LIKE '%ARKER%' THEN 'CENTRALIZADO'
             WHEN UPPER(COALESCE(NULLIF(buyer.PersonFirstLastName, ''), buyer.PersonNamePEOFullName, '')) LIKE '%ARKER%' THEN 'CENTRALIZADO'
             WHEN PHA.TYPE_LOOKUP_CODE = 'BLANKET' THEN 'CENTRALIZADO' 
             WHEN BPA.SEGMENT1 IS NOT NULL AND TRIM(BPA.SEGMENT1) <> '' THEN 'CENTRALIZADO' 
             WHEN UPPER(COALESCE(dept_buyer.DEPARTAMENTO, '')) LIKE '%COMPRAS%' THEN 'CENTRALIZADO' 
             WHEN UPPER(COALESCE(cf.AREA, '')) LIKE '%COMPRAS%' THEN 'CENTRALIZADO' 
             ELSE 'DESCENTRALIZADO' 
        END AS CENTRALIZADO,
        REPLACE(FV_UNI.description, 'BBR_', '') AS UNIDADE,
        FV_AREA.description AS AREA, FV_CAT.description AS CATEGORIA_OC,
        -- Solicitante / Requisitante
        COALESCE(req.SOLICITANTE_REQUISICAO, user_dist.PersonNamePEOFullName) AS SOLICITANTE_REQUISICAO, 
        req.REQUISICAO, 
        COALESCE(req.EMAIL_REQUISITANTE, user_dist.EmailAddress) AS EMAIL_REQUISITANTE,
        COALESCE(dept_req.DEPARTAMENTO, dept_dist.DEPARTAMENTO) AS DEPARTAMENTO_REQUISITANTE,
        -- Comprador
        COALESCE(NULLIF(buyer.PersonFirstLastName, ''), buyer.PersonNamePEOFullName) AS COMPRADOR,
        buyer.Username AS USUARIO_COMPRADOR,
        buyer.EmailAddress AS EMAIL_COMPRADOR,
        dept_buyer.DEPARTAMENTO AS DEPARTAMENTO_COMPRADOR,
        CASE WHEN fe.COD_FORNECEDOR_ORACLE IS NOT NULL THEN 'SIM' ELSE 'NAO' END AS FORNECEDOR_ESPECIAL,
        CASE WHEN fn.COD_FORNECEDOR_ORACLE IS NOT NULL THEN 'SIM' ELSE 'NAO' END AS FORNECEDOR_NAO_NEGOCIAVEL
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all PHA
    LEFT JOIN (
        SELECT PoHeaderId, PoLineId, 
               SUM(AmountBilled) AS AmountBilled, 
               SUM(UnencumberedAmount) AS UnencumberedAmount, 
               MAX(CodeCombinationId) AS CodeCombinationId, 
               SUM(QuantityOrdered) AS QuantityOrdered, 
               SUM(QuantityBilled) AS QuantityBilled, 
               MAX(Rate) AS Rate, 
               MAX(RateDate) AS RateDate,
               MAX(DeliverToPersonId) AS DeliverToPersonId
        FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentdistributionextractpvo 
        GROUP BY PoHeaderId, PoLineId
    ) PDA ON PHA.PO_HEADER_ID = PDA.PoHeaderId
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentlineextractpvo PDL ON PHA.PO_HEADER_ID = PDL.PoHeaderId AND PDA.PoLineId = PDL.PoLineId
    LEFT JOIN (
        SELECT PoHeaderId, PoLineId,
               MIN(CAST(NeedByDate AS DATE)) AS DT_NECESSIDADE,
               MIN(CAST(PromisedDate AS DATE)) AS DT_PROMESSA
        FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentlinelocationextractpvo
        GROUP BY PoHeaderId, PoLineId
    ) LLOC ON PDL.PoHeaderId = LLOC.PoHeaderId AND PDL.PoLineId = LLOC.PoLineId
    LEFT JOIN (SELECT INVENTORY_ITEM_ID, MAX(ITEM_NUMBER) AS ITEM_NUMBER, MAX(DESCRIPTION) AS DESCRIPTION, MAX(ITEM_TYPE) AS ITEM_TYPE, MAX(TRIM(ITEM_CLASS_CODE)) AS ITEM_CLASS_CODE FROM cat_ocloud_r5_dv.rg5glofsn_cz.egp_system_items_vl WHERE ITEM_NUMBER IS NOT NULL GROUP BY INVENTORY_ITEM_ID) ITM ON CAST(PDL.ItemId AS DECIMAL(38,0)) = ITM.INVENTORY_ITEM_ID
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_egp_categories_vl CAT ON PDL.CategoryId = CAT.CATEGORY_ID
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_gl_codecombinationextractpvo GCC ON PDA.CodeCombinationId = GCC.CodeCombinationCodeCombinationId
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_fnd_flex_values_vl FV_AREA ON GCC.CodeCombinationSegment3 = FV_AREA.value AND FV_AREA.valuesetid = 55003 AND FV_AREA.language = 'PTB'
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_fnd_flex_values_vl FV_CAT ON GCC.CodeCombinationSegment4 = FV_CAT.value AND FV_CAT.valuesetid = 55001 AND FV_CAT.language = 'PTB'
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_fnd_flex_values_vl FV_UNI ON GCC.CodeCombinationSegment2 = FV_UNI.value AND FV_UNI.valuesetid = 55002 AND FV_UNI.language = 'PTB'
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prcpoz_supplierpvo SUP ON PHA.VENDOR_ID = SUP.VendorId
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prcpoz_suppliersitepvo SUPS ON PHA.VENDOR_ID = SUPS.SupplierVendorId AND PHA.VENDOR_SITE_ID = SUPS.VendorSiteId
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_paymenttermlineextractpvo TER ON PHA.TERMS_ID = TER.ApTermsLinesTermId
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_paymenttermlineextractpvo TER2 ON SUPS.SupplierSiteTermsId = TER2.ApTermsLinesTermId
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo user1 ON user1.Username = PHA.CREATED_BY
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_draftpurchasingdocumentheaderdffextractpvo dff_po ON CAST(PHA.PO_HEADER_ID AS BIGINT) = CAST(dff_po.s_k_5000 AS BIGINT)
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all BPA ON BPA.PO_HEADER_ID = PDL.FromHeaderId
    LEFT JOIN (SELECT PaymentTermHeaderTranslationTermId, MAX(PaymentTermHeaderTranslationName) AS PaymentTermName FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_paymenttermheadertranslationextractpvo GROUP BY PaymentTermHeaderTranslationTermId) TER_BPA ON BPA.TERMS_ID = TER_BPA.PaymentTermHeaderTranslationTermId
    -- Requisição
    LEFT JOIN (
        SELECT 
            a.PoHeaderId, a.PoLineId, 
            COALESCE(a.RequesterId, b.PreparerId) AS RequesterPersonId,
            user1.PersonNamePEOFullName AS SOLICITANTE_REQUISICAO, 
            user1.EmailAddress AS EMAIL_REQUISITANTE, 
            b.RequisitionNumber AS REQUISICAO, 
            b.EmergencyReqFlag 
        FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_por_requisitionlineextractpvo a 
        LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_por_requisitionheaderextractpvo b ON a.RequisitionHeaderId = b.RequisitionHeaderId 
        LEFT JOIN users_dedup user1 ON COALESCE(a.RequesterId, b.PreparerId) = user1.PersonId
    ) req ON req.PoLineId = PDL.PoLineId AND req.PoHeaderId = PDL.PoHeaderId
    LEFT JOIN asg_dept dept_req ON req.RequesterPersonId = dept_req.person_id
    -- Fallback Solicitante via DeliverToPersonId (para OCs sem requisição vinculada)
    LEFT JOIN users_dedup user_dist ON CAST(PDA.DeliverToPersonId AS BIGINT) = user_dist.PersonId
    LEFT JOIN asg_dept dept_dist ON CAST(PDA.DeliverToPersonId AS BIGINT) = dept_dist.person_id
    -- Comprador via AGENT_ID
    LEFT JOIN users_dedup buyer ON CAST(PHA.AGENT_ID AS BIGINT) = buyer.PersonId
    LEFT JOIN asg_dept dept_buyer ON CAST(PHA.AGENT_ID AS BIGINT) = dept_buyer.person_id
    LEFT JOIN (SELECT b.ApInvoiceLinesAllPoHeaderId, b.ApInvoiceLinesAllPoLineId, MIN(DATE_FORMAT(a.ApInvoicesInvoiceDate, 'yyyy-MM-dd')) AS DT_NOTA FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoiceheaderextractpvo a LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoicelineextractpvo b ON b.ApInvoiceLinesAllInvoiceId = a.ApInvoicesInvoiceId GROUP BY b.ApInvoiceLinesAllPoHeaderId, b.ApInvoiceLinesAllPoLineId) c ON PDL.PoHeaderId = c.ApInvoiceLinesAllPoHeaderId AND PDL.PoLineId = c.ApInvoiceLinesAllPoLineId
    LEFT JOIN (SELECT DISTINCT MAX(k.seg) AS ACORDO_COMPRA, (CASE WHEN PDA.PoHeaderId IS NULL THEN k.ID ELSE PDA.PoHeaderId END) AS num_header FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentheaderextractpvo PHA LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentdistributionextractpvo PDA ON PHA.PoHeaderId = PDA.PoHeaderId LEFT JOIN (SELECT MAX(PHA.TypeLookupCode) AS TIPO_OC, MAX(PHA.AmountReleased) AS VL_ACORDO_COMPRA, MAX(PHA.Comments) AS DESCRICAO_ACORDO_COMPRA, MAX(PHA.insertion_date) AS insertion_date, PHA.PoHeaderId AS ID, PHA.VendorId, PHA.VendorSiteId, PHA.TermsId, PHA.Segment1 AS seg, PHA.InventoryOrganizationId, PHA.BillToLocationId, MAX(PHA.FobLookupCode) AS FobLookupCode, MAX(PHA.FreightTermsLookupCode) AS FreightTermsLookupCode FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentheaderextractpvo PHA INNER JOIN (SELECT MAX(insertion_date) AS insertion_date, VendorId, VendorSiteId, TermsId, InventoryOrganizationId, MAX(FobLookupCode) AS FobLookupCode, MAX(FreightTermsLookupCode) AS FreightTermsLookupCode FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentheaderextractpvo WHERE BudgetControlEnabledFlag = 'N' AND TypeLookupCode = 'BLANKET' AND LastReleaseDate IS NOT NULL GROUP BY VendorId, VendorSiteId, TermsId, InventoryOrganizationId, PoHeaderId) l ON l.insertion_date = PHA.insertion_date AND l.VendorId = PHA.VendorId AND l.VendorSiteId = PHA.VendorSiteId AND l.TermsId = PHA.TermsId AND l.InventoryOrganizationId = PHA.InventoryOrganizationId AND PHA.FreightTermsLookupCode = l.FreightTermsLookupCode AND PHA.FobLookupCode = l.FobLookupCode GROUP BY PHA.VendorId, PHA.VendorSiteId, PHA.TermsId, PHA.Segment1, PHA.InventoryOrganizationId, PHA.PoHeaderId, PHA.BillToLocationId) k ON k.VendorId = PHA.VendorId AND k.VendorSiteId = PHA.VendorSiteId AND k.TermsId = PHA.TermsId AND k.InventoryOrganizationId = PHA.InventoryOrganizationId AND PHA.FreightTermsLookupCode = k.FreightTermsLookupCode AND PHA.FobLookupCode = k.FobLookupCode GROUP BY CASE WHEN PDA.PoHeaderId IS NULL THEN k.ID ELSE PDA.PoHeaderId END) i ON i.num_header = PDL.PoHeaderId
    LEFT JOIN (SELECT A.* FROM (SELECT PurchasingDocumentHeaderSegment1, DisplayName AS APROVADOR, SequenceNum, ROW_NUMBER() OVER (PARTITION BY PurchasingDocumentHeaderSegment1 ORDER BY SequenceNum DESC) AS RowNum FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prcpo_purchaseorderhistorypvo WHERE DisplayName IS NOT NULL) A WHERE RowNum = 1) apr ON PHA.SEGMENT1 = apr.PurchasingDocumentHeaderSegment1
    LEFT JOIN cat_dnabb_dv.grobbcompr_cz.fornecedores_especiais fe ON SUPS.SupplierSegment1 = fe.COD_FORNECEDOR_ORACLE
    LEFT JOIN cat_dnabb_dv.grobbcompr_cz.fornecedores_nao_negociaveis fn ON SUPS.SupplierSegment1 = fn.COD_FORNECEDOR_ORACLE
    LEFT JOIN cat_dnabb_dv.grobbcompr_cz.compradores_funcionais cf ON PHA.CREATED_BY = cf.USUARIO_ORACLE
    WHERE PHA.TYPE_LOOKUP_CODE <> 'CONTRACT'
)
SELECT
    MAX(OC_POS_FATURA) AS OC_POS_FATURA, MAX(ACORDO_COMPRA) AS ACORDO_COMPRA, MAX(NUMERO_ACORDO) AS NUMERO_ACORDO,
    MAX(DT_NOTA) AS DT_NOTA, MAX(DT_FECHAMENTO) AS DT_FECHAMENTO, MAX(NOME_USUARIO) AS NOME_USUARIO,
    MAX(NUMERO_FORNECEDOR) AS NUMERO_FORNECEDOR, MAX(FORNECEDOR) AS FORNECEDOR, MAX(PO_DIAS_PGTO) AS PO_DIAS_PGTO,
    MAX(TIPO_FORNECEDOR) AS TIPO_FORNECEDOR, MAX(TIPO_VENDOR) AS TIPO_VENDOR, MAX(DT_RELEASE) AS DT_RELEASE, MAX(DESCRICAO) AS DESCRICAO,
    SUM(VALOR_ORIGINAL) AS VALOR_ORIGINAL, SUM(VALOR_UTILIZADO) AS VALOR_UTILIZADO, SUM(QTD_FATURADA) AS QTD_FATURADA,
    MAX(TAXA_CAMBIO) AS TAXA_CAMBIO, MAX(DT_TAXA_CAMBIO) AS DT_TAXA_CAMBIO, MAX(CODIGO_MOEDA) AS CODIGO_MOEDA,
    MAX(CREATED_BY) AS USUARIO, MAX(STATUS_APROVACAO) AS STATUS_APROVACAO, MAX(ANO_MES) AS ANO_MES,
    CASE WHEN SUM(CASE WHEN UPPER(TRIM(URGENTE)) = 'SIM' THEN 1 ELSE 0 END) > 0 THEN 'SIM' ELSE 'NAO' END AS URGENTE,
    MAX(ID_CNPJ) AS CNPJ, MAX(STATUS_FECHAMENTO) AS STATUS_FECHAMENTO,
    MAX(DT_APROVACAO) AS DT_APROVACAO, MAX(DT_NECESSIDADE) AS DT_NECESSIDADE, MAX(DT_PROMESSA) AS DT_PROMESSA, MAX(DT_ATUALIZACAO) AS DT_ATUALIZACAO,
    MAX(CONTA_DEBITO) AS CONTA_DEBITO, MAX(CENTRALIZADO) AS CENTRALIZADO, MAX(UNIDADE) AS UNIDADE, MAX(DATA_OC) AS DATA_OC,
    NUMERO_OC, LINHA_OC, MAX(CHAVE_OC_LINHA) AS CHAVE_OC_LINHA,
    MAX(DT_NOTA) AS DT_PRIMEIRA_NF, MAX(APROVADOR) AS APROVADOR, MAX(TIPO) AS TIPO, MAX(org_desc) AS org_desc,
    MAX(ITEM_AQUISICAO) AS ITEM_AQUISICAO, MAX(DESCRICAO_ITEM) AS DESCRICAO_ITEM, MAX(CATEGORIA_ITEM) AS CATEGORIA_ITEM, MAX(CATEGORIA_CODIGO) AS CATEGORIA_CODIGO, MAX(ITEM_TYPE) AS ITEM_TYPE, MAX(ITEM_CLASS_CODE) AS ITEM_CLASS_CODE, MAX(GRUPO_COMPRAS_OC) AS GRUPO_COMPRAS_OC,
    MAX(AREA) AS AREA, MAX(CATEGORIA_OC) AS CATEGORIA_OC,
    MAX(SOLICITANTE_REQUISICAO) AS NOME_REQUISITANTE, MAX(DEPARTAMENTO_REQUISITANTE) AS DEPARTAMENTO_REQUISITANTE, MAX(REQUISICAO) AS REQUISICAO, MAX(EMAIL_USUARIO) AS EMAIL_USUARIO,
    MAX(EMAIL_REQUISITANTE) AS EMAIL_REQUISITANTE, MAX(TIPO_COMPRA) AS TIPO_COMPRA,
    MAX(COMPRADOR) AS COMPRADOR, MAX(DEPARTAMENTO_COMPRADOR) AS DEPARTAMENTO_COMPRADOR, MAX(USUARIO_COMPRADOR) AS USUARIO_COMPRADOR, MAX(EMAIL_COMPRADOR) AS EMAIL_COMPRADOR,
    MAX(OC_SEM_USO) AS OC_SEM_USO,
    MAX(FORNECEDOR_ESPECIAL) AS FORNECEDOR_ESPECIAL,
    MAX(FORNECEDOR_NAO_NEGOCIAVEL) AS FORNECEDOR_NAO_NEGOCIAVEL,
    'OCLOUD' AS FONTE,
    -- ═══════════════════════════════════════════════════════════════
    -- DIAS_ABERTO: dias desde aprovação até hoje (apenas OCs ABERTAS)
    -- Equivale ao DAX: DATEDIFF(DT_APROVACAO, TODAY(), DAY)
    -- ═══════════════════════════════════════════════════════════════
    CASE WHEN MAX(STATUS_FECHAMENTO) = 'ABERTA' 
         THEN DATEDIFF(CURRENT_DATE(), MAX(DT_APROVACAO))
         ELSE NULL 
    END AS DIAS_ABERTO,
    CASE WHEN MAX(STATUS_FECHAMENTO) = 'ABERTA'
              AND MAX(DT_NECESSIDADE) IS NOT NULL
              AND CURRENT_DATE() > MAX(DT_NECESSIDADE)
         THEN 'SIM'
         ELSE 'NÃO'
    END AS OC_ATRASADA,
    CASE WHEN MAX(STATUS_FECHAMENTO) = 'ABERTA'
              AND MAX(DT_NECESSIDADE) IS NOT NULL
              AND CURRENT_DATE() > MAX(DT_NECESSIDADE)
         THEN DATEDIFF(CURRENT_DATE(), MAX(DT_NECESSIDADE))
         ELSE NULL
    END AS DIAS_ATRASO_OC,
    CASE WHEN MAX(DT_NOTA) IS NOT NULL
              AND MAX(DT_NECESSIDADE) IS NOT NULL
         THEN DATEDIFF(TO_DATE(MAX(DT_NOTA)), MAX(DT_NECESSIDADE))
         ELSE NULL
    END AS ATRASO_REAL_NF,
    MAX(ACORDO_STATUS) AS ACORDO_STATUS,
    MAX(ACORDO_DT_CRIACAO) AS ACORDO_DT_CRIACAO,
    MAX(ACORDO_DATA_INICIAL) AS ACORDO_DATA_INICIAL,
    MAX(ACORDO_DATA_FINAL) AS ACORDO_DATA_FINAL,
    MAX(ACORDO_VALOR_TOTAL) AS ACORDO_VALOR_TOTAL,
    MAX(ACORDO_VALOR_MIN_LIBERACAO) AS ACORDO_VALOR_MIN_LIBERACAO,
    MAX(ACORDO_VALOR_LIBERADO) AS ACORDO_VALOR_LIBERADO,
    MAX(ACORDO_DESCRICAO) AS ACORDO_DESCRICAO,
    MAX(ACORDO_FOB) AS ACORDO_FOB,
    MAX(ACORDO_CONDICAO_FRETE) AS ACORDO_CONDICAO_FRETE,
    MAX(ACORDO_CONDICAO_PGTO) AS ACORDO_CONDICAO_PGTO
FROM oc_detalhe
GROUP BY NUMERO_OC, LINHA_OC
-- ═══════════════════════════════════════════════════════════════════════
-- FILTRO DE STATUS: excluir OCs com status não relevante para análise
-- Editar a lista abaixo conforme necessidade
-- ═══════════════════════════════════════════════════════════════════════
HAVING MAX(STATUS_FECHAMENTO) NOT IN (
    'RETIRADA',
    'SEM STATUS',
    'REJEITADA',
    'INCOMPLETA'
)
AND (
    MAX(STATUS_FECHAMENTO) <> 'CANCELADA'
    OR (
        MAX(DT_NOTA) IS NOT NULL 
        OR COALESCE(SUM(QTD_FATURADA), 0) > 0 
        OR COALESCE(SUM(VALOR_UTILIZADO), 0) > 0
    )
)