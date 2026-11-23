import zipfile
import json

with zipfile.ZipFile('DNA DE VENDAS_BQ.vpax') as z:
    with z.open('Model.bim') as f:
        model = json.load(f)

m = model.get('model', {})

print("="*60)
print("PARAMETERS / SHARED EXPRESSIONS:")
print("="*60)
for e in m.get('expressions', []):
    print(f"Name: {e.get('name')}")
    lines = e.get('expression', [])
    if isinstance(lines, list):
        print('\n'.join(lines))
    else:
        print(lines)
    print("-"*40)

print("\n" + "="*60)
print("PHYSICAL TABLES POWER QUERY M:")
print("="*60)
for t in m.get('tables', []):
    name = t.get('name')
    for p in t.get('partitions', []):
        src = p.get('source', {})
        if src.get('type') == 'm':
            print(f"\n>>> TABLE: {name} <<<")
            lines = src.get('expression', [])
            if isinstance(lines, list):
                print('\n'.join(lines))
            else:
                print(lines)
            print("-"*40)
