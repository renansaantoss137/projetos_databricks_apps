import re

with open('src/dados/compras_360_lakebase_etl.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Extract DDL columns
ddl_match = re.search(r'CREATE TABLE IF NOT EXISTS {schema}\.ordens_compra \((.*?)\)\s*"""', text, re.DOTALL)
ddl_cols = []
for line in ddl_match.group(1).strip().split('\n'):
    line = line.strip().rstrip(',')
    if line:
        col = line.split()[0].lower()
        ddl_cols.append(col)

# Extract SELECT columns from df_ordens
select_match = re.search(r'df_ordens = spark\.sql\("""\s*SELECT(.*?)\s*FROM vw_ordens_compra', text, re.DOTALL)
select_cols = []
for line in select_match.group(1).strip().split('\n'):
    line = line.strip().rstrip(',')
    if ' AS ' in line.upper():
        parts = re.split(r'\s+AS\s+', line, flags=re.IGNORECASE)
        col = parts[-1].strip().lower()
        select_cols.append(col)

print(f"DDL columns count: {len(ddl_cols)}")
print(f"SELECT columns count: {len(select_cols)}")

mismatch = False
for i in range(max(len(ddl_cols), len(select_cols))):
    d = ddl_cols[i] if i < len(ddl_cols) else "MISSING"
    s = select_cols[i] if i < len(select_cols) else "MISSING"
    if d != s:
        print(f"MISMATCH at position {i+1}: DDL has '{d}', SELECT has '{s}'")
        mismatch = True

if not mismatch and len(ddl_cols) == len(select_cols):
    print("ALL COLUMNS MATCH 100% IN ORDER!")
