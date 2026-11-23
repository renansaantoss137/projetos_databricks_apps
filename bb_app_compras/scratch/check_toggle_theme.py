import os, sys

sys.stdout.reconfigure(encoding='utf-8')
for fname in sorted(os.listdir('src/app')):
    if fname.endswith('.html') or fname.endswith('.js'):
        fpath = os.path.join('src/app', fname)
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if 'toggleTheme' in content:
                print(f"Found toggleTheme in {fname}")
            if 'data-theme' in content:
                print(f"Found data-theme in {fname}")
