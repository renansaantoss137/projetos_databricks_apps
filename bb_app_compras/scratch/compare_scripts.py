import re

for name, path in [('PROD', 'scratch/prod_performance.html'), ('CURR', 'src/app/performance.html')]:
    with open(path, encoding='utf-8') as f:
        content = f.read()
    script_srcs = re.findall(r'<script\b[^>]*src=[\'"]([^\'"]+)[\'"]', content)
    print(f'=== {name} script srcs ===')
    for s in script_srcs:
        print('  src:', s)
