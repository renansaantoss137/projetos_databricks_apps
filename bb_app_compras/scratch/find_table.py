import os

app_dir = 'src/app'
for fname in os.listdir(app_dir):
    if fname.endswith('.html') or fname.endswith('.js'):
        fpath = os.path.join(app_dir, fname)
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if '_paSortClick' in content:
                print(f"Found _paSortClick in {fname}")
            if 'pa-sort-icon' in content:
                print(f"Found pa-sort-icon in {fname}")
