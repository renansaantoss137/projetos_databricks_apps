with open('src/app/app.py', 'r', encoding='utf-8') as f:
    text = f.read()

import re
patterns = [
    r'departamento_comprador',
    r'usuario_comprador',
    r'email_comprador',
    r'email_usuario',
    r'departamento_requisitante',
    r'oc\.(comprador|comprador_funcional)',
    r'nf\.(comprador|departamento_comprador)'
]

for p in patterns:
    matches = [m.start() for m in re.finditer(p, text, re.IGNORECASE)]
    print(f"Pattern '{p}': {len(matches)} occurrences")
    for idx in matches[:5]:
        start = max(0, idx - 40)
        end = min(len(text), idx + 60)
        print('   ...', text[start:end].replace('\n', ' '), '...')
