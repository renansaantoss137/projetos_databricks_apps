import difflib

with open('scratch/prod_app.py', encoding='utf-8') as f:
    prod_lines = f.readlines()

with open('src/app/app.py', encoding='utf-8') as f:
    local_lines = f.readlines()

diff = list(difflib.unified_diff(prod_lines, local_lines, fromfile='PROD', tofile='LOCAL', n=2))
print(f'Total diff lines: {len(diff)}')

chunks = []
cur_chunk = []
for line in diff:
    if line.startswith('@@'):
        if cur_chunk:
            chunks.append(cur_chunk)
        cur_chunk = [line]
    elif cur_chunk:
        cur_chunk.append(line)
if cur_chunk:
    chunks.append(cur_chunk)

print(f'Total diff chunks: {len(chunks)}')
for i, chunk in enumerate(chunks[:10]):
    print(f'--- CHUNK {i+1} ---')
    print(''.join(chunk[:15]))
