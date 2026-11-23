with open('src/app/performance.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '_pasortclick' in line.lower() or 'pa-table' in line.lower() or 'pa_table' in line.lower() or 'price_alerts' in line.lower() or 'alertas de pre' in line.lower():
        print(f"L{i+1}: {line.strip()[:120]}")
