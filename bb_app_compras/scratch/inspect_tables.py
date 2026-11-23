import os, sys, re

sys.stdout.reconfigure(encoding='utf-8')

app_dir = 'src/app'
for fname in sorted(os.listdir(app_dir)):
    if fname.endswith('.html'):
        fpath = os.path.join(app_dir, fname)
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Check table headers
        ths = re.findall(r'(\.[a-zA-Z0-9_-]*table[^{]*\{[^}]*\})', content)
        th_heads = re.findall(r'([^{]*thead\s+th[^{]*\{[^}]*\})', content)
        if ths or th_heads:
            print(f"=== {fname} ===")
            for t in ths + th_heads:
                print(" ", t.strip().replace('\n', ' '))
