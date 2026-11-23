WITH users_dedup AS (
    SELECT * FROM (
        SELECT 
            PersonId,
            Username,
            EmailAddress,
            PersonNamePEOFullName,
            ROW_NUMBER() OVER (
                PARTITION BY PersonId 
                ORDER BY LastUpdateDate DESC
            ) AS rn
        FROM cat_ocloud_r5_dv.rg5glofsn_cz.crm_crm_userpvo
        WHERE PersonId IS NOT NULL
    ) WHERE rn = 1
),
asg_dept AS (
    SELECT * FROM (
        SELECT 
            a.person_id,
            org.NAME AS DEPARTAMENTO,
            ROW_NUMBER() OVER (
                PARTITION BY a.person_id 
                ORDER BY a.effective_end_date DESC, a.effective_start_date DESC
            ) AS rn
        FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_per_all_assignments_f a
        LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.hr_organization_units org 
            ON a.organization_id = org.ORGANIZATION_ID
        WHERE a.person_id IS NOT NULL
    ) WHERE rn = 1
)
SELECT 
    bpa.SEGMENT1 AS numero_acordo,
    bpa.DOCUMENT_STATUS AS status,
    DATE_FORMAT(bpa.CREATION_DATE, 'yyyy-MM-dd') AS dt_criacao,
    DATE_FORMAT(bpa.START_DATE, 'yyyy-MM-dd') AS dt_inicio,
    DATE_FORMAT(bpa.END_DATE, 'yyyy-MM-dd') AS dt_fim,
    CAST(bpa.BLANKET_TOTAL_AMOUNT AS DOUBLE) AS valor_total,
    CAST(COALESCE(bpa.AMOUNT_RELEASED, 0) AS DOUBLE) AS valor_liberado,
    bpa.COMMENTS AS descricao,
    sups.SuppPartyPartyName AS fornecedor,
    sups.SupplierSegment1 AS numero_fornecedor,
    buyer.PersonNamePEOFullName AS comprador,
    buyer.Username AS usuario_comprador,
    dept.DEPARTAMENTO AS departamento_comprador,
    CASE 
        WHEN bu.BU_NAME LIKE '%BQ%' OR bu.BU_NAME LIKE '%PULLMAN%' THEN 'BQ'
        ELSE 'BB'
    END AS empresa,
    DATEDIFF(CURRENT_DATE(), CAST(bpa.CREATION_DATE AS DATE)) AS dias_aberto
FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all bpa
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fscm_prcpoz_suppliersitepvo sups 
       ON bpa.VENDOR_ID = sups.SupplierVendorId AND bpa.VENDOR_SITE_ID = sups.VendorSiteId
LEFT JOIN users_dedup buyer 
       ON CAST(bpa.AGENT_ID AS BIGINT) = buyer.PersonId
LEFT JOIN asg_dept dept 
       ON CAST(bpa.AGENT_ID AS BIGINT) = dept.person_id
LEFT JOIN cat_ocloud_r5_dv.rg5glofsn_cz.fun_all_business_units_v bu 
       ON bpa.PRC_BU_ID = bu.BU_ID
WHERE bpa.TYPE_LOOKUP_CODE = 'BLANKET'
