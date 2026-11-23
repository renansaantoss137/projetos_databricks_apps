import zipfile
import json
import os

with zipfile.ZipFile('DNA DE VENDAS_BQ.vpax') as z:
    with z.open('Model.bim') as f:
        model = json.load(f)

m = model.get('model', {})
print("=== MODEL KEYS ===")
print(list(m.keys()))

print("\n=== EXPRESSIONS (POWER QUERY SHARED QUERIES) ===")
for e in m.get('expressions', []):
    name = e.get('name')
    kind = e.get('kind')
    expr = e.get('expression')
    if isinstance(expr, list):
        expr = '\n'.join(expr)
    print(f"--- Expression: {name} (kind: {kind}) ---")
    print(expr[:500] if expr else "None")

print("\n=== TABLES AND PARTITIONS ===")
for t in m.get('tables', []):
    name = t.get('name')
    print(f"\nTABLE: {name}")
    for p in t.get('partitions', []):
        p_name = p.get('name')
        source = p.get('source', {})
        print(f"  Partition: {p_name}, Source Keys: {list(source.keys())}")
        query = source.get('query') or source.get('expression')
        if isinstance(query, list):
            query = '\n'.join(query)
        if query:
            print("  Query/Expression snippet:")
            for line in str(query).split('\n')[:15]:
                print("   ", line)

print("\n=== RELATIONSHIPS ===")
for r in m.get('relationships', []):
    from_table = r.get('fromTable')
    from_col = r.get('fromColumn')
    to_table = r.get('toTable')
    to_col = r.get('toColumn')
    cross_filter = r.get('crossFilteringBehavior')
    is_active = r.get('isActive', True)
    print(f"- {from_table}[{from_col}] -> {to_table}[{to_col}] (Active: {is_active}, Filter: {cross_filter})")

print("\n=== MEASURES COUNT ===")
total_measures = 0
for t in m.get('tables', []):
    measures = t.get('measures', [])
    if measures:
        total_measures += len(measures)
        print(f"Table '{t.get('name')}': {len(measures)} measures")
print(f"Total measures across model: {total_measures}")
