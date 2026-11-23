import re, sys

with open('src/app/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Clean governance_by_buyer
new_by_buyer = '''@app.route('/api/governance/by-buyer')
def governance_by_buyer():
    """Buyer exceptions table with type, qty, value, and % of buyer total."""
    # Build date + entity filters: LANÇAMENTO para emergencial, PAGAMENTO para pos_fatura, DATA_OC para descentral
    exc_lancto_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', table_prefix='nf')
    exc_pgto_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')

    lancto_date = [c for c in exc_lancto_clauses if 'DATA_LANCAMENTO' in c]
    pgto_date = [c for c in exc_pgto_clauses if 'DATA_PAGAMENTO' in c]
    exc_base = [c for c in exc_lancto_clauses if 'DATA_LANCAMENTO' not in c and not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    exc_base_and = ('AND ' + ' AND '.join(exc_base)) if exc_base else ''

    lancto_d_and = (' AND ' + ' AND '.join(lancto_date)) if lancto_date else ''
    pgto_d_and = (' AND ' + ' AND '.join(pgto_date)) if pgto_date else ''

    _comp_vals = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    comp_and = f"AND oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})" if _comp_vals else ''

    # Filtros de ordens_compra para OCs descentralizadas
    oc_clauses_gov, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
    w_oc_gov = _where(oc_clauses_gov)
    oc_and_kw = 'AND' if oc_clauses_gov else 'WHERE'
    oc_comp_and = f"AND oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})" if _comp_vals else ''

    sql = f"""
    WITH oc_desc_30k AS (
        SELECT oc.NUMERO_OC
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.CENTRALIZADO = 'DESCENTRALIZADO'
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
          AND (oc.email_usuario IS NULL OR LOWER(oc.email_usuario) NOT IN (SELECT LOWER(email) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND email IS NOT NULL))
          AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
        GROUP BY oc.NUMERO_OC
        HAVING SUM(oc.valor_original_brl) > 30000
    ),
    buyer_totals AS (
        SELECT
            COALESCE(oc.NOME_USUARIO, 'Não identificado') AS buyer,
            COUNT(DISTINCT nf.NOTA_FISCAL) AS total_transactions
        FROM notas_ri nf
        LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        WHERE 1=1 {exc_base_and} {pgto_d_and} {comp_and}
        GROUP BY COALESCE(oc.NOME_USUARIO, 'Não identificado')
    ),
    buyer_exceptions AS (
        SELECT
            COALESCE(oc.NOME_USUARIO, 'Não identificado') AS buyer,
            MAX(oc.USUARIO) AS usuario,
            MAX(oc.EMAIL_USUARIO) AS email,
            MAX(oc.AREA) AS area_oc,
            CASE
                WHEN nf.OC_POS_FATURA = 'SIM'{pgto_d_and} THEN 'OCs Pós-Fatura'
                WHEN nf.URGENTE = 'SIM'{lancto_d_and} THEN 'Emergencial'
                ELSE 'Outra'
            END AS tipo_excecao,
            COUNT(DISTINCT nf.NUMERO_OC) AS qty,
            SUM(nf.VALOR_LIQUIDO_BRL) AS valor
        FROM notas_ri nf
        LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        WHERE 1=1 {exc_base_and} {comp_and}
          AND nf.NUMERO_OC != 'Nota sem OC'
          AND (
              (nf.OC_POS_FATURA = 'SIM'{pgto_d_and})
              OR (nf.URGENTE = 'SIM'{lancto_d_and})
          )
        GROUP BY COALESCE(oc.NOME_USUARIO, 'Não identificado'),
                 CASE
                    WHEN nf.OC_POS_FATURA = 'SIM'{pgto_d_and} THEN 'OCs Pós-Fatura'
                    WHEN nf.URGENTE = 'SIM'{lancto_d_and} THEN 'Emergencial'
                    ELSE 'Outra'
                 END

        UNION ALL

        SELECT
            COALESCE(oc.NOME_USUARIO, 'Não identificado') AS buyer,
            MAX(oc.USUARIO) AS usuario,
            MAX(oc.EMAIL_USUARIO) AS email,
            MAX(oc.AREA) AS area_oc,
            'OC Descentr. >30K' AS tipo_excecao,
            COUNT(DISTINCT oc.NUMERO_OC) AS qty,
            SUM(oc.valor_original_brl) AS valor
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k)
        {oc_comp_and}
        GROUP BY COALESCE(oc.NOME_USUARIO, 'Não identificado')
    )
    SELECT
        be.buyer,
        be.tipo_excecao,
        be.qty,
        be.valor,
        CASE WHEN COALESCE(bt.total_transactions, 0) > 0
             THEN LEAST(100.0, ROUND((be.qty::float / bt.total_transactions * 100)::numeric, 1))
             ELSE 100.0 END AS pct_transacoes,
        REGEXP_REPLACE(
            COALESCE(
                CASE 
                    WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                    THEN cf.area || ' - ' || cf.unidade
                    ELSE cf.area 
                END,
                NULLIF(be.area_oc, ''),
                'Não informado'
            ),
            '^[0-9]+\\s*-\\s*',
            ''
        ) AS depart,
        REGEXP_REPLACE(
            COALESCE(
                CASE 
                    WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                    THEN cf.area || ' - ' || cf.unidade
                    ELSE cf.area 
                END,
                NULLIF(be.area_oc, ''),
                'Não informado'
            ),
            '^[0-9]+\\s*-\\s*',
            ''
        ) AS area
    FROM buyer_exceptions be
    LEFT JOIN buyer_totals bt ON be.buyer = bt.buyer
    LEFT JOIN compradores_funcionais cf ON (
        LOWER(cf.usuario_oracle) = LOWER(be.usuario)
        OR (be.email IS NOT NULL AND cf.email IS NOT NULL AND LOWER(cf.email) = LOWER(be.email))
        OR (cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(be.buyer))
    )
    ORDER BY be.valor DESC
    LIMIT 200
    """
    rows, err = query_debug(sql)
    if err:
        _log.error("BY-BUYER ERROR: %s", err)
    return jsonify(rows)
'''

# 2. Clean governance_exceptions_table
new_exceptions_table = '''@app.route('/api/governance/exceptions-table')
def governance_exceptions_table():
    """Exceptions detail table with native Oracle Buyer and Requester information."""
    exc_type = request.args.get('type', 'all')
    page = int(request.args.get('page', '1'))
    per_page = int(request.args.get('per_page', '50'))
    offset = (page - 1) * per_page

    type_filter = ""
    if exc_type == 'pos_fatura':
        # Filtros de entidade e data ancorada em DATA_PAGAMENTO
        pf_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')
        _pf_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _pf_comp:
            pf_clauses.append(f"oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _pf_comp])})")
        pf_where_and = 'AND ' + ' AND '.join(pf_clauses) if pf_clauses else ''

        # Agrupado por OC: uma linha por NUMERO_OC, filtrado por DATA_PAGAMENTO
        sql = f"""
        WITH oc_pos AS (
            SELECT
                nf.NUMERO_OC,
                MIN(CASE WHEN nf.DT_NOTA ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN SUBSTRING(nf.DT_NOTA, 1, 10) ELSE NULL END) AS primeira_nf,
                MAX(CASE WHEN oc.DT_APROVACAO ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN SUBSTRING(oc.DT_APROVACAO, 1, 10) ELSE NULL END) AS dt_aprovacao,
                MAX(COALESCE(oc.NOME_USUARIO, 'Não informado')) AS comprador,
                MAX(oc.USUARIO) AS usuario,
                MAX(oc.EMAIL_USUARIO) AS email,
                MAX(oc.AREA) AS area_oc,
                MAX(COALESCE(oc.NOME_REQUISITANTE, 'Não informado')) AS solicitante,
                MAX(nf.NOME_FORNECEDOR) AS fornecedor,
                SUM(nf.VALOR_LIQUIDO_BRL) AS net_spend,
                COUNT(DISTINCT nf.NOTA_FISCAL)::int AS qty_notas,
                STRING_AGG(DISTINCT nf.NOTA_FISCAL, ', ') AS "NOTA_FISCAL"
            FROM notas_ri nf
            LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
            WHERE nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != '' AND nf.NUMERO_OC != 'Nota sem OC'
              AND nf.OC_POS_FATURA = 'SIM'
              AND nf.DT_NOTA IS NOT NULL AND nf.DT_NOTA != ''
              {pf_where_and}
            GROUP BY nf.NUMERO_OC
        )
        SELECT
            'OCs pós-fatura' AS tipo_excecao,
            p.NUMERO_OC AS "NUMERO_OC",
            p."NOTA_FISCAL",
            p.qty_notas,
            p.primeira_nf AS data_fatura,
            p.dt_aprovacao AS data_oc,
            CASE
                WHEN p.dt_aprovacao ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND p.primeira_nf ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN (p.dt_aprovacao::date - p.primeira_nf::date)
                ELSE NULL
            END AS dias_pos_fatura,
            p.comprador,
            REGEXP_REPLACE(
                COALESCE(
                    CASE 
                        WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                        THEN cf.area || ' - ' || cf.unidade
                        ELSE cf.area 
                    END,
                    NULLIF(p.area_oc, ''),
                    'Não informado'
                ),
                '^[0-9]+\\s*-\\s*',
                ''
            ) AS depart_comprador,
            p.solicitante,
            REGEXP_REPLACE(
                COALESCE(p.area_oc, ''),
                '^[0-9]+\\s*-\\s*',
                ''
            ) AS depart_solicitante,
            p.fornecedor,
            p.net_spend
        FROM oc_pos p
        LEFT JOIN compradores_funcionais cf ON (
            LOWER(cf.usuario_oracle) = LOWER(p.usuario)
            OR (p.email IS NOT NULL AND cf.email IS NOT NULL AND LOWER(cf.email) = LOWER(p.email))
            OR (cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(p.comprador))
        )
        ORDER BY p.net_spend DESC
        LIMIT {per_page} OFFSET {offset}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [pos_fatura] ERROR: %s", err)
        return jsonify(rows)

    # ── OC abertas >90 dias (ignores date filters, queries ordens_compra) ──
    if exc_type == 'oc_90':
        oc90_parts = ["oc.STATUS_FECHAMENTO = 'ABERTA'", "oc.dias_aberto > 90"]
        _oc90_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        if _oc90_emp:
            oc90_parts.append(f"oc.org_desc IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _oc90_emp])})")
        _oc90_grp = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
        if _oc90_grp:
            oc90_parts.append(f"oc.grupo_compras_oc IN ({','.join([chr(39)+_esc(g)+chr(39) for v in _oc90_grp])})")
        _oc90_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
        if _oc90_frn:
            oc90_parts.append(f"oc.nome_fornecedor IN ({','.join([chr(39)+_esc(f_)+chr(39) for f_ in _oc90_frn])})")
        _oc90_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _oc90_comp:
            oc90_parts.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _oc90_comp])})")
        oc90_where = ' AND '.join(oc90_parts)
        sql = f"""
        SELECT 'OC aberta >90 dias' AS tipo_excecao,
               oc.NUMERO_OC AS "NUMERO_OC",
               oc.nome_fornecedor AS fornecedor,
               COALESCE(oc.nome_usuario, 'Não informado') AS comprador,
               REGEXP_REPLACE(
                   COALESCE(
                       CASE 
                           WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                           THEN cf.area || ' - ' || cf.unidade
                           ELSE cf.area 
                       END,
                       NULLIF(oc.area, ''),
                       'Não informado'
                   ),
                   '^[0-9]+\\s*-\\s*',
                   ''
               ) AS depart_comprador,
               COALESCE(oc.nome_requisitante, 'Não informado') AS solicitante,
               REGEXP_REPLACE(COALESCE(oc.area, ''), '^[0-9]+\\s*-\\s*', '') AS depart_solicitante,
               oc.valor_original_brl AS net_spend,
               oc.DATA_OC AS data_oc,
               oc.dias_aberto,
               oc.STATUS_FECHAMENTO AS status
        FROM ordens_compra oc
        LEFT JOIN compradores_funcionais cf ON (
            LOWER(cf.usuario_oracle) = LOWER(oc.usuario)
            OR (oc.email_usuario IS NOT NULL AND cf.email IS NOT NULL AND LOWER(cf.email) = LOWER(oc.email_usuario))
            OR (cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(oc.nome_usuario))
        )
        WHERE {oc90_where}
        ORDER BY oc.dias_aberto DESC
        LIMIT {per_page} OFFSET {offset}
        """
        return jsonify(query(sql))

    # ── Acordos abertos >180 dias (acordo_status='OPEN', age from acordo_dt_criacao) ──
    if exc_type == 'blanket_old':
        bla_parts = [
            "oc.acordo_status = 'OPEN'",
            "oc.numero_acordo IS NOT NULL",
            "oc.numero_acordo != ''",
            "oc.acordo_dt_criacao IS NOT NULL",
            "oc.acordo_dt_criacao != ''",
            "(CURRENT_DATE - oc.acordo_dt_criacao::date) > 180",
            "COALESCE(oc.acordo_valor_liberado, 0) = 0",
        ]
        _bla_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        if _bla_emp:
            bla_parts.append(f"oc.org_desc IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _bla_emp])})")
        _bla_grp = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
        if _bla_grp:
            bla_parts.append(f"oc.grupo_compras_oc IN ({','.join([chr(39)+_esc(g)+chr(39) for v in _bla_grp])})")
        _bla_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
        if _bla_frn:
            bla_parts.append(f"oc.nome_fornecedor IN ({','.join([chr(39)+_esc(f_)+chr(39) for f_ in _bla_frn])})")
        _bla_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _bla_comp:
            bla_parts.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _bla_comp])})")
        bla_where = ' AND '.join(bla_parts)
        sql = f"""
        SELECT 'Acordo de Compra >180 dias' AS tipo_excecao,
               oc.numero_acordo AS "NUMERO_OC",
               MAX(oc.nome_fornecedor) AS fornecedor,
               MAX(COALESCE(oc.nome_usuario, 'Não informado')) AS comprador,
               REGEXP_REPLACE(
                   COALESCE(
                       MAX(CASE 
                           WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                           THEN cf.area || ' - ' || cf.unidade
                           ELSE cf.area 
                       END),
                       NULLIF(MAX(oc.area), ''),
                       'Não informado'
                   ),
                   '^[0-9]+\\s*-\\s*',
                   ''
               ) AS depart_comprador,
               MAX(oc.acordo_valor_total) AS net_spend,
               MAX(oc.DATA_OC) AS data_oc,
               (CURRENT_DATE - MAX(oc.acordo_dt_criacao)::date) AS dias_aberto,
               MAX(oc.acordo_dt_criacao) AS acordo_dt_criacao,
               MAX(oc.acordo_data_final) AS acordo_data_final,
               MAX(oc.acordo_status) AS acordo_status,
               MAX(oc.acordo_descricao) AS acordo_descricao
        FROM ordens_compra oc
        LEFT JOIN compradores_funcionais cf ON (
            LOWER(cf.usuario_oracle) = LOWER(oc.usuario)
            OR (oc.email_usuario IS NOT NULL AND cf.email IS NOT NULL AND LOWER(cf.email) = LOWER(oc.email_usuario))
            OR (cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(oc.nome_usuario))
        )
        WHERE {bla_where}
        GROUP BY oc.numero_acordo
        ORDER BY (CURRENT_DATE - MAX(oc.acordo_dt_criacao)::date) DESC
        LIMIT {per_page} OFFSET {offset}
        """
        return jsonify(query(sql))

    # ── OC Descentralizada >30k (source: ordens_compra, filter by DATA_OC) ──
    if exc_type == 'decentral':
        dec_oc_clauses, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
        dec_oc_base = [c for c in dec_oc_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        dec_oc_and = ('AND ' + ' AND '.join(dec_oc_base)) if dec_oc_base else ''
        sql = f"""
        SELECT 'Descentralizada' AS tipo_excecao,
               oc.numero_oc AS "NUMERO_OC",
               MAX(COALESCE(oc.nome_usuario, 'Não informado')) AS comprador,
               REGEXP_REPLACE(
                   COALESCE(
                       MAX(CASE 
                           WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                           THEN cf.area || ' - ' || cf.unidade
                           ELSE cf.area 
                       END),
                       NULLIF(MAX(oc.area), ''),
                       'Não informado'
                   ),
                   '^[0-9]+\\s*-\\s*',
                   ''
               ) AS depart_comprador,
               MAX(COALESCE(oc.nome_requisitante, 'Não informado')) AS solicitante,
               REGEXP_REPLACE(MAX(COALESCE(oc.area, '')), '^[0-9]+\\s*-\\s*', '') AS depart_solicitante,
               MAX(oc.nome_fornecedor) AS fornecedor,
               MAX(oc.data_oc) AS data_oc,
               SUM(oc.valor_original_brl)::float AS net_spend
        FROM ordens_compra oc
        LEFT JOIN compradores_funcionais cf ON (
            LOWER(cf.usuario_oracle) = LOWER(oc.usuario)
            OR (oc.email_usuario IS NOT NULL AND cf.email IS NOT NULL AND LOWER(cf.email) = LOWER(oc.email_usuario))
            OR (cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(oc.nome_usuario))
        )
        WHERE oc.CENTRALIZADO = 'DESCENTRALIZADO'
          AND oc.numero_oc IS NOT NULL AND oc.numero_oc != ''
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
          AND (oc.email_usuario IS NULL OR LOWER(oc.email_usuario) NOT IN (SELECT LOWER(email) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND email IS NOT NULL))
          AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
          {dec_oc_and}
        GROUP BY oc.numero_oc
        HAVING SUM(oc.valor_original_brl) > 30000
        ORDER BY net_spend DESC
        LIMIT {per_page} OFFSET {offset}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [decentral] ERROR: %s", err)
        return jsonify(rows)

    # ── Notas sem OCs (source: notas_ri, filter by DATA_LANCAMENTO) ──
    if exc_type == 'sem_oc':
        sem_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', table_prefix='nf')
        sem_base = [c for c in sem_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        sem_w = _where(sem_base)
        and_kw = 'AND' if sem_base else 'WHERE'

        sql = f"""
        SELECT
            'Notas sem OCs' AS tipo_excecao,
            NULL AS "NUMERO_OC",
            nf.NOTA_FISCAL AS "NOTA_FISCAL",
            NULL AS comprador,
            NULL AS depart_comprador,
            NULL AS solicitante,
            NULL AS depart_solicitante,
            nf.NOME_FORNECEDOR AS fornecedor,
            nf.VALOR_LIQUIDO_BRL AS net_spend,
            nf.DATA_LANCAMENTO AS data_fatura,
            NULL AS data_emissao_oc,
            NULL AS data_oc,
            NULL AS dias_pos_fatura
        FROM notas_ri nf
        {sem_w} {and_kw} nf.NUMERO_OC = 'Nota sem OC'
        ORDER BY nf.VALOR_LIQUIDO_BRL DESC
        LIMIT {per_page} OFFSET {offset}
        """
        return jsonify(query(sql))

    # Demais tipos: query por linha individual
    # Build date + entity filters: LANÇAMENTO para sem_oc/decentral, PAGAMENTO para pos_fatura
    exc_lancto_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', table_prefix='nf')
    exc_pgto_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')

    lancto_date = [c for c in exc_lancto_clauses if 'DATA_LANCAMENTO' in c]
    pgto_date = [c for c in exc_pgto_clauses if 'DATA_PAGAMENTO' in c]
    exc_base = [c for c in exc_lancto_clauses if 'DATA_LANCAMENTO' not in c and not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    exc_and = ('AND ' + ' AND '.join(exc_base)) if exc_base else ''
    _exc_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    exc_comp_and = f"AND oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _exc_comp])})" if _exc_comp else ''

    lancto_d_and = (' AND ' + ' AND '.join(lancto_date)) if lancto_date else ''
    pgto_d_and = (' AND ' + ' AND '.join(pgto_date)) if pgto_date else ''

    # For emergencial: override date filter to use oc.DATA_OC
    if exc_type == 'urgente':
        urg_parts = []
        _urg_ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
        if _urg_ano:
            urg_parts.append(f"SUBSTRING(oc.DATA_OC, 1, 4) IN ({','.join([chr(39)+a+chr(39) for a in _urg_ano])})")
        _urg_mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
        if _urg_mes:
            urg_parts.append(f"CAST(SUBSTRING(oc.DATA_OC, 6, 2) AS INT) IN ({','.join(_urg_mes)})")
        _urg_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        if _urg_emp:
            urg_parts.append(f"nf.EMPRESA IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _urg_emp])})")
        _urg_grp = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
        if _urg_grp:
            urg_parts.append(f"nf.GRUPO_COMPRAS IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _urg_grp])})")
        _urg_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
        if _urg_frn:
            urg_parts.append(f"nf.NOME_FORNECEDOR IN ({','.join([chr(39)+_esc(f_)+chr(39) for f_ in _urg_frn])})")
        _urg_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _urg_comp:
            urg_parts.append(f"oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _urg_comp])})")
        exc_and = ('AND ' + ' AND '.join(urg_parts)) if urg_parts else ''
        exc_comp_and = ''  # already handled above in urg_parts

    # Build decentral CTE for type=all (same pattern as by-buyer endpoint)
    oc_pos_cte = f"""WITH oc_desc_30k AS (
        SELECT oc.NUMERO_OC
        FROM ordens_compra oc
        WHERE oc.CENTRALIZADO = 'DESCENTRALIZADO' AND oc.NUMERO_OC IS NOT NULL AND oc.NUMERO_OC != ''
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
          AND (oc.email_usuario IS NULL OR LOWER(oc.email_usuario) NOT IN (SELECT LOWER(email) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND email IS NOT NULL))
          AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
        GROUP BY oc.NUMERO_OC
        HAVING SUM(oc.valor_original_brl) > 30000
    )"""

    type_filter = ""
    if exc_type == 'urgente':
        type_filter = "AND nf.URGENTE = 'SIM'"
    elif exc_type == 'sem_oc':
        type_filter = f"AND nf.NUMERO_OC = 'Nota sem OC'{lancto_d_and}"
    elif exc_type == 'decentral':
        type_filter = f"AND nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC != 'Nota sem OC' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k){lancto_d_and}"
    else:
        type_filter = f"AND ((nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC'{pgto_d_and}) OR (nf.URGENTE = 'SIM'{lancto_d_and}) OR (nf.NUMERO_OC = 'Nota sem OC'{lancto_d_and}) OR (nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k){lancto_d_and}))"

    # Fixed label per type (OC can belong to multiple types simultaneously)
    tipo_label_map = {
        'urgente': "'OC emergencial'",
        'sem_oc': "'Notas sem OCs'",
        'decentral': "'Descentralizada'",
    }
    tipo_expr = tipo_label_map.get(exc_type, """
        CASE
            WHEN nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC' THEN 'OCs pós-fatura'
            WHEN nf.URGENTE = 'SIM' THEN 'OC emergencial'
            WHEN nf.NUMERO_OC = 'Nota sem OC' THEN 'Notas sem OCs'
            WHEN nf.CENTRALIZADO = 'DESCENTRALIZADO' THEN 'Descentralizada'
            ELSE 'Outro'
        END""")

    sql = f"""
    {oc_pos_cte}
    SELECT
        {tipo_expr} AS tipo_excecao,
        CASE
            WHEN nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != '' AND nf.NUMERO_OC != 'Nota sem OC'
            THEN nf.NUMERO_OC
            ELSE oc.NUMERO_OC
        END AS "NUMERO_OC",
        nf.NOTA_FISCAL AS "NOTA_FISCAL",
        COALESCE(oc.NOME_USUARIO, 'Não informado') AS comprador,
        REGEXP_REPLACE(
            COALESCE(
                CASE 
                    WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                    THEN cf.area || ' - ' || cf.unidade
                    ELSE cf.area 
                END,
                NULLIF(oc.AREA, ''),
                'Não informado'
            ),
            '^[0-9]+\\s*-\\s*',
            ''
        ) AS depart_comprador,
        COALESCE(oc.NOME_REQUISITANTE, 'Não informado') AS solicitante,
        REGEXP_REPLACE(
            COALESCE(oc.AREA, ''),
            '^[0-9]+\\s*-\\s*',
            ''
        ) AS depart_solicitante,
        nf.NOME_FORNECEDOR AS fornecedor,
        nf.VALOR_LIQUIDO_BRL AS net_spend,
        COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) AS data_fatura,
        oc.DATA_OC AS data_emissao_oc,
        oc.DT_APROVACAO AS data_oc,
        CASE
            WHEN oc.DT_APROVACAO ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' 
                 AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
            THEN (SUBSTRING(oc.DT_APROVACAO, 1, 10)::date 
                  - SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date)
            ELSE NULL
        END AS dias_pos_fatura
    FROM notas_ri nf
    LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
    LEFT JOIN compradores_funcionais cf ON (
        LOWER(cf.usuario_oracle) = LOWER(oc.usuario)
        OR (oc.email_usuario IS NOT NULL AND cf.email IS NOT NULL AND LOWER(cf.email) = LOWER(oc.email_usuario))
        OR (cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(oc.nome_usuario))
    )
    WHERE 1=1 {type_filter} {exc_and} {exc_comp_and}
    ORDER BY nf.VALOR_LIQUIDO_BRL DESC
    LIMIT {per_page} OFFSET {offset}
    """
    rows, err = query_debug(sql)
    if err:
        _log.error("EXCEPTIONS-TABLE [%s] ERROR: %s", exc_type, err)
    return jsonify(rows)
'''

# Now perform replacement
idx_by_buyer = content.find("@app.route('/api/governance/by-buyer')")
idx_reports = content.find("@app.route('/api/reports/data')")

if idx_by_buyer == -1 or idx_reports == -1:
    print(f"Error finding markers: idx_by_buyer={idx_by_buyer}, idx_reports={idx_reports}")
    sys.exit(1)

new_content = content[:idx_by_buyer] + new_by_buyer + "\n\n" + new_exceptions_table + "\n\n" + content[idx_reports:]

with open('src/app/app.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Replaced successfully!")
