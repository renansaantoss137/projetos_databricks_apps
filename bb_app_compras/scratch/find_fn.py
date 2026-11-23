import os, sys

sys.stdout.reconfigure(encoding='utf-8')
for fname in sorted(os.listdir('src/app')):
    fpath = os.path.join('src/app', fname)
    if os.path.isfile(fpath):
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if 'function toggletheme' in line.lower() or 'toggletheme =' in line.lower() or 'toggletheme()' in line.lower() and '{' in line.lower():
                    print(f"{fname}:{i+1} -> {line.strip()}")
