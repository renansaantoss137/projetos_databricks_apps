WITH req_base AS (
            SELECT DISTINCT 
                req.requisicao, 
                NULLIF(TRIM(req.numero_oc), '') AS numero_oc,
                NULLIF(TRIM(COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), ''))), '')::date AS req_dt
            FROM requisicoes req
            WHERE NULLIF(TRIM(COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), ''))), '') IS NOT NULL AND req.empresa IN ('BB','BQ') AND SUBSTRING(COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), '')), 1, 4) IN ('2026') AND (LENGTH(TRIM(COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), '')))) >= 7 AND CAST(SUBSTRING(TRIM(COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), ''))), 6, 2) AS INT) IN (10))
        ),
        req_items AS (
            SELECT 
                requisicao, 
                req_dt,
                TRIM(oc_num) AS po_num
            FROM req_base,
                 UNNEST(string_to_array(numero_oc, ',')) AS oc_num
            WHERE numero_oc IS NOT NULL 
              AND numero_oc != 'Requisicao sem OC'
              AND TRIM(oc_num) != '' 
              AND TRIM(oc_num) != 'Requisicao sem OC'
        ),
        req_nums AS (
            SELECT DISTINCT requisicao 
            FROM req_base 
            WHERE requisicao IS NOT NULL AND requisicao != ''
        ),
        req_ocs AS (
            SELECT DISTINCT po_num AS numero_oc 
            FROM req_items
        ),
        req_metrics AS (
            SELECT 
                COUNT(DISTINCT req.requisicao)::int AS qty_req,
                COALESCE(SUM(CASE WHEN req.valor_requisicao < 1000000000 THEN req.valor_requisicao ELSE 0 END), 0)::float AS spend_req
            FROM requisicoes req
            WHERE NULLIF(TRIM(COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), ''))), '') IS NOT NULL AND req.empresa IN ('BB','BQ') AND SUBSTRING(COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), '')), 1, 4) IN ('2026') AND (LENGTH(TRIM(COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), '')))) >= 7 AND CAST(SUBSTRING(TRIM(COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), ''))), 6, 2) AS INT) IN (10))
        ),
        oc_cohort AS (
            SELECT 
                oc.numero_oc,
                oc.chave_oc_linha,
                oc.valor_original_brl,
                NULLIF(TRIM(oc.data_oc), '')::date AS d_oc,
                NULLIF(TRIM(oc.dt_aprovacao), '')::date AS d_aprov,
                oc.status_aprovacao,
                oc.status_fechamento,
                oc.requisicao
            FROM ordens_compra oc
            WHERE oc.ORG_DESC IN ('BB','BQ') AND oc.IS_FORNECEDOR_NAO_NEGOCIAVEL IN ('NEGOCIAVEL') AND UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'INDIRETOS'
              AND (
                  (oc.requisicao IS NOT NULL AND oc.requisicao != '' AND oc.requisicao IN (SELECT requisicao FROM req_nums))
                  OR oc.numero_oc IN (SELECT numero_oc FROM req_ocs)
              )
              AND UPPER(TRIM(COALESCE(oc.status_fechamento, ''))) NOT IN ('CANCELADA', 'CANCELADO', 'INCOMPLETA', 'RETIRADA', 'REJEITADA')
        ),
        oc_aprov AS (
            SELECT * FROM oc_cohort 
            WHERE UPPER(TRIM(COALESCE(status_aprovacao, ''))) IN ('APPROVED', 'APROVADO')
               OR (dt_aprovacao IS NOT NULL AND UPPER(TRIM(COALESCE(status_fechamento, ''))) NOT IN ('PENDENTE APROVACAO', 'PENDING APPROVAL'))
        ),
        nf_agg AS (
            SELECT 
                nf.chave_oc_linha,
                SUM(nf.valor_liquido_brl) AS nf_line_spend,
                COUNT(DISTINCT nf.nota_fiscal) AS nf_line_count,
                MIN(NULLIF(TRIM(nf.data_lancamento), '')::date) AS min_nf_dt,
                MAX(NULLIF(TRIM(nf.data_lancamento), '')::date) AS max_nf_dt
            FROM oc_aprov a
            JOIN notas_ri nf ON nf.chave_oc_linha = a.chave_oc_linha
            WHERE NULLIF(TRIM(nf.data_lancamento), '') IS NOT NULL
            GROUP BY nf.chave_oc_linha
        ),
        oc_summary AS (
            SELECT 
                a.numero_oc,
                MIN(a.d_aprov) AS d_aprov,
                SUM(a.valor_original_brl) AS total_oc_vl,
                SUM(COALESCE(n.nf_line_spend, 0)) AS total_nf_vl,
                SUM(COALESCE(n.nf_line_count, 0)) AS total_nfs,
                MIN(n.min_nf_dt) AS first_nf_date,
                MAX(n.max_nf_dt) AS last_nf_date,
                BOOL_OR(UPPER(TRIM(COALESCE(a.status_fechamento, ''))) IN ('FECHADO', 'FECHADO P/ FATURAMENTO', 'FINALMENTE FECHADO')) AS is_closed
            FROM oc_aprov a
            LEFT JOIN nf_agg n ON n.chave_oc_linha = a.chave_oc_linha
            GROUP BY a.numero_oc
        ),
        oc_fat_metrics AS (
            SELECT 
                COUNT(CASE WHEN total_nf_vl > 0 OR total_nfs > 0 THEN 1 END)::int AS qty_fat_ini,
                COALESCE(SUM(CASE WHEN total_nf_vl > 0 OR total_nfs > 0 THEN total_nf_vl ELSE 0 END), 0)::float AS spend_fat_ini,
                COUNT(CASE WHEN (total_nf_vl > 0 OR total_nfs > 0) AND (is_closed = TRUE OR (total_oc_vl > 0 AND total_nf_vl >= total_oc_vl * 0.98) OR (total_oc_vl = 0 AND total_nf_vl > 0)) THEN 1 END)::int AS qty_fat_tot,
                COALESCE(SUM(CASE WHEN (total_nf_vl > 0 OR total_nfs > 0) AND (is_closed = TRUE OR (total_oc_vl > 0 AND total_nf_vl >= total_oc_vl * 0.98) OR (total_oc_vl = 0 AND total_nf_vl > 0)) THEN total_nf_vl ELSE 0 END), 0)::float AS spend_fat_tot,
                AVG(CASE WHEN first_nf_date IS NOT NULL AND d_aprov IS NOT NULL AND (first_nf_date - d_aprov) >= 0 THEN (first_nf_date - d_aprov) END)::float AS avg_days_aprov_to_first_nf,
                AVG(CASE WHEN last_nf_date IS NOT NULL AND first_nf_date IS NOT NULL AND (last_nf_date - first_nf_date) >= 0 THEN (last_nf_date - first_nf_date) END)::float AS avg_days_first_to_last_nf
            FROM oc_summary
        ),
        req_pairs AS (
            SELECT r.requisicao, r.req_dt, c.numero_oc, c.d_oc
            FROM req_base r
            JOIN (SELECT DISTINCT numero_oc, requisicao, d_oc FROM oc_cohort WHERE d_oc IS NOT NULL) c
              ON c.requisicao = r.requisicao AND c.requisicao IS NOT NULL AND c.requisicao != ''
            UNION
            SELECT ri.requisicao, ri.req_dt, c.numero_oc, c.d_oc
            FROM req_items ri
            JOIN (SELECT DISTINCT numero_oc, d_oc FROM oc_cohort WHERE d_oc IS NOT NULL) c
              ON c.numero_oc = ri.po_num
        ),
        req_to_oc_lead AS (
            SELECT AVG(d_oc - req_dt)::float AS avg_days_req_to_emit
            FROM req_pairs
            WHERE d_oc >= req_dt
        )
        SELECT 
            (SELECT spend_req FROM req_metrics) AS spend_req,
            (SELECT qty_req FROM req_metrics) AS qty_req,
            (SELECT COALESCE(SUM(valor_original_brl), 0)::float FROM oc_cohort) AS spend_emit,
            (SELECT COUNT(DISTINCT numero_oc)::int FROM oc_cohort) AS qty_emit,
            (SELECT avg_days_req_to_emit FROM req_to_oc_lead) AS avg_days_req_to_emit,
            (SELECT COALESCE(SUM(valor_original_brl), 0)::float FROM oc_aprov) AS spend_aprov,
            (SELECT COUNT(DISTINCT numero_oc)::int FROM oc_aprov) AS qty_aprov,
            (SELECT AVG(d_aprov - d_oc)::float FROM oc_aprov WHERE d_aprov IS NOT NULL AND d_oc IS NOT NULL AND (d_aprov - d_oc) >= 0) AS avg_days_emit_to_aprov,
            (SELECT qty_fat_ini FROM oc_fat_metrics) AS qty_fat_ini,
            (SELECT spend_fat_ini FROM oc_fat_metrics) AS spend_fat_ini,
            (SELECT qty_fat_tot FROM oc_fat_metrics) AS qty_fat_tot,
            (SELECT spend_fat_tot FROM oc_fat_metrics) AS spend_fat_tot,
            (SELECT avg_days_aprov_to_first_nf FROM oc_fat_metrics) AS avg_days_aprov_to_first_nf,
            (SELECT avg_days_first_to_last_nf FROM oc_fat_metrics) AS avg_days_first_to_last_nf