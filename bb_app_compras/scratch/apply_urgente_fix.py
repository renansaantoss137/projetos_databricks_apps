with open("scratch/app_from_workspace.py", "r", encoding="utf-8") as f:
    content = f.read()

# Normalize line endings to \n
content = content.replace("\r\n", "\n")

sem_oc_block = """    # ── Notas sem OCs (source: notas_ri, filter by DATA_LANCAMENTO) ──
    if exc_type == 'sem_oc':
        sem_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', table_prefix='nf')
        sem_base = [c for c in sem_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        sem_w = _where(sem_base)
        and_kw = 'AND' if sem_base else 'WHERE'

        sql = f\"\"\"
        SELECT
            'Notas sem OCs' AS tipo_excecao,
            NULL AS "NUMERO_OC",
            nf.NOTA_FISCAL AS "NOTA_FISCAL",
            NULL AS comprador,
            NULL AS depart_comprador,
            NULL AS solicitante,
            NULL AS depart_solicitante,
            MAX(nf.NOME_FORNECEDOR) AS fornecedor,
            SUM(nf.VALOR_LIQUIDO_BRL) AS net_spend,
            MAX(nf.DATA_LANCAMENTO) AS data_fatura,
            NULL AS data_emissao_oc,
            NULL AS data_oc,
            NULL AS dias_pos_fatura
        FROM notas_ri nf
        {sem_w} {and_kw} nf.NUMERO_OC = 'Nota sem OC'
        GROUP BY nf.NOTA_FISCAL
        ORDER BY net_spend DESC
        {limit_clause}
        \"\"\"
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [sem_oc] ERROR: %s", err)
        return jsonify(rows)"""

urgente_block = """

    # ── OC Emergencial (source: notas_ri, filter by DATA_LANCAMENTO alinhado ao KPI) ──
    if exc_type == 'urgente':
        urg_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', table_prefix='nf')
        urg_base = [c for c in urg_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        _urg_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _urg_comp:
            _c_list = ','.join([chr(39)+_esc(v)+chr(39) for v in _urg_comp])
            urg_base.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO) IN ({_c_list})")
        urg_w = _where(urg_base)
        and_kw = 'AND' if urg_base else 'WHERE'

        sql = f\"\"\"
        WITH urg_raw AS (
            SELECT
                'OC emergencial' AS tipo_excecao,
                nf.NUMERO_OC AS "NUMERO_OC",
                MAX(COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não informado')) AS comprador,
                MAX(COALESCE(NULLIF(oc.usuario_comprador, ''), oc.usuario)) AS usuario,
                MAX(oc.DEPARTAMENTO_COMPRADOR) AS dept_oc,
                MAX(COALESCE(oc.NOME_REQUISITANTE, 'Não informado')) AS solicitante,
                REGEXP_REPLACE(
                    COALESCE(MAX(NULLIF(oc.DEPARTAMENTO_REQUISITANTE, '')), MAX(NULLIF(oc.area, '')), '--'),
                    '^[0-9]+\\\\s*-\\\\s*',
                    ''
                ) AS depart_solicitante,
                MAX(nf.NOME_FORNECEDOR) AS fornecedor,
                SUM(nf.VALOR_LIQUIDO_BRL)::float AS net_spend,
                MAX(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO)) AS data_fatura,
                MAX(COALESCE(oc.DATA_OC, oc.DT_APROVACAO)) AS data_emissao_oc,
                MAX(oc.DT_APROVACAO) AS data_oc
            FROM notas_ri nf
            LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
            {urg_w} {and_kw} nf.URGENTE = 'SIM'
              AND nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != '' AND nf.NUMERO_OC != 'Nota sem OC'
            GROUP BY nf.NUMERO_OC
        ),
        buyers_map AS (
            SELECT
                db.comprador,
                db.usuario,
                COALESCE(
                    CASE 
                        WHEN colab.area IS NOT NULL AND colab.nm_unidade IS NOT NULL AND colab.nm_unidade != '' 
                        THEN colab.area || ' - ' || colab.nm_unidade
                        ELSE colab.area 
                    END,
                    CASE 
                        WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                        THEN cf.area || ' - ' || cf.unidade
                        ELSE cf.area 
                    END
                ) AS dept_resolved
            FROM (SELECT DISTINCT comprador, usuario FROM urg_raw) db
            LEFT JOIN LATERAL (
                SELECT area, nm_unidade
                FROM colaboradores
                WHERE (matricula IS NOT NULL AND matricula = db.usuario)
                   OR (id_colaborador IS NOT NULL AND id_colaborador = db.usuario)
                   OR (nome_completo IS NOT NULL AND UPPER(nome_completo) = UPPER(db.comprador))
                   OR (UPPER(nome_completo) LIKE UPPER(db.comprador) || '%')
                LIMIT 1
            ) colab ON true
            LEFT JOIN LATERAL (
                SELECT area, unidade
                FROM compradores_funcionais
                WHERE (usuario_oracle IS NOT NULL AND LOWER(usuario_oracle) = LOWER(db.usuario))
                   OR (comprador_funcional IS NOT NULL AND UPPER(comprador_funcional) = UPPER(db.comprador))
                LIMIT 1
            ) cf ON true
        )
        SELECT
            ur.tipo_excecao,
            ur."NUMERO_OC",
            ur.comprador,
            REGEXP_REPLACE(
                COALESCE(bm.dept_resolved, NULLIF(ur.dept_oc, ''), 'Não informado'),
                '^[0-9]+\\\\s*-\\\\s*',
                ''
            ) AS depart_comprador,
            ur.solicitante,
            ur.depart_solicitante,
            ur.fornecedor,
            ur.net_spend,
            ur.data_fatura,
            ur.data_emissao_oc,
            ur.data_oc
        FROM urg_raw ur
        LEFT JOIN buyers_map bm 
          ON ur.comprador = bm.comprador 
         AND (ur.usuario = bm.usuario OR (ur.usuario IS NULL AND bm.usuario IS NULL))
        ORDER BY ur.net_spend DESC
        {limit_clause}
        \"\"\"
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [urgente] ERROR: %s", err)
        return jsonify(rows)"""

old_urg_override = """    # For emergencial: override date filter to use oc.DATA_OC
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
            urg_parts.append(f"nf.NOME_FORNECEDOR IN ({','.join([chr(39)+_esc(f_)+chr(39) for e in _urg_frn])})")
        _urg_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _urg_comp:
            urg_parts.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO) IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _urg_comp])})")
        exc_and = ('AND ' + ' AND '.join(urg_parts)) if urg_parts else ''
        exc_comp_and = ''"""

old_urg_all_check = """    if exc_type == 'urgente':
        type_filter = "AND nf.URGENTE = 'SIM'"
        tipo_expr = "'OC emergencial'"
    else:
        # type == 'all'
        type_filter = f\"AND ((nf.NUMERO_OC != 'Nota sem OC' AND oc.DT_APROVACAO ~ '^[0-9]{{{{4}}}}-[0-9]{{{{2}}}}-[0-9]{{{{2}}}}' AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{{{4}}}}-[0-9]{{{{2}}}}-[0-9]{{{{2}}}}' AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'{pgto_d_and}) OR (nf.URGENTE = 'SIM'{lancto_d_and}) OR (nf.NUMERO_OC = 'Nota sem OC'{lancto_d_and}) OR (nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k){lancto_d_and}))\""""

new_urg_all_check = """    # type == 'all'
    type_filter = f\"AND ((nf.NUMERO_OC != 'Nota sem OC' AND oc.DT_APROVACAO ~ '^[0-9]{{{{4}}}}-[0-9]{{{{2}}}}-[0-9]{{{{2}}}}' AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{{{4}}}}-[0-9]{{{{2}}}}-[0-9]{{{{2}}}}' AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'{pgto_d_and}) OR (nf.URGENTE = 'SIM'{lancto_d_and}) OR (nf.NUMERO_OC = 'Nota sem OC'{lancto_d_and}) OR (nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k){lancto_d_and}))\""""

assert sem_oc_block in content, "sem_oc_block not found in content!"
assert old_urg_override in content, "old_urg_override not found in content!"
assert old_urg_all_check in content, "old_urg_all_check not found in content!"

content = content.replace(sem_oc_block, sem_oc_block + urgente_block)
content = content.replace(old_urg_override, "    # Date and entity filters for type=all")
content = content.replace(old_urg_all_check, new_urg_all_check)

with open("src/app/app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("[SUCCESS] src/app/app.py updated cleanly and accurately!")
