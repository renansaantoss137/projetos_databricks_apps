import difflib
import os

files_to_check = ['app.py', 'comercial.html', 'governanca.html', 'performance.html', 'relatorios.html', 'spend.html']

for fname in files_to_check:
    prod_path = os.path.join('scratch', 'download_prod', fname)
    local_path = os.path.join('src', 'app', fname)
    
    with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
        local_lines = f.readlines()
    with open(prod_path, 'r', encoding='utf-8', errors='ignore') as f:
        prod_lines = f.readlines()
        
    diff = list(difflib.unified_diff(local_lines, prod_lines, fromfile=f'local/{fname}', tofile=f'prod/{fname}', n=2))
    print(f"=== DIFF FOR {fname} ({len(diff)} diff lines) ===")
    for line in diff[:30]:
        print(line, end='')
    if len(diff) > 30:
        print(f"\n... and {len(diff) - 30} more diff lines ...")
    print("\n" + "="*50 + "\n")
