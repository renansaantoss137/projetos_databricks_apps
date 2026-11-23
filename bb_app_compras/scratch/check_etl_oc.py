with open('src/dados/compras_360_lakebase_etl.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if 'vw_ordens_compra' in l or 'df_oc' in l or 'insert into' in l.lower() and 'ordens' in l.lower():
        print(f'{i+1}: {l.strip()[:100]}'.encode('ascii', 'ignore').decode())
