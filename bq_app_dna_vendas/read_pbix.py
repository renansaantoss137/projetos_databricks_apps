import zipfile
import json
import re

pbix = r'C:\Users\renan.ferreira\OneDrive - Corporativo Bimbo, S.A. de C. V\Área de Trabalho\Projetos Databricks Apps\bq_app_dna_vendas\DNA DE VENDAS_BQ-copia.pbix'

with zipfile.ZipFile(pbix, 'r') as z:
    layout_raw = z.read('Report/Layout')
    try:
        layout_str = layout_raw.decode('utf-16-le')
    except Exception:
        layout_str = layout_raw.decode('utf-8', errors='ignore')
    
    layout = json.loads(layout_str)
    print('=== REPORT SECTIONS (PAGES) ===')
    for s in layout.get('sections', []):
        print(f"Name: {s.get('name')} | Display: {s.get('displayName')} | Hidden: {s.get('isHidden', False)}")

    # Check config
    config_raw = layout.get('config')
    if config_raw:
        config = json.loads(config_raw)
        print('\n=== CONFIG KEYS ===')
        print(list(config.keys()))
        if 'modelExtensions' in config:
            print('Model extensions found!')
            print(json.dumps(config['modelExtensions'], indent=2)[:500])

    # Check DataModel strings (tables, measures, SQL queries, M expressions)
    dm = z.read('DataModel')
    print(f"\nDataModel total bytes: {len(dm)}")
