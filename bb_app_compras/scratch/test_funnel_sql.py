import sys
from werkzeug.datastructures import MultiDict

def _esc(val):
    return str(val).replace("'", "''")

with open('src/app/app.py', 'r', encoding='utf-8') as f:
    text = f.read()

idx_start = text.find('def _parse_filters(')
idx_end = text.find('def _where(', idx_start)
parse_filters_code = text[idx_start:idx_end]
exec(parse_filters_code, globals())

# Test query params sent by performance.html:
args = MultiDict([
    ('empresa', 'BB'),
    ('empresa', 'BQ'),
    ('ano', '2026'),
    ('mes', '10'),
    ('is_fornecedor_nao_negociavel', 'NEGOCIAVEL')
])

args_clean = args.copy()
if 'grupo_compras' in args_clean:
    del args_clean['grupo_compras']

oc_clauses, _ = _parse_filters(args_clean, date_col='DATA_OC', table_prefix='oc', empresa_col='ORG_DESC', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', fornecedor_col='nome_fornecedor')
oc_clauses.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'DIRETOS'")

print('Generated oc_clauses:')
for c in oc_clauses:
    print('  -', c)

oc_where = " AND ".join(oc_clauses) if oc_clauses else "1=1"
print('\noc_where:\n', oc_where)
