import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

files = ['performance.html', 'ordens.html', 'comercial.html', 'governanca.html']
for fn in files:
    path = f'src/app/{fn}'
    with open(path, encoding='utf-8') as f:
        html = f.read()
    print('='*60)
    print(f'FILE: {fn}')
    print('='*60)
    
    # Find loadKPIs or card update function in javascript
    scripts = re.findall(r'<script.*?</script>', html, re.DOTALL)
    for s in scripts:
        lines = s.split('\n')
        in_kpi = False
        kpi_lines = []
        for line in lines:
            if any(term in line for term in ['function loadKPI', 'async function loadKPI', 'function loadCards', 'async function loadCards']):
                in_kpi = True
            if in_kpi:
                kpi_lines.append(line)
                if line.strip() == '}' and len(kpi_lines) > 10:
                    in_kpi = False
                    break
        if kpi_lines:
            print('\n'.join(kpi_lines[:45]))
            print('...\n')
