import zipfile
import json

with zipfile.ZipFile('DNA DE VENDAS_BQ.vpax') as z:
    with z.open('DaxVpaView.json') as f:
        vpa = json.load(f)

print("=== TABLES IN VPAX VIEW ===")
for t in vpa.get('Tables', []):
    print(f"Table: {t.get('TableName')} | Rows: {t.get('RowsCount')} | Columns: {len(t.get('Columns', []))}")
