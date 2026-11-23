import os, sys

sys.stdout.reconfigure(encoding='utf-8')
with open('src/app/styles.css', 'r', encoding='utf-8', errors='ignore') as f:
    for i, line in enumerate(f):
        if 'lang-' in line:
            print(f"styles.css:{i+1} {line.strip()[:100]}")

for fname in os.listdir('src/app'):
    if fname.endswith('.html'):
        with open(os.path.join('src/app', fname), 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if 'lang-btn' in line or 'lang-switcher' in line:
                    print(f"{fname}:{i+1} {line.strip()[:100]}")
                    break
