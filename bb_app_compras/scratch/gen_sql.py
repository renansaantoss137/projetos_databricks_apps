import sys
from werkzeug.datastructures import MultiDict

with open('src/app/app.py', 'r', encoding='utf-8') as f:
    text = f.read()

idx_start = text.find('def _parse_filters(')
idx_end = text.find('def _where(', idx_start)
parse_filters_code = text[idx_start:idx_end]
exec(parse_filters_code, globals())

def _esc(val):
    return str(val).replace("'", "''")

def get_sql(scope, args):
    args_clean = args.copy()
    if 'grupo_compras' in args_clean:
        del args_clean['grupo_compras']

    oc_clauses, _ = _parse_filters(args_clean, date_col='DATA_OC', table_prefix='oc', empresa_col='ORG_DESC', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', fornecedor_col='nome_fornecedor')

    if scope == 'diretos':
        oc_clauses.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'DIRETOS'")
    elif scope == 'indiretos':
        oc_clauses.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'INDIRETOS'")

    oc_where = " AND ".join(oc_clauses) if oc_clauses else "1=1"

    if scope == 'indiretos':
        f_empresa = [e.strip() for e in args.getlist('empresa') if e.strip()]
        f_ano = [a.strip() for a in args.getlist('ano') if a.strip()]
        f_mes = [m.strip() for m in args.getlist('mes') if m.strip()]
        f_dia = [d.strip() for d in args.getlist('dia') if d.strip()]
        f_dt_ini = args.get('dt_ini', '').strip()
        f_dt_fim = args.get('dt_fim', '').strip()

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

        req_st = [v.strip() for v in args.getlist('req_status') if v.strip()]
        if req_st:
            vals = ','.join([f"'{_esc(v)}'" for v in req_st])
            req_parts.append(f"req.status IN ({vals})")

        req_where = " AND ".join(req_parts)

        args_oc = args_clean.copy()
        for k in ('ano', 'mes', 'dia', 'dt_ini', 'dt_fim'):
            args_oc.pop(k, None)
        oc_clauses_cohort, _ = _parse_filters(args_oc, date_col='DATA_OC', table_prefix='oc', empresa_col='ORG_DESC', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', fornecedor_col='nome_fornecedor')
        oc_clauses_cohort.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'INDIRETOS'")
        oc_where_cohort = " AND ".join(oc_clauses_cohort) if oc_clauses_cohort else "1=1"

        # load SQL from funnel_func.py lines 90 to 280
        with open('scratch/funnel_func.py', 'r', encoding='utf-8') as f:
            ff_text = f.read()
        s1 = ff_text.find('WITH req_base AS (')
        s2 = ff_text.find('rows = query(sql)')
        sql_tmpl = ff_text[s1:s2].strip()
        if sql_tmpl.endswith('"""'):
            sql_tmpl = sql_tmpl[:-3].strip()
        sql = eval(f'f"""{sql_tmpl}"""')
        return sql
    else:
        with open('scratch/funnel_func.py', 'r', encoding='utf-8') as f:
            ff_text = f.read()
        s1 = ff_text.find('WITH oc_cohort AS (')
        s2 = ff_text.rfind('rows = query(sql)')
        sql_tmpl = ff_text[s1:s2].strip()
        if sql_tmpl.endswith('"""'):
            sql_tmpl = sql_tmpl[:-3].strip()
        sql = eval(f'f"""{sql_tmpl}"""')
        return sql

args = MultiDict([
    ('empresa', 'BB'),
    ('empresa', 'BQ'),
    ('ano', '2026'),
    ('mes', '10'),
    ('is_fornecedor_nao_negociavel', 'NEGOCIAVEL')
])

sql_dir = get_sql('diretos', args)
with open('scratch/sql_diretos.sql', 'w', encoding='utf-8') as f:
    f.write(sql_dir)

sql_ind = get_sql('indiretos', args)
with open('scratch/sql_indiretos.sql', 'w', encoding='utf-8') as f:
    f.write(sql_ind)

print("Generated sql_diretos.sql (len %d) and sql_indiretos.sql (len %d)" % (len(sql_dir), len(sql_ind)))
