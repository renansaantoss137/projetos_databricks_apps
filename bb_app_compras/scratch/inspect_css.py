with open('src/app/styles.css', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '.navbar' in line or 'pa-' in line or 'th-bg' in line or 'fr-th' in line or 'th {' in line:
        print(f"L{i+1}: {line.strip()[:100]}")
