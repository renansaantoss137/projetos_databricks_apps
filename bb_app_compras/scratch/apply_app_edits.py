import re
import shutil
import py_compile

APP_PATH = 'src/app/app.py'
BACKUP_PATH = 'src/app/app.py.bak_before_sem_oc'

shutil.copy2(APP_PATH, BACKUP_PATH)
print(f"Backup created at {BACKUP_PATH}")

with open(APP_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add fornecedores_sem_oc to LOOKUP_CONFIG
sem_oc_lookup = '''    "fornecedores_sem_oc": {
        "title": "Fornecedores sem OC",
        "description": "Fornecedores permitidos faturar sem PO (sem atuação de Compras)",
        "table_name": "fornecedores_sem_oc",
        "csv_filename": "fornecedores_sem_oc.csv",
        "primary_key": "cod_fornecedor_oracle",
        "columns": [
            {"key": "cod_fornecedor_oracle", "label": "Cód. Fornecedor (Oracle)", "required": True, "type": "text"},
            {"key": "nome_fornecedor_oracle", "label": "Nome Fornecedor (Oracle)", "required": True, "type": "text"},
            {"key": "produto_servico", "label": "Produto / Serviço", "required": False, "type": "text"},
            {"key": "area", "label": "Área", "required": False, "type": "text"},
            {"key": "justificativa", "label": "Justificativa", "required": False, "type": "text"},
            {"key": "data_registro", "label": "Data Registro", "required": False, "type": "text"}
        ]
    },
'''

if '"fornecedores_sem_oc"' not in content:
    target = '"compradores_funcionais": {'
    assert target in content, "Could not find compradores_funcionais in LOOKUP_CONFIG"
    content = content.replace(target, sem_oc_lookup + '    ' + target, 1)
    print("1. Added fornecedores_sem_oc to LOOKUP_CONFIG")

# 2. Update _read_local_csv_fallback header normalization
old_norm = '''        if "fornecedor" in norm and "cod" in norm:
            norm = "cod_fornecedor_oracle"
        elif "fornecedor" in norm and "nome" in norm:
            norm = "nome_fornecedor_oracle"'''

new_norm = '''        if "fornecedor" in norm and ("cod" in norm or "num" in norm or "codigo" in norm):
            norm = "cod_fornecedor_oracle"
        elif "fornecedor" in norm and ("nome" in norm or "razao" in norm or norm == "fornecedor"):
            norm = "nome_fornecedor_oracle"'''

assert old_norm in content, "Could not find header normalization in _read_local_csv_fallback"
content = content.replace(old_norm, new_norm, 1)
print("2. Updated header normalization in _read_local_csv_fallback")

# 3. Add recalculation in _recalc_lakebase_flags
recalc_sem_oc = '''        elif table_key == "fornecedores_sem_oc":
            _log.info("Recalculating is_fornecedor_sem_oc in Lakebase...")
            cur.execute(f"""
                UPDATE "{_PG_SCHEMA}"."notas_ri"
                SET is_fornecedor_sem_oc = CASE 
                    WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_sem_oc") THEN 'SEM OC'
                    ELSE 'COM ATUAÇÃO'
                END
                WHERE is_fornecedor_sem_oc IS DISTINCT FROM (
                    CASE WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_sem_oc") THEN 'SEM OC' ELSE 'COM ATUAÇÃO' END
                )
            """)
            cur.execute(f"""
                UPDATE "{_PG_SCHEMA}"."ordens_compra"
                SET is_fornecedor_sem_oc = CASE 
                    WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_sem_oc") THEN 'SEM OC'
                    ELSE 'COM ATUAÇÃO'
                END
                WHERE is_fornecedor_sem_oc IS DISTINCT FROM (
                    CASE WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_sem_oc") THEN 'SEM OC' ELSE 'COM ATUAÇÃO' END
                )
            """)
'''

target_recalc = '        elif table_key == "fornecedores_nao_negociaveis":'
assert target_recalc in content, "Could not find table_key == fornecedores_nao_negociaveis in _recalc_lakebase_flags"
content = content.replace(target_recalc, recalc_sem_oc + target_recalc, 1)
print("3. Added recalculation for fornecedores_sem_oc in _recalc_lakebase_flags")

# 4. Trigger recalculation in lookups_save
old_trigger = 'if pg_ok and table_key in ["fornecedores_especiais", "fornecedores_nao_negociaveis"]:'
new_trigger = 'if pg_ok and table_key in ["fornecedores_especiais", "fornecedores_nao_negociaveis", "fornecedores_sem_oc"]:'
assert old_trigger in content, "Could not find recalculation trigger in lookups_save"
content = content.replace(old_trigger, new_trigger, 1)
print("4. Updated trigger in lookups_save to include fornecedores_sem_oc")

# 5. Add filter clauses in build_filter_clauses and _cascading_where
# 5a. First filter clause builder (around line 885)
old_clause_1 = '''    is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"{p}IS_FORNECEDOR_NAO_NEGOCIAVEL IN ({vals})")'''

new_clause_1 = '''    is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"{p}IS_FORNECEDOR_NAO_NEGOCIAVEL IN ({vals})")
    is_forn_sem_oc = [v.strip() for v in args.getlist('is_fornecedor_sem_oc') if v.strip()]
    if is_forn_sem_oc:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_sem_oc])
        clauses.append(f"{p}IS_FORNECEDOR_SEM_OC IN ({vals})")'''

assert old_clause_1 in content, "Could not find old_clause_1"
content = content.replace(old_clause_1, new_clause_1, 1)
print("5a. Added is_fornecedor_sem_oc to first filter clause builder")

# 5b. Second filter clause builder (around line 1135)
old_clause_2 = '''    is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")'''

new_clause_2 = '''    is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")
    is_forn_sem_oc = [v.strip() for v in args.getlist('is_fornecedor_sem_oc') if v.strip()]
    if is_forn_sem_oc:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_sem_oc])
        clauses.append(f"is_fornecedor_sem_oc IN ({vals})")'''

assert old_clause_2 in content, "Could not find old_clause_2"
content = content.replace(old_clause_2, new_clause_2, 1)
print("5b. Added is_fornecedor_sem_oc to second filter clause builder")

# 5c. Cascading where clause builder (around line 1243)
old_clause_3 = '''    if exclude_field != 'is_fornecedor_nao_negociavel':
        is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
        if is_forn_nn:
            vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
            clauses.append(f"IS_FORNECEDOR_NAO_NEGOCIAVEL IN ({vals})")'''

new_clause_3 = '''    if exclude_field != 'is_fornecedor_nao_negociavel':
        is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
        if is_forn_nn:
            vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
            clauses.append(f"IS_FORNECEDOR_NAO_NEGOCIAVEL IN ({vals})")
    if exclude_field != 'is_fornecedor_sem_oc':
        is_forn_sem_oc = [v.strip() for v in args.getlist('is_fornecedor_sem_oc') if v.strip()]
        if is_forn_sem_oc:
            vals = ','.join([f"'{_esc(v)}'" for v in is_forn_sem_oc])
            clauses.append(f"IS_FORNECEDOR_SEM_OC IN ({vals})")'''

assert old_clause_3 in content, "Could not find old_clause_3"
content = content.replace(old_clause_3, new_clause_3, 1)
print("5c. Added is_fornecedor_sem_oc to cascading where builder")

# 5d. Metric endpoints (5 occurrences of request.args.getlist('is_fornecedor_nao_negociavel'))
old_req_nn = '''    is_forn_nn = [v.strip() for v in request.args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")'''

new_req_nn = '''    is_forn_nn = [v.strip() for v in request.args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")
    is_forn_sem_oc = [v.strip() for v in request.args.getlist('is_fornecedor_sem_oc') if v.strip()]
    if is_forn_sem_oc:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_sem_oc])
        clauses.append(f"is_fornecedor_sem_oc IN ({vals})")'''

count_req = content.count(old_req_nn)
print(f"5d. Found {count_req} occurrences of metric endpoint filter")
content = content.replace(old_req_nn, new_req_nn)
print(f"5d. Updated all {count_req} metric endpoints with is_fornecedor_sem_oc")

# 6. Add to relatorios query (line 5187)
old_rel_query = '''            COALESCE(nf.IS_FORNECEDOR_ESPECIAL, oc.is_fornecedor_especial) AS "IS_FORNECEDOR_ESPECIAL",
            COALESCE(nf.IS_FORNECEDOR_NAO_NEGOCIAVEL, oc.is_fornecedor_nao_negociavel) AS "IS_FORNECEDOR_NAO_NEGOCIAVEL",'''

new_rel_query = '''            COALESCE(nf.IS_FORNECEDOR_ESPECIAL, oc.is_fornecedor_especial) AS "IS_FORNECEDOR_ESPECIAL",
            COALESCE(nf.IS_FORNECEDOR_NAO_NEGOCIAVEL, oc.is_fornecedor_nao_negociavel) AS "IS_FORNECEDOR_NAO_NEGOCIAVEL",
            COALESCE(nf.IS_FORNECEDOR_SEM_OC, oc.is_fornecedor_sem_oc) AS "IS_FORNECEDOR_SEM_OC",'''

assert old_rel_query in content, "Could not find old_rel_query"
content = content.replace(old_rel_query, new_rel_query, 1)
print("6. Added IS_FORNECEDOR_SEM_OC to relatorios SQL SELECT")

# 7. Add to REPORT_COLUMNS_DEFINITION (line 5462)
old_col_def = '''            ('COALESCE(nf.IS_FORNECEDOR_ESPECIAL, oc.is_fornecedor_especial)', 'Forn. Especial', 'text', 'IS_FORNECEDOR_ESPECIAL'),
            ('COALESCE(nf.IS_FORNECEDOR_NAO_NEGOCIAVEL, oc.is_fornecedor_nao_negociavel)', 'Negociabilidade', 'text', 'IS_FORNECEDOR_NAO_NEGOCIAVEL'),'''

new_col_def = '''            ('COALESCE(nf.IS_FORNECEDOR_ESPECIAL, oc.is_fornecedor_especial)', 'Forn. Especial', 'text', 'IS_FORNECEDOR_ESPECIAL'),
            ('COALESCE(nf.IS_FORNECEDOR_NAO_NEGOCIAVEL, oc.is_fornecedor_nao_negociavel)', 'Negociabilidade', 'text', 'IS_FORNECEDOR_NAO_NEGOCIAVEL'),
            ('COALESCE(nf.IS_FORNECEDOR_SEM_OC, oc.is_fornecedor_sem_oc)', 'Forn. sem OC / Atuação', 'text', 'IS_FORNECEDOR_SEM_OC'),'''

assert old_col_def in content, "Could not find old_col_def"
content = content.replace(old_col_def, new_col_def, 1)
print("7. Added IS_FORNECEDOR_SEM_OC to REPORT_COLUMNS_DEFINITION")

with open(APP_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Saved modified {APP_PATH}")
py_compile.compile(APP_PATH, doraise=True)
print("✓ py_compile succeeded! No syntax errors in app.py.")
