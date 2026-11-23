import re

def extract_func(text, func_name):
    idx = text.find(f'async function {func_name}(')
    if idx == -1:
        idx = text.find(f'function {func_name}(')
    if idx == -1:
        return None
    # Find closing brace by counting braces
    start_brace = text.find('{', idx)
    count = 1
    i = start_brace + 1
    while count > 0 and i < len(text):
        if text[i] == '{':
            count += 1
        elif text[i] == '}':
            count -= 1
        i += 1
    return text[idx:i]

with open('scratch/prod_performance.html', encoding='utf-8') as f:
    prod_text = f.read()

with open('src/app/performance.html', encoding='utf-8') as f:
    curr_text = f.read()

for fn in ['loadKPIs', 'loadSpendYoY', 'loadDiscountChart', 'loadLeadTime', 'loadAttention', 'getFilters']:
    p_fn = extract_func(prod_text, fn)
    c_fn = extract_func(curr_text, fn)
    print(f'=== {fn} ===')
    if p_fn == c_fn:
        print('IDENTICAL')
    else:
        print('DIFFERENT!')
        if not p_fn: print('  Missing in PROD')
        if not c_fn: print('  Missing in CURR')
        if p_fn and c_fn:
            print('  PROD len:', len(p_fn), 'CURR len:', len(c_fn))
