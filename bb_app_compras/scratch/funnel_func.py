def performance_lead_time():
    """Process Funnel & Par-a-Par Lead Time:
    Scope: 'diretos' (default), 'indiretos', 'todos'
    Temporal Anchor:
      - Diretos / Todos: ordens_compra.DATA_OC (order emission cohort)
      - Indiretos: requisicoes.dt_aprovacao / dt_criacao (requisition cohort, linking downstream to OCs)
    Tracking: par-a-par cohort with First Delivery (MIN(data_lancamento)) for invoices.
    """
    scope = request.args.get('scope', 'diretos').strip().lower()
    if scope not in ('diretos', 'indiretos', 'todos'):
        scope = 'diretos'

    def _format_lead(val):
        """Convert avg_days to (value, unit). If 0 < val < 1, show hours."""
        if val is None:
            return None, 'dias'
        if val == 0:
            return 0, 'dias'
        if 0 < val < 1:
            h = round(val * 24, 1)
            return int(h) if h.is_integer() else h, 'horas'
        d = round(val, 1)
        return int(d) if d.is_integer() else d, 'dias'

    # Build clean args without 'grupo_compras' to avoid conflicting with the scope pills
    args_clean = request.args.copy()
    if 'grupo_compras' in args_clean:
        del args_clean['grupo_compras']

    oc_clauses, _ = _parse_filters(args_clean, date_col='DATA_OC', table_prefix='oc', empresa_col='ORG_DESC', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', fornecedor_col='nome_fornecedor')

    # Scope condition for ordens_compra
    if scope == 'diretos':
        oc_clauses.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'DIRETOS'")
    elif scope == 'indiretos':
        oc_clauses.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'INDIRETOS'")
    # scope == 'todos' does not filter by grupo_compras_oc

    oc_where = " AND ".join(oc_clauses) if oc_clauses else "1=1"

    if scope == 'indiretos':
        # Requisicoes filter conditions
        f_empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        f_ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
        f_mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
        f_dia = [d.strip() for d in request.args.getlist('dia') if d.strip()]
        f_dt_ini = request.args.get('dt_ini', '').strip()
        f_dt_fim = request.args.get('dt_fim', '').strip()

        req_date_expr = "COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), ''))"
        req_parts = [f"NULLIF(TRIM({req_date_expr}), '') IS NOT NULL"]
        if f_empresa:
            vals = ','.join([f"'{_esc(e)}'" for e in f_empresa])
            req_parts.append(f"req.empresa IN ({vals})")
        if f_ano:
            vals = ','.join([f"'{_esc(a)}'" for a in f_ano if a])
            if vals:
                req_parts.append(f"SUBSTRING({req_date_expr}, 1, 4) IN ({vals})")
        if f_mes:
            clean_months = [str(int(m)) for m in f_mes if m.isdigit()]
            if clean_months:
                vals = ','.join(clean_months)
                req_parts.append(f"(LENGTH(TRIM({req_date_expr})) >= 7 AND CAST(SUBSTRING(TRIM({req_date_expr}), 6, 2) AS INT) IN ({vals}))")
        if f_dia:
            clean_days = [str(int(d)) for d in f_dia if d.isdigit()]
            if clean_days:
                vals = ','.join(clean_days)
                req_parts.append(f"(LENGTH(TRIM({req_date_expr})) >= 10 AND CAST(SUBSTRING(TRIM({req_date_expr}), 9, 2) AS INT) IN ({vals}))")
        if f_dt_ini and not f_ano:
            req_parts.append(f"NULLIF(TRIM({req_date_expr}), '')::date >= '{_esc(f_dt_ini)}'::date")
        if f_dt_fim and not f_ano:
            req_parts.append(f"NULLIF(TRIM({req_date_expr}), '')::date <= '{_esc(f_dt_fim)}'::date")

        req_st = [v.strip() for v in request.args.getlist('req_status') if v.strip()]
        if req_st:
            vals = ','.join([f"'{_esc(v)}'" for v in req_st])
            req_parts.append(f"req.status IN ({vals})")

        req_where = " AND ".join(req_parts)

        # For the cohort of OCs generated from these requisitions:
        # Entity filters on OC (empresa, fornecedor, unidade, etc.) are kept, while the cohort timeline is anchored on the requisitions
        args_oc = args_clean.copy()
        for k in ('ano', 'mes', 'dia', 'dt_ini', 'dt_fim'):
            args_oc.pop(k, None)
        oc_clauses_cohort, _ = _parse_filters(args_oc, date_col='DATA_OC', table_prefix='oc', empresa_col='ORG_DESC', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', fornecedor_col='nome_fornecedor')
        oc_clauses_cohort.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'INDIRETOS'")
        oc_where_cohort = " AND ".join(oc_clauses_cohort) if oc_clauses_cohort else "1=1"

        sql = f"""
        WITH req_base AS (
            SELECT DISTINCT 
                req.requisicao, 
                NULLIF(TRIM(req.numero_oc), '') AS numero_oc,
                NULLIF(TRIM({req_date_expr}), '')::date AS req_dt
            FROM requisicoes req
            WHERE {req_where}
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
            WHERE {req_where}
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
            WHERE {oc_where_cohort}
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
        """
        rows = query(sql)
        row = rows[0] if rows else {}

        spend_req = float(row.get('spend_req') or 0)
        qty_req = int(row.get('qty_req') or 0)
        spend_emit = float(row.get('spend_emit') or 0)
        qty_emit = int(row.get('qty_emit') or 0)
        spend_aprov = float(row.get('spend_aprov') or 0)
        qty_aprov = int(row.get('qty_aprov') or 0)
        spend_fat_ini = float(row.get('spend_fat_ini') or 0)
        qty_fat_ini = int(row.get('qty_fat_ini') or 0)
        spend_fat_tot = float(row.get('spend_fat_tot') or 0)
        qty_fat_tot = int(row.get('qty_fat_tot') or 0)

        v_req_emit, u_req_emit = _format_lead(row.get('avg_days_req_to_emit'))
        v_emit_aprov, u_emit_aprov = _format_lead(row.get('avg_days_emit_to_aprov'))
        v_aprov_nf, u_aprov_nf = _format_lead(row.get('avg_days_aprov_to_first_nf'))
        v_nf_fat, u_nf_fat = _format_lead(row.get('avg_days_first_to_last_nf'))

        qty_parcial = max(0, qty_fat_ini - qty_fat_tot)

        stages = [
            {
                'id': 'req',
                'name': 'Requisições',
                'sub': 'Aprovadas',
                'icon': 'req',
                'spend': spend_req,
                'qty': qty_req,
                'qty_label': 'requisições',
                'conv_pct': 100.0,
                'step_conv_pct': 100.0
            },
            {
                'id': 'emit',
                'name': 'Pedidos',
                'sub': 'Emitidos',
                'icon': 'cart',
                'spend': spend_emit,
                'qty': qty_emit,
                'qty_label': 'pedidos emitidos',
                'conv_pct': round(qty_emit / qty_req * 100, 1) if qty_req > 0 else 100.0,
                'step_conv_pct': round(qty_emit / qty_req * 100, 1) if qty_req > 0 else 100.0
            },
            {
                'id': 'aprov',
                'name': 'Pedidos',
                'sub': 'Aprovados',
                'icon': 'cart',
                'spend': spend_aprov,
                'qty': qty_aprov,
                'qty_label': 'pedidos aprovados',
                'conv_pct': round(qty_aprov / qty_req * 100, 1) if qty_req > 0 else 0,
                'step_conv_pct': round(qty_aprov / qty_emit * 100, 1) if qty_emit > 0 else 0
            },
            {
                'id': 'fat_ini',
                'name': 'Faturamento',
                'sub': 'Iniciado',
                'icon': 'fat_ini',
                'spend': spend_fat_ini,
                'qty': qty_fat_ini,
                'qty_label': 'pedidos faturados',
                'conv_pct': round(qty_fat_ini / qty_req * 100, 1) if qty_req > 0 else 0,
                'step_conv_pct': round(qty_fat_ini / qty_aprov * 100, 1) if qty_aprov > 0 else 0,
                'open_spend': max(0.0, spend_aprov - spend_fat_ini),
                'open_pct': round(max(0.0, spend_aprov - spend_fat_ini) / spend_aprov * 100, 1) if spend_aprov > 0 else 0
            },
            {
                'id': 'fat_tot',
                'name': 'Faturamento',
                'sub': 'Totalmente Concluído',
                'icon': 'fat_tot',
                'spend': spend_fat_tot,
                'qty': qty_fat_tot,
                'qty_label': 'pedidos concluídos',
                'conv_pct': round(qty_fat_tot / qty_req * 100, 1) if qty_req > 0 else 0,
                'step_conv_pct': round(qty_fat_tot / qty_fat_ini * 100, 1) if qty_fat_ini > 0 else 0,
                'open_spend': max(0.0, spend_fat_ini - spend_fat_tot),
                'open_pct': round(qty_parcial / qty_fat_ini * 100, 1) if qty_fat_ini > 0 else 0,
                'open_qty': qty_parcial,
                'open_label': f'Parciais: {qty_parcial:,}'.replace(',', '.')
            }
        ]
        connectors = [
            {'from': 'req', 'to': 'emit', 'val': v_req_emit, 'unit': u_req_emit, 'label': 'Requisição Aprovada e Pedido Emitido'},
            {'from': 'emit', 'to': 'aprov', 'val': v_emit_aprov, 'unit': u_emit_aprov, 'label': 'Pedido Emitido e Pedido Aprovado'},
            {'from': 'aprov', 'to': 'fat_ini', 'val': v_aprov_nf, 'unit': u_aprov_nf, 'label': 'Pedido Aprovado e 1ª NF'},
            {'from': 'fat_ini', 'to': 'fat_tot', 'val': v_nf_fat, 'unit': u_nf_fat, 'label': '1ª NF e Conclusão do Faturamento'}
        ]

    else:
        # Diretos or Todos
        sql = f"""
        WITH oc_cohort AS (
            SELECT 
                oc.numero_oc,
                oc.chave_oc_linha,
                oc.valor_original_brl,
                NULLIF(TRIM(oc.data_oc), '')::date AS d_oc,
                NULLIF(TRIM(oc.dt_aprovacao), '')::date AS d_aprov,
                oc.status_aprovacao,
                oc.status_fechamento
            FROM ordens_compra oc
            WHERE {oc_where}
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
        )
        SELECT 
            (SELECT COALESCE(SUM(valor_original_brl), 0)::float FROM oc_cohort) AS spend_emit,
            (SELECT COUNT(DISTINCT numero_oc)::int FROM oc_cohort) AS qty_emit,
            (SELECT COALESCE(SUM(valor_original_brl), 0)::float FROM oc_aprov) AS spend_aprov,
            (SELECT COUNT(DISTINCT numero_oc)::int FROM oc_aprov) AS qty_aprov,
            (SELECT AVG(d_aprov - d_oc)::float FROM oc_aprov WHERE d_aprov IS NOT NULL AND d_oc IS NOT NULL AND (d_aprov - d_oc) >= 0) AS avg_days_emit_to_aprov,
            (SELECT qty_fat_ini FROM oc_fat_metrics) AS qty_fat_ini,
            (SELECT spend_fat_ini FROM oc_fat_metrics) AS spend_fat_ini,
            (SELECT qty_fat_tot FROM oc_fat_metrics) AS qty_fat_tot,
            (SELECT spend_fat_tot FROM oc_fat_metrics) AS spend_fat_tot,
            (SELECT avg_days_aprov_to_first_nf FROM oc_fat_metrics) AS avg_days_aprov_to_first_nf,
            (SELECT avg_days_first_to_last_nf FROM oc_fat_metrics) AS avg_days_first_to_last_nf
        """
        rows = query(sql)
        row = rows[0] if rows else {}

        spend_emit = float(row.get('spend_emit') or 0)
        qty_emit = int(row.get('qty_emit') or 0)
        spend_aprov = float(row.get('spend_aprov') or 0)
        qty_aprov = int(row.get('qty_aprov') or 0)
        spend_fat_ini = float(row.get('spend_fat_ini') or 0)
        qty_fat_ini = int(row.get('qty_fat_ini') or 0)
        spend_fat_tot = float(row.get('spend_fat_tot') or 0)
        qty_fat_tot = int(row.get('qty_fat_tot') or 0)

        v_emit_aprov, u_emit_aprov = _format_lead(row.get('avg_days_emit_to_aprov'))
        v_aprov_nf, u_aprov_nf = _format_lead(row.get('avg_days_aprov_to_first_nf'))
        v_nf_fat, u_nf_fat = _format_lead(row.get('avg_days_first_to_last_nf'))
        v_req_emit, u_req_emit = None, 'dias'

        qty_parcial = max(0, qty_fat_ini - qty_fat_tot)

        stages = [
            {
                'id': 'emit',
                'name': 'Pedidos',
                'sub': 'Emitidos',
                'icon': 'cart',
                'spend': spend_emit,
                'qty': qty_emit,
                'qty_label': 'pedidos emitidos',
                'conv_pct': 100.0,
                'step_conv_pct': 100.0
            },
            {
                'id': 'aprov',
                'name': 'Pedidos',
                'sub': 'Aprovados',
                'icon': 'cart',
                'spend': spend_aprov,
                'qty': qty_aprov,
                'qty_label': 'pedidos aprovados',
                'conv_pct': round(qty_aprov / qty_emit * 100, 1) if qty_emit > 0 else 0,
                'step_conv_pct': round(qty_aprov / qty_emit * 100, 1) if qty_emit > 0 else 0
            },
            {
                'id': 'fat_ini',
                'name': 'Faturamento',
                'sub': 'Iniciado',
                'icon': 'fat_ini',
                'spend': spend_fat_ini,
                'qty': qty_fat_ini,
                'qty_label': 'pedidos faturados',
                'conv_pct': round(qty_fat_ini / qty_emit * 100, 1) if qty_emit > 0 else 0,
                'step_conv_pct': round(qty_fat_ini / qty_aprov * 100, 1) if qty_aprov > 0 else 0,
                'open_spend': max(0.0, spend_aprov - spend_fat_ini),
                'open_pct': round(max(0.0, spend_aprov - spend_fat_ini) / spend_aprov * 100, 1) if spend_aprov > 0 else 0
            },
            {
                'id': 'fat_tot',
                'name': 'Faturamento',
                'sub': 'Totalmente Concluído',
                'icon': 'fat_tot',
                'spend': spend_fat_tot,
                'qty': qty_fat_tot,
                'qty_label': 'pedidos concluídos',
                'conv_pct': round(qty_fat_tot / qty_emit * 100, 1) if qty_emit > 0 else 0,
                'step_conv_pct': round(qty_fat_tot / qty_fat_ini * 100, 1) if qty_fat_ini > 0 else 0,
                'open_spend': max(0.0, spend_fat_ini - spend_fat_tot),
                'open_pct': round(qty_parcial / qty_fat_ini * 100, 1) if qty_fat_ini > 0 else 0,
                'open_qty': qty_parcial,
                'open_label': f'Parciais: {qty_parcial:,}'.replace(',', '.')
            }
        ]
        connectors = [
            {'from': 'emit', 'to': 'aprov', 'val': v_emit_aprov, 'unit': u_emit_aprov, 'label': 'Pedido Emitido e Pedido Aprovado'},
            {'from': 'aprov', 'to': 'fat_ini', 'val': v_aprov_nf, 'unit': u_aprov_nf, 'label': 'Pedido Aprovado e 1ª NF'},
            {'from': 'fat_ini', 'to': 'fat_tot', 'val': v_nf_fat, 'unit': u_nf_fat, 'label': '1ª NF e Conclusão do Faturamento'}
        ]

    # Find longest lead time leg for summary
    legs_sorted = sorted([c for c in connectors if c['val'] is not None], key=lambda c: c['val'] * (24 if c['unit'] == 'dias' else 1), reverse=True)
    longest_leg_name = legs_sorted[0]['label'] if legs_sorted else 'Pedido Aprovado e 1ª NF'
    summary_title = f"O maior tempo do processo está entre {longest_leg_name}."

    result = [{
        'scope': scope,
        'stages': stages,
        'connectors': connectors,
        'longest_leg': longest_leg_name,
        'summary_title': summary_title,
        # Legacy compatibility fields
        'req_to_po_emit_days': v_req_emit,
        'req_to_po_emit_unit': u_req_emit,
        'po_emit_to_aprov_days': v_emit_aprov,
        'po_emit_to_aprov_unit': u_emit_aprov,
        'po_to_nf_days': v_aprov_nf,
        'po_to_nf_unit': u_aprov_nf,
        'qty_req': stages[0]['qty'] if scope == 'indiretos' and len(stages) > 0 else 0,
        'qty_emit': stages[1]['qty'] if scope == 'indiretos' and len(stages) > 1 else (stages[0]['qty'] if len(stages) > 0 else 0),
        'qty_aprov': stages[2]['qty'] if scope == 'indiretos' and len(stages) > 2 else (stages[1]['qty'] if len(stages) > 1 else 0),
        'qty_nf': stages[3]['qty'] if scope == 'indiretos' and len(stages) > 3 else (stages[2]['qty'] if len(stages) > 2 else 0)
    }]
    return jsonify(result)



@app.route('/api/performance/process-deviations')
def performance_process_deviations():
    """Process deviations: Regular, Post-Invoice PO, Invoice Without PO."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        SUM(CASE WHEN NUMERO_OC != 'Nota sem OC' AND OC_POS_FATURA = 'NÃO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS regular,
        SUM(CASE WHEN OC_POS_FATURA = 'SIM' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS pos_fatura,
        SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS sem_oc,
        SUM(VALOR_LIQUIDO_BRL) AS total
    FROM notas_ri
    {w}
    """
    return jsonify(query(sql, params))


