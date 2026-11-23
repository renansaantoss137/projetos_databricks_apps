with open('src/app/app.py', 'r', encoding='utf-8') as f:
    text = f.read()

idx_start = text.find("def performance_lead_time():")
idx_end = text.find("@app.route('/api/performance/attention')", idx_start)
funnel_func_code = text[idx_start:idx_end]

with open('scratch/funnel_func.py', 'w', encoding='utf-8') as f:
    f.write(funnel_func_code)

print("Saved funnel_func.py, length:", len(funnel_func_code))
