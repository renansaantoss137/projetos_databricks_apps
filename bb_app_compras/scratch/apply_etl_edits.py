import shutil
import py_compile

ETL_PATH = 'src/dados/compras_360_lakebase_etl.py'
BACKUP_PATH = 'src/dados/compras_360_lakebase_etl.py.bak_before_sem_oc'

shutil.copy2(ETL_PATH, BACKUP_PATH)
print(f"Backup created at {BACKUP_PATH}")

with open(ETL_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add CSV_FORNECEDORES_SEM_OC
old_csvs = '''CSV_FORNECEDORES_ESP = _resolve_csv("fornecedores_especiais.csv")
CSV_FORNECEDORES_NN = _resolve_csv("fornecedores_nao_negociaiveis.csv")'''

new_csvs = '''CSV_FORNECEDORES_ESP = _resolve_csv("fornecedores_especiais.csv")
CSV_FORNECEDORES_NN = _resolve_csv("fornecedores_nao_negociaiveis.csv")
CSV_FORNECEDORES_SEM_OC = _resolve_csv("fornecedores_sem_oc.csv")'''

assert old_csvs in content, "Could not find old_csvs in ETL"
content = content.replace(old_csvs, new_csvs, 1)
print("1. Added CSV_FORNECEDORES_SEM_OC")

# 2. Add is_fornecedor_sem_oc to DDL of notas_ri and ordens_compra
old_ddl_notas = '''        is_fornecedor_especial TEXT,
        is_fornecedor_nao_negociavel TEXT,'''

new_ddl_notas = '''        is_fornecedor_especial TEXT,
        is_fornecedor_nao_negociavel TEXT,
        is_fornecedor_sem_oc TEXT,'''

assert content.count(old_ddl_notas) == 2, f"Expected 2 occurrences of old_ddl_notas, got {content.count(old_ddl_notas)}"
content = content.replace(old_ddl_notas, new_ddl_notas)
print("2. Added is_fornecedor_sem_oc to DDL of notas_ri and ordens_compra")

# 3. Load lookup and register temp view
old_lookup_block = '''# --- 2. Fornecedores Não Negociáveis ---
pdf_forn_nn = load_lookup_csv(CSV_FORNECEDORES_NN, cols_forn)
pdf_forn_nn["COD_FORNECEDOR_ORACLE"] = pdf_forn_nn["COD_FORNECEDOR_ORACLE"].astype(str).str.strip()
pdf_forn_nn = pdf_forn_nn.drop_duplicates(subset=["COD_FORNECEDOR_ORACLE"])
print(f"✓ fornecedores_nao_negociaveis: {len(pdf_forn_nn)} registros")'''

new_lookup_block = '''# --- 2. Fornecedores Não Negociáveis ---
pdf_forn_nn = load_lookup_csv(CSV_FORNECEDORES_NN, cols_forn)
pdf_forn_nn["COD_FORNECEDOR_ORACLE"] = pdf_forn_nn["COD_FORNECEDOR_ORACLE"].astype(str).str.strip()
pdf_forn_nn = pdf_forn_nn.drop_duplicates(subset=["COD_FORNECEDOR_ORACLE"])
print(f"✓ fornecedores_nao_negociaveis: {len(pdf_forn_nn)} registros")

# --- 2b. Fornecedores sem OC (Permitidos faturar sem PO) ---
pdf_forn_sem_oc = load_lookup_csv(CSV_FORNECEDORES_SEM_OC, cols_forn)
pdf_forn_sem_oc["COD_FORNECEDOR_ORACLE"] = pdf_forn_sem_oc["COD_FORNECEDOR_ORACLE"].astype(str).str.strip()
pdf_forn_sem_oc = pdf_forn_sem_oc.drop_duplicates(subset=["COD_FORNECEDOR_ORACLE"])
print(f"✓ fornecedores_sem_oc: {len(pdf_forn_sem_oc)} registros")'''

assert old_lookup_block in content, "Could not find old_lookup_block"
content = content.replace(old_lookup_block, new_lookup_block, 1)

old_temp_views = '''spark.createDataFrame(pdf_forn_esp).createOrReplaceTempView("tv_fornecedores_especiais")
spark.createDataFrame(pdf_forn_nn).createOrReplaceTempView("tv_fornecedores_nao_negociaveis")'''

new_temp_views = '''spark.createDataFrame(pdf_forn_esp).createOrReplaceTempView("tv_fornecedores_especiais")
spark.createDataFrame(pdf_forn_nn).createOrReplaceTempView("tv_fornecedores_nao_negociaveis")
spark.createDataFrame(pdf_forn_sem_oc).createOrReplaceTempView("tv_fornecedores_sem_oc")'''

assert old_temp_views in content, "Could not find old_temp_views"
content = content.replace(old_temp_views, new_temp_views, 1)

old_bulk_staging = '''bulk_load_to_pg(pdf_forn_nn[["COD_FORNECEDOR_ORACLE", "NOME_FORNECEDOR_ORACLE", "PRODUTO_SERVICO", "AREA", "JUSTIFICATIVA", "DATA_REGISTRO"]], SCHEMA_STAGING, "fornecedores_nao_negociaveis", conn)
print(f"✓ {SCHEMA_STAGING}.fornecedores_nao_negociaveis carregada")'''

new_bulk_staging = '''bulk_load_to_pg(pdf_forn_nn[["COD_FORNECEDOR_ORACLE", "NOME_FORNECEDOR_ORACLE", "PRODUTO_SERVICO", "AREA", "JUSTIFICATIVA", "DATA_REGISTRO"]], SCHEMA_STAGING, "fornecedores_nao_negociaveis", conn)
print(f"✓ {SCHEMA_STAGING}.fornecedores_nao_negociaveis carregada")

bulk_load_to_pg(pdf_forn_sem_oc[["COD_FORNECEDOR_ORACLE", "NOME_FORNECEDOR_ORACLE", "PRODUTO_SERVICO", "AREA", "JUSTIFICATIVA", "DATA_REGISTRO"]], SCHEMA_STAGING, "fornecedores_sem_oc", conn)
print(f"✓ {SCHEMA_STAGING}.fornecedores_sem_oc carregada")'''

assert old_bulk_staging in content, "Could not find old_bulk_staging"
content = content.replace(old_bulk_staging, new_bulk_staging, 1)
print("3. Added lookup loading, temp view and staging load for fornecedores_sem_oc")

# 4. In df_notas query:
old_notas_flags = '''        CASE WHEN _supplier_number IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_especiais) THEN 'ESPECIAL' ELSE 'NÃO ESPECIAL' END AS is_fornecedor_especial,
        CASE WHEN _supplier_number IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_nao_negociaveis) THEN 'NÃO NEGOCIAVEL' ELSE 'NEGOCIAVEL' END AS is_fornecedor_nao_negociavel,'''

new_notas_flags = '''        CASE WHEN _supplier_number IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_especiais) THEN 'ESPECIAL' ELSE 'NÃO ESPECIAL' END AS is_fornecedor_especial,
        CASE WHEN _supplier_number IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_nao_negociaveis) THEN 'NÃO NEGOCIAVEL' ELSE 'NEGOCIAVEL' END AS is_fornecedor_nao_negociavel,
        CASE WHEN _supplier_number IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_sem_oc) THEN 'SEM OC' ELSE 'COM ATUAÇÃO' END AS is_fornecedor_sem_oc,'''

assert old_notas_flags in content, "Could not find old_notas_flags"
content = content.replace(old_notas_flags, new_notas_flags, 1)
print("4. Added is_fornecedor_sem_oc column expression to df_notas")

# 5. In df_ordens query:
old_ordens_flags = '''        CASE WHEN NUMERO_FORNECEDOR IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_especiais) THEN 'ESPECIAL' ELSE 'NÃO ESPECIAL' END AS is_fornecedor_especial,
        CASE WHEN NUMERO_FORNECEDOR IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_nao_negociaveis) THEN 'NÃO NEGOCIAVEL' ELSE 'NEGOCIAVEL' END AS is_fornecedor_nao_negociavel,'''

new_ordens_flags = '''        CASE WHEN NUMERO_FORNECEDOR IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_especiais) THEN 'ESPECIAL' ELSE 'NÃO ESPECIAL' END AS is_fornecedor_especial,
        CASE WHEN NUMERO_FORNECEDOR IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_nao_negociaveis) THEN 'NÃO NEGOCIAVEL' ELSE 'NEGOCIAVEL' END AS is_fornecedor_nao_negociavel,
        CASE WHEN NUMERO_FORNECEDOR IN (SELECT COD_FORNECEDOR_ORACLE FROM tv_fornecedores_sem_oc) THEN 'SEM OC' ELSE 'COM ATUAÇÃO' END AS is_fornecedor_sem_oc,'''

assert old_ordens_flags in content, "Could not find old_ordens_flags"
content = content.replace(old_ordens_flags, new_ordens_flags, 1)
print("5. Added is_fornecedor_sem_oc column expression to df_ordens")

with open(ETL_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Saved modified {ETL_PATH}")
py_compile.compile(ETL_PATH, doraise=True)
print("OK! py_compile succeeded with zero syntax errors.")
