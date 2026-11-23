import py_compile

with open("scratch/app_from_workspace.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# 1. Dedicated urgente block lines:
urgente_code = '''
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

        sql = f"""
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
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [urgente] ERROR: %s", err)
        return jsonify(rows)
'''

# Find positions
sem_oc_end = None
for i, l in enumerate(lines):
    if "EXCEPTIONS-TABLE [sem_oc] ERROR" in l:
        sem_oc_end = i + 2
        break

urg_start = None
urg_end = None
for i, l in enumerate(lines):
    if "# For emergencial: override date filter to use oc.DATA_OC" in l:
        urg_start = i
    if urg_start is not None and "exc_comp_and = ''" in l:
        urg_end = i + 1
        break

# Reconstruct file lines:
new_lines = (
    lines[:sem_oc_end]
    + [urgente_code + "\n"]
    + lines[sem_oc_end:urg_start]
    + ["    # Date and entity filters for type=all\n"]
    + lines[urg_end:]
)

with open("src/app/app.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Verifying syntax...")
py_compile.compile("src/app/app.py", doraise=True)
print("[SUCCESS] src/app/app.py compiled successfully without syntax errors!")
