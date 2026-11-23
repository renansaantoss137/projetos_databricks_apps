import os
import sys
sys.path.insert(0, 'src/app')
from app import query, _parse_filters
from werkzeug.datastructures import MultiDict

print("--- Testing Database Query for NF 42 ---")
# 1. Search for 42 in database
rows = query("SELECT nota_fiscal, nome_fornecedor, numero_oc, data_lancamento FROM notas_ri WHERE TRIM(nota_fiscal) = '42' OR nota_fiscal ILIKE '%42%' LIMIT 10")
print(f"Total found in raw query: {len(rows)}")
for r in rows:
    print(" ", r)

# 2. Test via _parse_filters with 'equals'
args_eq = MultiDict({'nota_fiscal': '42', 'nota_fiscal_op': 'equals'})
w_eq = _parse_filters(args_eq, 'nf.')
sql_eq = f"SELECT nf.nota_fiscal, nf.nome_fornecedor FROM notas_ri nf WHERE {' AND '.join(w_eq)} LIMIT 5"
rows_eq = query(sql_eq)
print(f"\n_parse_filters(equals, 42) returned: {len(rows_eq)} rows")
for r in rows_eq:
    print(" ", r)

# 3. Test via header filter hf_NOTA_FISCAL with 'equals'
args_hf = MultiDict({'hf_NOTA_FISCAL': '42', 'hf_NOTA_FISCAL_op': 'equals'})
w_hf = _parse_filters(args_hf, 'nf.')
sql_hf = f"SELECT nf.nota_fiscal, nf.nome_fornecedor FROM notas_ri nf WHERE {' AND '.join(w_hf)} LIMIT 5"
rows_hf = query(sql_hf)
print(f"\n_parse_filters(hf_NOTA_FISCAL=42, equals) returned: {len(rows_hf)} rows")
for r in rows_hf:
    print(" ", r)
