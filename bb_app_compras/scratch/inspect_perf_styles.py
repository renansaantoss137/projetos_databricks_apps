with open('src/app/performance.html', 'r', encoding='utf-8') as f:
    content = f.read()

import re
styles = re.findall(r'<style>([\s\S]*?)</style>', content)
print(f"Number of style tags in performance.html: {len(styles)}")
for i, s in enumerate(styles):
    for line in s.split('\n'):
        if 'th' in line.lower() or 'pa-' in line.lower() or 'table' in line.lower() or 'navbar' in line.lower() or 'light' in line.lower():
            print(f"  [style {i}] {line.strip()[:100]}")
