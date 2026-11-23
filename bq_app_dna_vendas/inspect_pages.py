import json
import glob
import os

base_dir = r'..\DNA DE VENDAS_BQ.Report\definition\pages'
try:
    with open(os.path.join(base_dir, 'pages.json'), 'r', encoding='utf-8') as f:
        pages_meta = json.load(f)
    print('pages.json:', pages_meta)
except Exception as e:
    print('Error reading pages.json:', e)

for p in glob.glob(os.path.join(base_dir, '*', 'page.json')):
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        folder = os.path.basename(os.path.dirname(p))
        name = data.get('name')
        disp = data.get('displayName')
        vis = data.get('visibility', 'Visible')
        print(f"Folder: {folder} | Name: {name} | DisplayName: {disp} | Visibility: {vis}")
    except Exception as e:
        print(f"Error reading {p}: {e}")
