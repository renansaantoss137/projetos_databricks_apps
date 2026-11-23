import re, sys

# 1. Prepare clean governance replacement block
clean_governance_block = '''@app.route('/api/governance/kpis')
def governance_kpis():
    """Exception KPIs."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        COUNT(DISTINCT CASE WHEN NUMERO_OC != 'Nota sem OC' AND NUMERO_OC IS NOT NULL THEN NUMERO_OC END) AS total_oc_faturadas,
        COUNT(DISTINCT NOTA_FISCAL) AS total_notas,
        COUNT(DISTINCT CASE WHEN URGENTE = 'SIM' THEN NUMERO_OC END) AS urgente_qty,
        SUM(CASE WHEN URGENTE = 'SIM' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS urgente_val,
        COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' THEN NOTA_FISCAL END) AS sem_oc_qty,
        SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS sem_oc_val
    FROM notas_ri
    {w}
    """
    result = query(sql, params)

    # OC Pós-Fatura: usa coluna oc_pos_fatura calculada no ETL com âncora em DATA_PAGAMENTO
    pf_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO')
    w_pf = _where(pf_clauses)
    and_pf = 'AND' if pf_clauses else 'WHERE'

    pos_fatura_sql = f"""
    SELECT COUNT(DISTINCT NUMERO_OC) AS qty, COALESCE(SUM(VALOR_LIQUIDO_BRL), 0) AS val
    FROM notas_ri
    {w_pf}
    {and_pf} OC_POS_FATURA = 'SIM' AND NUMERO_OC != 'Nota sem OC'
    """
    pos_result = query(pos_fatura_sql)

    # Total de OCs faturadas no período com âncora em DATA_PAGAMENTO (para o percentual do card pós-fatura)
    total_oc_pgto_sql = f"""
    SELECT COUNT(DISTINCT NUMERO_OC) AS total
    FROM notas_ri
    {w_pf}
    {and_pf} NUMERO_OC != 'Nota sem OC' AND NUMERO_OC IS NOT NULL AND NUMERO_OC != ''
    """
    total_oc_pgto = query(total_oc_pgto_sql)

    # Decentralized >30k (source: ordens_compra, filter by DATA_OC)
    oc_clauses_gov, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
    oc_gov_filtered = [c for c in oc_clauses_gov if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    _comp_vals = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _comp_vals:
        oc_gov_filtered.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})")
    w_oc_gov = _where(oc_gov_filtered)
    oc_and_kw = 'AND' if oc_gov_filtered else 'WHERE'

    decentral_sql = f"""
    SELECT COUNT(*) AS qty, COALESCE(SUM(valor_oc), 0) AS valor
    FROM (
        SELECT oc.NUMERO_OC, SUM(oc.valor_original_brl) AS valor_oc
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.CENTRALIZADO = 'DESCENTRALIZADO'
        AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
        AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
        AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
        GROUP BY oc.NUMERO_OC
        HAVING SUM(oc.valor_original_brl) > 30000
    ) sub
    """
    decentral = query(decentral_sql)

    # Total OCs descentralizadas emitidas no período (para o percentual do card)
    total_dec_sql = f"""
    SELECT COUNT(DISTINCT oc.NUMERO_OC) AS total
    FROM ordens_compra oc
    {w_oc_gov}
    {oc_and_kw} oc.CENTRALIZADO = 'DESCENTRALIZADO'
      AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
      AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
      AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
    """
    total_dec = query(total_dec_sql)

    # Blanket >180 dias (entity-only filters, no date — referência: acordo_dt_criacao)
    _bla_ent = []
    _bla_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if _bla_emp:
        _bla_ent.append(f"org_desc IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _bla_emp])})")
    _bla_grp = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if _bla_grp:
        _bla_ent.append(f"grupo_compras_oc IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _bla_grp])})")
    _bla_ent_and = 'AND ' + ' AND '.join(_bla_ent) if _bla_ent else ''
    blanket_old = query(f"""
    SELECT COUNT(*)::int AS qty, SUM(vl)::float AS valor
    FROM (
        SELECT numero_acordo, MAX(acordo_valor_total) AS vl
        FROM ordens_compra
        WHERE acordo_status = 'OPEN'
          AND numero_acordo IS NOT NULL AND numero_acordo != ''
          AND acordo_dt_criacao IS NOT NULL AND acordo_dt_criacao != ''
          AND (CURRENT_DATE - acordo_dt_criacao::date) > 180
          AND COALESCE(acordo_valor_liberado, 0) = 0
          {_bla_ent_and}
        GROUP BY numero_acordo
    ) sub
    """)

    r = result[0] if result else {}
    r['pos_fatura_qty'] = pos_result[0]['qty'] if pos_result else 0
    r['pos_fatura_val'] = pos_result[0]['val'] if pos_result else 0
    r['total_oc_faturadas_pgto'] = total_oc_pgto[0]['total'] if total_oc_pgto else 0
    r['decentral_qty'] = decentral[0]['qty'] if decentral else 0
    r['decentral_val'] = decentral[0]['valor'] if decentral else 0
    r['total_oc_decentral'] = total_dec[0]['total'] if total_dec else 0
    r['blanket_old_qty'] = blanket_old[0]['qty'] if blanket_old else 0
    r['blanket_old_val'] = blanket_old[0]['valor'] if blanket_old else 0
    return jsonify(r)


@app.route('/api/governance/deviation-impact')
def governance_deviation_impact():
    """Which deviation has largest impact."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    and_kw = 'AND' if clauses else 'WHERE'

    # Post-invoice: usa coluna oc_pos_fatura calculada no ETL com âncora em DATA_PAGAMENTO
    clauses_pf, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO')
    w_pf = _where(clauses_pf)
    and_pf = 'AND' if clauses_pf else 'WHERE'
    pos_sql = f"""SELECT COALESCE(SUM(VALOR_LIQUIDO_BRL), 0) AS val, COUNT(DISTINCT NUMERO_OC)::int AS qty
    FROM notas_ri
    {w_pf} {and_pf} OC_POS_FATURA = 'SIM' AND NUMERO_OC != 'Nota sem OC'"""
    # Emergency
    urg_sql = f"SELECT SUM(VALOR_LIQUIDO_BRL) AS val, COUNT(DISTINCT NUMERO_OC)::int AS qty FROM notas_ri {w} {and_kw} URGENTE = 'SIM'"
    # Without PO
    sem_sql = f"SELECT SUM(VALOR_LIQUIDO_BRL) AS val, COUNT(DISTINCT NOTA_FISCAL)::int AS qty FROM notas_ri {w} {and_kw} NUMERO_OC = 'Nota sem OC'"
    # Decentralized >30k (source: ordens_compra, filter by DATA_OC — alinhado com o Card e com a Tabela)
    oc_clauses_gov, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
    oc_gov_filtered = [c for c in oc_clauses_gov if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    _comp_vals = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _comp_vals:
        oc_gov_filtered.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})")
    w_oc_gov = _where(oc_gov_filtered)
    oc_and_kw = 'AND' if oc_gov_filtered else 'WHERE'
    dec_sql = f"""
    SELECT COALESCE(SUM(valor_oc), 0)::float AS val, COUNT(*)::int AS qty FROM (
        SELECT oc.NUMERO_OC, SUM(oc.valor_original_brl) AS valor_oc
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.CENTRALIZADO = 'DESCENTRALIZADO'
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
          AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
        GROUP BY oc.NUMERO_OC
        HAVING SUM(oc.valor_original_brl) > 30000
    ) sub
    """
    # Acordos OPEN >180 dias (mesma regra da aba Governança — referência: acordo_dt_criacao)
    bla_sql = """
    SELECT SUM(vl) AS val, COUNT(*)::int AS qty FROM (
        SELECT numero_acordo, MAX(acordo_valor_total) AS vl
        FROM ordens_compra
        WHERE acordo_status = 'OPEN'
          AND numero_acordo IS NOT NULL AND numero_acordo != ''
          AND acordo_dt_criacao IS NOT NULL AND acordo_dt_criacao != ''
          AND (CURRENT_DATE - acordo_dt_criacao::date) > 180
          AND COALESCE(acordo_valor_liberado, 0) = 0
        GROUP BY numero_acordo
    ) sub
    """
    # OCs abertas > 90 dias
    oc90_sql = """
    SELECT SUM(valor_original_brl) AS val, COUNT(DISTINCT numero_oc)::int AS qty
    FROM ordens_compra
    WHERE STATUS_FECHAMENTO = 'ABERTA' AND dias_aberto > 90
    """

    results = []
    for label, s, p in [
        ('OCs pós-fatura', pos_sql, []),
        ('OC emergencial', urg_sql, params),
        ('Notas sem OCs', sem_sql, params),
        ('OCs Descentr. >30K', dec_sql, []),
        ('OCs abertas >90 dias', oc90_sql, []),
        ('Acordos de Compra >180 dias', bla_sql, []),
    ]:
        r = query(s, p)
        results.append({'label': label, 'value': r[0]['val'] if r and r[0]['val'] else 0, 'qty': r[0].get('qty', 0) if r else 0})

    return jsonify(sorted(results, key=lambda x: (x.get('qty', 0) or 0, x.get('value', 0) or 0), reverse=True))


@app.route('/api/governance/by-buyer')
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
    oc_gov_filtered = [c for c in oc_clauses_gov if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    if _comp_vals:
        oc_gov_filtered.append(f"oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})")
    w_oc_gov = _where(oc_gov_filtered)
    oc_and_kw = 'AND' if oc_gov_filtered else 'WHERE'

    sql = f"""
    WITH oc_desc_30k AS (
        SELECT oc.NUMERO_OC
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.CENTRALIZADO = 'DESCENTRALIZADO'
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
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
            MAX(oc.AREA) AS area_oc,
            'OC Descentr. >30K' AS tipo_excecao,
            COUNT(DISTINCT oc.NUMERO_OC) AS qty,
            SUM(oc.valor_original_brl) AS valor
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k)
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
            '^[0-9]+\\\\s*-\\\\s*',
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
            '^[0-9]+\\\\s*-\\\\s*',
            ''
        ) AS area
    FROM buyer_exceptions be
    LEFT JOIN buyer_totals bt ON be.buyer = bt.buyer
    LEFT JOIN compradores_funcionais cf ON (
        (be.usuario IS NOT NULL AND cf.usuario_oracle IS NOT NULL AND LOWER(cf.usuario_oracle) = LOWER(be.usuario))
        OR (be.buyer IS NOT NULL AND cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(be.buyer))
    )
    ORDER BY be.valor DESC
    LIMIT 200
    """
    rows, err = query_debug(sql)
    if err:
        _log.error("BY-BUYER ERROR: %s", err)
    return jsonify(rows)


@app.route('/api/governance/exceptions-table')
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
        pf_base = [c for c in pf_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        _pf_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _pf_comp:
            pf_base.append(f"oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _pf_comp])})")
        pf_where_and = 'AND ' + ' AND '.join(pf_base) if pf_base else ''

        # Agrupado por OC: uma linha por NUMERO_OC, filtrado por DATA_PAGAMENTO
        sql = f"""
        WITH oc_pos AS (
            SELECT
                nf.NUMERO_OC,
                MIN(CASE WHEN nf.DT_NOTA ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}' THEN SUBSTRING(nf.DT_NOTA, 1, 10) ELSE NULL END) AS primeira_nf,
                MAX(CASE WHEN oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}' THEN SUBSTRING(oc.DT_APROVACAO, 1, 10) ELSE NULL END) AS dt_aprovacao,
                MAX(COALESCE(oc.NOME_USUARIO, 'Não informado')) AS comprador,
                MAX(oc.USUARIO) AS usuario,
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
                WHEN p.dt_aprovacao ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}' AND p.primeira_nf ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
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
                '^[0-9]+\\\\s*-\\\\s*',
                ''
            ) AS depart_comprador,
            p.solicitante,
            REGEXP_REPLACE(
                COALESCE(p.area_oc, ''),
                '^[0-9]+\\\\s*-\\\\s*',
                ''
            ) AS depart_solicitante,
            p.fornecedor,
            p.net_spend
        FROM oc_pos p
        LEFT JOIN compradores_funcionais cf ON (
            (p.usuario IS NOT NULL AND cf.usuario_oracle IS NOT NULL AND LOWER(cf.usuario_oracle) = LOWER(p.usuario))
            OR (p.comprador IS NOT NULL AND cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(p.comprador))
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
            oc90_parts.append(f"oc.grupo_compras_oc IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _oc90_grp])})")
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
                   '^[0-9]+\\\\s*-\\\\s*',
                   ''
               ) AS depart_comprador,
               COALESCE(oc.nome_requisitante, 'Não informado') AS solicitante,
               REGEXP_REPLACE(COALESCE(oc.area, ''), '^[0-9]+\\\\s*-\\\\s*', '') AS depart_solicitante,
               oc.valor_original_brl AS net_spend,
               oc.DATA_OC AS data_oc,
               oc.dias_aberto,
               oc.STATUS_FECHAMENTO AS status
        FROM ordens_compra oc
        LEFT JOIN compradores_funcionais cf ON (
            (oc.usuario IS NOT NULL AND cf.usuario_oracle IS NOT NULL AND LOWER(cf.usuario_oracle) = LOWER(oc.usuario))
            OR (oc.nome_usuario IS NOT NULL AND cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(oc.nome_usuario))
        )
        WHERE {oc90_where}
        ORDER BY oc.dias_aberto DESC
        LIMIT {per_page} OFFSET {offset}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [oc_90] ERROR: %s", err)
        return jsonify(rows)

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
            bla_parts.append(f"oc.grupo_compras_oc IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _bla_grp])})")
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
                   '^[0-9]+\\\\s*-\\\\s*',
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
            (oc.usuario IS NOT NULL AND cf.usuario_oracle IS NOT NULL AND LOWER(cf.usuario_oracle) = LOWER(oc.usuario))
            OR (oc.nome_usuario IS NOT NULL AND cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(oc.nome_usuario))
        )
        WHERE {bla_where}
        GROUP BY oc.numero_acordo
        ORDER BY (CURRENT_DATE - MAX(oc.acordo_dt_criacao)::date) DESC
        LIMIT {per_page} OFFSET {offset}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [blanket_old] ERROR: %s", err)
        return jsonify(rows)

    # ── OC Descentralizada >30k (source: ordens_compra, filter by DATA_OC) ──
    if exc_type == 'decentral':
        dec_oc_clauses, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
        dec_oc_base = [c for c in dec_oc_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        _dec_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _dec_comp:
            dec_oc_base.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _dec_comp])})")
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
                   '^[0-9]+\\\\s*-\\\\s*',
                   ''
               ) AS depart_comprador,
               MAX(COALESCE(oc.nome_requisitante, 'Não informado')) AS solicitante,
               REGEXP_REPLACE(MAX(COALESCE(oc.area, '')), '^[0-9]+\\\\s*-\\\\s*', '') AS depart_solicitante,
               MAX(oc.nome_fornecedor) AS fornecedor,
               MAX(oc.data_oc) AS data_oc,
               SUM(oc.valor_original_brl)::float AS net_spend
        FROM ordens_compra oc
        LEFT JOIN compradores_funcionais cf ON (
            (oc.usuario IS NOT NULL AND cf.usuario_oracle IS NOT NULL AND LOWER(cf.usuario_oracle) = LOWER(oc.usuario))
            OR (oc.nome_usuario IS NOT NULL AND cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(oc.nome_usuario))
        )
        WHERE oc.CENTRALIZADO = 'DESCENTRALIZADO'
          AND oc.numero_oc IS NOT NULL AND oc.numero_oc != ''
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
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
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [sem_oc] ERROR: %s", err)
        return jsonify(rows)

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
        exc_comp_and = ''

    # Build decentral CTE for type=all
    oc_pos_cte = f"""WITH oc_desc_30k AS (
        SELECT oc.NUMERO_OC
        FROM ordens_compra oc
        WHERE oc.CENTRALIZADO = 'DESCENTRALIZADO' AND oc.NUMERO_OC IS NOT NULL AND oc.NUMERO_OC != ''
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
          AND (oc.nome_usuario IS NULL OR UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
        GROUP BY oc.NUMERO_OC
        HAVING SUM(oc.valor_original_brl) > 30000
    )"""

    if exc_type == 'urgente':
        type_filter = "AND nf.URGENTE = 'SIM'"
        tipo_expr = "'OC emergencial'"
    else:
        # type == 'all'
        type_filter = f"AND ((nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC'{pgto_d_and}) OR (nf.URGENTE = 'SIM'{lancto_d_and}) OR (nf.NUMERO_OC = 'Nota sem OC'{lancto_d_and}) OR (nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k){lancto_d_and}))"
        tipo_expr = """
        CASE
            WHEN nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC' THEN 'OCs pós-fatura'
            WHEN nf.URGENTE = 'SIM' THEN 'OC emergencial'
            WHEN nf.NUMERO_OC = 'Nota sem OC' THEN 'Notas sem OCs'
            WHEN nf.CENTRALIZADO = 'DESCENTRALIZADO' THEN 'Descentralizada'
            ELSE 'Outro'
        END"""

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
            '^[0-9]+\\\\s*-\\\\s*',
            ''
        ) AS depart_comprador,
        COALESCE(oc.NOME_REQUISITANTE, 'Não informado') AS solicitante,
        REGEXP_REPLACE(
            COALESCE(oc.AREA, ''),
            '^[0-9]+\\\\s*-\\\\s*',
            ''
        ) AS depart_solicitante,
        nf.NOME_FORNECEDOR AS fornecedor,
        nf.VALOR_LIQUIDO_BRL AS net_spend,
        COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) AS data_fatura,
        oc.DATA_OC AS data_emissao_oc,
        oc.DT_APROVACAO AS data_oc,
        CASE
            WHEN oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}' 
                 AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
            THEN (SUBSTRING(oc.DT_APROVACAO, 1, 10)::date 
                  - SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date)
            ELSE NULL
        END AS dias_pos_fatura
    FROM notas_ri nf
    LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
    LEFT JOIN compradores_funcionais cf ON (
        (oc.usuario IS NOT NULL AND cf.usuario_oracle IS NOT NULL AND LOWER(cf.usuario_oracle) = LOWER(oc.usuario))
        OR (oc.nome_usuario IS NOT NULL AND cf.comprador_funcional IS NOT NULL AND UPPER(cf.comprador_funcional) = UPPER(oc.nome_usuario))
    )
    WHERE 1=1 {type_filter} {exc_and} {exc_comp_and}
    ORDER BY nf.VALOR_LIQUIDO_BRL DESC
    LIMIT {per_page} OFFSET {offset}
    """
    rows, err = query_debug(sql)
    if err:
        _log.error("EXCEPTIONS-TABLE [%s] ERROR: %s", exc_type, err)
    return jsonify(rows)'''


with open('src/app/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix _EXCL_COMPRAS_OCS definition
excl_compras_pattern = re.compile(r'_EXCL_COMPRAS_OCS = """[\s\S]*?"""', re.MULTILINE)
new_excl_compras = '''_EXCL_COMPRAS_OCS = """
    SELECT DISTINCT oc_x.numero_oc
    FROM ordens_compra oc_x
    WHERE oc_x.numero_oc IS NOT NULL AND oc_x.numero_oc != ''
      AND (
          LOWER(oc_x.usuario) IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
          OR (oc_x.nome_usuario IS NOT NULL AND UPPER(oc_x.nome_usuario) IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL))
      )
"""'''
content = excl_compras_pattern.sub(new_excl_compras, content)

# Replace entire governance block from @app.route('/api/governance/kpis') to @app.route('/api/reports/data')
idx_kpis = content.find("@app.route('/api/governance/kpis')")
idx_reports = content.find("@app.route('/api/reports/data')")

if idx_kpis == -1 or idx_reports == -1:
    print(f"Error finding markers: idx_kpis={idx_kpis}, idx_reports={idx_reports}")
    sys.exit(1)

content = content[:idx_kpis] + clean_governance_block + "\n\n\n" + content[idx_reports:]

# Fix reports/data columns
# Replace phantom cols in reports/data
old_notas_cols = 'comprador AS COMPRADOR, departamento_comprador AS DEPARTAMENTO_COMPRADOR'
new_notas_cols = 'NULL AS COMPRADOR, NULL AS DEPARTAMENTO_COMPRADOR'
content = content.replace(old_notas_cols, new_notas_cols)

old_ordens_comprador = 'COALESCE(comprador, comprador_funcional) AS COMPRADOR,\n                  departamento_comprador AS DEPARTAMENTO_COMPRADOR,'
new_ordens_comprador = 'nome_usuario AS COMPRADOR,\n                  area AS DEPARTAMENTO_COMPRADOR,'
content = content.replace(old_ordens_comprador, new_ordens_comprador)

old_ordens_req = 'departamento_requisitante AS DEPARTAMENTO_REQUISITANTE,'
new_ordens_req = 'area AS DEPARTAMENTO_REQUISITANTE,'
content = content.replace(old_ordens_req, new_ordens_req)

old_req_cols = 'departamento_requisitante AS DEPARTAMENTO_REQUISITANTE, DESCRICAO_REQ, NUMERO_OC, DT_CRIACAO, DT_APROVACAO, VALOR_REQUISICAO, STATUS, STATUS_ORDEM, user_requisicao AS USER_REQUISICAO, email_requisitante AS EMAIL_REQUISITANTE, user_aprovador AS USER_APROVADOR, nome_aprovador AS NOME_APROVADOR, comprador_sugerido AS COMPRADOR_SUGERIDO, departamento_comprador AS DEPARTAMENTO_COMPRADOR'
new_req_cols = 'NULL AS DEPARTAMENTO_REQUISITANTE, DESCRICAO_REQ, NUMERO_OC, DT_CRIACAO, DT_APROVACAO, VALOR_REQUISICAO, STATUS, STATUS_ORDEM, user_requisicao AS USER_REQUISICAO, email_requisitante AS EMAIL_REQUISITANTE, user_aprovador AS USER_APROVADOR, nome_aprovador AS NOME_APROVADOR, NULL AS COMPRADOR_SUGERIDO, NULL AS DEPARTAMENTO_COMPRADOR'
content = content.replace(old_req_cols, new_req_cols)

with open('src/app/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("src/app/app.py updated cleanly!")
