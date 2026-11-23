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
)
SELECT DISTINCT

    -- BLOCO 1: IDENTIFICAÇÃO DA NOTA
    c.INVOICE_ID,
    c.INVOICE_LINE_ID,
    a.ApInvoicesInvoiceId AS NUMERO_RI,
    a.ApInvoicesInvoiceNum AS NOTA_FISCAL,
    SUBSTRING_INDEX(SUBSTRING_INDEX(a.ApInvoicesInvoiceNum, '-', 2), '-', -1) AS SERIE,
    COALESCE(h.SEGMENT1, 'Nota sem OC') AS NUMERO_OC,
    CASE WHEN COALESCE(h.REQ_BU_ID, a.ApInvoicesOrgId) = 300000002033035 THEN 'BB'
         WHEN COALESCE(h.REQ_BU_ID, a.ApInvoicesOrgId) = 300000002033048 THEN 'BQ'
         ELSE '' END AS EMPRESA,
    b.ApInvoiceLinesAllDescription AS DS_ITEM,
    ITM_NF.ITEM_NUMBER AS CODIGO_ITEM,
    ITM_NF.DESCRIPTION AS DESCRICAO_ITEM,
    ITM_NF.ITEM_TYPE,
    ITM_NF.ITEM_CLASS_CODE,
    CAT_NF.CATEGORY_NAME AS CATEGORIA_ITEM,
    CAT_NF.CATEGORY_CODE AS CATEGORIA_CODIGO,
    SUP_NF.SupplierVendorTypeLookupCode AS TIPO_VENDOR,
    CASE
        WHEN TRIM(COALESCE(ITM_NF.ITEM_NUMBER, '')) = '' AND h.CREATED_BY = 'BBAPPA0001' THEN 'COMERCIAL'
        WHEN TRIM(COALESCE(ITM_NF.ITEM_NUMBER, '')) = '' THEN 'INDIRETOS'
        WHEN UPPER(SUBSTR(TRIM(ITM_NF.ITEM_NUMBER), 1, 1)) IN ('A', 'B') THEN 'DIRETOS'
        ELSE 'INDIRETOS'
    END AS GRUPO_COMPRAS,
    CASE
        WHEN UPPER(COALESCE(NULLIF(buyer.PersonFirstLastName, ''), buyer.PersonNamePEOFullName, '')) LIKE '%ABEL MOREIRA MARTINS FILHO%' THEN 'DESCENTRALIZADO'
        WHEN h.TYPE_LOOKUP_CODE = 'BLANKET' THEN 'CENTRALIZADO'
        WHEN BPA_NR.SEGMENT1 IS NOT NULL AND TRIM(BPA_NR.SEGMENT1) <> '' THEN 'CENTRALIZADO'
        WHEN UPPER(COALESCE(dept_buyer.DEPARTAMENTO, '')) LIKE '%COMPRAS%' THEN 'CENTRALIZADO'
        ELSE 'DESCENTRALIZADO'
    END AS CENTRALIZADO,
    COALESCE(NULLIF(buyer.PersonFirstLastName, ''), buyer.PersonNamePEOFullName) AS COMPRADOR,
    dept_buyer.DEPARTAMENTO AS DEPARTAMENTO_COMPRADOR,
    b.ApInvoiceLinesAllPoHeaderId,
    CAST(PDL_KEY.LineNum AS INT) AS LINHA_OC,
    COALESCE(h.SEGMENT1, 'Nota sem OC') || '_' || CAST(COALESCE(PDL_KEY.LineNum, 0) AS INT) AS CHAVE_OC_LINHA,

    -- BLOCO 2: DATAS
    c.DATA_NOTA,
    DATE_FORMAT(a.ApInvoicesInvoiceDate, 'yyyy-MM-dd') AS DT_NOTA,
    DATE_FORMAT(a.ApInvoicesCreationDate, 'yyyy-MM-dd') AS DATA_LANCAMENTO,
    DATE_FORMAT(a.ApInvoicesCreationDate, 'yyyy-MM-dd') AS DT_REGISTRO,
    SCHED.DATA_VENCIMENTO,
    PMT.DATA_PAGAMENTO,
    DATE_FORMAT(a.ApInvoicesInvoiceDate, 'yyyy-MM') AS ANO_MES,
    ROUND(EXTRACT(DAY FROM (a.ApInvoicesInvoiceDate - a.ApInvoicesCreationDate))) AS DIAS_ATRASO,
    CASE WHEN h.APPROVED_DATE IS NOT NULL AND a.ApInvoicesInvoiceDate < h.APPROVED_DATE THEN 'SIM' ELSE 'NÃO' END AS OC_POS_FATURA,
    CASE WHEN UPPER(COALESCE(dff_po.TIPO_ORDEN_, '')) = 'URGENTE' THEN 'SIM' ELSE 'NAO' END AS URGENTE,

    -- BLOCO 3: VALORES FINANCEIROS
    b.ApInvoiceLinesAllAmount AS VALOR_NOTA,
    CASE WHEN a.ApInvoicesInvoiceCurrencyCode = 'BRL'
         THEN b.ApInvoiceLinesAllAmount
         ELSE b.ApInvoiceLinesAllAmount * COALESCE(a.ApInvoicesExchangeRate, 1)
    END AS VALOR_NOTA_BRL,
    b.ApInvoiceLinesAllQuantityInvoiced * COALESCE(c.SAFE_CONV_RATE, 1) AS QUANTIDADE,
    b.ApInvoiceLinesAllUnitPrice AS PRECO,
    CASE WHEN b.ApInvoiceLinesAllQuantityInvoiced != 0 AND b.ApInvoiceLinesAllQuantityInvoiced IS NOT NULL
         THEN (b.ApInvoiceLinesAllAmount - COALESCE(b.ApInvoiceLinesAllIncludedTaxAmount, 0)) 
              / (b.ApInvoiceLinesAllQuantityInvoiced * COALESCE(c.SAFE_CONV_RATE, 1))
         ELSE 0 END AS PRECO_LIQUIDO,
    (b.ApInvoiceLinesAllAmount - COALESCE(b.ApInvoiceLinesAllIncludedTaxAmount, 0)) AS VALOR_LIQUIDO,
    CASE WHEN a.ApInvoicesInvoiceCurrencyCode = 'BRL'
         THEN (b.ApInvoiceLinesAllAmount - COALESCE(b.ApInvoiceLinesAllIncludedTaxAmount, 0))
         ELSE (b.ApInvoiceLinesAllAmount - COALESCE(b.ApInvoiceLinesAllIncludedTaxAmount, 0)) * COALESCE(a.ApInvoicesExchangeRate, 1)
    END AS VALOR_LIQUIDO_BRL,

    -- BLOCO 4: IMPOSTOS
    CASE WHEN b.ApInvoiceLinesAllAmount != 0 THEN round(c.ICMS / b.ApInvoiceLinesAllAmount, 4) ELSE 0 END AS PERC_ICMS,
    nvl(c.ICMS, 0) AS ICMS,
    nvl(TAX.PIS_RATE, 0) / 100 AS PERC_PIS,
    nvl(TAX.PIS_AMT, 0) AS PIS,
    nvl(TAX.COFINS_RATE, 0) / 100 AS PERC_COFINS,
    nvl(TAX.COFINS_AMT, 0) AS COFINS,

    -- BLOCO 5: FORNECEDOR
    CLI.CNPJ AS CNPJ_FORNECEDOR,
    CLI.SuppPartyPartyName AS NOME_FORNECEDOR,
    CLI.PartyCity AS CIDADE,
    CLI.PartyState AS UF,

    -- BLOCO 6: LOCALIZAÇÃO / ORGANIZAÇÃO
    REPLACE(FV_UNIDADE.description, 'BBR_', '') AS UNIDADE,
    (CT.AN || '_' || ITEM.LocDetailsLocationName) AS LOCAL,
    ITEM.LocDetailsLocationName AS LOCAL_FORNECEDOR,
    a.ApInvoicesCustRegistrationNumber AS CNPJ_BIMBO,
    CHARINDEX('/', REVERSE(b.ApInvoiceLinesAllTrxBusinessCategory)) AS CFOP,

    -- BLOCO 7: CONDIÇÕES DE PAGAMENTO
    CASE WHEN TER2.ApTermsLinesDueDays RLIKE '[0-9]'
         THEN CAST(regexp_extract(TER2.ApTermsLinesDueDays, '([0-9]+)', 1) AS DECIMAL(18,2))
         ELSE 0 END AS COND_PGTO_CADASTRO,
    CASE WHEN TER.ApTermsLinesDueDays RLIKE '[0-9]'
         THEN CAST(regexp_extract(TER.ApTermsLinesDueDays, '([0-9]+)', 1) AS DECIMAL(18,2))
         ELSE 0 END AS COND_PGTO_AP,
    VALOR_LIQUIDO_BRL * COND_PGTO_AP AS PGTO_X_VALOR,
    CASE
        WHEN COND_PGTO_AP = 0 THEN '00. À vista'
        WHEN COND_PGTO_AP <= 15 THEN '01. Até 15 dias'
        WHEN COND_PGTO_AP <= 30 THEN '02. 16 a 30 dias'
        WHEN COND_PGTO_AP <= 45 THEN '03. 31 a 45 dias'
        WHEN COND_PGTO_AP < 60 THEN '04. 46 a 59 dias'
        WHEN COND_PGTO_AP = 60 THEN '05. Meta: 60 dias'
        WHEN COND_PGTO_AP > 60 THEN '06. Acima de 60 dias'
        ELSE 'Não identificado'
    END AS FAIXA_PRAZO_PAGAMENTO,
    CLI.BULastUpdateDate AS DT_ATUALIZACAO_CADASTRO,

    -- BLOCO 8: CONTABILIDADE
    CT.CONTA_CONTABIL,
    CT.CONTA,
    CT.CENTRO_CUSTO,

    -- BLOCO 9: STATUS
    CASE WHEN a.ApInvoicesApprovalStatus = 'CANCELLED' THEN 'Cancelada' ELSE 'Validada' END AS STATUS_VALIDACAO_FATURA,
    CASE WHEN a.ApInvoicesPaymentStatusFlag = 'Y' THEN 'Totalmente paga'
         WHEN a.ApInvoicesPaymentStatusFlag = 'P' THEN 'Parcialmente pago'
         ELSE 'Não paga' END AS STATUS_PAGAMENTO,

    -- BLOCO 10: SAVING HISTÓRICO
    SAV.PRECO_ANTERIOR,
    CASE WHEN SAV.PRECO_ANTERIOR IS NOT NULL AND SAV.PRECO_ANTERIOR > 0
         THEN SAV.PRECO_ANTERIOR - b.ApInvoiceLinesAllUnitPrice ELSE NULL END AS SAVING_UNITARIO,
    CASE WHEN SAV.PRECO_ANTERIOR IS NOT NULL AND SAV.PRECO_ANTERIOR > 0
         THEN ROUND((SAV.PRECO_ANTERIOR - b.ApInvoiceLinesAllUnitPrice) / SAV.PRECO_ANTERIOR * 100, 2) ELSE NULL END AS SAVING_PCT,
    CASE WHEN SAV.PRECO_ANTERIOR IS NOT NULL AND SAV.PRECO_ANTERIOR > 0
         THEN (SAV.PRECO_ANTERIOR - b.ApInvoiceLinesAllUnitPrice) * b.ApInvoiceLinesAllQuantityInvoiced ELSE NULL END AS SAVING_TOTAL,
    SAV.PRECO_BASE_ANO,
    CASE WHEN SAV.PRECO_BASE_ANO IS NOT NULL AND SAV.PRECO_BASE_ANO > 0
         THEN ROUND((SAV.PRECO_BASE_ANO - b.ApInvoiceLinesAllUnitPrice) / SAV.PRECO_BASE_ANO * 100, 2) ELSE NULL END AS SAVING_PCT_ANO,
    CASE WHEN SAV.PRECO_BASE_ANO IS NOT NULL AND SAV.PRECO_BASE_ANO > 0
         THEN (SAV.PRECO_BASE_ANO - b.ApInvoiceLinesAllUnitPrice) * b.ApInvoiceLinesAllQuantityInvoiced ELSE NULL END AS SAVING_TOTAL_ANO

-- JOINs
FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoiceheaderextractpvo a
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoicelineextractpvo b
    ON b.ApInvoiceLinesAllInvoiceId = a.ApInvoicesInvoiceId 
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all h
    ON b.ApInvoiceLinesAllPoHeaderId = h.PO_HEADER_ID
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_draftpurchasingdocumentheaderdffextractpvo dff_po
    ON CAST(h.PO_HEADER_ID AS BIGINT) = CAST(dff_po.s_k_5000 AS BIGINT)
LEFT JOIN users_dedup buyer ON CAST(h.AGENT_ID AS BIGINT) = buyer.PersonId
LEFT JOIN asg_dept dept_buyer ON CAST(h.AGENT_ID AS BIGINT) = dept_buyer.person_id
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentlineextractpvo PDL_KEY
    ON b.ApInvoiceLinesAllPoHeaderId = PDL_KEY.PoHeaderId AND b.ApInvoiceLinesAllPoLineId = PDL_KEY.PoLineId
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all BPA_NR ON BPA_NR.PO_HEADER_ID = PDL_KEY.FromHeaderId
LEFT JOIN (
    SELECT INVENTORY_ITEM_ID, MAX(ITEM_NUMBER) AS ITEM_NUMBER, MAX(DESCRIPTION) AS DESCRIPTION, MAX(ITEM_TYPE) AS ITEM_TYPE, MAX(TRIM(ITEM_CLASS_CODE)) AS ITEM_CLASS_CODE
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.egp_system_items_vl
    WHERE ITEM_NUMBER IS NOT NULL
    GROUP BY INVENTORY_ITEM_ID
) ITM_NF ON CAST(PDL_KEY.ItemId AS DECIMAL(38,0)) = ITM_NF.INVENTORY_ITEM_ID
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_egp_categories_vl CAT_NF ON PDL_KEY.CategoryId = CAT_NF.CATEGORY_ID
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prcpoz_supplierpvo SUP_NF ON a.ApInvoicesVendorId = SUP_NF.VendorId
LEFT JOIN (
    SELECT invoiceid, LineNumber, MAX(LocDetailsLocationName) AS LocDetailsLocationName
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fait_invoicelinepvo
    GROUP BY invoiceid, LineNumber
) ITEM ON a.ApInvoicesInvoiceId = ITEM.invoiceid AND b.ApInvoiceLinesAllLineNumber = ITEM.LineNumber
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_paymenttermlineextractpvo TER
    ON a.ApInvoicesTermsId = TER.ApTermsLinesTermId
LEFT JOIN (
    SELECT a2.ApInvoicesVendorId, a2.ApInvoicesInvoiceId, SUP.PartyCity, SUP.PartyState,
        SUPS.PartySitePartySiteName AS CNPJ, SUPS.SuppPartyPartyName, SUPS.SupplierSiteTermsId, SUPS.BULastUpdateDate
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoiceheaderextractpvo a2
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prcpoz_supplierpvo SUP ON a2.ApInvoicesVendorId = SUP.VendorId
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prcpoz_suppliersitepvo SUPS ON a2.ApInvoicesVendorId = SUPS.SupplierVendorId AND a2.ApInvoicesVendorSiteId = SUPS.VendorSiteId
) CLI ON a.ApInvoicesInvoiceId = CLI.ApInvoicesInvoiceId
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_paymenttermlineextractpvo TER2
    ON CLI.SupplierSiteTermsId = TER2.ApTermsLinesTermId
LEFT JOIN (
    SELECT a3.ApInvoicesInvoiceId, MAX(CodeCombinationSegment2) AS AN,
        MAX(d.CodeCombinationSegment1 || '-' || d.CodeCombinationSegment2 || '-' || d.CodeCombinationSegment3 || '-' || d.CodeCombinationSegment4 || '-' || d.CodeCombinationSegment5 || '-' || d.CodeCombinationSegment6 || '-' || d.CodeCombinationSegment7 || '-' || d.CodeCombinationSegment8) AS CONTA_CONTABIL,
        MAX(d.CodeCombinationSegment4) AS CONTA, MAX(d.CodeCombinationSegment3) AS CENTRO_CUSTO
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoiceheaderextractpvo a3
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoicedistributionextractpvo e ON a3.ApInvoicesInvoiceId = e.ApInvoiceDistributionsInvoiceId
    LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_gl_codecombinationextractpvo d ON d.CodeCombinationCodeCombinationId = e.ApInvoiceDistributionsDistCodeCombinationId
    GROUP BY a3.ApInvoicesInvoiceId
) CT ON CT.ApInvoicesInvoiceId = a.ApInvoicesInvoiceId
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_fnd_flex_values_vl FV_UNIDADE ON CT.AN = FV_UNIDADE.value AND FV_UNIDADE.valuesetid = 55002 AND FV_UNIDADE.language = 'PTB'
LEFT JOIN (
    SELECT e.ApInvoiceDistributionsInvoiceId AS INVOICE_ID, e.ApInvoiceDistributionsInvoiceLineNumber AS INVOICE_LINE_ID,
        MAX(e.ApInvoiceDistributionsAccountingDate) AS DATA_NOTA,
        MAX(CASE WHEN e.ApInvoiceDistributionsRecoveryRateName = 'BR DFLT STATE ICMS' THEN e.ApInvoiceDistributionsTotalDistAmount ELSE 0 END) AS ICMS,
        CASE WHEN MAX(uom.CONVERSION_RATE) > 50000 THEN 1 ELSE COALESCE(MAX(uom.CONVERSION_RATE), 1) END AS SAFE_CONV_RATE
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoicedistributionextractpvo e
    LEFT JOIN (SELECT UOM_CODE, MAX(CONVERSION_RATE) AS CONVERSION_RATE FROM cat_ocloud_r5_dv.rg5glofsn_cz.inv_uom_conversions GROUP BY UOM_CODE) uom
        ON e.ApInvoiceDistributionsMatchedUomLookupCode = uom.UOM_CODE
    GROUP BY e.ApInvoiceDistributionsInvoiceId, e.ApInvoiceDistributionsInvoiceLineNumber
) c ON c.INVOICE_ID = a.ApInvoicesInvoiceId AND c.INVOICE_LINE_ID = b.ApInvoiceLinesAllLineNumber
LEFT JOIN (
    SELECT PDL_S.PoHeaderId, PDL_S.PoLineId,
        LAG(PDL_S.UnitPrice) OVER (PARTITION BY PDL_S.ItemId, PH_S.VendorId ORDER BY PH_S.CreationDate, PDL_S.PoHeaderId) AS PRECO_ANTERIOR,
        FIRST_VALUE(PDL_S.UnitPrice) OVER (PARTITION BY PDL_S.ItemId, PH_S.VendorId, YEAR(PH_S.CreationDate) ORDER BY PH_S.CreationDate, PDL_S.PoHeaderId) AS PRECO_BASE_ANO
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentlineextractpvo PDL_S
    INNER JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prc_po_purchasingdocumentheaderextractpvo PH_S ON PDL_S.PoHeaderId = PH_S.PoHeaderId
    WHERE PDL_S.UnitPrice > 0 AND PDL_S.ItemId IS NOT NULL AND PH_S.VendorId IS NOT NULL
) SAV ON SAV.PoHeaderId = b.ApInvoiceLinesAllPoHeaderId AND SAV.PoLineId = b.ApInvoiceLinesAllPoLineId
LEFT JOIN (
    SELECT z.DetailTaxLineTrxId AS INVOICE_ID, z.DetailTaxLineTrxNumber AS INVOICE_NUM, z.DetailTaxLineTrxLineNumber AS LINE_NUMBER,
        SUM(CASE WHEN z.DetailTaxLineTax LIKE '%PIS%' AND z.DetailTaxLineTax NOT LIKE '%COST%' THEN z.DetailTaxLineTaxAmt ELSE 0 END) AS PIS_AMT,
        MAX(CASE WHEN z.DetailTaxLineTax LIKE '%PIS%' AND z.DetailTaxLineTax NOT LIKE '%COST%' AND z.DetailTaxLineTaxAmt > 0 THEN z.DetailTaxLineTaxRate END) AS PIS_RATE,
        SUM(CASE WHEN (z.DetailTaxLineTax LIKE '%COF%' OR z.DetailTaxLineTax LIKE '%COFINS%') AND z.DetailTaxLineTax NOT LIKE '%COST%' THEN z.DetailTaxLineTaxAmt ELSE 0 END) AS COFINS_AMT,
        MAX(CASE WHEN (z.DetailTaxLineTax LIKE '%COF%' OR z.DetailTaxLineTax LIKE '%COFINS%') AND z.DetailTaxLineTax NOT LIKE '%COST%' AND z.DetailTaxLineTaxAmt > 0 THEN z.DetailTaxLineTaxRate END) AS COFINS_RATE
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_zx_detailtaxlineextractpvo z
    WHERE z.DetailTaxLineTax LIKE '%PIS%' OR z.DetailTaxLineTax LIKE '%COF%'
    GROUP BY z.DetailTaxLineTrxId, z.DetailTaxLineTrxNumber, z.DetailTaxLineTrxLineNumber
) TAX ON TAX.INVOICE_ID = a.ApInvoicesInvoiceId AND TAX.INVOICE_NUM = a.ApInvoicesInvoiceNum AND TAX.LINE_NUMBER = b.ApInvoiceLinesAllLineNumber
LEFT JOIN (
    SELECT 
        p.INVOICE_ID,
        MAX(DATE_FORMAT(c.check_date, 'yyyy-MM-dd')) AS DATA_PAGAMENTO
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_ap_invoice_payments_all p
    JOIN cat_ocloud_r5_dv.rg5glofsn_cz.vw_ap_checks_all c 
        ON p.CHECK_ID = c.check_id
    GROUP BY p.INVOICE_ID
) PMT ON PMT.INVOICE_ID = a.ApInvoicesInvoiceId
LEFT JOIN (
    SELECT 
        ApPaymentSchedulesAllInvoiceId AS INVOICE_ID,
        MAX(DATE_FORMAT(ApPaymentSchedulesAllDueDate, 'yyyy-MM-dd')) AS DATA_VENCIMENTO
    FROM cat_ocloud_r5_dv.rg5glofsn_cz.fscm_fin_ap_invoicepaymentscheduleextractpvo
    GROUP BY ApPaymentSchedulesAllInvoiceId
) SCHED ON SCHED.INVOICE_ID = a.ApInvoicesInvoiceId
WHERE b.ApInvoiceLinesAllLineTypeLookupCode = 'ITEM'
  AND (a.ApInvoicesInvoiceNum IS NULL OR (
      UPPER(a.ApInvoicesInvoiceNum) NOT LIKE '%FOPAG%'
      AND UPPER(a.ApInvoicesInvoiceNum) NOT LIKE '%RGB%'
      AND UPPER(a.ApInvoicesInvoiceNum) NOT LIKE 'ADV%'
      AND UPPER(a.ApInvoicesInvoiceNum) NOT LIKE '%ARKER%'
      AND UPPER(a.ApInvoicesInvoiceNum) NOT LIKE '%FISCAL%'
  ))